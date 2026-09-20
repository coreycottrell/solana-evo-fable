"""Fee math extracted from v1 paper_broker (the reusable leaf).

Transplanted from coreycottrell/solana-evo-bot @ 322a88f — round-trip drag
and soft edge gate only. Full fill/reducer lives elsewhere in v2.
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


def passes_min_edge_gate(
    *,
    size_usd: float,
    strength: float,
    fees: FeesConfig,
) -> bool:
    """Soft entry gate: skip if gas dominates or signal is too weak.

    Swap fee scales with notional (~2 * swap_fee_bps RT, size-invariant in bps).
    Gas does not — tiny clips make gas dominate. Reject when gas-only RT drag
    (bps) exceeds min_net_edge_bps. Also require mild |strength| floor.
    """
    if size_usd <= 0:
        return False
    gas_rt_bps = (2.0 * fees.gas_usd_per_tx / size_usd) * 10_000.0
    if gas_rt_bps > fees.min_net_edge_bps:
        return False
    # strength typically in [0, 1]; map min_net_edge_bps=15 → ~0.075 floor
    min_strength = min(0.5, fees.min_net_edge_bps / 200.0)
    return abs(strength) >= min_strength
