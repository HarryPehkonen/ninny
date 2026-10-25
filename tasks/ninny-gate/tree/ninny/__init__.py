"""Ninny — a tiny coding-agent harness.

A fork of mini-swe-agent (MIT) re-implemented on the standard library, with a
test-first state machine, path confinement for the file tools, and an optional
bubblewrap sandbox.

Nothing in this package imports anything outside the standard library, on
purpose: the point of the exercise is that a harness this small does not need a
framework, and that `litellm`'s transitive `mcp` dependency is avoidable.
"""

__version__ = "0.1.0"

#: The run ends when the model emits this inside a bash action. Kept from
#: mini-swe-agent so the prompt and the model's habit both carry over.
SUBMIT_SENTINEL = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"

UPSTREAM = "mini-swe-agent 2.4.6"
UPSTREAM_URL = "https://github.com/SWE-agent/mini-swe-agent"
UPSTREAM_COPYRIGHT = "Copyright (c) 2025 Kilian A. Lieret and Carlos E. Jimenez"
