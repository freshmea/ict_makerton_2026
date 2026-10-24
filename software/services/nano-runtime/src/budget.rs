//! Local hard attempt budget, not an account-wide quota/billing meter.
use super::*;
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::OpenOptionsExt;
static SERIAL: std::sync::Mutex<()> = std::sync::Mutex::new(());
fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn change(reserve: bool, status: Option<u16>, usage: Option<Value>) -> Result<Value> {
    let _g = SERIAL.lock().map_err(|_| error("budget lock poisoned"))?;
    let mut file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(env(
            "NANO_USAGE_FILE",
            "/var/lib/300seconds-runtime/ai-usage.json",
        ))?;
    if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } != 0 {
        return Err(error("usage file lock failed"));
    }
    let mut raw = String::new();
    Read::by_ref(&mut file)
        .take(65537)
        .read_to_string(&mut raw)?;
    if raw.len() > 65536 {
        return Err(error("usage ledger size invalid"));
    }
    let mut v: Value = if raw.is_empty() {
        json!({"attempts":[],"cooldown_until":0,"last_usage":null,"last_http_status":null})
    } else {
        serde_json::from_str(&raw).map_err(|_| error("usage ledger corrupt; requests blocked"))?
    };
    let t = now();
    let attempts = v["attempts"]
        .as_array_mut()
        .ok_or_else(|| error("invalid budget ledger"))?;
    // Retain a rolling 24h window. Clock rollback cannot replenish the budget.
    attempts.retain(|x| x.as_u64().unwrap_or(u64::MAX).saturating_add(86400) > t);
    let daily = env("NANO_AI_MAX_24H", "10")
        .parse::<usize>()
        .unwrap_or(10)
        .min(1000);
    let rpm = env("NANO_AI_MAX_RPM", "1")
        .parse::<usize>()
        .unwrap_or(1)
        .min(30);
    let minute = attempts
        .iter()
        .filter(|x| x.as_u64().unwrap_or(u64::MAX).saturating_add(60) > t)
        .count();
    if reserve {
        if attempts.len() >= daily || minute >= rpm {
            return Err(error("local_AI_budget_exhausted; no network request made"));
        }
        if v["cooldown_until"].as_u64().unwrap_or(u64::MAX) > t {
            return Err(error("provider_cooldown; no network request made"));
        }
        v["attempts"].as_array_mut().unwrap().push(json!(t));
    }
    if let Some(s) = status {
        v["last_http_status"] = json!(s);
        if s == 429 {
            v["cooldown_until"] = json!(t + 3600);
        } else if s >= 500 || s == 0 {
            v["cooldown_until"] = json!(t + 60);
        }
    }
    if let Some(u) = usage {
        v["last_usage"] = u;
    }
    let bytes = serde_json::to_vec(&v)?;
    file.seek(SeekFrom::Start(0))?;
    file.set_len(0)?;
    file.write_all(&bytes)?;
    file.sync_data()?;
    Ok(
        json!({"local_only":true,"account_remaining":"unknown; consult provider dashboard","rolling_24h_attempts":v["attempts"].as_array().unwrap().len(),"max_24h":daily,"max_rpm":rpm,"cooldown_until_unix":v["cooldown_until"],"last_http_status":v["last_http_status"],"last_usage":v["last_usage"],"automatic_retry":false}),
    )
}
pub fn reserve() -> Result<()> {
    if env("NANO_AI_TEST", "") != "1" {
        change(true, None, None)?;
    }
    Ok(())
}
pub fn record(status: u16, usage: Option<Value>) {
    if env("NANO_AI_TEST", "") != "1" {
        if let Err(e) = change(false, Some(status), usage) {
            eprintln!("AI usage ledger: {e}");
        }
    }
}
pub fn status() -> Result<Value> {
    change(false, None, None)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn local_attempts_persist_and_429_blocks_further_calls() {
        let p = std::env::temp_dir().join(format!("budget-{}.json", std::process::id()));
        std::env::set_var("NANO_USAGE_FILE", &p);
        std::env::set_var("NANO_AI_MAX_RPM", "2");
        std::env::set_var("NANO_AI_MAX_24H", "3");
        reserve().unwrap();
        reserve().unwrap();
        assert!(reserve().is_err());
        assert_eq!(status().unwrap()["rolling_24h_attempts"], 2);
        record(429, None);
        assert!(status().unwrap()["cooldown_until_unix"].as_u64().unwrap() > now());
        std::fs::remove_file(p).unwrap();
        for k in ["NANO_USAGE_FILE", "NANO_AI_MAX_RPM", "NANO_AI_MAX_24H"] {
            std::env::remove_var(k);
        }
    }
}
