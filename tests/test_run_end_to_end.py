"""The last thing a run does: write its line in the index.

Nothing drove `cmd_run` end to end, and it showed. `cmd_run` read `result.cost_usd`, which
does not exist on `RunResult` (the field is `cost`), so every run crashed on its final step
— after the model had already been paid for. That is the worst place in a program to find a
typo, and the reason this file exists.

No network, no model, no money: the client and the prices are both stubs. What is real is
everything downstream of the model — the sandbox plan, the tree copy, the trajectory, the
diff, the log, and the index line.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ninny import SUBMIT_SENTINEL, cli
from ninny.model import Response, ToolCall

REPO = Path(__file__).resolve().parent.parent


class StubClient:
    """A model with exactly one move: submit."""

    def __init__(self, model="stub/model", base_url="", api_key="", wire="chat", **kwargs):
        self.model = model
        self.wire = wire
        self.calls = 0

    def complete(self, messages, tools=None):
        self.calls += 1
        call = ToolCall(name="bash", arguments={"command": f"echo {SUBMIT_SENTINEL}"}, id="call-1")
        return Response(
            text="submitting",
            tool_calls=[call],
            usage={"prompt_tokens": 100, "completion_tokens": 20},
            finish_reason="stop",
            latency_s=0.01,
        )


class StubPricing:
    """No endpoint, no catalogue: a price we already know, so the run costs nothing."""

    def __init__(self, *args, **kwargs):
        pass

    def describe(self, model_id):
        return "stub: $1.00/M in, $2.00/M out"

    def cost(self, model_id, usage):
        return (usage.get("prompt_tokens", 0) * 1.0 + usage.get("completion_tokens", 0) * 2.0) / 1_000_000


class IndexLineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.logs = self.root / "logs"
        env = mock.patch.dict(os.environ, {"NINNY_LOG_DIR": str(self.logs)})
        env.start()
        self.addCleanup(env.stop)
        self.arms = 0

    def run_arm(self, *extra):
        self.arms += 1
        with mock.patch.object(cli, "ModelClient", StubClient), \
                mock.patch.object(cli, "Pricing", StubPricing):
            return cli.main([
                "run",
                "--task", str(REPO / "tasks" / "roman"),
                "--model", "stub/model",
                "--sandbox", "none",
                "--allow-oracle-visible",  # `none` cannot hide the oracle; the run says so
                "--out", str(self.root / "runs"),
                "--name", f"stub-arm-{self.arms}",
                "--steps", "4",
                *extra,
            ])

    def records(self) -> list[str]:
        text = (self.logs / "history.tsv").read_text()
        return [line for line in text.splitlines() if line and not line.startswith("#")]

    def columns(self) -> dict[str, str]:
        from ninny import logs

        values = self.records()[0].split("\t")
        return dict(zip(("timestamp", *logs.HISTORY_FIELDS), values))

    def test_a_run_that_submits_writes_its_index_line(self):
        code = self.run_arm()
        self.assertEqual(code, 0, "a submitted run is a success")
        fields = self.columns()
        self.assertEqual(fields["subcommand"], "run")
        self.assertEqual(fields["task"], "roman")
        self.assertEqual(fields["model"], "stub/model")
        self.assertEqual(fields["exit_status"], "Submitted")
        self.assertEqual(fields["steps"], "1")
        self.assertNotEqual(fields["cost_usd"], "", "the cost column is filled in")
        self.assertEqual(len(self.records()), 1, "one invocation, one line")

    def test_the_index_line_points_at_a_transcript_that_exists(self):
        self.run_arm()
        log_file = Path(self.columns()["log_file"])
        self.assertTrue(log_file.exists(), f"{log_file} is named by the index but missing")
        text = log_file.read_text()
        self.assertIn("# ninny run stub-arm-1", text)
        self.assertIn("=== Submitted ===", text)
        self.assertIn("next, BY HAND:", text)

    def test_the_run_directory_holds_the_four_artifacts(self):
        self.run_arm()
        run_dir = Path(self.columns()["run_dir"])
        for name in ("trajectory.json", "trajectory.md", "diff.patch"):
            self.assertTrue((run_dir / name).exists(), f"{name} missing from {run_dir}")
        self.assertTrue((run_dir / "tree").is_dir())

    def test_the_verdict_the_index_carries_is_the_one_in_the_record(self):
        """The index is a pointer, not a second opinion: it has to agree with the record."""
        import json

        self.run_arm()
        fields = self.columns()
        record = json.loads((Path(fields["run_dir"]) / "trajectory.json").read_text())
        self.assertEqual(fields["verdict"], record["result"]["tdd"]["verdict"])
        self.assertEqual(fields["exit_status"], record["result"]["exit_status"])

    def test_no_log_writes_nothing_at_all(self):
        self.run_arm("--no-log")
        self.assertFalse(self.logs.exists(),
                         "a disabled run must not create the state directory")


if __name__ == "__main__":
    unittest.main()
