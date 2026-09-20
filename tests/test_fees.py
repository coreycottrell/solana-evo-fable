"""Fee math leaf — transplanted assertions from v1 test_fees.py."""

from __future__ import annotations

from evobot.fees import FeesConfig, passes_min_edge_gate, round_trip_fee_drag_bps


def test_round_trip_fee_drag_bps_rule_of_thumb():
    fees = FeesConfig(gas_usd_per_tx=0.03, swap_fee_bps=10.0)
    # $100: swap=$0.10; side=$0.13; RT=$0.26 → 26 bps
    drag = round_trip_fee_drag_bps(100.0, fees)
    assert abs(drag - 26.0) < 1e-6
    drag_big = round_trip_fee_drag_bps(1000.0, fees)
    assert abs(drag_big - 20.6) < 1e-6


def test_soft_edge_gate_rejects_tiny_size():
    fees = FeesConfig(gas_usd_per_tx=0.03, swap_fee_bps=10.0, min_net_edge_bps=15.0)
    assert not passes_min_edge_gate(size_usd=5.0, strength=1.0, fees=fees)
    assert passes_min_edge_gate(size_usd=100.0, strength=0.2, fees=fees)
    assert not passes_min_edge_gate(size_usd=100.0, strength=0.0, fees=fees)
