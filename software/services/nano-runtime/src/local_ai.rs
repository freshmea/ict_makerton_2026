use super::*;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
pub async fn worker(q: Value) -> Result<Value> {
    let operation = q["op"].as_str().unwrap_or("unknown").to_owned();
    let limit = if operation == "asr" || operation == "tts" {
        60
    } else {
        25
    };
    let mut child =
        tokio::process::Command::new(env("NANO_AI_PYTHON", "/opt/300seconds/ai/venv/bin/python"))
            .arg(env("NANO_AI_WORKER", "/opt/300seconds/runtime/local_ai.py"))
            .env_remove("OPENAI_API_KEY")
            .env_remove("GEMINI_API_KEY")
            .env_remove("TYPESAFE_API_KEY")
            .env_remove("TYPECAST_API_KEY")
            .env("OPENBLAS_NUM_THREADS", "1")
            .env("OMP_NUM_THREADS", "1")
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .kill_on_drop(true)
            .spawn()?;
    let mut stdin = child.stdin.take().unwrap();
    stdin.write_all(format!("{q}\n").as_bytes()).await?;
    drop(stdin);
    let output = async {
        let mut bytes = Vec::new();
        child
            .stdout
            .take()
            .unwrap()
            .take(32769)
            .read_to_end(&mut bytes)
            .await?;
        if bytes.len() > 32768 {
            return Err(error("ML adapter output limit"));
        }
        let status = child.wait().await?;
        let v: Value = serde_json::from_slice(&bytes)?;
        if !status.success() || v["ok"] != true {
            return Err(error(format!("ML adapter failed: {}", v["error"])));
        }
        Ok(v["data"].clone())
    };
    timeout(Duration::from_secs(limit), output)
        .await
        .map_err(|_| error(format!("local_{operation}_deadline_{limit}s")))?
}
pub fn private_dir(c: &Context, epoch: u64) -> Result<PathBuf> {
    let p = c.root.join(format!(
        "turn-{}-{epoch}-{}",
        c.generation,
        pico_device_bench::new_session()?
    ));
    std::fs::create_dir(&p)?;
    std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o700))?;
    Ok(p)
}
pub struct Temporary(pub PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
pub async fn speak(
    c: &Context,
    text: &str,
    epoch: u64,
    external: Option<&std::path::Path>,
    backend: &str,
) -> Result<Value> {
    let temp = Temporary(private_dir(c, epoch)?);
    let wav = temp.0.join("tts.wav");
    let pcm = temp.0.join("tts.s16");
    let v = if let Some(source) = external {
        let root = std::fs::canonicalize(&c.root)?;
        let source = std::fs::canonicalize(source)?;
        if !source.starts_with(root)
            || source.file_name().and_then(|s| s.to_str()) != Some("typecast.wav")
        {
            return Err(error("external TTS path outside private runtime"));
        }
        worker(json!({"op":"prepare_wav","wav":source,"pcm":pcm})).await?
    } else {
        worker(json!({"op":"tts","text":text,"wav":wav,"pcm":pcm,"backend":backend})).await?
    };
    let data = tokio::fs::read(pcm).await?;
    if data.len() > 48000 * 2 * 30 {
        return Err(error("TTS too long"));
    }
    let mut s = UnixStream::connect(c.root.join("audiod.playback.sock")).await?;
    let start = monotonic_ms();
    let playback = async {
        for (i, chunk) in data.chunks(960).enumerate() {
            super::turns::current(c, epoch).await?;
            let due = start + i as u64 * 10;
            let now = monotonic_ms();
            if due > now {
                tokio::time::sleep(Duration::from_millis(due - now)).await;
            }
            if monotonic_ms().saturating_sub(due) > 150 {
                return Err(error("TTS sender lag; dropping stale audio"));
            }
            let packet = host_core::PcmHeader {
                epoch,
                seq: i as u64 + 1,
                timestamp_ms: monotonic_ms(),
                samples: (chunk.len() / 2) as u32,
            }
            .encode(chunk)?;
            timeout(Duration::from_millis(100), write_frame(&mut s, &packet)).await??;
            let ack = timeout(Duration::from_millis(150), s.read_u64()).await??;
            if ack != i as u64 + 1 {
                return Err(error("PCM acceptance ACK mismatch"));
            }
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
        Ok::<(), Box<dyn std::error::Error + Send + Sync>>(())
    };
    let interrupt = async {
        if env("NANO_BARGE_IN", "0") != "1" || env("NANO_AEC_VERIFIED", "0") != "1" {
            std::future::pending::<()>().await;
        }
        let mut capture = UnixStream::connect(c.root.join("audiod.capture.sock")).await?;
        let mut vad = host_core::speech::Vad::default();
        loop {
            let packet = timeout(Duration::from_millis(500), read_frame(&mut capture)).await??;
            let (h, bytes) = host_core::PcmHeader::decode(&packet)?;
            if h.epoch != epoch
                || h.timestamp_ms > monotonic_ms()
                || monotonic_ms().saturating_sub(h.timestamp_ms) > 200
            {
                continue;
            }
            if monotonic_ms().saturating_sub(start) < 700 {
                continue;
            }
            if vad.push(bytes, 48000) == host_core::speech::Segment::Speaking {
                return Ok::<(), Box<dyn std::error::Error + Send + Sync>>(());
            }
        }
    };
    tokio::select! {r=playback=>{r?;Ok(v)},r=interrupt=>{r?;rpc(&c.root,"audiod",Command::Stop).await?;Err(error("barge_in_candidate: playback stopped; explicit next request required"))}}
}
pub async fn listen(c: &Context, epoch: u64) -> Result<Value> {
    let temp = Temporary(private_dir(c, epoch)?);
    let wav = temp.0.join("asr.wav");
    let data = capture(c, epoch)
        .await
        .map_err(|e| error(format!("microphone_capture: {e}")))?;
    let recorded_ms = (data.len().saturating_sub(44)) / 96;
    tokio::fs::write(&wav, data).await?;
    *c.turn_state.write().await =
        json!({"phase":"running","epoch":epoch,"stage":"local_asr","recorded_ms":recorded_ms});
    worker(json!({"op":"asr","wav":wav})).await
}
pub async fn capture(c: &Context, epoch: u64) -> Result<Vec<u8>> {
    let mut s = UnixStream::connect(c.root.join("audiod.capture.sock")).await?;
    let mut vad = host_core::speech::Vad::default();
    let mut pcm = Vec::<u8>::new();
    let mut pre = std::collections::VecDeque::<u8>::new();
    let start = monotonic_ms();
    let mut started = false;
    let mut last = 0;
    while monotonic_ms() - start < 15000 {
        super::turns::current(c, epoch).await?;
        let packet = timeout(Duration::from_millis(500), read_frame(&mut s)).await??;
        let (h, bytes) = host_core::PcmHeader::decode(&packet)?;
        if h.epoch != epoch
            || h.seq <= last
            || h.timestamp_ms > monotonic_ms()
            || monotonic_ms() - h.timestamp_ms > 200
        {
            continue;
        }
        last = h.seq;
        let segment = vad.push(bytes, 48000);
        if !started {
            pre.extend(bytes);
            while pre.len() > 48000 * 2 / 3 {
                pre.pop_front();
            }
        }
        if matches!(
            segment,
            host_core::speech::Segment::Speaking
                | host_core::speech::Segment::Finished
                | host_core::speech::Segment::TooLong
        ) {
            if !started {
                pcm.extend(pre.drain(..));
                started = true;
            } else {
                pcm.extend(bytes);
            }
        }
        if pcm.len() > 48000 * 2 * 11 {
            return Err(error("utterance limit"));
        }
        if matches!(
            segment,
            host_core::speech::Segment::Finished | host_core::speech::Segment::TooLong
        ) {
            break;
        }
    }
    if !started {
        return Err(error("no_speech_detected; quiet retained"));
    }
    Ok(host_core::speech::wav(&pcm, 48000))
}
