use pico_device_protocol::*;

#[test]
fn appended_servo_messages_round_trip_without_changing_hello_wire_tag() {
    for body in [Message::SeedServoPositions{positions_cdeg:[Some(2800),Some(6500),Some(10600),Some(7700),None,None]},Message::SetServo{channel:5,target_cdeg:18000,move_ms:6000},
                 Message::Capabilities{single_servo:true},Message::CheckServoDriver,
                 Message::ServoDriver(ServoDriverStatus{selected_address:0x40,probes:[1,2],
                     sda_high:true,scl_high:true,initialized:true,last_error:0})] {
        let frame=Frame{version:VERSION,session:42,seq:10,body};
        let mut bytes=[0u8;MAX_WIRE];let len=encode_frame(&frame,&mut bytes).unwrap();
        let mut decoder=FrameDecoder::new();let mut found=None;
        for byte in &bytes[..len] {if let Some(value)=decoder.push(*byte){found=Some(value.unwrap());}}
        assert_eq!(found,Some(frame));
    }
}
