#![no_std]
#[path = "../../shared/picotool_reset.rs"]
pub mod picotool_reset;

use pico_device_protocol::{AckCode, DeviceConfig, Module};
pub const CAPACITY: usize = 36;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Admission { New, Duplicate(AckCode), Stale }
pub struct SessionGate {
    pub session: u64,
    newest: Option<u32>,
    cache: [Option<(u32, AckCode)>; 8],
    slot: usize,
}
impl SessionGate {
    pub const fn new() -> Self { Self { session: 0, newest: None, cache: [None;8], slot: 0 } }
    pub fn open(&mut self, session: u64) { *self = Self::new(); self.session = session; }
    pub fn check(&self, seq: u32) -> Admission {
        for entry in self.cache.iter().flatten() { if entry.0 == seq { return Admission::Duplicate(entry.1); } }
        match self.newest {
            Some(previous) if seq.wrapping_sub(previous) == 0 || seq.wrapping_sub(previous) >= 0x8000_0000 => Admission::Stale,
            _ => Admission::New,
        }
    }
    pub fn finish(&mut self, seq: u32, code: AckCode) {
        if matches!(self.check(seq), Admission::New) { self.newest = Some(seq); }
        self.cache[self.slot] = Some((seq, code));
        self.slot = (self.slot + 1) % self.cache.len();
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GestureAction { Test(Module), Stop }
pub struct ReleaseGuard { waiting: bool, since: Option<u64> }
impl ReleaseGuard {
    pub const fn new() -> Self { Self { waiting: true, since: None } }
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
pub struct Gesture {
    was_pressed: bool,
    started: u64,
    generation: u32,
    consumed: bool,
}
impl Gesture {
    pub const fn new() -> Self { Self { was_pressed: false, started: 0, generation: 0, consumed: true } }
    pub fn clear(&mut self, pressed: bool) { self.was_pressed = pressed; self.consumed = true; }
    /// A generation change cancels a held gesture; its release cannot re-run.
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
pub fn servo_angle(phase: u16, span: u8) -> u16 {
    match phase % 4 { 1 => 90 - span as u16, 2 => 90 + span as u16, _ => 90 }
}
pub fn servo_ticks(config: &DeviceConfig, angle: u16) -> u16 {
    let pulse = config.servo_min_us as u32 + ((config.servo_max_us - config.servo_min_us) as u32 * angle.min(180) as u32 + 90) / 180;
    ((pulse * 25 + 61) / 122) as u16
}
pub fn stage(selected: Module, index: usize) -> Option<Module> {
    if selected != Module::All { return if index == 0 { Some(selected) } else { None }; }
    [Module::Matrix, Module::NeoLeft, Module::NeoRight, Module::Servos].get(index).copied()
}

#[derive(Clone, Copy)]
pub struct MatrixFrame { pub left: [u8;8], pub right: [u8;8] }
impl MatrixFrame { pub const BLANK: Self = Self { left:[0;8],right:[0;8] }; }
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
        assert_eq!((0..4).map(|p| servo_angle(p,10)).collect::<heapless::Vec<u16,4>>().as_slice(), &[90,80,100,90]);
        assert_eq!(servo_ticks(&config,90),307);
        assert!(servo_ticks(&config,80) < servo_ticks(&config,100));
        assert_eq!(stage(Module::All,3),Some(Module::Servos));
        assert_eq!(stage(Module::All,4),None);
    }
}
