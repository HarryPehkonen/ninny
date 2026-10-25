# Cron kernel — implement to this spec

You are in the working directory: **this project's root**. Every path below is
relative to it, and your work must stay inside it.

## How to work (TDD — this is scored)

1. **Read this whole file first.** Then read `include/cronx/cronx.hpp` (frozen — the
   contract). The acceptance corpus is NOT in this tree: it is held outside it and is
   not readable from here, so the semantics below are the whole contract.
2. **Write your own failing tests first**, in `tests/own/`, at least 8 named cases.
   Every `tests/own/*.cpp` you leave there is compiled as your suite, so the filename is
   yours to choose. Name the cases for the behaviour and the trap they pin. Do not try to
   guess the acceptance cases; pick the edges *you* would want to defend.
3. **Make them compile against a stub, then watch them fail on the CHECK.** In C++ a
   missing function is a BUILD error, and a build error is not a RED — nothing ran, so
   nothing was observed. Declare each function with its frozen signature and return a
   placeholder, run the suite, read the failures it reports, and only then implement.
4. **Implement** `src/` until your own suite passes, using the frozen semantics below as
   your reading of the corpus you cannot see.
5. **Run `bash tools/run_own_tests.sh` after every change.** That is your loop, and it is
   what the record of this run is built on.
6. Do not modify anything in `include/` or `tests/harness.hpp`. The oracle hashes them
   against a pristine manifest, outside your tree, and a submission whose instrument
   moved fails whole.
7. **Report evidence, never impressions.** If you stop early, that is a valid result —
   say so and say where you stopped. A claim not backed by output is not a result.
   Genuine ambiguity: take the strict reading, say so, and carry on.

## What to build

A library implementing the frozen API in `include/cronx/cronx.hpp`:

- `cronx::parse(const std::string&)` — the 5-field classic cron form.
- `cronx::matches(const Schedule&, Minute)` — does a UTC minute match?
- `cronx::next(const Schedule&, Minute from, std::size_t count, std::int64_t search_limit)`
  — the next matching minutes strictly after `from`.

Put the implementation in `src/*.cpp` (any number of files you like).

## What NOT to build

- **No timezones, no DST, no local time.** Time is minutes since the epoch, UTC.
- **No `@daily`-style macros, no seconds field, no year field, no `L`, `W`, `#`.**
- **No daemon, no sleeping, no file I/O, no threads.**
- **No third-party dependency.** C++17 standard library only.
- `Minute` values below 0 are out of scope; behaviour there is not tested.

## The frozen semantics (exact — this is where arms lose points)

Fields, in order: minute (0–59), hour (0–23), day-of-month (1–31),
month (1–12), day-of-week (0–6 with **0 = Sunday**). Fields are separated by one
or more spaces or tabs; leading and trailing whitespace is accepted.

**Field grammar.** A field is a comma-separated list of items. An item is:

- `*` — every allowed value in the field
- `N` — the single value N
- `A-B` — the inclusive range A..B (A must be ≤ B)
- `A-B/S` — every S-th value in A..B, starting at A
- `*/S` — every S-th value in the whole field, starting at the field minimum
- `N/S` — the single value N only (a step on a single value is legal and means N)

Values may be given as **names**: months `JAN FEB MAR APR MAY JUN JUL AUG SEP
OCT NOV DEC` (1–12), weekdays `SUN MON TUE WED THU FRI SAT` (0–6). Names are
case-insensitive and cannot carry a step (`MON-FRI/2` is an error).

**Day-of-week 7** is accepted on input and means Sunday; the stored bit is 0.

**Restricted vs unrestricted.** A field counts as *unrestricted* only if its
text is exactly `*`. `*/1` is **restricted** (this is deliberate; it is what
classic Vixie cron does and it changes the next rule).

**The day rule.** Let `dom` and `dow` be the two day fields:

- if **both** are restricted → a minute matches when **either** matches (OR)
- otherwise → it matches when **both** match (AND)

Minute, hour and month are always AND-ed.

**Weekday arithmetic.** 1970-01-01 was a Thursday. Weekday = `(days_since_epoch
+ 4) mod 7` with Sunday = 0. Get this from the epoch; do not hard-code a
calendar.

**`next`.** Returns matching minutes strictly greater than `from`, ascending.
It stops after scanning `search_limit` minutes past `from` and returns what it
found (possibly none) — a schedule that never matches (`0 0 30 2 *`) must
return an empty vector, not hang.

## The frozen API

`include/cronx/cronx.hpp` is the contract. Both `parse` and `matches` and `next`
must exist with exactly those signatures. `Schedule`'s five bit sets are part of
the contract: bit *i* set means value *i* is allowed (`dom` uses bits 1..31,
`month` bits 1..12, `dow` bits 0..6, `minute` bits 0..59, `hour` bits 0..23).
The acceptance corpus reads those bits directly, so a schedule that "behaves
right" but stores the wrong bits fails.

`parse` never throws. On failure: `ok == false`, `error_field` names the
offending field (0 minute … 4 dow), `error` is free text (contents not pinned),
and `schedule` must be left untouched — no half-parsed schedule committed.

**Every input is either a valid schedule or a reported error.** These must all
be rejected, each with the `error_field` shown:

| Input | Why | error_field |
|---|---|---|
| `* * * *` | four fields | 5 |
| `* * * * * *` | six fields | 5 |
| `` (empty) | no fields | 5 |
| `  * * * * *  ` | surrounding whitespace | accepted, not an error |
| `60 * * * *` | minute out of range | 0 |
| `* 24 * * *` | hour out of range | 1 |
| `* * 0 * *` | dom below 1 | 2 |
| `* * 32 * *` | dom above 31 | 2 |
| `* * * 13 *` | month above 12 | 3 |
| `* * * * 8` | dow above 7 | 4 |
| `*/0 * * * *` | step of zero | 0 |
| `/5 * * * *` | step with no base | 0 |
| `10-5 * * * *` | descending range | 0 |
| `1,,2 * * * *` | empty list element | 0 |
| `* * * JAX *` | unknown month name | 3 |
| `MON-FRI/2 * * * *` | step on a named range | 4 |
| `1-2-3 * * * *` | malformed range | 0 |

Anything not listed is a matter of judgement; take the strict reading (reject)
and say so in the report.

## The acceptance corpus is not here

It is held outside this tree and is not readable from here — deliberately, because a
suite written from the answer key proves nothing about the work. Its cases pin exactly
the semantics stated above: the field grammar, the restricted rule and the day rule, the
weekday arithmetic, and the `error_field` for every rejected input in the table.

Treat that prose as the contract, and write the cases you would want to defend.

## Your loop (verbatim)

```
bash tools/run_own_tests.sh
```

It compiles `src/*.cpp` together with `tests/own/*.cpp` under `-std=c++17 -Wall -Wextra
-Wpedantic -Werror`, runs the result, and exits non-zero when the suite does not compile,
when it reports no checks at all, or when a case fails. A `tests/own/` with no `.cpp` in
it is not a pass. **There is no hosted CI and you must not add one.** The acceptance
corpus, the sanitizers and clang-tidy all run outside your tree, after you hand over.

## Stages and when to stop

Work through both stages in one run:

- **Stage A** — your own tests exist in `tests/own/`, were seen failing against a stub,
  and now pass.
- **Stage B** — the implementation follows the frozen semantics, including the error
  fields, and your suite is green after the last change you made.

You have a limited number of steps. Spend them on the implementation, not on exploring.
If you run out, stop and say where you stopped — an honest red report scores better than
a claim of success.

Editing a frozen file (`include/`, `tests/harness.hpp`) is detected by the oracle against
a pristine manifest kept outside your tree, and fails the whole submission. Only those
paths are hashed, so `src/` and `tests/own/` are yours to fill as you like.

## Acceptance (what "done" means)

The acceptance corpus passes, your own tests are present in `tests/own/` and pass, and
every frozen file is byte-identical to how you found it.