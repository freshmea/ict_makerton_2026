//! Latest target output state; the device task remains the single I2C/PIO owner.
//!
//! 명령을 받으면 목표와 시작 시각을 저장하고 [`Application::tick`]에서 실제
//! 장치에 적용한다. 포즈·SW4·조명·눈은 같은 소유자가 순서대로 처리한다.
//! 각도 배열은 centidegree이며 `current`도 실제 센서값이 아닌 명령값이다.
use super::*;
use pico_device_protocol::{ActuatorConfig,OutputStatus};
use pico2_device_bench::arm_patterns::{ArmPatterns,MAX_SPEED_CDEG_S};
/// Arm 설정과 일반 출력 목표의 상태. 하드웨어 자체는 빌려서 사용한다.
pub struct Application {
    /// 축별 보정과 출력 허용 조건. armed 상태여도 servo_enabled=false일 수 있다.
    pub cfg:ActuatorConfig,
    current:[u16;6],start:[u16;6],target:[u16;6],started:u64,duration:u64,
    pose_seq:Option<u32>,pose_mask:u8,pose_kind:u8,pca_ready:bool,
    light:Option<([u8;3],u8,u16)>,light_seq:Option<u32>,
    eyes:Option<([u8;8],[u8;8],u8,u32)>,
    generation:u32,applied:u32,
    arm_patterns:ArmPatterns,arm_cfg:ActuatorConfig,
}
impl Application {
    /// Arm 설정과 마지막 명령각으로 출력 상태를 만든다. PWM은 시작하지 않는다.
    pub fn new(cfg:ActuatorConfig,current:[u16;6])->Self{Self{current,start:current,target:current,cfg,started:0,duration:1,pose_seq:None,pose_mask:0,pose_kind:1,pca_ready:false,light:None,light_seq:None,eyes:None,generation:GENERATION.load(Ordering::SeqCst),applied:0,arm_patterns:ArmPatterns::new(Instant::now().as_micros()),arm_cfg:cfg}}
    /// 명령 기준의 출력 상태를 반환한다. 실제 각도나 전압을 읽지 않는다.
    pub fn status(&self)->OutputStatus {OutputStatus{armed:true,calibration_id:self.cfg.calibration_id,commanded_cdeg:self.current,pose_active:self.pose_seq.is_some()||self.arm_patterns.active(),light_active:self.light.is_some(),applied_seq:self.applied}}
    /// 지정된 축의 기준각만 복원한다. 실제 출력은 하지 않는다.
    pub fn seed(&mut self,positions:[Option<u16>;6]){for i in 0..6{if let Some(value)=positions[i]{self.current[i]=value;}}}
    /// 호스트 서보 소유권과 포즈 이동이 없을 때 SW4 팔 동작을 선택한다.
    pub fn arm_pattern(&mut self,config:&DeviceConfig,entropy:u32)->bool{
        // A host servo Arm owns the motors until an acknowledged Stop.
        if self.cfg.servo_enabled||self.pose_seq.is_some(){return false;}
        let local=ActuatorConfig{calibration_id:20261025,min_cdeg:[0;6],max_cdeg:[18000;6],neutral_cdeg:self.current,
            min_us:[config.servo_min_us;6],max_us:[config.servo_max_us;6],invert_mask:0,
            max_speed_cdeg_s:MAX_SPEED_CDEG_S,servo_enabled:true,matrix_installed:self.cfg.matrix_installed};
        if !local.validate(){return false;}
        self.arm_cfg=local;
        self.arm_patterns.select(self.current,entropy,Instant::now().as_millis());true
    }
    /// 전체 목표를 검사하고 이동을 설정한다. 속도 제한에 따라 시간을 늘릴 수 있다.
    pub fn pose(&mut self,target:[u16;6],ms:u16,seq:u32)->bool{
        if !self.cfg.accepts(&target,ms){return false;}
        self.pose_mask=0x3f;self.pose_kind=1;
        self.start=self.current;self.target=target;self.started=Instant::now().as_millis();
        let distance=(0..6).map(|i|self.current[i].abs_diff(target[i])as u64).max().unwrap_or(0);
        self.duration=(ms as u64).max(distance*1000/self.cfg.max_speed_cdeg_s as u64).max(1);self.pose_seq=Some(seq);true
    }
    /// 기존 이동이 없으면 한 축의 목표와 mask를 설정한다. angle은 centidegree다.
    pub fn servo(&mut self,channel:u8,angle:u16,ms:u16,seq:u32)->bool{
        let Some((target,mask))=pico2_device_bench::servo_target(&self.cfg,self.current,channel,angle,ms) else{return false;};
        // A second channel is never queued behind an unfinished first motion.
        if self.pose_seq.is_some(){return false;}
        self.start=self.current;self.target=target;self.pose_mask=mask;self.pose_kind=4;
        self.started=Instant::now().as_millis();
        let distance=self.current[channel as usize].abs_diff(angle)as u64;
        self.duration=(ms as u64).max(distance*1000/self.cfg.max_speed_cdeg_s as u64).max(1);
        self.pose_seq=Some(seq);true
    }
    /// 고정 또는 삼각파 조명 목표를 설정한다. period=0은 고정, 그 외 단위는 ms다.
    pub fn light(&mut self,rgb:[u8;3],brightness:u8,period:u16,seq:u32)->bool{
        if brightness>64||(period!=0&&!(200..=10000).contains(&period)){return false;}
        self.light=Some((rgb,brightness,period));self.light_seq=Some(seq);true
    }
    /// SW3 등에 조명 소유권을 넘기기 위해 일반 조명 목표를 지운다.
    pub fn clear_light(&mut self){self.light=None;self.light_seq=None;}
    /// 한 번 적용할 논리 좌우 눈 프레임을 저장한다. 설치 설정이 필요하다.
    pub fn eyes(&mut self,left:[u8;8],right:[u8;8],brightness:u8,seq:u32)->bool{if !self.cfg.matrix_installed||brightness>15{return false;}self.eyes=Some((left,right,brightness,seq));true}
    fn valid(&self)->bool{run_valid(self.generation)}
    /// 포즈·SW4·조명·눈을 적용한다. 호스트 포즈·단일 서보·조명·눈 명령에 Applied를 보낸다.
    /// SW4 로컬 패턴은 완료 후 PWM을 끄며 별도의 Applied를 보내지 않는다.
    ///
    /// await 전후에 Stop·generation·lease를 재검사한다. 오류값은 fault 비트이며
    /// 취소는 0일 수 있다. 호출자가 정지 경로와 하드웨어 정리를 이어서 수행한다.
    pub async fn tick(&mut self,d:&mut Devices,config:&DeviceConfig)->Result<(),u32>{
        if !self.valid(){d.oe.set_high();return Err(0);}
        if self.pose_seq.is_some(){
            if !self.pca_ready{d.oe.set_high();d.pca.init().await.map_err(|_|PCA_FAULT)?;self.pca_ready=true;}
            let elapsed=Instant::now().as_millis().saturating_sub(self.started).min(self.duration);
            let pose=pico2_device_bench::interpolate_pose(self.start,self.target,elapsed,self.duration);
            for i in 0..6{
                if self.pose_mask&(1<<i)==0{continue;}
                let next=pose[i];
                if !self.valid(){d.oe.set_high();return Err(0);}
                d.pca.pulse(i as u8,self.cfg.ticks(i,next as u16)).await.map_err(|_|PCA_FAULT)?;self.current[i]=next as u16;d.last_commanded[i]=next;d.known_positions|=1<<i;
            }
            if !self.valid(){d.oe.set_high();return Err(0);}d.oe.set_low();
            if elapsed==self.duration{let seq=self.pose_seq.take().unwrap();self.applied=seq;event(Message::Applied{request_seq:seq,kind:self.pose_kind});}
        }
        if self.arm_patterns.active(){
            if !self.pca_ready{d.oe.set_high();d.pca.init().await.map_err(|_|PCA_FAULT)?;self.pca_ready=true;}
            let time=Instant::now().as_millis();let pose=self.arm_patterns.sample(time);
            for i in 0..4{
                if !self.valid(){d.oe.set_high();return Err(0);}
                d.pca.pulse(i as u8,self.arm_cfg.ticks(i,pose[i])).await.map_err(|_|PCA_FAULT)?;
                self.current[i]=pose[i];d.last_commanded[i]=pose[i];
            }
            if !self.valid(){d.oe.set_high();return Err(0);}d.oe.set_low();
            if self.arm_patterns.finished(time){
                // Finite gesture: return to its center, then release only these PWM channels.
                for i in 0..4{
                    if !self.valid(){d.oe.set_high();return Err(0);}
                    d.pca.off(i).await.map_err(|_|PCA_FAULT)?;
                }
                d.oe.set_high();self.arm_patterns.clear();
            }
        }
        if let Some((rgb,brightness,period))=self.light {
            let scale=if period==0{brightness as u32}else{let t=(Instant::now().as_millis()%period as u64)as u32;let half=period as u32/2;brightness as u32*(if t<half{t}else{period as u32-t})/half.max(1)};
            let color=rgb.map(|v|(v as u32*scale/255)as u8);let mut left=[[0;3];CAPACITY];let mut right=left;
            for p in &mut left[..config.left_total().min(CAPACITY)]{*p=color;}for p in &mut right[..config.right_total().min(CAPACITY)]{*p=color;}
            if !self.valid(){return Err(0);}d.neo(Module::NeoLeft,left).await;if !self.valid(){return Err(0);}d.neo(Module::NeoRight,right).await;
            if let Some(seq)=self.light_seq.take(){self.applied=seq;event(Message::Applied{request_seq:seq,kind:2});}
        }
        if let Some((left,right,b,seq))=self.eyes.take(){
            if !self.valid(){return Err(0);}d.matrix.init().map_err(|_|MATRIX_FAULT)?;d.matrix.reg(0xa,b,b).map_err(|_|MATRIX_FAULT)?;d.matrix.frame(MatrixFrame{left,right}).map_err(|_|MATRIX_FAULT)?;d.matrix.enable().map_err(|_|MATRIX_FAULT)?;self.applied=seq;event(Message::Applied{request_seq:seq,kind:3});
        }
        Ok(())
    }
}
