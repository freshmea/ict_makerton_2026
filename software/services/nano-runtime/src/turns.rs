use super::*;
use host_core::decision::{self, Action};
pub async fn current(c: &Context, epoch: u64) -> Result<()> {
    let p = c.policy.lock().await;
    if c.shutdown.load(Ordering::SeqCst)
        || c.stopping.load(Ordering::SeqCst)
        || p.epoch != epoch
        || p.phase != "help_requested"
    {
        return Err(error("turn_cancelled_or_stale"));
    }
    Ok(())
}
pub async fn start(
    c: &Context,
    text: Option<String>,
    listen: bool,
    consent: bool,
    audio_consent: bool,
    speak: bool,
) -> Result<Value> {
    if text
        .as_ref()
        .map(|s| s.trim().is_empty() || s.len() > 2048)
        .unwrap_or(false)
        || text.is_none() && !listen
    {
        return Err(error("provide text or listen=true"));
    }
    let slot = c.job.lock().await;
    if slot.as_ref().is_some_and(|h| !h.is_finished()) {
        return Err(error("turn_busy; stop or correct first"));
    }
    // Help waits on the Stop gate. Never wait there while holding the job
    // mutex, because Stop needs the job mutex to cancel an active turn.
    drop(slot);
    if c.policy.lock().await.phase != "help_requested" {
        Box::pin(policy::dispatch(c, Command::Help)).await?;
    }
    let mut slot = c.job.lock().await;
    if slot.as_ref().is_some_and(|h| !h.is_finished()) {
        return Err(error("turn_busy; stop or correct first"));
    }
    let p = c.policy.lock().await;
    if p.phase != "help_requested" {
        return Err(error("turn_cancelled_before_start"));
    }
    let epoch = p.epoch;
    drop(p);
    if let Some(t) = text.as_ref() {
        *c.last_request.write().await = t.clone();
    }
    *c.turn_state.write().await =
        json!({"phase":"running","epoch":epoch,"stage":if listen{"listening"}else{"classifying"}});
    let worker = c.clone();
    *slot = Some(tokio::spawn(async move {
        let result = execute(&worker, epoch, text, listen, consent, audio_consent, speak).await;
        let _guard = worker.stop_gate.lock().await;
        let mut p = worker.policy.lock().await;
        let valid = p.epoch == epoch && p.phase == "help_requested";
        if valid {
            p.phase = "finishing".into();
        }
        drop(p);
        if valid {
            let cleanup = policy::stop_children(&worker).await;
            let mut p = worker.policy.lock().await;
            if p.epoch == epoch {
                p.epoch += 1;
                p.phase = if cleanup.is_ok() { "quiet" } else { "fault" }.into();
            }
            *worker.turn_state.write().await = match (result, cleanup) {
                (Ok(v), Ok(_)) => json!({"phase":"done","epoch":epoch,"result":v}),
                (r, s) => {
                    json!({"phase":"failed","epoch":epoch,"error":r.err().map(|e|e.to_string()),"stop_error":s.err().map(|e|e.to_string()),"spoken_result_confirmed":false})
                }
            };
        }
    }));
    Ok(json!({"started":true,"epoch":epoch,"poll":"turn_result"}))
}
async fn execute(
    c: &Context,
    epoch: u64,
    text: Option<String>,
    listen: bool,
    consent: bool,
    audio_consent: bool,
    speak: bool,
) -> Result<Value> {
    let mut provenance = Vec::new();
    let mut audio_temp = None;
    let mut audio_wav = None;
    let text = if listen && audio_consent && consent {
        let temp = local_ai::Temporary(local_ai::private_dir(c, epoch)?);
        let wav = temp.0.join("asr.wav");
        tokio::fs::write(&wav, local_ai::capture(c, epoch).await?).await?;
        audio_wav = Some(wav.to_string_lossy().into_owned());
        audio_temp = Some(temp);
        "Explicit user audio help request; use the attached utterance.".into()
    } else if listen {
        let a = local_ai::listen(c, epoch).await?;
        let t = a["text"].as_str().unwrap_or("").to_owned();
        return Ok(
            json!({"action":"confirm_transcript","recognized_text":t,"asr":a,"spoken":false,"cloud_calls":0,"next":"Confirm or correct this text with a new explicit help request. Local ASR confidence is not calibrated."}),
        );
    } else {
        text.unwrap_or_default()
    };
    current(c, epoch).await?;
    if let Some(a) = host_core::speech::local_intent(&text) {
        if a == Action::EndSession {
            c.problem.write().await.clear();
            c.last_request.write().await.clear();
        }
        return Ok(
            json!({"action":a,"source":"local_explicit_intent","spoken":false,"provenance":provenance}),
        );
    }
    if !consent {
        return Err(error("cloud_consent_required; no external request made"));
    }
    *c.turn_state.write().await =
        json!({"phase":"running","epoch":epoch,"stage":"decision_and_generation"});
    rpc(
        &c.root,
        "dialogued",
        Command::Dialogue {
            owner: c.generation,
            epoch,
            text,
            cloud_consent: consent,
            audio_wav,
            synthesize: speak,
        },
    )
    .await?;
    let start = monotonic_ms();
    let result = loop {
        current(c, epoch).await?;
        if monotonic_ms() - start > 45000 {
            let _ = rpc(&c.root, "dialogued", Command::Stop).await;
            return Err(error("dialogue_deadline"));
        }
        let v = rpc(&c.root, "dialogued", Command::TurnResult).await?;
        if v["epoch"] == epoch && v["phase"] == "done" {
            break v["result"].clone();
        }
        if v["epoch"] == epoch && v["phase"] == "failed" {
            return Err(error(format!("dialogue_failed:{}", v["error"])));
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    };
    current(c, epoch).await?;
    drop(audio_temp);
    if result["action"] == "end_session" {
        c.problem.write().await.clear();
        c.last_request.write().await.clear();
    }
    let hint = result["hint"].as_str().unwrap_or("");
    if speak && !hint.is_empty() {
        *c.turn_state.write().await =
            json!({"phase":"running","epoch":epoch,"stage":"speaking","hint":hint});
        let audio = result["tts"]["path"].as_str().map(PathBuf::from);
        provenance.push(json!({"tts":local_ai::speak(c,hint,epoch,audio.as_deref(),result["tts"]["backend"].as_str().unwrap_or("supertonic")).await?}));
    }
    Ok(
        json!({"dialogue":result,"spoken":speak&&!hint.is_empty(),"provenance":provenance,"next":"quiet; explicit next request required"}),
    )
}
async fn check_controller(c: &Context, owner: u64, epoch: u64) -> Result<()> {
    let s = rpc(&c.root, "controllerd", Command::Status).await?;
    if s["generation"] != owner || s["turn_epoch"] != epoch || s["phase"] != "help_requested" {
        return Err(error("controller_turn_revoked"));
    }
    Ok(())
}
pub async fn dialogue(
    c: &Context,
    owner: u64,
    epoch: u64,
    text: String,
    consent: bool,
    audio_wav: Option<String>,
    synthesize: bool,
) -> Result<Value> {
    if !consent || text.trim().is_empty() || text.len() > 2048 {
        return Err(error("dialogue requires consent and bounded text"));
    }
    check_controller(c, owner, epoch).await?;
    let mut slot = c.job.lock().await;
    if slot.as_ref().is_some_and(|h| !h.is_finished()) {
        return Err(error("dialogue_busy"));
    }
    *c.turn_state.write().await = json!({"phase":"running","epoch":epoch});
    let worker = c.clone();
    *slot = Some(tokio::spawn(async move {
        let work = async {
            let goal = rpc(&worker.root, "memoryd", Command::GetGoal).await?;
            let query = text.split_whitespace().next().unwrap_or("").to_owned();
            let memories = rpc(
                &worker.root,
                "memoryd",
                Command::Memory {
                    request: host_core::MemoryRequest::Search { query },
                },
            )
            .await?;
            let vision = rpc(&worker.root, "visiond", Command::Status)
                .await
                .unwrap_or(json!({"fresh":false}));
            let observations = if vision["fresh"] == true {
                vision["state"].clone()
            } else {
                json!({"presence":"unknown","stale":true})
            };
            let controller = rpc(&worker.root, "controllerd", Command::TurnResult).await?;
            let input = json!({"help_requested":true,"user_text":text,"goal":goal,"confirmed_memories":memories,"observations":observations,"confirmed_problem":controller["confirmed_problem"],"allowed_actions":["wait","clarify","offer_hint","end_session"]});
            let combined = env("NANO_DECISION_PROVIDER", "gemini") == "gemini"
                && env("NANO_GENERATION_PROVIDER", "gemini") == "gemini";
            let audio = if let Some(path) = audio_wav.as_ref() {
                let path = std::fs::canonicalize(path)?;
                let root = std::fs::canonicalize(&worker.root)?;
                let parent = path
                    .parent()
                    .and_then(|p| p.file_name())
                    .and_then(|s| s.to_str())
                    .unwrap_or("");
                if !path.starts_with(root)
                    || !parent.starts_with(&format!("turn-{owner}-{epoch}-"))
                    || path.file_name().and_then(|s| s.to_str()) != Some("asr.wav")
                {
                    return Err(error("audio path outside current private turn"));
                }
                let meta = std::fs::metadata(&path)?;
                if meta.len() > 1_100_000 || meta.len() < 44 {
                    return Err(error("audio upload size invalid"));
                }
                Some(tokio::fs::read(path).await?)
            } else {
                None
            };
            if audio.is_some() && !combined {
                return Err(error(
                    "single-call audio path requires Gemini decision and generation",
                ));
            }
            let (d, classification, candidate_hint) = if combined {
                let (d, h, m) = providers::combined_gemini(&input, epoch, audio.as_deref()).await?;
                (d, m, Some(h))
            } else {
                let (d, m) = providers::decide(&input, epoch).await?;
                (d, m, None)
            };
            check_controller(&worker, owner, epoch).await?;
            let action = decision::permit(&d, epoch, monotonic_ms(), true, false);
            let (hint, generation) = match action {
                Action::OfferHint => {
                    if let Some(h) = candidate_hint {
                        (h, json!({"same_request_as_classification":true}))
                    } else {
                        providers::generate(&input).await?
                    }
                }
                Action::Clarify => (
                    "어느 부분에서 도움이 필요한지 한 가지만 알려 줄래?".into(),
                    json!({"provider":"local_fixed_clarification"}),
                ),
                _ => (String::new(), Value::Null),
            };
            let (hint, numeric_hint_replaced) = providers::guard_hint(&hint);
            check_controller(&worker, owner, epoch).await?;
            let tts = if synthesize
                && !hint.is_empty()
                && env("NANO_TTS_BACKEND", "typecast") == "typecast"
            {
                let (wav, mut metadata) = typecast::synthesize(&hint).await?;
                check_controller(&worker, owner, epoch).await?;
                let directory = local_ai::private_dir(&worker, epoch)?;
                *worker.external_audio.lock().await = Some(directory.clone());
                let path = directory.join("typecast.wav");
                tokio::fs::write(&path, wav).await?;
                metadata["path"] = json!(path);
                metadata
            } else {
                json!({"backend":env("NANO_TTS_BACKEND","typecast")})
            };
            Ok::<Value, Box<dyn std::error::Error + Send + Sync>>(
                json!({"action":action,"confidence":d.confidence,"hint":hint,"classification":classification,"generation":generation,"raw_media_uploaded":audio.is_some(),"tts":tts,"numeric_hint_replaced":numeric_hint_replaced,"semantic_correctness":"not guaranteed; conceptual hint only"}),
            )
        };
        let cancel = async {
            loop {
                tokio::time::sleep(Duration::from_millis(100)).await;
                if check_controller(&worker, owner, epoch).await.is_err() {
                    break;
                }
            }
        };
        let r = tokio::select! {r=work=>r,_=cancel=>Err(error("controller_revoked; transport_cancelled"))};
        *worker.turn_state.write().await = match r {
            Ok(v) => json!({"phase":"done","epoch":epoch,"result":v}),
            Err(e) => json!({"phase":"failed","epoch":epoch,"error":e.to_string()}),
        };
    }));
    Ok(json!({"started":true,"epoch":epoch}))
}
