"""The loop, and the record it leaves behind.

One model call per step, at least one action per call, a step limit, format-error
repair when a reply contains no usable action, and a trajectory that keeps every
observation. The differences from mini-swe-agent are the ones that were paid for
in measurements: four actions instead of one, a test-first gate, path
confinement, and a cost that is either real or admitted to be unknown.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from ninny import SUBMIT_SENTINEL, UPSTREAM, UPSTREAM_URL, __version__
from ninny.actions import TOOLS, parse_reply, validate
from ninny.artifacts import tree_digest
from ninny.prompt import SYSTEM_TEMPLATE, format_error_message, render_instance
from ninny.tdd import PHASE_LABELS


@dataclass
class Step:
    step: int
    action: str
    args: dict
    allowed: bool
    observation: str
    exit_code: int | None = None


@dataclass
class RunResult:
    exit_status: str = ""
    steps: int = 0
    api_calls: int = 0
    usage: dict = field(default_factory=dict)
    cost: float | None = None
    cost_note: str = ""
    tdd: dict = field(default_factory=dict)
    final_output: str = ""
    wall_time_s: float = 0.0
    run_dir: Path | None = None
    model: str = ""
    wire: str = "chat"

    def summary(self) -> str:
        cost = f"${self.cost:.4f}" if self.cost is not None else f"unknown ({self.cost_note})"
        verdict = self.tdd.get("verdict", "n/a")
        return (
            f"exit={self.exit_status}  steps={self.steps}  api_calls={self.api_calls}  "
            f"cost={cost}\n"
            f"tokens: in={self.usage.get('prompt_tokens', 0)} out={self.usage.get('completion_tokens', 0)}\n"
            f"test-first: {verdict}  (mode={self.tdd.get('mode')}, "
            f"red_step={self.tdd.get('red_step')}{self._red_exit_note()}, "
            f"first_src_step={self.tdd.get('first_src_step')}, refusals={len(self.tdd.get('refusals', []))}, "
            f"bypasses={len(self.tdd.get('bypass_detected', []))}, "
            f"suite_frozen={self._seal_note()})"
        )

    def _seal_note(self) -> str:
        """Whether the suite handed back is the suite that went red.

        `n/a` when no red was banked -- there is nothing to seal, and `yes` there would
        claim a guarantee the run never earned. `no` names the one case where `red-first`
        is true and the shipped tests are nonetheless not the tests that failed.
        """
        frozen = self.tdd.get("suite_frozen_since_red")
        if frozen is None:
            return "n/a (no red)"
        added = self.tdd.get("tests_added_after_red", [])
        extra = f", {len(added)} added after the red: {', '.join(added)}" if added else ""
        how = "read-only" if self.tdd.get("sealed_readonly") else "reported only"
        if frozen:
            return f"yes (sealed at step {self.tdd.get('seal_step')}, {how}{extra})"
        changed = self.tdd.get("suite_changed_after_red", [])
        return f"no ({len(changed)} sealed file(s) changed after the red: {', '.join(changed)}{extra})"

    def _red_exit_note(self) -> str:
        """Which exit code the banked RED came from.

        Printed next to `red_step` because the number alone is not the whole claim: a
        red is only an observation if the suite ran, and exit 2 means it did not. The
        codes are the task contract (see `ninny/tdd.py`).
        """
        if self.tdd.get("red_step") is None or self.tdd.get("red_exit") is None:
            return ""
        return f" (exit {self.tdd['red_exit']})"


class Agent:
    def __init__(
        self,
        client,
        environment,
        policy,
        task,
        workdir: str | Path,
        run_dir: str | Path,
        pricing=None,
        step_limit: int = 40,
        wall_time_limit: int = 0,
        max_format_errors: int = 3,
        sandbox_note: str = "",
        prompt_mode: str = "",
        log=print,
    ):
        self.client = client
        self.env = environment
        # The sealed suite is made read-only once, at the step the red is banked.
        self._sealed_applied = False
        self.policy = policy
        self.task = task
        self.workdir = Path(workdir)
        self.run_dir = Path(run_dir)
        self.pricing = pricing
        self.step_limit = step_limit
        self.wall_time_limit = wall_time_limit
        self.max_format_errors = max_format_errors
        self.sandbox_note = sandbox_note
        # What the model is TOLD is a different axis from what the gate BLOCKS.
        # Empty means "same as the gate", so every existing arm keeps its behaviour.
        self.prompt_mode = prompt_mode
        self.log = log
        self.messages: list[dict] = []
        self.steps: list[Step] = []

    # ---------------------------------------------------------------------- run
    def run(self) -> RunResult:
        result = RunResult(model=self.client.model, wire=self.client.wire, run_dir=self.run_dir)
        started = time.time()
        self._started_at = started
        state = self.policy.new_state()
        instance = render_instance(
            self.task, str(self.workdir), self.prompt_mode or self.policy.mode, self.sandbox_note
        )
        self.messages = [
            {"role": "system", "content": SYSTEM_TEMPLATE},
            {"role": "user", "content": instance},
        ]
        format_errors = 0
        tools = TOOLS if self.client.wire == "chat" else None

        for step in range(1, self.step_limit + 1):
            if self.wall_time_limit and time.time() - started > self.wall_time_limit:
                result.exit_status = "WallTimeLimit"
                break
            response = self.client.complete(self.messages, tools)
            result.api_calls += 1
            _merge_usage(result.usage, response.usage)
            self.log(
                f"[step {step}] {PHASE_LABELS.get(state.phase, state.phase)}  "
                f"{response.latency_s:.1f}s  {_usage_line(response.usage)}"
            )

            actions, note = parse_reply(response)
            if not actions:
                format_errors += 1
                self.messages.append({"role": "assistant", "content": response.text or ""})
                self.messages.append(
                    {"role": "user", "content": format_error_message(response, note, self.client.wire)}
                )
                self.log(f"[step {step}] no action in the reply (format error {format_errors})")
                if format_errors > self.max_format_errors:
                    result.exit_status = "RepeatedFormatError"
                    break
                continue
            format_errors = 0

            assistant = self._assistant_message(response)
            self.messages.append(assistant)
            use_tool_role = bool(assistant.get("tool_calls"))

            for index, action in enumerate(actions):
                call_id = self._call_id(assistant, index)
                problem = validate(action)
                if problem:
                    self._record(step, action, False, problem, None)
                    self._append_observation(use_tool_role, call_id, f"Error: {problem}")
                    continue

                suspect = ""
                if action.name == "bash":
                    suspect = self.env.looks_like_src_write(action.command)
                refusal = self.policy.gate(action, state, step, suspect)
                if not refusal and action.is_submit():
                    refusal = self.policy.gate_submit_reverse(state, step)
                if refusal:
                    self._record(step, action, False, refusal, None)
                    self._append_observation(use_tool_role, call_id, refusal)
                    self.log(f"[step {step}] refused: {action.describe()}")
                    continue

                observation = self.env.execute(action)
                self.policy.observe(action, observation, state, step)
                self.policy.observe_tree(state, step)
                self._enforce_seal(state)
                # What the model is told and what the record says it was told are the same
                # string: the phase note is prepended to the observation itself, because a
                # note in the harness's own log is a note the model never reads.
                told = observation.render()
                note = self.policy.note_for(action, observation, state)
                if note:
                    told = f"{note}\n{told}"
                self._record(step, action, True, told, observation.exit_code)
                self._append_observation(use_tool_role, call_id, told)
                self.log(f"[step {step}] {action.describe()}  -> exit {observation.exit_code}")

                if action.is_submit():
                    result.final_output = observation.output
                    result.exit_status = "Submitted"

            result.steps = step
            if result.exit_status:
                break

        if not result.exit_status:
            result.exit_status = "StepLimit"

        result.wall_time_s = time.time() - started
        self.policy.close_seal(state)
        result.tdd = state.as_dict()
        if self.pricing is not None:
            result.cost = self.pricing.cost(self.client.model, result.usage)
            if result.cost is None:
                result.cost_note = self.pricing.describe(self.client.model)
        self._write_trajectory(result)
        return result

    # ------------------------------------------------------------------ helpers
    def _assistant_message(self, response) -> dict:
        message: dict = {"role": "assistant", "content": response.text or ""}
        if response.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id or f"call_{index}",
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for index, call in enumerate(response.tool_calls)
            ]
        return message

    def _call_id(self, assistant: dict, index: int) -> str:
        calls = assistant.get("tool_calls") or []
        if index < len(calls):
            return calls[index]["id"]
        return f"call_{index}"

    def _append_observation(self, use_tool_role: bool, call_id: str, text: str) -> None:
        if use_tool_role:
            self.messages.append({"role": "tool", "tool_call_id": call_id, "content": text})
        else:
            # A reply that used fenced blocks instead of tool calls has no tool
            # role to answer into; the result goes back as the next user turn.
            self.messages.append({"role": "user", "content": f"Result:\n{text}"})

    def _enforce_seal(self, state) -> None:
        """Make the sealed suite read-only the moment a red is banked.

        The gate refuses a `write_file` into a sealed test file, but a shell heredoc is not a
        `write_file`: the first live `split` run rewrote its failing test through one and the
        gate never saw it. So the seal is enforced where the shell cannot route around it --
        the sandbox binds each sealed file read-only for the remainder of the run.

        Reported either way, and the record says which: a seal that is only *reported* is a
        different claim from one that is *enforced*, and collapsing them would let the weaker
        one read as the stronger.
        """
        sealed = state.sealed or {}
        if not sealed or self._sealed_applied:
            return
        self._sealed_applied = True
        names = ", ".join(sorted(sealed))
        state.sealed_readonly = self.env.sandbox.seal_readonly(
            [str(self.workdir / rel) for rel in sealed]
        )
        if state.sealed_readonly:
            self.log(f"[seal] read-only for the rest of the run: {names}")
        else:
            self.log(
                f"[seal] sealed in the record but NOT enforced -- sandbox "
                f"{self.env.sandbox.name!r} cannot make a path read-only: {names}"
            )

    def _record(self, step: int, action, allowed: bool, observation: str, exit_code) -> None:
        self.steps.append(
            Step(step=step, action=action.name, args=action.args, allowed=allowed,
                 observation=observation, exit_code=exit_code)
        )

    # ---------------------------------------------------------------- the record
    def _write_trajectory(self, result: RunResult) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "ninny": {
                "version": __version__,
                "fork_of": UPSTREAM,
                "upstream": UPSTREAM_URL,
            },
            "run": {
                "model": result.model,
                "wire": result.wire,
                "task": self.task.name,
                "task_root": str(self.task.root),
                "workdir": str(self.workdir),
                "sandbox": self.env.sandbox.name,
                "tdd_mode": self.policy.mode,
                "tdd_prompt_mode": self.prompt_mode or self.policy.mode,
                "require_green": self.policy.require_green,
                "step_limit": self.step_limit,
                # The inputs, hashed, so a finished number can be traced back to the
                # exact spec and starting tree it came from.
                "spec_sha256": hashlib.sha256(self.task.spec.encode()).hexdigest()[:16],
                "tree_sha256": tree_digest(self.task.tree_src),
                "test_cmd": self.task.test_cmd,
                "oracle_cmd": self.task.oracle_cmd,
                "started": _ts(self._started_at),
                "finished": _ts(time.time()),
            },
            "messages": self.messages,
            "steps": [step.__dict__ for step in self.steps],
            "result": {
                "exit_status": result.exit_status,
                "steps": result.steps,
                "api_calls": result.api_calls,
                "usage": result.usage,
                "cost_usd": result.cost,
                "cost_note": result.cost_note,
                "wall_time_s": round(result.wall_time_s, 1),
                "tdd": result.tdd,
                "final_output": result.final_output,
            },
        }
        (self.run_dir / "trajectory.json").write_text(json.dumps(payload, indent=2))
        (self.run_dir / "result.json").write_text(json.dumps(payload["result"], indent=2))
        (self.run_dir / "trajectory.md").write_text(self._trajectory_markdown(result))
        result.trajectory = self.run_dir / "trajectory.json"

    def _trajectory_markdown(self, result: RunResult) -> str:
        lines = [
            f"# {self.task.name} -- {result.model}",
            "",
            f"- verdict: **{result.tdd.get('verdict')}** (tdd mode `{self.policy.mode}`)",
            f"- exit: `{result.exit_status}` after {result.steps} steps / {result.api_calls} model calls",
            f"- cost: "
            + (f"${result.cost:.4f}" if result.cost is not None else f"unknown -- {result.cost_note}"),
            f"- sandbox: `{self.env.sandbox.name}`",
            "",
            "| step | action | allowed | exit |",
            "|---|---|---|---|",
        ]
        for step in self.steps:
            detail = step.args.get("command") or step.args.get("path") or ""
            detail = str(detail).splitlines()[0][:70] if detail else ""
            lines.append(f"| {step.step} | `{step.action}` {detail} | {'yes' if step.allowed else 'NO'} | {step.exit_code} |")
        lines += ["", "## Observations", ""]
        for step in self.steps:
            lines += [f"### step {step.step}: `{step.action}`", "", "```", step.observation[:2000], "```", ""]
        return "\n".join(lines)


def _merge_usage(total: dict, usage: dict) -> None:
    for key, value in (usage or {}).items():
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value
        elif isinstance(value, dict):
            total.setdefault(key, {})
            _merge_usage(total[key], value)


def _usage_line(usage: dict) -> str:
    if not usage:
        return "no usage reported"
    return f"in={usage.get('prompt_tokens', 0)} out={usage.get('completion_tokens', 0)}"


def _ts(value) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(value))
