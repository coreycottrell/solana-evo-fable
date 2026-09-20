"""Durable mid-price pool for nursery/deep backtests.

Ticks land in ``data/price_pool/{SYMBOL}.jsonl`` (one JSON object per line):
``{"ts": ISO8601, "mint": "...", "mid": float, "source": "jupiter"|"synthetic"|"coingecko"|...}``.

Optional aggregated bars can be rebuilt on read via ``load_bars``; we also
append to ``{SYMBOL}_1m.jsonl`` when ticks span a new minute (best-effort).

Thread-safe enough for a single paper-loop writer (file lock via ``threading.Lock``
per process + atomic append with flush).
"""

from __future__ import annotations

import json
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import httpx

log = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_guard:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        ts = raw
    else:
        s = str(raw).replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(s)
        except Exception:
            return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


class PricePool:
    """Append-only JSONL mid store keyed by symbol."""

    def __init__(self, root: str | Path = "data/price_pool") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _tick_path(self, symbol: str) -> Path:
        return self.root / f"{symbol.upper()}.jsonl"

    def _bar_path(self, symbol: str, bar_seconds: int = 60) -> Path:
        label = "1m" if bar_seconds == 60 else f"{bar_seconds}s"
        return self.root / f"{symbol.upper()}_{label}.jsonl"

    def append_tick(
        self,
        symbol: str,
        mint: str,
        mid: float,
        source: str,
        ts: Optional[datetime | str] = None,
    ) -> None:
        """Append one mid tick. Safe for a single writer process."""
        if mid is None or float(mid) <= 0:
            return
        symbol = (symbol or "").upper().strip()
        if not symbol:
            return
        src = str(source or "unknown").strip().lower()
        if src == "synthetic":
            raise ValueError(
                "synthetic source rejected: real tape only (invariant 4); "
                "record a gap or omit the tick — never invent mids"
            )
        when = _parse_ts(ts)
        if when is None:
            raise ValueError(
                "append_tick requires ts= (injected clock); "
                "wall clock banned outside live/ (invariant 2)"
            )
        row = {
            "ts": when.isoformat(),
            "mint": mint,
            "mid": float(mid),
            "source": str(source or "unknown"),
        }
        path = self._tick_path(symbol)
        lock = _lock_for(path)
        with lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
                f.flush()

    def load_ticks(self, symbol: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
        path = self._tick_path(symbol)
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        if limit is not None and limit > 0:
            rows = rows[-limit:]
        return rows

    def load_mids(self, symbol: str, limit: Optional[int] = None) -> list[float]:
        return [float(r["mid"]) for r in self.load_ticks(symbol, limit=limit) if r.get("mid") is not None]

    def tick_count(self, symbol: str) -> int:
        path = self._tick_path(symbol)
        if not path.exists():
            return 0
        n = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    def load_bars(
        self,
        symbol: str,
        bar_seconds: int,
        n: Optional[int] = None,
        sources: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        """Build OHLCV bars from ticks (resample on read).

        ``sources`` (F6): if set, only ticks whose ``source`` is in this
        allowlist are used. Comparison is case-insensitive.
        """
        ticks = self.load_ticks(symbol)
        if not ticks:
            return []
        if sources is not None:
            allow = {str(s).strip().lower() for s in sources}
            ticks = [t for t in ticks if str(t.get("source") or "").strip().lower() in allow]
            if not ticks:
                return []
        bars = _resample_ticks(ticks, bar_seconds)
        if n is not None and n > 0:
            bars = bars[-n:]
        return bars

    def stats(self, symbols: Optional[Sequence[str]] = None) -> dict[str, dict[str, Any]]:
        """Per-symbol tick count + first/last timestamps."""
        out: dict[str, dict[str, Any]] = {}
        if symbols is None:
            symbols = sorted({p.stem for p in self.root.glob("*.jsonl") if "_" not in p.stem})
        for sym in symbols:
            sym_u = sym.upper()
            ticks = self.load_ticks(sym_u)
            if not ticks:
                out[sym_u] = {"n": 0, "first": None, "last": None}
                continue
            first = ticks[0].get("ts")
            last = ticks[-1].get("ts")
            out[sym_u] = {
                "n": len(ticks),
                "first": first,
                "last": last,
                "sources": _source_counts(ticks),
            }
        return out

    def has_enough_bars(
        self,
        symbols: Sequence[str],
        *,
        bar_seconds: int,
        min_bars: int,
    ) -> bool:
        if min_bars <= 0:
            return False
        for sym in symbols:
            bars = self.load_bars(sym, bar_seconds, n=min_bars)
            if len(bars) < min_bars:
                return False
        return True


def _source_counts(ticks: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in ticks:
        s = str(t.get("source") or "unknown")
        counts[s] = counts.get(s, 0) + 1
    return counts


def _resample_ticks(ticks: Sequence[dict[str, Any]], bar_seconds: int) -> list[dict[str, Any]]:
    if bar_seconds <= 0:
        bar_seconds = 60
    buckets: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for t in ticks:
        ts = _parse_ts(t.get("ts"))
        if ts is None:
            continue
        mid = float(t.get("mid") or 0.0)
        if mid <= 0:
            continue
        epoch = int(ts.timestamp())
        key = epoch - (epoch % bar_seconds)
        if key not in buckets:
            buckets[key] = {
                "ts": datetime.fromtimestamp(key, tz=timezone.utc).isoformat(),
                "mint": t.get("mint"),
                "o": mid,
                "h": mid,
                "l": mid,
                "c": mid,
                "mid": mid,
                "v": 1,
                "n": 1,
                "symbol": None,
            }
            order.append(key)
        else:
            b = buckets[key]
            b["h"] = max(float(b["h"]), mid)
            b["l"] = min(float(b["l"]), mid)
            b["c"] = mid
            b["mid"] = mid
            b["v"] = int(b.get("v", 0)) + 1
            b["n"] = int(b.get("n", 0)) + 1
    return [buckets[k] for k in order]


# CoinGecko id map for bootstrap (best-effort, no key)
COINGECKO_IDS: dict[str, str] = {
    "SOL": "solana",
    "JUP": "jupiter-exchange-solana",
    "WIF": "dogwifcoin",
    "BONK": "bonk",
    "RAY": "raydium",
}


def bootstrap_from_coingecko(
    pool: PricePool,
    watchlist: Sequence[Any],
    *,
    days: int = 7,
    timeout_sec: float = 12.0,
) -> dict[str, Any]:
    """Best-effort historical mids from CoinGecko market_chart.

    Returns ``{symbol: {ok, n, error?}}``. Failures are non-fatal.
    """
    results: dict[str, Any] = {}
    mint_by_sym = {getattr(i, "symbol", "").upper(): getattr(i, "mint", "") for i in watchlist}
    watch_syms = set(mint_by_sym.keys())
    with httpx.Client(timeout=timeout_sec) as client:
        for sym, cg_id in COINGECKO_IDS.items():
            if watch_syms and sym not in watch_syms:
                continue
            mint = mint_by_sym.get(sym, "")
            # Skip only when we already have meaningful temporal coverage
            existing_bars = pool.load_bars(sym, 60)
            if len(existing_bars) >= 50:
                results[sym] = {
                    "ok": True,
                    "n": pool.tick_count(sym),
                    "n_bars": len(existing_bars),
                    "skipped": "already_populated",
                }
                continue
            url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
            try:
                resp = client.get(url, params={"vs_currency": "usd", "days": str(days)})
                if resp.status_code != 200:
                    results[sym] = {"ok": False, "n": 0, "error": f"http_{resp.status_code}"}
                    continue
                payload = resp.json()
                prices = payload.get("prices") or []
                n = 0
                for pair in prices:
                    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                        continue
                    ms, px = pair[0], pair[1]
                    try:
                        ts = datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)
                        mid = float(px)
                    except Exception:
                        continue
                    if mid <= 0:
                        continue
                    pool.append_tick(sym, mint, mid, source="coingecko", ts=ts)
                    n += 1
                results[sym] = {"ok": n > 0, "n": n}
            except Exception as exc:  # noqa: BLE001
                results[sym] = {"ok": False, "n": 0, "error": str(exc)}
            time.sleep(1.25)  # polite pacing; CoinGecko free tier is strict
    return results


def bars_from_pool_for_watchlist(
    pool: PricePool,
    watchlist: Sequence[Any],
    *,
    bar_seconds: int,
    n_bars: int,
) -> dict[str, list[dict[str, Any]]]:
    """Build mint-keyed bar series matching synthetic bar schema."""
    series: dict[str, list[dict[str, Any]]] = {}
    for item in watchlist:
        sym = getattr(item, "symbol", "").upper()
        mint = getattr(item, "mint", "")
        bars = pool.load_bars(sym, bar_seconds, n=n_bars)
        rows: list[dict[str, Any]] = []
        for b in bars:
            mid = float(b.get("c") or b.get("mid") or 0.0)
            rows.append(
                {
                    "t": b.get("ts"),
                    "o": float(b.get("o", mid)),
                    "h": float(b.get("h", mid)),
                    "l": float(b.get("l", mid)),
                    "c": mid,
                    "mid": mid,
                    "symbol": sym,
                    "mint": mint,
                }
            )
        series[mint] = rows
    return series


def pool_from_config(cfg: Any) -> Optional[PricePool]:
    """Construct PricePool if ``cfg.price_pool.enabled``."""
    pp = getattr(cfg, "price_pool", None)
    if pp is None or not getattr(pp, "enabled", True):
        return None
    return PricePool(getattr(pp, "dir", "data/price_pool"))
