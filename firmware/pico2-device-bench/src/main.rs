#![no_std]
#![no_main]

use core::{cell::{Cell, RefCell}, sync::atomic::{AtomicBool, AtomicU32, Ordering}};
use embassy_executor::Spawner;
use embassy_futures::select::{select, select3, Either, Either3};
use embassy_rp::{bind_interrupts, dma, gpio::{Flex, Level, Output, Pull},
    i2c::{self,I2c}, peripherals::{DMA_CH0,DMA_CH1,I2C0,PIO0,SPI0,USB},
    pio::{self,Pio}, pio_programs::ws2812::{Grb,PioWs2812,PioWs2812Program},
    spi::{self,Spi}, usb::Driver};
use embassy_sync::{blocking_mutex::{raw::CriticalSectionRawMutex,Mutex},channel::Channel,signal::Signal};
use embassy_time::{with_timeout,Duration,Instant,Timer};
use embassy_usb::{class::cdc_acm::{CdcAcmClass,Receiver,Sender,State},UsbDevice};
use pico_device_protocol::{AckCode,DeviceConfig,DeviceStatus,Frame as WireFrame,FrameDecoder,
    Message,Module,TouchEngine,TouchState,VERSION,MAX_WIRE};
use pico2_device_bench::{picotool_reset,Admission,Gesture,GestureAction,MatrixFrame,
    SessionGate,CAPACITY,matrix_frame,neo_frame,servo_angle,servo_ticks,stage};
use smart_leds::RGB8;
use static_cell::StaticCell;

type UsbDriver=Driver<'static,USB>;
type Bus=I2c<'static,I2C0,i2c::Async>;
type Left=PioWs2812<'static,PIO0,0,CAPACITY,Grb>;
type Right=PioWs2812<'static,PIO0,1,CAPACITY,Grb>;
const LEASE_MS:u32=1000;
const PCA_FAULT:u32=1;
const MATRIX_FAULT:u32=2;
static COMMANDS:Channel<CriticalSectionRawMutex,Envelope,8>=Channel::new();
static LOCALS:Channel<CriticalSectionRawMutex,LocalCommand,2>=Channel::new();
static RESPONSES:Channel<CriticalSectionRawMutex,WireFrame,8>=Channel::new();
static EVENTS:Channel<CriticalSectionRawMutex,WireFrame,16>=Channel::new();
static STOP_WAKE:Signal<CriticalSectionRawMutex,()>=Signal::new();
static STOP_ACK:Signal<CriticalSectionRawMutex,WireFrame>=Signal::new();
static BOOT_ACK:Signal<CriticalSectionRawMutex,WireFrame>=Signal::new();
static TOUCH_CONFIG:Signal<CriticalSectionRawMutex,DeviceConfig>=Signal::new();
static SNAPSHOT:Mutex<CriticalSectionRawMutex,RefCell<Option<TouchSnapshot>>>=Mutex::new(RefCell::new(None));
static SESSION:Mutex<CriticalSectionRawMutex,Cell<u64>>=Mutex::new(Cell::new(0));
static CONNECTED:AtomicBool=AtomicBool::new(false);
static STOPPED:AtomicBool=AtomicBool::new(true);
static ACTIVE:AtomicBool=AtomicBool::new(false);
static GENERATION:AtomicU32=AtomicU32::new(0);
static LAST_PING:AtomicU32=AtomicU32::new(0);
static STOP_REASON:AtomicU32=AtomicU32::new(0);
static BOOT_REQUESTED:AtomicBool=AtomicBool::new(false);
static EVENT_SEQUENCE:AtomicU32=AtomicU32::new(0);
static DROPPED:AtomicU32=AtomicU32::new(0);

#[derive(Clone,Copy)]
struct Envelope{frame:WireFrame,generation:u32,busy:bool}
#[derive(Clone,Copy)]
struct LocalCommand{module:Module,generation:u32}
#[derive(Clone,Copy)]
struct TouchSnapshot{raw:u8,pressed:u8,states:[TouchState;6]}

bind_interrupts!(struct Irqs{
    USBCTRL_IRQ=>embassy_rp::usb::InterruptHandler<USB>;
    I2C0_IRQ=>i2c::InterruptHandler<I2C0>;
    PIO0_IRQ_0=>pio::InterruptHandler<PIO0>;
    DMA_IRQ_0=>dma::InterruptHandler<DMA_CH0>,dma::InterruptHandler<DMA_CH1>;
});
#[unsafe(link_section=".bi_entries")]
#[used]
pub static PICOTOOL_ENTRIES:[embassy_rp::binary_info::EntryAddr;4]=[
    embassy_rp::binary_info::rp_program_name!(c"Pico2 Device Bench"),
    embassy_rp::binary_info::rp_program_description!(c"Binary USB device tests; six touch inputs, dual NeoPixel, eyes, six PCA9685 servos"),
    embassy_rp::binary_info::rp_cargo_version!(),
    embassy_rp::binary_info::rp_program_build_attribute!(),
];
fn now()->u32{Instant::now().as_millis() as u32}
fn session()->u64{SESSION.lock(|v|v.get())}
fn set_session(value:u64){SESSION.lock(|v|v.set(value));}
fn lease_valid()->bool{CONNECTED.load(Ordering::SeqCst)&&now().wrapping_sub(LAST_PING.load(Ordering::SeqCst))<LEASE_MS}
fn request_stop(reason:u32){
    STOP_REASON.store(reason,Ordering::SeqCst);STOPPED.store(true,Ordering::SeqCst);
    GENERATION.fetch_add(1,Ordering::SeqCst);
    embassy_rp::pac::SIO.gpio_out(0).value_set().write_value(1<<12);
    STOP_WAKE.signal(());
}
fn request_bootloader(){BOOT_REQUESTED.store(true,Ordering::SeqCst);request_stop(7);}
fn reply(request:WireFrame,body:Message){
    if RESPONSES.try_send(WireFrame{version:VERSION,session:request.session,seq:request.seq,body}).is_err(){DROPPED.fetch_add(1,Ordering::SeqCst);}
}
fn ack(request:WireFrame,code:AckCode){reply(request,Message::Ack{request_seq:request.seq,code});}
fn event(body:Message){
    let seq=EVENT_SEQUENCE.fetch_add(1,Ordering::SeqCst).wrapping_add(1);
    let owner=session();
    // An unconnected local test must not block on USB or stop on TX timeout.
    if owner==0||!CONNECTED.load(Ordering::SeqCst){DROPPED.fetch_add(1,Ordering::SeqCst);return;}
    if EVENTS.try_send(WireFrame{version:VERSION,session:owner,seq,body}).is_err(){DROPPED.fetch_add(1,Ordering::SeqCst);}
}

#[embassy_executor::main(executor="embassy_rp::executor::Executor",entry="cortex_m_rt::entry")]
async fn main(spawner:Spawner){
    let p=embassy_rp::init(Default::default());
    let oe=Output::new(p.PIN_12,Level::High);
    let mut bus_config=i2c::Config::default();bus_config.frequency=100_000;
    let pca=Pca{bus:I2c::new_async(p.I2C0,p.PIN_5,p.PIN_4,Irqs,bus_config)};
    // Common and the shared loaded program stay alive for both state machines.
    let Pio{mut common,sm0,sm1,..}=Pio::new(p.PIO0,Irqs);
    let program=PioWs2812Program::new(&mut common);
    let left=PioWs2812::new(&mut common,sm0,p.DMA_CH0,Irqs,p.PIN_16,&program);
    let right=PioWs2812::new(&mut common,sm1,p.DMA_CH1,Irqs,p.PIN_17,&program);
    let cs=Output::new(p.PIN_20,Level::High);
    let mut spi_config=spi::Config::default();spi_config.frequency=1_000_000;
    let matrix=Matrix{spi:Spi::new_blocking_txonly(p.SPI0,p.PIN_18,p.PIN_19,spi_config),cs};
    let mut devices=Devices{pca,left,right,matrix,oe};
    let faults=devices.stop_all().await;
    let config=DeviceConfig::default();
    let pins=[Flex::new(p.PIN_6),Flex::new(p.PIN_7),Flex::new(p.PIN_8),
        Flex::new(p.PIN_9),Flex::new(p.PIN_10),Flex::new(p.PIN_11)];
    spawner.spawn(touch_task(pins,config).unwrap());
    let chipid=embassy_rp::otp::get_chipid().expect("Cannot read public chip ID");
    let driver=Driver::new(p.USB,Irqs);
    let mut usb_config=embassy_usb::Config::new(0xc0de,0xcafc);
    usb_config.manufacturer=Some("Makerthon bench");usb_config.product=Some("Pico2 Device Bench");
    static SERIAL:StaticCell<[u8;16]>=StaticCell::new();
    usb_config.serial_number=Some(core::str::from_utf8(SERIAL.init(picotool_reset::chipid_serial(chipid))).unwrap());
    usb_config.device_release=0x0011;usb_config.max_packet_size_0=64;usb_config.max_power=100;
    static CFG:StaticCell<[u8;256]>=StaticCell::new();static BOS:StaticCell<[u8;256]>=StaticCell::new();
    static MSOS:StaticCell<[u8;256]>=StaticCell::new();static CONTROL:StaticCell<[u8;64]>=StaticCell::new();
    static CDC:StaticCell<State>=StaticCell::new();static RESET:StaticCell<picotool_reset::State>=StaticCell::new();
    let mut builder=embassy_usb::Builder::new(driver,usb_config,CFG.init([0;256]),BOS.init([0;256]),MSOS.init([0;256]),CONTROL.init([0;64]));
    let class=CdcAcmClass::new(&mut builder,CDC.init(State::new()),64);let(sender,receiver)=class.split();
    picotool_reset::register(&mut builder,RESET.init(picotool_reset::State::new()),request_bootloader);
    spawner.spawn(usb_task(builder.build()).unwrap());spawner.spawn(rx_task(receiver).unwrap());spawner.spawn(tx_task(sender).unwrap());
    device_task(devices,config,chipid,faults).await;
}
#[embassy_executor::task]
async fn usb_task(mut usb:UsbDevice<'static,UsbDriver>)->!{usb.run().await}
#[embassy_executor::task]
async fn rx_task(mut rx:Receiver<'static,UsbDriver>){
    let mut packet=[0;64];let mut decoder=FrameDecoder::new();
    loop{
        rx.wait_connection().await;CONNECTED.store(true,Ordering::SeqCst);decoder.clear();
        loop{
            let n=match rx.read_packet(&mut packet).await{Ok(n)=>n,Err(_)=>break};
            for &byte in &packet[..n]{
                if let Some(result)=decoder.push(byte){match result{
                    Ok(frame)=>{
                        // A CRC-valid, decoded STOP always gates OE first,
                        // regardless of session or sequence admission.
                        if frame.body==Message::Stop{STOP_ACK.signal(frame);request_stop(1);continue;}
                        if frame.version!=VERSION{ack(frame,AckCode::BadVersion);continue;}
                        if frame.body==Message::Hello&&frame.session!=session(){request_stop(6);}
                        let envelope=Envelope{frame,generation:GENERATION.load(Ordering::SeqCst),busy:ACTIVE.load(Ordering::SeqCst)};
                        if COMMANDS.try_send(envelope).is_err(){ack(frame,AckCode::Busy);}
                    }
                    Err(_)=>{DROPPED.fetch_add(1,Ordering::SeqCst);}
                }}
            }
        }
        CONNECTED.store(false,Ordering::SeqCst);request_stop(2);
    }
}
#[embassy_executor::task]
async fn tx_task(mut tx:Sender<'static,UsbDriver>){
    let mut wire=[0;MAX_WIRE];
    loop{
        tx.wait_connection().await;
        loop{
            let frame=match select(RESPONSES.receive(),EVENTS.receive()).await{Either::First(v)|Either::Second(v)=>v};
            // Drop telemetry left over from an expired/changed session.
            if !matches!(frame.body,Message::Ack{..}|Message::HelloReply{..})&&frame.session!=session(){continue;}
            let len=match pico_device_protocol::encode_frame(&frame,&mut wire){Ok(n)=>n,Err(_)=>{DROPPED.fetch_add(1,Ordering::SeqCst);continue;}};
            let mut failed=false;
            for chunk in wire[..len].chunks(64){if !matches!(with_timeout(Duration::from_millis(500),tx.write_packet(chunk)).await,Ok(Ok(()))){failed=true;break;}}
            if !failed&&len%64==0&&!matches!(with_timeout(Duration::from_millis(500),tx.write_packet(&[])).await,Ok(Ok(()))){failed=true;}
            if failed{request_stop(2);while RESPONSES.try_receive().is_ok(){}while EVENTS.try_receive().is_ok(){}Timer::after_millis(50).await;break;}
        }
    }
}
#[embassy_executor::task]
async fn touch_task(mut pins:[Flex<'static>;6],mut config:DeviceConfig){
    for pin in &mut pins{pin.set_as_input();pin.set_pull(Pull::None);}
    let mut engine=TouchEngine::new(config).unwrap();let mut gesture=Gesture::new();
    // Require an initial release: a held input at boot/configuration is not a new gesture.
    let mut await_release=true;let mut release_since=None;
    loop{
        let time=Instant::now().as_millis();
        if let Some(value)=TOUCH_CONFIG.try_take(){config=value;let _=engine.configure(value,time);gesture.clear(true);await_release=true;release_since=None;}
        let mut raw=0;for(index,pin)in pins.iter().enumerate(){if pin.is_high(){raw|=1<<index;}}
        for value in engine.sample(raw,time){event(Message::Touch(value));}
        let pressed=engine.pressed_mask();
        SNAPSHOT.lock(|v|*v.borrow_mut()=Some(TouchSnapshot{raw,pressed,states:engine.states(time)}));
        let bit=if config.test_switch==0{0}else{1<<(config.test_switch-1)};
        let logical_raw=(raw^config.touch_active_low_mask)&bit!=0;
        if await_release{
            if logical_raw{release_since=None;}else{
                let since=release_since.get_or_insert(time);
                if time.saturating_sub(*since)>=30{await_release=false;gesture.clear(false);}
            }
        }else if let Some(action)=gesture.sample(pressed&bit!=0,ACTIVE.load(Ordering::SeqCst),
            config.local_tests_enabled&&bit!=0,GENERATION.load(Ordering::SeqCst),time,config.hold_interval_ms){
            match action{
                GestureAction::Stop=>request_stop(3),
                GestureAction::Test(module)=>{let generation=GENERATION.load(Ordering::SeqCst);let _=LOCALS.try_send(LocalCommand{module,generation});}
            }
        }
        Timer::after_millis(5).await;
    }
}

struct Pca{bus:Bus}
impl Pca{
    async fn write(&mut self,bytes:&[u8])->Result<(),()>{match with_timeout(Duration::from_millis(40),self.bus.write_async(0x41u8,bytes.iter().copied())).await{Ok(Ok(()))=>Ok(()),_=>Err(())}}
    // One register write also works before MODE1 auto-increment is enabled.
    // ALL_LED_OFF_H broadcasts the explicit FULL_OFF bit to every channel.
    async fn all_off(&mut self)->Result<(),()>{self.write(&[0xfd,0x10]).await}
    async fn off(&mut self,ch:u8)->Result<(),()>{self.write(&[0x06+ch*4,0,0,0,0x10]).await}
    async fn init(&mut self)->Result<(),()>{
        self.all_off().await?;self.write(&[0x00,0x30]).await?;self.write(&[0xfe,121]).await?;
        self.write(&[0x01,0x04]).await?;self.write(&[0x00,0x20]).await?;Timer::after_micros(600).await;
        self.write(&[0x00,0xa0]).await?;self.all_off().await
    }
    async fn pulse(&mut self,ch:u8,ticks:u16)->Result<(),()>{self.write(&[0x06+ch*4,0,0,ticks as u8,((ticks>>8)&0x0f)as u8]).await}
}
struct Matrix{spi:Spi<'static,SPI0,spi::Blocking>,cs:Output<'static>}
impl Matrix{
    fn reg(&mut self,address:u8,left:u8,right:u8)->Result<(),()>{self.cs.set_low();let result=self.spi.blocking_write(&[address,right,address,left]).map_err(|_|());self.cs.set_high();cortex_m::asm::delay(150);result}
    fn frame(&mut self,f:MatrixFrame)->Result<(),()>{for row in 0..8{self.reg(row as u8+1,f.left[row],f.right[row])?;}Ok(())}
    fn off(&mut self)->Result<(),()>{let mut ok=self.reg(0xf,0,0).is_ok();ok&=self.reg(0xc,0,0).is_ok();ok&=self.frame(MatrixFrame::BLANK).is_ok();if ok{Ok(())}else{Err(())}}
    fn init(&mut self)->Result<(),()>{self.off()?;self.reg(9,0,0)?;self.reg(0xb,7,7)?;self.reg(0xa,1,1)}
    fn enable(&mut self)->Result<(),()>{self.reg(0xc,1,1)}
}
struct Devices{pca:Pca,left:Left,right:Right,matrix:Matrix,oe:Output<'static>}
impl Devices{
    async fn neo(&mut self,module:Module,frame:[[u8;3];CAPACITY]){
        let rgb=frame.map(|v|RGB8{r:v[0],g:v[1],b:v[2]});
        if module==Module::NeoLeft{self.left.write(&rgb).await;}else{self.right.write(&rgb).await;}
        // DMA may finish before the FIFO tail. This adds >300 us actual reset LOW.
        Timer::after_micros(1000).await;
    }
    async fn stop_all(&mut self)->u32{
        self.oe.set_high();let mut faults=0;
        self.neo(Module::NeoLeft,[[0;3];CAPACITY]).await;self.neo(Module::NeoRight,[[0;3];CAPACITY]).await;
        if self.matrix.off().is_err(){faults|=MATRIX_FAULT;}
        if self.pca.all_off().await.is_err(){faults|=PCA_FAULT;}faults
    }
    async fn finish_module(&mut self,module:Module)->Result<(),()>{match module{
        Module::Matrix=>self.matrix.off(),Module::NeoLeft|Module::NeoRight=>{self.neo(module,[[0;3];CAPACITY]).await;Ok(())},
        Module::Servos=>{self.oe.set_high();self.pca.all_off().await},Module::All=>Ok(())}}
}
struct Run{selected:Module,index:usize,module:Module,phase:u16,generation:u32,next:Instant}
fn run_valid(generation:u32)->bool{!STOPPED.load(Ordering::SeqCst)&&GENERATION.load(Ordering::SeqCst)==generation&&(session()==0||lease_valid())}
fn phase_count(module:Module,cfg:&DeviceConfig)->u16{match module{Module::Matrix=>20,Module::NeoLeft=>9+cfg.left_total()as u16,Module::NeoRight=>9+cfg.right_total()as u16,Module::Servos=>24,Module::All=>0}}
fn phase_delay(module:Module,phase:u16)->u64{match module{Module::Matrix=>match phase{0|1|18=>800,19=>1000,_=>400},Module::NeoLeft|Module::NeoRight=>if phase<9{400}else{60},_=>500}}
async fn apply_phase(devices:&mut Devices,run:&Run,cfg:&DeviceConfig)->Result<(),()>{
    if !run_valid(run.generation){return Err(());}
    match run.module{
        Module::Matrix=>{if run.phase==0{devices.matrix.init()?;}devices.matrix.frame(matrix_frame(run.phase))?;devices.matrix.enable()?;}
        Module::NeoLeft|Module::NeoRight=>{let segments=if run.module==Module::NeoLeft{cfg.left_segments}else{cfg.right_segments};devices.neo(run.module,neo_frame(segments,run.phase)).await;}
        Module::Servos=>{
            if run.phase==0{devices.oe.set_high();devices.pca.init().await?;if !run_valid(run.generation){return Err(());}}
            let channel=(run.phase/4)as u8;
            if run.phase%4==0&&channel>0{devices.oe.set_high();devices.pca.off(channel-1).await?;if !run_valid(run.generation){return Err(());}}
            let angle=servo_angle(run.phase,cfg.test_span_degrees);
            devices.pca.pulse(channel,servo_ticks(cfg,angle)).await?;
            if !run_valid(run.generation){devices.oe.set_high();return Err(());}
            devices.oe.set_low();
        }
        Module::All=>return Err(()),
    }
    if run_valid(run.generation){Ok(())}else{devices.oe.set_high();Err(())}
}
fn status(config:DeviceConfig,run:&Option<Run>,faults:u32,oe_high:bool)->DeviceStatus{
    let snapshot=SNAPSHOT.lock(|v|*v.borrow());
    let touch=snapshot.unwrap_or(TouchSnapshot{raw:0,pressed:0,states:[TouchState::default();6]});
    DeviceStatus{uptime_ms:Instant::now().as_millis(),raw_mask:touch.raw,pressed_mask:touch.pressed,touches:touch.states,
        running:run.as_ref().map(|v|v.module),local_enabled:config.local_tests_enabled,oe_high,faults,
        dropped_events:DROPPED.load(Ordering::SeqCst),config}
}
async fn start_run(module:Module,devices:&mut Devices,config:&DeviceConfig)->Result<Run,()>{
    STOPPED.store(false,Ordering::SeqCst);ACTIVE.store(true,Ordering::SeqCst);
    let mut run=Run{selected:module,index:0,module:stage(module,0).unwrap(),phase:0,
        generation:GENERATION.load(Ordering::SeqCst),next:Instant::now()};
    apply_phase(devices,&run,config).await?;
    run.next=Instant::now()+Duration::from_millis(phase_delay(run.module,0));
    event(Message::TestEvent{module:run.module,phase:0,done:false,fault:false});Ok(run)
}

async fn device_task(mut devices:Devices,mut config:DeviceConfig,chipid:u64,mut faults:u32)->!{
    let mut gate=SessionGate::new();let mut run:Option<Run>=None;
    let mut tick=Instant::now()+Duration::from_millis(20);let mut next_status=Instant::now();
    loop{
        if gate.session!=0&&!lease_valid(){gate.open(0);set_session(0);request_stop(4);}
        match select3(STOP_WAKE.wait(),Timer::at(tick),select(COMMANDS.receive(),LOCALS.receive())).await{
            Either3::First(())=>{
                let old=run.take();ACTIVE.store(false,Ordering::SeqCst);
                faults|=devices.stop_all().await;
                if let Some(value)=old{event(Message::TestEvent{module:value.selected,phase:value.phase,done:true,fault:faults!=0});}
                if matches!(STOP_REASON.load(Ordering::SeqCst),2|4){gate.open(0);set_session(0);}
                if let Some(frame)=STOP_ACK.try_take(){if frame.session==gate.session{gate.finish(frame.seq,AckCode::Ok);}ack(frame,AckCode::Ok);}
                if BOOT_REQUESTED.load(Ordering::SeqCst){
                    if let Some(frame)=BOOT_ACK.try_take(){ack(frame,if faults==0{AckCode::Ok}else{AckCode::Fault});}
                    Timer::after_millis(150).await;embassy_rp::rom_data::reset_to_usb_boot(0,0);loop{cortex_m::asm::wfi();}
                }
                event(Message::Status(status(config,&run,faults,devices.oe.is_set_high())));
            }
            Either3::Second(())=>{
                tick=Instant::now()+Duration::from_millis(20);
                if Instant::now()>=next_status{next_status=Instant::now()+Duration::from_millis(100);event(Message::Status(status(config,&run,faults,devices.oe.is_set_high())));}
                if let Some(value)=run.as_mut(){
                    if !run_valid(value.generation){request_stop(5);continue;}
                    if Instant::now()<value.next{continue;}
                    value.phase+=1;
                    if value.phase>=phase_count(value.module,&config){
                        if devices.finish_module(value.module).await.is_err(){faults|=if value.module==Module::Servos{PCA_FAULT}else{MATRIX_FAULT};request_stop(5);continue;}
                        if !run_valid(value.generation){request_stop(5);continue;}
                        if value.selected==Module::All{event(Message::TestEvent{module:value.module,phase:value.phase,done:true,fault:false});}
                        value.index+=1;
                        if let Some(module)=stage(value.selected,value.index){value.module=module;value.phase=0;}
                        else{let selected=value.selected;run=None;ACTIVE.store(false,Ordering::SeqCst);STOPPED.store(true,Ordering::SeqCst);event(Message::TestEvent{module:selected,phase:0,done:true,fault:false});continue;}
                    }
                    if apply_phase(&mut devices,value,&config).await.is_err(){
                        if run_valid(value.generation){faults|=if value.module==Module::Servos{PCA_FAULT}else{MATRIX_FAULT};}
                        request_stop(5);continue;
                    }
                    value.next=Instant::now()+Duration::from_millis(phase_delay(value.module,value.phase));
                    event(Message::TestEvent{module:value.module,phase:value.phase,done:false,fault:false});
                }
            }
            Either3::Third(Either::Second(local))=>{
                if local.generation!=GENERATION.load(Ordering::SeqCst)||run.is_some()||!config.local_tests_enabled{continue;}
                if gate.session!=0&&!lease_valid(){continue;}
                match start_run(local.module,&mut devices,&config).await{Ok(value)=>run=Some(value),Err(())=>request_stop(5)}
            }
            Either3::Third(Either::First(envelope))=>{
                let frame=envelope.frame;
                if envelope.generation!=GENERATION.load(Ordering::SeqCst){ack(frame,AckCode::StaleSequence);continue;}
                if frame.body==Message::Hello{
                    if frame.session==0{ack(frame,AckCode::BadSession);continue;}
                    if frame.session!=gate.session{
                        devices.oe.set_high();faults=devices.stop_all().await;run=None;ACTIVE.store(false,Ordering::SeqCst);
                        gate.open(frame.session);set_session(frame.session);
                    }
                    match gate.check(frame.seq){
                        Admission::Stale=>{ack(frame,AckCode::StaleSequence);continue;},
                        Admission::New=>LAST_PING.store(now(),Ordering::SeqCst),
                        Admission::Duplicate(_)=>(),
                    }
                    gate.finish(frame.seq,AckCode::Ok);
                    reply(frame,Message::HelloReply{device_id:chipid,uptime_ms:Instant::now().as_millis()});ack(frame,AckCode::Ok);continue;
                }
                if gate.session==0{ack(frame,AckCode::NoSession);continue;}
                if frame.session!=gate.session{ack(frame,AckCode::BadSession);continue;}
                match gate.check(frame.seq){Admission::Duplicate(code)=>{ack(frame,code);continue;},Admission::Stale=>{ack(frame,AckCode::StaleSequence);continue;},Admission::New=>()}
                let code=match frame.body{
                    Message::KeepAlive=>{LAST_PING.store(now(),Ordering::SeqCst);AckCode::Ok}
                    Message::GetStatus=>{reply(frame,Message::Status(status(config,&run,faults,devices.oe.is_set_high())));AckCode::Ok}
                    Message::Configure(value)=>{
                        if run.is_some()||envelope.busy{AckCode::Busy}else if value.validate().is_err(){AckCode::InvalidConfig}
                        else{config=value;GENERATION.fetch_add(1,Ordering::SeqCst);TOUCH_CONFIG.signal(value);AckCode::Ok}
                    }
                    Message::RunTest(module)=>{
                        if run.is_some()||envelope.busy{AckCode::Busy}else if !lease_valid(){AckCode::NoSession}
                        else{match start_run(module,&mut devices,&config).await{Ok(value)=>{run=Some(value);AckCode::Ok},Err(())=>{request_stop(5);AckCode::Fault}}}
                    }
                    Message::Bootloader=>{BOOT_ACK.signal(frame);request_bootloader();continue;}
                    _=>AckCode::Unsupported,
                };
                gate.finish(frame.seq,code);ack(frame,code);
            }
        }
    }
}
#[panic_handler]
fn panic(_info:&core::panic::PanicInfo)->!{
    embassy_rp::pac::SIO.gpio_out(0).value_set().write_value(1<<12);
    // NeoPixel/MAX7219 can retain a latched display on CPU failure.
    loop{cortex_m::asm::wfi();}
}
