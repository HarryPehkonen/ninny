// The acceptance corpus for the jsonptr task.
//
// It lives OUTSIDE the task tree, and `ninny check` stages the submission beside this file rather
// than running inside it, so the agent never reads it.
//
// Three families, and the names say which: `parse:` for decoding a pointer into tokens, `resolve:`
// for walking a document, `cli:` for the frozen command line. The teeth tests attribute a failure
// to a rule by reading those names, so keep them honest.
//
// The families are not equal in what they can prove. Every pointer in RFC 6901 section 5 passes
// against an implementation with the unescaping order backwards -- that is the entire reason this
// task exists -- so the discriminating cases are the ones the specification's own example set does
// not contain, and they are named `parse: trap ...` on purpose.
'use strict';

const { execFileSync } = require('child_process');
const path = require('path');

const TREE = process.env.NINNY_TREE || process.argv[2];
if (!TREE || !require('fs').existsSync(path.join(TREE, 'src', 'pointer.js'))) {
  console.error(`acceptance: no src/pointer.js under ${TREE}`);
  process.exit(2);
}
const { parsePointer, resolve } = require(path.join(TREE, 'src', 'pointer.js'));

let checked = 0;
const failures = [];

function check(name, fn) {
  checked += 1;
  try {
    fn();
  } catch (err) {
    failures.push(`${name} -- ${err.message}`);
  }
}

function eq(actual, expected, what) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${what}: got ${a}, want ${e}`);
}

function cli(args, input) {
  try {
    const out = execFileSync('node', [path.join(TREE, 'src', 'cli.js'), ...args],
      { input: input ?? '', encoding: 'utf8', cwd: TREE, stdio: ['pipe', 'pipe', 'pipe'] });
    return { rc: 0, out };
  } catch (err) {
    return { rc: err.status, out: `${err.stdout || ''}${err.stderr || ''}` };
  }
}

// ---------------------------------------------------------------- decoding
const TOKENS = [
  ['', []],
  ['/', ['']],
  ['//', ['', '']],
  ['/foo', ['foo']],
  ['/foo/0', ['foo', '0']],
  ['/foo/', ['foo', '']],
  ['/ ', [' ']],
  ['/a~1b', ['a/b']],
  ['/m~0n', ['m~n']],
  ['/c%d', ['c%d']],
  ['/i\\j', ['i\\j']],
  ['/☃', ['☃']],
  ['/a/b/c', ['a', 'b', 'c']],
];
for (const [text, tokens] of TOKENS) {
  check(`parse: ${JSON.stringify(text)} decodes to ${JSON.stringify(tokens)}`,
    () => eq(parsePointer(text), tokens, 'tokens'));
}

// The traps. The specification's example set contains no case that separates the two unescaping
// orders, so these are the only pointers that can tell a careful implementation from a hasty one.
const TRAPS = [
  ['/~01', ['~1']],
  ['/~00', ['~0']],
  ['/~10', ['/0']],
  ['/~001', ['~01']],
  ['/~1~0', ['/~']],
  ['/~0~1', ['~/']],
  ['/a%20b', ['a%20b']],          // a pointer is not a URI fragment: no percent-decoding
];
for (const [text, tokens] of TRAPS) {
  check(`parse: trap ${JSON.stringify(text)} decodes to ${JSON.stringify(tokens)}`,
    () => eq(parsePointer(text), tokens, 'tokens'));
}

const BAD = ['foo', '~1', '/a~2b', '/a~', '/a~0~', '/~'];
for (const text of BAD) {
  check(`parse: ${JSON.stringify(text)} is not a well-formed pointer`,
    () => eq(parsePointer(text), null, 'tokens'));
}

// ---------------------------------------------------------------- resolution
const DOC = {
  foo: ['bar', 'baz'],
  '': 0,
  'a/b': 1,
  'c%d': 2,
  'e^f': 3,
  'g|h': 4,
  'i\\j': 5,
  'k"l': 6,
  ' ': 7,
  'm~n': 8,
};

const RFC_EXAMPLES = [
  ['', DOC],
  ['/foo', ['bar', 'baz']],
  ['/foo/0', 'bar'],
  ['/', 0],
  ['/a~1b', 1],
  ['/c%d', 2],
  ['/e^f', 3],
  ['/g|h', 4],
  ['/i\\j', 5],
  ['/k"l', 6],
  ['/ ', 7],
  ['/m~0n', 8],
];
for (const [text, value] of RFC_EXAMPLES) {
  check(`resolve: RFC 6901 section 5, ${JSON.stringify(text)}`,
    () => eq(resolve(DOC, text), { found: true, value }, 'result'));
}

// Keys chosen so each trap token names a member: `~01` -> `~1`, `~00` -> `~0`, `~10` -> `/0`.
const FOUND = [
  ['/~01', 9, { '~1': 9, '~0': 10, '/0': 11 }],
  ['/~00', 10, { '~1': 9, '~0': 10, '/0': 11 }],
  ['/~10', 11, { '~1': 9, '~0': 10, '/0': 11 }],
];
for (const [text, value, doc] of FOUND) {
  check(`resolve: trap ${JSON.stringify(text)} finds the member it names`,
    () => eq(resolve(doc, text), { found: true, value }, 'result'));
}

const ARRAY_DOC = { a: ['x', 'y', 'z'], s: 'abc', n: 7, t: true, nil: null, o: { k: 1 } };
const NOT_FOUND = [
  ['/a/3', 'an index past the end'],
  ['/a/01', 'a leading zero is not an index'],
  ['/a/00', 'a leading zero is not an index'],
  ['/a/-', '`-` is the element after the last one, which does not exist'],
  ['/a/1e1', 'not digits'],
  ['/a/ 1', 'not digits'],
  ['/a/+1', 'not digits'],
  ['/a/length', "an array has no member called length"],
  ['/s/0', 'a pointer does not walk into a string'],
  ['/s/length', 'nor into anything else a string carries'],
  ['/n/x', 'a number has no members'],
  ['/t/x', 'a boolean has no members'],
  ['/nil/x', 'null has no members'],
  ['/o/toString', 'own members only'],
  ['/o/missing', 'absent member'],
  ['/missing/deep', 'absent member'],
  ['/a/0/deeper', 'walking into a string element'],
  ['/~01', 'a pointer that is not well-formed resolves to nothing'],
  ['/a~', 'a bad escape resolves to nothing'],
];
for (const [text, why] of NOT_FOUND) {
  check(`resolve: ${JSON.stringify(text)} resolves to nothing (${why})`,
    () => eq(resolve(ARRAY_DOC, text), { found: false }, 'result'));
}

// A round trip over keys that carry the two characters the escape covers, plus the keys where the
// two unescaping orders disagree. The oracle escapes; the submission must decode.
const escapeToken = (key) => key.replace(/~/g, '~0').replace(/\//g, '~1');
const KEYS = ['plain', 'a/b', 'm~n', '~', '/', '~1', '~0', '~01', 'a~1b', '', ' ', '☃', 'a%b'];
const KEY_DOC = {};
KEYS.forEach((key, i) => { KEY_DOC[key] = i; });
for (const key of KEYS) {
  const pointer = `/${escapeToken(key)}`;
  check(`resolve: round trip through ${JSON.stringify(pointer)} finds ${JSON.stringify(key)}`,
    () => eq(resolve(KEY_DOC, pointer), { found: true, value: KEY_DOC[key] }, 'result'));
}

// ---------------------------------------------------------------- the command line
const CLI = [
  [['parse', '/a~1b'], '', 0, '"a/b"\n'],
  [['parse', '/~01'], '', 0, '"~1"\n'],
  [['parse', '/foo/0'], '', 0, '"foo"\n"0"\n'],
  [['parse', 'foo'], '', 1, null],
  [['get', '/foo/1'], JSON.stringify(DOC), 0, '"baz"\n'],
  [['get', '/'], JSON.stringify(DOC), 0, '0\n'],
  [['get', '/~01'], JSON.stringify({ '~1': 42 }), 0, '42\n'],
  [['get', '/a/01'], JSON.stringify(ARRAY_DOC), 1, null],
  [['get', '/a/9'], JSON.stringify(ARRAY_DOC), 1, null],
  [['get', 'foo'], JSON.stringify(ARRAY_DOC), 1, null],
  [[], '', 2, null],
  [['nonsense', '/a'], '', 2, null],
];
for (const [args, input, rc, out] of CLI) {
  check(`cli: ${JSON.stringify(args)} exits ${rc}${out ? ` printing ${JSON.stringify(out)}` : ''}`,
    () => {
      const got = cli(args, input);
      if (got.rc !== rc) throw new Error(`exit ${got.rc}, want ${rc}: ${got.out.trim()}`);
      if (out !== null && got.out !== out) {
        throw new Error(`stdout ${JSON.stringify(got.out)}, want ${JSON.stringify(out)}`);
      }
    });
}

// ---------------------------------------------------------------- verdict
const failed = failures.length;
console.log(`ACCEPTANCE: ${checked} tests, ${failed} failed`);
for (const line of failures) console.log(`  FAILED ${line}`);
process.exit(failed === 0 ? 0 : 1);
