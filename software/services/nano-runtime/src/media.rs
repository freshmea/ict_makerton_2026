use super::*;
use host_core::{
    shm::{self, Frame, MAX_PIXELS},
    PcmHeader,
};
pub fn start(
    c: Context,
    audio_rx: std::sync::mpsc::Receiver<Vec<u8>>,
) -> Result<Vec<std::thread::JoinHandle<()>>> {
    let mut threads = Vec::new();
    match c.role.as_str() {
        "camerad" => {
            *c.state.try_write()? = json!({"cameras":[{},{}]});
            for camera in 0..2 {
                let c = c.clone();
                threads.push(std::thread::spawn(move || {
                    let result: Result<()> = (|| {
                        let pipeline=format!("nvarguscamerasrc name=raw_source sensor-id={camera} sensor-mode=4 ! video/x-raw(memory:NVMM),width=1280,height=720,format=NV12,framerate=30/1 ! tee name=t t. ! queue max-size-buffers=1 leaky=downstream ! nvvidconv ! video/x-raw,width=320,height=240,format=NV12 ! videorate drop-only=true ! video/x-raw,framerate=10/1 ! appsink name=capture max-buffers=1 drop=true sync=false t. ! queue max-size-buffers=1 leaky=downstream ! valve name=problem_gate drop=true ! nvvidconv ! video/x-raw,width=1280,height=720,format=I420 ! jpegenc quality=85 ! appsink name=problem max-buffers=1 drop=true sync=false async=false");
                        let mut native = native::Media::open(&pipeline)?;
                        let mut bytes = vec![0; MAX_PIXELS];
                        let mut id = 0;
                        let mut dropped = 0;
                        let mut snapshot_at=0;
                        while !c.shutdown.load(Ordering::SeqCst) {
                            if c.image_request.fetch_and(!(1<<camera),Ordering::SeqCst)&(1<<camera)!=0 {
                                match native.snapshot(){Ok(image)=>{
                                    let path=c.root.join(format!("problem-{camera}.jpg"));let tmp=path.with_extension("new");
                                    std::fs::write(&tmp,image)?;std::fs::set_permissions(&tmp,std::fs::Permissions::from_mode(0o600))?;std::fs::rename(tmp,path)?;
                                    c.image_seq[camera as usize].fetch_add(1,Ordering::SeqCst);
                                    snapshot_at=monotonic_ms();
                                },Err(e)=>eprintln!("camera snapshot: {e}")}
                            }
                            if snapshot_at>0&&monotonic_ms().saturating_sub(snapshot_at)>120000{let _=std::fs::remove_file(c.root.join(format!("problem-{camera}.jpg")));snapshot_at=0;}
                            let n = native.read(&mut bytes)?;
                            if n == 0 {
                                continue;
                            }
                            if n != MAX_PIXELS {
                                return Err(error(format!("unexpected NV12 allocation {n}")));
                            }
                            id += 1;
                            let now = monotonic_ms();
                            let f = Frame {
                                generation: c.generation,
                                id,
                                timestamp: now,
                                width: 320,
                                height: 240,
                                pixels: bytes.clone(),
                            };
                            if !shm::publish(&c.root, camera, &f)? {
                                dropped += 1;
                            }
                            let mut s = c.state.blocking_write();
                            s["received_ms"] = json!(now);
                            s["cameras"][camera as usize] = json!({"frame_id":id,"source_frame_id":native.source_frames(),"sensor_mode":4,"received_ms":now,"width":320,"height":240,"format":"NV12","shm_dropped":dropped});
                        }
                        let _=std::fs::remove_file(c.root.join(format!("problem-{camera}.jpg")));
                        Ok(())
                    })();
                    if let Err(e) = result {
                        let _=std::fs::remove_file(c.root.join(format!("problem-{camera}.jpg")));
                        eprintln!("camera{camera}: {e}");
                        c.state.blocking_write()["cameras"][camera as usize] =
                            json!({"error":e.to_string()});
                    }
                }));
            }
        }
        "visiond" => {
            let handle = tokio::runtime::Handle::current();
            threads.push(std::thread::spawn(move || {
                let mut prev: [Vec<u8>; 2] = [Vec::new(), Vec::new()];
                let mut last = [0u64; 2];
                let mut generation = 0;
                *c.state.blocking_write()=json!({"stage":"loading_models","received_ms":0});
                let model_start=monotonic_ms();let mut detector=native::Detector::open().ok();let model_load_ms=monotonic_ms()-model_start;
                let mut semantic=[json!({"error":"no model inference yet"}),json!({"error":"no model inference yet"})];
                let mut inference_time=[0u64;2];let mut positive=[0u64;2];let mut hits=[0u32;2];
                while !c.shutdown.load(Ordering::SeqCst) {
                    let result: Result<Value> = (|| {
                        let status = handle.block_on(rpc(&c.root, "camerad", Command::Status))?;
                        let gen = status["generation"]
                            .as_u64()
                            .ok_or_else(|| error("camera generation missing"))?;
                        if gen != generation {
                            prev = [Vec::new(), Vec::new()];
                            last = [0; 2];
                            generation = gen;
                            inference_time=[0;2];hits=[0;2];positive=[0;2];
                        }
                        let mut samples = Vec::new();
                        for camera in 0..2 {
                            let f = shm::latest(&c.root, camera, generation)?;
                            let i = camera as usize;
                            if f.id == last[i] {
                                continue;
                            }
                            let y = &f.pixels[..76800];
                            let first = prev[i].is_empty();
                            if first {
                                prev[i] = y.to_vec()
                            }
                            let (mean, motion, backend) =
                                native::stats(y, &prev[i], env("NANO_CUDA", "0") == "1")?;
                            prev[i].copy_from_slice(y);
                            last[i] = f.id;
                            let now=monotonic_ms();
                            if now.saturating_sub(inference_time[i])>=1000 {
                                let t=monotonic_ms();
                                semantic[i]=match detector.as_mut(){Some(d)=>d.infer(&f.pixels).unwrap_or_else(|e|json!({"error":e.to_string()})),None=>json!({"error":"model unavailable"})};
                                semantic[i]["inference_ms"]=json!(monotonic_ms()-t);semantic[i]["frame_id"]=json!(f.id);semantic[i]["generation"]=json!(generation);semantic[i]["frame_received_ms"]=json!(f.timestamp);
                                inference_time[i]=monotonic_ms();
                                let person=semantic[i]["persons"].as_array().is_some_and(|x|!x.is_empty());let face=semantic[i]["faces"].as_array().is_some_and(|x|!x.is_empty());
                                if person||face {if now.saturating_sub(positive[i])<3000{hits[i]+=1;}else{hits[i]=1;}positive[i]=now;}
                            }
                            let age=monotonic_ms().saturating_sub(f.timestamp);let observation_age=monotonic_ms().saturating_sub(semantic[i]["frame_received_ms"].as_u64().unwrap_or(0));
                            let presence=if hits[i]>=2&&monotonic_ms().saturating_sub(positive[i])<3000&&observation_age<1500{"present_candidate"}else{"unknown"};
                            samples.push(json!({"camera":camera,"frame_id":f.id,"generation":generation,"luma_mean":mean,"luma_motion":if first{Value::Null}else{json!(motion)},"backend":backend,"presence":presence,"inference":semantic[i],"observation_age_ms":observation_age,"frame_age_ms":age}));
                        }
                        if samples.is_empty() {
                            return Err(error("no new frames"));
                        }
                        Ok(json!({"received_ms":monotonic_ms(),"model_load_ms":model_load_ms,"cameras":samples}))
                    })();
                    match result {
                        Ok(v) => *c.state.blocking_write() = v,
                        Err(e) => {
                            *c.state.blocking_write() =
                                json!({"received_ms":0,"stage":"waiting_frames","model_load_ms":model_load_ms,"presence":"unknown","error":e.to_string()})
                        }
                    }
                    std::thread::sleep(Duration::from_millis(200));
                }
            }));
        }
        "audiod" => {
            let handle = tokio::runtime::Handle::current();
            let worker = c.clone();
            threads.push(std::thread::spawn(move || {
                let c = worker;
                let result: Result<()> = (|| {
                    // Silence keeps the shared playback clock/reference alive;
                    // no tone or spoken audio is generated on startup.
                    let pipeline="appsrc name=play is-live=true format=time do-timestamp=true max-bytes=9600 block=false ! audio/x-raw,format=S16LE,rate=48000,channels=1 ! queue max-size-buffers=4 max-size-bytes=0 max-size-time=100000000 leaky=downstream ! audioconvert ! audio/x-raw,format=S16LE,rate=48000,channels=2 ! webrtcechoprobe name=reference ! alsasink device=robot_playback async=false sync=true buffer-time=40000 latency-time=10000 alsasrc device=robot_capture buffer-time=40000 latency-time=10000 ! audio/x-raw,format=S16LE,rate=48000,channels=1 ! webrtcdsp probe=reference echo-cancel=true gain-control=false ! appsink name=capture max-buffers=4 drop=true sync=false";
                    let pipeline=pipeline.replace("echo-cancel=true",if env("NANO_AEC","1")=="1"{"echo-cancel=true"}else{"echo-cancel=false"});
                    let mut media = native::Media::open(&pipeline)?;
                    let mut bytes = vec![0; 9600];
                    let (mut seq, mut accepted, mut rejected, mut resets) = (0, 0, 0, 0);
                    let mut pending=None;
                    while !c.shutdown.load(Ordering::SeqCst) {
                        if c.reset.load(Ordering::SeqCst) {
                            while audio_rx.try_recv().is_ok() {}
                            pending=None;
                            media.reset()?;
                            resets += 1;
                            c.reset.store(false, Ordering::SeqCst);
                        }
                        // One PCM block or silence per capture iteration, bounded.
                        let mut played=false;
                        for _ in 0..4 {
                            let packet=match pending.take().or_else(||audio_rx.try_recv().ok()){Some(v)=>v,None=>break};
                            let (h, pcm) = PcmHeader::decode(&packet)?;
                            let lease = c.lease.blocking_lock();
                            if lease.valid(monotonic_ms())
                                && h.epoch == lease.epoch
                                && monotonic_ms().saturating_sub(h.timestamp_ms) < 200
                            {
                                if !media.push(pcm)?{pending=Some(packet);break;}
                                played=true;
                                accepted += 1;
                            } else {
                                rejected += 1;
                            }
                        }
                        if !played&&pending.is_none() {let _=media.push(&[0u8;960])?;}
                        let n = media.read(&mut bytes)?;
                        if n == 0 {
                            continue;
                        }
                        seq += 1;
                        let lease = c.lease.blocking_lock();
                        let epoch = lease.epoch;
                        drop(lease);
                        let now = monotonic_ms();
                        let packet = PcmHeader {
                            epoch,
                            seq,
                            timestamp_ms: now,
                            samples: (n / 2) as u32,
                        }
                        .encode(&bytes[..n])?;
                        c.pcm.send_replace(Arc::new(packet));
                        let rms = (bytes[..n]
                            .chunks_exact(2)
                            .map(|x| {
                                let y = i16::from_le_bytes([x[0], x[1]]) as f64 / 32768.0;
                                y * y
                            })
                            .sum::<f64>()
                            / (n / 2) as f64)
                            .sqrt();
                        *c.state.blocking_write() = json!({"received_ms":now,"capture_seq":seq,"rate":48000,"channels":1,"rms":rms,"pcm_accepted":accepted,"pcm_rejected":rejected,"device_flushes":resets,"aec_pipeline":true,"aec_acoustic_verified":false});
                    }
                    Ok(())
                })();
                if let Err(e) = result {
                    eprintln!("audio: {e}");
                    *c.state.blocking_write() = json!({"error":e.to_string(),"received_ms":0});
                }
            }));
            let capture = socket(&c.root, "audiod.capture.sock")?;
            let playback = socket(&c.root, "audiod.playback.sock")?;
            let slots = Arc::new(Semaphore::new(4));
            let capture_slots = slots.clone();
            let c1 = c.clone();
            tokio::spawn(async move {
                while let Ok((mut s, _)) = capture.accept().await {
                    if peer(&s).is_err() {
                        continue;
                    }
                    let Ok(permit) = capture_slots.clone().try_acquire_owned() else {
                        continue;
                    };
                    let mut rx = c1.pcm.subscribe();
                    tokio::spawn(async move {
                        let _permit = permit;
                        while rx.changed().await.is_ok() {
                            let packet = rx.borrow_and_update().clone();
                            if packet.is_empty() {
                                continue;
                            }
                            if !matches!(
                                timeout(Duration::from_millis(100), write_frame(&mut s, &packet))
                                    .await,
                                Ok(Ok(()))
                            ) {
                                break;
                            }
                        }
                    });
                }
            });
            tokio::spawn(async move {
                while let Ok((mut s, _)) = playback.accept().await {
                    if peer(&s).is_err() {
                        continue;
                    }
                    let Ok(permit) = slots.clone().try_acquire_owned() else {
                        continue;
                    };
                    let c = c.clone();
                    tokio::spawn(async move {
                        let _permit = permit;
                        let mut seq = 0;
                        let mut epoch = 0;
                        loop {
                            let bytes =
                                match timeout(Duration::from_secs(2), read_frame(&mut s)).await {
                                    Ok(Ok(v)) => v,
                                    _ => break,
                                };
                            let Ok((h, _)) = PcmHeader::decode(&bytes) else {
                                break;
                            };
                            let lease = c.lease.lock().await;
                            if !lease.valid(monotonic_ms())
                                || h.epoch != lease.epoch
                                || h.timestamp_ms > monotonic_ms()
                                || monotonic_ms() - h.timestamp_ms > 200
                            {
                                break;
                            }
                            if epoch != h.epoch {
                                seq = 0;
                                epoch = h.epoch
                            }
                            if h.seq <= seq {
                                break;
                            }
                            seq = h.seq;
                            drop(lease);
                            let mut packet = bytes;
                            let start = monotonic_ms();
                            let mut queued = false;
                            loop {
                                match c.audio_tx.try_send(packet) {
                                    Ok(()) => {
                                        queued = true;
                                        break;
                                    }
                                    Err(std::sync::mpsc::TrySendError::Full(v)) => {
                                        packet = v;
                                        if monotonic_ms() - start > 100 {
                                            break;
                                        }
                                        tokio::time::sleep(Duration::from_millis(1)).await;
                                    }
                                    Err(_) => break,
                                }
                            }
                            if !queued {
                                break;
                            }
                            if !matches!(
                                timeout(
                                    Duration::from_millis(100),
                                    tokio::io::AsyncWriteExt::write_u64(&mut s, h.seq)
                                )
                                .await,
                                Ok(Ok(()))
                            ) {
                                break;
                            }
                        }
                    });
                }
            });
            let _ = handle;
        }
        "dialogued" => {
            *c.state.try_write()? = providers::configured();
        }
        _ => {}
    }
    Ok(threads)
}
