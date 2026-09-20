"""Fee math extracted from v1 paper_broker (the reusable leaf).

Transplanted from coreycottrell/solana-evo-bot @ 322a88f — round-trip drag,
soft edge gate, fill price, fee components. Full fill/reducer lives in broker.py.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeesConfig:
    """Solana Jupiter-style paper costs (USD)."""

    gas_usd_per_tx: float = 0.03
    swap_fee_bps: float = 10.0
    min_net_edge_bps: float = 15.0  # soft entry gate after fee drag


def round_trip_fee_drag_bps(size_usd: float, fees: FeesConfig) -> float:
    """Round-trip fee drag in bps of notional: 2*(gas + swap_fee)."""
    if size_usd <= 0:
        return float("inf")
    gas = fees.gas_usd_per_tx
    swap = size_usd * fees.swap_fee_bps / 10_000.0
    rt_usd = 2.0 * (gas + swap)
    return rt_usd / size_usd * 10_000.0


def fee_components(notional_usd: float, fees: FeesConfig) -> tuple[float, float, float]:
    """Return (gas_usd, swap_fee_usd, total_usd)."""
    gas = float(fees.gas_usd_per_tx)
    swap = float(notional_usd) * fees.swap_fee_bps / 10_000.0
    return gas, swap, gas + swap


def fill_price(mid: float, side: str, slippage_bps: float) -> float:
    slip = slippage_bps / 10_000.0
    if side == "buy":
        return mid * (1.0 + slip)
    return mid * (1.0 - slip)


def passes_min_edge_gate(
    *,
    size_usd: float,
    strength: float,
    fees: FeesConfig,
) -> bool:
    """Soft entry gate: skip if gas dominates or signal is too weak.

    Also requires round-trip fee drag to be finite and size sensible.
    """
    if size_usd <= 0:
        return False
    # Use round_trip explicitly so the leaf is on the hot path.
    drag = round_trip_fee_drag_bps(size_usd, fees)
    if not (drag < float("inf")):
        return False
    gas_rt_bps = (2.0 * fees.gas_usd_per_tx / size_usd) * 10_000.0
    if gas_rt_bps > fees.min_net_edge_bps:
        return False
    min_strength = min(0.5, fees.min_net_edge_bps / 200.0)
    return abs(strength) >= min_strength
