# Traps found the hard way

> Extracted verbatim from `ninny-harness/SKILL.md` (split by scripts/split_skill.py).
> The body keeps a pointer; this file keeps the detail.

- **`str.lstrip("./")` strips a character set, not a prefix** — it turns
  `../../etc/passwd` into `etc/passwd`. Use `Path.resolve()` + `relative_to` to ask
  where a path LANDS. Ninny's own gate had this hole (see `tasks/ninny-gate`).
- **Change detection cannot use mtime+size.** Two writes in the same filesystem
  timestamp tick are invisible. Hash content (`snapshot()` does).
- `ninny check` must resolve `--tree` and its staging dir to ABSOLUTE paths; a
  relative path makes the oracle grade the wrong directory (the failure looks like a
  weird `AttributeError` from the stub, not like a path bug).
- Check directories are stamped to the second: give the stamp a uniqueness fallback
  or two checks in one second collide in `copytree`.
- `python3 -m unittest discover -s tests -t .` needs `tests/__init__.py`.
- **Build a task tree from the commit BEFORE the fix** (`git archive <sha> ninny tests |
  tar -x -C tasks/<name>/tree`) so the task carries exactly one defect. If the tree's own
  suite already fails, the agent chases pre-existing failures instead of the task.
- **An oracle script's exit status is its LAST command's.** An `echo` after the `grep`
  makes every verdict a pass. `verify-task` catches it in plain words ("it passes on the
  tree the agent starts from, so it grades nothing").
- **A run must not hand back a red tree**: if the last `run_tests` exited non-zero the
  submit is refused once, in EVERY `--tdd` mode (`--allow-red-submit` opts out). It is a
  quality guarantee, not a test-first rule, so it is not conditional on the mode.
- **The write gate can be routed around — trust the TREE, not the action log.** Both live
  bypasses smuggled a source change through an intermediary: a script written into the
  tree root and run (`python3 patch_x.py && rm patch_x.py`), and a `python3 - <<'EOF'`
  heredoc. The path detector can read neither. `snapshot()` reconciliation against the
  tree caught both, which is why the tree is the arbiter of what happened.
- **To ask whether an arm's own tests have teeth**: patch the module the tests import
  BEFORE they import it, run the arm's own `test_cmd`, and see whether the suite goes red.
  Twenty arms against six seeded wrong answers took 19 s and produced a number no other
  field gives. Note it is only valid where the baseline is green, and that a wrong answer
  the acceptance suite does not test is not a defect the arm was required to catch.
- **Never trust a PASS without reading the diff.** A model that rewrites an 11 KB module
  and passes the oracle may still have weakened something the oracle does not check. The
  oracle's `test_the_submitted_suite_still_passes` covers part of that; the diff is your
  job.
- A submission's baseline can predate your latest commits — diff it against the commit
  the tree was built from, or you will read your own fixes as the model's reverts.
- **Cover the last step of the main subcommand end to end.** Nothing drove `cmd_run` to
  completion, so a rename on `RunResult` (`cost_usd` vs `cost`) broke EVERY run on its
  final step — after the model had been paid for, with the record, the diff and the log
  already on disk and no index line. `tests/test_run_end_to_end.py` drives the real CLI
  with a stubbed client and stubbed prices: no network, no money.
- **On a C++ task the first RED is usually a build error.** `cc1plus: fatal error:
  src/*.cpp: No such file` and a genuine assertion failure both arrive as "exit 1", so a
  `red-first` verdict on C++ can rest on a red where nothing ran at all. The runner
  prints the distinction (BUILD FAILED versus assertion output); the record does not
  carry it yet. Record which kind of red it was — never gate on it.
- **A model may build its own second opinion.** In the live C++ run the model wrote a
  238-line Python re-implementation of the frozen spec as a differential oracle and
  checked its C++ against it. That is not a bypass; it is the behaviour a harness wants,
  and it costs steps (that run hit the 40-step limit while its acceptance corpus passed
  122/122 at $0.0614).
- **A task can be unsolvable and still pass both controls.** Check that every file the task
  REQUIRES the agent to edit is absent from `protected_globs`: the gate refuses a protected
  write in every mode, so a required edit becomes an impossible one. `tasks/bits` shipped with
  `CMakeLists.txt` protected while its README, its own header and the oracle's comment all told
  the agent to register a target there -- no target, no compiled test; no test, no red; the task
  could not be done at all. `verify-task` passed anyway, because it grades the answer key, whose
  CMakeLists is already correct: both controls grade the ENDS of a task and neither runs the
  middle. **Run one arm on every task before trusting it** -- the broken one here had 20 log rows
  and every one of them was `verify-task`, none of them a run.
- **A file's own header is a specification, and it can be unmet.** That CMakeLists said the
  acceptance corpus "checks that everything else is unchanged"; the corpus hashed two other
  files and deliberately skipped this one. When a file promises a check, implement it before
  believing it: hash the region ABOVE the marker (`awk '/MARKER/{print; exit} {print}'`), record
  that hash in the oracle, then unprotect the file so the required edit is allowed. Teeth: a flag
  changed above the marker must FAIL, and the clean answer key must still verify.
- **The verdict only sees the `run_tests` action, so a real red can be recorded as none.**
  `red_step` comes from `run_tests` observations alone; an arm that runs `bash
tools/run_own_tests.sh` sees exactly the same output, prints `EXIT=1`, and its process record
  stays blank. Measured on the bits arms: 2 of 3 were red-first in substance (runner printed
  `EXIT=1` before the first source write) and are recorded `no-red`. Both wrote
  `; echo "EXIT=$?"` -- they were reading the exit code, just not through the action. So quote a
  verdict as "recorded no-red", never as "did not test first": it describes what the harness
  could see, not what the model did. **The first cross-task sweep put a number on it: 17 of 18
  arms ran the suite through `bash` at least once and 4 of 18 are recorded `no-red`.** Treat a
  blank process record as "the harness could not see it" by default.
- **A killed action is indistinguishable from a suite that reported nothing.** a3's first
  suite run died at Ninny's own 180 s action timeout (exit 124, no verdict printed) and the
  model worked around it with `timeout 170 bash tools/run_own_tests.sh`. A cold CMake +
  GoogleTest build of 13 targets does not fit in 180 s on this machine; a weaker arm reads that
  observation as "my tests failed" or as a broken task. Raise the task's `timeout_s`, or say in
  the observation that the harness killed it. It is reproducible: in the first cross-task sweep
  `bits-s1` was killed the same way at step 13, so 2 of the 6 bits arms now end this way.
- **The tree's own files are enough onboarding -- measured, not hoped.** One bits arm opened by
  reading `tests/own/README.md` and `tools/run_own_tests.sh`; all three found the
  register-your-test-in-CMakeLists rule without being told, because the file's own header says
  it. Entry cost: 10-33 steps and 1.1-1.8 cents to a passing submission. When asked to improve
  accessibility, look for signal gaps before documentation gaps; the documentation gap was not
  there.
- **A task with no arms is an untested task.** `tasks/bits` shipped with a required-but-refused
  edit and passed `verify-task` for weeks: the controls grade the ENDS of a task (oracle RED on
  the stub, GREEN on the answer key) and nothing runs the middle. One arm found it.
- **The third control's dataset has to be a PLANTED test, not a broken answer key.** Sabotaging
  the answer key asks the runner nothing: the answer key carries no suite (the agent writes
  that), so `test_cmd` on it correctly answers exit 2 "nothing ran" and the control measures
  nothing. Measured on four real tasks -- every one came back 2. Plant a test that cannot pass
  (`oracle/probe.sh`, declared as `probe_cmd`) and require exit 1.
- **A planted test must match the runner's own discovery rule, or it never runs.** `roman`'s
  first probe wrote `tests/own/probe_test.py`; unittest's default pattern is `test*.py`, so the
  suite correctly found nothing and the control failed with exit 2. The probe's file NAME is
  part of the task's contract, not an implementation detail.
- **A tree's README may promise a discovery rule the toolchain does not have, and then an agent
  that follows it cannot bank a red.** `tasks/intset/tests/own/README.md` said every
  `tests/own/*.rs` is a Cargo integration test; Cargo autodiscovers only `tests/*.rs` and
  `tests/*/main.rs`. Measured: `tests/own/merging.rs` left the suite at exit 2 "0 passed",
  `tests/own/main.rs` produced a real red -- so under `--tdd enforce` that task was unsolvable.
  Fix the README, then run its own example against the answer key to prove the doc is real code.
- **An empty frozen manifest is a vacuous pass inside an oracle.** A `frozen.sha256` emptied by a
  stray redirect makes the oracle's `while read` loop run zero times and it still prints
  *"every frozen file is unchanged"*. Require at least one entry (`grep -c .`).
- **`fixed/` must be changed WITH `tree/`.** Every frozen file lives in both, so a correction
  applied to one without the other makes the answer key fail its own frozen check -- caught by
  the two-way control within a minute of the edit (*"oracle is GREEN on the fixed tree"* FAILED).
- **Re-measure a task's step limit only after its instrument tells the truth.** `tasks/intset`
  hit its 35-step limit in 3 of 3 arms while its runner was mislabelling every red; steps spent
  fighting the instrument are not evidence about the limit. Measured after the runner fix, same
  model and mode: `red-first` 3/3 (was 0/3), acceptance 3/3 (was 1/3), steps 23/35/22 (was
  35/35/35), $0.015 per arm (was $0.031). An instrument that lies costs money as well as truth --
  and the limit then needed no change, because it had never been the problem.
