use serialport::{SerialPort, SerialPortType};
use std::error::Error;
use std::io::{self, Read, Write};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc,
};
use std::time::{Duration, Instant};

const IDENTITY: &str = "protocol=servo-bench-v1";
const HELP: &str = "pico-servo-bench list\n\
pico-servo-bench --port COM8 status|scan|stop\n\
pico-servo-bench --port COM8 config --min-us 1000 --max-us 2000\n\
pico-servo-bench --port COM8 sweep\n\
No command moves a servo except explicit sweep. Sweep arms, sends a one-pass\n\
1..6 sweep, keeps the firmware lease alive, then sends STOP. Ctrl-C sends STOP.\n\
0/180 are nominal setpoints; physical endpoints need servo calibration.";

#[derive(Debug, PartialEq)]
struct Args {
    command: String,
    port: Option<String>,
    min_us: Option<u16>,
    max_us: Option<u16>,
}

fn parse_args(values: impl IntoIterator<Item = String>) -> Result<Args, String> {
    let mut args = Args {
        command: String::new(),
        port: None,
        min_us: None,
        max_us: None,
    };
    let mut values = values.into_iter();
    while let Some(value) = values.next() {
        match value.as_str() {
            "-h" | "--help" => return Err(HELP.into()),
            "--port" => args.port = Some(values.next().ok_or("--port needs a value")?),
            "--min-us" => {
                args.min_us = Some(
                    values
                        .next()
                        .ok_or("--min-us needs a value")?
                        .parse()
                        .map_err(|_| "Invalid --min-us")?,
                )
            }
            "--max-us" => {
                args.max_us = Some(
                    values
                        .next()
                        .ok_or("--max-us needs a value")?
                        .parse()
                        .map_err(|_| "Invalid --max-us")?,
                )
            }
            "list" | "status" | "scan" | "stop" | "config" | "sweep" if args.command.is_empty() => {
                args.command = value
            }
            _ => return Err(format!("Unknown or duplicate argument: {value}")),
        }
    }
    if args.command.is_empty() {
        return Err(HELP.into());
    }
    if args.command != "list" && args.port.is_none() {
        return Err("An explicit --port is required; use list first".into());
    }
    if args.command == "config" {
        let (min, max) = args
            .min_us
            .zip(args.max_us)
            .ok_or("config requires --min-us and --max-us")?;
        if !(500..=2500).contains(&min) || !(500..=2500).contains(&max) || min >= max {
            return Err(
                "Require 500 <= min_us < max_us <= 2500; verify servo specifications first".into(),
            );
        }
    } else if args.min_us.is_some() || args.max_us.is_some() {
        return Err("Pulse settings are accepted only by config".into());
    }
    Ok(args)
}

struct Link {
    port: Box<dyn SerialPort>,
    partial: Vec<u8>,
}
impl Link {
    fn send(&mut self, command: &str) -> Result<(), Box<dyn Error>> {
        self.port.write_all(command.as_bytes())?;
        self.port.write_all(b"\n")?;
        self.port.flush()?;
        Ok(())
    }

    fn line(&mut self, deadline: Instant) -> Result<Option<String>, Box<dyn Error>> {
        let mut byte = [0_u8; 1];
        while Instant::now() < deadline {
            match self.port.read(&mut byte) {
                Ok(0) => (),
                Ok(_) if byte[0] == b'\n' => {
                    let bytes = std::mem::take(&mut self.partial);
                    let line = String::from_utf8(bytes)?.trim_end_matches('\r').to_owned();
                    if !line.is_empty() {
                        return Ok(Some(line));
                    }
                }
                Ok(_) => {
                    if self.partial.len() >= 1024 {
                        return Err("Overlong device line".into());
                    }
                    self.partial.push(byte[0]);
                }
                Err(e)
                    if matches!(
                        e.kind(),
                        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
                    ) =>
                {
                    ()
                }
                Err(e) => return Err(e.into()),
            }
        }
        Ok(None)
    }

    fn wait_for(&mut self, prefix: &str, duration: Duration) -> Result<String, Box<dyn Error>> {
        let deadline = Instant::now() + duration;
        while let Some(line) = self.line(deadline)? {
            if line != "OK PING" {
                println!("{line}");
            }
            if line.starts_with("ERR ") {
                return Err(line.into());
            }
            if line.starts_with(prefix) {
                return Ok(line);
            }
        }
        Err(format!("Timed out waiting for {prefix}").into())
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), Box<dyn Error>> {
    let args = parse_args(std::env::args().skip(1))?;
    let ports = serialport::available_ports()?;
    if args.command == "list" {
        for port in ports {
            match port.port_type {
                SerialPortType::UsbPort(usb) => println!(
                    "{} USB {:04x}:{:04x} serial={} product={}",
                    port.port_name,
                    usb.vid,
                    usb.pid,
                    usb.serial_number.unwrap_or_default(),
                    usb.product.unwrap_or_default()
                ),
                other => println!("{} {other:?}", port.port_name),
            }
        }
        return Ok(());
    }
    let name = args.port.as_deref().unwrap();
    if !ports
        .iter()
        .any(|port| port.port_name.eq_ignore_ascii_case(name))
    {
        return Err(format!(
            "Port {name} was not enumerated; run list and choose the Pico port explicitly"
        )
        .into());
    }
    let interrupted = Arc::new(AtomicBool::new(false));
    let flag = interrupted.clone();
    ctrlc::set_handler(move || flag.store(true, Ordering::SeqCst))?;
    let mut link = Link {
        port: serialport::new(name, 115_200)
            .timeout(Duration::from_millis(40))
            .open()?,
        partial: Vec::new(),
    };
    link.port.write_data_terminal_ready(true)?;
    // A non-moving identity request is the only command sent before verification.
    link.send("status")?;
    let status = link.wait_for("STATUS ", Duration::from_secs(4))?;
    if !status.split_whitespace().any(|field| field == IDENTITY) {
        return Err("Unexpected firmware identity; refusing further commands".into());
    }
    match args.command.as_str() {
        "status" => (),
        "stop" => {
            link.send("stop")?;
            link.wait_for("OK STOP", Duration::from_secs(2))?;
        }
        "scan" => {
            link.send("scan")?;
            link.wait_for("SCAN DONE ", Duration::from_secs(8))?;
        }
        "config" => {
            link.send(&format!(
                "config {} {}",
                args.min_us.unwrap(),
                args.max_us.unwrap()
            ))?;
            link.wait_for("OK CONFIG ", Duration::from_secs(2))?;
        }
        "sweep" => {
            let outcome = (|| -> Result<(), Box<dyn Error>> {
                if interrupted.load(Ordering::SeqCst) {
                    return Err("Interrupted before ARM".into());
                }
                link.send("arm")?;
                link.wait_for("OK ARM", Duration::from_secs(2))?;
                if interrupted.load(Ordering::SeqCst) {
                    return Err("Interrupted before SWEEP".into());
                }
                link.send("sweep")?;
                let deadline = Instant::now() + Duration::from_secs(120);
                let mut next_ping = Instant::now();
                let mut sweep_accepted = false;
                while Instant::now() < deadline {
                    if interrupted.load(Ordering::SeqCst) {
                        return Err("Interrupted; requesting STOP".into());
                    }
                    if Instant::now() >= next_ping {
                        link.send("ping")?;
                        next_ping = Instant::now() + Duration::from_millis(200);
                    }
                    if let Some(line) = link.line(std::cmp::min(next_ping, deadline))? {
                        if line != "OK PING" {
                            println!("{line}");
                        }
                        if line == "OK SWEEP" {
                            sweep_accepted = true;
                        }
                        if line.starts_with("ERR ") || line.starts_with("EVENT STOP ") {
                            return Err(line.into());
                        }
                        if line == "EVENT DONE" && sweep_accepted {
                            return Ok(());
                        }
                    }
                }
                Err("Sweep timed out".into())
            })();
            // Always attempt an explicit stop; a broken link also expires the firmware lease.
            let stopped = link
                .send("stop")
                .and_then(|_| link.wait_for("OK STOP", Duration::from_secs(2)).map(|_| ()));
            outcome?;
            stopped?;
        }
        _ => unreachable!(),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn args(values: &[&str]) -> Result<Args, String> {
        parse_args(values.iter().map(|value| (*value).to_owned()))
    }
    #[test]
    fn explicit_port_required_for_commands() {
        assert!(args(&["sweep"]).is_err());
        assert!(args(&["list"]).is_ok());
        assert_eq!(args(&["--port", "COM8", "sweep"]).unwrap().command, "sweep");
    }
    #[test]
    fn rejects_invalid_or_partial_calibration() {
        for values in [
            vec!["config", "--port", "COM8"],
            vec![
                "config", "--port", "COM8", "--min-us", "400", "--max-us", "2500",
            ],
            vec![
                "config", "--port", "COM8", "--min-us", "2000", "--max-us", "1000",
            ],
        ] {
            assert!(args(&values).is_err());
        }
        assert!(
            args(&["config", "--port", "COM8", "--min-us", "1000", "--max-us", "2000"]).is_ok()
        );
        assert!(args(&["sweep", "--port", "COM8", "--min-us", "1000"]).is_err());
    }
}
