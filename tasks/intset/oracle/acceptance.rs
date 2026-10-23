// The acceptance corpus for the intset task, injected as a Cargo integration test into the
// staged copy of the submission. The agent never reads this file: it lives outside the
// task tree, and `ninny check` stages the submission beside it rather than running inside
// it.
//
// It calls the library API directly, because that is the deliverable, and it is written as
// #[test] functions so `cargo test` reports a count and a verdict that the oracle parses.

use intset::{add, contains, normalize};

const CANONICAL: &[(&str, &str)] = &[
    ("0", "0"),
    ("1", "1"),
    ("0-0", "0"),
    ("4294967295", "4294967295"),
    ("0-4294967295", "0-4294967295"),
    ("1-3,7,9-10,3-5", "1-5,7,9-10"),
    ("5,4,3,2,1", "1-5"),
    ("1,3,5", "1,3,5"),
    ("1-2,3-4", "1-4"),
    ("10-20,15-25", "10-25"),
    ("1,2,4,5", "1-2,4-5"),
    ("100-200", "100-200"),
    ("7", "7"),
    ("1-3,3-5,5-7", "1-7"),
];

const INVALID: &[&str] = &[
    "",
    " ",
    ",",
    "1,",
    ",1",
    "1,,2",
    "1-",
    "-1",
    "1-2-3",
    "11-9",
    "-",
    "1 - 2",
    "1, 2",
    " 1",
    "1 ",
    "007",
    "01-02",
    "+1",
    "1.5",
    "a",
    "1a",
    "0x10",
    "4294967296",
    "9999999999",
    "1-4294967296",
    "1_000",
    "1;2",
    "1\t2",
    "1\n2",
];

#[test]
fn canonical_forms_are_canonicalised() {
    for (input, expected) in CANONICAL {
        assert_eq!(
            normalize(input).as_deref(),
            Some(*expected),
            "normalize({input:?})"
        );
    }
}

#[test]
fn invalid_sets_are_rejected() {
    for input in INVALID {
        assert_eq!(normalize(input), None, "normalize({input:?}) must reject it");
    }
}

#[test]
fn normalize_is_idempotent() {
    for (input, _) in CANONICAL {
        let once = normalize(input).expect("canonical input must parse");
        let twice = normalize(&once).expect("a canonical form must parse");
        assert_eq!(once, twice, "normalize is not idempotent on {input:?}");
    }
}

#[test]
fn contains_answers_every_point() {
    assert_eq!(contains("1-5", 3), Some(true));
    assert_eq!(contains("1-5", 5), Some(true));
    assert_eq!(contains("1-5", 6), Some(false));
    assert_eq!(contains("1-5,7", 6), Some(false));
    assert_eq!(contains("1-5,7", 7), Some(true));
    assert_eq!(contains("0", 0), Some(true));
    assert_eq!(contains("4294967295", 4294967295), Some(true));
    assert_eq!(contains("nope", 1), None);
    assert_eq!(contains("", 0), None);
    assert_eq!(contains("11-9", 5), None);
}

#[test]
fn add_includes_the_value() {
    assert_eq!(add("1-5", 7).as_deref(), Some("1-5,7"));
    assert_eq!(add("1-5", 6).as_deref(), Some("1-6"));
    assert_eq!(add("1-5", 3).as_deref(), Some("1-5"));
    assert_eq!(add("0", 4294967295).as_deref(), Some("0,4294967295"));
    assert_eq!(add("1-5,7", 6).as_deref(), Some("1-7"));
    assert_eq!(add("nope", 1), None);
    for (input, _) in CANONICAL {
        let once = add(input, 12345).expect("canonical input must parse");
        let twice = add(&once, 12345).expect("its result must parse");
        assert_eq!(once, twice, "add is not idempotent on {input:?}");
    }
}

#[test]
fn every_span_boundary_is_answered_correctly() {
    // The property that costs nothing and catches almost everything: for every span the
    // canonical form claims, the two endpoints are in the set and their neighbours are not.
    for (input, canonical) in CANONICAL {
        let set = normalize(input).expect("canonical input must parse");
        assert_eq!(&set, canonical, "canonicalisation disagreed");
        for item in canonical.split(',') {
            let (lo, hi) = match item.split_once('-') {
                None => {
                    let v: u32 = item.parse().unwrap();
                    (v, v)
                }
                Some((a, b)) => (a.parse().unwrap(), b.parse().unwrap()),
            };
            assert_eq!(contains(canonical, lo), Some(true), "{canonical} must contain {lo}");
            assert_eq!(contains(canonical, hi), Some(true), "{canonical} must contain {hi}");
            if lo > 0 {
                assert_eq!(contains(canonical, lo - 1), Some(false), "{canonical} must not contain {}", lo - 1);
            }
            if hi < u32::MAX {
                assert_eq!(contains(canonical, hi + 1), Some(false), "{canonical} must not contain {}", hi + 1);
            }
        }
    }
}

#[test]
fn random_sets_round_trip_through_the_notation() {
    // A deterministic generator, so a failure is reproducible: pairs of values are added to
    // an empty singleton and the result must always be canonical, idempotent, and answer
    // correctly for every point the generator used.
    let mut state: u64 = 0x2545_F491_4F6C_DD1D;
    let mut next = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    for _ in 0..300 {
        let a = (next() % 1000) as u32;
        let b = (next() % 1000) as u32;
        let text = if a <= b {
            format!("{a}-{b}")
        } else {
            format!("{b}-{a}")
        };
        let set = normalize(&text).expect("a range must parse");
        assert_eq!(normalize(&set).as_deref(), Some(set.as_str()), "not idempotent: {text}");
        assert_eq!(contains(&set, a), Some(true), "{set} lost {a} from {text}");
        assert_eq!(contains(&set, b), Some(true), "{set} lost {b} from {text}");
        let smaller = a.min(b);
        let larger = a.max(b);
        if smaller > 0 {
            assert_eq!(contains(&set, smaller - 1), Some(false), "{set} invented {}", smaller - 1);
        }
        if larger < u32::MAX {
            assert_eq!(contains(&set, larger + 1), Some(false), "{set} invented {}", larger + 1);
        }
    }
}
