// Implement this file.
//
// Cargo.toml, src/main.rs and everything in tools/ are frozen. Everything you write goes
// here and in tests/own/.
//
// This file compiles as it stands -- a stub that builds, not a build error -- so your first
// own-test run is a test that ran and failed, which is what a RED observation is supposed
// to be.
use std::fmt;

/// An inclusive set of non-negative integers.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct IntSet {
    pub spans: Vec<(u32, u32)>,
}

impl IntSet {
    /// Parse the canonical-or-not notation, or `None` when it is not a set at all.
    pub fn parse(_text: &str) -> Option<IntSet> {
        None
    }

    /// The canonical text: ascending, merged, single values printed bare.
    pub fn to_text(&self) -> String {
        String::new()
    }

    /// Whether `value` is in the set.
    pub fn contains(&self, _value: u32) -> bool {
        false
    }

    /// This set with `value` included.
    pub fn with(&self, _value: u32) -> IntSet {
        self.clone()
    }
}

impl fmt::Display for IntSet {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.to_text())
    }
}

/// The canonical form of `text`, or `None` when `text` is not a set.
pub fn normalize(_text: &str) -> Option<String> {
    None
}

/// Whether `text` contains `value`, or `None` when `text` is not a set.
pub fn contains(_text: &str, _value: u32) -> Option<bool> {
    None
}

/// The canonical form of `text` with `value` added, or `None` when `text` is not a set.
pub fn add(_text: &str, _value: u32) -> Option<String> {
    None
}
