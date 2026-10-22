"""The provider seam: how a reply comes back from an endpoint.

Two wires are implemented and both are exercised against a real endpoint:

    chat         POST {base}/chat/completions    OpenAI-compatible, tool calls
    completions  POST {base}/completions         plain text, no tool calls

The second one is not decoration. A model that cannot emit a tool call at all is
a real and measured failure mode — openai/gpt-oss-20b produced zero valid actions
in 2 runs out of 2 through a tool-calling scaffold — and the honest fix is to let
it write an action as text rather than to score it as unable to code.

Adding a third wire is the point of the seam: a wire is a path, a function from
(messages, tools) to a request body, and a function from the returned JSON to a
Response. See docs/PROVIDERS.md for a worked example.
"""

from __future__ import annotations

import json
import random
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

#: Endpoints that are OpenAI-compatible out of the box. Anything else goes in
#: with --base-url, which is all a wire needs to know.
PROVIDERS: dict[str, dict[str, str]] = {
    "local": {"base_url": "http://127.0.0.1:8645/v1", "key_env": "NINNY_API_KEY", "wire": "chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY", "wire": "chat"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY", "wire": "chat"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "key_env": "NINNY_API_KEY", "wire": "chat"},
    "llamacpp": {"base_url": "http://127.0.0.1:8080/v1", "key_env": "NINNY_API_KEY", "wire": "chat"},
}

TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class ModelError(Exception):
    """A failure that retrying will not fix."""


class TransientError(Exception):
    """A failure worth retrying: timeout, 429, 5xx, connection reset."""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass
class Response:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""
    latency_s: float = 0.0
    raw: dict = field(default_factory=dict)


def flatten_messages(messages: list[dict]) -> str:
    """Render a message list as a single prompt, for endpoints without chat."""
    parts: list[str] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        calls = m.get("tool_calls") or []
        if calls:
            rendered = "\n".join(
                f"[{c.get('function', {}).get('name', '')}] {c.get('function', {}).get('arguments', '')}"
                for c in calls
            )
            content = f"{content}\n{rendered}".strip()
        label = {"system": "System", "assistant": "Assistant", "tool": "Result", "user": "User"}.get(role, role)
        parts.append(f"### {label}\n{content}")
    parts.append("### Assistant")
    return "\n\n".join(parts)


class ModelClient:
    """One endpoint, one model, one wire."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "",
        wire: str = "chat",
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int = 600,
        retries: int = 4,
        headers: dict[str, str] | None = None,
    ):
        if wire not in ("chat", "completions"):
            raise ModelError(
                f"unknown wire {wire!r}; Ninny implements 'chat' and 'completions'. "
                "A new endpoint goes in with --base-url; a new protocol needs a wire "
                "(see docs/PROVIDERS.md)."
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.wire = wire
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries
        self.headers = headers or {}

    # ------------------------------------------------------------------ request
    @property
    def path(self) -> str:
        return "/chat/completions" if self.wire == "chat" else "/completions"

    def build_body(self, messages: list[dict], tools: list[dict] | None) -> dict:
        if self.wire == "chat":
            body: dict = {"model": self.model, "messages": _clean_messages(messages)}
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"
        else:
            body = {"model": self.model, "prompt": flatten_messages(messages)}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        return body

    def parse_body(self, data: dict) -> Response:
        choices = data.get("choices") or [{}]
        choice = choices[0]
        if self.wire == "chat":
            message = choice.get("message") or {}
            text = message.get("content") or ""
            calls: list[ToolCall] = []
            for raw in message.get("tool_calls") or []:
                fn = raw.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"__unparsed__": args}
                calls.append(ToolCall(name=fn.get("name", ""), arguments=args or {}, id=raw.get("id", "")))
            legacy = message.get("function_call")
            if not calls and isinstance(legacy, dict):
                args = legacy.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"__unparsed__": args}
                calls.append(ToolCall(name=legacy.get("name", ""), arguments=args or {}))
        else:
            text = choice.get("text") or ""
            calls = []
        return Response(
            text=text or "",
            tool_calls=calls,
            usage=data.get("usage") or {},
            finish_reason=choice.get("finish_reason") or "",
            raw=data,
        )

    # ------------------------------------------------------------------- talking
    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> Response:
        body = self.build_body(messages, tools)
        url = self.base_url + self.path
        failure: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                started = time.time()
                data = self._post(url, body)
                response = self.parse_body(data)
                response.latency_s = time.time() - started
                return response
            except TransientError as exc:
                failure = exc
                if attempt >= self.retries:
                    break
                time.sleep(min(2 ** attempt, 30) + random.random())
        raise ModelError(f"{self.wire} call to {url} failed after {self.retries + 1} attempts: {failure}")

    def _post(self, url: str, body: dict) -> dict:
        payload = json.dumps(body).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.headers)
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = _short(exc.read().decode("utf-8", "replace"))
            if exc.code in TRANSIENT_STATUS:
                raise TransientError(f"HTTP {exc.code}: {detail}") from exc
            raise ModelError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise TransientError(f"{type(exc).__name__}: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            raise ModelError(f"endpoint returned non-JSON ({_short(raw.decode('utf-8', 'replace'))})") from exc
        if isinstance(data, dict) and data.get("error"):
            raise ModelError(f"endpoint error: {_short(json.dumps(data['error']))}")
        return data


def _clean_messages(messages: list[dict]) -> list[dict]:
    """Some endpoints reject null content on assistant turns carrying tool calls."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("content") is None:
            m["content"] = ""
        out.append(m)
    return out


def _short(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."
