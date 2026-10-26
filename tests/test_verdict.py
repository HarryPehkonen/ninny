"""The verdict an orchestrator reads instead of prose.

`result.json` carries 25 fields under `tdd` plus an `exit_status`, and a caller that wants to know
"may I apply this patch?" had to know which five to AND together. The exit code is the API:

    0  artifact present       submitted, red before the first source write, the suite handed back
                              is the suite that went red, green observed after the last write
    1  handed back, unproven  submitted, but at least one of those is false; `reasons` names them
    2  did not hand back      nothing to grade (StepLimit, wall clock, repeated format errors)

Three rules these tests pin. A **missing field is exit 2** with `record incomplete: <field>` --
never a silent pass, because a verifier that passes on absent evidence is the failure the whole
repo is built to catch. **Reasons are plural and specific**: an orchestrator routes on them, so
"unproven" alone is not an answer. And the line is **deterministic**: the same record produces the
same bytes, because a verifier whose output moves cannot be diffed or replayed.
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from ninny.verdict import EXIT_ARTIFACT, EXIT_NO_HANDBACK, EXIT_UNPROVEN, verdict_of

A_REAL_ARM = Path(__file__).resolve().parent.parent / "runs/dogfood-stamp/ab-editfile2-1/result.json"


def a_record(**over) -> dict:
    """A record that earns exit 0, then whatever the test breaks."""
    tdd = {
        "mode": "enforce",
        "verdict": "red-first",
        "red_step": 14,
        "first_src_step": 15,
        "last_src_step": 20,
        "red_before_code": True,
        "suite_frozen_since_red": True,
        "green_after_last_write": True,
        "bypass_detected": [],
        "harness_runs": [],
    }
    tdd.update(over.pop("tdd", {}))
    record = {"exit_status": "Submitted", "steps": 28, "cost_usd": 0.01, "tdd": tdd}
    record.update(over)
    return record


class TheThreeExits(unittest.TestCase):
    def test_a_complete_run_is_the_artifact(self):
        code, line = verdict_of(a_record())
        self.assertEqual(code, EXIT_ARTIFACT)
        self.assertEqual(line["verdict"], "artifact")
        self.assertEqual(line["reasons"], [])

    def test_a_submission_missing_one_property_is_unproven(self):
        code, line = verdict_of(a_record(tdd={"suite_frozen_since_red": False}))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertEqual(line["verdict"], "unproven")
        self.assertEqual(len(line["reasons"]), 1)
        self.assertIn("suite", line["reasons"][0])

    def test_nothing_handed_back_is_not_a_verdict_on_anything(self):
        code, line = verdict_of(a_record(exit_status="StepLimit"))
        self.assertEqual(code, EXIT_NO_HANDBACK)
        self.assertEqual(line["verdict"], "no-handback")
        self.assertIn("StepLimit", line["reasons"][0])


class EveryWayARunIsUnproven(unittest.TestCase):
    def test_a_red_that_came_after_the_code(self):
        code, line = verdict_of(a_record(tdd={"red_before_code": False, "verdict": "red-after-code"}))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertTrue(any("red before" in r for r in line["reasons"]), line["reasons"])

    def test_no_green_after_the_last_write(self):
        code, line = verdict_of(a_record(tdd={"green_after_last_write": False}))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertTrue(any("green" in r for r in line["reasons"]), line["reasons"])

    def test_a_suite_that_is_not_the_suite_that_went_red(self):
        code, line = verdict_of(a_record(tdd={"suite_frozen_since_red": False}))
        self.assertTrue(any("went red" in r for r in line["reasons"]), line["reasons"])

    def test_a_write_that_went_round_the_tools(self):
        code, line = verdict_of(a_record(tdd={"bypass_detected": [[15, "src/thing.py"]]}))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertTrue(any("round the tools" in r for r in line["reasons"]), line["reasons"])

    def test_every_reason_is_listed_not_just_the_first(self):
        code, line = verdict_of(a_record(tdd={"red_before_code": False,
                                              "suite_frozen_since_red": False,
                                              "green_after_last_write": False}))
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertEqual(len(line["reasons"]), 3, line["reasons"])


class AMissingFieldIsNeverAPass(unittest.TestCase):
    def test_an_absent_tdd_field_is_exit_two_and_names_itself(self):
        record = a_record()
        del record["tdd"]["suite_frozen_since_red"]
        code, line = verdict_of(record)
        self.assertEqual(code, EXIT_NO_HANDBACK)
        self.assertIn("record incomplete: tdd.suite_frozen_since_red", line["reasons"])

    def test_a_record_with_no_tdd_block_at_all_is_exit_two(self):
        code, line = verdict_of({"exit_status": "Submitted", "steps": 3})
        self.assertEqual(code, EXIT_NO_HANDBACK)
        self.assertTrue(all("record incomplete" in r for r in line["reasons"]), line["reasons"])


class TheLineIsDeterministic(unittest.TestCase):
    def test_the_same_record_produces_the_same_bytes(self):
        first = json.dumps(verdict_of(a_record())[1], sort_keys=True)
        second = json.dumps(verdict_of(a_record())[1], sort_keys=True)
        self.assertEqual(first, second)

    def test_the_line_carries_the_evidence_and_not_just_the_label(self):
        _, line = verdict_of(a_record())
        for key in ("exit_status", "order", "red_step", "first_src_step", "green_after_last_write",
                    "suite_frozen_since_red", "bypass_detected", "steps", "cost_usd"):
            self.assertIn(key, line, f"an orchestrator routing on this needs {key}")


class ARecordFromThisCampaign(unittest.TestCase):
    """The line has to agree with a record a real arm actually wrote."""

    @unittest.skipUnless(A_REAL_ARM.exists(), "runs/ is gitignored: nothing to check here")
    def test_the_editfile_arm_earns_the_artifact(self):
        code, line = verdict_of(json.loads(A_REAL_ARM.read_text()))
        self.assertEqual(code, EXIT_ARTIFACT, line)
        self.assertEqual(line["order"], "red-first")
        self.assertEqual(line["bypass_detected"], [])


class TheCommandLine(unittest.TestCase):
    def test_cmd_verdict_prints_one_json_line_and_returns_its_code(self):
        import io
        import contextlib
        from ninny.cli import cmd_verdict

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "result.json"
            record.write_text(json.dumps(a_record()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cmd_verdict(SimpleNamespace(run=str(record)))
        self.assertEqual(code, EXIT_ARTIFACT)
        printed = out.getvalue().strip().splitlines()
        self.assertEqual(len(printed), 1, out.getvalue())
        self.assertEqual(json.loads(printed[0])["verdict"], "artifact")

    def test_a_missing_run_directory_is_exit_two_with_a_sentence(self):
        from ninny.cli import cmd_verdict
        import io
        import contextlib

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cmd_verdict(SimpleNamespace(run="/nonexistent/run/dir"))
        self.assertEqual(code, EXIT_NO_HANDBACK)


if __name__ == "__main__":
    unittest.main()
