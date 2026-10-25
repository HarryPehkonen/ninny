# Close a bypass in the test-first gate

`ninny` enforces test-first. While a run is in the test phase, `TDDPolicy.gate()`
refuses a write into the source tree until a test has been observed to fail.

There is a hole. The gate classifies a path by the string the model wrote, and a
string can walk back out of the directory it appears to be in.

## Reproduction

With no test yet observed to fail, the gate refuses these as expected:

```
ninny/tdd.py                     refused
```

but these get through, and the environment then lets the write happen because it
really does land inside the working tree:

```
tests/../ninny/tdd.py            NOT refused
tests/own/../../ninny/tdd.py     NOT refused
../outside.py                    NOT refused
../../etc/passwd                 NOT refused
```

## Required behaviour

A path must be classified by **where it lands**, not by how it is spelled.

With no test yet observed to fail, all of these must be refused:

```
ninny/tdd.py
tests/../ninny/tdd.py
tests/own/../../ninny/tdd.py
../outside.py
../../etc/passwd
```

and these must still be allowed:

```
tests/own/test_gate.py
tests/test_gate.py
```

After a test has been written and observed to fail, writes into `ninny/` must be
allowed again — including a path spelled with `..`. A gate that simply refuses
everything fails this.

## Constraints

- `Task.is_test_path` and `Task.is_src_path` must keep working for ordinary
  relative paths.
- `ninny`'s own test suite must keep passing: `python3 -m unittest discover -s tests -t .`
- Standard library only.
- `ninny/env.py` (`Environment.resolve`) already resolves paths for real; it is the
  behaviour the gate should agree with.

## Where things are

- The gate is `ninny/tdd.py`.
- Put your tests under `tests/` in files matching `test*.py` and run them with the
  `run_tests` action.
- `tools/` is not yours to edit.
