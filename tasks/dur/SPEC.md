# Durations, in both directions

Implement `src/duration.js` so that the frozen command line works both ways.

```
$ node src/cli.js parse 1h30m
5400
$ node src/cli.js format 3661
1h1m1s
```

Export exactly two functions (`module.exports`, CommonJS -- the CLI is frozen and requires
them):

```js
parseDuration(text)   // -> seconds, or null when text is not a canonical duration
formatDuration(secs)  // -> the canonical duration, or null when secs is not valid input
```

## The canonical form

A canonical duration is one or more `<number><unit>` segments, in **descending** unit
order, no unit repeated, where every unit except the largest present carries less than the
next unit up:

- units: `w` (604800 s), `d` (86400), `h` (3600), `m` (60), `s` (1)
- every unit carries less than the one above it, and weeks are the only unbounded unit:
  seconds and minutes `0..59`, hours `0..23`, days `0..6`, weeks any non-negative integer
- zero segments are not printed, except that zero itself is `0s`
- lower case, no spaces, no signs, no fractions, no leading zeros on a segment

The carry rule is what makes the form a fixed point rather than just an order: `90h` is
not canonical even though it is descending, because 90 hours is 3 days 18 hours, and the
formatter would never print it. The parser accepts exactly what the formatter prints.

So `1w2d3h4m5s`, `1h30m`, `0s`, `59s`, `1w` are canonical; `90m`, `1h60m`, `1h90m`,
`1m1h`, `1h1h`, `1H`, `1`, `h`, ``, ` 1h`, `1h `, `-1h`, `1.5h`, `01h` are not.

## Requirements

1. `parseDuration` returns seconds for every canonical duration, and `null` for anything
   that is not one -- including the empty string, wrong case, a missing or unknown unit,
   a repeated unit, out-of-order units, and a segment that would carry into the unit above.
2. `formatDuration` returns the canonical duration for every non-negative integer number
   of seconds, and `null` for anything else: negatives, fractions, `NaN`, `Infinity`, and
   values that are not numbers at all.
3. The two agree exactly: `parseDuration(formatDuration(n)) === n` for every non-negative
   integer, and `formatDuration(parseDuration(s)) === s` for every string the parser
   accepts. The parser accepts exactly what the formatter prints.
4. No dependencies. Standard library only -- no `npm install`, no third-party packages.
   The tests run with Node's built-in runner.

## The command line contract

- `node src/cli.js parse <text>` -- the number of seconds on stdout, exit 0; rejected
  input prints a message on stderr and exits 1.
- `node src/cli.js format <seconds>` -- the canonical duration on stdout, exit 0; rejected
  input prints a message on stderr and exits 1.
- Any other invocation -- usage on stderr, exit 2.

## Where things are

- Your implementation: `src/duration.js`. Everything you write goes in `src/`.
- Your own tests: `tests/own/`, run with the `run_tests` action. That runs
  `tools/run_own_tests.sh`, which runs `node --test tests/own/` and prints the counts. It
  exits 2 when `tests/own/` holds no tests at all, and exits 2 rather than 1 when the
  suite cannot run, because a suite that did not run observed nothing.
- `tools/`, `src/cli.js` and `tests/own/README.md` are not yours to edit.
- The acceptance corpus is not in this tree. Write the cases you would want to defend.
