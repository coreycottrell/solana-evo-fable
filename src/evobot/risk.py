"""Risk: blocks opens only. Closes always allowed (inv 1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RiskConfig:
    max_notional_per_trade: float = 200.0
    max_position_usd: float = 400.0
    max_open_trades: int = 8
    max_stale_data_sec: float = 600.0
    kill_switch_path: str = "data/KILL"
    slippage_bps: float = 5.0


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def kill_switch_active(self) -> bool:
        return Path(self.config.kill_switch_path).exists()

    def check_order(
        self,
        *,
        notional_usd: float,
        data_age_sec: float,
        would_open: bool,
        cash_usd: float,
        position_notional: float,
        open_trade_count: Optional[int] = None,
    ) -> RiskDecision:
        # Invariant 1: never gate a reduce/close.
        if not would_open:
            return RiskDecision(True, "close_always_ok")

        if self.kill_switch_active():
            return RiskDecision(False, "kill_switch")

        if data_age_sec > self.config.max_stale_data_sec:
            return RiskDecision(False, f"stale data age={data_age_sec:.1f}s")

        if notional_usd > self.config.max_notional_per_trade + 1e-9:
            return RiskDecision(False, "max_notional")

        projected = position_notional + notional_usd
        if projected > self.config.max_position_usd + 1e-9:
            return RiskDecision(False, "max_position")

        open_count = open_trade_count if open_trade_count is not None else (1 if position_notional > 0 else 0)
        if open_count >= self.config.max_open_trades:
            return RiskDecision(False, "max_open_trades")

        if cash_usd < notional_usd:
            return RiskDecision(False, "insufficient_cash")

        return RiskDecision(True, "ok")
