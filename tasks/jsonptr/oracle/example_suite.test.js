// The suite a reader who tests what the specification SHOWS would write. It is a control, not an
// example: `tests/test_jsonptr_oracle_has_teeth.py` copies it into a tree and requires that it does
// NOT catch `sabotage/wrong_unescape_order.js`.
//
// That is the claim this task rests on. Every pointer in RFC 6901 section 5 -- which is the table
// SPEC.md prints -- decodes identically whether `~1` is transformed before `~0` or after, so a
// suite built from the examples passes against an implementation with the order backwards. If this
// file ever kills the trap, the task has stopped measuring care and is only measuring whether the
// examples were typed in correctly.
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { parsePointer, resolve } = require('../../src/pointer.js');

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

test('the pointers in the specification resolve to the values it lists', () => {
  assert.deepStrictEqual(resolve(DOC, ''), { found: true, value: DOC });
  assert.deepStrictEqual(resolve(DOC, '/foo'), { found: true, value: ['bar', 'baz'] });
  assert.deepStrictEqual(resolve(DOC, '/foo/0'), { found: true, value: 'bar' });
  assert.deepStrictEqual(resolve(DOC, '/'), { found: true, value: 0 });
  assert.deepStrictEqual(resolve(DOC, '/a~1b'), { found: true, value: 1 });
  assert.deepStrictEqual(resolve(DOC, '/c%d'), { found: true, value: 2 });
  assert.deepStrictEqual(resolve(DOC, '/e^f'), { found: true, value: 3 });
  assert.deepStrictEqual(resolve(DOC, '/g|h'), { found: true, value: 4 });
  assert.deepStrictEqual(resolve(DOC, '/i\\j'), { found: true, value: 5 });
  assert.deepStrictEqual(resolve(DOC, '/k"l'), { found: true, value: 6 });
  assert.deepStrictEqual(resolve(DOC, '/ '), { found: true, value: 7 });
  assert.deepStrictEqual(resolve(DOC, '/m~0n'), { found: true, value: 8 });
});

test('the escapes decode the way the section on decoding says', () => {
  assert.deepStrictEqual(parsePointer('/a~1b'), ['a/b']);
  assert.deepStrictEqual(parsePointer('/m~0n'), ['m~n']);
  assert.deepStrictEqual(parsePointer('/'), ['']);
  assert.deepStrictEqual(parsePointer(''), []);
});

test('a pointer that does not begin with a slash is not a pointer', () => {
  assert.strictEqual(parsePointer('foo'), null);
});

test('walking off the document resolves to nothing', () => {
  assert.deepStrictEqual(resolve(DOC, '/foo/2'), { found: false });
  assert.deepStrictEqual(resolve(DOC, '/nope'), { found: false });
});
