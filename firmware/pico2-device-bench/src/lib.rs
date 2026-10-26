#![no_std]
#![doc = include_str!("../docs/architecture.md")]
#![doc = include_str!("../docs/use-cases.md")]
/// BOOTSEL USB 요청과 RP2350 ROM 호환 장치 식별자.
pub mod picotool_reset;
/// SW3 입력 수락과 시간 기반 NeoPixel 프레임 계산.
pub mod light_patterns;
/// SW4의 유한한 팔 동작을 기준각과 시간으로 계산한다.
pub mod arm_patterns;

use pico_device_protocol::{AckCode, DeviceConfig, Frame, Message, Module, VERSION};
/// 한 손의 NeoPixel 출력 버퍼 크기. 사용하지 않는 뒤쪽 픽셀도 검정으로 전송한다.
pub const CAPACITY: usize = 36;
/// Refuse ambiguous buses rather than silently picking a different board.
///
/// 입력은 `[0x40의 probe 결과, 0x41의 probe 결과]`다. 값 `1`이 정상 응답을
/// 뜻한다. 정상 주소가 정확히 하나일 때만 선택하며 실제 I2C 통신은 하지 않는다.
pub fn servo_driver_address(probes: [u8; 2]) -> Option<u8> {
    match probes { [1, other] if other != 1 => Some(0x40),
                   [other, 1] if other != 1 => Some(0x41), _ => None }
}
/// 선택한 CH0~CH5의 목표각만 바꾸고 전체 포즈를 보정 범위로 검사한다.
///
/// 각도는 centidegree이며 `9000`은 90도다. 성공하면 6축 목표와 변경 채널의
/// 비트 마스크를 반환한다. 잘못된 채널·목표·이동 시간은 `None`이다.
/// 이 함수는 이동을 시작하거나 PWM을 쓰지 않는다.
pub fn servo_target(cfg: &pico_device_protocol::ActuatorConfig, current: [u16;6], channel: u8,
                    angle: u16, move_ms: u16) -> Option<([u16;6],u8)> {
    if channel >= 6 { return None; }
    let mut target = current;
    target[channel as usize] = angle;
    if !cfg.accepts(&target, move_ms) { return None; }
    Some((target, 1 << channel))
}
/// 두 6축 포즈를 정수 선형 보간한다. 종료 시 목표를 넘지 않는다.
///
/// `elapsed`와 `duration`은 같은 단위를 사용한다. 실행부에서는 ms다.
/// `duration=0`은 1로 취급한다. 실제 출력과 속도 제한은 호출자 책임이다.
///
/// ```
/// use pico2_device_bench::interpolate_pose;
/// assert_eq!(interpolate_pose([8000; 6], [10000; 6], 500, 1000), [9000; 6]);
/// assert_eq!(interpolate_pose([8000; 6], [10000; 6], 2000, 1000), [10000; 6]);
/// ```
pub fn interpolate_pose(start:[u16;6],target:[u16;6],elapsed:u64,duration:u64)->[u16;6]{
    let duration=duration.max(1);let elapsed=elapsed.min(duration);
    core::array::from_fn(|i|(start[i]as i64+(target[i]as i64-start[i]as i64)*elapsed as i64/duration as i64)as u16)
}
#[cfg(test)]
mod motion_tests {
    use super::*;
    #[test]fn servo_driver_requires_exactly_one_valid_address(){
        assert_eq!(servo_driver_address([1,2]),Some(0x40));
        assert_eq!(servo_driver_address([2,1]),Some(0x41));
        for probes in [[0,0],[1,1],[2,2],[3,3],[4,5]] {
            assert_eq!(servo_driver_address(probes),None);
        }
    }
    #[test]fn single_servo_preserves_other_targets_and_checks_bounds(){
        let mut cfg=pico_device_protocol::ActuatorConfig::default();cfg.servo_enabled=true;
        let (target,mask)=servo_target(&cfg,[9000;6],2,10000,1000).unwrap();
        assert_eq!(mask,4);assert_eq!(target,[9000,9000,10000,9000,9000,9000]);
        assert!(servo_target(&cfg,[9000;6],6,9000,1000).is_none());
        assert!(servo_target(&cfg,[9000;6],0,18000,1000).is_none());
        cfg.servo_enabled=false;assert!(servo_target(&cfg,[9000;6],0,9000,1000).is_none());
    }
    #[test]fn interpolation_is_bounded_and_reaches_target_without_overshoot(){
        assert_eq!(interpolate_pose([8000;6],[10000;6],500,1000),[9000;6]);
        assert_eq!(interpolate_pose([10000;6],[8000;6],500,1000),[9000;6]);
        assert_eq!(interpolate_pose([8000;6],[10000;6],5000,1000),[10000;6]);
    }
}

/// 지원 버전의 Stop인지 검사한다. session과 seq의 일치는 요구하지 않는다.
///
/// CRC·COBS 검증은 이 함수보다 앞선 `pico_device_protocol::FrameDecoder`가
/// 담당한다. 이 함수만으로 수신 바이트의 무결성이 검증되지는 않는다.
pub fn is_priority_stop(frame: &Frame) -> bool {
    frame.version == VERSION && frame.body == Message::Stop
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
/// 동일 세션 안에서 요청 sequence를 분류한 결과.
pub enum Admission { New, Duplicate(AckCode), Stale }
/// 최근 8개 ACK를 보관해 중복 요청의 재실행을 막는다.
///
/// session 일치와 lease 검사는 `main.rs`의 호출자가 수행한다. 이 자료형은
/// sequence 순서와 중복 판정만 소유한다. u32 순서는 wraparound를 고려한다.
///
/// ```
/// use pico2_device_bench::{Admission, SessionGate};
/// use pico_device_protocol::AckCode;
/// let mut gate = SessionGate::new();
/// gate.open(9);
/// assert_eq!(gate.check(1), Admission::New);
/// gate.finish(1, AckCode::Ok);
/// assert_eq!(gate.check(1), Admission::Duplicate(AckCode::Ok));
/// ```
pub struct SessionGate {
    /// 현재 세션. 0은 원격 세션이 없음을 뜻한다.
    pub session: u64,
    newest: Option<u32>,
    cache: [Option<(u32, AckCode)>; 8],
    slot: usize,
}
impl SessionGate {
    /// 원격 세션과 처리 이력이 없는 문지기를 만든다.
    pub const fn new() -> Self { Self { session: 0, newest: None, cache: [None;8], slot: 0 } }
    /// 세션을 바꾸면서 이전 sequence와 ACK 캐시를 모두 비운다.
    pub fn open(&mut self, session: u64) { *self = Self::new(); self.session = session; }
    /// 요청을 실행하기 전에 새 요청·중복·오래된 순서로 분류한다.
    pub fn check(&self, seq: u32) -> Admission {
        for entry in self.cache.iter().flatten() { if entry.0 == seq { return Admission::Duplicate(entry.1); } }
        match self.newest {
            Some(previous) if seq.wrapping_sub(previous) == 0 || seq.wrapping_sub(previous) >= 0x8000_0000 => Admission::Stale,
            _ => Admission::New,
        }
    }
    /// 결정된 ACK 결과를 캐시한다. 새 요청이면 최신 sequence도 갱신한다.
    pub fn finish(&mut self, seq: u32, code: AckCode) {
        if matches!(self.check(seq), Admission::New) { self.newest = Some(seq); }
        self.cache[self.slot] = Some((seq, code));
        self.slot = (self.slot + 1) % self.cache.len();
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
/// SW6 제스처가 선택한 유한 진단 또는 전체 정지.
pub enum GestureAction { Test(Module), Stop }
/// 실제 입력이 30ms 연속 해제된 뒤 새 누름을 허용하는 재무장 상태.
///
/// 부팅·Stop·설정 변경 때 이미 눌려 있던 버튼의 release가 새 명령으로
/// 해석되지 않도록 사용한다. 입력은 active-low 보정을 끝낸 논리 raw 값이다.
pub struct ReleaseGuard { waiting: bool, since: Option<u64> }
impl ReleaseGuard {
    /// 먼저 안정된 해제를 기다리는 상태로 시작한다.
    pub const fn new() -> Self { Self { waiting: true, since: None } }
    /// 기존 해제 이력을 버리고 다시 30ms 해제를 요구한다.
    pub fn cancel(&mut self) { self.waiting = true; self.since = None; }
    /// Use the logical raw level, not a debouncer's reset-to-false state.
    pub fn armed(&mut self, raw_pressed: bool, now: u64) -> bool {
        if self.waiting {
            if raw_pressed { self.since = None; }
            else {
                let since = self.since.get_or_insert(now);
                if now.saturating_sub(*since) >= 30 { self.waiting = false; }
            }
        }
        !self.waiting
    }
}
/// SW6의 hold 구간을 진단 모듈 선택으로 바꾸는 상태 기계.
///
/// 기본 500ms 구간에서 release 시 0·1은 눈, 2는 왼손, 3은 오른손,
/// 4는 서보, 5는 전체 진단이다. 6구간 도달 또는 동작 중 새 누름은 Stop이다.
/// 실제 raw 해제 확인과 디바운스는 호출자가 먼저 처리한다.
pub struct Gesture {
    was_pressed: bool,
    started: u64,
    generation: u32,
    consumed: bool,
}
impl Gesture {
    /// 이전 눌림을 소비한 상태로 시작한다.
    pub const fn new() -> Self { Self { was_pressed: false, started: 0, generation: 0, consumed: true } }
    /// 눌림 상태를 맞추고 현재 제스처의 release 동작을 소비한다.
    pub fn clear(&mut self, pressed: bool) { self.was_pressed = pressed; self.consumed = true; }
    /// A generation change cancels a held gesture; its release cannot re-run.
    /// `now`와 `interval_ms`는 ms다. `interval_ms`는 검증된 0보다 큰 값이어야 한다.
    pub fn sample(&mut self, pressed: bool, active: bool, enabled: bool,
        generation: u32, now: u64, interval_ms: u32) -> Option<GestureAction> {
        if pressed && !self.was_pressed {
            self.started = now;
            self.generation = generation;
            self.consumed = !enabled || active;
            self.was_pressed = true;
            return if active { Some(GestureAction::Stop) } else { None };
        }
        if pressed && (generation != self.generation || !enabled) { self.consumed = true; }
        let count = now.saturating_sub(self.started) / interval_ms as u64;
        if pressed && !self.consumed && count >= 6 {
            self.consumed = true;
            return Some(GestureAction::Stop);
        }
        if !pressed && self.was_pressed {
            self.was_pressed = false;
            if self.consumed || active || !enabled || generation != self.generation { return None; }
            self.consumed = true;
            return Some(GestureAction::Test(match count {
                0 | 1 => Module::Matrix, 2 => Module::NeoLeft, 3 => Module::NeoRight,
                4 => Module::Servos, 5 => Module::All, _ => return Some(GestureAction::Stop),
            }));
        }
        None
    }
}

/// 순차 진단용 RGB·이동점 프레임을 만든다. SW3 랜덤 패턴과는 별개다.
pub fn neo_frame(segments: [u8; 3], phase: u16) -> [[u8;3]; CAPACITY] {
    let mut out = [[0;3]; CAPACITY];
    let total: usize = segments.iter().map(|n| *n as usize).sum();
    if phase < 9 {
        let segment = phase as usize / 3;
        let begin: usize = segments[..segment].iter().map(|n| *n as usize).sum();
        let end = (begin + segments[segment] as usize).min(CAPACITY);
        for pixel in &mut out[begin.min(CAPACITY)..end] { pixel[phase as usize % 3] = 32; }
    } else if (phase as usize - 9) < total.min(CAPACITY) { out[phase as usize - 9] = [32;3]; }
    out
}
/// 서보 진단의 `90 → 90-span → 90+span → 90`을 도 단위로 반환한다.
/// `span`은 검증된 `DeviceConfig::test_span_degrees` 범위의 값이어야 한다.
pub fn servo_angle(phase: u16, span: u8) -> u16 {
    match phase % 4 { 1 => 90 - span as u16, 2 => 90 + span as u16, _ => 90 }
}
/// 진단용 도 단위 각도를 공통 펄스 범위의 PCA9685 tick으로 환산한다.
/// 일반 구동의 축별 보정 `ActuatorConfig::ticks`와 구분한다.
pub fn servo_ticks(config: &DeviceConfig, angle: u16) -> u16 {
    let pulse = config.servo_min_us as u32 + ((config.servo_max_us - config.servo_min_us) as u32 * angle.min(180) as u32 + 90) / 180;
    ((pulse * 25 + 61) / 122) as u16
}
/// All 진단의 눈·왼손·오른손·서보 순서 또는 단일 모듈을 조회한다.
pub fn stage(selected: Module, index: usize) -> Option<Module> {
    if selected != Module::All { return if index == 0 { Some(selected) } else { None }; }
    [Module::Matrix, Module::NeoLeft, Module::NeoRight, Module::Servos].get(index).copied()
}

#[derive(Clone, Copy)]
/// 로봇 본체 기준 좌우 눈. 위에서 아래로 8행이며 bit7이 논리 왼쪽이다.
pub struct MatrixFrame { pub left: [u8;8], pub right: [u8;8] }
impl MatrixFrame {
    /// 두 눈이 모두 꺼진 논리 프레임.
    pub const BLANK: Self = Self { left:[0;8],right:[0;8] };
}
/// Physical daisy-chain buffers, independent of the robot's left/right eyes.
pub struct MatrixOutputFrame { pub near: [u8;8], pub far: [u8;8] }
/// Logical left/right are the robot's eyes, opposite the viewer's screen sides.
/// Observed wiring: near/first = robot left, mounted 90 degrees counterclockwise.
/// Far/second = robot right, upright. Map once here for diagnostics and SetEyes.
pub fn matrix_mount_frame(logical: MatrixFrame) -> MatrixOutputFrame {
    let mut near = [0u8; 8];
    for (y, row) in logical.left.iter().enumerate() {
        for (x, output_row) in near.iter_mut().enumerate() {
            if row & (0x80 >> x) != 0 {
                *output_row |= 1 << y;
            }
        }
    }
    MatrixOutputFrame { near, far: logical.right }
}
/// MAX7219 두 개의 직렬 연결에서 먼 모듈의 명령부터 전송한다.
pub fn matrix_packet(address:u8,near:u8,far:u8)->[u8;4] { [address,far,address,near] }
/// L/R 식별, 행·열 스캔, checker 등의 유한 진단 프레임을 조회한다.
pub fn matrix_frame(phase: u16) -> MatrixFrame {
    let mut frame = MatrixFrame::BLANK;
    match phase {
        0 => frame.left = [0x40,0x40,0x40,0x40,0x40,0x40,0x7e,0],
        1 => frame.right = [0x7c,0x42,0x42,0x7c,0x50,0x48,0x44,0],
        2..=9 => { frame.left[phase as usize - 2] = 0xff; frame.right = frame.left; }
        10..=17 => { frame.left = [1 << (phase - 10);8]; frame.right = frame.left; }
        18 => { frame.left = [0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55]; frame.right = [0x55,0xaa,0x55,0xaa,0x55,0xaa,0x55,0xaa]; }
        19 => { frame.left = [0,0x3c,0x42,0x52,0x52,0x42,0x3c,0]; frame.right = [0,0x3c,0x42,0x4a,0x4a,0x42,0x3c,0]; }
        _ => (),
    }
    frame
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn duplicate_and_out_of_order_never_restart() {
        let mut gate = SessionGate::new(); gate.open(9);
        assert_eq!(gate.check(1), Admission::New); gate.finish(1, AckCode::Ok);
        assert_eq!(gate.check(1), Admission::Duplicate(AckCode::Ok));
        gate.finish(2, AckCode::Busy);
        assert_eq!(gate.check(2), Admission::Duplicate(AckCode::Busy));
        assert_eq!(gate.check(0), Admission::Stale);
        for seq in 3..20 { gate.finish(seq, AckCode::Ok); }
        assert_eq!(gate.check(1), Admission::Stale);
        gate.open(10); assert_eq!(gate.check(1), Admission::New);
    }
    #[test]
    fn switch_hold_mapping_and_stop_consumes_release() {
        for (count, module) in [(0,Module::Matrix),(1,Module::Matrix),(2,Module::NeoLeft),(3,Module::NeoRight),(4,Module::Servos),(5,Module::All)] {
            let mut g = Gesture::new(); assert_eq!(g.sample(true,false,true,0,0,500),None);
            assert_eq!(g.sample(false,false,true,0,count*500+100,500),Some(GestureAction::Test(module)));
        }
        let mut g = Gesture::new(); g.sample(true,false,true,0,0,500);
        assert_eq!(g.sample(true,false,true,0,3000,500),Some(GestureAction::Stop));
        assert_eq!(g.sample(false,false,true,0,3100,500),None);
        let mut g = Gesture::new(); g.sample(true,false,true,1,0,500);
        g.sample(true,false,true,2,100,500);
        assert_eq!(g.sample(false,false,true,2,200,500),None);
        let mut g = Gesture::new(); assert_eq!(g.sample(true,true,true,0,0,500),Some(GestureAction::Stop));
        assert_eq!(g.sample(false,false,true,1,200,500),None);
    }
    #[test]
    fn boot_or_config_held_requires_real_raw_release_before_new_press() {
        let mut guard = ReleaseGuard::new();
        assert!(!guard.armed(true,0)); assert!(!guard.armed(true,2000));
        assert!(!guard.armed(false,2010)); assert!(!guard.armed(false,2039));
        assert!(guard.armed(false,2040));
        guard.cancel();
        // Even if TouchEngine.configure temporarily reports debounced false,
        // a physically held raw input cannot re-arm the diagnostic gesture.
        assert!(!guard.armed(true,3000)); assert!(!guard.armed(true,4000));
        assert!(!guard.armed(false,4010)); assert!(guard.armed(false,4040));
        let mut g = Gesture::new();
        assert_eq!(g.sample(true,false,true,1,4100,500),None);
        assert_eq!(g.sample(false,false,true,1,4200,500),Some(GestureAction::Test(Module::Matrix)));
    }
    #[test]
    fn segments_tail_black_and_small_servo_excursion() {
        let config = DeviceConfig::default();
        assert_eq!(config.left_total(),18); assert_eq!(config.right_total(),18);
        for phase in 0..27 {
            let f = neo_frame(config.left_segments, phase);
            assert!(f[18..].iter().all(|v| *v == [0;3]));
            assert!(f.iter().flatten().all(|v| *v <= 32));
        }
        assert_eq!(core::array::from_fn::<_,4,_>(|p| servo_angle(p as u16,10)), [90,80,100,90]);
        assert_eq!(servo_ticks(&config,90),307);
        assert!(servo_ticks(&config,80) < servo_ticks(&config,100));
        assert_eq!(stage(Module::All,3),Some(Module::Servos));
        assert_eq!(stage(Module::All,4),None);
    }
    #[test]
    fn stop_requires_protocol_version_but_not_session_or_sequence() {
        let mut frame = Frame { version: VERSION, session: 99, seq: 0, body: Message::Stop };
        assert!(is_priority_stop(&frame));
        frame.version = VERSION + 1;
        assert!(!is_priority_stop(&frame));
        frame.version = VERSION; frame.body = Message::RunTest(Module::All);
        assert!(!is_priority_stop(&frame));
    }
    #[test]
    fn stop_during_pending_debounce_consumes_later_release() {
        use pico_device_protocol::TouchEngine;
        let config=DeviceConfig::default(); let bit=1<<5;
        let mut engine=TouchEngine::new(config).unwrap();
        let mut guard=ReleaseGuard::new(); let mut gesture=Gesture::new();
        engine.sample(0,0); assert!(!guard.armed(false,0)); assert!(guard.armed(false,30));
        engine.sample(bit,40); // Raw press, not yet a debounced edge.
        guard.cancel(); gesture.clear(true); // Remote STOP at t=60, generation changes.
        engine.sample(bit,70);
        assert_eq!(engine.pressed_mask(),bit); assert!(!guard.armed(true,70));
        engine.sample(0,100); assert!(!guard.armed(false,100));
        engine.sample(0,130); assert!(guard.armed(false,130)); gesture.clear(false);
        assert_eq!(gesture.sample(false,false,true,1,130,500),None);
        // Only a fresh physical press after stable release can launch a test.
        engine.sample(bit,140); engine.sample(bit,170);
        assert_eq!(gesture.sample(engine.pressed_mask()&bit!=0,false,true,1,170,500),None);
        engine.sample(0,200); engine.sample(0,230);
        assert_eq!(gesture.sample(false,false,true,1,230,500),Some(GestureAction::Test(Module::Matrix)));
    }
    #[test]
    fn matrix_wire_order_is_far_before_near() {
        assert_eq!(matrix_packet(3,0x12,0x34),[3,0x34,3,0x12]);
        let left=matrix_frame(0); let right=matrix_frame(1);
        assert_ne!(left.left,[0;8]); assert_eq!(left.right,[0;8]);
        assert_eq!(right.left,[0;8]); assert_ne!(right.right,[0;8]);
    }
    #[test]
    fn observed_left_eye_is_rotated_near_and_right_eye_is_upright_far() {
        let left = matrix_frame(0).left;
        let output = matrix_mount_frame(MatrixFrame { left, right: matrix_frame(1).right });
        assert_eq!(output.near, [0,0x7f,0x40,0x40,0x40,0x40,0x40,0]);
        assert_eq!(output.far, matrix_frame(1).right);
        let l_only = matrix_mount_frame(matrix_frame(0));
        let r_only = matrix_mount_frame(matrix_frame(1));
        assert_ne!(l_only.near, [0;8]); assert_eq!(l_only.far, [0;8]);
        assert_eq!(r_only.near, [0;8]); assert_eq!(r_only.far, matrix_frame(1).right);
    }
    #[test]
    fn left_eye_mount_preserves_upright_row_and_column_scans() {
        // A logical top row becomes the module's right column before mounting.
        let top = matrix_mount_frame(matrix_frame(2));
        assert_eq!(top.near, [0x01;8]);
        assert_eq!(top.far, [0xff,0,0,0,0,0,0,0]);
        // A logical right column becomes the module's bottom row.
        let right_column = matrix_mount_frame(matrix_frame(10));
        assert_eq!(right_column.near, [0,0,0,0,0,0,0,0xff]);
        assert_eq!(right_column.far, [0x01;8]);
    }
    #[test]
    fn eye_mapping_keeps_blank_frames_blank_for_stop_and_startup() {
        let blank = matrix_mount_frame(MatrixFrame::BLANK);
        assert_eq!(blank.near, [0;8]);
        assert_eq!(blank.far, [0;8]);
    }
    #[test]
    fn corrupt_wire_never_reaches_stop_admission() {
        use pico_device_protocol::{encode_frame,FrameDecoder,MAX_WIRE};
        let frame=Frame{version:VERSION,session:5,seq:7,body:Message::Stop};
        let mut wire=[0;MAX_WIRE]; let len=encode_frame(&frame,&mut wire).unwrap();
        wire[len-2]^=0x80; // Corrupt CRC payload before the trailing delimiter.
        let mut decoder=FrameDecoder::new(); let mut actions=0;
        for &byte in &wire[..len]{
            if let Some(Ok(decoded))=decoder.push(byte){if is_priority_stop(&decoded){actions+=1;}}
        }
        assert_eq!(actions,0);
    }
}
