// A reference implementation of the intset task -- the answer key.
//
// It exists for one reason: to prove the acceptance corpus can pass. An oracle that only
// ever fails is not evidence of anything, so this is the positive control that
// `ninny verify-task` runs the corpus against.
use std::fmt;

/// An inclusive set of non-negative integers, kept in canonical order: ascending, with
/// overlapping and touching spans merged.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct IntSet {
    pub spans: Vec<(u32, u32)>,
}

/// A decimal value with no sign, no space and no leading zero.
fn value(text: &str) -> Option<u32> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if text.len() > 1 && text.starts_with('0') {
        return None;
    }
    text.parse::<u32>().ok()
}

fn merged(mut spans: Vec<(u32, u32)>) -> Vec<(u32, u32)> {
    spans.sort_unstable();
    let mut out: Vec<(u32, u32)> = Vec::with_capacity(spans.len());
    for (lo, hi) in spans {
        match out.last_mut() {
            // Touching counts as overlapping: 1-2 and 3-4 are 1-4. saturating_add keeps
            // this correct at u32::MAX instead of wrapping to zero.
            Some(last) if lo <= last.1.saturating_add(1) => {
                if hi > last.1 {
                    last.1 = hi;
                }
            }
            _ => out.push((lo, hi)),
        }
    }
    out
}

impl IntSet {
    /// Parse the notation, or `None` when it is not a set at all.
    pub fn parse(text: &str) -> Option<IntSet> {
        if text.is_empty() {
            return None;
        }
        let mut spans = Vec::new();
        for item in text.split(',') {
            let span = match item.split_once('-') {
                None => {
                    let only = value(item)?;
                    (only, only)
                }
                Some((low, high)) => {
                    let low = value(low)?;
                    let high = value(high)?;
                    if low > high {
                        return None;
                    }
                    (low, high)
                }
            };
            spans.push(span);
        }
        Some(IntSet { spans: merged(spans) })
    }

    /// The canonical text.
    pub fn to_text(&self) -> String {
        let mut parts = Vec::with_capacity(self.spans.len());
        for (lo, hi) in &self.spans {
            if lo == hi {
                parts.push(format!("{lo}"));
            } else {
                parts.push(format!("{lo}-{hi}"));
            }
        }
        parts.join(",")
    }

    pub fn contains(&self, value: u32) -> bool {
        self.spans.iter().any(|&(lo, hi)| value >= lo && value <= hi)
    }

    pub fn with(&self, value: u32) -> IntSet {
        let mut spans = self.spans.clone();
        spans.push((value, value));
        IntSet { spans: merged(spans) }
    }
}

impl fmt::Display for IntSet {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_text())
    }
}

pub fn normalize(text: &str) -> Option<String> {
    IntSet::parse(text).map(|set| set.to_text())
}

pub fn contains(text: &str, value: u32) -> Option<bool> {
    IntSet::parse(text).map(|set| set.contains(value))
}

pub fn add(text: &str, value: u32) -> Option<String> {
    IntSet::parse(text).map(|set| set.with(value).to_text())
}
