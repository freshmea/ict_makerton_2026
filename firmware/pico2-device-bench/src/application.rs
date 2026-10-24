//! Latest target output state; the device task remains the single I2C/PIO owner.
use super::*;
use pico_device_protocol::{ActuatorConfig,OutputStatus};
pub struct Application {
    pub cfg:ActuatorConfig,
    current:[u16;6],start:[u16;6],target:[u16;6],started:u64,duration:u64,
    pose_seq:Option<u32>,pose_mask:u8,pose_kind:u8,pca_ready:bool,
    light:Option<([u8;3],u8,u16)>,light_seq:Option<u32>,
    eyes:Option<([u8;8],[u8;8],u8,u32)>,
    generation:u32,applied:u32,
}
impl Application {
    pub fn new(cfg:ActuatorConfig)->Self{Self{current:cfg.neutral_cdeg,start:cfg.neutral_cdeg,target:cfg.neutral_cdeg,cfg,started:0,duration:1,pose_seq:None,pose_mask:0,pose_kind:1,pca_ready:false,light:None,light_seq:None,eyes:None,generation:GENERATION.load(Ordering::SeqCst),applied:0}}
    pub fn status(&self)->OutputStatus {OutputStatus{armed:true,calibration_id:self.cfg.calibration_id,commanded_cdeg:self.current,pose_active:self.pose_seq.is_some(),light_active:self.light.is_some(),applied_seq:self.applied}}
    pub fn pose(&mut self,target:[u16;6],ms:u16,seq:u32)->bool{
        if !self.cfg.accepts(&target,ms){return false;}
        self.pose_mask=0x3f;self.pose_kind=1;
        self.start=self.current;self.target=target;self.started=Instant::now().as_millis();
        let distance=(0..6).map(|i|self.current[i].abs_diff(target[i])as u64).max().unwrap_or(0);
        self.duration=(ms as u64).max(distance*1000/self.cfg.max_speed_cdeg_s as u64).max(1);self.pose_seq=Some(seq);true
    }
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
    pub fn light(&mut self,rgb:[u8;3],brightness:u8,period:u16,seq:u32)->bool{
        if brightness>64||(period!=0&&!(200..=10000).contains(&period)){return false;}
        self.light=Some((rgb,brightness,period));self.light_seq=Some(seq);true
    }
    pub fn eyes(&mut self,left:[u8;8],right:[u8;8],brightness:u8,seq:u32)->bool{if !self.cfg.matrix_installed||brightness>15{return false;}self.eyes=Some((left,right,brightness,seq));true}
    fn valid(&self)->bool{run_valid(self.generation)}
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
                d.pca.pulse(i as u8,self.cfg.ticks(i,next as u16)).await.map_err(|_|PCA_FAULT)?;self.current[i]=next as u16;
            }
            if !self.valid(){d.oe.set_high();return Err(0);}d.oe.set_low();
            if elapsed==self.duration{let seq=self.pose_seq.take().unwrap();self.applied=seq;event(Message::Applied{request_seq:seq,kind:self.pose_kind});}
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
