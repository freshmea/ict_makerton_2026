use host_core::{error, Result};
use std::{
    ffi::{c_char, c_int, c_void, CString},
    ptr::NonNull,
};
unsafe extern "C" {
    #[cfg(has_detector)]
    fn nano_detector_open() -> *mut c_void;
    #[cfg(has_detector)]
    fn nano_detector_infer(
        p: *mut c_void,
        data: *const u8,
        width: c_int,
        height: c_int,
        out: *mut c_char,
        cap: c_int,
    ) -> c_int;
    #[cfg(has_detector)]
    fn nano_detector_close(p: *mut c_void);
    fn nano_media_open(p: *const c_char) -> *mut c_void;
    fn nano_media_read(p: *mut c_void, dest: *mut u8, max: c_int) -> c_int;
    fn nano_media_source_frames(p: *mut c_void) -> u32;
    fn nano_media_push(p: *mut c_void, data: *const u8, len: c_int) -> c_int;
    fn nano_media_reset(p: *mut c_void) -> c_int;
    fn nano_media_snapshot(p: *mut c_void, dest: *mut u8, max: c_int) -> c_int;
    fn nano_media_close(p: *mut c_void);
    fn nano_goal(
        path: *const c_char,
        op: c_int,
        text: *const c_char,
        out: *mut c_char,
        cap: c_int,
    ) -> c_int;
    #[cfg(has_cuda)]
    fn nano_cuda_stats(
        cur: *const u8,
        prev: *const u8,
        len: c_int,
        mean: *mut f64,
        motion: *mut f64,
    ) -> c_int;
}
pub struct Detector(NonNull<c_void>);
impl Detector {
    pub fn open() -> Result<Self> {
        #[cfg(has_detector)]
        {
            return NonNull::new(unsafe { nano_detector_open() })
                .map(Self)
                .ok_or_else(|| error("detector model failed to load"));
        }
        #[cfg(not(has_detector))]
        {
            Err(error("TensorRT/OpenCV detector not compiled"))
        }
    }
    pub fn infer(&mut self, nv12: &[u8]) -> Result<serde_json::Value> {
        if nv12.len() != 320 * 240 * 3 / 2 {
            return Err(error("detector expects NV12 320x240"));
        }
        #[cfg(has_detector)]
        {
            let mut out = vec![0 as c_char; 16384];
            if unsafe {
                nano_detector_infer(
                    self.0.as_ptr(),
                    nv12.as_ptr(),
                    320,
                    240,
                    out.as_mut_ptr(),
                    out.len() as c_int,
                )
            } != 0
            {
                return Err(error("semantic inference failed"));
            }
            return Ok(serde_json::from_str(
                unsafe { std::ffi::CStr::from_ptr(out.as_ptr()) }.to_str()?,
            )?);
        }
        #[cfg(not(has_detector))]
        {
            Err(error("detector unavailable"))
        }
    }
}
impl Drop for Detector {
    fn drop(&mut self) {
        #[cfg(has_detector)]
        unsafe {
            nano_detector_close(self.0.as_ptr());
        }
    }
}
// Each Media is owned and accessed by one dedicated media thread only.
pub struct Media(NonNull<c_void>);
impl Media {
    pub fn source_frames(&self) -> u32 {
        unsafe { nano_media_source_frames(self.0.as_ptr()) }
    }
    pub fn snapshot(&mut self) -> Result<Vec<u8>> {
        let mut b = vec![0; 1024 * 1024];
        let n = unsafe { nano_media_snapshot(self.0.as_ptr(), b.as_mut_ptr(), b.len() as c_int) };
        if n <= 0 {
            return Err(error("camera snapshot failed"));
        }
        b.truncate(n as usize);
        Ok(b)
    }
    pub fn open(pipeline: &str) -> Result<Self> {
        NonNull::new(unsafe { nano_media_open(CString::new(pipeline)?.as_ptr()) })
            .map(Self)
            .ok_or_else(|| error("GStreamer pipeline failed"))
    }
    pub fn read(&mut self, bytes: &mut [u8]) -> Result<usize> {
        let n =
            unsafe { nano_media_read(self.0.as_ptr(), bytes.as_mut_ptr(), bytes.len() as c_int) };
        if n < 0 {
            Err(error("GStreamer EOS/error/oversize"))
        } else {
            Ok(n as usize)
        }
    }
    pub fn push(&mut self, bytes: &[u8]) -> Result<bool> {
        match unsafe { nano_media_push(self.0.as_ptr(), bytes.as_ptr(), bytes.len() as c_int) } {
            0 => Ok(true),
            2 => Ok(false),
            _ => Err(error("PCM push failed")),
        }
    }
    pub fn reset(&mut self) -> Result<()> {
        if unsafe { nano_media_reset(self.0.as_ptr()) } != 0 {
            Err(error("device flush failed"))
        } else {
            Ok(())
        }
    }
}
impl Drop for Media {
    fn drop(&mut self) {
        unsafe { nano_media_close(self.0.as_ptr()) }
    }
}
pub fn goal(path: &str, op: i32, text: &str) -> Result<String> {
    let mut buf = vec![0 as c_char; 4096];
    let p = CString::new(path)?;
    let t = CString::new(text)?;
    if unsafe {
        nano_goal(
            p.as_ptr(),
            op,
            t.as_ptr(),
            buf.as_mut_ptr(),
            buf.len() as c_int,
        )
    } != 0
    {
        return Err(error("SQLite operation failed"));
    }
    Ok(unsafe { std::ffi::CStr::from_ptr(buf.as_ptr()) }
        .to_str()?
        .to_owned())
}
pub fn stats(cur: &[u8], prev: &[u8], cuda: bool) -> Result<(f64, f64, &'static str)> {
    if cur.is_empty() || cur.len() != prev.len() || cur.len() > 320 * 240 {
        return Err(error("invalid luma planes"));
    }
    if cuda {
        #[cfg(has_cuda)]
        {
            let (mut mean, mut motion) = (0.0, 0.0);
            if unsafe {
                nano_cuda_stats(
                    cur.as_ptr(),
                    prev.as_ptr(),
                    cur.len() as c_int,
                    &mut mean,
                    &mut motion,
                )
            } == 0
            {
                return Ok((mean, motion, "cuda-sm53"));
            }
            return Err(error("CUDA kernel failed"));
        }
        #[cfg(not(has_cuda))]
        return Err(error("CUDA backend not built"));
    }
    let mean = cur.iter().map(|x| *x as f64).sum::<f64>() / cur.len() as f64;
    let motion = cur
        .iter()
        .zip(prev)
        .map(|(a, b)| (*a as f64 - *b as f64).abs())
        .sum::<f64>()
        / cur.len() as f64;
    Ok((mean, motion, "cpu"))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sqlite_is_parameter_bound_and_recoverable() {
        let p = std::env::temp_dir().join(format!("goal-test-{}.sqlite3", std::process::id()));
        let name = p.to_str().unwrap();
        goal(name, 1, "reading'; DROP TABLE goal; --").unwrap();
        assert_eq!(goal(name, 0, "").unwrap(), "reading'; DROP TABLE goal; --");
        goal(name, 2, "").unwrap();
        assert_eq!(goal(name, 0, "").unwrap(), "");
        std::fs::remove_file(p).unwrap();
    }
    #[test]
    fn luma_cpu_contract_is_exact() {
        assert_eq!(
            stats(&[0, 100, 200], &[10, 90, 180], false).unwrap(),
            (100.0, 40.0 / 3.0, "cpu")
        );
        assert!(stats(&[], &[], false).is_err());
    }
}
