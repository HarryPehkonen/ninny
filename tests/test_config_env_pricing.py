"""Configuration rules, path confinement, and honest pricing."""

import json
import tempfile
import unittest
from pathlib import Path

from ninny.config import ConfigError, load_task
from ninny.env import ActionError, Environment
from ninny.pricing import Pricing
from ninny.sandbox import Sandbox, SandboxError, build_sandbox, child_env


def write_task(root: Path, **overrides) -> Path:
    (root / "tree" / "src").mkdir(parents=True, exist_ok=True)
    (root / "tree" / "src" / "a.py").write_text("x = 1\n")
    (root / "SPEC.md").write_text("do the thing\n")
    body = {
        "name": "tiny",
        "tree": "tree",
        "oracle": "oracle",
        "oracle_cmd": "bash oracle/gate.sh",
        "test_cmd": "true",
    }
    body.update(overrides)
    lines = []
    for key, value in body.items():
        if value is None:
            continue
        if isinstance(value, list):
            lines.append(f"{key} = {json.dumps(value)}")
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value}")
    (root / "task.toml").write_text("\n".join(lines) + "\n")
    return root / "task.toml"


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_valid_task_loads_with_defaults(self):
        write_task(self.root)
        (self.root / "oracle").mkdir()
        task = load_task(self.root)
        self.assertEqual(task.name, "tiny")
        self.assertEqual(task.test_globs, ["tests/own/**"])
        self.assertEqual(task.src_globs, ["src/**"])
        self.assertEqual(task.step_limit, 40)

    def test_an_oracle_inside_the_tree_is_refused(self):
        write_task(self.root, oracle="tree/oracle")
        (self.root / "tree" / "oracle").mkdir()
        with self.assertRaises(ConfigError) as caught:
            load_task(self.root)
        self.assertIn("inside the task tree", str(caught.exception))

    def test_a_task_with_no_test_command_is_refused(self):
        write_task(self.root, test_cmd=None)
        (self.root / "oracle").mkdir()
        with self.assertRaises(ConfigError) as caught:
            load_task(self.root)
        self.assertIn("test_cmd", str(caught.exception))

    def test_a_missing_spec_is_refused(self):
        write_task(self.root)
        (self.root / "oracle").mkdir()
        (self.root / "SPEC.md").unlink()
        with self.assertRaises(ConfigError):
            load_task(self.root)

    def test_protected_globs_survive_loading(self):
        write_task(self.root, protected_globs=["tools/**"])
        (self.root / "oracle").mkdir()
        task = load_task(self.root)
        self.assertTrue(task.is_protected("tools/run.sh"))
        self.assertFalse(task.is_protected("src/a.py"))


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        (self.work / "src").mkdir()
        self.env = Environment(self.work, Sandbox(), test_cmd="true")

    def tearDown(self):
        self._tmp.cleanup()

    def test_writing_and_reading_a_file(self):
        self.assertTrue(self.env.write_file("src/a.py", "x = 1\n").ok)
        observation = self.env.read_file("src/a.py")
        self.assertIn("x = 1", observation.output)
        self.assertIn("1", observation.note)

    def test_writing_creates_parent_directories(self):
        self.assertTrue(self.env.write_file("deep/down/a.py", "pass\n").ok)
        self.assertTrue((self.work / "deep" / "down" / "a.py").is_file())

    def test_escaping_the_tree_with_dotdot_is_refused(self):
        with self.assertRaises(ActionError):
            self.env.write_file("../outside.py", "nope")

    def test_escaping_the_tree_with_an_absolute_path_is_refused(self):
        with self.assertRaises(ActionError):
            self.env.write_file("/tmp/outside-ninny-test.py", "nope")

    def test_reading_outside_is_refused_by_default(self):
        with self.assertRaises(ActionError):
            self.env.read_file("/etc/hostname")

    def test_allow_outside_permits_reading_but_still_not_writing_out(self):
        env = Environment(self.work, Sandbox(), allow_outside=True)
        self.assertTrue(env.read_file("/etc/hostname").ok)
        with self.assertRaises(ActionError):
            env.write_file("/tmp/outside-ninny-test.py", "nope")

    def test_read_file_with_a_line_range(self):
        self.env.write_file("src/a.py", "one\ntwo\nthree\n")
        self.assertIn("two", self.env.read_file("src/a.py", start=2, end=2).output)
        self.assertNotIn("three", self.env.read_file("src/a.py", start=2, end=2).output)

    def test_long_output_is_cut_with_a_marker_rather_than_silently(self):
        env = Environment(self.work, Sandbox(), output_limit=100)
        text = env.limit("A" * 500)
        self.assertIn("bytes omitted by the harness", text)

    def test_a_shell_redirect_into_the_source_is_spotted(self):
        self.assertEqual(self.env.looks_like_src_write("echo x > src/a.py"), "src/a.py")
        self.assertEqual(self.env.looks_like_src_write("sed -i s/a/b/ src/a.py"), "src/a.py")
        self.assertEqual(self.env.looks_like_src_write("g++ -c src/a.cpp -o a.o"), "")

    def test_a_refused_action_comes_back_as_an_observation_not_a_crash(self):
        from ninny.actions import Action

        observation = self.env.execute(Action(name="write_file", args={"path": "../x", "content": ""}))
        self.assertFalse(observation.ok)
        self.assertEqual(observation.note, "refused")


class PricingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.prices = Path(self._tmp.name) / "prices.json"
        self.prices.write_text(
            json.dumps({"models": {"some/model": {"prompt": 1e-6, "completion": 2e-6, "input_cache_read": 1e-7}}})
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_price_file_wins_over_the_endpoint(self):
        pricing = Pricing("http://127.0.0.1:1/v1", price_file=self.prices)
        self.assertEqual(pricing.for_model("some/model")["prompt"], 1e-6)
        self.assertIn("price file", pricing.source)

    def test_cost_is_tokens_times_price(self):
        pricing = Pricing("http://127.0.0.1:1/v1", price_file=self.prices)
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        self.assertAlmostEqual(pricing.cost("some/model", usage), 1000 * 1e-6 + 500 * 2e-6)

    def test_cached_tokens_are_discounted(self):
        pricing = Pricing("http://127.0.0.1:1/v1", price_file=self.prices)
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 0,
            "prompt_tokens_details": {"cached_tokens": 400},
        }
        self.assertAlmostEqual(pricing.cost("some/model", usage), 600 * 1e-6 + 400 * 1e-7)

    def test_an_unknown_model_costs_None_and_says_so(self):
        pricing = Pricing("http://127.0.0.1:1/v1", price_file=self.prices)
        self.assertIsNone(pricing.cost("nobody/knows", {"prompt_tokens": 10}))
        self.assertIn("unavailable", pricing.describe("nobody/knows"))

    def test_a_dead_endpoint_does_not_raise_it_just_has_no_prices(self):
        pricing = Pricing("http://127.0.0.1:1/v1")
        self.assertIsNone(pricing.for_model("some/model"))


class SandboxTests(unittest.TestCase):
    def test_none_is_a_sandbox_that_says_what_it_is_not(self):
        sandbox = build_sandbox("none")
        self.assertEqual(sandbox.name, "none")
        ok, note = sandbox.plan(Path("."))
        self.assertTrue(ok)
        self.assertIn("NO SANDBOX", note)

    def test_asking_for_an_unknown_sandbox_is_an_error(self):
        with self.assertRaises(SandboxError):
            build_sandbox("chroot")

    def test_asking_for_bwrap_without_one_says_how_to_get_it_without_root(self):
        with self.assertRaises(SandboxError) as caught:
            build_sandbox("bwrap", bwrap_path="/nonexistent/bwrap")
        message = str(caught.exception)
        self.assertIn("apt-get download bubblewrap", message)

    def test_the_agent_does_not_inherit_the_api_key(self):
        import os

        os.environ["NINNY_TEST_SECRET_API_KEY"] = "sk-should-not-be-here"
        try:
            self.assertNotIn("NINNY_TEST_SECRET_API_KEY", child_env())
        finally:
            del os.environ["NINNY_TEST_SECRET_API_KEY"]


if __name__ == "__main__":
    unittest.main()
