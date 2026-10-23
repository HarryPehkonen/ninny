# Your tests go here

Every `tests/own/*.test.js` is run by Node's built-in runner. No packages, no
`npm install`:

```js
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parseDuration, formatDuration } = require('../../src/duration.js');

test('a canonical duration parses to its seconds', () => {
  assert.strictEqual(parseDuration('1h30m'), 5400);
});
```

`tools/run_own_tests.sh` runs `node --test tests/own/` and prints the counts. It reports
the run as exit 2 rather than a pass when the suite found no tests at all, and 2 rather
than 1 when the suite could not run, because a suite that did not run observed nothing.

These cases are the only tests anybody will read when they ask whether the implementation
can be trusted. Write the ones you would want to defend: the edges of every unit
boundary, the rejected input, and at least one property that has to hold for every value
rather than for the examples you happened to pick.
