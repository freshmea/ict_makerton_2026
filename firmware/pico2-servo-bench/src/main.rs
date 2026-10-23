#![no_std]
#![no_main]

use core::{fmt::Write, sync::atomic::{AtomicBool, AtomicU32, Ordering}};
use embassy_executor::Spawner;
use embassy_futures::select::{select3, Either3};
use embassy_rp::{bind_interrupts, gpio::{Level, Output}, i2c::{self, I2c}, peripherals::{I2C0, USB}, usb::Driver};
use embassy_sync::{blocking_mutex::raw::CriticalSectionRawMutex, channel::Channel, signal::Signal};
use embassy_time::{with_timeout, Duration, Instant, Timer};
use embassy_usb::{class::cdc_acm::{CdcAcmClass, Receiver, Sender, State}, UsbDevice};
use heapless::{String, Vec};
use pico2_servo_bench::{parse, Command, Input, PulseRange};
use static_cell::StaticCell;

type UsbDriver = Driver<'static, USB>;
type Bus = I2c<'static, I2C0, i2c::Async>;
type Line = String<256>;

const ADDRESS: u8 = 0x41;
const LEASE_MS: u32 = 1000;
const TICK_MS: u64 = 20;
const I2C_TIMEOUT: Duration = Duration::from_millis(40);

static COMMANDS: Channel<CriticalSectionRawMutex, Envelope, 8> = Channel::new();
static REPLIES: Channel<CriticalSectionRawMutex, Line, 16> = Channel::new();
static STOP_WAKE: Signal<CriticalSectionRawMutex, ()> = Signal::new();
static STOPPED: AtomicBool = AtomicBool::new(true);
static STOP_REASON: AtomicU32 = AtomicU32::new(0);
static GENERATION: AtomicU32 = AtomicU32::new(0);
static CONNECTED: AtomicBool = AtomicBool::new(false);
static LAST_PING: AtomicU32 = AtomicU32::new(0);

#[derive(Clone, Copy)]
struct Envelope { generation: u32, command: Command }

bind_interrupts!(struct Irqs {
    USBCTRL_IRQ => embassy_rp::usb::InterruptHandler<USB>;
    I2C0_IRQ => i2c::InterruptHandler<I2C0>;
});

#[unsafe(link_section = ".bi_entries")]
#[used]
pub static PICOTOOL_ENTRIES: [embassy_rp::binary_info::EntryAddr; 4] = [
    embassy_rp::binary_info::rp_program_name!(c"Pico2 Servo Bench"),
    embassy_rp::binary_info::rp_program_description!(c"RP2350 USB CDC PCA9685 0x41 six-servo bench; no motion on boot"),
    embassy_rp::binary_info::rp_cargo_version!(),
    embassy_rp::binary_info::rp_program_build_attribute!(),
];

fn now_ms() -> u32 { Instant::now().as_millis() as u32 }
fn lease_valid() -> bool {
    CONNECTED.load(Ordering::SeqCst)
        && now_ms().wrapping_sub(LAST_PING.load(Ordering::SeqCst)) < LEASE_MS
}

fn request_stop(reason: u32) {
    STOP_REASON.store(reason, Ordering::SeqCst);
    STOPPED.store(true, Ordering::SeqCst);
    GENERATION.fetch_add(1, Ordering::SeqCst);
    // Hardware atomic SET avoids waiting for an in-flight I2C operation. Only
    // disables GP12; the control task alone may enable it after latch checks.
    embassy_rp::pac::SIO.gpio_out(0).value_set().write_value(1 << 12);
    STOP_WAKE.signal(());
}

// Diagnostics may be dropped under a non-reading host. Motion/stop must never
// wait for USB TX or a full telemetry queue.
fn emit(args: core::fmt::Arguments<'_>) {
    let mut line = Line::new();
    let _ = line.write_fmt(args);
    let _ = line.push_str("\r\n");
    let _ = REPLIES.try_send(line);
}
macro_rules! reply { ($($arg:tt)*) => { emit(format_args!($($arg)*)) }; }

#[embassy_executor::main(executor = "embassy_rp::executor::Executor", entry = "cortex_m_rt::entry")]
async fn main(spawner: Spawner) {
    let p = embassy_rp::init(Default::default());
    // Active-low PCA9685 OE. This pin is HIGH before any I2C/USB work.
    // During reset/BOOTSEL the pin floats: hardware reset gating is separate.
    let oe = Output::new(p.PIN_12, Level::High);
    let mut bus_config = i2c::Config::default();
    bus_config.frequency = 100_000;
    let bus = I2c::new_async(p.I2C0, p.PIN_5, p.PIN_4, Irqs, bus_config);

    let driver = Driver::new(p.USB, Irqs);
    // Example VID/PID for this local bench only, not a production assignment.
    let mut config = embassy_usb::Config::new(0xc0de, 0xcafe);
    config.manufacturer = Some("Makerthon bench");
    config.product = Some("Pico2 Servo Bench");
    config.serial_number = Some("PICO2-SERVO-BENCH-01");
    config.max_power = 100;
    config.max_packet_size_0 = 64;
    static CONFIG: StaticCell<[u8; 256]> = StaticCell::new();
    static BOS: StaticCell<[u8; 256]> = StaticCell::new();
    static CONTROL: StaticCell<[u8; 64]> = StaticCell::new();
    static CDC_STATE: StaticCell<State> = StaticCell::new();
    let mut builder = embassy_usb::Builder::new(driver, config, CONFIG.init([0; 256]), BOS.init([0; 256]), &mut [], CONTROL.init([0; 64]));
    let class = CdcAcmClass::new(&mut builder, CDC_STATE.init(State::new()), 64);
    let (sender, receiver) = class.split();
    spawner.spawn(usb_task(builder.build()).unwrap());
    spawner.spawn(rx_task(receiver).unwrap());
    spawner.spawn(tx_task(sender).unwrap());
    control_task(bus, oe).await;
}

#[embassy_executor::task]
async fn usb_task(mut usb: UsbDevice<'static, UsbDriver>) -> ! { usb.run().await }

#[embassy_executor::task]
async fn rx_task(mut rx: Receiver<'static, UsbDriver>) {
    let mut packet = [0u8; 64];
    let mut line: Vec<u8, 96> = Vec::new();
    loop {
        rx.wait_connection().await;
        CONNECTED.store(true, Ordering::SeqCst);
        line.clear();
        let mut overflow = false;
        loop {
            let n = match rx.read_packet(&mut packet).await {
                Ok(n) => n,
                Err(_) => break,
            };
            for &byte in &packet[..n] {
                if byte == b'\n' || byte == b'\r' {
                    if overflow {
                        reply!("ERR line_too_long");
                    } else if !line.is_empty() {
                        match core::str::from_utf8(&line).ok().and_then(parse) {
                            Some(Input::Stop) => {
                                request_stop(1);
                                reply!("OK STOP");
                            }
                            Some(Input::Ping) => {
                                LAST_PING.store(now_ms(), Ordering::SeqCst);
                                reply!("OK PING");
                            }
                            Some(Input::Command(command)) => {
                                let generation = GENERATION.load(Ordering::SeqCst);
                                if COMMANDS.try_send(Envelope { generation, command }).is_err() {
                                    reply!("ERR busy");
                                }
                            }
                            None => reply!("ERR invalid_command"),
                        }
                    }
                    line.clear();
                    overflow = false;
                } else if !overflow && line.push(byte).is_err() {
                    overflow = true;
                    // A malformed long line cannot be allowed to hold a run open.
                    request_stop(5);
                }
            }
        }
        CONNECTED.store(false, Ordering::SeqCst);
        request_stop(2);
    }
}

#[embassy_executor::task]
async fn tx_task(mut tx: Sender<'static, UsbDriver>) {
    loop {
        tx.wait_connection().await;
        loop {
            let line = REPLIES.receive().await;
            let mut failed = false;
            for chunk in line.as_bytes().chunks(64) {
                if !matches!(with_timeout(Duration::from_millis(500), tx.write_packet(chunk)).await, Ok(Ok(()))) {
                    failed = true;
                    break;
                }
            }
            // A full-size final packet requires a zero-length terminator.
            if !failed && line.len() % 64 == 0
                && !matches!(with_timeout(Duration::from_millis(500), tx.write_packet(&[])).await, Ok(Ok(()))) {
                failed = true;
            }
            if failed {
                request_stop(2);
                while REPLIES.try_receive().is_ok() {}
                Timer::after_millis(50).await;
                break;
            }
        }
    }
}

struct Pca { bus: Bus }
impl Pca {
    async fn write(&mut self, bytes: &[u8]) -> Result<(), ()> {
        match with_timeout(I2C_TIMEOUT, self.bus.write_async(ADDRESS, bytes.iter().copied())).await {
            Ok(Ok(())) => Ok(()), _ => Err(())
        }
    }
    async fn read_mode(&mut self, address: u8) -> Result<u8, ()> {
        let mut b = [0];
        match with_timeout(I2C_TIMEOUT, self.bus.write_read_async(address, [0].into_iter(), &mut b)).await {
            Ok(Ok(())) => Ok(b[0]), _ => Err(())
        }
    }
    async fn init(&mut self) -> Result<(), ()> {
        self.read_mode(ADDRESS).await?;
        // Sleep, auto-increment; clear all-call/subaddress enables.
        self.write(&[0x00, 0x30]).await?;
        self.write(&[0xfe, 121]).await?;
        // OUTDRV=1, OCH=0 (update on STOP), OUTNE=00 (OE HIGH -> LOW).
        self.write(&[0x01, 0x04]).await?;
        self.all_off().await?;
        self.write(&[0x00, 0x20]).await?;
        Timer::after_micros(600).await;
        self.write(&[0x00, 0xa0]).await?;
        self.all_off().await
    }
    async fn all_off(&mut self) -> Result<(), ()> {
        // Write each channel's explicit full-OFF bit. ALL_LED registers are
        // broadcast loaders for these same registers, not a separate mask;
        // writing zero to ALL_LED afterwards would erase the full-OFF bits.
        for channel in 0..16 {
            self.channel_off(channel).await?;
        }
        Ok(())
    }
    async fn channel_off(&mut self, channel: u8) -> Result<(), ()> {
        self.write(&[0x06 + channel * 4, 0, 0, 0, 0x10]).await
    }
    async fn pulse(&mut self, channel: u8, ticks: u16) -> Result<(), ()> {
        self.write(&[0x06 + channel * 4, 0, 0, ticks as u8, ((ticks >> 8) & 0x0f) as u8]).await
    }
}

#[derive(Clone, Copy, PartialEq)]
enum RunState { Disarmed, Armed, Sweeping, Done, Stopped, Fault }
impl RunState {
    fn name(self) -> &'static str {
        match self { Self::Disarmed => "disarmed", Self::Armed => "armed", Self::Sweeping => "sweeping", Self::Done => "done", Self::Stopped => "stopped", Self::Fault => "fault" }
    }
}
fn stop_reason() -> &'static str {
    match STOP_REASON.load(Ordering::SeqCst) {
        1 => "host_stop", 2 => "usb_disconnected", 3 => "lease_expired", 4 => "i2c_error", 5 => "invalid_frame", _ => "boot_disarmed"
    }
}

async fn control_task(bus: Bus, mut oe: Output<'static>) -> ! {
    let mut pca = Pca { bus };
    let mut state = RunState::Disarmed;
    let mut range = PulseRange::default();
    let mut i2c_state = "unchecked";
    let mut servo: u8 = 0;
    let mut angle: u16 = 0;
    let mut hold_ticks: u8 = 0;
    let mut next_tick = Instant::now() + Duration::from_millis(TICK_MS);
    loop {
        match select3(STOP_WAKE.wait(), COMMANDS.receive(), Timer::at(next_tick)).await {
            Either3::First(()) => {
                oe.set_high();
                servo = 0;
                state = RunState::Stopped;
                // OE goes HIGH immediately before attempting bus cleanup.
                // No bus response is needed to gate pulses via OE.
                let _ = pca.all_off().await;
                reply!("EVENT STOP reason={}", stop_reason());
            }
            Either3::Second(envelope) => {
                if envelope.generation != GENERATION.load(Ordering::SeqCst) {
                    reply!("ERR stale_command");
                    continue;
                }
                match envelope.command {
                    Command::Status => reply!("STATUS protocol=servo-bench-v1 state={} servo={} angle={} address=0x41 i2c={} min_us={} max_us={} reason={} oe_high={}", state.name(), servo, angle, i2c_state, range.min_us, range.max_us, stop_reason(), if oe.is_set_high() { 1 } else { 0 }),
                    Command::Scan => {
                        if state == RunState::Sweeping || state == RunState::Armed {
                            reply!("ERR disarm_before_scan");
                            continue;
                        }
                        oe.set_high();
                        let mut count = 0;
                        i2c_state = "error";
                        for address in 0x08..=0x77 {
                            if envelope.generation != GENERATION.load(Ordering::SeqCst) { break; }
                            if let Ok(mode1) = pca.read_mode(address).await {
                                count += 1;
                                if address == ADDRESS { i2c_state = "ok"; }
                                reply!("SCAN address=0x{:02x} mode1=0x{:02x}", address, mode1);
                            }
                        }
                        reply!("SCAN DONE count={}", count);
                    }
                    Command::Config(new_range) => {
                        if state == RunState::Sweeping || state == RunState::Armed {
                            reply!("ERR disarm_before_config");
                        } else {
                            range = new_range;
                            reply!("OK CONFIG min_us={} max_us={}", range.min_us, range.max_us);
                        }
                    }
                    Command::Arm => {
                        if state == RunState::Sweeping {
                            reply!("ERR busy");
                            continue;
                        }
                        oe.set_high();
                        if pca.init().await.is_err() {
                            i2c_state = "error";
                            state = RunState::Fault;
                            request_stop(4);
                            reply!("ERR i2c_init");
                        } else if envelope.generation == GENERATION.load(Ordering::SeqCst) && CONNECTED.load(Ordering::SeqCst) {
                            i2c_state = "ok";
                            LAST_PING.store(now_ms(), Ordering::SeqCst);
                            STOPPED.store(false, Ordering::SeqCst);
                            STOP_REASON.store(0, Ordering::SeqCst);
                            state = RunState::Armed;
                            servo = 0;
                            reply!("OK ARM");
                        } else { reply!("ERR arm_cancelled"); }
                    }
                    Command::Sweep => {
                        if state != RunState::Armed || STOPPED.load(Ordering::SeqCst) || !lease_valid() {
                            reply!("ERR not_armed");
                            continue;
                        }
                        // All channels are OFF; only CH0 receives the first pulse.
                        if pca.pulse(0, range.ticks(0)).await.is_err() {
                            oe.set_high();
                            i2c_state = "error";
                            state = RunState::Fault;
                            request_stop(4);
                            reply!("ERR i2c_write");
                            continue;
                        }
                        // Re-check after I2C awaits: a stop may have arrived.
                        if STOPPED.load(Ordering::SeqCst) || !lease_valid() { oe.set_high(); continue; }
                        servo = 1;
                        angle = 0;
                        hold_ticks = 25; // allow initial 0-label positioning (500ms)
                        state = RunState::Sweeping;
                        oe.set_low();
                        reply!("OK SWEEP");
                        reply!("EVENT servo=1 angle=0 phase=start");
                    }
                }
            }
            Either3::Third(()) => {
                next_tick = Instant::now() + Duration::from_millis(TICK_MS);
                if matches!(state, RunState::Armed | RunState::Sweeping) && !lease_valid() {
                    oe.set_high();
                    request_stop(3);
                    continue;
                }
                if STOPPED.load(Ordering::SeqCst) || state != RunState::Sweeping { continue; }
                if hold_ticks > 0 { hold_ticks -= 1; continue; }
                if angle < 180 {
                    angle += 1;
                    if pca.pulse(servo - 1, range.ticks(angle)).await.is_err() {
                        oe.set_high();
                        i2c_state = "error";
                        state = RunState::Fault;
                        request_stop(4);
                    }
                    // Hold at the last commanded position for 500 ms before OFF.
                    if angle == 180 { hold_ticks = 25; reply!("EVENT servo={} angle=180 phase=end", servo); }
                } else {
                    oe.set_high();
                    if pca.channel_off(servo - 1).await.is_err() {
                        i2c_state = "error";
                        state = RunState::Fault;
                        request_stop(4);
                        continue;
                    }
                    if servo == 6 {
                        state = RunState::Done;
                        STOPPED.store(true, Ordering::SeqCst);
                        servo = 0;
                        reply!("EVENT DONE");
                    } else {
                        servo += 1;
                        angle = 0;
                        hold_ticks = 25;
                        if pca.pulse(servo - 1, range.ticks(0)).await.is_err() {
                            i2c_state = "error";
                            state = RunState::Fault;
                            request_stop(4);
                            continue;
                        }
                        if STOPPED.load(Ordering::SeqCst) || !lease_valid() { oe.set_high(); continue; }
                        oe.set_low();
                        reply!("EVENT servo={} angle=0 phase=start", servo);
                    }
                }
            }
        }
    }
}

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    // Drive GP12's already-configured SIO output HIGH even if another task
    // panics. No reset is attempted because reset makes OE high-impedance.
    embassy_rp::pac::SIO.gpio_out(0).value_set().write_value(1 << 12);
    loop { cortex_m::asm::wfi(); }
}
