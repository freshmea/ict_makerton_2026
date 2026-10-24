use pico_device_protocol::{DeviceConfig, TouchEngine, TouchKind};

// The deployed firmware uses this exact engine. Sound rendering belongs to Jetson;
// do not replace GPIO debounce/counts with browser or host timers.
#[test]
fn all_six_buttons_emit_one_press_then_rising_counts_and_release() {
    for index in 0..6 {
        let config = DeviceConfig { hold_interval_ms: 800, ..DeviceConfig::default() };
        let mut engine = TouchEngine::new(config).unwrap();
        let mask = 1 << index;
        assert!(engine.sample(mask, 0).is_empty());
        assert!(engine.sample(mask, 29).is_empty());
        let pressed = engine.sample(mask, 30);
        assert_eq!(pressed.len(), 1);
        assert_eq!(pressed[0].index, index + 1);
        assert_eq!(pressed[0].kind, TouchKind::Pressed);
        assert_eq!(pressed[0].interval_count, 0);
        let mut previous_seq = pressed[0].event_seq;
        assert!(engine.sample(mask, 829).is_empty());
        for count in 1..=12 {
            let events = engine.sample(mask, 30 + count as u64 * 800);
            let interval = events.iter().find(|e| e.kind == TouchKind::Interval).unwrap();
            assert_eq!(interval.interval_count, count);
            assert_eq!(interval.index, index + 1);
            assert!(interval.pressed);
            assert!(interval.event_seq > previous_seq);
            previous_seq = interval.event_seq;
        }
        engine.sample(0, 9650);
        let released = engine.sample(0, 9680);
        assert_eq!(released[0].kind, TouchKind::Released);
        assert_eq!(released[0].interval_count, 12);
        assert!(engine.sample(0, 10100).iter().all(|e| e.kind != TouchKind::Interval));
    }
}
