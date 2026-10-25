"""What a run actually cost, from the endpoint's own prices.

Ninny never invents a number. If the price is unknown the cost is reported as
unknown, because a bundled price table that silently disagrees with your provider
is how an evaluation publishes costs that are wrong by 2-5x. (Measured: Aider's
bundled deepseek table says $0.14/$0.28 per M for a model this proxy bills at
$0.106/$0.513 per M.)

Precedence: an explicit --price-file wins; otherwise the endpoint's /models is
consulted; otherwise the cost is None and the caller must say so.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path


def _load_price_file(path: str | Path) -> dict[str, dict]:
    data = json.loads(Path(path).expanduser().read_text())
    models = data.get("models", data)
    out: dict[str, dict] = {}
    for model_id, p in models.items():
        if not isinstance(p, dict):
            continue
        entry = {}
        for key, aliases in (
            ("prompt", ("prompt", "input", "in")),
            ("completion", ("completion", "output", "out")),
            ("input_cache_read", ("input_cache_read", "cache_read", "cached")),
        ):
            for alias in aliases:
                if p.get(alias) is not None:
                    entry[key] = float(p[alias])
                    break
        if entry:
            out[model_id] = entry
    return out


def _candidates(model_id: str) -> list[str]:
    """Model ids are written with and without a provider prefix; try both."""
    out = [model_id]
    if "/" in model_id:
        out.append(model_id.split("/", 1)[1])
    return out


class Pricing:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        price_file: str | Path | None = None,
        fetch: bool = True,
        timeout: int = 20,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.fetch = fetch
        self._override = _load_price_file(price_file) if price_file else None
        self._catalog: dict[str, dict] | None = None
        self.source = f"price file {price_file}" if price_file else "endpoint /models"

    def _catalog_models(self) -> dict[str, dict]:
        if self._catalog is not None:
            return self._catalog
        if not self.fetch:
            self._catalog = {}
            return self._catalog
        try:
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            req = urllib.request.Request(self.base_url + "/models", headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self._catalog = {m["id"]: m for m in json.load(r).get("data", [])}
        except Exception:
            # An endpoint that does not publish a catalogue is not an error; it
            # just means the cost will be reported as unknown.
            self._catalog = {}
        return self._catalog

    def for_model(self, model_id: str) -> dict | None:
        if self._override is not None:
            for cand in _candidates(model_id):
                if cand in self._override:
                    return self._override[cand]
        for cand in _candidates(model_id):
            model = self._catalog_models().get(cand) or {}
            prices = model.get("pricing") or {}
            if not prices:
                continue
            entry = {}
            for key, aliases in (
                ("prompt", ("prompt", "input")),
                ("completion", ("completion", "output")),
                ("input_cache_read", ("input_cache_read", "cache_read")),
            ):
                for alias in aliases:
                    if prices.get(alias) is not None:
                        try:
                            entry[key] = float(prices[alias])
                        except (TypeError, ValueError):
                            pass
                        break
            if entry:
                return entry
        return None

    def cost(self, model_id: str, usage: dict) -> float | None:
        prices = self.for_model(model_id)
        if not prices:
            return None
        details = usage.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0) if isinstance(details, dict) else 0
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        fresh = max(prompt_tokens - cached, 0)
        total = fresh * float(prices.get("prompt", 0.0))
        total += completion_tokens * float(prices.get("completion", 0.0))
        if cached:
            total += cached * float(prices.get("input_cache_read", prices.get("prompt", 0.0)))
        return total

    def describe(self, model_id: str) -> str:
        prices = self.for_model(model_id)
        if not prices:
            return f"pricing unavailable for {model_id} (source: {self.source})"
        bits = [f"${prices['prompt'] * 1e6:.3f}/M in", f"${prices['completion'] * 1e6:.3f}/M out"]
        if "input_cache_read" in prices:
            bits.append(f"${prices['input_cache_read'] * 1e6:.3f}/M cached")
        return ", ".join(bits) + f"  (source: {self.source})"
