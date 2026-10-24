use pico_device_protocol::*;

fn hello() -> Frame { Frame { version: VERSION, session: 0, seq: 0, body: Message::Hello } }
fn wire(frame: &Frame) -> Vec<u8> {
    let mut bytes = [0; MAX_WIRE];
    let len = encode_frame(frame, &mut bytes).unwrap();
    bytes[..len].to_vec()
}
fn decode(bytes: &[u8]) -> Vec<Result<Frame, CodecError>> {
    let mut decoder = FrameDecoder::new();
    bytes.iter().filter_map(|byte| decoder.push(*byte)).collect()
}

#[test]
fn crc_standard_check_and_external_golden_hello() {
    assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
    assert_eq!(crc32(b""), 0);
    // Independently computed with Python zlib.crc32 over Postcard [2,0,0,0].
    let golden = [2, 2, 1, 1, 5, 0x97, 0x17, 0x4d, 0x8b, 0];
    assert_eq!(wire(&hello()), golden);
    assert_eq!(decode(&golden), vec![Ok(hello())]);
}
#[test]
fn actuator_configuration_bounds_and_new_frames(){
    let mut c=ActuatorConfig::default();assert!(c.validate());assert!(!c.accepts(&[9000;6],500));
    c.servo_enabled=true;assert!(c.accepts(&[9000;6],500));assert!(!c.accepts(&[11000;6],500));
    assert_eq!(c.ticks(0,9000),307);c.invert_mask=1;assert_eq!(c.ticks(0,0),410);
    let f=Frame{version:VERSION,session:u64::MAX,seq:u32::MAX,body:Message::Arm(c)};assert_eq!(decode(&wire(&f)),vec![Ok(f)]);
    c.min_cdeg[0]=18001;assert!(!c.validate());
}

#[test]
fn fragments_concatenated_frames_and_empty_delimiters() {
    let mut second = hello();
    second.session = u64::MAX;
    second.seq = u32::MAX;
    second.body = Message::RunTest(Module::NeoRight);
    let first_wire = wire(&hello());
    let second_wire = wire(&second);
    let mut combined = vec![0, 0];
    combined.extend_from_slice(&first_wire);
    combined.push(0);
    combined.extend_from_slice(&second_wire);
    for chunk_size in 1..=9 {
        let mut decoder = FrameDecoder::new();
        let mut frames = vec![];
        for chunk in combined.chunks(chunk_size) {
            for byte in chunk { if let Some(frame) = decoder.push(*byte) { frames.push(frame); } }
        }
        assert_eq!(frames, vec![Ok(hello()), Ok(second)]);
    }
}

#[test]
fn corrupted_crc_bad_cobs_and_overlong_stream_resynchronize() {
    let good = wire(&hello());
    let mut bad_crc = good.clone();
    bad_crc[8] ^= 1;
    bad_crc.extend_from_slice(&good);
    assert_eq!(decode(&bad_crc), vec![Err(CodecError::BadCrc), Ok(hello())]);
    let mut bad_cobs = vec![5, 1, 0];
    bad_cobs.extend_from_slice(&good);
    assert_eq!(decode(&bad_cobs), vec![Err(CodecError::BadCobs), Ok(hello())]);
    let mut overlong = vec![1; MAX_WIRE + 40];
    overlong.push(0);
    overlong.extend_from_slice(&good);
    assert_eq!(decode(&overlong), vec![Err(CodecError::TooLong), Ok(hello())]);
}

#[test]
fn caller_output_capacity_is_enforced() {
    for capacity in 0..wire(&hello()).len() {
        assert_eq!(encode_frame(&hello(), &mut vec![0; capacity]), Err(CodecError::BufferTooSmall));
    }
}

#[test]
fn maximum_integer_status_fits_decoded_and_wire_limits() {
    let touch = TouchState { pressed: true, held_ms: u32::MAX, interval_count: u32::MAX,
        last_duration_ms: u32::MAX, last_interval_count: u32::MAX,
        press_count: u32::MAX, window_remaining_ms: u32::MAX };
    // Use even policy-invalid maxima: codec capacity must not depend on validation.
    let config = DeviceConfig { left_segments: [u8::MAX; 3], right_segments: [u8::MAX; 3],
        touch_active_low_mask: u8::MAX, local_tests_enabled: true, test_switch: u8::MAX,
        hold_interval_ms: u32::MAX, press_window_ms: u32::MAX,
        servo_min_us: u16::MAX, servo_max_us: u16::MAX, test_span_degrees: u8::MAX };
    let status = DeviceStatus { uptime_ms: u64::MAX, raw_mask: u8::MAX,
        pressed_mask: u8::MAX, touches: [touch; 6], running: Some(Module::All),
        local_enabled: true, oe_high: true, faults: u32::MAX, dropped_events: u32::MAX, config };
    let frame = Frame { version: u8::MAX, session: u64::MAX, seq: u32::MAX, body: Message::Status(status) };
    let mut payload = [0; MAX_DECODED];
    let payload_len = postcard::to_slice(&frame, &mut payload).unwrap().len();
    assert!(payload_len + 4 <= MAX_DECODED);
    let encoded = wire(&frame);
    assert!(encoded.len() <= MAX_WIRE);
    assert_eq!(decode(&encoded), vec![Ok(frame)]);
    println!("worst_status_postcard_bytes={payload_len} decoded_with_crc={} wire_bytes={}", payload_len + 4, encoded.len());
}

#[test]
fn configuration_limits_cover_topology_and_runtime_bounds() {
    let config = DeviceConfig::default();
    assert_eq!(config.left_total(), 18);
    assert_eq!(config.right_total(), 18);
    assert!(config.validate().is_ok());
    assert_eq!(config.test_switch, 6);
    assert!(config.local_tests_enabled);
    assert!(DeviceConfig { left_segments: [36, 0, 0], right_segments: [0, 0, 36], test_switch: 0, ..config }.validate().is_ok());
    for invalid in [
        DeviceConfig { left_segments: [0; 3], ..config },
        DeviceConfig { right_segments: [37, 0, 0], ..config },
        DeviceConfig { touch_active_low_mask: 0x40, ..config },
        DeviceConfig { test_switch: 7, ..config },
        DeviceConfig { hold_interval_ms: 99, ..config },
        DeviceConfig { press_window_ms: 60_001, ..config },
        DeviceConfig { servo_min_us: 2000, servo_max_us: 1000, ..config },
        DeviceConfig { servo_min_us: 499, ..config },
        DeviceConfig { servo_max_us: 2501, ..config },
        DeviceConfig { test_span_degrees: 0, ..config },
        DeviceConfig { test_span_degrees: 31, ..config },
    ] { assert!(invalid.validate().is_err()); }
}

#[test]
fn debounce_requires_thirty_ms_and_release_preserves_final_duration() {
    let mut engine = TouchEngine::new(DeviceConfig::default()).unwrap();
    assert!(engine.sample(1, 0).is_empty());
    assert!(engine.sample(0, 5).is_empty());
    assert!(engine.sample(1, 10).is_empty());
    assert!(engine.sample(1, 39).is_empty());
    let pressed = engine.sample(1, 40);
    assert_eq!(pressed.len(), 1);
    assert_eq!(pressed[0].kind, TouchKind::Pressed);
    assert_eq!(pressed[0].index, 1);
    assert_eq!(pressed[0].press_count, 1);
    assert!(engine.sample(1, 539).is_empty());
    let interval = engine.sample(1, 540);
    assert_eq!(interval[0].kind, TouchKind::Interval);
    assert_eq!(interval[0].duration_ms, 500);
    assert_eq!(interval[0].interval_count, 1);
    assert!(engine.sample(0, 610).is_empty());
    let released = engine.sample(0, 640);
    assert_eq!(released[0].kind, TouchKind::Released);
    assert!(!released[0].pressed);
    assert_eq!(released[0].duration_ms, 600);
    assert_eq!(released[0].interval_count, 1);
    let state = engine.states(700)[0];
    assert!(!state.pressed);
    assert_eq!(state.held_ms, 0);
    assert_eq!(state.interval_count, 0);
    assert_eq!(state.last_duration_ms, 600);
    assert_eq!(state.last_interval_count, 1);
}

#[test]
fn fixed_first_press_window_counts_edges_not_hold_intervals() {
    let mut engine = TouchEngine::new(DeviceConfig::default()).unwrap();
    engine.sample(1, 0);
    engine.sample(1, 30);
    engine.sample(0, 40);
    engine.sample(0, 70);
    engine.sample(1, 100);
    assert_eq!(engine.sample(1, 130)[0].press_count, 2);
    engine.sample(0, 140);
    engine.sample(0, 170);
    // Debounced third press occurs exactly at first window's end, 30+2000.
    engine.sample(1, 2000);
    assert!(engine.sample(1, 2029).is_empty());
    let boundary = engine.sample(1, 2030);
    assert_eq!(boundary.len(), 2);
    assert_eq!(boundary[0].kind, TouchKind::WindowClosed);
    assert_eq!(boundary[0].press_count, 2);
    assert_eq!(boundary[1].kind, TouchKind::Pressed);
    assert_eq!(boundary[1].press_count, 1);
    assert_eq!(engine.states(2030)[0].window_remaining_ms, 2000);
}

#[test]
fn long_hold_does_not_wrap_at_original_uint8_limit() {
    let mut engine = TouchEngine::new(DeviceConfig::default()).unwrap();
    engine.sample(1, 0);
    engine.sample(1, 30);
    let events = engine.sample(1, 128_030);
    assert!(events.iter().any(|event| event.kind == TouchKind::Interval && event.interval_count == 256));
    assert!(engine.sample(1, 128_035).is_empty());
    let events = engine.sample(1, u64::MAX);
    assert_eq!(events.last().unwrap().interval_count, u32::MAX);
    assert_eq!(events.last().unwrap().duration_ms, u32::MAX);
    assert!(engine.sample(1, u64::MAX).is_empty());
}

#[test]
fn six_active_low_inputs_and_reconfiguration_remain_bounded() {
    let config = DeviceConfig { touch_active_low_mask: 0x3f, ..DeviceConfig::default() };
    let mut engine = TouchEngine::new(config).unwrap();
    engine.sample(0, 0);
    let pressed = engine.sample(0, 30);
    assert_eq!(pressed.len(), 6);
    assert_eq!(engine.raw_mask(), 0);
    assert_eq!(engine.pressed_mask(), 0x3f);
    let boundary = engine.sample(0, 2030);
    assert_eq!(boundary.len(), 12);
    assert!(boundary.len() <= 24);
    let invalid = DeviceConfig { hold_interval_ms: 0, ..config };
    assert!(engine.configure(invalid, 2030).is_err());
    assert_eq!(engine.pressed_mask(), 0x3f);
    engine.configure(DeviceConfig::default(), 2030).unwrap();
    assert_eq!(engine.pressed_mask(), 0);
    assert_eq!(engine.states(2030), [TouchState::default(); 6]);
    engine.sample(1, 2040);
    let next = engine.sample(1, 2070);
    assert!(next[0].event_seq > boundary.last().unwrap().event_seq);
}
