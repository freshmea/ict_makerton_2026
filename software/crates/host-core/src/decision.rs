//! Provider-independent policy gate. A model answer is evidence, never a device command.
use serde::{Deserialize, Serialize};
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Wait,
    Clarify,
    OfferHint,
    EndSession,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Decision {
    pub epoch: u64,
    pub observed_ms: u64,
    pub action: Action,
    pub confidence: f64,
}
pub fn permit(
    answer: &Decision,
    epoch: u64,
    now: u64,
    help_requested: bool,
    stopped: bool,
) -> Action {
    if stopped
        || !help_requested
        || answer.epoch != epoch
        || answer.observed_ms > now
        || now - answer.observed_ms > 2000
    {
        return Action::Wait;
    }
    if !answer.confidence.is_finite()
        || !(0.0..=1.0).contains(&answer.confidence)
        || answer.confidence < 0.85
    {
        return Action::Clarify;
    }
    answer.action
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn synthetic_200_candidates_never_bypass_local_stop_epoch_or_consent() {
        let mut n = 0;
        for line in include_str!("../../../tests/decision-candidates.jsonl").lines() {
            let v: serde_json::Value = serde_json::from_str(line).unwrap();
            let a = serde_json::from_value(v["expected"].clone()).unwrap();
            let d = Decision {
                epoch: 1,
                observed_ms: 100,
                action: a,
                confidence: 0.99,
            };
            assert_eq!(permit(&d, 1, 101, false, false), Action::Wait);
            assert_eq!(permit(&d, 1, 101, true, true), Action::Wait);
            assert_eq!(permit(&d, 2, 101, true, false), Action::Wait);
            n += 1;
        }
        assert_eq!(n, 200);
    }
    #[test]
    fn model_never_overrides_stop_quiet_or_epoch() {
        let d = Decision {
            epoch: 2,
            observed_ms: 100,
            action: Action::OfferHint,
            confidence: 0.99,
        };
        assert_eq!(permit(&d, 2, 101, true, true), Action::Wait);
        assert_eq!(permit(&d, 2, 101, false, false), Action::Wait);
        assert_eq!(permit(&d, 3, 101, true, false), Action::Wait);
        assert_eq!(permit(&d, 2, 2200, true, false), Action::Wait);
        assert_eq!(permit(&d, 2, 101, true, false), Action::OfferHint);
    }
    #[test]
    fn uncertainty_is_not_an_action_permission() {
        let mut d = Decision {
            epoch: 1,
            observed_ms: 10,
            action: Action::OfferHint,
            confidence: 0.5,
        };
        assert_eq!(permit(&d, 1, 11, true, false), Action::Clarify);
        d.confidence = f64::NAN;
        assert_eq!(permit(&d, 1, 11, true, false), Action::Clarify);
        assert!(serde_json::from_str::<Decision>(
            r#"{"epoch":1,"observed_ms":10,"action":"servo","confidence":1}"#
        )
        .is_err());
    }
}
