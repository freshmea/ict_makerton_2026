//! Bounded local energy VAD. Speech candidates are never Help permissions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Segment {
    Waiting,
    Speaking,
    Finished,
    TooLong,
}
pub struct Vad {
    noise: f64,
    voiced_ms: u64,
    silence_ms: u64,
    duration_ms: u64,
    started: bool,
}
impl Default for Vad {
    fn default() -> Self {
        Self {
            noise: 0.002,
            voiced_ms: 0,
            silence_ms: 0,
            duration_ms: 0,
            started: false,
        }
    }
}
impl Vad {
    pub fn push(&mut self, pcm: &[u8], rate: u32) -> Segment {
        if pcm.is_empty() || rate == 0 {
            return Segment::Waiting;
        }
        let n = pcm.len() / 2;
        let rms = (pcm
            .chunks_exact(2)
            .map(|x| {
                let v = i16::from_le_bytes([x[0], x[1]]) as f64 / 32768.;
                v * v
            })
            .sum::<f64>()
            / n as f64)
            .sqrt();
        let ms = (n as u64 * 1000 / rate as u64).max(1);
        let voiced = rms > (self.noise * 3.5).max(0.008);
        if !self.started && !voiced {
            self.noise = self.noise * 0.98 + rms * 0.02;
        }
        if voiced {
            self.voiced_ms += ms;
            self.silence_ms = 0;
        } else {
            self.silence_ms += ms;
        }
        if !self.started && self.voiced_ms >= 160 {
            self.started = true;
        }
        if !self.started && self.silence_ms >= 150 {
            self.voiced_ms = 0;
        }
        if self.started {
            self.duration_ms += ms;
        }
        if self.duration_ms >= 10000 {
            Segment::TooLong
        } else if self.started && self.silence_ms >= 650 {
            Segment::Finished
        } else if self.started {
            Segment::Speaking
        } else {
            Segment::Waiting
        }
    }
}
pub fn local_intent(text: &str) -> Option<super::decision::Action> {
    use super::decision::Action;
    let t = text.trim().to_lowercase().replace([' ', '.', '!', '?'], "");
    if [
        "멈춰",
        "멈추어",
        "그만",
        "중지",
        "stop",
        "기다려",
        "잠깐",
        "쉿",
        "조용히",
    ]
    .iter()
    .any(|s| t.starts_with(s))
    {
        return Some(Action::Wait);
    }
    if ["끝낼래", "공부끝", "종료", "finish", "이제끝"]
        .iter()
        .any(|s| t.starts_with(s))
    {
        return Some(Action::EndSession);
    }
    if [
        "응",
        "네",
        "그래",
        "아니",
        "음",
        "어",
        "알겠어",
        "됐어",
        "고마워",
        "잘모르겠어",
    ]
    .contains(&t.as_str())
    {
        return Some(Action::Wait);
    }
    None
}
pub fn wav(pcm: &[u8], rate: u32) -> Vec<u8> {
    let len = pcm.len() as u32;
    let mut w = b"RIFF".to_vec();
    w.extend((36 + len).to_le_bytes());
    w.extend(b"WAVEfmt ");
    w.extend(16u32.to_le_bytes());
    w.extend(1u16.to_le_bytes());
    w.extend(1u16.to_le_bytes());
    w.extend(rate.to_le_bytes());
    w.extend((rate * 2).to_le_bytes());
    w.extend(2u16.to_le_bytes());
    w.extend(16u16.to_le_bytes());
    w.extend(b"data");
    w.extend(len.to_le_bytes());
    w.extend(pcm);
    w
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn vad_silence_noise_and_bounded_utterance() {
        let mut v = Vad::default();
        for _ in 0..100 {
            assert_eq!(v.push(&[0; 960], 48000), Segment::Waiting);
        }
        let loud: Vec<u8> = (0..480)
            .flat_map(|i| {
                if i % 2 == 0 {
                    5000i16.to_le_bytes()
                } else {
                    (-5000i16).to_le_bytes()
                }
            })
            .collect();
        for _ in 0..20 {
            v.push(&loud, 48000);
        }
        assert_eq!(v.push(&loud, 48000), Segment::Speaking);
        let mut end = Segment::Waiting;
        for _ in 0..66 {
            end = v.push(&[0; 960], 48000);
        }
        assert_eq!(end, Segment::Finished);
        assert_eq!(
            local_intent("잠깐 기다려"),
            Some(super::super::decision::Action::Wait)
        );
        assert_eq!(local_intent("정답 말고 힌트 줘"), None);
    }
}
