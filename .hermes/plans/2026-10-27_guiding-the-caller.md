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

1. **A preflight line at launch (cheap, certain).** Before the first model call, print the facts the caller
   is deciding with: the repo's size in translation units; the declared test command, **and whether the
   suite is currently GREEN or RED**; the step budget; the per-bash timeout against the suite's measured
   duration; and whether the prompt names any path that exists in the tree. Those are checks, not
   judgements — no model call, no guessing.
2. **Refuse the deadlock (cheap, certain).** `--repo --tdd enforce` with no `--test-glob`, or with a suite
   that is currently GREEN, cannot be satisfied: every way to make a red is itself a write the gate
   refuses. Refuse the invocation and say that sentence, rather than spending 40 steps proving it.
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
