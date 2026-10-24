use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
pub mod decision;
pub mod shm;
pub mod speech;
pub const MAX_BODY: usize = 65536;
pub const LEASE_MS: u64 = 750;
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
pub fn error(s: impl Into<String>) -> Box<dyn std::error::Error + Send + Sync> {
    Box::new(io::Error::other(s.into()))
}
pub fn monotonic_ms() -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // CLOCK_MONOTONIC is shared across Linux processes on this boot.
    assert_eq!(
        unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) },
        0
    );
    ts.tv_sec as u64 * 1000 + ts.tv_nsec as u64 / 1_000_000
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub v: u8,
    pub id: u64,
    pub deadline_ms: u64,
    pub body: Command,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "cmd", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    Status,
    Stop,
    Acquire {
        owner: u64,
        epoch: u64,
    },
    Renew {
        owner: u64,
        epoch: u64,
    },
    Test {
        owner: u64,
        epoch: u64,
        module: String,
    },
    Help,
    Finish,
    PutGoal {
        text: String,
    },
    GetGoal,
    DeleteGoal,
    Decide {
        text: String,
    },
    StartTurn {
        #[serde(default)]
        text: Option<String>,
        #[serde(default)]
        listen: bool,
        #[serde(default)]
        cloud_consent: bool,
        #[serde(default)]
        audio_cloud_consent: bool,
        #[serde(default)]
        speak: bool,
    },
    TurnResult,
    Usage,
    Correct {
        text: String,
        #[serde(default)]
        cloud_consent: bool,
        #[serde(default)]
        speak: bool,
    },
    Dialogue {
        owner: u64,
        epoch: u64,
        text: String,
        cloud_consent: bool,
        #[serde(default)]
        audio_wav: Option<String>,
        #[serde(default)]
        synthesize: bool,
    },
    Memory {
        request: MemoryRequest,
    },
    Snapshot {
        camera: u8,
    },
    Ocr {
        camera: u8,
        roi: [u32; 4],
        #[serde(default)]
        rotation: u16,
    },
    ConfirmProblem {
        text: String,
    },
    Pose {
        #[serde(default)]
        owner: u64,
        #[serde(default)]
        epoch: u64,
        targets_cdeg: [u16; 6],
        move_ms: u16,
    },
    Light {
        #[serde(default)]
        owner: u64,
        #[serde(default)]
        epoch: u64,
        rgb: [u8; 3],
        brightness: u8,
        period_ms: u16,
    },
    Eyes {
        #[serde(default)]
        owner: u64,
        #[serde(default)]
        epoch: u64,
        left: [u8; 8],
        right: [u8; 8],
        brightness: u8,
    },
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum MemoryRequest {
    Consent {
        enabled: bool,
    },
    Save {
        text: String,
        confirmed: bool,
        #[serde(default)]
        source: String,
    },
    Update {
        id: u64,
        text: String,
        confirmed: bool,
        #[serde(default)]
        source: String,
    },
    Search {
        query: String,
    },
    List {
        #[serde(default)]
        before: u64,
    },
    Delete {
        id: u64,
    },
    DeleteAll,
    Export {
        #[serde(default)]
        before: u64,
    },
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Reply {
    pub v: u8,
    pub id: u64,
    pub generation: u64,
    pub ok: bool,
    pub data: Value,
}
impl Request {
    pub fn new(body: Command) -> Self {
        let now = monotonic_ms();
        Self {
            v: 1,
            id: now,
            deadline_ms: now + 2000,
            body,
        }
    }
    pub fn validate(&self) -> Result<()> {
        let now = monotonic_ms();
        if self.v != 1 {
            return Err(error("unsupported schema version"));
        }
        if !matches!(self.body, Command::Stop)
            && (self.deadline_ms < now || self.deadline_ms > now + 5000)
        {
            return Err(error("expired or excessive monotonic deadline"));
        }
        Ok(())
    }
}
pub async fn read_frame<R: AsyncRead + Unpin>(r: &mut R) -> Result<Vec<u8>> {
    let n = r.read_u32().await? as usize;
    if n == 0 || n > MAX_BODY {
        return Err(error("invalid frame length"));
    }
    let mut data = vec![0; n];
    r.read_exact(&mut data).await?;
    Ok(data)
}
pub async fn write_frame<W: AsyncWrite + Unpin>(w: &mut W, data: &[u8]) -> Result<()> {
    if data.is_empty() || data.len() > MAX_BODY {
        return Err(error("invalid frame length"));
    }
    w.write_u32(data.len() as u32).await?;
    w.write_all(data).await?;
    Ok(())
}
#[derive(Debug, Default)]
pub struct Lease {
    pub owner: u64,
    pub epoch: u64,
    pub until_ms: u64,
    pub stopped: bool,
    retired: std::collections::HashSet<u64>,
}
impl Lease {
    pub fn acquire(&mut self, owner: u64, epoch: u64, now: u64) -> Result<()> {
        if owner == 0 || epoch == 0 {
            return Err(error("zero owner or epoch"));
        }
        if self.retired.contains(&owner) {
            return Err(error("retired controller generation"));
        }
        if self.valid(now) && self.owner != owner {
            return Err(error("another controller owns this device"));
        }
        if self.owner == owner && epoch <= self.epoch {
            return Err(error("new acquire requires a newer epoch"));
        }
        if self.owner != 0 && self.owner != owner {
            if self.retired.len() >= 64 {
                return Err(error("owner history full; manual restart required"));
            }
            self.retired.insert(self.owner);
        }
        self.owner = owner;
        self.epoch = epoch;
        self.until_ms = now + LEASE_MS;
        self.stopped = false;
        Ok(())
    }
    pub fn valid(&self, now: u64) -> bool {
        self.owner != 0 && !self.stopped && now < self.until_ms
    }
    pub fn check(&self, owner: u64, epoch: u64, now: u64) -> Result<()> {
        if !self.valid(now) || self.owner != owner || self.epoch != epoch {
            Err(error("no current controller lease / stale epoch"))
        } else {
            Ok(())
        }
    }
    pub fn renew(&mut self, owner: u64, epoch: u64, now: u64) -> Result<()> {
        self.check(owner, epoch, now)?;
        self.until_ms = now + LEASE_MS;
        Ok(())
    }
    pub fn stop(&mut self) {
        self.stopped = true;
        self.until_ms = 0;
    }
    pub fn expire(&mut self, now: u64) -> bool {
        if self.owner != 0 && !self.stopped && now >= self.until_ms {
            self.stop();
            true
        } else {
            false
        }
    }
}
#[derive(Debug, Clone, Copy)]
pub struct PcmHeader {
    pub epoch: u64,
    pub seq: u64,
    pub timestamp_ms: u64,
    pub samples: u32,
}
impl PcmHeader {
    pub fn encode(&self, pcm: &[u8]) -> Result<Vec<u8>> {
        if self.samples == 0 || self.samples > 4800 || pcm.len() != self.samples as usize * 2 {
            return Err(error("invalid mono S16 PCM block"));
        }
        let mut v = b"PCM1".to_vec();
        for x in [self.epoch, self.seq, self.timestamp_ms] {
            v.extend(x.to_be_bytes());
        }
        v.extend(48000u32.to_be_bytes());
        v.extend(self.samples.to_be_bytes());
        v.extend(pcm);
        Ok(v)
    }
    pub fn decode(data: &[u8]) -> Result<(Self, &[u8])> {
        if data.len() < 36
            || &data[..4] != b"PCM1"
            || u32::from_be_bytes(data[28..32].try_into()?) != 48000
        {
            return Err(error("invalid PCM header"));
        }
        let h = Self {
            epoch: u64::from_be_bytes(data[4..12].try_into()?),
            seq: u64::from_be_bytes(data[12..20].try_into()?),
            timestamp_ms: u64::from_be_bytes(data[20..28].try_into()?),
            samples: u32::from_be_bytes(data[32..36].try_into()?),
        };
        h.encode(&data[36..])?;
        Ok((h, &data[36..]))
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lease_stop_and_expiry_cannot_be_renewed_or_replayed() {
        let mut l = Lease::default();
        l.acquire(1, 1, 100).unwrap();
        assert!(l.acquire(2, 1, 101).is_err());
        l.stop();
        assert!(l.renew(1, 1, 102).is_err());
        assert!(l.acquire(1, 1, 102).is_err());
        l.acquire(1, 2, 103).unwrap();
        assert!(l.expire(853));
        assert!(l.renew(1, 2, 854).is_err());
        l.acquire(2, 1, 900).unwrap();
        assert!(l.check(1, 2, 901).is_err());
        l.stop();
        assert!(l.acquire(1, 3, 902).is_err());
    }
    #[tokio::test]
    async fn fragmented_frames_and_oversize() {
        let (mut a, mut b) = tokio::io::duplex(16);
        let task = tokio::spawn(async move {
            a.write_all(&[0, 0]).await.unwrap();
            a.write_all(&[0, 3, 1, 2, 3]).await.unwrap();
        });
        assert_eq!(read_frame(&mut b).await.unwrap(), vec![1, 2, 3]);
        task.await.unwrap();
        let mut bad: &[u8] = &[0, 1, 0, 1];
        assert!(read_frame(&mut bad).await.is_err());
    }
    #[test]
    fn pcm_is_bounded_and_versioned() {
        let h = PcmHeader {
            epoch: 3,
            seq: 1,
            timestamp_ms: 8,
            samples: 480,
        };
        let data = h.encode(&vec![0; 960]).unwrap();
        assert_eq!(PcmHeader::decode(&data).unwrap().0.epoch, 3);
        assert!(PcmHeader::decode(&data[..100]).is_err());
    }
    #[test]
    fn unknown_commands_and_future_deadlines_fail() {
        assert!(serde_json::from_str::<Command>(r#"{"cmd":"shell","text":"anything"}"#).is_err());
        let mut r = Request::new(Command::Status);
        r.deadline_ms = monotonic_ms() + 6000;
        assert!(r.validate().is_err());
        r.body = Command::Stop;
        r.deadline_ms = 0;
        assert!(r.validate().is_ok());
    }
}
