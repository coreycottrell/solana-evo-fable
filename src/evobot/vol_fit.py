"""Tape metrics extract from v1 vol_fit — measure only, no genome nudging.

Takes: measure_tape, TapeMetrics, percentile/ATR helpers.
Drops: score_vol_fit, mutate_toward_vol_fit (F10-adjacent genome rewrite).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Optional, Sequence

# Medium-TF regime multipliers (document once; used by baseline templates).
MEDIUM_ATR_STOP_MULT = 3.5
MEDIUM_ATR_TP_MULT = 5.5


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile; q in [0, 100]. Empty → 0."""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    q = max(0.0, min(100.0, float(q)))
    pos = (len(sorted_vals) - 1) * (q / 100.0)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    w = pos - lo
    return float(sorted_vals[lo]) * (1.0 - w) + float(sorted_vals[hi]) * w


def _abs_ret_bps(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        a, b = float(closes[i - 1]), float(closes[i])
        if a > 0 and b > 0:
            out.append(abs(b / a - 1.0) * 10_000.0)
    return out


def _hl_range_bps(bars: Sequence[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for b in bars:
        h = float(b.get("h") or b.get("high") or 0.0)
        l = float(b.get("l") or b.get("low") or 0.0)
        c = float(b.get("c") or b.get("mid") or b.get("close") or 0.0)
        if c > 0 and h >= l > 0:
            out.append((h - l) / c * 10_000.0)
    return out


def _atr_like_bps(bars: Sequence[dict[str, Any]], period: int = 14) -> float:
    """Wilder-ish ATR from mid OHLC bars, expressed in bps of close."""
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    prev_c = float(bars[0].get("c") or bars[0].get("mid") or 0.0)
    for b in bars[1:]:
        h = float(b.get("h") or b.get("high") or prev_c)
        l = float(b.get("l") or b.get("low") or prev_c)
        c = float(b.get("c") or b.get("mid") or prev_c)
        if prev_c <= 0 or c <= 0:
            prev_c = c
            continue
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr / c * 10_000.0)
        prev_c = c
    if not trs:
        return 0.0
    window = trs[-max(1, period) :]
    return float(sum(window) / len(window))


def _pstdev(vals: Sequence[float]) -> float:
    if len(vals) < 2:
        return abs(float(vals[0])) if vals else 0.0
    mean = sum(vals) / len(vals)
    var = sum((x - mean) ** 2 for x in vals) / len(vals)
    return math.sqrt(var)


@dataclass
class TapeMetrics:
    symbol: str
    n_bars_1m: int = 0
    n_bars_15m: int = 0
    abs_ret_1m_p50_bps: float = 0.0
    abs_ret_1m_p75_bps: float = 0.0
    abs_ret_1m_p90_bps: float = 0.0
    abs_ret_15m_p50_bps: float = 0.0
    abs_ret_15m_p75_bps: float = 0.0
    abs_ret_15m_p90_bps: float = 0.0
    atr_1m_bps: float = 0.0
    atr_15m_bps: float = 0.0
    hl_range_1m_p50_bps: float = 0.0
    hl_range_15m_p50_bps: float = 0.0
    vol_pstdev_1m: float = 0.0
    volume_p50: Optional[float] = None
    volume_p90: Optional[float] = None
    volume_present: bool = False
    insufficient: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def measure_tape(
    pool: Any,
    symbol: str = "SOL",
    *,
    min_bars_1m: int = 60,
) -> TapeMetrics:
    """Compute |r| percentiles, ATR-like, HL range, optional volume from price_pool."""
    symbol = (symbol or "SOL").upper()
    bars_1m = pool.load_bars(symbol, 60) if pool is not None else []
    bars_15m = pool.load_bars(symbol, 900) if pool is not None else []
    m = TapeMetrics(symbol=symbol, n_bars_1m=len(bars_1m), n_bars_15m=len(bars_15m))
    if len(bars_1m) < min_bars_1m:
        m.insufficient = True
        return m

    closes_1m = [float(b.get("c") or b.get("mid") or 0.0) for b in bars_1m]
    closes_1m = [c for c in closes_1m if c > 0]
    rets_1m = _abs_ret_bps(closes_1m)
    rets_1m_s = sorted(rets_1m)
    m.abs_ret_1m_p50_bps = _percentile(rets_1m_s, 50)
    m.abs_ret_1m_p75_bps = _percentile(rets_1m_s, 75)
    m.abs_ret_1m_p90_bps = _percentile(rets_1m_s, 90)
    atr1 = _atr_like_bps(bars_1m, 14)
    if atr1 > max(100.0, m.abs_ret_1m_p90_bps * 8):
        atr1 = m.abs_ret_1m_p75_bps or m.abs_ret_1m_p50_bps
    m.atr_1m_bps = atr1
    hl1 = sorted(_hl_range_bps(bars_1m))
    m.hl_range_1m_p50_bps = _percentile(hl1, 50)

    frac_rets = []
    for i in range(1, len(closes_1m)):
        if closes_1m[i - 1] > 0:
            frac_rets.append(closes_1m[i] / closes_1m[i - 1] - 1.0)
    window = frac_rets[-max(30, min(len(frac_rets), 180)) :]
    if len(window) >= 5:
        abs_w = sorted(abs(x) for x in window)
        med = _percentile(abs_w, 50)
        mad = _percentile(sorted(abs(x - med) for x in abs_w), 50)
        m.vol_pstdev_1m = float(mad * 1.4826) if mad > 0 else _pstdev(window)
    else:
        m.vol_pstdev_1m = _pstdev(window) if window else 0.0

    vols = []
    for b in bars_1m:
        v = b.get("volume")
        if v is None:
            v = b.get("v")
        if v is not None:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if fv > 0:
                vols.append(fv)
    if vols and max(vols) > 10:
        vs = sorted(vols)
        m.volume_p50 = _percentile(vs, 50)
        m.volume_p90 = _percentile(vs, 90)
        m.volume_present = True

    if len(bars_15m) >= 20:
        closes_15 = [float(b.get("c") or b.get("mid") or 0.0) for b in bars_15m]
        closes_15 = [c for c in closes_15 if c > 0]
        r15 = sorted(_abs_ret_bps(closes_15))
        m.abs_ret_15m_p50_bps = _percentile(r15, 50)
        m.abs_ret_15m_p75_bps = _percentile(r15, 75)
        m.abs_ret_15m_p90_bps = _percentile(r15, 90)
        atr15 = _atr_like_bps(bars_15m, 14)
        if atr15 > max(500.0, m.abs_ret_15m_p90_bps * 8):
            atr15 = m.abs_ret_15m_p75_bps or m.abs_ret_15m_p50_bps
        m.atr_15m_bps = atr15
        m.hl_range_15m_p50_bps = _percentile(sorted(_hl_range_bps(bars_15m)), 50)

    return m
