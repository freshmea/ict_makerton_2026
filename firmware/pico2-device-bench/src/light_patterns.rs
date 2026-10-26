//! Group-aware, time-based NeoPixel animations. No delays or hardware ownership here.
//!
//! SW3 입력은 [`PatternButton`](crate::light_patterns::PatternButton)이 수락하고
//! [`ButtonPatterns`](crate::light_patterns::ButtonPatterns)가 선택 상태를 보관한다.
//! [`pattern_frame`](crate::light_patterns::pattern_frame)은 경과 시간에서 RGB 배열만 계산한다. 실제 PIO·DMA
//! 전송과 session·lease 검사는 `main.rs`의 장치 태스크가 담당한다.
//!
//! Inspired by Adafruit's strandtest/buttoncycler color wipe, rainbow and theater chase:
//! <https://github.com/adafruit/Adafruit_NeoPixel/tree/master/examples>
use crate::{CAPACITY, ReleaseGuard};
use pico_device_protocol::{TouchEvent, TouchKind};

/// 선택 가능한 패턴 수. ID는 0~9다.
pub const PATTERN_COUNT: u8 = 10;
/// 255를 전체 밝기로 볼 때 각 RGB 채널의 상한.
pub const MAX_CHANNEL: u8 = 32;
/// ID 순서의 패턴 이름. `pattern_frame`과 대응한다.
pub const PATTERN_NAMES: [&str; 10] = [
    "group rainbow",
    "color wipe",
    "theater chase",
    "rainbow theater chase",
    "group breathing",
    "group relay",
    "comet",
    "main row wave",
    "main column scan",
    "sparkle",
];
// Main lamp's DIN order: top 3, middle 4, bottom 3 (each row left to right).
/// 메인 램프 10픽셀의 3·4·3 행 인덱스.
pub const MAIN_ROWS: [usize; 10] = [0, 0, 0, 1, 1, 1, 1, 2, 2, 2];
/// 메인 램프의 각 행 안에서의 열 인덱스.
pub const MAIN_COLUMNS: [usize; 10] = [0, 1, 2, 0, 1, 2, 3, 0, 1, 2];

/// Initial release and generation changes are handled before accepting debounced edges.
///
/// 입력 번호는 SW1~SW6의 1-based 값이다. `sample_raw`를 먼저 호출하고
/// 디바운스된 Pressed를 `accepts`로 검사한다. release에서 선택하지 않는다.
pub struct PatternButton {
    index: u8,
    release: ReleaseGuard,
    generation: u32,
    armed: bool,
}
impl PatternButton {
    /// SW3용 입력 수락 상태를 만든다.
    pub const fn new() -> Self {
        Self::for_switch(3)
    }
    /// 지정한 SW 번호용 상태를 만든다. 호출자는 1~6을 사용한다.
    pub const fn for_switch(index: u8) -> Self {
        Self {
            index,
            release: ReleaseGuard::new(),
            generation: 0,
            armed: false,
        }
    }
    /// 다음 명령 전에 raw 입력의 안정된 해제를 다시 요구한다.
    pub fn cancel(&mut self) {
        self.release.cancel();
        self.armed = false;
    }
    /// 논리 raw 입력과 취소 세대를 갱신한다. 시각 단위는 ms다.
    pub fn sample_raw(&mut self, pressed: bool, generation: u32, now_ms: u64) {
        if generation != self.generation {
            self.cancel();
            self.generation = generation;
        }
        self.armed = self.release.armed(pressed, now_ms);
    }
    /// 재무장된 상태에서 지정 SW의 Pressed 이벤트만 수락한다.
    pub fn accepts(&self, event: &TouchEvent) -> bool {
        self.armed && event.index == self.index && event.kind == TouchKind::Pressed
    }
}

/// 직전 패턴을 제외한 선택과 경과 시간 기반 프레임 생성 상태.
///
/// 난수는 연출용이며 암호학적 용도가 아니다. `clear()`는 활성 상태만 지워
/// 다음 선택에서도 직전 번호 제외 규칙을 유지한다.
///
/// ```
/// use pico2_device_bench::light_patterns::ButtonPatterns;
/// let mut lights = ButtonPatterns::new(123);
/// let first = lights.select(17, 1000, 7);
/// let frame = lights.frame(1000, [4, 4, 10], 0);
/// assert!(frame[18..].iter().all(|pixel| *pixel == [0; 3]));
/// assert_ne!(lights.select(18, 2000, 7), first);
/// lights.clear();
/// assert_eq!(lights.frame(3000, [4, 4, 10], 0), [[0; 3]; 36]);
/// ```
pub struct ButtonPatterns {
    rng: u32,
    previous: Option<u8>,
    /// 현재 패턴 ID. `None`이면 검정 프레임을 반환한다.
    pub active: Option<u8>,
    /// 선택 당시 generation. 실제 출력 전 호출자가 현재 세대와 비교한다.
    pub generation: u32,
    started: u64,
}
impl ButtonPatterns {
    /// 장치 식별자 등의 seed로 선택기를 만든다. 출력은 비활성이다.
    pub fn new(seed: u64) -> Self {
        Self {
            rng: (seed as u32 ^ (seed >> 32) as u32).max(1),
            previous: None,
            active: None,
            generation: 0,
            started: 0,
        }
    }
    fn random(&mut self) -> u32 {
        let mut x = self.rng;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        self.rng = x;
        x
    }
    /// 직전과 다른 패턴을 고르고 시작 시각과 generation을 교체한다.
    pub fn select(&mut self, entropy: u32, now_ms: u64, generation: u32) -> u8 {
        self.rng = (self.rng ^ entropy).max(1);
        let count = if self.previous.is_some() {
            PATTERN_COUNT - 1
        } else {
            PATTERN_COUNT
        };
        // Rejection sampling avoids a modulo bias; xorshift's output excludes zero.
        let limit = u32::MAX - u32::MAX % count as u32;
        let draw = loop {
            let value = self.random();
            if value <= limit {
                break value - 1;
            }
        };
        let mut selected = (draw % count as u32) as u8;
        if let Some(last) = self.previous {
            if selected >= last {
                selected += 1;
            }
        }
        self.active = Some(selected);
        self.previous = Some(selected);
        self.started = now_ms;
        self.generation = generation;
        selected
    }
    /// 현재 패턴을 끈다. 마지막 선택 이력은 보존한다.
    pub fn clear(&mut self) {
        self.active = None;
    }
    /// 현재 시각의 RGB 배열을 계산한다. side 0은 왼손, 1은 오른손이다.
    pub fn frame(&self, now_ms: u64, segments: [u8; 3], side: usize) -> [[u8; 3]; CAPACITY] {
        self.active.map_or([[0; 3]; CAPACITY], |id| {
            pattern_frame(id, now_ms.saturating_sub(self.started), segments, side)
        })
    }
}

fn wheel(hue: u8) -> [u8; 3] {
    let h = hue as u16;
    let rgb = if h < 85 {
        [255 - h * 3, h * 3, 0]
    } else if h < 170 {
        [0, 255 - (h - 85) * 3, (h - 85) * 3]
    } else {
        [(h - 170) * 3, 0, 255 - (h - 170) * 3]
    };
    rgb.map(|v| (v * MAX_CHANNEL as u16 / 255) as u8)
}
fn scale(rgb: [u8; 3], level: u8) -> [u8; 3] {
    rgb.map(|v| (v as u16 * level as u16 / 255) as u8)
}
fn triangle(t: u64, period: u64) -> u8 {
    let p = t % period;
    let half = period / 2;
    ((if p < half { p } else { period - p }) * 255 / half) as u8
}
fn hash(mut n: u32) -> u32 {
    n ^= n >> 16;
    n = n.wrapping_mul(0x7feb352d);
    n ^= n >> 15;
    n = n.wrapping_mul(0x846ca68b);
    n ^ (n >> 16)
}

/// One frame, with separate floor/arm/main phases. All unused tail pixels stay black.
/// ID와 경과 ms로 바닥·팔·메인 세 그룹의 프레임을 만든다.
///
/// 검증된 segment 합계는 1~36이다. 기본값은 `[4,4,10]`이며 미사용 tail은
/// 검정이다. 각 채널은 [`MAX_CHANNEL`] 이하이고 실제 전송은 하지 않는다.
pub fn pattern_frame(id: u8, elapsed: u64, segments: [u8; 3], side: usize) -> [[u8; 3]; CAPACITY] {
    let mut out = [[0; 3]; CAPACITY];
    let mut begin = 0;
    for (group, size) in segments.into_iter().enumerate() {
        let end = (begin + size as usize).min(CAPACITY);
        let length = end - begin;
        for (j, pixel) in out[begin..end].iter_mut().enumerate() {
            let hue = (elapsed / 20 + group as u64 * 85 + side as u64 * 24) as u8;
            let color = wheel(hue);
            *pixel = match id {
                0 => color,
                1 => {
                    // Wipe and clear each group at its own length, with a phase offset.
                    let step = (elapsed / 100 + group as u64 * 2) as usize;
                    if j <= step % (length + 2) && step % (length + 2) < length {
                        color
                    } else {
                        [0; 3]
                    }
                }
                2 | 3 => {
                    if (j + (elapsed / 120) as usize + group) % 3 == 0 {
                        if id == 3 {
                            wheel(hue.wrapping_add((j * 256 / length) as u8))
                        } else {
                            wheel((group * 85 + side * 24) as u8)
                        }
                    } else {
                        [0; 3]
                    }
                }
                4 => scale(
                    wheel((group * 85 + side * 24) as u8),
                    24 + (triangle(elapsed + group as u64 * 450, 2400) as u16 * 231 / 255) as u8,
                ),
                5 => {
                    if (elapsed / 350) as usize % 3 == group {
                        color
                    } else {
                        [0; 3]
                    }
                }
                6 => {
                    let head = (elapsed / 100) as usize % length;
                    let distance = (head + length - j) % length;
                    if distance < 3 {
                        scale(color, [255, 100, 30][distance])
                    } else {
                        [0; 3]
                    }
                }
                7 => {
                    let row = if group == 2 {
                        MAIN_ROWS.get(j).copied().unwrap_or(2)
                    } else {
                        group
                    };
                    if row == (elapsed / 250) as usize % 3 {
                        color
                    } else {
                        scale(color, 20)
                    }
                }
                8 => {
                    let column = if group == 2 {
                        MAIN_COLUMNS.get(j).copied().unwrap_or(j % 4)
                    } else {
                        j % 4
                    };
                    let phase = (elapsed / 180) as usize % 6;
                    let scan = if phase <= 3 { phase } else { 6 - phase };
                    if column == scan {
                        color
                    } else {
                        scale(color, 20)
                    }
                }
                9 => {
                    let key = (elapsed / 120) as u32
                        ^ (group as u32 * 4099)
                        ^ (j as u32 * 131)
                        ^ (side as u32 * 65537);
                    if hash(key) % 5 == 0 {
                        wheel(hash(key.wrapping_add(1)) as u8)
                    } else {
                        scale(color, 12)
                    }
                }
                _ => [0; 3],
            };
        }
        begin = end;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use pico_device_protocol::{DeviceConfig, TouchEngine};

    #[test]
    fn all_patterns_animate_with_bounded_channels_and_black_tails() {
        for id in 0..PATTERN_COUNT {
            let initial = pattern_frame(id, 0, [4, 4, 10], 0);
            assert!(
                (1..=60).any(|t| pattern_frame(id, t * 100, [4, 4, 10], 0) != initial),
                "{id}"
            );
            for segments in [[4, 4, 10], [0, 0, 0], [36, 0, 0], [255, 255, 255]] {
                let total = segments
                    .iter()
                    .map(|&v| v as usize)
                    .sum::<usize>()
                    .min(CAPACITY);
                for t in [0, 120, 350, 999, 2400, u32::MAX as u64] {
                    for side in 0..2 {
                        let frame = pattern_frame(id, t, segments, side);
                        assert!(frame.iter().flatten().all(|&v| v <= MAX_CHANNEL));
                        assert!(frame[total..].iter().all(|&p| p == [0; 3]));
                    }
                }
            }
        }
    }
    #[test]
    fn random_selection_covers_ten_without_immediate_repeats_and_restarts() {
        let mut player = ButtonPatterns::new(123456);
        let mut mask = 0u16;
        let mut last = None;
        for n in 0..1000 {
            let chosen = player.select(n * 799, n as u64, 7);
            assert_ne!(Some(chosen), last);
            assert!(chosen < PATTERN_COUNT);
            mask |= 1 << chosen;
            last = Some(chosen);
            assert_eq!(
                player.frame(n as u64, [4, 4, 10], 0),
                pattern_frame(chosen, 0, [4, 4, 10], 0)
            );
        }
        assert_eq!(mask, 1023);
        player.clear();
        assert_eq!(player.frame(9999, [4, 4, 10], 0), [[0; 3]; CAPACITY]);
    }
    #[test]
    fn main_row_wave_uses_three_four_three_and_groups_relay_independently() {
        for (time, range) in [(0, 8..11), (250, 11..15), (500, 15..18)] {
            let frame = pattern_frame(7, time, [4, 4, 10], 0);
            for i in 8..18 {
                assert_eq!(
                    frame[i].iter().copied().max().unwrap() > 2,
                    range.contains(&i)
                );
            }
        }
        for group in 0..3 {
            let frame = pattern_frame(5, group * 350, [4, 4, 10], 0);
            for (index, range) in [0..4, 4..8, 8..18].into_iter().enumerate() {
                assert_eq!(
                    frame[range].iter().any(|&p| p != [0; 3]),
                    index == group as usize
                );
            }
        }
    }
    #[test]
    fn real_debouncer_short_press_hold_bounce_and_generation_release_guard() {
        for index in [3, 4] {
            for active_low in [false, true] {
                let bit = 1 << (index - 1);
                let mut cfg = DeviceConfig::default();
                if active_low {
                    cfg.touch_active_low_mask = bit;
                }
                let mut engine = TouchEngine::new(cfg).unwrap();
                let mut button = PatternButton::for_switch(index);
                let mut other = PatternButton::for_switch(if index == 3 { 4 } else { 3 });
                let mut accepted = 0;
                for t in (0..4000).step_by(5) {
                    // Boot held; release; bouncing short press; long hold; Stop while held;
                    // release then a new press. Only three fresh presses should act.
                    let pressed = t < 100
                        || (200..205).contains(&t)
                        || (210..215).contains(&t)
                        || (220..280).contains(&t)
                        || (400..3500).contains(&t)
                        || t >= 3600;
                    let generation = if t < 1000 { 1 } else { 2 };
                    button.sample_raw(pressed, generation, t);
                    other.sample_raw(false, generation, t);
                    let raw = if pressed ^ active_low { bit } else { 0 };
                    for event in engine.sample(raw, t) {
                        assert!(!other.accepts(&event));
                        if button.accepts(&event) {
                            accepted += 1;
                        }
                    }
                }
                assert_eq!(accepted, 3);
            }
        }
    }
}
