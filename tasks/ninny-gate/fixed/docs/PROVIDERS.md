# Providers: pointing Ninny at an endpoint it has never seen

Ninny talks to endpoints through a **wire**: a protocol shape, not a vendor.

```bash
--provider local|openai|openrouter|ollama|llamacpp
--base-url http://host:port/v1     # anything OpenAI-compatible; overrides --provider
--wire chat|completions            # protocol shape
--api-key ...                      # else the provider's environment variable
```

A provider preset is only three facts, in `ninny/model.py`:

```python
PROVIDERS = {
    "local": {"base_url": "http://127.0.0.1:8645/v1", "key_env": "NINNY_API_KEY", "wire": "chat"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "key_env": "NINNY_API_KEY", "wire": "chat"},
}
```

So connecting an OpenAI-compatible server needs no code at all:

```bash
ninny run --task tasks/roman --model my-model \
    --base-url http://127.0.0.1:8080/v1 --api-key sk-whatever
```

## The two wires that ship

| wire | path | actions come back as |
|---|---|---|
| `chat` | `POST {base}/chat/completions` | tool calls (`tools` + `tool_choice: auto`) |
| `completions` | `POST {base}/completions` | fenced blocks in the text |

`completions` is not a historical curiosity. A model that cannot emit a tool call at
all is a real, measured failure mode — `openai/gpt-oss-20b` produced zero valid
actions in 2 runs out of 2 against a tool-calling scaffold — and the honest response
is to let it write the action as text rather than score it as unable to code.

With `--wire completions` the model writes actions like this:

````text
```bash
ls -la
```

```write_file src/thing.py
value = 1
```

```run_tests
```
````

## Adding a third wire

Three methods in `ModelClient`, and nothing else in the codebase has to know. As a
worked example, here is the shape of Anthropic's native `/v1/messages`, which is
**not** OpenAI-compatible and therefore genuinely needs a wire of its own.

### 1. The path

```python
@property
def path(self) -> str:
    if self.wire == "chat":
        return "/chat/completions"
    if self.wire == "completions":
        return "/completions"
    return "/messages"          # new
```

### 2. The request body

`build_body` currently returns an OpenAI-shaped dict. `/v1/messages` differs in ways
that matter:

```python
if self.wire == "messages":
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = []
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "tool":
            turns.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            ]})
        elif m.get("tool_calls"):
            blocks = [{"type": "text", "text": m.get("content") or ""}]
            for call in m["tool_calls"]:
                blocks.append({
                    "type": "tool_use",
                    "id": call["id"],
                    "name": call["function"]["name"],
                    "input": json.loads(call["function"]["arguments"] or "{}"),
                })
            turns.append({"role": "assistant", "content": blocks})
        else:
            turns.append({"role": m["role"], "content": m["content"]})
    body = {"model": self.model, "messages": turns, "max_tokens": self.max_tokens or 4096}
    if system:
        body["system"] = system                      # a top-level field, not a message
    if tools:
        body["tools"] = [
            {"name": t["function"]["name"], "description": t["function"].get("description", ""),
             "input_schema": t["function"]["parameters"]}
            for t in tools
        ]
    return body
```

Note what this exposes: `tools` must be re-shaped (`input_schema`, not `parameters`),
`system` is not a message, and `max_tokens` is **required** rather than optional. A
wire is where a protocol's opinions live, which is exactly why it is a seam and not
a scattering of `if vendor == ...` through the loop.

You will also need a required header, which `ModelClient` already supports:

```python
headers={"anthropic-version": "2023-06-01"}
```

### 3. The reply

```python
if self.wire == "messages":
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    calls = [
        ToolCall(name=b["name"], arguments=b.get("input") or {}, id=b.get("id", ""))
        for b in blocks if b.get("type") == "tool_use"
    ]
    return Response(
        text=text,
        tool_calls=calls,
        usage=_anthropic_usage(data.get("usage") or {}),   # input_tokens -> prompt_tokens
        finish_reason=data.get("stop_reason") or "",
        raw=data,
    )
```

`usage` must be normalised to the OpenAI key names (`prompt_tokens`,
`completion_tokens`, `prompt_tokens_details.cached_tokens`), because pricing and the
trajectory both read them. A wire that forgets this produces runs that look free.

### Then

- Add the wire name to the `if wire not in (...)` guard in `ModelClient.__init__`.
- Add a `PROVIDERS` entry if there is a sensible default `base_url`.
- Add unit tests in `tests/test_model_prompt.py`, the way the other two wires have:
  one for the body, one for the reply. No network needed — `parse_body` and
  `build_body` are pure functions precisely so that this is testable without an
  endpoint.
