"""Pure fill + book reducer. Risk blocks opens only; closes never gated."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from evobot.fees import FeesConfig, fee_components, fill_price as fees_fill_price
from evobot.models import Organism, Position, SignalAction
from evobot.risk import RiskConfig, RiskManager


@dataclass
class Fill:
    side: str  # buy | sell
    qty: float
    price: float
    notional_usd: float
    fee_usd: float
    pnl_usd: float
    is_close: bool
    reason: str
    ts: datetime


def fill_price(mid: float, side: str, slippage_bps: float) -> float:
    return fees_fill_price(mid, side, slippage_bps)


def fee_total(notional_usd: float, fees: FeesConfig) -> float:
    return fee_components(notional_usd, fees)[2]


class PaperBroker:
    def __init__(
        self,
        risk: RiskManager,
        fees: Optional[FeesConfig] = None,
        risk_cfg: Optional[RiskConfig] = None,
    ) -> None:
        self.risk = risk
        self.fees = fees or FeesConfig()
        self.slippage_bps = float((risk_cfg or risk.config).slippage_bps)
        self.fills: list[Fill] = []

    def execute(
        self,
        organism: Organism,
        action: SignalAction,
        *,
        mid: float,
        symbol: str,
        mint: str,
        now: datetime,
        data_age_sec: float = 0.0,
        reason: str = "",
        open_trade_count: Optional[int] = None,
    ) -> Optional[Fill]:
        if action == SignalAction.HOLD or mid <= 0:
            return None

        pos = organism.position
        closing = (pos.qty > 0 and action == SignalAction.SELL) or (
            pos.qty < 0 and action == SignalAction.BUY
        )

        if closing:
            return self._close(organism, mid=mid, symbol=symbol, mint=mint, now=now, reason=reason or "close")

        # Opening / adding
        size_usd = min(organism.genome.size_usd, organism.cash_usd)
        if size_usd <= 0:
            return None
        position_notional = abs(pos.qty) * (pos.avg_entry or mid)
        decision = self.risk.check_order(
            notional_usd=size_usd,
            data_age_sec=data_age_sec,
            would_open=True,
            cash_usd=organism.cash_usd,
            position_notional=position_notional,
            open_trade_count=open_trade_count,
        )
        if not decision.allowed:
            return None

        side = "buy" if action == SignalAction.BUY else "sell"
        px = fill_price(mid, side, self.slippage_bps)
        qty = size_usd / px
        if action == SignalAction.SELL:
            qty = -qty
        fee = fee_total(size_usd, self.fees)

        # Flat open
        if pos.qty == 0:
            organism.position = Position(
                mint=mint,
                symbol=symbol,
                qty=qty,
                avg_entry=px,
                opened_at=now,
                side="long" if qty > 0 else "short",
            )
        else:
            # same-side add (simple average)
            new_qty = pos.qty + qty
            if abs(new_qty) < 1e-12:
                organism.position = Position()
            else:
                organism.position = Position(
                    mint=mint,
                    symbol=symbol,
                    qty=new_qty,
                    avg_entry=px,
                    opened_at=pos.opened_at or now,
                    side="long" if new_qty > 0 else "short",
                )

        organism.cash_usd -= fee
        if action == SignalAction.BUY:
            organism.cash_usd -= size_usd
        else:
            organism.cash_usd += size_usd  # short proceeds

        organism.realized_pnl -= fee
        organism.window.realized_pnl -= fee
        organism.window.fees_usd += fee
        organism.window.turnover_usd += size_usd
        organism.window.n_trades += 1
        organism.last_trade_at = now
        organism.last_signal = action

        fill = Fill(
            side=side,
            qty=abs(qty),
            price=px,
            notional_usd=size_usd,
            fee_usd=fee,
            pnl_usd=-fee,
            is_close=False,
            reason=reason or "open",
            ts=now,
        )
        self.fills.append(fill)
        return fill

    def _close(
        self,
        organism: Organism,
        *,
        mid: float,
        symbol: str,
        mint: str,
        now: datetime,
        reason: str,
    ) -> Fill:
        pos = organism.position
        qty = abs(pos.qty)
        side = "sell" if pos.qty > 0 else "buy"
        # Risk is consulted but MUST allow (inv 1) — we call with would_open=False.
        self.risk.check_order(
            notional_usd=qty * mid,
            data_age_sec=0.0,
            would_open=False,
            cash_usd=organism.cash_usd,
            position_notional=qty * (pos.avg_entry or mid),
        )
        px = fill_price(mid, side, self.slippage_bps)
        notional = qty * px
        fee = fee_total(notional, self.fees)
        entry = pos.avg_entry or px
        if pos.qty > 0:
            pnl = (px - entry) * qty - fee
            organism.cash_usd += notional - fee
        else:
            pnl = (entry - px) * qty - fee
            organism.cash_usd -= notional + fee  # cover short

        organism.realized_pnl += pnl
        organism.window.realized_pnl += pnl
        organism.window.fees_usd += fee
        organism.window.turnover_usd += notional
        organism.window.n_trades += 1
        organism.position = Position()
        organism.last_trade_at = now
        organism.last_signal = SignalAction.SELL if side == "sell" else SignalAction.BUY

        fill = Fill(
            side=side,
            qty=qty,
            price=px,
            notional_usd=notional,
            fee_usd=fee,
            pnl_usd=pnl,
            is_close=True,
            reason=reason,
            ts=now,
        )
        self.fills.append(fill)
        return fill
