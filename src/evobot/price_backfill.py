"""Backfill durable price_pool from free public APIs.

Sources (labeled honestly — never claim CEX=DEX):
  - Binance Spot klines → source ``SOLUSDT_CEX`` (SOL only; USDT quote)
  - GeckoTerminal on-chain pool OHLCV → source ``geckoterminal`` (Solana pools)

Rate limits: GeckoTerminal ~30/min keyless — we sleep between calls.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import httpx

from evobot.price_pool import PricePool

log = logging.getLogger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
GECKO_BASE = "https://api.geckoterminal.com/api/v2"

# Solana mint → GeckoTerminal search hint
_DEFAULT_TOKENS: dict[str, str] = {
    "SOL": "So11111111111111111111111111111111111111112",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
}

_INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000}


def _ts_iso(ms: int) -> str:
    # Binance Vision CSVs sometimes emit microseconds; normalize to ms.
    ms = int(ms)
    if ms > 10_000_000_000_000:  # > year ~2286 in ms ⇒ treat as µs
        ms //= 1000
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def backfill_binance_sol(
    pool: PricePool,
    *,
    interval: str = "1m",
    limit_per_call: int = 1000,
    max_candles: int = 5000,
    mint: str = "So11111111111111111111111111111111111111112",
    symbol: str = "SOL",
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Pull SOLUSDT klines from Binance Spot (no API key). Label SOLUSDT_CEX."""
    if interval not in _INTERVAL_MS:
        raise ValueError(f"unsupported interval {interval}")
    written = 0
    end_ms: Optional[int] = None
    calls = 0
    with httpx.Client(timeout=timeout) as client:
        while written < max_candles:
            params: dict[str, Any] = {
                "symbol": "SOLUSDT",
                "interval": interval,
                "limit": min(limit_per_call, max_candles - written),
            }
            if end_ms is not None:
                params["endTime"] = end_ms
            r = client.get(BINANCE_KLINES, params=params)
            r.raise_for_status()
            rows = r.json()
            calls += 1
            if not rows:
                break
            # rows: [open_time, open, high, low, close, volume, close_time, ...]
            batch = 0
            for row in rows:
                open_ms = int(row[0])
                close = float(row[4])
                pool.append_tick(
                    symbol,
                    mint,
                    close,
                    source="SOLUSDT_CEX",
                    ts=_ts_iso(open_ms),
                )
                batch += 1
            written += batch
            # paginate backward
            first_open = int(rows[0][0])
            next_end = first_open - 1
            if end_ms is not None and next_end >= end_ms:
                break
            end_ms = next_end
            if len(rows) < params["limit"]:
                break
            time.sleep(0.15)
    return {
        "source": "SOLUSDT_CEX",
        "symbol": symbol,
        "interval": interval,
        "candles_written": written,
        "calls": calls,
        "note": "Binance Spot SOLUSDT — CEX, not Solana DEX",
    }



def backfill_binance_vision_sol(
    pool: PricePool,
    *,
    days: int = 7,
    mint: str = "So11111111111111111111111111111111111111112",
    symbol: str = "SOL",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Fallback: daily 1m kline CSVs from data.binance.vision (no key).

    Used when api.binance.com returns geo-block (HTTP 451). Labeled SOLUSDT_CEX.
    """
    import csv
    import io
    import zipfile
    from datetime import date, timedelta

    written = 0
    files = 0
    errors: list[str] = []
    day = date.today() - timedelta(days=1)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for _ in range(max(1, days)):
            ymd = day.isoformat()
            url = (
                "https://data.binance.vision/data/spot/daily/klines/"
                f"SOLUSDT/1m/SOLUSDT-1m-{ymd}.zip"
            )
            try:
                r = client.get(url)
                if r.status_code != 200:
                    errors.append(f"{ymd}:HTTP{r.status_code}")
                    day -= timedelta(days=1)
                    continue
                with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                    name = zf.namelist()[0]
                    with zf.open(name) as fh:
                        reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8"))
                        batch = 0
                        for row in reader:
                            if not row or not str(row[0]).isdigit():
                                continue
                            open_ms = int(row[0])
                            close = float(row[4])
                            pool.append_tick(
                                symbol,
                                mint,
                                close,
                                source="SOLUSDT_CEX",
                                ts=_ts_iso(open_ms),
                            )
                            batch += 1
                        written += batch
                        files += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{ymd}:{exc}")
            day -= timedelta(days=1)
            time.sleep(0.2)
    return {
        "source": "SOLUSDT_CEX",
        "via": "data.binance.vision",
        "symbol": symbol,
        "candles_written": written,
        "files": files,
        "errors": errors[:12],
        "note": "Binance Spot SOLUSDT daily CSV — CEX, not Solana DEX",
    }


def backfill_geckoterminal(
    pool: PricePool,
    tokens: Optional[dict[str, str]] = None,
    *,
    aggregate_minutes: int = 5,
    max_candles_per_symbol: int = 2000,
    sleep_sec: float = 2.1,
    timeout: float = 25.0,
) -> dict[str, Any]:
    """Backfill Solana on-chain pool OHLCV for JUP/BONK/RAY/WIF/SOL via GeckoTerminal."""
    tokens = tokens or dict(_DEFAULT_TOKENS)
    out: dict[str, Any] = {"source": "geckoterminal", "symbols": {}}
    with httpx.Client(timeout=timeout, headers={"Accept": "application/json"}) as client:
        for sym, mint in tokens.items():
            time.sleep(sleep_sec)
            try:
                pool_addr = _discover_top_pool(client, mint)
            except Exception as exc:  # noqa: BLE001
                out["symbols"][sym] = {"error": f"discover:{exc}"}
                continue
            if not pool_addr:
                out["symbols"][sym] = {"error": "no_pool"}
                continue
            written = 0
            before: Optional[int] = None
            calls = 0
            errors: list[str] = []
            while written < max_candles_per_symbol:
                time.sleep(sleep_sec)
                try:
                    rows = _ohlcv_aggregate(
                        client,
                        pool_addr,
                        timeframe="minute",
                        aggregate=aggregate_minutes,
                        before_timestamp=before,
                        limit=min(1000, max_candles_per_symbol - written),
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))
                    break
                calls += 1
                if not rows:
                    break
                for row in rows:
                    # [ts_sec, o, h, l, c, vol]
                    ts_sec = int(row[0])
                    close = float(row[4])
                    pool.append_tick(
                        sym,
                        mint,
                        close,
                        source="geckoterminal",
                        ts=_ts_iso(ts_sec * 1000),
                    )
                    written += 1
                oldest = int(rows[-1][0])
                next_before = oldest - 1
                if before is not None and next_before >= before:
                    break
                before = next_before
                if len(rows) < 50:
                    break
            out["symbols"][sym] = {
                "pool": pool_addr,
                "candles_written": written,
                "calls": calls,
                "errors": errors,
                "aggregate_minutes": aggregate_minutes,
            }
    return out


def backfill_all(
    pool: PricePool,
    *,
    binance_interval: str = "1m",
    binance_max: int = 5000,
    gecko_aggregate: int = 5,
    gecko_max_per_symbol: int = 1500,
    include_binance: bool = True,
    include_gecko: bool = True,
    tokens: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    if include_binance:
        try:
            report["binance"] = backfill_binance_sol(
                pool, interval=binance_interval, max_candles=binance_max
            )
            err = str(report["binance"].get("error") or "")
            if "451" in err or report["binance"].get("candles_written", 0) == 0:
                report["binance_vision"] = backfill_binance_vision_sol(pool)
        except Exception as exc:  # noqa: BLE001
            report["binance"] = {"error": str(exc)}
            try:
                report["binance_vision"] = backfill_binance_vision_sol(pool)
            except Exception as exc2:  # noqa: BLE001
                report["binance_vision"] = {"error": str(exc2)}
    if include_gecko:
        try:
            report["geckoterminal"] = backfill_geckoterminal(
                pool,
                tokens=tokens,
                aggregate_minutes=gecko_aggregate,
                max_candles_per_symbol=gecko_max_per_symbol,
            )
        except Exception as exc:  # noqa: BLE001
            report["geckoterminal"] = {"error": str(exc)}
    return report
