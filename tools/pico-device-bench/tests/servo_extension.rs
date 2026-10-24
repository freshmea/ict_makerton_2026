use pico_device_bench::*;
use pico_device_protocol::{Frame,Message,VERSION,MAX_WIRE,encode_frame};
use std::sync::{Arc,atomic::AtomicBool};
use tokio::io::AsyncWriteExt;
use tokio::time::{Instant,Duration};

#[test]
fn servo_ipc_rejects_other_channels_ranges_and_unknown_fields() {
    assert!(parse_ipc(br#"{"cmd":"servo","channel":0,"target_cdeg":18000,"move_ms":6000}"#).is_ok());
    assert!(parse_ipc(br#"{"cmd":"servo","channel":6,"target_cdeg":9000,"move_ms":500}"#).is_err());
    assert!(parse_ipc(br#"{"cmd":"servo","channel":0,"target_cdeg":18001,"move_ms":500}"#).is_err());
    assert!(parse_ipc(br#"{"cmd":"servo","channel":0,"target_cdeg":9000,"move_ms":500,"pin":1}"#).is_err());
}

#[tokio::test]
async fn old_firmware_has_no_servo_capability_until_explicit_device_report() {
    let (stream,mut peer)=tokio::io::duplex(1024);
    let mut link=DeviceLink::new(stream,42,Arc::new(AtomicBool::new(false)),false);
    assert!(!link.supports_single_servo());
    let frame=Frame{version:VERSION,session:42,seq:1,body:Message::Capabilities{single_servo:true}};
    let mut bytes=[0u8;MAX_WIRE];let len=encode_frame(&frame,&mut bytes).unwrap();
    peer.write_all(&bytes[..len]).await.unwrap();
    link.next_frame(Instant::now()+Duration::from_secs(1)).await.unwrap();
    assert!(link.supports_single_servo());
}

#[tokio::test]
async fn servo_driver_diagnostics_survive_the_native_bridge_snapshot() {
    use pico_device_protocol::{DeviceStatus,ServoDriverStatus};
    let (stream,mut peer)=tokio::io::duplex(2048);
    let mut link=DeviceLink::new(stream,42,Arc::new(AtomicBool::new(false)),false);
    for body in [Message::ServoDriver(ServoDriverStatus{selected_address:0,probes:[2,3],
                     sda_high:false,scl_high:true,initialized:false,last_error:0}),
                 Message::Status(DeviceStatus::default())] {
        let frame=Frame{version:VERSION,session:42,seq:1,body};
        let mut bytes=[0u8;MAX_WIRE];let len=encode_frame(&frame,&mut bytes).unwrap();
        peer.write_all(&bytes[..len]).await.unwrap();
        link.next_frame(Instant::now()+Duration::from_secs(1)).await.unwrap();
    }
    let snapshot=link.snapshot_json();
    assert_eq!(snapshot["servo_driver"]["probes"],serde_json::json!([2,3]));
    assert_eq!(snapshot["servo_driver"]["sda_high"],false);
}
