# Your tests go here

Every `tests/own/*.test.js` is run by Node's built-in runner. No packages, no `npm install`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parsePointer, resolve } = require('../../src/pointer.js');

test('the key a/b', () => {
  assert.deepStrictEqual(parsePointer('/a~1b'), ['a/b']);
});
```

Run `node --test tests/own/` by hand, or `bash tools/run_own_tests.sh` for the same thing with the
harness's exit-code contract around it.

A file with no cases in it counts as nothing having run, and so does a file whose every case was
skipped: at least one case has to really assert something.

Adding a test file is one step -- write it. There is no list to register it in.
