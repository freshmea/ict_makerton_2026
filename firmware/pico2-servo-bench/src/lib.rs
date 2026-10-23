#![no_std]

/// Nominal angle labels need calibration against the actual servo and mechanism.
/// Defaults intentionally use 1000..2000 us, not unverified mechanical end stops.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PulseRange {
    pub min_us: u16,
    pub max_us: u16,
}

impl Default for PulseRange {
    fn default() -> Self {
        Self { min_us: 1000, max_us: 2000 }
    }
}

impl PulseRange {
    pub const fn new(min_us: u16, max_us: u16) -> Option<Self> {
        if min_us >= 500 && max_us <= 2500 && min_us < max_us {
            Some(Self { min_us, max_us })
        } else {
            None
        }
    }

    pub fn pulse_us(self, angle: u16) -> u16 {
        let angle = angle.min(180) as u32;
        (self.min_us as u32 + ((self.max_us - self.min_us) as u32 * angle + 90) / 180) as u16
    }

    /// Prescale=121 yields an actual nominal period 19988.48 us at 25 MHz.
    pub fn ticks(self, angle: u16) -> u16 {
        ((self.pulse_us(angle) as u32 * 25 + 61) / 122) as u16
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Command {
    Status,
    Scan,
    Arm,
    Sweep,
    Config(PulseRange),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Input {
    Command(Command),
    Ping,
    Stop,
}

pub fn parse(line: &str) -> Option<Input> {
    let mut words = line.split_ascii_whitespace();
    let command = match words.next()? {
        "status" => Input::Command(Command::Status),
        "scan" => Input::Command(Command::Scan),
        "arm" => Input::Command(Command::Arm),
        "sweep" => Input::Command(Command::Sweep),
        "stop" => Input::Stop,
        "ping" => Input::Ping,
        "config" => {
            let low = words.next()?.parse().ok()?;
            let high = words.next()?.parse().ok()?;
            Input::Command(Command::Config(PulseRange::new(low, high)?))
        }
        _ => return None,
    };
    if words.next().is_some() { None } else { Some(command) }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endpoints_and_monotonic_ticks() {
        let p = PulseRange::default();
        assert_eq!((p.pulse_us(0), p.pulse_us(90), p.pulse_us(180)), (1000,1500,2000));
        assert_eq!((p.ticks(0), p.ticks(180)), (205,410));
        let ticks: [u16; 181] = core::array::from_fn(|n| p.ticks(n as u16));
        assert!(ticks.windows(2).all(|a| a[0] <= a[1]));
        assert_eq!(p.ticks(181), p.ticks(180));
    }

    #[test]
    fn rejects_out_of_range_and_ambiguous_commands() {
        assert_eq!(parse("stop"), Some(Input::Stop));
        assert_eq!(parse("sweep"), Some(Input::Command(Command::Sweep)));
        for invalid in ["sweep 1", "stop later", "config 499 2000", "config 1000 2501", "config 2000 1000", "config 1000 2000 extra"] {
            assert_eq!(parse(invalid), None, "{invalid}");
        }
        assert_eq!(parse("config 500 2500"), Some(Input::Command(Command::Config(PulseRange { min_us:500, max_us:2500 }))));
    }
}
