"""OpenRouter Decisions API client — Jev models only.

Hard rules:
- Allowlist: typesafe/jev-1.13 and optionally ~typesafe/jev-latest.
- Endpoint: POST https://openrouter.ai/api/alpha/decisions ONLY.
- Never log or print the API key.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

ALLOWED_MODELS = frozenset({"typesafe/jev-1.13", "~typesafe/jev-latest"})
DEFAULT_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
HTTP_REFERER = "https://github.com/coreycottrell/solana-evo-fable"
X_TITLE = "solana-evo-fable"


class JevModelNotAllowed(ValueError):
    """Raised before HTTP when model id is not on the allowlist."""


class JevError(RuntimeError):
    """Transport / API failure (timeout, HTTP error, bad payload)."""


@dataclass
class JevUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    @classmethod
    def from_dict(cls, raw: Optional[dict[str, Any]]) -> "JevUsage":
        if not raw:
            return cls()
        return cls(
            input_tokens=int(raw.get("input_tokens") or raw.get("prompt_tokens") or 0),
            output_tokens=int(raw.get("output_tokens") or raw.get("completion_tokens") or 0),
            cost=float(raw.get("cost") or 0.0),
        )


@dataclass
class JevResult:
    model: str
    answers: dict[str, Any]
    usage: JevUsage = field(default_factory=JevUsage)
    id: str = ""
    provider: str = ""
    mocked: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        """Compact summary for logs / CLI (no secrets)."""
        out: dict[str, Any] = {
            "model": self.model,
            "id": self.id,
            "provider": self.provider,
            "mocked": self.mocked,
            "cost": self.usage.cost,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "answers": {},
        }
        for qid, ans in (self.answers or {}).items():
            if not isinstance(ans, dict):
                out["answers"][qid] = ans
                continue
            t = ans.get("type")
            entry: dict[str, Any] = {"type": t}
            if t == "noul" or "noul" in ans:
                entry["noul"] = ans.get("noul")
            if t == "choice" or "choice" in ans:
                entry["choice"] = ans.get("choice")
                entry["confidence"] = ans.get("confidence")
            if t == "score" or "score" in ans:
                entry["score"] = ans.get("score")
                entry["confidence"] = ans.get("confidence")
            out["answers"][qid] = entry
        return out

    def to_persist_dict(self) -> dict[str, Any]:
        """Serializable blob for data/jev_last.json (no secrets)."""
        return {
            "model": self.model,
            "answers": self.answers,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "cost": self.usage.cost,
            },
            "id": self.id,
            "provider": self.provider,
            "mocked": self.mocked,
        }


def assert_model_allowed(model: str) -> str:
    mid = (model or "").strip()
    if mid not in ALLOWED_MODELS:
        raise JevModelNotAllowed(
            f"model {mid!r} rejected — allowlist={sorted(ALLOWED_MODELS)}"
        )
    return mid


def _load_env_file(path: Path) -> None:
    """Load KEY=VALUE from .env into os.environ if not already set. Never prints values."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


def resolve_api_key(*, project_root: Optional[Path] = None) -> Optional[str]:
    """Return OPENROUTER_API_KEY from env or project .env; never log it."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    roots: list[Path] = []
    if project_root is not None:
        roots.append(project_root)
    roots.append(Path.cwd())
    # package → src → project root
    here = Path(__file__).resolve()
    roots.append(here.parents[2])
    for root in roots:
        _load_env_file(root / ".env")
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if key:
            return key
    return None


def _mock_answers(questions: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fake answers for tests / offline (stable hash of keys)."""
    seed = sum(ord(c) for c in json.dumps(sorted(questions.keys()), sort_keys=True))
    seed += int(abs(float(state.get("px") or 0)) * 100) % 97
    answers: dict[str, Any] = {}
    for qid, q in questions.items():
        qtype = (q.get("type") or "").lower() if isinstance(q, dict) else ""
        if qtype == "noul":
            # stable-ish values in (0,1)
            n = ((seed + sum(ord(c) for c in qid) * 17) % 100) / 100.0
            # bias toxic/abstain low so mock trades can pass
            if "toxic" in qid or "abstain" in qid:
                n = min(n, 0.35)
            if "liquidity" in qid:
                n = min(n, 0.40)
            answers[qid] = {"type": "noul", "noul": round(n, 4)}
        elif qtype == "choice":
            raw_crit = q.get("criteria") if isinstance(q, dict) else None
            if isinstance(raw_crit, dict):
                criteria = list(raw_crit.keys())
            elif isinstance(raw_crit, list):
                criteria = list(raw_crit)
            else:
                criteria = ["other"]
            if not criteria:
                criteria = ["other"]
            idx = (seed + sum(ord(c) for c in qid)) % len(criteria)
            choice = criteria[idx]
            # Prefer regime/direction alignment with proposed side when possible
            side = str(state.get("side_proposed") or "").upper()
            island = str(state.get("island") or "")
            if qid == "regime" and "trending_up" in criteria and "trending_down" in criteria:
                if island == "contrarian" and "mean_reverting" in criteria:
                    choice = "mean_reverting"
                elif side == "BUY":
                    choice = "trending_up"
                elif side == "SELL":
                    choice = "trending_down"
            if qid == "direction" and "up" in criteria and "down" in criteria:
                if side == "BUY":
                    choice = "up"
                elif side == "SELL":
                    choice = "down"
            probs = {c: (0.7 if c == choice else 0.3 / max(1, len(criteria) - 1)) for c in criteria}
            answers[qid] = {
                "type": "choice",
                "choice": choice,
                "probabilities": probs,
                "confidence": 0.82,
            }
        elif qtype == "score":
            criteria = list(q.get("criteria") or []) if isinstance(q, dict) else []
            if not criteria:
                criteria = ["poor", "weak", "adequate", "strong", "excellent"]
            # score ~2.1 (adequate+) so min_setup gates can pass
            score = 2.0 + ((seed + len(qid)) % 10) / 10.0
            legend = {c: float(i) for i, c in enumerate(criteria)}
            answers[qid] = {
                "type": "score",
                "score": round(score, 4),
                "legend": legend,
                "probabilities": {c: 1.0 / len(criteria) for c in criteria},
                "confidence": 0.75,
            }
        else:
            answers[qid] = {"type": qtype or "unknown"}
    return answers


class JevClient:
    """Thin Decisions API wrapper with allowlist + mock mode."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout_sec: float = 20.0,
        api_key: Optional[str] = None,
        project_root: Optional[Path] = None,
        force_mock: Optional[bool] = None,
    ) -> None:
        self.model = assert_model_allowed(model)
        ep = (endpoint or DEFAULT_ENDPOINT).rstrip("/")
        if ep != DEFAULT_ENDPOINT.rstrip("/") and "openrouter.ai/api/alpha/decisions" not in ep:
            raise JevError(
                f"endpoint must be Decisions API ({DEFAULT_ENDPOINT}), got {endpoint!r}"
            )
        self.endpoint = ep
        self.timeout_sec = float(timeout_sec)
        self._project_root = project_root
        env_mock = os.environ.get("EVO_BOT_JEV_MOCK", "0") == "1"
        self._force_mock = bool(force_mock) if force_mock is not None else env_mock
        self._api_key = api_key  # may be None; resolved lazily
        self._resolved_key: Optional[str] = None

    def _key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        if self._resolved_key is not None:
            return self._resolved_key or None
        self._resolved_key = resolve_api_key(project_root=self._project_root) or ""
        return self._resolved_key or None

    @property
    def mock_mode(self) -> bool:
        if self._force_mock:
            return True
        return not bool(self._key())

    def decide(self, state: dict[str, Any], questions: dict[str, Any]) -> JevResult:
        """Call Decisions API (or mock). Rejects non-allowlisted models before HTTP."""
        model = assert_model_allowed(self.model)
        if not questions:
            raise JevError("questions must be non-empty")
        if self.mock_mode:
            answers = _mock_answers(questions, state or {})
            return JevResult(
                model=f"{model}-mock",
                answers=answers,
                usage=JevUsage(input_tokens=0, output_tokens=0, cost=0.0),
                id="mock-dec",
                provider="mock",
                mocked=True,
                raw={"answers": answers, "mocked": True},
            )

        key = self._key()
        if not key:
            # should be unreachable due to mock_mode, but keep safe
            answers = _mock_answers(questions, state or {})
            return JevResult(
                model=f"{model}-mock",
                answers=answers,
                usage=JevUsage(),
                id="mock-dec",
                provider="mock",
                mocked=True,
            )

        body = {"model": model, "state": state, "questions": questions}
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": HTTP_REFERER,
            "X-OpenRouter-Title": X_TITLE,
        }
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.post(self.endpoint, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise JevError(f"Jev timeout after {self.timeout_sec}s") from exc
        except httpx.HTTPError as exc:
            raise JevError(f"Jev HTTP error: {exc}") from exc

        if resp.status_code >= 400:
            detail = ""
            try:
                err = resp.json().get("error") or {}
                msg = err.get("message") if isinstance(err, dict) else str(err)
                if isinstance(msg, str):
                    detail = msg[:240].replace("\n", " ")
            except Exception:  # noqa: BLE001
                detail = ""
            raise JevError(f"Jev HTTP {resp.status_code}" + (f": {detail}" if detail else ""))

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise JevError("Jev response was not JSON") from exc

        answers = data.get("answers") or {}
        if not isinstance(answers, dict):
            raise JevError("Jev response missing answers object")

        return JevResult(
            model=str(data.get("model") or model),
            answers=answers,
            usage=JevUsage.from_dict(data.get("usage") if isinstance(data.get("usage"), dict) else None),
            id=str(data.get("id") or ""),
            provider=str(data.get("provider") or ""),
            mocked=False,
            raw=data,
        )


def persist_jev_result(path: str | Path, result: JevResult) -> None:
    """Write last Jev result to JSON (no secrets)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result.to_persist_dict(), indent=2, default=str) + "\n", encoding="utf-8")
