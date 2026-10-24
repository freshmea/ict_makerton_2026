//! Typecast credentials remain in dialogued. Only the final permitted hint is sent.
use super::*;
use std::io::{Read, Seek, SeekFrom, Write};
use std::os::unix::fs::OpenOptionsExt;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
static LEDGER: std::sync::Mutex<()> = std::sync::Mutex::new(());
fn seconds() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
fn local(reserve: Option<usize>, http: Option<u16>) -> Result<Value> {
    if env("NANO_AI_TEST", "0") == "1" {
        return Ok(json!({"fixture":true}));
    }
    let _g = LEDGER.lock().map_err(|_| error("TTS ledger poisoned"))?;
    let mut f = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(env(
            "NANO_TTS_USAGE_FILE",
            "/var/lib/300seconds-runtime/tts-usage.json",
        ))?;
    if unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX) } != 0 {
        return Err(error("TTS usage lock failed"));
    }
    let mut raw = String::new();
    Read::by_ref(&mut f).take(65537).read_to_string(&mut raw)?;
    if raw.len() > 65536 {
        return Err(error("TTS usage size invalid"));
    }
    let mut v: Value = if raw.is_empty() {
        json!({"attempts":[],"cooldown_until":0})
    } else {
        serde_json::from_str(&raw).map_err(|_| error("TTS ledger corrupt; blocked"))?
    };
    let t = seconds();
    let a = v["attempts"]
        .as_array_mut()
        .ok_or_else(|| error("TTS ledger shape invalid"))?;
    a.retain(|x| x[0].as_u64().unwrap_or(u64::MAX).saturating_add(30 * 86400) > t);
    let day = a
        .iter()
        .filter(|x| x[0].as_u64().unwrap_or(u64::MAX).saturating_add(86400) > t)
        .map(|x| x[1].as_u64().unwrap_or(100000))
        .sum::<u64>();
    let month = a
        .iter()
        .map(|x| x[1].as_u64().unwrap_or(100000))
        .sum::<u64>();
    let minute = a
        .iter()
        .filter(|x| x[0].as_u64().unwrap_or(u64::MAX).saturating_add(60) > t)
        .count();
    let max_day = env("NANO_TTS_MAX_24H_CHARS", "500")
        .parse::<u64>()
        .unwrap_or(500)
        .min(15000);
    let max_month = env("NANO_TTS_MAX_30D_CHARS", "12000")
        .parse::<u64>()
        .unwrap_or(12000)
        .min(15000);
    if let Some(n) = reserve {
        if day + n as u64 > max_day
            || month + n as u64 > max_month
            || minute >= 2
            || v["cooldown_until"].as_u64().unwrap_or(u64::MAX) > t
        {
            return Err(error(
                "local_TTS_budget_or_cooldown; no synthesis request made",
            ));
        }
        v["attempts"].as_array_mut().unwrap().push(json!([t, n]));
    }
    if let Some(code) = http {
        v["last_http_status"] = json!(code);
        if [401, 402, 403, 429].contains(&code) {
            v["cooldown_until"] = json!(t + 3600);
        } else if code == 0 || code >= 500 {
            v["cooldown_until"] = json!(t + 60);
        }
    }
    let data = serde_json::to_vec(&v)?;
    f.seek(SeekFrom::Start(0))?;
    f.set_len(0)?;
    f.write_all(&data)?;
    f.sync_data()?;
    Ok(
        json!({"local_only":true,"rolling_24h_characters":day+reserve.unwrap_or(0) as u64,"rolling_30d_characters":month+reserve.unwrap_or(0) as u64,"max_24h_characters":max_day,"max_30d_characters":max_month,"max_rpm":2,"cooldown_until_unix":v["cooldown_until"],"last_http_status":v["last_http_status"],"automatic_retry":false}),
    )
}
fn quote(s: &str) -> String {
    format!(
        "\"{}\"",
        s.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('\n', "\\n")
            .replace('\r', "\\r")
            .replace('\t', "\\t")
    )
}
async fn request(path: &str, body: Option<&Value>, limit: usize) -> Result<Vec<u8>> {
    let fixture = env("NANO_AI_TEST", "0") == "1";
    let (url, key) = if fixture {
        let base = env("NANO_AI_TEST_URL", "");
        if !base.starts_with("http://127.0.0.1:") || base.contains(['@', '#', '?', '\n', '\r']) {
            return Err(error("invalid TTS fixture endpoint"));
        }
        (format!("{base}{path}"), "fixture-only".into())
    } else {
        let key = env("TYPECAST_API_KEY", "");
        if key.is_empty() || key.contains(['\r', '\n']) {
            return Err(error("credential_missing_or_invalid:TYPECAST_API_KEY"));
        }
        (format!("https://api.typecast.ai{path}"), key)
    };
    let mut config = format!(
        "url = {}\nheader = {}\n",
        quote(&url),
        quote(&format!("X-API-KEY: {key}"))
    );
    if let Some(body) = body {
        config += &format!(
            "request = \"POST\"\nheader = \"Content-Type: application/json\"\ndata-binary = {}\n",
            quote(&body.to_string())
        );
    }
    let mut child = tokio::process::Command::new("curl")
        .args([
            "--silent",
            "--connect-timeout",
            "5",
            "--max-time",
            "18",
            "--max-filesize",
            &limit.to_string(),
            "--proto",
            "=https,http",
            "--write-out",
            "\n%{http_code}",
            "--config",
            "-",
        ])
        .env_remove("TYPECAST_API_KEY")
        .env_remove("GEMINI_API_KEY")
        .env_remove("OPENAI_API_KEY")
        .env_remove("TYPESAFE_API_KEY")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .kill_on_drop(true)
        .spawn()?;
    let mut stdin = child.stdin.take().unwrap();
    stdin.write_all(config.as_bytes()).await?;
    drop(stdin);
    let mut out = Vec::new();
    child
        .stdout
        .take()
        .unwrap()
        .take((limit + 1) as u64)
        .read_to_end(&mut out)
        .await?;
    if out.len() > limit {
        let _ = child.kill().await;
        return Err(error("Typecast response too large"));
    }
    let status = child.wait().await?;
    let split = out
        .iter()
        .rposition(|&x| x == b'\n')
        .ok_or_else(|| error("Typecast HTTP status missing"))?;
    let code = std::str::from_utf8(&out[split + 1..])
        .unwrap_or("0")
        .parse::<u16>()
        .unwrap_or(0);
    local(None, Some(code))?;
    if code != 200 || !status.success() {
        return Err(error(format!("Typecast HTTP {code}; no automatic retry")));
    }
    out.truncate(split);
    Ok(out)
}
pub async fn account() -> Result<Value> {
    let data = request("/v1/users/me/subscription", None, 65536).await?;
    let v: Value = serde_json::from_slice(&data)?;
    let plan = v["plan"]
        .as_str()
        .ok_or_else(|| error("Typecast subscription plan missing"))?;
    let total = v["credits"]["plan_credits"]
        .as_u64()
        .ok_or_else(|| error("Typecast credit limit missing"))?;
    let used = v["credits"]["used_credits"]
        .as_u64()
        .ok_or_else(|| error("Typecast used credits missing"))?;
    Ok(
        json!({"provider":"typecast","plan":plan,"plan_credits":total,"used_credits":used,"remaining_plan_credits":total.saturating_sub(used),"checked_unix":seconds(),"source":"GET /v1/users/me/subscription"}),
    )
}
pub async fn usage() -> Result<Value> {
    Ok(json!({"account":account().await?,"local":local(None,None)?}))
}
pub async fn synthesize(text: &str) -> Result<(Vec<u8>, Value)> {
    let count = text.encode_utf16().count();
    if text.trim().is_empty() || count > 240 {
        return Err(error("Typecast text limit"));
    }
    if env("NANO_AI_TEST", "0") != "1" && env("NANO_ALLOW_CLOUD", "0") != "1" {
        return Err(error("Typecast cloud disabled"));
    }
    let voice = env("NANO_TYPECAST_VOICE_ID", "");
    if !voice.starts_with("tc_")
        || voice.len() > 64
        || !voice
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_')
    {
        return Err(error("Typecast built-in voice ID required"));
    }
    let model = env("NANO_TYPECAST_MODEL", "ssfm-v30");
    if !["ssfm-v30", "ssfm-v21"].contains(&model.as_str()) {
        return Err(error("Typecast model unsupported"));
    }
    let account = account().await?;
    if account["plan"] != "free" && env("NANO_TYPECAST_ALLOW_PAID", "0") != "1" {
        return Err(error("Typecast paid plan not enabled"));
    }
    if account["remaining_plan_credits"].as_u64().unwrap_or(0) < count as u64 {
        return Err(error(
            "Typecast included credits exhausted; synthesis blocked",
        ));
    }
    local(Some(count), None)?;
    let start = monotonic_ms();
    let prompt = if model == "ssfm-v30" {
        json!({"emotion_type":"preset","emotion_preset":"normal","emotion_intensity":0.5})
    } else {
        json!({"emotion_preset":"normal","emotion_intensity":0.5})
    };
    let body = json!({"voice_id":voice,"text":text,"model":model,"language":"kor","prompt":prompt,"output":{"audio_format":"wav","audio_tempo":1.0,"target_lufs":-23}});
    let wav = request("/v1/text-to-speech", Some(&body), 2_700_000).await?;
    if wav.len() < 44 || &wav[..4] != b"RIFF" || &wav[8..12] != b"WAVE" {
        return Err(error("Typecast response is not WAV"));
    }
    Ok((
        wav,
        json!({"provider":"typecast","model":model,"voice_id":voice,"requested_characters":count,"wall_ms":monotonic_ms()-start,"account_before":account,"microphone_uploaded":false,"disclosure":"Typecast AI 합성 음성"}),
    ))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn character_budget_persists_and_blocks_excess_and_429() {
        let p = std::env::temp_dir().join(format!("tts-budget-{}.json", std::process::id()));
        std::env::set_var("NANO_TTS_USAGE_FILE", &p);
        std::env::set_var("NANO_TTS_MAX_24H_CHARS", "6");
        local(Some(4), None).unwrap();
        assert!(local(Some(3), None).is_err());
        local(Some(2), None).unwrap();
        assert_eq!(local(None, None).unwrap()["rolling_24h_characters"], 6);
        local(None, Some(429)).unwrap();
        assert!(local(Some(1), None).is_err());
        assert!(
            local(None, None).unwrap()["cooldown_until_unix"]
                .as_u64()
                .unwrap()
                > seconds()
        );
        std::fs::remove_file(p).unwrap();
        std::env::remove_var("NANO_TTS_USAGE_FILE");
        std::env::remove_var("NANO_TTS_MAX_24H_CHARS");
    }
}
