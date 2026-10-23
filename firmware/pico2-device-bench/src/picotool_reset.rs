//! Pico SDK-compatible BOOTSEL reset interface with deferred output cleanup.
//! References (SDK 2.2.0, picotool 2.3.1):
//! https://github.com/raspberrypi/pico-sdk/blob/2.2.0/src/common/pico_usb_reset_interface_headers/include/pico/usb_reset_interface.h
//! https://github.com/raspberrypi/pico-sdk/blob/2.2.0/src/rp2_common/pico_stdio_usb/reset_interface.c
//! https://github.com/raspberrypi/picotool/blob/2.3.1/main.cpp#L9465-L9488

pub const RESET_INTERFACE_SUBCLASS:u8=0;
pub const RESET_INTERFACE_PROTOCOL:u8=1;
pub const RESET_REQUEST_BOOTSEL:u8=1;

/// Same uppercase, leading-zero-padded public-chip-ID serial as the RP2350 ROM.
pub fn chipid_serial(chipid:u64)->[u8;16]{
    let mut out=[b'0';16];
    for(index,byte)in out.iter_mut().enumerate(){
        *byte=b"0123456789ABCDEF"[((chipid>>((15-index)*4))&15)as usize];
    }
    out
}

fn is_bootsel_request(request_type:u8,request:u8,index:u16,interface:u8,length:u16)->bool{
    // picotool uses CLASS | INTERFACE | OUT, i.e. bmRequestType 0x21,
    // even though the advertised interface descriptor is vendor class 0xff.
    request_type==0x21&&request==RESET_REQUEST_BOOTSEL&&index==interface as u16&&length==0
}

#[cfg(target_os="none")]
mod usb{
    use super::*;
    use embassy_usb::{Builder,Handler,control::{OutResponse,Request},driver::Driver,
        msos::{CompatibleIdFeatureDescriptor,PropertyData,RegistryPropertyFeatureDescriptor}};

    pub struct State{interface:u8,request_boot:Option<fn()>}
    impl State{pub const fn new()->Self{Self{interface:u8::MAX,request_boot:None}}}
    impl Handler for State{
        fn control_out(&mut self,req:Request,data:&[u8])->Option<OutResponse>{
            let request_type=((req.direction as u8)<<7)|((req.request_type as u8)<<5)|(req.recipient as u8);
            if is_bootsel_request(request_type,req.request,req.index,self.interface,req.length)&&data.is_empty(){
                // Never reset inside the USB control handler. The callback gates
                // OE and wakes the device loop, which clears outputs first.
                if let Some(request)=self.request_boot{request();}
                return Some(OutResponse::Accepted);
            }
            None
        }
    }
    pub fn register<'d,D:Driver<'d>>(builder:&mut Builder<'d,D>,state:&'d mut State,request_boot:fn()){
        builder.msos_descriptor(0x0603_0000,1);
        {
            let mut function=builder.function(0xff,RESET_INTERFACE_SUBCLASS,RESET_INTERFACE_PROTOCOL);
            {
                let mut interface=function.interface();
                state.interface=u8::from(interface.interface_number());
                interface.alt_setting(0xff,RESET_INTERFACE_SUBCLASS,RESET_INTERFACE_PROTOCOL,None);
            }
            function.msos_feature(CompatibleIdFeatureDescriptor::new("WINUSB",""));
            // Use the Pico SDK reset interface GUID and property spelling.
            function.msos_feature(RegistryPropertyFeatureDescriptor::new("DeviceInterfaceGUID",
                PropertyData::Sz("{bc7398c1-73cd-4cb7-98b8-913a8fca7bf6}")));
        }
        state.request_boot=Some(request_boot);
        builder.handler(state);
    }
}
#[cfg(target_os="none")]
pub use usb::{State,register};

#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn serial_is_rom_compatible_uppercase_and_fixed_width(){
        assert_eq!(&chipid_serial(0xe679675a69c4039b),b"E679675A69C4039B");
        assert_eq!(&chipid_serial(1),b"0000000000000001");
    }
    #[test]
    fn only_exact_picotool_bootsel_control_shape_is_accepted(){
        assert!(is_bootsel_request(0x21,1,2,2,0));
        for input in [(0x41,1,2,0),(0xa1,1,2,0),(0x21,2,2,0),(0x21,1,1,0),(0x21,1,2,1)]{
            assert!(!is_bootsel_request(input.0,input.1,input.2,2,input.3));
        }
    }
}
