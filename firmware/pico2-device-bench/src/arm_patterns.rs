//! Bounded SW4 arm gestures for CH0..CH3; pure timing and interpolation.
//!
//! [`ArmPatterns`](crate::arm_patterns::ArmPatterns)는 목표각만 계산한다. session·lease·기준각·fault 검사,
//! PCA 쓰기와 완료 후 PWM 차단은 실행부 `Application`의 책임이다.
//! 시간은 ms, 각도는 centidegree다. 9000은 90도다.
use crate::{interpolate_pose, light_patterns::ButtonPatterns};

/// 기준각 양쪽으로 허용한 최대 편차. 1200은 12도다.
pub const EXCURSION_CDEG: i32 = 1200;
/// 실행부가 SW4 설정에 사용하는 최대 속도. 2400은 24도/초다.
pub const MAX_SPEED_CDEG_S: u16 = 2400;
/// 한 보간 구간의 길이.
pub const STEP_MS: u64 = 1000;
/// 여덟 목표 구간과 마지막 복귀를 합친 9초.
pub const TOTAL_MS: u64 = 9 * STEP_MS;
/// 조명 선택기와 같은 0~9 ID 순서의 팔 패턴 이름.
pub const PATTERN_NAMES: [&str; 10] = [
    "together wave",
    "left-right alternation",
    "paired twist",
    "forward ripple",
    "reverse ripple",
    "outer-inner wave",
    "diagonal wave",
    "staircase",
    "small flutter",
    "breathing arms",
];
// Signed per-channel offsets, in thousandths of the 12 degree excursion.
const STEPS: [[[i16; 4]; 8]; 10] = [
    [
        [1000; 4], [-1000; 4], [1000; 4], [-1000; 4], [1000; 4], [-1000; 4], [1000; 4], [0; 4],
    ],
    [
        [1000, 1000, -1000, -1000],
        [-1000, -1000, 1000, 1000],
        [1000, 1000, -1000, -1000],
        [-1000, -1000, 1000, 1000],
        [1000, 1000, -1000, -1000],
        [-1000, -1000, 1000, 1000],
        [1000, 1000, -1000, -1000],
        [0; 4],
    ],
    [
        [1000, -1000, 1000, -1000],
        [-1000, 1000, -1000, 1000],
        [1000, -1000, 1000, -1000],
        [-1000, 1000, -1000, 1000],
        [1000, -1000, 1000, -1000],
        [-1000, 1000, -1000, 1000],
        [1000, -1000, 1000, -1000],
        [0; 4],
    ],
    [
        [1000, 0, 0, 0],
        [0, 1000, 0, 0],
        [0, 0, 1000, 0],
        [0, 0, 0, 1000],
        [-1000, 0, 0, 0],
        [0, -1000, 0, 0],
        [0, 0, -1000, 0],
        [0, 0, 0, -1000],
    ],
    [
        [0, 0, 0, 1000],
        [0, 0, 1000, 0],
        [0, 1000, 0, 0],
        [1000, 0, 0, 0],
        [0, 0, 0, -1000],
        [0, 0, -1000, 0],
        [0, -1000, 0, 0],
        [-1000, 0, 0, 0],
    ],
    [
        [1000, 0, 0, 1000],
        [0, 1000, 1000, 0],
        [-1000, 0, 0, -1000],
        [0, -1000, -1000, 0],
        [1000, 0, 0, 1000],
        [0, 1000, 1000, 0],
        [-1000, 0, 0, -1000],
        [0; 4],
    ],
    [
        [1000, 0, 0, -1000],
        [0, 1000, -1000, 0],
        [-1000, 0, 0, 1000],
        [0, -1000, 1000, 0],
        [1000, 0, 0, -1000],
        [0, 1000, -1000, 0],
        [-1000, 0, 0, 1000],
        [0; 4],
    ],
    [
        [1000, 0, 0, 0],
        [1000, 1000, 0, 0],
        [1000, 1000, 1000, 0],
        [1000; 4],
        [0, 1000, 1000, 1000],
        [0, 0, 1000, 1000],
        [0, 0, 0, 1000],
        [0; 4],
    ],
    [
        [500, -500, 500, -500],
        [-500, 500, -500, 500],
        [500, -500, 500, -500],
        [-500, 500, -500, 500],
        [500, -500, 500, -500],
        [-500, 500, -500, 500],
        [500, -500, 500, -500],
        [0; 4],
    ],
    [
        [500; 4], [1000; 4], [500; 4], [0; 4], [-500; 4], [-1000; 4], [-500; 4], [0; 4],
    ],
];

/// 최초 기준각을 보존하며 CH0~CH3을 움직이는 유한 패턴 계산기.
///
/// CH4~CH5의 반환값은 기준값을 유지한다. 이는 물리 PWM의 독립 보장을
/// 뜻하지 않는다. `sample()`이 종료각을 반환해도 active를 지우지는 않는다.
///
/// ```
/// use pico2_device_bench::arm_patterns::{ArmPatterns, TOTAL_MS};
/// let base = [9000; 6];
/// let mut arms = ArmPatterns::new(123);
/// arms.select(base, 17, 1000);
/// assert_eq!(arms.sample(1000), base);
/// assert_eq!(arms.sample(1000 + TOTAL_MS), base);
/// assert!(arms.finished(1000 + TOTAL_MS));
/// assert!(arms.active());
/// arms.clear();
/// assert!(!arms.active());
/// ```
pub struct ArmPatterns {
    selector: ButtonPatterns,
    base: [u16; 6],
    start: [u16; 6],
    started: u64,
}
impl ArmPatterns {
    /// 비활성 패턴 계산기를 만든다. 첫 select에서 기준각을 저장한다.
    pub fn new(seed: u64) -> Self {
        Self {
            selector: ButtonPatterns::new(seed),
            base: [9000; 6],
            start: [9000; 6],
            started: 0,
        }
    }
    /// 선택한 패턴이 아직 clear되지 않았는지 반환한다.
    pub fn active(&self) -> bool {
        self.selector.active.is_some()
    }
    /// 패턴을 선택하고 현재 위치에서 시작한다. 재선택 중에는 원래 기준각을 유지한다.
    pub fn select(&mut self, current: [u16; 6], entropy: u32, now_ms: u64) -> u8 {
        // Keep the original center while changing an in-flight pattern, avoiding drift.
        if !self.active() {
            self.base = current;
        }
        self.start = current;
        self.started = now_ms;
        self.selector.select(entropy, now_ms, 0)
    }
    fn target(&self, pattern: usize, step: usize) -> [u16; 6] {
        let mut target = self.base;
        if step < 8 {
            for i in 0..4 {
                let offset = STEPS[pattern][step][i] as i32 * EXCURSION_CDEG / 1000;
                target[i] = (self.base[i] as i32 + offset).clamp(0, 18000) as u16;
            }
        }
        target
    }
    /// 현재 시각의 6축 목표를 계산한다. 종료 시 기준각으로 돌아온다.
    pub fn sample(&self, now_ms: u64) -> [u16; 6] {
        let Some(pattern) = self.selector.active else {
            return self.start;
        };
        let elapsed = now_ms.saturating_sub(self.started).min(TOTAL_MS);
        if elapsed == TOTAL_MS {
            return self.base;
        }
        let step = (elapsed / STEP_MS) as usize;
        let from = if step == 0 {
            self.start
        } else {
            self.target(pattern as usize, step - 1)
        };
        interpolate_pose(
            from,
            self.target(pattern as usize, step),
            elapsed % STEP_MS,
            STEP_MS,
        )
    }
    /// active이며 9초가 지났는지 검사한다. 상태를 변경하지 않는다.
    pub fn finished(&self, now_ms: u64) -> bool {
        self.active() && now_ms.saturating_sub(self.started) >= TOTAL_MS
    }
    /// 출력부가 PWM 정리를 끝낸 뒤 활성 패턴을 해제한다.
    pub fn clear(&mut self) {
        self.selector.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn ten_patterns_preserve_other_axes_and_obey_travel_speed_and_completion() {
        for base in [
            [9000, 9000, 9000, 9000, 4200, 12300],
            [0, 100, 17900, 18000, 5000, 15000],
        ] {
            for pattern in 0..10 {
                let mut player = ArmPatterns::new(123);
                player.select(base, 17, 0);
                player.selector.active = Some(pattern);
                let mut last = base;
                for t in (0..=TOTAL_MS).step_by(20) {
                    let pose = player.sample(t);
                    assert_eq!(pose[4..], base[4..]);
                    for i in 0..4 {
                        assert!(pose[i] <= 18000);
                        assert!(pose[i].abs_diff(base[i]) <= EXCURSION_CDEG as u16);
                        assert!(
                            pose[i].abs_diff(last[i]) as u64 <= MAX_SPEED_CDEG_S as u64 * 20 / 1000
                        );
                    }
                    last = pose;
                }
                assert_eq!(player.sample(TOTAL_MS), base);
                assert!(!player.finished(TOTAL_MS - 1));
                assert!(player.finished(TOTAL_MS));
                player.clear();
                assert!(!player.active());
                assert!(!player.finished(TOTAL_MS));
            }
        }
    }
    #[test]
    fn reselect_is_immediate_continuous_and_does_not_accumulate_offsets() {
        let mut player = ArmPatterns::new(456);
        let base = [9000; 6];
        let mut current = base;
        let mut previous = None;
        let mut mask = 0u16;
        for n in 0..1000 {
            let now = n as u64 * 350;
            let id = player.select(current, n * 701, now);
            assert_ne!(Some(id), previous);
            assert!(id < 10);
            mask |= 1 << id;
            assert_eq!(player.sample(now), current);
            assert_eq!(player.sample(now + TOTAL_MS), base);
            let next = player.sample(now + 350);
            for i in 0..4 {
                assert!(next[i].abs_diff(base[i]) <= EXCURSION_CDEG as u16);
                assert!(
                    next[i].abs_diff(current[i]) as u64 <= MAX_SPEED_CDEG_S as u64 * 350 / 1000
                );
            }
            current = next;
            previous = Some(id);
        }
        assert_eq!(mask, 1023);
    }
    #[test]
    fn all_ten_gestures_have_distinct_keyframes() {
        for i in 0..10 {
            for j in i + 1..10 {
                assert_ne!(STEPS[i], STEPS[j]);
            }
        }
    }
    #[test]
    fn doubled_swing_reaches_twelve_degrees_each_side_of_the_saved_center() {
        let base = [2800, 6500, 10600, 7700, 17700, 13400];
        let mut player = ArmPatterns::new(123);
        player.select(base, 1, 0);
        player.selector.active = Some(0);
        assert_eq!(player.sample(1000), [4000, 7700, 11800, 8900, 17700, 13400]);
        assert_eq!(player.sample(2000), [1600, 5300, 9400, 6500, 17700, 13400]);
        assert_eq!(player.sample(TOTAL_MS), base);
    }
}
