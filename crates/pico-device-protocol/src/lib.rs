#![no_std]

use serde::{Deserialize, Serialize};

pub const VERSION: u8 = 2;
pub const PROTOCOL_VERSION: u8 = VERSION;
pub const USB_VID: u16 = 0xc0de;
pub const USB_PID: u16 = 0xcafc;
pub const MAX_DECODED: usize = 512;
pub const MAX_WIRE: usize = 520;
pub const TOUCH_COUNT: usize = 6;
pub const DEBOUNCE_MS: u64 = 30;
pub const SAMPLE_INTERVAL_MS: u64 = 5;
pub type TouchEvents = heapless::Vec<TouchEvent, 24>;

// Variant declaration order is the version-1 Postcard discriminant order.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Module { Matrix, NeoLeft, NeoRight, Servos, All }

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum AckCode {
    Ok, InvalidConfig, Busy, NoSession, Unsupported, Fault,
    BadVersion, BadSession, StaleSequence,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeviceConfig {
    pub left_segments: [u8; 3],
    pub right_segments: [u8; 3],
    pub touch_active_low_mask: u8,
    pub local_tests_enabled: bool,
    /// One-based sensor index; zero disables local test selection.
    pub test_switch: u8,
    pub hold_interval_ms: u32,
    pub press_window_ms: u32,
    pub servo_min_us: u16,
    pub servo_max_us: u16,
    pub test_span_degrees: u8,
}

impl Default for DeviceConfig {
    fn default() -> Self {
        Self {
            left_segments: [4, 4, 10], right_segments: [4, 4, 10],
            touch_active_low_mask: 0, local_tests_enabled: true, test_switch: 6,
            hold_interval_ms: 500, press_window_ms: 2000,
            servo_min_us: 1000, servo_max_us: 2000, test_span_degrees: 10,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ValidationError {
    LeftSegments, RightSegments, TouchMask, TestSwitch,
    HoldInterval, PressWindow, ServoRange, TestSpan,
}
impl core::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result { write!(f, "invalid device configuration: {self:?}") }
}
impl core::error::Error for ValidationError {}

impl DeviceConfig {
    pub fn left_total(&self) -> usize { self.left_segments.iter().map(|v| *v as usize).sum() }
    pub fn right_total(&self) -> usize { self.right_segments.iter().map(|v| *v as usize).sum() }
    pub fn validate(&self) -> Result<(), ValidationError> {
        if !(1..=36).contains(&self.left_total()) { return Err(ValidationError::LeftSegments); }
        if !(1..=36).contains(&self.right_total()) { return Err(ValidationError::RightSegments); }
        if self.touch_active_low_mask & !0x3f != 0 { return Err(ValidationError::TouchMask); }
        if self.test_switch > 6 { return Err(ValidationError::TestSwitch); }
        if !(100..=60_000).contains(&self.hold_interval_ms) { return Err(ValidationError::HoldInterval); }
        if !(100..=60_000).contains(&self.press_window_ms) { return Err(ValidationError::PressWindow); }
        if self.servo_min_us < 500 || self.servo_max_us > 2500 || self.servo_min_us >= self.servo_max_us {
            return Err(ValidationError::ServoRange);
        }
        if !(1..=30).contains(&self.test_span_degrees) { return Err(ValidationError::TestSpan); }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct TouchState {
    pub pressed: bool,
    pub held_ms: u32,
    pub interval_count: u32,
    pub last_duration_ms: u32,
    pub last_interval_count: u32,
    pub press_count: u32,
    pub window_remaining_ms: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum TouchKind { Pressed, Interval, Released, WindowClosed }

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct TouchEvent {
    /// One-based sensor index, 1 through 6.
    pub index: u8,
    pub kind: TouchKind,
    pub event_seq: u32,
    pub uptime_ms: u64,
    pub pressed: bool,
    pub duration_ms: u32,
    pub interval_count: u32,
    pub press_count: u32,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct DeviceStatus {
    pub uptime_ms: u64,
    pub raw_mask: u8,
    pub pressed_mask: u8,
    pub touches: [TouchState; TOUCH_COUNT],
    pub running: Option<Module>,
    pub local_enabled: bool,
    pub oe_high: bool,
    pub faults: u32,
    pub dropped_events: u32,
    pub config: DeviceConfig,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum Message {
    Hello,
    HelloReply { device_id: u64, uptime_ms: u64 },
    KeepAlive,
    GetStatus,
    Status(DeviceStatus),
    Configure(DeviceConfig),
    RunTest(Module),
    Stop,
    Ack { request_seq: u32, code: AckCode },
    Touch(TouchEvent),
    TestEvent { module: Module, phase: u16, done: bool, fault: bool },
    Bootloader,
    Arm(ActuatorConfig),
    SetPose { targets_cdeg: [u16;6], move_ms: u16 },
    SetLight { rgb: [u8;3], brightness: u8, period_ms: u16 },
    SetEyes { left: [u8;8], right: [u8;8], brightness: u8 },
    Outputs(OutputStatus),
    Applied { request_seq: u32, kind: u8 },
}

#[derive(Clone,Copy,Debug,PartialEq,Eq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActuatorConfig {
    pub calibration_id:u32,
    pub min_cdeg:[u16;6],
    pub max_cdeg:[u16;6],
    pub neutral_cdeg:[u16;6],
    pub min_us:[u16;6],
    pub max_us:[u16;6],
    pub invert_mask:u8,
    pub max_speed_cdeg_s:u16,
    pub servo_enabled:bool,
    pub matrix_installed:bool,
}
impl Default for ActuatorConfig {fn default()->Self{Self{calibration_id:1,min_cdeg:[8000;6],max_cdeg:[10000;6],neutral_cdeg:[9000;6],min_us:[1000;6],max_us:[2000;6],invert_mask:0,max_speed_cdeg_s:1000,servo_enabled:false,matrix_installed:false}}}
impl ActuatorConfig {
    pub fn validate(&self)->bool {self.calibration_id!=0&&self.invert_mask&!63==0&&(100..=6000).contains(&self.max_speed_cdeg_s)&&(0..6).all(|i|self.min_cdeg[i]<self.max_cdeg[i]&&self.max_cdeg[i]<=18000&&self.neutral_cdeg[i]>=self.min_cdeg[i]&&self.neutral_cdeg[i]<=self.max_cdeg[i]&&self.min_us[i]>=500&&self.max_us[i]<=2500&&self.min_us[i]<self.max_us[i])}
    pub fn accepts(&self,target:&[u16;6],move_ms:u16)->bool{self.validate()&&self.servo_enabled&&(100..=10000).contains(&move_ms)&&(0..6).all(|i|(self.min_cdeg[i]..=self.max_cdeg[i]).contains(&target[i]))}
    pub fn ticks(&self,i:usize,cdeg:u16)->u16{let angle=if self.invert_mask&(1<<i)!=0{18000-cdeg.min(18000)}else{cdeg.min(18000)};let us=self.min_us[i]as u32+(self.max_us[i]-self.min_us[i])as u32*angle as u32/18000;((us*4096+10000)/20000)as u16}
}
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq,Serialize,Deserialize)]
pub struct OutputStatus {pub armed:bool,pub calibration_id:u32,pub commanded_cdeg:[u16;6],pub pose_active:bool,pub light_active:bool,pub applied_seq:u32}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct Frame {
    pub version: u8,
    pub session: u64,
    pub seq: u32,
    pub body: Message,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CodecError { BufferTooSmall, TooLong, BadCobs, BadCrc, BadPayload }
impl core::fmt::Display for CodecError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result { write!(f, "protocol codec: {self:?}") }
}
impl core::error::Error for CodecError {}

/// CRC-32/ISO-HDLC: reflected polynomial, init/xorout 0xffffffff.
pub fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0u32;
    for byte in bytes {
        crc ^= *byte as u32;
        for _ in 0..8 { crc = (crc >> 1) ^ (0xedb8_8320 & (0u32.wrapping_sub(crc & 1))); }
    }
    !crc
}

fn cobs_encode(input: &[u8], output: &mut [u8]) -> Result<usize, CodecError> {
    if output.is_empty() { return Err(CodecError::BufferTooSmall); }
    let mut code_at = 0;
    let mut write = 1;
    let mut code = 1u8;
    for &byte in input {
        if byte == 0 {
            output[code_at] = code;
            code_at = write;
            if write >= output.len() { return Err(CodecError::BufferTooSmall); }
            write += 1;
            code = 1;
        } else {
            if write >= output.len() { return Err(CodecError::BufferTooSmall); }
            output[write] = byte;
            write += 1;
            code += 1;
            if code == 0xff {
                output[code_at] = code;
                code_at = write;
                if write >= output.len() { return Err(CodecError::BufferTooSmall); }
                write += 1;
                code = 1;
            }
        }
    }
    output[code_at] = code;
    Ok(write)
}

fn cobs_decode(input: &[u8], output: &mut [u8]) -> Result<usize, CodecError> {
    let mut read = 0;
    let mut write = 0;
    while read < input.len() {
        let code = input[read];
        if code == 0 { return Err(CodecError::BadCobs); }
        read += 1;
        let count = code as usize - 1;
        if read + count > input.len() { return Err(CodecError::BadCobs); }
        if write + count > output.len() { return Err(CodecError::TooLong); }
        for &byte in &input[read..read + count] {
            if byte == 0 { return Err(CodecError::BadCobs); }
            output[write] = byte;
            write += 1;
        }
        read += count;
        if code != 0xff && read < input.len() {
            if write >= output.len() { return Err(CodecError::TooLong); }
            output[write] = 0;
            write += 1;
        }
    }
    Ok(write)
}

/// Encodes COBS(Postcard(Frame) || CRC32_LE), followed by one zero delimiter.
/// Session, version and sequence policy belongs to the caller.
pub fn encode_frame(frame: &Frame, output: &mut [u8]) -> Result<usize, CodecError> {
    let mut decoded = [0u8; MAX_DECODED];
    let payload_len = postcard::to_slice(frame, &mut decoded[..MAX_DECODED - 4])
        .map_err(|_| CodecError::BadPayload)?.len();
    let crc = crc32(&decoded[..payload_len]);
    decoded[payload_len..payload_len + 4].copy_from_slice(&crc.to_le_bytes());
    let encoded_len = cobs_encode(&decoded[..payload_len + 4], output)?;
    if encoded_len >= output.len() { return Err(CodecError::BufferTooSmall); }
    output[encoded_len] = 0;
    Ok(encoded_len + 1)
}

fn decode_packet(packet: &[u8]) -> Result<Frame, CodecError> {
    let mut decoded = [0u8; MAX_DECODED];
    let len = cobs_decode(packet, &mut decoded)?;
    if len < 5 { return Err(CodecError::BadPayload); }
    let payload_len = len - 4;
    let expected = u32::from_le_bytes(decoded[payload_len..len].try_into().unwrap());
    if crc32(&decoded[..payload_len]) != expected { return Err(CodecError::BadCrc); }
    let (frame, remainder) = postcard::take_from_bytes(&decoded[..payload_len])
        .map_err(|_| CodecError::BadPayload)?;
    if !remainder.is_empty() { return Err(CodecError::BadPayload); }
    Ok(frame)
}

/// Incremental decoder. After overflow, discard until the next zero delimiter.
pub struct FrameDecoder { encoded: [u8; MAX_WIRE - 1], len: usize, discarding: bool }
impl Default for FrameDecoder { fn default() -> Self { Self::new() } }
impl FrameDecoder {
    pub const fn new() -> Self { Self { encoded: [0; MAX_WIRE - 1], len: 0, discarding: false } }
    pub fn clear(&mut self) { self.len = 0; self.discarding = false; }
    pub fn push(&mut self, byte: u8) -> Option<Result<Frame, CodecError>> {
        if byte != 0 {
            if !self.discarding {
                if self.len < self.encoded.len() { self.encoded[self.len] = byte; self.len += 1; }
                else { self.discarding = true; }
            }
            return None;
        }
        if self.discarding { self.clear(); return Some(Err(CodecError::TooLong)); }
        if self.len == 0 { return None; }
        let result = decode_packet(&self.encoded[..self.len]);
        self.len = 0;
        Some(result)
    }
}

#[derive(Clone, Copy)]
struct Tracker {
    pressed: bool, candidate: bool, candidate_since: u64, started: u64,
    interval_count: u32, last_duration: u32, last_interval: u32,
    window_start: Option<u64>, press_count: u32,
}
impl Tracker {
    const EMPTY: Self = Self { pressed: false, candidate: false, candidate_since: 0, started: 0,
        interval_count: 0, last_duration: 0, last_interval: 0, window_start: None, press_count: 0 };
}

pub struct TouchEngine {
    config: DeviceConfig,
    trackers: [Tracker; TOUCH_COUNT],
    raw: u8,
    event_seq: u32,
}

fn milliseconds(value: u64) -> u32 { value.min(u32::MAX as u64) as u32 }
fn interval_count(duration: u64, interval: u32) -> u32 { milliseconds(duration / interval as u64) }

impl TouchEngine {
    pub fn new(config: DeviceConfig) -> Result<Self, ValidationError> {
        config.validate()?;
        Ok(Self { config, trackers: [Tracker::EMPTY; TOUCH_COUNT], raw: 0, event_seq: 0 })
    }
    /// Clears held/window history after validated configuration; event sequence continues.
    pub fn configure(&mut self, config: DeviceConfig, now_ms: u64) -> Result<(), ValidationError> {
        config.validate()?;
        self.config = config;
        self.clear(now_ms);
        Ok(())
    }
    pub fn clear(&mut self, now_ms: u64) {
        self.trackers = [Tracker::EMPTY; TOUCH_COUNT];
        for tracker in &mut self.trackers { tracker.candidate_since = now_ms; }
        self.raw = 0;
    }
    pub fn config(&self) -> &DeviceConfig { &self.config }
    pub fn raw_mask(&self) -> u8 { self.raw }
    pub fn pressed_mask(&self) -> u8 {
        self.trackers.iter().enumerate().fold(0, |mask, (index, tracker)| mask | ((tracker.pressed as u8) << index))
    }
    pub fn states(&self, now_ms: u64) -> [TouchState; TOUCH_COUNT] {
        core::array::from_fn(|index| {
            let tracker = self.trackers[index];
            let duration = if tracker.pressed { now_ms.saturating_sub(tracker.started) } else { 0 };
            TouchState {
                pressed: tracker.pressed, held_ms: milliseconds(duration),
                interval_count: if tracker.pressed { interval_count(duration, self.config.hold_interval_ms) } else { 0 },
                last_duration_ms: tracker.last_duration, last_interval_count: tracker.last_interval,
                press_count: tracker.press_count,
                window_remaining_ms: tracker.window_start.map_or(0, |start| milliseconds(
                    (self.config.press_window_ms as u64).saturating_sub(now_ms.saturating_sub(start)))),
            }
        })
    }
    fn event(&mut self, events: &mut TouchEvents, index: usize, kind: TouchKind, now_ms: u64,
        duration_ms: u32, count: u32, presses: u32) {
        self.event_seq = self.event_seq.wrapping_add(1);
        let event = TouchEvent { index: index as u8 + 1, kind, event_seq: self.event_seq,
            uptime_ms: now_ms, pressed: self.trackers[index].pressed,
            duration_ms, interval_count: count, press_count: presses };
        let result = events.push(event);
        debug_assert!(result.is_ok());
    }
    /// `raw_mask` has one bit per GPIO HIGH. Polarity and 30 ms debounce are internal.
    /// Call every 5 ms with a monotonic device uptime. No local device action is performed.
    pub fn sample(&mut self, raw_mask: u8, now_ms: u64) -> TouchEvents {
        let mut events = TouchEvents::new();
        self.raw = raw_mask & 0x3f;
        let logical = self.raw ^ self.config.touch_active_low_mask;
        for index in 0..TOUCH_COUNT {
            let pressed = logical & (1 << index) != 0;
            // A press exactly at the fixed-window boundary starts a new window.
            if let Some(start) = self.trackers[index].window_start {
                if now_ms.saturating_sub(start) >= self.config.press_window_ms as u64 {
                    let tracker = self.trackers[index];
                    let duration = if tracker.pressed { now_ms.saturating_sub(tracker.started) } else { 0 };
                    self.event(&mut events, index, TouchKind::WindowClosed, now_ms,
                        milliseconds(duration), if tracker.pressed { interval_count(duration, self.config.hold_interval_ms) } else { 0 }, tracker.press_count);
                    self.trackers[index].window_start = None;
                    self.trackers[index].press_count = 0;
                }
            }
            if pressed != self.trackers[index].candidate {
                self.trackers[index].candidate = pressed;
                self.trackers[index].candidate_since = now_ms;
            }
            let changed = self.trackers[index].pressed != pressed
                && now_ms.saturating_sub(self.trackers[index].candidate_since) >= DEBOUNCE_MS;
            if changed {
                self.trackers[index].pressed = pressed;
                if pressed {
                    self.trackers[index].started = now_ms;
                    self.trackers[index].interval_count = 0;
                    if self.trackers[index].window_start.is_none() { self.trackers[index].window_start = Some(now_ms); }
                    self.trackers[index].press_count = self.trackers[index].press_count.saturating_add(1);
                    self.event(&mut events, index, TouchKind::Pressed, now_ms, 0, 0, self.trackers[index].press_count);
                } else {
                    let duration = now_ms.saturating_sub(self.trackers[index].started);
                    let count = interval_count(duration, self.config.hold_interval_ms);
                    self.trackers[index].last_duration = milliseconds(duration);
                    self.trackers[index].last_interval = count;
                    self.trackers[index].interval_count = 0;
                    self.event(&mut events, index, TouchKind::Released, now_ms,
                        milliseconds(duration), count, self.trackers[index].press_count);
                }
            }
            if self.trackers[index].pressed {
                let duration = now_ms.saturating_sub(self.trackers[index].started);
                let count = interval_count(duration, self.config.hold_interval_ms);
                if count > self.trackers[index].interval_count {
                    self.trackers[index].interval_count = count;
                    self.event(&mut events, index, TouchKind::Interval, now_ms,
                        milliseconds(duration), count, self.trackers[index].press_count);
                }
            }
        }
        events
    }
}
