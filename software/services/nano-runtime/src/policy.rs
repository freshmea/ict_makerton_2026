use super::*;
use pico_device_bench::{IpcRequest, TestModule};
async fn udp(c: &Context, command: &IpcRequest) -> Result<Value> {
    let _ = c;
    let reply = pico_device_bench::udp_roundtrip("127.0.0.1:37920".parse()?, command).await?;
    if reply["ok"] != true {
        return Err(error(reply.to_string()));
    }
    Ok(reply)
}
pub async fn stop(c: &Context) -> Result<Value> {
    let _stop_guard = c.stop_gate.lock().await;
    c.pico_arm_uptime.store(0, Ordering::SeqCst);
    if c.role == "controllerd" {
        c.problem.write().await.clear();
        c.last_request.write().await.clear();
    }
    if let Some(job) = c.job.lock().await.take() {
        job.abort();
        let _ = job.await;
    }
    if let Some(path) = c.external_audio.lock().await.take() {
        let _ = tokio::fs::remove_dir_all(path).await;
    }
    {
        let mut s = c.turn_state.write().await;
        s["phase"] = json!("cancelled");
    }
    {
        let mut lease = c.lease.lock().await;
        lease.stop();
        c.stopping.store(true, Ordering::SeqCst);
    }
    let result = match c.role.as_str() {
        "picod" => udp(c, &IpcRequest::Stop).await,
        "audiod" => {
            c.reset.store(true, Ordering::SeqCst);
            let start = monotonic_ms();
            while c.reset.load(Ordering::SeqCst) && monotonic_ms() - start < 2000 {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
            if c.reset.load(Ordering::SeqCst) {
                Err(error("device flush unconfirmed"))
            } else {
                Ok(json!({"device_flushed":true}))
            }
        }
        "controllerd" => {
            let mut p = c.policy.lock().await;
            p.epoch += 1;
            p.phase = "stopped".into();
            drop(p);
            stop_children(c).await
        }
        _ => Ok(json!({"stopped":true})),
    };
    // A failed Stop remains latched; no rearm until manual service recovery.
    if result.is_ok() {
        c.stopping.store(false, Ordering::SeqCst)
    }
    result
}
pub(crate) async fn stop_children(c: &Context) -> Result<Value> {
    let (a, p, d) = tokio::join!(
        rpc(&c.root, "audiod", Command::Stop),
        rpc(&c.root, "picod", Command::Stop),
        timeout(
            Duration::from_millis(350),
            rpc(&c.root, "dialogued", Command::Stop)
        )
    );
    match (a, p) {
        (Ok(a), Ok(p)) => {
            Ok(json!({"audio":a,"pico":p,"dialogue_cancelled":matches!(d,Ok(Ok(_)))}))
        }
        (a, p) => Err(error(format!("Stop unconfirmed: audio={a:?}, pico={p:?}"))),
    }
}
pub async fn dispatch(c: &Context, cmd: Command) -> Result<Value> {
    if matches!(cmd, Command::Stop) {
        return stop(c).await;
    }
    if matches!(cmd, Command::Status) {
        let state = c.state.read().await.clone();
        let lease = c.lease.lock().await;
        let p = c.policy.lock().await;
        let received = state["received_ms"].as_u64().unwrap_or(0);
        return Ok(
            json!({"role":c.role,"generation":c.generation,"monotonic_ms":monotonic_ms(),"fresh":received>0&&monotonic_ms().saturating_sub(received)<1500,"lease_valid":lease.valid(monotonic_ms()),"epoch":lease.epoch,"phase":p.phase,"turn_epoch":p.epoch,"state":state}),
        );
    }
    match (&*c.role, cmd) {
        ("dialogued", Command::Usage) => {
            let mut v = budget::status()?;
            v["tts"] = match timeout(Duration::from_millis(1500), typecast::usage()).await {
                Ok(Ok(v)) => v,
                Ok(Err(e)) => json!({"provider":"typecast","error":e.to_string()}),
                Err(_) => {
                    json!({"provider":"typecast","account_remaining":"unknown; account lookup timeout"})
                }
            };
            Ok(v)
        }
        ("controllerd" | "dialogued" | "visiond", Command::TurnResult) => {
            let mut s = c.turn_state.read().await.clone();
            if c.role == "controllerd" {
                s["confirmed_problem"] = json!(c.problem.read().await.clone());
            }
            Ok(s)
        }
        (
            "controllerd",
            Command::StartTurn {
                text,
                listen,
                cloud_consent,
                audio_cloud_consent,
                speak,
            },
        ) => turns::start(c, text, listen, cloud_consent, audio_cloud_consent, speak).await,
        (
            "controllerd",
            Command::Correct {
                text,
                cloud_consent,
                speak,
            },
        ) => {
            let previous = c.last_request.read().await.clone();
            let problem = c.problem.read().await.clone();
            stop(c).await?;
            let corrected = if previous.is_empty() {
                text
            } else {
                json!({"previous_request":previous,"user_correction":text,"confirmed_problem":problem}).to_string()
            };
            turns::start(c, Some(corrected), false, cloud_consent, false, speak).await
        }
        (
            "dialogued",
            Command::Dialogue {
                owner,
                epoch,
                text,
                cloud_consent,
                audio_wav,
                synthesize,
            },
        ) => turns::dialogue(c, owner, epoch, text, cloud_consent, audio_wav, synthesize).await,
        ("controllerd", Command::ConfirmProblem { text }) => {
            if text.len() > 2048 {
                return Err(error("confirmed problem size invalid"));
            }
            let confirmed = !text.trim().is_empty();
            *c.problem.write().await = text;
            Ok(json!({"confirmed":confirmed}))
        }
        ("memoryd", Command::Memory { request }) => {
            let _g = c.memory_gate.lock().await;
            learning::execute(
                &env("NANO_DB", "/var/lib/300seconds/runtime.sqlite3"),
                request,
            )
        }
        ("camerad", Command::Snapshot { camera }) => {
            if camera > 1 {
                return Err(error("camera must be 0 or 1"));
            }
            let i = camera as usize;
            let seq = c.image_seq[i].load(Ordering::SeqCst);
            c.image_request.fetch_or(1 << camera, Ordering::SeqCst);
            let start = monotonic_ms();
            while c.image_seq[i].load(Ordering::SeqCst) == seq && monotonic_ms() - start < 1800 {
                tokio::time::sleep(Duration::from_millis(20)).await;
            }
            if c.image_seq[i].load(Ordering::SeqCst) == seq {
                return Err(error("snapshot timeout"));
            }
            Ok(
                json!({"camera":camera,"generation":c.generation,"snapshot_id":c.image_seq[i].load(Ordering::SeqCst),"path":c.root.join(format!("problem-{camera}.jpg")),"width":1280,"height":720}),
            )
        }
        (
            "visiond",
            Command::Ocr {
                camera,
                roi,
                rotation,
            },
        ) => {
            let mut slot = c.job.lock().await;
            if slot.as_ref().is_some_and(|j| !j.is_finished()) {
                return Err(error("OCR busy"));
            }
            let snapshot = rpc(&c.root, "camerad", Command::Snapshot { camera }).await?;
            let temp = local_ai::Temporary(local_ai::private_dir(c, monotonic_ms())?);
            let image = temp.0.join("problem.jpg");
            tokio::fs::copy(
                snapshot["path"]
                    .as_str()
                    .ok_or_else(|| error("snapshot path missing"))?,
                &image,
            )
            .await?;
            *c.turn_state.write().await = json!({"phase":"running","snapshot":snapshot});
            let worker = c.clone();
            *slot = Some(tokio::spawn(async move {
                let _temp = temp;
                let r = local_ai::worker(
                    json!({"op":"ocr","image":image,"roi":roi,"rotation":rotation}),
                )
                .await;
                *worker.turn_state.write().await = match r {
                    Ok(v) => json!({"phase":"done","result":v}),
                    Err(e) => json!({"phase":"failed","error":e.to_string()}),
                };
            }));
            Ok(json!({"started":true,"poll":"visiond turn_result"}))
        }
        ("picod" | "audiod", Command::Acquire { owner, epoch }) => {
            let _stop_guard = c.stop_gate.lock().await;
            let state = c.state.read().await;
            let received = state["received_ms"].as_u64().unwrap_or(0);
            if received == 0 || monotonic_ms().saturating_sub(received) > 1500 {
                return Err(error("device telemetry unavailable; lease denied"));
            }
            drop(state);
            let mut lease = c.lease.lock().await;
            if c.stopping.load(Ordering::SeqCst) {
                return Err(error("Stop cleanup not complete"));
            }
            lease.acquire(owner, epoch, monotonic_ms())?;
            drop(lease);
            drop(_stop_guard); // A slow Arm must not block a new Stop.
            if c.role == "picod" {
                let config: pico_device_protocol::ActuatorConfig =
                    serde_json::from_str(&std::fs::read_to_string(env(
                        "NANO_ACTUATORS",
                        "/opt/300seconds/runtime/actuators.json",
                    ))?)?;
                let reply = match udp(c, &IpcRequest::Arm { config }).await {
                    Ok(v) => v,
                    Err(e) => {
                        c.lease.lock().await.stop();
                        return Err(e);
                    }
                };
                if reply["status"]["outputs"]["armed"] != true {
                    c.lease.lock().await.stop();
                    return Err(error("Pico Arm not confirmed by output snapshot"));
                }
                c.pico_arm_uptime.store(
                    reply["status"]["device"]["uptime_ms"].as_u64().unwrap_or(0),
                    Ordering::SeqCst,
                );
            }
            Ok(json!({"lease_ms":host_core::LEASE_MS}))
        }
        ("picod" | "audiod", Command::Renew { owner, epoch }) => {
            c.lease.lock().await.renew(owner, epoch, monotonic_ms())?;
            Ok(json!({"renewed":true}))
        }
        (
            "picod",
            Command::Test {
                owner,
                epoch,
                module,
            },
        ) => {
            let module = TestModule::parse(&module).ok_or_else(|| error("unknown module"))?;
            if matches!(module, TestModule::Matrix | TestModule::All) {
                return Err(error("matrix/touch installation missing; test blocked"));
            }
            // Holding only through send orders the request before any Stop;
            // reply waiting never holds the lease mutex.
            let socket = tokio::net::UdpSocket::bind("127.0.0.1:0").await?;
            socket.connect("127.0.0.1:37920").await?;
            let lease = c.lease.lock().await;
            lease.check(owner, epoch, monotonic_ms())?;
            c.pico_arm_uptime.store(0, Ordering::SeqCst);
            socket
                .send(&serde_json::to_vec(&IpcRequest::Test { module })?)
                .await?;
            drop(lease);
            let mut buf = [0; 8193];
            let n = timeout(Duration::from_secs(4), socket.recv(&mut buf)).await??;
            if n > 8192 {
                return Err(error("oversize USB response"));
            }
            let result: Value = serde_json::from_slice(&buf[..n])?;
            if result["ok"] != true {
                return Err(error(result.to_string()));
            }
            Ok(result)
        }
        ("controllerd", Command::Help) => {
            // A local MCU Stop publishes stopped before child flush completes.
            // Wait for that Stop before granting the next turn's device leases.
            let _stop_guard = c.stop_gate.lock().await;
            let epoch = {
                let mut p = c.policy.lock().await;
                if p.phase == "starting" || p.phase == "help_requested" || p.phase == "finishing" {
                    return Err(error(
                        "turn already active; Stop or Finish before a new Help",
                    ));
                }
                p.epoch += 1;
                p.phase = "starting".into();
                p.epoch
            };
            drop(_stop_guard); // Stop must still preempt slow device acquisition.
            for role in ["picod", "audiod"] {
                if let Err(e) = rpc(
                    &c.root,
                    role,
                    Command::Acquire {
                        owner: c.generation,
                        epoch,
                    },
                )
                .await
                {
                    let _ = stop_children(c).await;
                    let mut p = c.policy.lock().await;
                    if p.epoch == epoch {
                        p.phase = "fault".into()
                    }
                    return Err(e);
                }
            }
            let mut p = c.policy.lock().await;
            if p.epoch != epoch || p.phase != "starting" {
                drop(p);
                let _ = stop_children(c).await;
                return Err(error("help cancelled while acquiring devices"));
            }
            p.phase = "help_requested".into();
            Ok(json!({"epoch":epoch,"state":"help_requested","llm_invoked":false}))
        }
        ("controllerd", Command::Finish) => {
            stop(c).await?;
            c.policy.lock().await.phase = "quiet".into();
            Ok(json!({"state":"quiet"}))
        }
        ("controllerd", Command::Test { module, .. }) => {
            let p = c.policy.lock().await;
            if p.phase != "help_requested" {
                return Err(error("explicit Help required before a test"));
            }
            let epoch = p.epoch;
            drop(p);
            rpc(
                &c.root,
                "picod",
                Command::Test {
                    owner: c.generation,
                    epoch,
                    module,
                },
            )
            .await
        }
        (
            "controllerd",
            Command::Pose {
                targets_cdeg,
                move_ms,
                ..
            },
        ) => {
            let p = c.policy.lock().await;
            if p.phase != "help_requested" {
                return Err(error("explicit Help required for pose"));
            }
            let epoch = p.epoch;
            drop(p);
            rpc(
                &c.root,
                "picod",
                Command::Pose {
                    owner: c.generation,
                    epoch,
                    targets_cdeg,
                    move_ms,
                },
            )
            .await
        }
        (
            "controllerd",
            Command::Light {
                rgb,
                brightness,
                period_ms,
                ..
            },
        ) => {
            let p = c.policy.lock().await;
            if p.phase != "help_requested" {
                return Err(error("explicit Help required for light"));
            }
            let epoch = p.epoch;
            drop(p);
            rpc(
                &c.root,
                "picod",
                Command::Light {
                    owner: c.generation,
                    epoch,
                    rgb,
                    brightness,
                    period_ms,
                },
            )
            .await
        }
        (
            "controllerd",
            Command::Eyes {
                left,
                right,
                brightness,
                ..
            },
        ) => {
            let p = c.policy.lock().await;
            if p.phase != "help_requested" {
                return Err(error("explicit Help required for eyes"));
            }
            let epoch = p.epoch;
            drop(p);
            rpc(
                &c.root,
                "picod",
                Command::Eyes {
                    owner: c.generation,
                    epoch,
                    left,
                    right,
                    brightness,
                },
            )
            .await
        }
        (
            "picod",
            Command::Pose {
                owner,
                epoch,
                targets_cdeg,
                move_ms,
            },
        ) => {
            actuate(
                c,
                owner,
                epoch,
                IpcRequest::Pose {
                    targets_cdeg,
                    move_ms,
                },
            )
            .await
        }
        (
            "picod",
            Command::Light {
                owner,
                epoch,
                rgb,
                brightness,
                period_ms,
            },
        ) => {
            actuate(
                c,
                owner,
                epoch,
                IpcRequest::Light {
                    rgb,
                    brightness,
                    period_ms,
                },
            )
            .await
        }
        (
            "picod",
            Command::Eyes {
                owner,
                epoch,
                left,
                right,
                brightness,
            },
        ) => {
            actuate(
                c,
                owner,
                epoch,
                IpcRequest::Eyes {
                    left,
                    right,
                    brightness,
                },
            )
            .await
        }
        ("memoryd", Command::PutGoal { text }) => {
            if text.is_empty() || text.len() > 2048 {
                return Err(error("goal must be 1..2048 UTF-8 bytes"));
            }
            native::goal(
                &env("NANO_DB", "/var/lib/300seconds/runtime.sqlite3"),
                1,
                &text,
            )?;
            Ok(json!({"saved":true}))
        }
        ("memoryd", Command::GetGoal) => Ok(
            json!({"goal":native::goal(&env("NANO_DB","/var/lib/300seconds/runtime.sqlite3"),0,"")?}),
        ),
        ("memoryd", Command::DeleteGoal) => {
            native::goal(
                &env("NANO_DB", "/var/lib/300seconds/runtime.sqlite3"),
                2,
                "",
            )?;
            Ok(json!({"deleted":true}))
        }
        ("dialogued", Command::Decide { .. }) => Err(error(
            "use controllerd start_turn; direct model calls cannot bypass a user turn",
        )),
        _ => Err(error("command not supported by this service")),
    }
}
async fn actuate(c: &Context, owner: u64, epoch: u64, command: IpcRequest) -> Result<Value> {
    command.validate()?;
    let socket = tokio::net::UdpSocket::bind("127.0.0.1:0").await?;
    socket.connect("127.0.0.1:37920").await?;
    let lease = c.lease.lock().await;
    lease.check(owner, epoch, monotonic_ms())?;
    socket.send(&serde_json::to_vec(&command)?).await?;
    drop(lease);
    let mut b = [0; 8193];
    let n = timeout(Duration::from_secs(3), socket.recv(&mut b)).await??;
    if n > 8192 {
        return Err(error("oversize actuator response"));
    }
    let v: Value = serde_json::from_slice(&b[..n])?;
    if v["ok"] != true {
        return Err(error(v.to_string()));
    }
    Ok(v)
}
pub async fn watchdog(c: Context) {
    let mut tick = tokio::time::interval(Duration::from_millis(50));
    while !c.shutdown.load(Ordering::SeqCst) {
        tick.tick().await;
        if c.role == "picod"
            && c.pico_arm_uptime.load(Ordering::SeqCst) > 0
            && c.lease.lock().await.valid(monotonic_ms())
        {
            let s = c.state.read().await;
            let t = &s["telemetry"];
            let local_stop = t["status"]["uptime_ms"].as_u64().unwrap_or(0)
                >= c.pico_arm_uptime.load(Ordering::SeqCst)
                && t["outputs"]["armed"] == false;
            drop(s);
            if local_stop {
                c.pico_arm_uptime.store(0, Ordering::SeqCst);
                c.lease.lock().await.stop();
                eprintln!("MCU disarmed/fault -> revoke host turn and flush audio");
                let stopped = timeout(
                    Duration::from_millis(400),
                    rpc(&c.root, "controllerd", Command::Stop),
                )
                .await;
                // A successful controller Stop already flushed audiod. A
                // second Stop here could arrive after the next Help and
                // revoke its newly acquired audio lease.
                if !matches!(stopped, Ok(Ok(_))) {
                    let _ = rpc(&c.root, "audiod", Command::Stop).await;
                }
            }
        }
        if ["picod", "audiod"].contains(&c.role.as_str())
            && c.lease.lock().await.expire(monotonic_ms())
        {
            eprintln!("{}: controller lease expired -> Stop", c.role);
            let _ = stop(&c).await;
        }
        if c.role == "controllerd" {
            let p = c.policy.lock().await;
            let active = p.phase == "help_requested";
            let epoch = p.epoch;
            drop(p);
            if active {
                for role in ["picod", "audiod"] {
                    if rpc(
                        &c.root,
                        role,
                        Command::Renew {
                            owner: c.generation,
                            epoch,
                        },
                    )
                    .await
                    .is_err()
                    {
                        // A renewal can finish after the turn's normal Stop.
                        // Serialize with completion/Stop and recheck its epoch
                        // before revoking anything; never stop a newer turn.
                        let _stop_guard = c.stop_gate.lock().await;
                        let mut p = c.policy.lock().await;
                        if p.epoch != epoch || p.phase != "help_requested" {
                            break;
                        }
                        p.epoch += 1;
                        p.phase = "fault".into();
                        drop(p);
                        let _ = stop_children(&c).await;
                        break;
                    }
                }
            }
        }
    }
}
