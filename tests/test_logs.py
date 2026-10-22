"""Where Ninny leaves a durable account of itself.

The run directory answers "what happened in this run". These tests are about the other
question -- the one an agent asks after the terminal is gone: what has Ninny been doing,
and where is the log of it.

The answer lives in the state directory and never in the working tree. That is not
tidiness: a log written inside the tree is a file the next model reads, and a log of a
run is a log of *the model's own reasoning about the task*. It would be context, and
context about the task is something a run must not get.

The one thing a log must never carry is a credential. The process that writes these logs
is the process holding the API key, and the reader is an agent that may paste the file
into a context window -- so a registered secret is scrubbed on the way to disk, not left
to the care of whoever wrote the print statement.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from ninny import logs


class LogDirTests(unittest.TestCase):
    """XDG, in the order a Linux user expects: an override, then the spec, then the default."""

    def test_honours_an_explicit_directory(self):
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"NINNY_LOG_DIR": tmp}, clear=False):
                self.assertEqual(logs.log_dir(), Path(tmp))
                self.assertTrue(logs.log_dir().is_dir())

    def test_honours_xdg_state_home(self):
        with TemporaryDirectory() as tmp:
            env = {"XDG_STATE_HOME": tmp}
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("NINNY_LOG_DIR", None)
                self.assertEqual(logs.log_dir(), Path(tmp) / "ninny" / "logs")

    def test_falls_back_to_local_state(self):
        with TemporaryDirectory() as home:
            env = {"HOME": home}
            with mock.patch.dict(os.environ, env, clear=False):
                os.environ.pop("NINNY_LOG_DIR", None)
                os.environ.pop("XDG_STATE_HOME", None)
                self.assertEqual(logs.log_dir(), Path(home) / ".local" / "state" / "ninny" / "logs")

    def test_the_directory_is_private(self):
        """A log of what a model wrote in a run is nobody else's business on this machine."""
        with TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"NINNY_LOG_DIR": tmp + "/nested"}, clear=False):
                logs.log_dir()
                mode = logs.log_dir().stat().st_mode & 0o777
                self.assertEqual(mode, 0o700, f"expected 0700, got {oct(mode)}")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"NINNY_LOG_DIR": self._tmp.name}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_session_writes_a_transcript_file(self):
        with logs.session("run", "arm-one") as log:
            print("step 1: wrote src/thing.py")
        text = log.path.read_text()
        self.assertIn("wrote src/thing.py", text)
        self.assertIn("step 1", text)

    def test_it_still_prints_to_the_terminal(self):
        written = []
        with mock.patch("sys.stdout", new=type("S", (), {"write": lambda _s, t: written.append(t),
                                                        "flush": lambda _s: None})()):
            with logs.session("run", "arm-one"):
                print("visible")
        self.assertIn("visible", "".join(written))

    def test_a_log_file_is_not_readable_by_others(self):
        with logs.session("run", "arm") as log:
            print("something a model wrote")
        mode = log.path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600, f"expected 0600, got {oct(mode)}")

    def test_the_name_says_what_it_was(self):
        with logs.session("verify-task", "cron") as log:
            pass
        self.assertIn("verify-task", log.path.name)
        self.assertIn("cron", log.path.name)

    def test_two_sessions_in_the_same_second_do_not_collide(self):
        """The check-directory bug, again, in a new place: stamps collide within a second."""
        with logs.session("run", "arm") as first:
            pass
        with logs.session("run", "arm") as second:
            pass
        self.assertNotEqual(first.path, second.path)
        self.assertTrue(first.path.exists())
        self.assertTrue(second.path.exists())

    def test_a_session_that_raises_still_leaves_a_readable_log(self):
        """An agent reads logs of runs that failed. Those are the ones it needs."""
        log = None
        with self.assertRaises(RuntimeError):
            with logs.session("run", "arm") as log:
                print("before the failure")
                raise RuntimeError("model call died")
        self.assertIn("before the failure", log.path.read_text())


class SecretTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"NINNY_LOG_DIR": self._tmp.name}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(logs.clear_secrets)

    def test_a_registered_secret_never_reaches_the_file(self):
        logs.register_secret("sk-a-real-looking-key-value")
        with logs.session("run", "arm") as log:
            print("calling the endpoint with sk-a-real-looking-key-value now")
        text = log.path.read_text()
        self.assertNotIn("sk-a-real-looking-key-value", text)
        self.assertIn("[redacted]", text)
        self.assertIn("calling the endpoint with", text)

    def test_a_registered_secret_never_reaches_the_history_line(self):
        logs.register_secret("sk-a-real-looking-key-value")
        logs.record(subcommand="run", model="sk-a-real-looking-key-value")
        text = logs.history_path().read_text()
        self.assertNotIn("sk-a-real-looking-key-value", text)
        self.assertIn("[redacted]", text)

    def test_an_empty_secret_is_ignored(self):
        """`register_secret("")` would scrub every character out of every log."""
        logs.register_secret("")
        with logs.session("run", "arm") as log:
            print("nothing to hide")
        self.assertIn("nothing to hide", log.path.read_text())


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"NINNY_LOG_DIR": self._tmp.name}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_history_is_appended_never_rewritten(self):
        logs.record(subcommand="run", task="roman", exit_status="Submitted", steps=18)
        first = self.records()
        logs.record(subcommand="run", task="cron", exit_status="StepLimit", steps=40)
        lines = self.records()
        self.assertEqual(lines[0], first[0])
        self.assertEqual(len(lines), 2)
        self.assertIn("roman", lines[0])
        self.assertIn("cron", lines[1])

    def records(self) -> list[str]:
        """The lines that are records, which is every line but the column names."""
        return [line for line in logs.history_path().read_text().splitlines()
                if line and not line.startswith("#")]

    def test_a_history_line_carries_the_three_artifacts_and_the_verdict(self):
        """The three-artifact rule, in one line: record, diff, and how it ended."""
        logs.record(
            subcommand="run",
            task="cron",
            model="deepseek/deepseek-v4.1-flash",
            exit_status="StepLimit",
            steps=40,
            cost_usd=0.0614,
            verdict="red-first",
            run_dir="/tmp/runs/cron/cpp-told-r1",
            log_file="/tmp/logs/x.log",
        )
        line = self.records()[0]
        for field in ("cron", "deepseek/deepseek-v4.1-flash", "StepLimit", "40",
                      "0.0614", "red-first", "/tmp/runs/cron/cpp-told-r1"):
            self.assertIn(field, line)

    def test_history_is_one_line_per_call_under_a_header(self):
        logs.record(subcommand="check", task="cron", exit_status="ACCEPTANCE PASSED")
        logs.record(subcommand="verify-task", task="cron", exit_status="VERIFIED")
        everything = logs.history_path().read_text().strip().splitlines()
        self.assertTrue(everything[0].startswith("# "), "the first line names the columns")
        for field in logs.HISTORY_FIELDS:
            self.assertIn(field, everything[0])
        lines = self.records()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("2"), "a timestamp leads each line")
        self.assertIn("check", lines[0])
        self.assertIn("verify-task", lines[1])

    def records(self) -> list[str]:
        return [line for line in logs.history_path().read_text().splitlines()
                if line and not line.startswith("#")]

    def test_a_missing_field_leaves_an_empty_column_not_the_word_none(self):
        """Column five has to be column five on every line, including the sparse ones."""
        logs.record(subcommand="doctor")
        line = self.records()[0]
        self.assertNotIn("None", line)
        self.assertEqual(len(line.split("\t")), 1 + len(logs.HISTORY_FIELDS))
        self.assertEqual(line.split("\t")[1], "doctor")
        self.assertEqual(line.split("\t")[9], "")


class OffSwitchTests(unittest.TestCase):
    def test_a_disabled_session_writes_nothing_and_creates_no_directory(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-used"
            with mock.patch.dict(os.environ, {"NINNY_LOG_DIR": str(target)}, clear=False):
                with logs.session("run", "arm", enabled=False) as log:
                    print("not logged")
                self.assertIsNone(log.path)
                self.assertFalse(target.exists(),
                                 "a disabled run must not create the state directory")

    def test_a_run_survives_a_log_directory_it_cannot_write(self):
        """A harness that refuses to work because it cannot write a diary is worse than a
        harness with no diary."""
        with TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "a-file-where-a-directory-would-go"
            blocker.write_text("untouched")
            env = {"NINNY_LOG_DIR": str(blocker / "nested")}
            with mock.patch.dict(os.environ, env, clear=False):
                with logs.session("run", "arm") as log:
                    print("the run must not die because of this")
                self.assertIsNone(log.path)
                self.assertEqual(blocker.read_text(), "untouched")


if __name__ == "__main__":
    unittest.main()
