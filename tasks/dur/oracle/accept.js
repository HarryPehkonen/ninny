// The acceptance corpus for the dur task.
//
// It lives OUTSIDE the task tree, and `ninny check` stages the submission beside this file
// rather than running inside it, so the agent never reads it. It requires the submission's
// module directly AND drives the frozen CLI, because the CLI is what a user runs.
//
// Plain Node, no framework: a counter, a check(), and the same verdict lines the other
// corpora print.
'use strict';

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const tree = process.argv[2];
if (!tree) {
  console.error('accept.js: pass the staged tree as the first argument');
  process.exit(2);
}

let checks = 0;
let failures = 0;

function check(ok, message) {
  checks += 1;
  if (!ok) {
    failures += 1;
    console.log(`FAIL ${message}`);
  }
}

function eq(actual, expected, what) {
  check(
    actual === expected,
    `${what}: expected ${JSON.stringify(expected)} got ${JSON.stringify(actual)}`
  );
}

let duration = null;
try {
  duration = require(path.join(tree, 'src', 'duration.js'));
} catch (err) {
  console.log(`FAIL cannot require src/duration.js: ${err.message}`);
  console.log(`\nACCEPTANCE: 1 checked, 1 failed`);
  console.log('ACCEPTANCE FAILED');
  process.exit(1);
}

const parse = duration.parseDuration;
const format = duration.formatDuration;

check(typeof parse === 'function', 'src/duration.js must export a callable parseDuration');
check(typeof format === 'function', 'src/duration.js must export a callable formatDuration');

// --- parse: canonical input ------------------------------------------------------------
const PARSES = [
  ['0s', 0],
  ['1s', 1],
  ['59s', 59],
  ['1m', 60],
  ['1m1s', 61],
  ['59m59s', 3599],
  ['1h', 3600],
  ['1h1m1s', 3661],
  ['23h59m59s', 86399],
  ['1d', 86400],
  ['1d1h1m1s', 90061],
  ['6d23h59m59s', 604799],
  ['1w', 604800],
  ['1w2d3h4m5s', 788645],
  ['1w1d23h59m59s', 777599],
  ['4w', 2419200],
];
for (const [text, seconds] of PARSES) {
  eq(parse(text), seconds, `parseDuration(${JSON.stringify(text)})`);
}

// --- parse: everything that is not a canonical duration ---------------------------------
const REJECTS = [
  '', ' ', '1', 's', 'h', '1x', '1H', '1S', 'H1', '1h30', '30m1', '1.5h', '01h', '1h05m',
  '  1h', '1h  ', '1h ', ' 1h', '-1h', '+1h', '1 h', '1h 30m', '1h-30m', '1hh', '1h1m1',
  'NaN', 'null', 'undefined', '[]',
  // order and repetition
  '1m1h', '1s1m', '1h1h', '1m1m', '1s1s', '1d1w',
  // a segment that carries into the unit above
  '60s', '60m', '24h', '7d', '1h60m', '1h90m', '90m', '100m', '1d24h', '1w7d',
];
for (const text of REJECTS) {
  eq(parse(text), null, `parseDuration(${JSON.stringify(text)}) must reject it`);
}

// --- format: canonical output -----------------------------------------------------------
const FORMATS = [
  [0, '0s'],
  [1, '1s'],
  [59, '59s'],
  [60, '1m'],
  [61, '1m1s'],
  [3599, '59m59s'],
  [3600, '1h'],
  [3661, '1h1m1s'],
  [86399, '23h59m59s'],
  [86400, '1d'],
  [90061, '1d1h1m1s'],
  [604799, '6d23h59m59s'],
  [604800, '1w'],
  [777599, '1w1d23h59m59s'],
  [788645, '1w2d3h4m5s'],
];
for (const [seconds, text] of FORMATS) {
  eq(format(seconds), text, `formatDuration(${seconds})`);
}

// --- format: everything that is not a non-negative integer -------------------------------
for (const bad of [-1, -0.5, 0.5, 1.5, NaN, Infinity, -Infinity, '60', null, undefined, true, {}, []]) {
  eq(format(bad), null, `formatDuration(${JSON.stringify(bad)}) must reject it`);
}

// --- the property: the two agree, everywhere --------------------------------------------
let broken = 0;
let first = '';
for (let n = 0; n <= 200000; n += 1) {
  const text = format(n);
  if (typeof text !== 'string' || parse(text) !== n) {
    broken += 1;
    if (first === '') first = `n=${n} -> ${JSON.stringify(text)} -> ${JSON.stringify(parse(text))}`;
  }
}
for (const [text] of PARSES) {
  const back = format(parse(text));
  if (back !== text) {
    broken += 1;
    if (first === '') first = `parse ${JSON.stringify(text)} -> format -> ${JSON.stringify(back)}`;
  }
}
for (const [seconds, text] of FORMATS) {
  const back = parse(format(seconds));
  if (back !== seconds) {
    broken += 1;
    if (first === '') first = `format ${seconds} -> parse -> ${JSON.stringify(back)}`;
  }
}
check(broken === 0, `the two directions disagree ${broken} times${first ? `, first ${first}` : ''}`);

// --- the CLI, which is what a user runs --------------------------------------------------
const cli = path.join(tree, 'src', 'cli.js');

function runCli(args) {
  const proc = spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8' });
  return { code: proc.status, out: (proc.stdout || '').trim() };
}

for (const [args, code, out] of [
  [['parse', '1h30m'], 0, '5400'],
  [['parse', '0s'], 0, '0'],
  [['parse', '1w2d3h4m5s'], 0, '788645'],
  [['format', '3661'], 0, '1h1m1s'],
  [['format', '0'], 0, '0s'],
  [['parse', '90m'], 1, ''],
  [['parse', '1h'], 0, '3600'],
  [['parse', '1H'], 1, ''],
  [['format', '-1'], 1, ''],
  [['format', '1.5'], 1, ''],
  [['parse'], 2, ''],
  [[], 2, ''],
  [['nonsense', '1h'], 2, ''],
]) {
  const got = runCli(args);
  check(
    got.code === code && got.out === out,
    `cli ${args.join(' ')}: expected exit ${code} stdout ${JSON.stringify(out)} ` +
      `got exit ${got.code} stdout ${JSON.stringify(got.out)}`
  );
}

console.log(`\nACCEPTANCE: ${checks} checked, ${failures} failed`);
if (failures === 0 && checks > 0) {
  console.log('ACCEPTANCE PASSED');
  process.exit(0);
}
console.log('ACCEPTANCE FAILED');
process.exit(1);
