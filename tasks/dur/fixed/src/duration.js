// A reference implementation of the dur task -- the answer key.
//
// It exists for one reason: to prove the acceptance corpus can pass. An oracle that only
// ever fails is not evidence of anything, so this is the positive control that
// `ninny verify-task` runs the corpus against.
'use strict';

// Descending, so one greedy pass per unit yields the canonical form.
const UNITS = [
  ['w', 604800, null],
  ['d', 86400, 7],
  ['h', 3600, 24],
  ['m', 60, 60],
  ['s', 1, 60],
];

const SIZE = new Map(UNITS.map(([unit, size]) => [unit, size]));
const CARRY = new Map(UNITS.map(([unit, , carry]) => [unit, carry]));
const ORDER = UNITS.map(([unit]) => unit);

function formatDuration(seconds) {
  if (typeof seconds !== 'number') return null;
  if (!Number.isInteger(seconds)) return null;
  if (seconds < 0) return null;
  if (!Number.isSafeInteger(seconds)) return null;
  if (seconds === 0) return '0s';

  const parts = [];
  let rest = seconds;
  for (const [unit, size] of UNITS) {
    const count = Math.floor(rest / size);
    rest -= count * size;
    if (count > 0) parts.push(`${count}${unit}`);
  }
  return parts.join('');
}

function parseDuration(text) {
  if (typeof text !== 'string') return null;
  if (text === '0s') return 0;
  // Whole string only, no leading zeros, at least one segment.
  if (!/^(?:[1-9][0-9]*[wdhms])+$/.test(text)) return null;

  const segments = text.match(/[1-9][0-9]*[wdhms]/g);
  const seen = new Set();
  let previous = -1;
  let total = 0;

  for (const segment of segments) {
    const unit = segment.slice(-1);
    const count = Number(segment.slice(0, -1));
    const index = ORDER.indexOf(unit);

    if (seen.has(unit)) return null;          // a unit may appear once
    seen.add(unit);
    if (index <= previous) return null;       // descending, strictly
    previous = index;

    const carry = CARRY.get(unit);
    if (carry !== null && count >= carry) return null;  // would carry into the unit above
    total += count * SIZE.get(unit);
  }
  return total;
}

module.exports = { parseDuration, formatDuration };
