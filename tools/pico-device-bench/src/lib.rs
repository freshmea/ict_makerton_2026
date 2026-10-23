use pico_device_protocol::{
    encode_frame, AckCode, DeviceConfig, DeviceStatus, Frame, FrameDecoder, Message, Module,
    MAX_WIRE, VERSION,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::error::Error;
use std::fmt;
use std::io;
use std::net::SocketAddr;
use std::sync::{atomic::{AtomicBool, Ordering}, Arc};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
use tokio::net::UdpSocket;
use tokio::time::{self, Duration, Instant, Interval, MissedTickBehavior};

pub type DynError = Box<dyn Error + Send + Sync>;
pub type Result<T> = std::result::Result<T, DynError>;
pub const IPC_DEFAULT: &str = "127.0.0.1:37920";
pub const MAX_DATAGRAM: usize = 8192;
pub const KEEPALIVE_INTERVAL: Duration = Duration::from_millis(200);
pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(3);
pub const TEST_TIMEOUT: Duration = Duration::from_secs(180);
pub const PROTOCOL_NAME: &str = "pico-device-v1";

pub fn failure(message: impl Into<String>) -> DynError {
    Box::new(io::Error::other(message.into()))
}

pub fn unix_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default()
        .as_millis().min(u64::MAX as u128) as u64
}

pub fn output(mut value: Value) {
    if let Some(object) = value.as_object_mut() {
        object.entry("host_unix_ms").or_insert_with(|| json!(unix_ms()));
    }
    println!("{value}");
}

pub fn new_session() -> Result<u64> {
    let mut bytes = [0u8; 8];
    getrandom::getrandom(&mut bytes).map_err(|error| failure(format!("Session random source failed: {error}")))?;
    Ok(u64::from_le_bytes(bytes).max(1))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TestModule { Matrix, Left, Right, Servos, All }

impl TestModule {
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "matrix" => Some(Self::Matrix), "left" => Some(Self::Left),
            "right" => Some(Self::Right), "servos" => Some(Self::Servos),
            "all" => Some(Self::All), _ => None,
        }
    }
    pub fn wire(self) -> Module {
        match self {
            Self::Matrix => Module::Matrix, Self::Left => Module::NeoLeft,
            Self::Right => Module::NeoRight, Self::Servos => Module::Servos,
            Self::All => Module::All,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case", deny_unknown_fields)]
pub enum IpcRequest {
    Status,
    Test { module: TestModule },
    Stop,
    Configure { config: DeviceConfig },
}

impl IpcRequest {
    pub fn name(&self) -> &'static str {
        match self { Self::Status => "status", Self::Test { .. } => "test", Self::Stop => "stop", Self::Configure { .. } => "configure" }
    }
    pub fn validate(&self) -> Result<()> {
        if let Self::Configure { config } = self { validate_config(config)?; }
        Ok(())
    }
}

pub fn parse_ipc(bytes: &[u8]) -> Result<IpcRequest> {
    if bytes.len() > MAX_DATAGRAM { return Err(failure("UDP datagram exceeds 8192 bytes")); }
    let value: Value = serde_json::from_slice(bytes)?;
    let object = value.as_object().ok_or_else(|| failure("UDP request must be a JSON object"))?;
    let allowed: &[&str] = match object.get("cmd").and_then(Value::as_str) {
        Some("status" | "stop") => &["cmd"],
        Some("test") => &["cmd", "module"],
        Some("configure") => &["cmd", "config"],
        _ => return Err(failure("UDP cmd must be status, test, stop, or configure")),
    };
    if let Some(key) = object.keys().find(|key| !allowed.contains(&key.as_str())) {
        return Err(failure(format!("Unknown UDP request field: {key}")));
    }
    if let Some(config) = value.get("config").and_then(Value::as_object) {
        let known = serde_json::to_value(DeviceConfig::default())?;
        for key in config.keys() {
            if known.get(key).is_none() { return Err(failure(format!("Unknown UDP configuration field: {key}"))); }
        }
    }
    let request: IpcRequest = serde_json::from_slice(bytes)?;
    request.validate()?;
    Ok(request)
}

pub fn loopback_address(value: &str) -> Result<SocketAddr> {
    let address: SocketAddr = value.parse()?;
    if !address.ip().is_loopback() { return Err(failure("UDP IPC accepts loopback addresses only")); }
    Ok(address)
}

pub fn validate_config(config: &DeviceConfig) -> Result<()> {
    config.validate().map_err(|error| failure(format!("Invalid device configuration: {error:?}")))
}

/// CLI files may override a subset of defaults. UDP always receives a complete
/// typed DeviceConfig, never a server-side filesystem path.
pub fn config_from_json(bytes: &[u8]) -> Result<DeviceConfig> {
    let patch: Value = serde_json::from_slice(bytes)?;
    let patch = patch.as_object().ok_or_else(|| failure("Configuration must be a JSON object"))?;
    let mut base = serde_json::to_value(DeviceConfig::default())?;
    let object = base.as_object_mut().unwrap();
    for (key, value) in patch {
        if !object.contains_key(key) { return Err(failure(format!("Unknown configuration field: {key}"))); }
        object.insert(key.clone(), value.clone());
    }
    let config: DeviceConfig = serde_json::from_value(base)?;
    validate_config(&config)?;
    Ok(config)
}

#[derive(Debug)]
pub struct DeviceRejection { pub request_seq: u32, pub code: AckCode }
impl fmt::Display for DeviceRejection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "Device rejected request {}: {:?}", self.request_seq, self.code)
    }
}
impl Error for DeviceRejection {}

#[derive(Debug)]
pub struct RequestPreempted { pub stop_request_seq: u32 }
impl fmt::Display for RequestPreempted {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "Request cancelled by priority UDP Stop {}", self.stop_request_seq)
    }
}
impl Error for RequestPreempted {}

#[derive(Clone, Copy)]
pub struct Snapshot {
    pub status: DeviceStatus,
    pub received_unix_ms: u64,
    pub received_at: Instant,
}
impl Snapshot {
    pub fn json(self) -> Value {
        json!({"device": self.status, "received_unix_ms": self.received_unix_ms,
            "age_ms": Instant::now().saturating_duration_since(self.received_at).as_millis() as u64})
    }
}

pub enum Input { Frame(Frame), Datagram { bytes: Vec<u8>, peer: SocketAddr } }

/// One task owns this stream. Writes are awaited outside cancellable outer
/// select branches, so a UDP packet cannot interrupt a partial COBS write.
pub struct DeviceLink<S> {
    stream: S,
    decoder: FrameDecoder,
    pending: VecDeque<Frame>,
    keepalive_sequences: VecDeque<u32>,
    heartbeat: Interval,
    session: u64,
    next_seq: u32,
    hello_verified: bool,
    interrupted: Arc<AtomicBool>,
    shutdown_mode: bool,
    publish: bool,
    latest: Option<Snapshot>,
    started: Instant,
    ipc_socket: Option<Arc<UdpSocket>>,
}

impl<S: AsyncRead + AsyncWrite + Unpin> DeviceLink<S> {
    pub fn new(stream: S, session: u64, interrupted: Arc<AtomicBool>, publish: bool) -> Self {
        let mut heartbeat = time::interval_at(Instant::now() + KEEPALIVE_INTERVAL, KEEPALIVE_INTERVAL);
        heartbeat.set_missed_tick_behavior(MissedTickBehavior::Skip);
        Self { stream, decoder: FrameDecoder::new(), pending: VecDeque::new(),
            keepalive_sequences: VecDeque::new(), heartbeat, session, next_seq: 1,
            hello_verified: false, interrupted, shutdown_mode: false, publish,
            latest: None, started: Instant::now(), ipc_socket: None }
    }
    pub fn session(&self) -> u64 { self.session }
    pub fn latest(&self) -> Option<Snapshot> { self.latest }
    pub fn interrupted(&self) -> bool { self.interrupted.load(Ordering::SeqCst) }
    pub fn begin_shutdown(&mut self) { self.shutdown_mode = true; }
    pub fn snapshot_json(&self) -> Value { self.latest.map(Snapshot::json).unwrap_or(Value::Null) }
    pub fn attach_ipc(&mut self, socket: Arc<UdpSocket>) { self.ipc_socket = Some(socket); }

    fn emit(&self, mut value: Value) {
        if !self.publish { return; }
        if let Some(object) = value.as_object_mut() {
            object.insert("session".into(), json!(format!("{:016X}", self.session)));
            object.insert("host_monotonic_ms".into(), json!(self.started.elapsed().as_millis() as u64));
            object.insert("version".into(), json!(VERSION));
        }
        output(value);
    }

    pub async fn send(&mut self, body: Message) -> Result<u32> {
        if self.next_seq == u32::MAX { return Err(failure("Sequence exhausted; restart with a fresh Hello session")); }
        let seq = self.next_seq;
        self.next_seq += 1;
        let frame = Frame { version: VERSION, session: self.session, seq, body };
        let mut bytes = [0u8; MAX_WIRE];
        let size = encode_frame(&frame, &mut bytes).map_err(|error| failure(format!("Frame encoding failed: {error:?}")))?;
        time::timeout(Duration::from_millis(300), self.stream.write_all(&bytes[..size]))
            .await.map_err(|_| failure("Serial write timed out; no command replay will be attempted"))??;
        if matches!(body, Message::KeepAlive) {
            self.keepalive_sequences.push_back(seq);
            if self.keepalive_sequences.len() > 32 { self.keepalive_sequences.pop_front(); }
        }
        Ok(seq)
    }

    fn process(&mut self, frame: Frame) -> bool {
        if frame.version != VERSION || frame.session != self.session {
            self.emit(json!({"event":"rejected_frame","received_version":frame.version,
                "received_session":format!("{:016X}", frame.session),"seq":frame.seq}));
            return false;
        }
        let mut suppress = false;
        match frame.body {
            Message::Status(status) => {
                self.latest = Some(Snapshot { status, received_unix_ms: unix_ms(), received_at: Instant::now() });
                self.emit(json!({"event":"status","seq":frame.seq,"status":status}));
            }
            Message::Touch(event) => self.emit(json!({"event":"touch","seq":frame.seq,"touch":event})),
            Message::TestEvent { module, phase, done, fault } => self.emit(json!({"event":"test_event","seq":frame.seq,
                "module":module,"phase":phase,"done":done,"fault":fault})),
            Message::HelloReply { device_id, uptime_ms } => self.emit(json!({"event":"hello_reply","seq":frame.seq,
                "device_id":format!("{device_id:016X}"),"uptime_ms":uptime_ms,"protocol":PROTOCOL_NAME})),
            Message::Ack { request_seq, code } => {
                if let Some(index) = self.keepalive_sequences.iter().position(|seq| *seq == request_seq) {
                    self.keepalive_sequences.remove(index);
                    suppress = code == AckCode::Ok;
                }
                if !suppress { self.emit(json!({"event":"ack","seq":frame.seq,"request_seq":request_seq,"code":code})); }
            }
            _ => self.emit(json!({"event":"frame","seq":frame.seq,"message":frame.body})),
        }
        true
    }

    pub async fn next_input(&mut self, socket: Option<&UdpSocket>, deadline: Instant) -> Result<Input> {
        let mut raw = [0u8; 256];
        let mut datagram = [0u8; MAX_DATAGRAM + 1];
        loop {
            if self.interrupted() && !self.shutdown_mode {
                return Err(Box::new(io::Error::new(io::ErrorKind::Interrupted, "Shutdown requested")));
            }
            while let Some(frame) = self.pending.pop_front() {
                if self.process(frame) { return Ok(Input::Frame(frame)); }
            }
            tokio::select! {
                biased;
                _ = time::sleep_until(deadline) => return Err(failure("Timed out waiting for a valid device frame")),
                _ = self.heartbeat.tick() => {
                    if self.hello_verified { self.send(Message::KeepAlive).await?; }
                }
                received = async {
                    match socket {
                        Some(socket) => socket.recv_from(&mut datagram).await,
                        None => std::future::pending().await,
                    }
                } => {
                    let (count, peer) = received?;
                    if peer.ip().is_loopback() {
                        return Ok(Input::Datagram { bytes: datagram[..count].to_vec(), peer });
                    }
                }
                read = self.stream.read(&mut raw) => {
                    let count = read?;
                    if count == 0 { return Err(failure("Serial stream closed; restart manually with a fresh session")); }
                    for &byte in &raw[..count] {
                        if let Some(result) = self.decoder.push(byte) {
                            match result {
                                Ok(frame) => self.pending.push_back(frame),
                                Err(error) => self.emit(json!({"event":"codec_error","error":format!("{error:?}")})),
                            }
                        }
                    }
                }
            }
        }
    }

    pub async fn next_frame(&mut self, deadline: Instant) -> Result<Frame> {
        let socket = self.ipc_socket.clone();
        loop {
            match self.next_input(socket.as_deref(), deadline).await? {
                Input::Frame(frame) => return Ok(frame),
                Input::Datagram { bytes, peer } => {
                    let socket = socket.as_deref().unwrap();
                    match parse_ipc(&bytes) {
                        Ok(IpcRequest::Stop) => {
                            let stop_request_seq = self.priority_stop(socket, peer).await?;
                            return Err(Box::new(RequestPreempted { stop_request_seq }));
                        }
                        other => {
                            let error = match other {
                                Ok(_) => "USB request in progress; only stop can preempt it".to_owned(),
                                Err(error) => error.to_string(),
                            };
                            let reply = json!({"ok":false,"error":error,"status":self.snapshot_json()});
                            socket.send_to(&serde_json::to_vec(&reply)?, peer).await?;
                        }
                    }
                }
            }
        }
    }

    async fn boundary(&mut self) -> Result<()> {
        time::timeout(Duration::from_millis(300), self.stream.write_all(&[0])).await
            .map_err(|_| failure("Serial frame boundary resynchronization timed out"))??;
        Ok(())
    }

    /// No nested request_ack/next_frame call is made here. UDP Stop remains
    /// receivable even if the original RPC's ACK was lost while lease traffic
    /// continues. Other commands are rejected rather than queued for replay.
    async fn priority_stop(&mut self, socket: &UdpSocket, peer: SocketAddr) -> Result<u32> {
        let mut peers = vec![peer];
        self.boundary().await?;
        let stop_seq = self.send(Message::Stop).await?;
        let outcome: Result<()> = async {
            let mut deadline = Instant::now() + REQUEST_TIMEOUT;
            let mut query_seq = None;
            let mut query_ack = false;
            let mut query_status = false;
            loop {
                match self.next_input(Some(socket), deadline).await? {
                    Input::Frame(frame) => {
                        match frame.body {
                            Message::Ack { request_seq, code } if request_seq == stop_seq && frame.seq == stop_seq && query_seq.is_none() => {
                                if code != AckCode::Ok { return Err(Box::new(DeviceRejection { request_seq, code }) as DynError); }
                                query_seq = Some(self.send(Message::GetStatus).await?);
                                deadline = Instant::now() + REQUEST_TIMEOUT;
                            }
                            Message::Ack { request_seq, code } if query_seq == Some(request_seq) && frame.seq == request_seq => {
                                if code != AckCode::Ok { return Err(Box::new(DeviceRejection { request_seq, code }) as DynError); }
                                query_ack = true;
                            }
                            Message::Status(_) if query_seq == Some(frame.seq) => query_status = true,
                            _ => (),
                        }
                        if query_ack && query_status { return Ok(()); }
                    }
                    Input::Datagram { bytes, peer } => {
                        if matches!(parse_ipc(&bytes), Ok(IpcRequest::Stop)) && peers.len() < 8 {
                            if !peers.contains(&peer) { peers.push(peer); }
                        } else {
                            let reply = json!({"ok":false,"error":"Priority Stop cleanup in progress; command was not queued","status":self.snapshot_json()});
                            socket.send_to(&serde_json::to_vec(&reply)?, peer).await?;
                        }
                    }
                }
            }
        }.await;
        let reply = match &outcome {
            Ok(()) => json!({"ok":true,"cmd":"stop","ack_request_seq":stop_seq,"ack_code":"Ok",
                "session":format!("{:016X}",self.session),"status":self.snapshot_json()}),
            Err(error) => json!({"ok":false,"cmd":"stop","error":error.to_string(),"status":self.snapshot_json()}),
        };
        let bytes = serde_json::to_vec(&reply)?;
        for peer in peers { socket.send_to(&bytes, peer).await?; }
        outcome?;
        Ok(stop_seq)
    }

    pub async fn hello(&mut self) -> Result<u64> {
        self.emit(json!({"event":"session_open","security_token":false,"protocol":PROTOCOL_NAME}));
        self.boundary().await?;
        let mut request_seq = self.send(Message::Hello).await?;
        let deadline = Instant::now() + REQUEST_TIMEOUT;
        let mut next_hello = Instant::now() + Duration::from_millis(250);
        loop {
            // A newly opened CDC port can contain an unfinished telemetry frame
            // from the previous owner. Only the stop-safe Hello handshake is
            // repeated; actuator requests are still sent exactly once.
            // KeepAlive is disabled until HelloReply, so cancelling this receive
            // cannot cancel a serial write half way through a frame.
            let frame = match time::timeout_at(next_hello.min(deadline), self.next_frame(deadline)).await {
                Ok(frame) => frame?,
                Err(_) if Instant::now() < deadline => {
                    request_seq = self.send(Message::Hello).await?;
                    next_hello = Instant::now() + Duration::from_millis(250);
                    continue;
                }
                Err(_) => return Err(failure("Timed out waiting for HelloReply")),
            };
            if frame.seq == request_seq {
                if let Message::HelloReply { device_id, .. } = frame.body {
                    if device_id == 0 { return Err(failure("Device returned an invalid zero chip identity")); }
                    self.hello_verified = true;
                    return Ok(device_id);
                }
                if let Message::Ack { request_seq: echoed, code } = frame.body {
                    if echoed == request_seq && code != AckCode::Ok { return Err(Box::new(DeviceRejection { request_seq, code })); }
                }
            }
        }
    }


    pub async fn request_ack(&mut self, body: Message) -> Result<u32> {
        let request_seq = self.send(body).await?;
        let deadline = Instant::now() + REQUEST_TIMEOUT;
        loop {
            let frame = self.next_frame(deadline).await?;
            if let Message::Ack { request_seq: echoed, code } = frame.body {
                if frame.seq == request_seq && echoed == request_seq {
                    if code == AckCode::Ok { return Ok(request_seq); }
                    return Err(Box::new(DeviceRejection { request_seq, code }));
                }
            }
        }
    }

    pub async fn get_status(&mut self) -> Result<DeviceStatus> {
        let request_seq = self.send(Message::GetStatus).await?;
        let deadline = Instant::now() + REQUEST_TIMEOUT;
        let mut reply = None;
        let mut acknowledged = false;
        loop {
            let frame = self.next_frame(deadline).await?;
            match frame.body {
                Message::Status(status) if frame.seq == request_seq => reply = Some(status),
                Message::Ack { request_seq: echoed, code } if frame.seq == request_seq && echoed == request_seq => {
                    if code != AckCode::Ok { return Err(Box::new(DeviceRejection { request_seq, code })); }
                    acknowledged = true;
                }
                _ => (),
            }
            if acknowledged { if let Some(status) = reply { return Ok(status); } }
        }
    }

    pub async fn configure(&mut self, config: DeviceConfig) -> Result<u32> {
        validate_config(&config)?;
        self.request_ack(Message::Configure(config)).await
    }

    pub async fn stop(&mut self) -> Result<u32> {
        // An empty delimiter is ignored by the protocol. It also closes a
        // truncated previous write before the dominant STOP frame is sent.
        self.boundary().await?;
        self.request_ack(Message::Stop).await
    }
}

/// Each request is sent once. A lost UDP reply is never retried automatically,
/// since repeating a test could create a new physical action.
pub async fn udp_roundtrip(address: SocketAddr, request: &IpcRequest) -> Result<Value> {
    if !address.ip().is_loopback() { return Err(failure("UDP IPC accepts loopback addresses only")); }
    request.validate()?;
    let bind = if address.is_ipv4() { "127.0.0.1:0" } else { "[::1]:0" };
    let socket = UdpSocket::bind(bind).await?;
    let bytes = serde_json::to_vec(request)?;
    socket.send_to(&bytes, address).await?;
    let deadline = Instant::now() + Duration::from_secs(5);
    let mut reply = [0u8; MAX_DATAGRAM + 1];
    loop {
        let (count, peer) = time::timeout_at(deadline, socket.recv_from(&mut reply)).await
            .map_err(|_| failure("UDP IPC reply timed out; command was not resent"))??;
        if peer != address { continue; }
        if count > MAX_DATAGRAM { return Err(failure("UDP IPC reply exceeds 8192 bytes")); }
        return Ok(serde_json::from_slice(&reply[..count])?);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pico_device_protocol::TouchState;
    use tokio::io::DuplexStream;

    fn device_status() -> DeviceStatus {
        DeviceStatus { uptime_ms: 1, raw_mask: 0, pressed_mask: 0,
            touches: [TouchState::default(); 6], running: None, local_enabled: true,
            oe_high: true, faults: 0, dropped_events: 0, config: DeviceConfig::default() }
    }

    async fn read_frame(stream: &mut DuplexStream) -> Frame {
        let mut decoder = FrameDecoder::new();
        loop {
            let byte = stream.read_u8().await.unwrap();
            if let Some(result) = decoder.push(byte) { return result.unwrap(); }
        }
    }

    async fn write_fragmented(stream: &mut DuplexStream, frame: Frame) {
        let mut bytes = [0u8; MAX_WIRE];
        let size = encode_frame(&frame, &mut bytes).unwrap();
        for part in bytes[..size].chunks(3) { stream.write_all(part).await.unwrap(); tokio::task::yield_now().await; }
    }

    #[test]
    fn json_requests_allow_only_typed_loopback_commands_and_valid_config() {
        assert!(loopback_address("127.0.0.1:37920").is_ok());
        assert!(loopback_address("[::1]:37920").is_ok());
        assert!(loopback_address("0.0.0.0:37920").is_err());
        assert!(loopback_address("192.168.1.2:37920").is_err());
        assert_eq!(parse_ipc(br#"{"cmd":"test","module":"left"}"#).unwrap(), IpcRequest::Test { module: TestModule::Left });
        for bad in [br#"{"cmd":"reboot"}"#.as_slice(), br#"{"cmd":"test","module":"invalid"}"#,
            br#"{"cmd":"status","path":"/etc/passwd"}"#, br#"{"cmd":"configure","path":"config.json"}"#] {
            assert!(parse_ipc(bad).is_err());
        }
        let mut config = DeviceConfig::default();
        assert_eq!(config.left_total(), 18);
        config.left_segments = [36, 36, 36];
        let request = serde_json::to_vec(&IpcRequest::Configure { config }).unwrap();
        assert!(parse_ipc(&request).is_err());
        assert!(config_from_json(br#"{"right_segments":[4,4,8]}"#).is_ok());
        assert!(config_from_json(br#"{"servo_max_us":3000}"#).is_err());
        assert!(config_from_json(br#"{"not_a_setting":1}"#).is_err());
    }

    #[tokio::test]
    async fn fragmented_codec_session_and_ack_matching_over_fake_serial() {
        let (host, mut device) = tokio::io::duplex(2048);
        let mut link = DeviceLink::new(host, 42, Arc::new(AtomicBool::new(false)), false);
        let simulated = tokio::spawn(async move {
            let hello = read_frame(&mut device).await;
            assert_eq!(hello.body, Message::Hello);
            write_fragmented(&mut device, Frame { version: VERSION, session: 999, seq: hello.seq,
                body: Message::HelloReply { device_id: 111, uptime_ms: 0 } }).await;
            write_fragmented(&mut device, Frame { version: VERSION, session: 42, seq: hello.seq,
                body: Message::HelloReply { device_id: 222, uptime_ms: 1 } }).await;
            let stop = read_frame(&mut device).await;
            assert_eq!(stop.body, Message::Stop);
            write_fragmented(&mut device, Frame { version: VERSION, session: 42, seq: stop.seq,
                body: Message::Ack { request_seq: stop.seq + 1, code: AckCode::Fault } }).await;
            write_fragmented(&mut device, Frame { version: VERSION, session: 42, seq: stop.seq,
                body: Message::Ack { request_seq: stop.seq, code: AckCode::Ok } }).await;
        });
        assert_eq!(link.hello().await.unwrap(), 222);
        assert_eq!(link.stop().await.unwrap(), 2);
        simulated.await.unwrap();
    }

    #[tokio::test]
    async fn get_status_requires_both_correlated_snapshot_and_ack() {
        let (host, mut device) = tokio::io::duplex(4096);
        let mut link = DeviceLink::new(host, 43, Arc::new(AtomicBool::new(false)), false);
        let simulated = tokio::spawn(async move {
            let query = read_frame(&mut device).await;
            assert_eq!(query.body, Message::GetStatus);
            write_fragmented(&mut device, Frame { version: VERSION, session: 43, seq: 999,
                body: Message::Status(device_status()) }).await;
            write_fragmented(&mut device, Frame { version: VERSION, session: 43, seq: query.seq,
                body: Message::Status(device_status()) }).await;
            write_fragmented(&mut device, Frame { version: VERSION, session: 43, seq: query.seq,
                body: Message::Ack { request_seq: query.seq, code: AckCode::Ok } }).await;
        });
        assert!(link.get_status().await.unwrap().oe_high);
        simulated.await.unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn keepalive_runs_while_waiting_without_replaying_test() {
        let (host, mut device) = tokio::io::duplex(4096);
        let mut link = DeviceLink::new(host, 44, Arc::new(AtomicBool::new(false)), false);
        link.hello_verified = true;
        let simulated = tokio::spawn(async move {
            let first = read_frame(&mut device).await;
            assert_eq!(first.body, Message::RunTest(Module::Matrix));
            let heartbeat = read_frame(&mut device).await;
            assert_eq!(heartbeat.body, Message::KeepAlive);
            write_fragmented(&mut device, Frame { version: VERSION, session: 44, seq: first.seq,
                body: Message::Ack { request_seq: first.seq, code: AckCode::Ok } }).await;
        });
        assert_eq!(link.request_ack(Message::RunTest(Module::Matrix)).await.unwrap(), 1);
        simulated.await.unwrap();
    }

    #[tokio::test]
    async fn udp_client_sends_one_typed_command_and_receives_ack_snapshot() {
        let server = UdpSocket::bind("127.0.0.1:0").await.unwrap();
        let address = server.local_addr().unwrap();
        let simulated = tokio::spawn(async move {
            let mut bytes = [0u8; MAX_DATAGRAM];
            let (count, peer) = server.recv_from(&mut bytes).await.unwrap();
            assert_eq!(parse_ipc(&bytes[..count]).unwrap(), IpcRequest::Status);
            server.send_to(br#"{"ok":true,"cmd":"status","status":{"age_ms":0}}"#, peer).await.unwrap();
        });
        let reply = udp_roundtrip(address, &IpcRequest::Status).await.unwrap();
        assert_eq!(reply["ok"], true);
        simulated.await.unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn hello_retries_a_lost_identity_reply_without_replaying_actuators() {
        let (host, mut device) = tokio::io::duplex(4096);
        let mut link = DeviceLink::new(host, 46, Arc::new(AtomicBool::new(false)), false);
        let simulated = tokio::spawn(async move {
            let first = read_frame(&mut device).await;
            assert_eq!(first.body, Message::Hello);
            // ACK alone does not verify identity; the identity reply was lost.
            write_fragmented(&mut device, Frame { version: VERSION, session: 46, seq: first.seq,
                body: Message::Ack { request_seq: first.seq, code: AckCode::Ok } }).await;
            let second = read_frame(&mut device).await;
            assert_eq!(second.body, Message::Hello);
            assert!(second.seq > first.seq);
            write_fragmented(&mut device, Frame { version: VERSION, session: 46, seq: second.seq,
                body: Message::HelloReply { device_id: 123, uptime_ms: 42 } }).await;
        });
        assert_eq!(link.hello().await.unwrap(), 123);
        assert!(link.hello_verified);
        simulated.await.unwrap();
    }

    #[tokio::test]
    async fn udp_stop_preempts_a_lost_test_ack_without_waiting_for_rpc_timeout() {
        let (host, mut device) = tokio::io::duplex(4096);
        let socket = Arc::new(UdpSocket::bind("127.0.0.1:0").await.unwrap());
        let address = socket.local_addr().unwrap();
        let mut link = DeviceLink::new(host, 45, Arc::new(AtomicBool::new(false)), false);
        link.hello_verified = true;
        link.attach_ipc(socket);
        let (started, ready) = tokio::sync::oneshot::channel();
        let simulated = tokio::spawn(async move {
            let test = read_frame(&mut device).await;
            assert_eq!(test.body, Message::RunTest(Module::Servos));
            started.send(()).unwrap();
            // Deliberately never ACK the test. STOP must arrive promptly,
            // rather than after the original 3-second request timeout.
            let stop_deadline = Instant::now() + Duration::from_millis(500);
            let stop = loop {
                let frame = time::timeout_at(stop_deadline, read_frame(&mut device)).await.unwrap();
                if !matches!(frame.body, Message::KeepAlive) { break frame; }
            };
            assert_eq!(stop.body, Message::Stop);
            write_fragmented(&mut device, Frame { version: VERSION, session: 45, seq: stop.seq,
                body: Message::Ack { request_seq: stop.seq, code: AckCode::Ok } }).await;
            let query = read_frame(&mut device).await;
            assert_eq!(query.body, Message::GetStatus);
            write_fragmented(&mut device, Frame { version: VERSION, session: 45, seq: query.seq,
                body: Message::Status(device_status()) }).await;
            write_fragmented(&mut device, Frame { version: VERSION, session: 45, seq: query.seq,
                body: Message::Ack { request_seq: query.seq, code: AckCode::Ok } }).await;
        });
        let client = tokio::spawn(async move {
            ready.await.unwrap();
            udp_roundtrip(address, &IpcRequest::Stop).await.unwrap()
        });
        let error = link.request_ack(Message::RunTest(Module::Servos)).await.unwrap_err();
        assert!(error.downcast_ref::<RequestPreempted>().is_some());
        assert_eq!(client.await.unwrap()["ok"], true);
        simulated.await.unwrap();
    }
}
