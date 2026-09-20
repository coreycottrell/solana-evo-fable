"""Pure signal functions of (prices, thesis-scoped params).

Extracted from v1 strategies (signal_* + _ema/_vol/_respect_side). Exit/cooldown
helpers remain organism-bound for the paper engine; labels/ will replace them
on an injected clock later.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, Sequence, Union

from evobot.models import Genome, Organism, SideBias, Signal, SignalAction, ThesisType


# ---------------------------------------------------------------------------
# Thesis-scoped params (F14 — each thesis owns its entry_threshold unit)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeanReversionParams:
    lookback: int = 20
    entry_threshold: float = 0.85  # z-score
    exit_threshold: float = 0.35


@dataclass(frozen=True)
class MomentumParams:
    lookback: int = 16
    entry_threshold: float = 0.15  # percent points (÷100 → fractional)


@dataclass(frozen=True)
class BreakoutParams:
    lookback: int = 24
    breakout_buffer_bps: float = 3.0


@dataclass(frozen=True)
class LiquidityFadeParams:
    lookback: int = 8
    fade_move_bps: float = 8.0


@dataclass(frozen=True)
class MicroTrendParams:
    lookback: int = 20
    ema_fast: int = 5
    ema_slow: int = 18
    entry_threshold: float = 0.18  # per-mille EMA spread (÷1000)


ThesisParams = Union[
    MeanReversionParams,
    MomentumParams,
    BreakoutParams,
    LiquidityFadeParams,
    MicroTrendParams,
]


class _HasLookback(Protocol):
    lookback: int


def thesis_params_from_genome(thesis: ThesisType, g: Genome) -> ThesisParams:
    """Project the flat organism Genome onto a typed thesis bag."""
    if thesis == ThesisType.MEAN_REVERSION:
        return MeanReversionParams(
            lookback=g.lookback,
            entry_threshold=g.entry_threshold,
            exit_threshold=g.exit_threshold,
        )
    if thesis == ThesisType.MOMENTUM:
        return MomentumParams(lookback=g.lookback, entry_threshold=g.entry_threshold)
    if thesis == ThesisType.BREAKOUT:
        return BreakoutParams(lookback=g.lookback, breakout_buffer_bps=g.breakout_buffer_bps)
    if thesis == ThesisType.LIQUIDITY_FADE:
        return LiquidityFadeParams(lookback=g.lookback, fade_move_bps=g.fade_move_bps)
    if thesis == ThesisType.MICRO_TREND:
        return MicroTrendParams(
            lookback=g.lookback,
            ema_fast=g.ema_fast,
            ema_slow=g.ema_slow,
            entry_threshold=g.entry_threshold,
        )
    raise ValueError(f"unknown thesis {thesis}")


def _ema(prices: Sequence[float], period: int) -> float:
    if not prices:
        return 0.0
    period = max(1, period)
    alpha = 2.0 / (period + 1)
    e = prices[0]
    for p in prices[1:]:
        e = alpha * p + (1 - alpha) * e
    return e


def _vol(prices: Sequence[float]) -> float:
    if len(prices) < 2:
        return 0.0
    rets = [(prices[i] / prices[i - 1] - 1.0) for i in range(1, len(prices))]
    if len(rets) < 2:
        return abs(rets[0]) if rets else 0.0
    return statistics.pstdev(rets)


def _respect_side(action: SignalAction, bias: SideBias) -> SignalAction:
    if bias == SideBias.BOTH:
        return action
    if bias == SideBias.LONG and action == SignalAction.SELL:
        return SignalAction.HOLD
    if bias == SideBias.SHORT and action == SignalAction.BUY:
        return SignalAction.HOLD
    return action


def signal_mean_reversion(prices: Sequence[float], params: MeanReversionParams) -> Signal:
    lookback = max(5, params.lookback)
    if len(prices) < lookback:
        return Signal(action=SignalAction.HOLD, reason="warmup")
    window = list(prices[-lookback:])
    mean = statistics.fmean(window)
    std = statistics.pstdev(window) or 1e-12
    z = (window[-1] - mean) / std
    if z >= params.entry_threshold:
        return Signal(action=SignalAction.SELL, strength=min(1.0, abs(z) / 3), reason=f"mr_z={z:.2f}")
    if z <= -params.entry_threshold:
        return Signal(action=SignalAction.BUY, strength=min(1.0, abs(z) / 3), reason=f"mr_z={z:.2f}")
    if abs(z) <= params.exit_threshold:
        return Signal(action=SignalAction.HOLD, strength=0.0, reason=f"mr_exit_z={z:.2f}")
    return Signal(action=SignalAction.HOLD, reason=f"mr_z={z:.2f}")


def signal_momentum(prices: Sequence[float], params: MomentumParams) -> Signal:
    lookback = max(2, params.lookback)
    if len(prices) < lookback + 1:
        return Signal(action=SignalAction.HOLD, reason="warmup")
    ret = prices[-1] / prices[-1 - lookback] - 1.0
    thr = params.entry_threshold / 100.0
    if ret >= thr:
        return Signal(action=SignalAction.BUY, strength=min(1.0, abs(ret) / thr), reason=f"mom={ret:.4f}")
    if ret <= -thr:
        return Signal(action=SignalAction.SELL, strength=min(1.0, abs(ret) / thr), reason=f"mom={ret:.4f}")
    return Signal(action=SignalAction.HOLD, reason=f"mom={ret:.4f}")


def signal_breakout(prices: Sequence[float], params: BreakoutParams) -> Signal:
    lookback = max(5, params.lookback)
    if len(prices) < lookback + 1:
        return Signal(action=SignalAction.HOLD, reason="warmup")
    hist = list(prices[-(lookback + 1) : -1])
    hi, lo = max(hist), min(hist)
    px = prices[-1]
    buf = params.breakout_buffer_bps / 10_000.0
    if px > hi * (1 + buf):
        return Signal(action=SignalAction.BUY, strength=0.8, reason=f"bo_hi={hi:.6g}")
    if px < lo * (1 - buf):
        return Signal(action=SignalAction.SELL, strength=0.8, reason=f"bo_lo={lo:.6g}")
    return Signal(action=SignalAction.HOLD, reason="no_breakout")


def signal_liquidity_fade(prices: Sequence[float], params: LiquidityFadeParams) -> Signal:
    lookback = max(3, min(params.lookback, 10))
    if len(prices) < lookback + 1:
        return Signal(action=SignalAction.HOLD, reason="warmup")
    short_ret = prices[-1] / prices[-2] - 1.0
    move_bps = abs(short_ret) * 10_000.0
    if move_bps < params.fade_move_bps:
        return Signal(action=SignalAction.HOLD, reason=f"fade_quiet={move_bps:.1f}bps")
    if short_ret > 0:
        return Signal(action=SignalAction.SELL, strength=min(1.0, move_bps / 200), reason=f"fade_up={move_bps:.1f}")
    return Signal(action=SignalAction.BUY, strength=min(1.0, move_bps / 200), reason=f"fade_dn={move_bps:.1f}")


def signal_micro_trend(prices: Sequence[float], params: MicroTrendParams) -> Signal:
    need = max(params.ema_slow, params.lookback) + 1
    if len(prices) < need:
        return Signal(action=SignalAction.HOLD, reason="warmup")
    fast = _ema(prices, params.ema_fast)
    slow = _ema(prices, params.ema_slow)
    spread = (fast - slow) / (slow or 1e-12)
    thr = params.entry_threshold / 1000.0
    if spread > thr:
        return Signal(action=SignalAction.BUY, strength=min(1.0, abs(spread) / thr), reason=f"mt={spread:.5f}")
    if spread < -thr:
        return Signal(action=SignalAction.SELL, strength=min(1.0, abs(spread) / thr), reason=f"mt={spread:.5f}")
    return Signal(action=SignalAction.HOLD, reason=f"mt={spread:.5f}")


SIGNAL_FN = {
    ThesisType.MEAN_REVERSION: signal_mean_reversion,
    ThesisType.MOMENTUM: signal_momentum,
    ThesisType.BREAKOUT: signal_breakout,
    ThesisType.LIQUIDITY_FADE: signal_liquidity_fade,
    ThesisType.MICRO_TREND: signal_micro_trend,
}


def _stops(org: Organism, price: float) -> Optional[Signal]:
    if org.position.qty == 0 or not org.position.avg_entry:
        return None
    entry = org.position.avg_entry
    pnl_bps = (price / entry - 1.0) * 10_000.0
    if org.position.qty < 0:
        pnl_bps = -pnl_bps
    if pnl_bps <= -org.genome.stop_loss_bps:
        return Signal(
            action=SignalAction.SELL if org.position.qty > 0 else SignalAction.BUY,
            strength=1.0,
            reason=f"stop_loss pnl_bps={pnl_bps:.1f}",
        )
    if pnl_bps >= org.genome.take_profit_bps:
        return Signal(
            action=SignalAction.SELL if org.position.qty > 0 else SignalAction.BUY,
            strength=0.9,
            reason=f"take_profit pnl_bps={pnl_bps:.1f}",
        )
    return None


def _in_cooldown(org: Organism, now: datetime) -> bool:
    if org.last_trade_at is None:
        return False
    return (now - org.last_trade_at).total_seconds() < org.genome.cooldown_sec


def _max_hold_exit(org: Organism, now: datetime) -> bool:
    if org.position.qty == 0 or org.position.opened_at is None:
        return False
    return (now - org.position.opened_at).total_seconds() >= org.genome.max_hold_sec


def generate_signal(org: Organism, prices: Sequence[float], now: datetime) -> Signal:
    if not prices:
        return Signal(action=SignalAction.HOLD, reason="no_prices")
    stop = _stops(org, prices[-1])
    if stop is not None:
        return stop
    if _max_hold_exit(org, now):
        return Signal(
            action=SignalAction.SELL if org.position.qty > 0 else SignalAction.BUY,
            strength=0.7,
            reason="max_hold",
        )
    if _in_cooldown(org, now) and org.position.qty == 0:
        return Signal(action=SignalAction.HOLD, reason="cooldown")
    v = _vol(prices[-max(5, org.genome.lookback) :])
    if not (org.genome.vol_filter_min <= v <= org.genome.vol_filter_max):
        if org.position.qty == 0:
            return Signal(action=SignalAction.HOLD, reason="vol_filter")
    params = thesis_params_from_genome(org.thesis_type, org.genome)
    fn = SIGNAL_FN[org.thesis_type]
    sig = fn(prices, params)  # type: ignore[arg-type]
    if org.position.qty != 0:
        closing = (org.position.qty > 0 and sig.action == SignalAction.SELL) or (
            org.position.qty < 0 and sig.action == SignalAction.BUY
        )
        if not closing and sig.action != SignalAction.HOLD:
            return Signal(action=SignalAction.HOLD, reason="flat_only_when_open")
        if (
            org.thesis_type == ThesisType.MEAN_REVERSION
            and "mr_exit" in sig.reason
            and sig.action == SignalAction.HOLD
        ):
            return Signal(
                action=SignalAction.SELL if org.position.qty > 0 else SignalAction.BUY,
                strength=0.5,
                reason="mr_flatten",
            )
        return sig
    action = _respect_side(sig.action, org.genome.side_bias)
    return Signal(action=action, strength=sig.strength, reason=sig.reason)
