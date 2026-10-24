use host_core::{
    error, monotonic_ms, read_frame, write_frame, Command, Lease, Reply, Request, Result,
};
use serde_json::{json, Value};
use std::{
    fs::OpenOptions,
    os::{
        fd::AsRawFd,
        unix::fs::{FileTypeExt, PermissionsExt},
    },
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
};
use tokio::{
    io::{AsyncBufReadExt, BufReader},
    net::{UnixListener, UnixStream},
    sync::{watch, Mutex, RwLock, Semaphore},
    time::{timeout, Duration},
};
mod budget;
mod learning;
mod local_ai;
mod media;
mod native;
mod policy;
mod providers;
mod turns;
mod typecast;
#[derive(Default)]
struct Policy {
    phase: String,
    epoch: u64,
}
struct Shared {
    root: PathBuf,
    role: String,
    generation: u64,
    lease: Mutex<Lease>,
    stopping: AtomicBool,
    state: RwLock<Value>,
    policy: Mutex<Policy>,
    shutdown: AtomicBool,
    pcm: watch::Sender<Arc<Vec<u8>>>,
    audio_tx: std::sync::mpsc::SyncSender<Vec<u8>>,
    reset: AtomicBool,
    stop_gate: Mutex<()>,
    job: Mutex<Option<tokio::task::JoinHandle<()>>>,
    turn_state: RwLock<Value>,
    problem: RwLock<String>,
    last_request: RwLock<String>,
    memory_gate: Mutex<()>,
    image_request: std::sync::atomic::AtomicU32,
    image_seq: [std::sync::atomic::AtomicU64; 2],
    pico_arm_uptime: std::sync::atomic::AtomicU64,
    external_audio: Mutex<Option<PathBuf>>,
}
type Context = Arc<Shared>;
fn env(name: &str, default: &str) -> String {
    std::env::var(name).unwrap_or_else(|_| default.to_owned())
}
async fn rpc(root: &std::path::Path, role: &str, cmd: Command) -> Result<Value> {
    let stop = matches!(cmd, Command::Stop);
    let req = Request::new(cmd);
    let mut stream = timeout(
        Duration::from_millis(300),
        UnixStream::connect(root.join(format!(
            "{role}.{}.sock",
            if stop { "stop" } else { "control" }
        ))),
    )
    .await??;
    write_frame(&mut stream, &serde_json::to_vec(&req)?).await?;
    let bytes = timeout(Duration::from_secs(3), read_frame(&mut stream)).await??;
    let reply: Reply = serde_json::from_slice(&bytes)?;
    if reply.id != req.id || reply.v != 1 {
        return Err(error("mismatched RPC reply"));
    }
    if !reply.ok {
        return Err(error(reply.data.to_string()));
    }
    Ok(reply.data)
}
fn socket(root: &std::path::Path, name: &str) -> Result<UnixListener> {
    let path = root.join(name);
    if let Ok(meta) = std::fs::symlink_metadata(&path) {
        if !meta.file_type().is_socket() {
            return Err(error("refusing to replace non-socket"));
        }
        std::fs::remove_file(&path)?;
    }
    let s = UnixListener::bind(&path)?;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o660))?;
    Ok(s)
}
fn peer(stream: &UnixStream) -> Result<()> {
    if stream.peer_cred()?.uid() != unsafe { libc::geteuid() } {
        return Err(error("control socket requires same service uid"));
    }
    Ok(())
}
async fn serve(ctx: Context) -> Result<()> {
    let listener = socket(&ctx.root, &format!("{}.control.sock", ctx.role))?;
    let capacity = Arc::new(Semaphore::new(16));
    loop {
        let (mut stream, _) = listener.accept().await?;
        if peer(&stream).is_err() {
            continue;
        }
        let Ok(permit) = capacity.clone().try_acquire_owned() else {
            continue;
        };
        let c = ctx.clone();
        tokio::spawn(async move {
            let _permit = permit;
            let result: Result<()> = async {
                let bytes = timeout(Duration::from_millis(500), read_frame(&mut stream)).await??;
                let request: Request = serde_json::from_slice(&bytes)?;
                let id = request.id;
                let result = match request.validate() {
                    Ok(()) => policy::dispatch(&c, request.body).await,
                    Err(e) => Err(e),
                };
                let reply = Reply {
                    v: 1,
                    id,
                    generation: c.generation,
                    ok: result.is_ok(),
                    data: result.unwrap_or_else(|e| json!({"error":e.to_string()})),
                };
                timeout(
                    Duration::from_millis(500),
                    write_frame(&mut stream, &serde_json::to_vec(&reply)?),
                )
                .await??;
                Ok(())
            }
            .await;
            if let Err(e) = result {
                eprintln!("{} RPC: {e}", c.role)
            }
        });
    }
}
async fn serve_stop(ctx: Context) -> Result<()> {
    let listener = socket(&ctx.root, &format!("{}.stop.sock", ctx.role))?;
    let capacity = Arc::new(Semaphore::new(4));
    loop {
        let (mut stream, _) = listener.accept().await?;
        if peer(&stream).is_err() {
            continue;
        }
        let Ok(permit) = capacity.clone().try_acquire_owned() else {
            continue;
        };
        let c = ctx.clone();
        tokio::spawn(async move {
            let _permit = permit;
            let result: Result<()> = async {
                let bytes = timeout(Duration::from_millis(100), read_frame(&mut stream)).await??;
                let req: Request = serde_json::from_slice(&bytes)?;
                req.validate()?;
                let r = if matches!(req.body, Command::Stop) {
                    policy::stop(&c).await
                } else {
                    Err(error("stop-only endpoint"))
                };
                let reply = Reply {
                    v: 1,
                    id: req.id,
                    generation: c.generation,
                    ok: r.is_ok(),
                    data: r.unwrap_or_else(|e| json!({"error":e.to_string()})),
                };
                timeout(
                    Duration::from_millis(500),
                    write_frame(&mut stream, &serde_json::to_vec(&reply)?),
                )
                .await??;
                Ok(())
            }
            .await;
            if let Err(e) = result {
                eprintln!("Stop endpoint: {e}")
            }
        });
    }
}
async fn bridge(ctx: Context) -> Result<tokio::process::Child> {
    let mut command = tokio::process::Command::new(env(
        "NANO_BRIDGE",
        "/opt/300seconds/dashboard/pico-device-bench",
    ));
    command.args([
        "--port",
        &env("NANO_PICO", "/dev/pico-device"),
        "bridge",
        "--config",
        &env("NANO_CONFIG", "/opt/300seconds/runtime/pico-config.json"),
        "--listen",
        "127.0.0.1:37920",
    ]);
    command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::inherit())
        .kill_on_drop(true);
    // Parent death also terminates USB owner after an abrupt picod kill.
    unsafe {
        command.pre_exec(|| {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    let mut child = command.spawn()?;
    let stdout = child.stdout.take().unwrap();
    tokio::spawn(async move {
        let mut lines = BufReader::new(stdout).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if line.len() > 65536 {
                break;
            }
            if let Ok(v) = serde_json::from_str::<Value>(&line) {
                if v["event"] == "status" {
                    *ctx.state.write().await = json!({"received_ms":monotonic_ms(),"telemetry":v});
                }
            }
        }
        *ctx.state.write().await = json!({"error":"USB owner exited","received_ms":0});
    });
    Ok(child)
}
async fn run() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let root = PathBuf::from(env("NANO_RUN", "/run/300seconds"));
    if args.first().map(String::as_str) == Some("typecast-check") {
        println!("{}", typecast::usage().await?);
        return Ok(());
    }
    if args.first().map(String::as_str) == Some("typecast-sample") && args.len() == 2 {
        let (wav, metadata) =
            typecast::synthesize("문제에 주어진 조건을 먼저 하나 찾아볼까?").await?;
        use std::os::unix::fs::OpenOptionsExt;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&args[1])?;
        std::io::Write::write_all(&mut file, &wav)?;
        println!("{}", metadata);
        return Ok(());
    }
    if args.first().map(String::as_str) == Some("ctl") {
        if args.len() != 3 {
            return Err(error("nano-runtime ctl SERVICE '{\"cmd\":\"status\"}'"));
        }
        let command: Command = serde_json::from_str(&args[2])?;
        println!("{}", rpc(&root, &args[1], command).await?);
        return Ok(());
    }
    if [Some("cuda-check"), Some("cuda-bench")].contains(&args.first().map(String::as_str)) {
        let a: Vec<u8> = (0..76800).map(|i| (i % 251) as u8).collect();
        let b = vec![77; 76800];
        let cpu = native::stats(&a, &b, false)?;
        let gpu = native::stats(&a, &b, true)?;
        if (cpu.0 - gpu.0).abs() > 1e-9 || (cpu.1 - gpu.1).abs() > 1e-9 {
            return Err(error("CUDA reference mismatch"));
        }
        println!(
            "{}",
            json!({"backend":gpu.2,"pixels":76800,"mean":gpu.0,"motion":gpu.1,"cpu_match":true})
        );
        if args[0] == "cuda-bench" {
            let mut values = Vec::new();
            for cuda in [false, true] {
                let mut times = Vec::new();
                for _ in 0..50 {
                    let start = std::time::Instant::now();
                    std::hint::black_box(native::stats(
                        std::hint::black_box(&a),
                        std::hint::black_box(&b),
                        cuda,
                    )?);
                    times.push(start.elapsed().as_micros());
                }
                times.sort();
                values
                    .push(json!({"cuda":cuda,"p50_us":times[25],"p95_us":times[47],"samples":50}));
            }
            println!(
                "{}",
                json!({"benchmark":"luma_preprocessing_only","results":values,"persistent_cuda_buffers":true})
            );
        }
        return Ok(());
    }
    if args.first().map(String::as_str) == Some("detector-check") && args.len() == 2 {
        if std::fs::metadata(&args[1])?.len() != 115200 {
            return Err(error("detector-check expects 320x240 NV12 file"));
        }
        let data = std::fs::read(&args[1])?;
        let mut d = native::Detector::open()?;
        let mut result = Value::Null;
        let mut times = Vec::new();
        for _ in 0..10 {
            let start = std::time::Instant::now();
            result = d.infer(&data)?;
            times.push(start.elapsed().as_millis());
        }
        times.sort();
        println!(
            "{}",
            json!({"inference":result,"samples":10,"p50_ms":times[5],"p95_ms":times[9]})
        );
        return Ok(());
    }
    if args.len() != 2
        || args[0] != "serve"
        || ![
            "controllerd",
            "picod",
            "camerad",
            "visiond",
            "audiod",
            "memoryd",
            "dialogued",
        ]
        .contains(&args[1].as_str())
    {
        return Err(error("nano-runtime serve controllerd|picod|camerad|visiond|audiod|memoryd|dialogued; ctl SERVICE JSON; cuda-check"));
    }
    std::fs::create_dir_all(&root)?;
    let role = args[1].clone();
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(root.join(format!("{role}.lock")))?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        return Err(error("service already owns runtime lock"));
    }
    let (pcm, _) = watch::channel(Arc::new(Vec::new()));
    let (audio_tx, audio_rx) = std::sync::mpsc::sync_channel(4);
    let ctx = Arc::new(Shared {
        root,
        role,
        generation: pico_device_bench::new_session()?,
        lease: Mutex::new(Lease::default()),
        stopping: AtomicBool::new(false),
        state: RwLock::new(json!({})),
        policy: Mutex::new(Policy {
            phase: "quiet".into(),
            epoch: 0,
        }),
        shutdown: AtomicBool::new(false),
        pcm,
        audio_tx,
        reset: AtomicBool::new(false),
        stop_gate: Mutex::new(()),
        job: Mutex::new(None),
        turn_state: RwLock::new(json!({"phase":"idle"})),
        problem: RwLock::new(String::new()),
        last_request: RwLock::new(String::new()),
        memory_gate: Mutex::new(()),
        image_request: std::sync::atomic::AtomicU32::new(0),
        image_seq: [
            std::sync::atomic::AtomicU64::new(0),
            std::sync::atomic::AtomicU64::new(0),
        ],
        pico_arm_uptime: std::sync::atomic::AtomicU64::new(0),
        external_audio: Mutex::new(None),
    });
    let mut child = if ctx.role == "picod" {
        Some(bridge(ctx.clone()).await?)
    } else {
        None
    };
    let media_threads = media::start(ctx.clone(), audio_rx)?;
    {
        let c = ctx.clone();
        tokio::spawn(async move {
            if let Err(e) = serve_stop(c).await {
                eprintln!("Stop endpoint fatal: {e}");
                std::process::exit(1)
            }
        });
    }
    let c = ctx.clone();
    tokio::spawn(async move {
        policy::watchdog(c).await;
    });
    let c = ctx.clone();
    let server = tokio::spawn(async move { serve(c).await });
    let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    tokio::select! {r=server=>{r??;},_=tokio::signal::ctrl_c()=>{},_=term.recv()=>{}}
    let stopped = policy::stop(&ctx).await;
    ctx.shutdown.store(true, Ordering::SeqCst);
    if let Some(child) = child.as_mut() {
        child.start_kill()?;
        let _ = timeout(Duration::from_secs(3), child.wait()).await;
    }
    // Join owners so Argus/ALSA close before this process exits.
    for worker in media_threads {
        let _ = worker.join();
    }
    stopped?;
    drop(lock);
    Ok(())
}
#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() {
    if let Err(e) = run().await {
        eprintln!("{e}");
        std::process::exit(1)
    }
}
