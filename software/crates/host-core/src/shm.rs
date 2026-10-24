//! Three bounded tmpfs slots. Kernel flock releases locks on process death.
//! Copies under shared/exclusive locks avoid unsynchronized mmap/seqlock races.
use crate::{error, monotonic_ms, Result};
use std::{
    fs::{File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    os::fd::AsRawFd,
    path::{Path, PathBuf},
};
pub const MAX_PIXELS: usize = 320 * 240 * 3 / 2;
#[derive(Debug)]
pub struct Frame {
    pub generation: u64,
    pub id: u64,
    pub timestamp: u64,
    pub width: u64,
    pub height: u64,
    pub pixels: Vec<u8>,
}
fn path(root: &Path, camera: u8, slot: u64) -> PathBuf {
    root.join(format!("cam{camera}.{slot}.frame"))
}
struct Lock(File);
impl Lock {
    fn new(file: File, write: bool) -> Result<Self> {
        let mode = if write { libc::LOCK_EX } else { libc::LOCK_SH };
        if unsafe { libc::flock(file.as_raw_fd(), mode | libc::LOCK_NB) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        Ok(Self(file))
    }
}
impl Drop for Lock {
    fn drop(&mut self) {
        unsafe {
            libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
        }
    }
}
pub fn publish(root: &Path, camera: u8, frame: &Frame) -> Result<bool> {
    if frame.pixels.len() != MAX_PIXELS || frame.width != 320 || frame.height != 240 {
        return Err(error("only bounded NV12 320x240 accepted"));
    }
    for offset in 0..3 {
        let f = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(path(root, camera, (frame.id + offset) % 3))?;
        let Ok(mut guard) = Lock::new(f, true) else {
            continue;
        };
        guard.0.seek(SeekFrom::Start(0))?;
        guard.0.write_all(b"FRM1")?;
        for n in [
            frame.generation,
            frame.id,
            frame.timestamp,
            frame.width,
            frame.height,
            frame.pixels.len() as u64,
        ] {
            guard.0.write_all(&n.to_be_bytes())?;
        }
        guard.0.write_all(&frame.pixels)?;
        guard.0.set_len(52 + MAX_PIXELS as u64)?;
        return Ok(true);
    }
    Ok(false)
}
pub fn latest(root: &Path, camera: u8, generation: u64) -> Result<Frame> {
    let mut best: Option<Frame> = None;
    for slot in 0..3 {
        let Ok(file) = File::open(path(root, camera, slot)) else {
            continue;
        };
        let Ok(mut guard) = Lock::new(file, false) else {
            continue;
        };
        let mut header = [0u8; 52];
        if guard.0.read_exact(&mut header).is_err() || &header[..4] != b"FRM1" {
            continue;
        }
        let nums: Vec<u64> = header[4..]
            .chunks_exact(8)
            .map(|x| u64::from_be_bytes(x.try_into().unwrap()))
            .collect();
        if nums[0] != generation
            || nums[3] != 320
            || nums[4] != 240
            || nums[5] as usize != MAX_PIXELS
        {
            continue;
        }
        let now = monotonic_ms();
        if nums[2] > now || now - nums[2] > 500 {
            continue;
        }
        let mut pixels = vec![0; MAX_PIXELS];
        if guard.0.read_exact(&mut pixels).is_err() {
            continue;
        }
        if best.as_ref().is_none_or(|b| nums[1] > b.id) {
            best = Some(Frame {
                generation: nums[0],
                id: nums[1],
                timestamp: nums[2],
                width: nums[3],
                height: nums[4],
                pixels,
            });
        }
    }
    best.ok_or_else(|| error("no fresh frame for current producer generation"))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn restart_and_old_frame_are_invalid() {
        let root = std::env::temp_dir().join(format!("slots-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let f = Frame {
            generation: 5,
            id: 1,
            timestamp: monotonic_ms(),
            width: 320,
            height: 240,
            pixels: vec![0; MAX_PIXELS],
        };
        publish(&root, 0, &f).unwrap();
        assert!(latest(&root, 0, 5).is_ok());
        assert!(latest(&root, 0, 6).is_err());
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn busy_slots_drop_without_truncation_and_stale_frames_fail() {
        let root = std::env::temp_dir().join(format!("slots-busy-{}", std::process::id()));
        std::fs::create_dir_all(&root).unwrap();
        let f = Frame {
            generation: 1,
            id: 3,
            timestamp: monotonic_ms().saturating_sub(1000),
            width: 320,
            height: 240,
            pixels: vec![9; MAX_PIXELS],
        };
        publish(&root, 0, &f).unwrap();
        assert!(latest(&root, 0, 1).is_err());
        let mut locks = Vec::new();
        for i in 0..3 {
            let file = OpenOptions::new()
                .create(true)
                .truncate(false)
                .read(true)
                .write(true)
                .open(path(&root, 0, i))
                .unwrap();
            locks.push(Lock::new(file, true).unwrap());
        }
        assert!(!publish(&root, 0, &f).unwrap());
        drop(locks);
        assert!(publish(&root, 0, &f).unwrap());
        std::fs::remove_dir_all(root).unwrap();
    }
}
