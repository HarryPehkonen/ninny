"""Where bash is allowed to run.

`none` runs commands directly, as you. The file tools are still confined to the
working tree (ninny/env.py), but bash is not: it can reach anything you can.

`bwrap` runs every bash action inside a bubblewrap namespace in which nothing
outside the working tree exists. Not your home directory, and -- the part that
matters for an evaluation -- not any reference solution you keep beside the task.
If the agent can read the acceptance suite then its "own tests" can be written
from the answer key, and both "did it write tests" and "did it write them first"
stop meaning anything.

bubblewrap is Linux-only, so it is never a hard requirement. `none` is the
fallback, and the run says so out loud rather than pretending.

Getting bubblewrap without root, for a trial run (verified on Debian 13):

    apt-get download bubblewrap && dpkg -x bubblewrap_*.deb root
    ./root/usr/bin/bwrap --version
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

#: Mount set measured to be sufficient to compile C++ with g++ 14.2 inside a
#: bubblewrap namespace: g++ and its headers live entirely under /usr.
_RO_BINDS = [("/usr", "/usr"), ("/etc", "/etc")]
_SYMLINKS = [("usr/lib", "/lib"), ("usr/lib64", "/lib64"), ("usr/bin", "/bin"), ("usr/sbin", "/sbin")]


class SandboxError(Exception):
    """The requested sandbox cannot run. Loud, because a silently unsandboxed
    evaluation is worse than one that refuses to start."""


class Sandbox:
    name = "none"

    def wrap(self, command: str, workdir: Path) -> list[str]:
        return ["bash", "-c", command]

    def plan(self, workdir: Path) -> tuple[bool, str]:
        return True, (
            "NO SANDBOX: bash actions run as you and can reach anything you can. "
            "The file tools are confined to the working tree; bash is not. "
            "Use --sandbox bwrap to hide the rest of the machine."
        )

    def check(self, commands: list[str], workdir: Path) -> list[tuple[str, bool, str]]:
        return []

    def hides(self, path: Path, workdir: Path) -> bool | None:
        return None

    def run(self, command: str, workdir: Path, timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.wrap(command, workdir),
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=child_env(),
        )


class BwrapSandbox(Sandbox):
    name = "bwrap"

    def __init__(self, binary: str, share_net: bool = False, binds: list[str] | tuple[str, ...] = ()):
        self.binary = binary
        self.share_net = share_net
        # Extra paths this task's toolchain needs, exposed read-only at the same location.
        # Without them a task whose interpreter lives under a home directory cannot run at
        # all, and the refusal looks like the model's fault.
        self.binds = [str(path) for path in binds if path]

    def wrap(self, command: str, workdir: Path) -> list[str]:
        tree = str(workdir)
        args = [self.binary, "--die-with-parent", "--unshare-all"]
        if self.share_net:
            args.append("--share-net")
        for src, dst in _RO_BINDS:
            args += ["--ro-bind", src, dst]
        for path in self.binds:
            args += ["--ro-bind", path, path]
        for src, dst in _SYMLINKS:
            args += ["--symlink", src, dst]
        args += [
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--setenv", "HOME", "/tmp",
            "--bind", tree, tree,
            "--chdir", tree,
            "bash", "-c", command,
        ]
        return args

    def describe(self) -> str:
        """One line naming what the run can see. Printed at the start of every run."""
        line = (
            f"SANDBOXED with bubblewrap ({self.binary}); "
            + ("network shared" if self.share_net else "network unshared")
        )
        if self.binds:
            line += "; extra read-only binds: " + ", ".join(self.binds)
        return line + "."

    def plan(self, workdir: Path) -> tuple[bool, str]:
        if not os.access(self.binary, os.X_OK):
            return False, f"{self.binary} is not executable"
        try:
            done = self.run("echo ninny-sandbox-ok", workdir, timeout=30)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"sandbox did not start: {type(exc).__name__}: {exc}"
        if done.returncode != 0 or "ninny-sandbox-ok" not in (done.stdout or ""):
            detail = (done.stderr or done.stdout or "").strip()[:300]
            return False, f"sandbox started but the probe failed ({detail})"
        return True, self.describe()

    def check(self, commands: list[str], workdir: Path) -> list[tuple[str, bool, str]]:
        """The task's own preflight commands, run INSIDE the sandbox.

        A sandbox that hides the compiler would score every model as unable to
        build -- a harness-caused failure, and exactly the class of silent defect
        that a hidden gate contract is. So the task declares what must work, and
        the harness refuses to score a run where it does not.
        """
        results = []
        for command in commands:
            try:
                done = self.run(command, workdir, timeout=60)
                output = (done.stdout or "") + (done.stderr or "")
                results.append((command, done.returncode == 0, output.strip()[:200]))
            except (subprocess.TimeoutExpired, OSError) as exc:
                results.append((command, False, f"{type(exc).__name__}: {exc}"))
        return results

    def hides(self, path: Path, workdir: Path) -> bool | None:
        try:
            done = self.run(f"test -e {shlex_quote(str(path))}", workdir, timeout=30)
        except (subprocess.TimeoutExpired, OSError):
            return None
        return done.returncode != 0


def shlex_quote(text: str) -> str:
    import shlex

    return shlex.quote(text)


def child_env() -> dict[str, str]:
    """The environment handed to an action, with obvious secrets removed.

    An agent with a shell can print any environment variable it can see, so the
    harness does not hand it the API key it is being billed against.
    """
    env = dict(os.environ)
    for key in list(env):
        upper = key.upper()
        if any(marker in upper for marker in ("API_KEY", "APIKEY", "SECRET", "TOKEN", "PASSWORD", "_KEY")):
            if upper not in ("GPG_KEY", "SSL_CERT_FILE"):
                env.pop(key, None)
    return env


def find_bwrap(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if os.access(explicit, os.X_OK) else None
    env_path = os.environ.get("NINNY_BWRAP")
    if env_path:
        return env_path
    found = shutil.which("bwrap")
    if found:
        return found
    for candidate in ("/usr/bin/bwrap", os.path.expanduser("~/.local/bin/bwrap")):
        if os.access(candidate, os.X_OK):
            return candidate
    return None


def build_sandbox(
    kind: str,
    bwrap_path: str | None = None,
    share_net: bool = False,
    binds: list[str] | tuple[str, ...] = (),
) -> Sandbox:
    if kind == "none":
        return Sandbox()
    if kind != "bwrap":
        raise SandboxError(f"unknown sandbox {kind!r}; expected 'none' or 'bwrap'")
    binary = find_bwrap(bwrap_path)
    if not binary:
        raise SandboxError(
            "bubblewrap was requested but no bwrap binary was found. Either install it, "
            "point at one with --bwrap-path, or use --sandbox none.\n"
            "Without root, get one like this:\n"
            "    apt-get download bubblewrap && dpkg -x bubblewrap_*.deb root\n"
            "    ninny ... --bwrap-path ./root/usr/bin/bwrap"
        )
    return BwrapSandbox(binary, share_net=share_net, binds=binds)
