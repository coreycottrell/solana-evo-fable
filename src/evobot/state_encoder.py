"""Market-only state encoder — named buckets from tape (MISSION inv 7).

Backfill / judgment state contains NO organism, thesis, side, inventory,
timestamps, absolute prices, tickers or addresses. Numbers arrive as
code-computed named buckets so one call serves every consumer.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Sequence

STATE_V = "market_buckets_v1"

# Keys that must never appear in backfill-style Jev state.
FORBIDDEN_STATE_KEYS = frozenset(
    {
        "ts",
        "timestamp",
        "bar_ts",
        "now",
        "px",
        "price",
        "mid",
        "close",
        "open",
        "high",
        "low",
        "symbol",
        "ticker",
        "mint",
        "address",
        "org",
        "organism",
        "organism_id",
        "thesis",
        "thesis_type",
        "side",
        "side_proposed",
        "inventory",
        "qty",
        "position",
        "cash",
        "island",
        "label",
    }
)

_RET_BUCKETS = (
    ("strong_down", -80.0),
    ("down", -25.0),
    ("flat", 25.0),
    ("up", 80.0),
    ("strong_up", math.inf),
)

_VOL_BUCKETS = (
    ("very_low", 15.0),
    ("low", 40.0),
    ("mid", 90.0),
    ("high", 180.0),
    ("very_high", math.inf),
)

_Z_BUCKETS = (
    ("deep_oversold", -2.0),
    ("oversold", -0.75),
    ("neutral", 0.75),
    ("overbought", 2.0),
    ("deep_overbought", math.inf),
)

_STRETCH_BUCKETS = (
    ("compressed", 0.4),
    ("normal", 1.2),
    ("extended", 2.5),
    ("extreme", math.inf),
)

_TILT_BUCKETS = (
    ("bearish", -0.15),
    ("flat", 0.15),
    ("bullish", math.inf),
)


def _bucket(value: float, table: Sequence[tuple[str, float]]) -> str:
    for name, upper in table:
        if value <= upper:
            return name
    return table[-1][0]


def _ret_bps(prices: Sequence[float], n: int) -> float:
    if len(prices) <= n:
        return 0.0
    a, b = float(prices[-1 - n]), float(prices[-1])
    if a <= 0 or b <= 0:
        return 0.0
    return (b / a - 1.0) * 10_000.0


def _vol_bps(prices: Sequence[float], window: int = 20) -> float:
    if len(prices) < 3:
        return 0.0
    w = list(prices[-(window + 1) :])
    rets = []
    for i in range(1, len(w)):
        if w[i - 1] > 0 and w[i] > 0:
            rets.append(abs(w[i] / w[i - 1] - 1.0) * 10_000.0)
    if not rets:
        return 0.0
    if len(rets) == 1:
        return float(rets[0])
    return float(statistics.pstdev(rets))


def _z_mr(prices: Sequence[float], lookback: int = 20) -> float:
    lb = max(5, lookback)
    if len(prices) < lb:
        return 0.0
    window = [float(x) for x in prices[-lb:]]
    mean = statistics.fmean(window)
    std = statistics.pstdev(window) or 1e-12
    return float((window[-1] - mean) / std)


def _ema(prices: Sequence[float], span: int) -> float:
    if not prices:
        return 0.0
    alpha = 2.0 / (span + 1.0)
    ema = float(prices[0])
    for p in prices[1:]:
        ema = alpha * float(p) + (1.0 - alpha) * ema
    return ema


def encode_market_state(
    prices: Sequence[float],
    *,
    state_v: str = STATE_V,
) -> dict[str, Any]:
    """Build market-only named-bucket state from a price series (mids).

    Absolute levels and identifiers are never included.
    """
    px = [float(p) for p in prices if p is not None and float(p) > 0]
    if len(px) < 2:
        state = {
            "state_v": state_v,
            "tape": "insufficient",
            "ret_1": "flat",
            "ret_5": "flat",
            "ret_20": "flat",
            "vol": "mid",
            "z_mr": "neutral",
            "stretch": "normal",
            "trend_tilt": "flat",
            "n_bars_bucket": "thin",
        }
    else:
        r1 = _ret_bps(px, 1)
        r5 = _ret_bps(px, min(5, len(px) - 1))
        r20 = _ret_bps(px, min(20, len(px) - 1))
        vol = _vol_bps(px, 20)
        z = _z_mr(px, 20)
        # stretch = |last return| / typical vol (unitless ratio → bucket)
        stretch = abs(r1) / max(vol, 1.0)
        fast = _ema(px[-40:], 5) if len(px) >= 5 else px[-1]
        slow = _ema(px[-40:], 20) if len(px) >= 20 else px[-1]
        tilt = (fast / slow - 1.0) if slow > 0 else 0.0
        n = len(px)
        if n < 30:
            n_bucket = "thin"
        elif n < 80:
            n_bucket = "moderate"
        else:
            n_bucket = "rich"
        state = {
            "state_v": state_v,
            "tape": "ok",
            "ret_1": _bucket(r1, _RET_BUCKETS),
            "ret_5": _bucket(r5, _RET_BUCKETS),
            "ret_20": _bucket(r20, _RET_BUCKETS),
            "vol": _bucket(vol, _VOL_BUCKETS),
            "z_mr": _bucket(z, _Z_BUCKETS),
            "stretch": _bucket(stretch, _STRETCH_BUCKETS),
            "trend_tilt": _bucket(tilt, _TILT_BUCKETS),
            "n_bars_bucket": n_bucket,
        }
    assert_backfill_state_clean(state)
    return state


def assert_backfill_state_clean(state: dict[str, Any]) -> None:
    """Raise if state carries identifiers / absolute prices / timestamps."""
    bad = sorted(k for k in state if k.lower() in FORBIDDEN_STATE_KEYS or k in FORBIDDEN_STATE_KEYS)
    # also catch values that look like absolute prices or mint addresses
    for k, v in state.items():
        if isinstance(v, (int, float)) and k not in ("state_v",):
            # numeric raw levels forbidden — buckets are strings
            bad.append(f"{k}=numeric")
        if isinstance(v, str) and v.startswith("So1") and len(v) > 30:
            bad.append(f"{k}=mintish")
    # state_v is a version string, allowed
    bad = [b for b in bad if not str(b).startswith("state_v")]
    if bad:
        raise ValueError(f"backfill state has forbidden fields: {bad}")


def state_fingerprint(state: dict[str, Any]) -> str:
    """Stable short fingerprint of bucket state (for store / logs)."""
    import hashlib
    import json

    blob = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
