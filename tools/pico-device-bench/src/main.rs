use pico_device_bench::{
    config_from_json, failure, loopback_address, new_session, output, parse_ipc, udp_roundtrip,
    DeviceLink, DeviceRejection, Input, IpcRequest, RequestPreempted, Result, TestModule,
    IPC_DEFAULT, PROTOCOL_NAME, REQUEST_TIMEOUT, TEST_TIMEOUT,
};
use pico_device_protocol::{DeviceConfig, DeviceStatus, Message, USB_PID, USB_VID, VERSION};
use serde_json::{json, Value};
use serialport::SerialPortType;
use std::path::{Path, PathBuf};
use std::sync::{atomic::{AtomicBool, Ordering}, Arc};
use tokio::io::{AsyncRead, AsyncWrite};
use tokio::net::UdpSocket;
use tokio::time::Instant;
use tokio_serial::{SerialPort, SerialPortBuilderExt};

const HELP: &str = "pico-device-bench list\n\
pico-device-bench --port COM11 status|stop|bootloader\n\
pico-device-bench --port COM11 configure --config config.json\n\
pico-device-bench --port COM11 test matrix|left|right|servos|all [--config config.json]\n\
pico-device-bench --port /dev/serial/by-id/... bridge --config config.json --listen 127.0.0.1:37920\n\
pico-device-bench ctl --addr 127.0.0.1:37920 status|stop\n\
pico-device-bench ctl --addr 127.0.0.1:37920 test matrix|left|right|servos|all\n\
pico-device-bench ctl --addr 127.0.0.1:37920 configure --config config.json\n\
One bridge owns USB. Other Nano processes use ctl/loopback UDP, never a second\n\
serial opener. Device CDC carries only COBS/Postcard/CRC binary frames.\n\
bridge stdout is NDJSON. Standalone status/bootloader also emit uploader\n\
compatibility lines. Each serial connection starts a new Hello session;\n\
Hello stops any previous/local test. No test is replayed after a disconnect.";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Command { List, Status, Configure, Test(TestModule), Stop, Bootloader, Bridge }

#[derive(Debug, PartialEq, Eq)]
struct Args {
    command: Command,
    port: Option<String>,
    config: Option<PathBuf>,
    listen: Option<String>,
    addr: Option<String>,
    ctl: bool,
}

fn parse_args(values: impl IntoIterator<Item = String>) -> Result<Args> {
    let mut values = values.into_iter();
    let mut words = Vec::new();
    let mut port = None;
    let mut config = None;
    let mut listen = None;
    let mut addr = None;
    while let Some(value) = values.next() {
        match value.as_str() {
            "--port" | "--config" | "--listen" | "--addr" => {
                let destination = match value.as_str() {
                    "--port" => &mut port, "--config" => &mut config,
                    "--listen" => &mut listen, _ => &mut addr,
                };
                if destination.is_some() { return Err(failure(format!("Duplicate {value}"))); }
                let option = values.next().ok_or_else(|| failure(format!("{value} needs a value")))?;
                if option.is_empty() || option.starts_with('-') { return Err(failure(format!("{value} needs a value"))); }
                *destination = Some(option);
            }
            "--help" | "-h" => return Err(failure(HELP)),
            option if option.starts_with('-') => return Err(failure(format!("Unknown argument: {option}"))),
            _ => words.push(value),
        }
    }
    let ctl = words.first().is_some_and(|word| word == "ctl");
    if ctl { words.remove(0); }
    let command = match words.as_slice() {
        [value] => match value.as_str() {
            "list" => Command::List, "status" => Command::Status, "configure" => Command::Configure,
            "stop" => Command::Stop, "bootloader" => Command::Bootloader, "bridge" => Command::Bridge,
            _ => return Err(failure(HELP)),
        },
        [value, module] if value == "test" => Command::Test(TestModule::parse(module)
            .ok_or_else(|| failure("test requires matrix, left, right, servos, or all"))?),
        _ => return Err(failure(HELP)),
    };
    if ctl {
        if !matches!(command, Command::Status | Command::Configure | Command::Stop | Command::Test(_))
            || port.is_some() || listen.is_some() {
            return Err(failure("ctl accepts only status, configure, test or stop; it never opens USB"));
        }
    } else {
        if addr.is_some() { return Err(failure("--addr is supported only by ctl")); }
        if command == Command::List {
            if port.is_some() || config.is_some() || listen.is_some() { return Err(failure("list only enumerates ports; omit configuration and port options")); }
        } else if port.is_none() { return Err(failure("An explicit --port is required; use list first")); }
    }
    if command == Command::Configure && config.is_none() { return Err(failure("configure requires --config PATH")); }
    if config.is_some() && !matches!(command, Command::Configure | Command::Test(_) | Command::Bridge) {
        return Err(failure("--config is supported by configure, direct test, or bridge"));
    }
    if listen.is_some() && command != Command::Bridge { return Err(failure("--listen is supported only by bridge")); }
    if ctl && matches!(command, Command::Test(_)) && config.is_some() {
        return Err(failure("Use ctl configure first, then ctl test without --config"));
    }
    Ok(Args { command, port, config: config.map(PathBuf::from), listen, addr, ctl })
}

fn load_config(path: Option<&Path>) -> Result<DeviceConfig> {
    match path { Some(path) => config_from_json(&std::fs::read(path)?), None => Ok(DeviceConfig::default()) }
}

fn port_names_match(requested: &str, listed: &str, requested_path: Option<&Path>, listed_path: Option<&Path>) -> bool {
    let com_name = |name: &str| {
        let bytes = name.as_bytes();
        bytes.len() > 3 && bytes[..3].eq_ignore_ascii_case(b"COM") && bytes[3..].iter().all(u8::is_ascii_digit)
    };
    if requested == listed || (com_name(requested) && com_name(listed) && requested.eq_ignore_ascii_case(listed)) { return true; }
    requested_path.zip(listed_path).is_some_and(|(left, right)| left == right)
}

fn parse_usb_ids(vendor: &str, product: &str) -> Result<()> {
    let vid = u16::from_str_radix(vendor.trim(), 16)?;
    let pid = u16::from_str_radix(product.trim(), 16)?;
    if (vid, pid) != (USB_VID, USB_PID) { return Err(failure(format!("Unexpected USB {:04x}:{:04x}; require c0de:cafc", vid, pid))); }
    Ok(())
}

#[cfg(target_os = "linux")]
fn verify_linux_sysfs(canonical: &Path) -> Result<()> {
    let tty = canonical.file_name().and_then(|name| name.to_str())
        .ok_or_else(|| failure("The selected Linux serial symlink has no canonical tty name"))?;
    let root = PathBuf::from("/sys/class/tty").join(tty).join("device");
    let device = std::fs::canonicalize(&root).map_err(|error| failure(format!("Cannot resolve {} to validate USB IDs: {error}", root.display())))?;
    for ancestor in device.ancestors() {
        let vendor = ancestor.join("idVendor");
        let product = ancestor.join("idProduct");
        if vendor.is_file() && product.is_file() {
            return parse_usb_ids(&std::fs::read_to_string(vendor)?, &std::fs::read_to_string(product)?);
        }
    }
    Err(failure(format!("No USB vendor/product parent was found for {}. Refusing an unverified port; inspect its /dev/serial/by-id link and sysfs permissions", canonical.display())))
}

fn verify_serial_port(requested: &str) -> Result<()> {
    let canonical = std::fs::canonicalize(requested).ok();
    let ports = serialport::available_ports()?;
    for port in ports {
        let listed_canonical = std::fs::canonicalize(&port.port_name).ok();
        if port_names_match(requested, &port.port_name, canonical.as_deref(), listed_canonical.as_deref()) {
            if let SerialPortType::UsbPort(usb) = port.port_type {
                return parse_usb_ids(&format!("{:04x}", usb.vid), &format!("{:04x}", usb.pid));
            }
        }
    }
    #[cfg(target_os = "linux")]
    if let Some(canonical) = canonical { return verify_linux_sysfs(&canonical); }
    Err(failure("The explicit port is not a verified c0de:cafc USB device. Run list; on Linux inspect the by-id/udev link and USB sysfs IDs. No serial command was sent"))
}

fn list_ports() -> Result<()> {
    for port in serialport::available_ports()? {
        match port.port_type {
            SerialPortType::UsbPort(usb) => output(json!({"event":"port","port":port.port_name,
                "vid":format!("{:04x}",usb.vid),"pid":format!("{:04x}",usb.pid),
                "usb_serial":usb.serial_number,"product":usb.product,"manufacturer":usb.manufacturer})),
            other => output(json!({"event":"port","port":port.port_name,"kind":format!("{other:?}")})),
        }
    }
    Ok(())
}

async fn apply_ipc<S: AsyncRead + AsyncWrite + Unpin>(link: &mut DeviceLink<S>, request: &IpcRequest) -> Result<Value> {
    request.validate()?;
    let acknowledged = match request {
        IpcRequest::Status => None,
        IpcRequest::Test { module } => Some(link.request_ack(Message::RunTest(module.wire())).await?),
        IpcRequest::Stop => Some(link.stop().await?),
        IpcRequest::Configure { config } => Some(link.configure(*config).await?),
    };
    // A freshly correlated query follows the command ACK. This is a reported
    // device snapshot, not position feedback or electrical verification.
    link.get_status().await?;
    Ok(json!({"ok":true,"cmd":request.name(),"ack_request_seq":acknowledged,
        "ack_code":if acknowledged.is_some() { Some("Ok") } else { None },
        "session":format!("{:016X}",link.session()),"status":link.snapshot_json()}))
}

async fn bridge<S: AsyncRead + AsyncWrite + Unpin>(link: &mut DeviceLink<S>, address: &str) -> Result<()> {
    let socket = Arc::new(UdpSocket::bind(loopback_address(address)?).await?);
    link.attach_ipc(socket.clone());
    output(json!({"event":"bridge_ready","listen":socket.local_addr()?.to_string(),
        "session":format!("{:016X}",link.session()),"protocol":PROTOCOL_NAME,
        "status":link.snapshot_json()}));
    loop {
        match link.next_input(Some(&socket), Instant::now() + REQUEST_TIMEOUT).await? {
            Input::Frame(_) => (),
            Input::Datagram { bytes, peer } => {
                let request = match parse_ipc(&bytes) {
                    Ok(request) => request,
                    Err(error) => {
                        let reply = json!({"ok":false,"error":error.to_string(),"status":link.snapshot_json()});
                        socket.send_to(&serde_json::to_vec(&reply)?, peer).await?;
                        continue;
                    }
                };
                match apply_ipc(link, &request).await {
                    Ok(reply) => { socket.send_to(&serde_json::to_vec(&reply)?, peer).await?; }
                    Err(error) => {
                        let rejection = error.downcast_ref::<DeviceRejection>();
                        let reply = json!({"ok":false,"cmd":request.name(),"error":error.to_string(),
                            "ack_code":rejection.map(|rejection| format!("{:?}",rejection.code)),
                            "status":link.snapshot_json()});
                        socket.send_to(&serde_json::to_vec(&reply)?, peer).await?;
                        if rejection.is_none() && error.downcast_ref::<RequestPreempted>().is_none() { return Err(error); }
                    }
                }
            }
        }
    }
}

async fn finite_test<S: AsyncRead + AsyncWrite + Unpin>(link: &mut DeviceLink<S>, module: TestModule) -> Result<()> {
    let wire = module.wire();
    let request_seq = link.request_ack(Message::RunTest(wire)).await?;
    output(json!({"event":"test_accepted","module":module,"request_seq":request_seq}));
    let deadline = Instant::now() + TEST_TIMEOUT;
    loop {
        let frame = link.next_frame(deadline).await?;
        if let Message::TestEvent { module: event_module, done, fault, .. } = frame.body {
            if fault { return Err(failure(format!("Test ended abnormally or was cancelled: {event_module:?}; inspect Status.faults before classifying it as a hardware fault"))); }
            if done && event_module == wire { return Ok(()); }
        }
    }
}

fn uploader_status(status: &DeviceStatus, session: u64) {
    println!("STATUS protocol={} bootloader=picotool-v1 oe_high={} version={} session={:016X} left_pixels={} right_pixels={} running={:?} faults={} dropped_events={}",
        PROTOCOL_NAME, status.oe_high as u8, VERSION, session, status.config.left_total(),
        status.config.right_total(), status.running, status.faults, status.dropped_events);
}

async fn run_serial(args: &Args) -> Result<()> {
    let port = args.port.as_deref().unwrap();
    let selected_config = if matches!(args.command, Command::Configure | Command::Bridge) || args.config.is_some() {
        Some(load_config(args.config.as_deref())?)
    } else { None };
    if args.command == Command::Bridge { loopback_address(args.listen.as_deref().unwrap_or(IPC_DEFAULT))?; }
    verify_serial_port(port)?;
    let mut serial = tokio_serial::new(port, 115_200).open_native_async()?;
    #[cfg(unix)]
    serial.set_exclusive(true)?;
    serial.write_data_terminal_ready(true)?;
    let interrupted = Arc::new(AtomicBool::new(false));
    let flag = interrupted.clone();
    let signal_task = tokio::spawn(async move {
        if tokio::signal::ctrl_c().await.is_ok() { flag.store(true, Ordering::SeqCst); }
    });
    let mut link = DeviceLink::new(serial, new_session()?, interrupted, true);
    // Hello intentionally stops the old session, including a local test. A
    // bridge remains the owner; normal Nano clients use UDP instead.
    if let Err(error) = link.hello().await {
        // USB VID/PID was verified before opening. Even a damaged/partial
        // handshake receives a best-effort dominant STOP before exit.
        link.begin_shutdown();
        match link.stop().await {
            Ok(request_seq) => output(json!({"event":"cleanup_ack","request_seq":request_seq,"code":"Ok"})),
            Err(stop_error) => output(json!({"event":"cleanup_unconfirmed","error":stop_error.to_string()})),
        }
        signal_task.abort();
        return Err(error);
    }
    let outcome: Result<()> = async {
        match args.command {
            Command::Status => {
                let status = link.get_status().await?;
                uploader_status(&status, link.session());
            }
            Command::Configure => {
                let request_seq = link.configure(selected_config.unwrap()).await?;
                let status = link.get_status().await?;
                output(json!({"event":"configured","request_seq":request_seq,"status":status}));
            }
            Command::Stop => {
                let request_seq = link.stop().await?;
                output(json!({"event":"stopped","request_seq":request_seq}));
                link.get_status().await?;
            }
            Command::Bootloader => {
                link.stop().await?;
                let status = link.get_status().await?;
                if !status.oe_high { return Err(failure("Device Status did not confirm servo OE HIGH after Stop; no Bootloader request was sent")); }
                let request_seq = link.request_ack(Message::Bootloader).await?;
                output(json!({"event":"bootloader_ack","request_seq":request_seq,"code":"Ok"}));
                // Host stdout compatibility only. This text never enters CDC.
                println!("OK BOOTLOADER");
            }
            Command::Test(module) => {
                if let Some(config) = selected_config { link.configure(config).await?; }
                finite_test(&mut link, module).await?;
            }
            Command::Bridge => {
                link.configure(selected_config.unwrap()).await?;
                link.get_status().await?;
                bridge(&mut link, args.listen.as_deref().unwrap_or(IPC_DEFAULT)).await?;
            }
            Command::List => unreachable!(),
        }
        Ok(())
    }.await;
    let needs_cleanup = matches!(args.command, Command::Test(_) | Command::Bridge)
        || (outcome.is_err() && args.command != Command::Bootloader);
    if needs_cleanup {
        link.begin_shutdown();
        match link.stop().await {
            Ok(request_seq) => output(json!({"event":"cleanup_ack","request_seq":request_seq,"code":"Ok"})),
            Err(error) => {
                output(json!({"event":"cleanup_unconfirmed","error":error.to_string()}));
                if outcome.is_ok() { return Err(error); }
            }
        }
    }
    signal_task.abort();
    if outcome.as_ref().err().is_some_and(|error| error.downcast_ref::<std::io::Error>()
        .is_some_and(|error| error.kind() == std::io::ErrorKind::Interrupted)) {
        output(json!({"event":"shutdown_complete"}));
        return Ok(());
    }
    outcome
}

async fn run() -> Result<()> {
    let args = parse_args(std::env::args().skip(1))?;
    if args.command == Command::List { return list_ports(); }
    if args.ctl {
        let request = match args.command {
            Command::Status => IpcRequest::Status, Command::Stop => IpcRequest::Stop,
            Command::Test(module) => IpcRequest::Test { module },
            Command::Configure => IpcRequest::Configure { config: load_config(args.config.as_deref())? },
            _ => unreachable!(),
        };
        let reply = udp_roundtrip(loopback_address(args.addr.as_deref().unwrap_or(IPC_DEFAULT))?, &request).await?;
        let ok = reply.get("ok").and_then(Value::as_bool) == Some(true);
        output(json!({"event":"ipc_reply","reply":reply}));
        return if ok { Ok(()) } else { Err(failure("Bridge rejected the command; inspect ipc_reply")) };
    }
    run_serial(&args).await
}

#[tokio::main]
async fn main() {
    if std::env::args().skip(1).any(|value| value == "--help" || value == "-h") {
        println!("{HELP}"); return;
    }
    if let Err(error) = run().await {
        let record = json!({"event":"error","host_unix_ms":pico_device_bench::unix_ms(),"error":error.to_string()});
        eprintln!("{record}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Result<Args> { parse_args(values.iter().map(|value| (*value).to_owned())) }

    #[test]
    fn one_usb_owner_and_four_typed_ipc_commands_are_enforced() {
        assert!(args(&["status"]).is_err());
        assert!(args(&["ctl","--port","COM11","status"]).is_err());
        assert!(args(&["ctl","bootloader"]).is_err());
        assert!(args(&["ctl","test","all","--config","config.json"]).is_err());
        assert_eq!(args(&["ctl","configure","--config","config.json"]).unwrap().command, Command::Configure);
        assert_eq!(args(&["--port","COM11","test","left"]).unwrap().command, Command::Test(TestModule::Left));
        assert!(args(&["--port","COM11","bridge","--listen","127.0.0.1:37920"]).is_ok());
    }

    #[test]
    fn canonical_alias_matching_and_usb_identity_are_explicit() {
        let canonical = Path::new("/dev/ttyACM7");
        assert!(port_names_match("/dev/serial/by-id/board", "/dev/ttyACM7", Some(canonical), Some(canonical)));
        assert!(port_names_match("/dev/pico-device", "/dev/ttyACM7", Some(canonical), Some(canonical)));
        assert!(!port_names_match("/dev/pico-device", "/dev/ttyACM8", Some(canonical), Some(Path::new("/dev/ttyACM8"))));
        assert!(port_names_match("com11", "COM11", None, None));
        assert!(!port_names_match("x터치", "COM11", None, None));
        assert!(parse_usb_ids("c0de\n", "cafc\n").is_ok());
        assert!(parse_usb_ids("c0de", "caff").is_err());
        assert!(parse_usb_ids("2e8a", "000f").is_err());
    }
}
