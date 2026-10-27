# Guiding the caller — making Ninny hard to use unproductively

**Asked by Harri, 2026-10-27:** *"Can Ninny guide the user into using it in a productive way?"*
Written after two repository runs died with zero writes, on a brief whose own text ordered the reading.

The model-side half is under measurement (`2026-10-27_budget-notes-experiment.md`). This is the
caller-side half: the dials a person sets before the model ever runs.

## What went wrong, expressed as dials

- **The brief** — 9.7 KB, seven requirements, about ten files to read, and no entry point named. Its own
  text said *"Read these before writing anything … re-check every name"*, which is a reconnaissance order.
- **`--steps`** — 40, against a C++ repository with a 121 s gate. Smaller than the brief's reading list.
- **The per-bash timeout** — 120 s, below the gate's 121 s, so running the suite through bash got a silent
  kill. FIXED (`d537c3b`): the floor is now the declared test timeout.
- **`--tdd enforce`** — correct here only because `--test-glob tests/*` was passed. Without globs, or on a
  suite that is currently GREEN, `enforce` cannot be satisfied at all.
- **The launch** — `nohup … ; echo "NINNY EXIT: $?"`, so the shell reported 0 while the record said
  `StepLimit`. Not Ninny's bug, and still Ninny's caller to educate.

## Ranked, by what it costs and what it prevents

1. **A preflight line at launch — DONE.** Prints the repo's size in translation units, the test-source count,
   the step budget, the suite's timeout against the shell timeout, and which of the paths the brief names
   exist — with a warning when none of them do. **Deliberately left out: whether the suite is currently
   GREEN or RED.** That needs an execution, so it is not free, and it belongs with item 3 instead.
2. **Refuse the deadlock — DONE.** `--repo --tdd enforce` without `--test-glob` is refused with exit 2 and
   the reason: every way to make a red is a write the gate refuses. (`enforce` *with* a glob is legal and
   stays legal — a green suite does not deadlock it, because a test file may be written first.)
3. **State the suite's duration (cheap, certain).** Time `--test-cmd` once in the preflight and print the
   number. It is what tells a caller whether 40 steps is a budget or a trap.
4. **A brief template (cheap, high payoff).** Short and prescriptive: the first file to touch, the first
   test to write, the acceptance command, and what is out of scope. The failing brief had everything
   except the first two, and died exactly there.
5. **A step-budget suggestion (medium).** `--steps` is the caller's guess today. A floor derived from the
   tree's size and the measured gate duration is guessable from data Ninny already has.

## What this will NOT do

- It will not judge a brief's *content*. Whether a task is well-posed is not mechanically checkable, and a
  tool that pretends to understand the work is worse than one that states facts.
- It will not touch the run loop, the gate, the exit-code contract, or the record. Everything above is
  pre-run output, or a refusal before the run starts.
- It will not add a dial surface: no new modes, no config file, no plugin. Every item rides on flags that
  already exist, or on output that already has a printer.
