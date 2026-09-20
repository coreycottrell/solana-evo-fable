"""GET-only observer dashboard — dish visual language from v1 (inv 14 / F11).

Extracted patterns: theory_bullets / theory_body, esc hygiene (in HTML),
create_export_pack (git SHA + config + population + trades + cadences).
No POST/mutating routes.
"""

from __future__ import annotations

import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

_snapshot_fn: Optional[Callable[[], dict[str, Any]]] = None
_engine_ref: Any = None

THESIS_BLURBS: dict[str, str] = {
    "mean_reversion": (
        "Mean reversion expects price to snap back toward a recent average after "
        "an overshoot. Entries lean against short-term extremes; exits when the "
        "stretch collapses or stops hit."
    ),
    "momentum": (
        "Momentum follows N-bar returns in the direction of the move. It wants "
        "continuation, not fade — size and hold are tuned for trend persistence."
    ),
    "breakout": (
        "Breakout waits for price to clear a lookback range by a buffer, then "
        "rides the expansion. False breaks are cut with stop/TP and cooldown."
    ),
    "micro_trend": (
        "Micro-trend uses a fast/slow EMA cross (or tilt) on short horizons. "
        "It hunts small directional edges with tight risk and modest clips."
    ),
    "liquidity_fade": (
        "Liquidity fade treats sharp one-bar jumps as likely overshoots (proxy "
        "for thin book), then fades the move back toward pre-jump levels."
    ),
}

ISLAND_FLAVOR: dict[str, str] = {
    "trend": "Island prior: TREND — continuation theses (momentum, breakout, micro_trend).",
    "contrarian": "Island prior: CONTRARIAN — fade/revert theses (mean_reversion, liquidity_fade).",
}


def _thesis_key(o: Any) -> str:
    if isinstance(o, dict):
        return str(o.get("thesis") or o.get("thesis_type") or "")
    t = getattr(o, "thesis_type", None)
    return t.value if hasattr(t, "value") else str(t or "")


def _island_key(o: Any) -> str:
    if isinstance(o, dict):
        if o.get("island"):
            return str(o["island"])
        from evobot.evolution import island_for_thesis
        from evobot.models import ThesisType
        th = o.get("thesis") or o.get("thesis_type")
        try:
            return island_for_thesis(ThesisType(th))
        except Exception:
            return ""
    from evobot.evolution import island_for_thesis
    return island_for_thesis(o.thesis_type)


def _params_of(o: Any) -> dict[str, Any]:
    if isinstance(o, dict):
        return dict(o.get("genome") or o.get("params") or {})
    g = getattr(o, "genome", None)
    if g is not None and hasattr(g, "to_dict"):
        return g.to_dict()
    return {}


def theory_bullets(o: Any) -> list[str]:
    """3–6 point-form lines from thesis + live params (no Jev/Twitter)."""
    thesis = _thesis_key(o)
    island = _island_key(o)
    p = _params_of(o)
    bullets: list[str] = []
    lookback = p.get("lookback", 20)
    if thesis == "momentum":
        bullets.append(f"Momentum: follow {lookback}-bar return")
    elif thesis == "mean_reversion":
        bullets.append(
            f"Mean-revert vs {lookback}-bar average (entry thr {p.get('entry_threshold', '?')})"
        )
    elif thesis == "breakout":
        bullets.append(
            f"Breakout: clear {lookback}-bar range + {p.get('breakout_buffer_bps', 10)} bps buffer"
        )
    elif thesis == "micro_trend":
        bullets.append(f"Micro-trend: EMA {p.get('ema_fast', 5)}/{p.get('ema_slow', 20)}")
    elif thesis == "liquidity_fade":
        bullets.append(f"Liquidity fade: fade jumps ≥ {p.get('fade_move_bps', 80)} bps")
    else:
        bullets.append(f"Thesis: {thesis or 'unknown'} (lookback {lookback})")
    bullets.append(
        f"TP/SL: {p.get('take_profit_bps', '?')} / {p.get('stop_loss_bps', '?')} bps · "
        f"max hold {p.get('max_hold_sec', '?')}s · cooldown {p.get('cooldown_sec', '?')}s"
    )
    bullets.append(f"Side bias: {p.get('side_bias', 'both')} · clip ${p.get('size_usd', '?')}")
    if island:
        flavor = (
            "trend-continuation prior"
            if island == "trend"
            else ("fade/revert prior" if island == "contrarian" else f"{island} island")
        )
        bullets.append(f"Island: {island} ({flavor})")
    return bullets[:6]


def theory_body(o: Any) -> str:
    thesis = _thesis_key(o)
    island = _island_key(o)
    parts = [
        THESIS_BLURBS.get(thesis, f"Custom / unknown thesis: {thesis}."),
        ISLAND_FLAVOR.get(island, f"Island: {island or 'unspecified'}."),
    ]
    return " ".join(parts)


def esc(s: Any) -> str:
    """HTML escape — same hygiene as v1 dashboard JS esc()."""
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _git_sha() -> str:
    try:
        import subprocess
        root = Path(__file__).resolve().parents[2]
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=root, stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def create_export_pack(
    data_dir: Path,
    snapshot: dict[str, Any],
    dumps_dir: Path | None = None,
    *,
    now: datetime | None = None,
) -> Path:
    """Timestamped review pack with SHA, snapshot, population, trades, cadences.

    ``now`` must be injected (inv 2) — typically engine.last_step_at or live clock.
    """
    data_dir = Path(data_dir)
    dumps = dumps_dir or (data_dir / "dumps")
    dumps.mkdir(parents=True, exist_ok=True)
    if now is None:
        # Prefer clock already on the snapshot (paper engine last_step_at).
        raw = snapshot.get("last_step_at") or snapshot.get("cadence_started_at")
        if raw:
            now = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        else:
            now = datetime(1970, 1, 1, tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pack_name = f"pack_{stamp}"
    pack_dir = dumps / pack_name
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True)

    (pack_dir / "snapshot.json").write_text(
        json.dumps(snapshot, indent=2, default=str), encoding="utf-8"
    )
    for name in ("population.json", "trades.jsonl", "cadences.jsonl"):
        src = data_dir / name
        if src.exists():
            shutil.copy2(src, pack_dir / name)

    theory = []
    for o in snapshot.get("organisms") or []:
        theory.append(
            {
                "id": o.get("id"),
                "label": o.get("label"),
                "thesis": o.get("thesis"),
                "island": o.get("island"),
                "theory_bullets": o.get("theory_bullets") or theory_bullets(o),
                "theory_body": o.get("theory_body") or theory_body(o),
                "genome": o.get("genome") or {},
                "parent_ids": o.get("parent_ids") or [],
            }
        )
    (pack_dir / "organisms_theory.json").write_text(
        json.dumps(theory, indent=2, default=str), encoding="utf-8"
    )
    readme = (
        "# Fable review pack\n\n"
        "GET-only colony dump. Read manifest.json, organisms_theory.json, "
        "population.json, trades.jsonl, cadences.jsonl.\n"
    )
    (pack_dir / "README_FOR_AI.md").write_text(readme, encoding="utf-8")

    files = sorted(str(p.relative_to(pack_dir)) for p in pack_dir.rglob("*") if p.is_file())
    manifest = {
        "pack_id": pack_name,
        "created_at": now.astimezone(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "bot_version": "0.2.0",
        "mode": "paper",
        "n_organisms": len(snapshot.get("organisms") or []),
        "files": sorted(set(files + ["manifest.json"])),
        "notes": "Fable review pack — SHA + config snapshot + theory.",
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    zip_path = dumps / f"{pack_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in pack_dir.rglob("*"):
            if p.is_file():
                zf.write(p, arcname=str(Path(pack_name) / p.relative_to(pack_dir)))
    return zip_path


DASHBOARD_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="utf-8"/>\n  <meta name="viewport" content="width=device-width, initial-scale=1"/>\n  <title>Fable Colony — Solana Evo</title>\n  <style>\n    :root {\n      --bg: #070d0a; --dish: #0c1612; --panel: #101c17; --border: #1e3a2f;\n      --border-glow: #2a5a45; --text: #d8efe4; --muted: #7a9a8a; --accent: #3ecf8e;\n      --good: #3ecf8e; --warn: #e6c07b; --bad: #f07178; --cell: #12241c; --cell-border: #24503c;\n    }\n    * { box-sizing: border-box; }\n    body {\n      margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;\n      background: radial-gradient(ellipse at 20% 0%, #0f2a1c 0%, transparent 50%),\n                  radial-gradient(ellipse at 80% 100%, #0a1a28 0%, transparent 45%), var(--bg);\n      color: var(--text); line-height: 1.45; min-height: 100vh;\n    }\n    header.colony-bar {\n      display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px;\n      padding: 12px 18px; border-bottom: 1px solid var(--border);\n      background: linear-gradient(180deg, #0e1a14, var(--bg));\n      position: sticky; top: 0; z-index: 20; backdrop-filter: blur(8px);\n    }\n    header h1 { margin: 0; font-size: 1.1rem; letter-spacing: 0.04em; font-weight: 700; color: var(--accent); }\n    .pill { display: inline-block; padding: 2px 10px; border-radius: 999px; background: #143028;\n      color: var(--accent); font-size: 0.72rem; font-weight: 700; border: 1px solid var(--border-glow);\n      text-transform: uppercase; letter-spacing: 0.05em; }\n    .meta { color: var(--muted); font-size: 0.8rem; }\n    .stat-chip { font-size: 0.78rem; padding: 4px 10px; border-radius: 8px;\n      background: var(--panel); border: 1px solid var(--border); }\n    .stat-chip strong { color: var(--text); font-weight: 600; }\n    .btn { appearance: none; border: 1px solid var(--border-glow); background: #143028;\n      color: var(--accent); font: inherit; font-size: 0.78rem; font-weight: 600;\n      padding: 6px 12px; border-radius: 8px; cursor: pointer; }\n    .btn:hover { background: #1a3e32; }\n    .btn:disabled { opacity: 0.5; cursor: wait; }\n    main { padding: 16px 18px 48px; display: grid; gap: 18px; max-width: 1400px; margin: 0 auto; }\n    .boards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }\n    @media (max-width: 900px) { .boards { grid-template-columns: 1fr; } }\n    .board { background: var(--dish); border: 1px solid var(--border); border-radius: 16px;\n      padding: 14px; box-shadow: inset 0 0 40px rgba(30, 80, 55, 0.15); min-height: 200px; }\n    .board h2 { margin: 0 0 12px; font-size: 0.85rem; text-transform: uppercase;\n      letter-spacing: 0.08em; color: var(--muted); display: flex; align-items: center; gap: 8px; }\n    .board h2 .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent);\n      box-shadow: 0 0 8px var(--accent); }\n    .board.contrarian h2 .dot { background: var(--warn); box-shadow: 0 0 8px var(--warn); }\n    .cells { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }\n    .cell { position: relative; background: var(--cell); border: 1px solid var(--cell-border);\n      border-radius: 14px; padding: 12px 12px 10px; overflow: hidden;\n      transition: transform 0.12s ease, box-shadow 0.12s ease; }\n    .cell::before { content: ""; position: absolute; inset: 0;\n      background: radial-gradient(circle at 80% 20%, rgba(62,207,142,0.08), transparent 55%);\n      pointer-events: none; }\n    .cell:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,0.35); }\n    .cell.health-good { border-color: #2d6b4a; }\n    .cell.health-mid { border-color: #6b5a2d; }\n    .cell.health-bad { border-color: #6b2d2d; }\n    .cell-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 6px; }\n    .gen-badge { font-size: 0.65rem; font-weight: 700; padding: 2px 7px; border-radius: 999px;\n      background: #1a3028; color: var(--accent); border: 1px solid var(--border); }\n    .info-btn { width: 24px; height: 24px; border-radius: 50%; border: 1px solid var(--border-glow);\n      background: #143028; color: var(--accent); font-weight: 700; font-size: 0.75rem;\n      cursor: pointer; line-height: 1; flex-shrink: 0; }\n    .cell-label { font-weight: 700; font-size: 0.92rem; margin: 6px 0 2px; }\n    .cell-thesis { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }\n    .big-scores { display: flex; gap: 12px; margin: 10px 0 8px; align-items: baseline; }\n    .big-scores .fit { font-size: 1.35rem; font-weight: 800; font-variant-numeric: tabular-nums; }\n    .big-scores .pnl { font-size: 0.95rem; font-weight: 600; font-variant-numeric: tabular-nums; }\n    .pos { color: var(--good); } .neg { color: var(--bad); }\n    .pos-chip { display: inline-block; font-size: 0.7rem; font-weight: 600; padding: 2px 8px;\n      border-radius: 999px; margin-bottom: 8px; background: #1a2430; border: 1px solid var(--border); color: var(--muted); }\n    .pos-chip.long { color: var(--good); border-color: #2d6b4a; }\n    .pos-chip.short { color: var(--bad); border-color: #6b2d2d; }\n    .vitals { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 8px; font-size: 0.68rem;\n      color: var(--muted); margin-bottom: 8px; font-variant-numeric: tabular-nums; }\n    .vitals span b { color: var(--text); font-weight: 600; }\n    .theory-list { margin: 0; padding-left: 16px; font-size: 0.72rem; color: #a8c4b6; }\n    .theory-list li { margin: 2px 0; }\n    .strip, .log-card { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px; }\n    .strip h2, .log-card h2 { margin: 0 0 10px; font-size: 0.8rem; text-transform: uppercase;\n      letter-spacing: 0.06em; color: var(--muted); }\n    .timeline { list-style: none; margin: 0; padding: 0; }\n    .timeline li { font-size: 0.82rem; padding: 8px 0; border-bottom: 1px solid var(--border);\n      color: #b8d4c6; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }\n    .timeline li:last-child { border-bottom: none; }\n    .timeline .t { color: var(--muted); }\n    .empty { color: var(--muted); font-size: 0.85rem; }\n    footer { color: var(--muted); font-size: 0.72rem; text-align: center; padding: 0 18px 24px; }\n    .modal-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.65);\n      z-index: 100; align-items: center; justify-content: center; padding: 20px; }\n    .modal-backdrop.open { display: flex; }\n    .modal { background: #0e1a14; border: 1px solid var(--border-glow); border-radius: 16px;\n      max-width: 720px; width: 100%; max-height: 90vh; overflow: auto; padding: 20px 22px;\n      box-shadow: 0 20px 60px rgba(0,0,0,0.5); }\n    .modal h3 { margin: 0 0 8px; color: var(--accent); }\n    .modal .close { float: right; border: none; background: transparent; color: var(--muted);\n      font-size: 1.4rem; cursor: pointer; line-height: 1; }\n    .modal section { margin: 14px 0; }\n    .modal section h4 { margin: 0 0 6px; font-size: 0.75rem; text-transform: uppercase;\n      letter-spacing: 0.05em; color: var(--muted); }\n    .modal p { margin: 0; font-size: 0.9rem; color: #c8e0d4; }\n    .modal table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }\n    .modal th, .modal td { text-align: left; padding: 5px 6px; border-bottom: 1px solid var(--border);\n      font-variant-numeric: tabular-nums; }\n    .modal th { color: var(--muted); font-weight: 600; width: 45%; }\n    .rank-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; font-variant-numeric: tabular-nums; }\n    .rank-table th, .rank-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }\n    .rank-table th { color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.68rem; }\n    .rank-table tr:hover td { background: rgba(62,207,142,0.04); }\n  </style>\n</head>\n<body>\n  <header class="colony-bar">\n    <h1>Fable Colony</h1>\n    <span class="pill" id="mode-pill">PAPER</span>\n    <span class="stat-chip" id="chip-cadence">cadence —</span>\n    <span class="stat-chip" id="chip-fills">fills —</span>\n    <span class="stat-chip" id="chip-gen">gen —</span>\n    <span class="stat-chip" id="chip-fee">rt fee —</span>\n    <span class="stat-chip" id="chip-jev">jev —</span>\n    <span class="stat-chip" id="chip-jev-cost">jev cost —</span>\n    <span class="meta" id="updated" style="margin-left:auto">loading…</span>\n    <button class="btn" id="btn-snapshot" type="button">Export dump</button>\n    <button class="btn" id="btn-pack" type="button">Download review pack</button>\n  </header>\n  <main>\n    <section class="boards">\n      <div class="board trend" id="board-trend">\n        <h2><span class="dot"></span> Trend <span class="meta" id="trend-count"></span></h2>\n        <div class="cells" id="cells-trend"><div class="empty">Loading…</div></div>\n      </div>\n      <div class="board contrarian" id="board-contrarian">\n        <h2><span class="dot"></span> Contrarian <span class="meta" id="contra-count"></span></h2>\n        <div class="cells" id="cells-contrarian"><div class="empty">Loading…</div></div>\n      </div>\n    </section>\n    <section class="strip">\n      <h2>Ranks (window fitness)</h2>\n      <div style="overflow-x:auto">\n        <table class="rank-table" id="rank-table">\n          <thead><tr>\n            <th>#</th><th>label</th><th>thesis</th><th>island</th><th>fit</th><th>win PnL</th><th>trades</th><th>gen</th>\n          </tr></thead>\n          <tbody id="rank-body"><tr><td colspan="8" class="empty">Loading…</td></tr></tbody>\n        </table>\n      </div>\n    </section>\n    <section class="log-card">\n      <h2>Cadence history</h2>\n      <ul class="timeline" id="cadence-history"><li class="empty">No cadence events yet</li></ul>\n    </section>\n    <section class="log-card">\n      <h2>Last breed</h2>\n      <ul class="timeline" id="breeding-log"><li class="empty">No cadence events yet</li></ul>\n    </section>\n    <section class="log-card">\n      <h2>Jev panel</h2>\n      <ul class="timeline" id="jev-log"><li class="empty">No Jev calls yet</li></ul>\n    </section>\n  </main>\n  <footer>GET-only observer · auto-refresh ~12s · review packs → data/dumps/</footer>\n  <div class="modal-backdrop" id="modal" role="dialog" aria-modal="true">\n    <div class="modal">\n      <button class="close" id="modal-close" type="button" aria-label="Close">×</button>\n      <h3 id="modal-title">Organism</h3>\n      <div class="meta" id="modal-sub"></div>\n      <section><h4>Underlying theory</h4><p id="modal-theory"></p>\n        <ul class="theory-list" id="modal-bullets"></ul></section>\n      <section><h4>Genome params</h4>\n        <div style="overflow-x:auto"><table><tbody id="modal-genome"></tbody></table></div></section>\n      <section><h4>Lineage</h4><p id="modal-lineage" class="meta"></p></section>\n    </div>\n  </div>\n<script>\nlet lastOrganisms = [];\nfunction fmt(n, d=2) {\n  if (n === null || n === undefined || Number.isNaN(n)) return \'—\';\n  return Number(n).toFixed(d);\n}\nfunction cls(n) { return n > 0 ? \'pos\' : (n < 0 ? \'neg\' : \'\'); }\nfunction shortId(id) { return (id || \'\').slice(0, 12); }\nfunction healthClass(fit) {\n  if (fit === null || fit === undefined) return \'health-mid\';\n  if (fit > 0.05) return \'health-good\';\n  if (fit < -0.05) return \'health-bad\';\n  return \'health-mid\';\n}\nfunction esc(s) {\n  return String(s ?? \'\').replace(/[&<>"\']/g, c => ({\n    \'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\',"\'":\'&#39;\'\n  })[c]);\n}\nasync function fetchJson(url) {\n  const r = await fetch(url, { cache: \'no-store\' });\n  if (!r.ok) throw new Error(url + \' \' + r.status);\n  return r.json();\n}\nfunction posChip(o) {\n  const qty = o.pos_qty || 0;\n  if (!qty) return \'<span class="pos-chip">flat</span>\';\n  const side = qty > 0 ? \'long\' : \'short\';\n  return `<span class="pos-chip ${side}">${side}:${fmt(Math.abs(qty), 4)}</span>`;\n}\nfunction cellHtml(o) {\n  const bullets = (o.theory_bullets || []).slice(0, 5).map(b => `<li>${esc(b)}</li>`).join(\'\');\n  return `<article class="cell ${healthClass(o.fitness)}" data-id="${esc(o.id)}">\n    <div class="cell-top">\n      <span class="gen-badge">gen ${o.generation ?? 0}</span>\n      <button class="info-btn" type="button" data-info="${esc(o.id)}" title="Theory &amp; genome">i</button>\n    </div>\n    <div class="cell-label">${esc(o.label || shortId(o.id))}</div>\n    <div class="cell-thesis">${esc(o.thesis || \'—\')} · ${esc(o.island || \'\')}</div>\n    <div class="big-scores">\n      <span class="fit ${cls(o.fitness)}">${fmt(o.fitness, 4)}</span>\n      <span class="pnl ${cls(o.window_pnl ?? o.lifetime_pnl)}">PnL $${fmt(o.window_pnl ?? o.lifetime_pnl)}</span>\n    </div>\n    ${posChip(o)}\n    <div class="vitals">\n      <span>cash <b>$${fmt(o.cash)}</b></span>\n      <span>size <b>$${fmt(o.size_usd)}</b></span>\n      <span>trades <b>${o.window_trades ?? 0}</b></span>\n      <span>rt fee <b>${fmt(o.round_trip_fee_bps, 1)}bps</b></span>\n      <span>idle <b>${o.idle_cadences ?? 0}</b></span>\n      <span>signal <b>${esc(o.last_signal || \'HOLD\')}</b></span>\n    </div>\n    <ul class="theory-list">${bullets || \'<li class="empty">no theory</li>\'}</ul>\n  </article>`;\n}\nfunction renderBoards(organisms) {\n  const trend = organisms.filter(o => o.island === \'trend\');\n  const contra = organisms.filter(o => o.island !== \'trend\');\n  document.getElementById(\'trend-count\').textContent = `(${trend.length})`;\n  document.getElementById(\'contra-count\').textContent = `(${contra.length})`;\n  document.getElementById(\'cells-trend\').innerHTML =\n    trend.length ? trend.map(cellHtml).join(\'\') : \'<div class="empty">Empty dish</div>\';\n  document.getElementById(\'cells-contrarian\').innerHTML =\n    contra.length ? contra.map(cellHtml).join(\'\') : \'<div class="empty">Empty dish</div>\';\n}\nfunction renderHeader(s) {\n  document.getElementById(\'mode-pill\').textContent = \'PAPER\';\n  const cad = `cadence ${s.cadence_sec ?? \'—\'}s · #${s.cadence_index ?? 0}`;\n  document.getElementById(\'chip-cadence\').innerHTML = `<strong>${esc(cad)}</strong>`;\n  document.getElementById(\'chip-fills\').innerHTML =\n    `<strong>fills ${s.n_fills ?? 0} · polls ${s.poll_count ?? 0}</strong>`;\n  document.getElementById(\'chip-gen\').innerHTML =\n    `<strong>max gen ${s.generation_max ?? 0} · evolves ${s.n_evolves ?? 0}</strong>`;\n  document.getElementById(\'chip-fee\').innerHTML =\n    `<strong>rt fee ~${fmt(s.round_trip_fee_bps_ref, 1)} bps @$100</strong>`;\n  const j = s.jev || {};\n  const lastJ = s.last_jev || {};\n  const model = lastJ.model || j.last_model || \'—\';\n  const mocked = (lastJ.mocked ?? j.last_mocked);\n  const calls = s.jev_calls ?? j.n_calls ?? 0;\n  const live = j.n_live ?? 0;\n  document.getElementById(\'chip-jev\').innerHTML =\n    `<strong>jev ${esc(String(model).slice(0,28))}${mocked ? \' MOCK\' : \'\'} · calls ${calls} (live ${live})</strong>`;\n  document.getElementById(\'chip-jev-cost\').innerHTML =\n    `<strong>jev cost $${fmt(j.total_cost ?? lastJ.cost ?? 0, 6)}</strong>`;\n}\nfunction renderJevLog(s) {\n  const el = document.getElementById(\'jev-log\');\n  const last = s.last_jev;\n  const j = s.jev || {};\n  if (!last && !j.last_model) { el.innerHTML = \'<li class="empty">No Jev calls yet</li>\'; return; }\n  const ans = last && last.answers ? Object.keys(last.answers).join(\', \') : Object.keys(j.last_answers || {}).join(\', \');\n  const arms = last ? `arms with=${esc((last.arm_with_jev&&last.arm_with_jev.policy)||\'—\')} / without=${esc((last.arm_without_jev&&last.arm_without_jev.policy)||\'—\')}` : \'\';\n  const mocked = (last && last.mocked) ?? j.last_mocked;\n  const liveLine = `calls ${s.jev_calls ?? j.n_calls ?? 0} · live ${j.n_live ?? 0} · mocked ${j.n_mocked ?? 0} · cost $${fmt(j.total_cost ?? (last && last.cost) || 0, 6)}`;\n  el.innerHTML = [\n    `<li><span class="t">${esc(last && last.bar_ts || j.last_bar_ts || \'\')}</span> · ${esc(last && last.trigger || j.last_trigger || \'\')} · model ${esc((last && last.model) || j.last_model || \'\')}${mocked ? \' MOCK\' : \' LIVE\'} · ${esc(ans)}</li>`,\n    `<li>${arms || \'arms —\'}</li>`,\n    `<li>${esc(liveLine)} · policy log-only (inv 6)</li>`\n  ].join(\'\');\n}\nfunction renderRanks(ranks) {\n  const body = document.getElementById(\'rank-body\');\n  if (!ranks || !ranks.length) {\n    body.innerHTML = \'<tr><td colspan="8" class="empty">No organisms</td></tr>\';\n    return;\n  }\n  body.innerHTML = ranks.map(r => `<tr>\n    <td>${r.rank ?? \'\'}</td>\n    <td>${esc(r.label || shortId(r.id))}</td>\n    <td>${esc(r.thesis || \'\')}</td>\n    <td>${esc(r.island || \'\')}</td>\n    <td class="${cls(r.fitness)}">${fmt(r.fitness, 4)}</td>\n    <td class="${cls(r.window_pnl)}">${fmt(r.window_pnl, 2)}</td>\n    <td>${r.window_trades ?? 0}</td>\n    <td>${r.generation ?? 0}</td>\n  </tr>`).join(\'\');\n}\nfunction renderCadenceHistory(hist) {\n  const el = document.getElementById(\'cadence-history\');\n  if (!hist || !hist.length) { el.innerHTML = \'<li class="empty">No cadence events yet</li>\'; return; }\n  const rows = hist.slice().reverse().slice(0, 20);\n  el.innerHTML = rows.map(ev => {\n    const t = (ev.at || \'\').replace(\'T\', \' \').slice(0, 19);\n    const retire = (ev.retired && (ev.retired.label || ev.retired.id)) || \'—\';\n    const child = (ev.child && (ev.child.label || ev.child.id)) || \'—\';\n    const why = (ev.retired && ev.retired.why) || \'\';\n    return `<li><span class="t">#${ev.cadence ?? \'?\'} ${esc(t)}</span> · retire ${esc(retire)} → spawn ${esc(child)} · ${esc(why)}</li>`;\n  }).join(\'\');\n}\nfunction renderBreedingLog(last) {\n  const el = document.getElementById(\'breeding-log\');\n  if (!last) { el.innerHTML = \'<li class="empty">No cadence events yet</li>\'; return; }\n  const t = (last.at || \'\').replace(\'T\', \' \').slice(0, 19);\n  const retire = (last.retired && last.retired.id) || \'—\';\n  const child = (last.child && last.child.id) || \'—\';\n  el.innerHTML = `<li><span class="t">#${last.cadence ?? \'?\'} ${esc(t)}</span> · retire ${esc(shortId(retire))} → spawn ${esc(shortId(child))} · ${esc((last.retired&&last.retired.why)||\'\')}</li>`;\n}\nfunction openModal(id) {\n  const o = lastOrganisms.find(x => x.id === id);\n  if (!o) return;\n  document.getElementById(\'modal-title\').textContent = (o.label || shortId(o.id)) + \' · \' + (o.thesis || \'\');\n  document.getElementById(\'modal-sub\').textContent =\n    `${o.id} · ${o.island || \'—\'} · gen ${o.generation ?? 0} · fitness ${fmt(o.fitness, 4)}`;\n  document.getElementById(\'modal-theory\').textContent = o.theory_body || \'—\';\n  document.getElementById(\'modal-bullets\').innerHTML =\n    (o.theory_bullets || []).map(b => `<li>${esc(b)}</li>`).join(\'\');\n  const genome = o.genome || {};\n  document.getElementById(\'modal-genome\').innerHTML = Object.keys(genome).sort().map(k =>\n    `<tr><th>${esc(k)}</th><td>${esc(genome[k])}</td></tr>`\n  ).join(\'\') || \'<tr><td colspan="2">—</td></tr>\';\n  const parents = (o.parent_ids || []).join(\', \') || \'seed / none\';\n  document.getElementById(\'modal-lineage\').textContent = \'Parents: \' + parents;\n  document.getElementById(\'modal\').classList.add(\'open\');\n}\ndocument.getElementById(\'modal-close\').addEventListener(\'click\', () => {\n  document.getElementById(\'modal\').classList.remove(\'open\');\n});\ndocument.getElementById(\'modal\').addEventListener(\'click\', (e) => {\n  if (e.target.id === \'modal\') document.getElementById(\'modal\').classList.remove(\'open\');\n});\ndocument.addEventListener(\'click\', (e) => {\n  const btn = e.target.closest(\'[data-info]\');\n  if (btn) openModal(btn.getAttribute(\'data-info\'));\n});\nasync function downloadUrl(url, fallbackName) {\n  const r = await fetch(url, { cache: \'no-store\' });\n  if (!r.ok) throw new Error(url + \' \' + r.status);\n  const cd = r.headers.get(\'content-disposition\') || \'\';\n  let name = fallbackName;\n  const m = /filename="?([^";]+)"?/i.exec(cd);\n  if (m) name = m[1];\n  const blob = await r.blob();\n  const a = document.createElement(\'a\');\n  a.href = URL.createObjectURL(blob);\n  a.download = name;\n  document.body.appendChild(a); a.click(); a.remove();\n  setTimeout(() => URL.revokeObjectURL(a.href), 2000);\n}\ndocument.getElementById(\'btn-snapshot\').addEventListener(\'click\', async () => {\n  const btn = document.getElementById(\'btn-snapshot\');\n  btn.disabled = true;\n  try { await downloadUrl(\'/api/export/snapshot\', \'snapshot.json\'); }\n  catch (e) { alert(\'Export failed: \' + e.message); }\n  finally { btn.disabled = false; }\n});\ndocument.getElementById(\'btn-pack\').addEventListener(\'click\', async () => {\n  const btn = document.getElementById(\'btn-pack\');\n  btn.disabled = true; btn.textContent = \'Packing…\';\n  try { await downloadUrl(\'/api/export/pack\', \'review_pack.zip\'); }\n  catch (e) { alert(\'Pack failed: \' + e.message); }\n  finally { btn.disabled = false; btn.textContent = \'Download review pack\'; }\n});\nasync function refresh() {\n  try {\n    const s = await fetchJson(\'/snapshot\');\n    lastOrganisms = s.organisms || [];\n    renderHeader(s);\n    renderBoards(lastOrganisms);\n    renderRanks(s.ranks || lastOrganisms.map((o,i)=>({rank:i+1,...o})));\n    renderCadenceHistory(s.cadence_history || []);\n    renderBreedingLog(s.last_evolve);\n    renderJevLog(s);\n    document.getElementById(\'updated\').textContent =\n      \'updated \' + new Date().toLocaleTimeString() + \' · refresh 12s\';\n  } catch (e) {\n    document.getElementById(\'updated\').textContent = \'error: \' + e.message;\n  }\n}\nrefresh();\nsetInterval(refresh, 12000);\n</script>\n</body>\n</html>\n'

try:
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

    app = FastAPI(title="evo-fable", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def root() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/snapshot")
    def snapshot() -> dict[str, Any]:
        if _snapshot_fn is None:
            return {}
        return _snapshot_fn()

    @app.get("/api/export/snapshot")
    def export_snapshot() -> Response:
        snap = _snapshot_fn() if _snapshot_fn else {}
        body = json.dumps(snap, indent=2, default=str)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="snapshot.json"'},
        )

    @app.get("/api/export/pack")
    def export_pack() -> FileResponse:
        if _engine_ref is None or _snapshot_fn is None:
            return JSONResponse({"error": "no engine"}, status_code=503)  # type: ignore[return-value]
        snap = _snapshot_fn()
        now = None
        raw = snap.get("last_step_at") or snap.get("cadence_started_at")
        if raw:
            now = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        zip_path = create_export_pack(Path(_engine_ref.data_dir), snap, now=now)
        return FileResponse(
            path=str(zip_path),
            filename=zip_path.name,
            media_type="application/zip",
        )

except ImportError:  # pragma: no cover
    app = None  # type: ignore[assignment]


def serve(engine: Any, *, port: int = 8766, host: str = "127.0.0.1") -> None:
    global _snapshot_fn, _engine_ref
    if app is None:
        raise RuntimeError("pip install 'solana-evo-fable[dashboard]'")
    import uvicorn

    _snapshot_fn = engine.snapshot
    _engine_ref = engine
    uvicorn.run(app, host=host, port=port, log_level="warning")
