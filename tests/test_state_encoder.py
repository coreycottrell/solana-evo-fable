from evobot.state_encoder import encode_market_state, state_fingerprint


def test_encode_deterministic_buckets():
    prices = [100.0 + i * 0.05 for i in range(80)]
    a = encode_market_state(prices)
    b = encode_market_state(prices)
    assert a == b
    assert state_fingerprint(a) == state_fingerprint(b)
    assert a["vol"] in {"very_low", "low", "mid", "high", "very_high"}
