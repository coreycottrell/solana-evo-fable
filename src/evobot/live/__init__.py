"""Live holdout tail — the ONLY package allowed to read the wall clock.

Everything outside ``live/`` must receive ``now`` (injected). See MISSION
invariant 2 and ``tests/invariants/test_no_wall_clock_outside_live.py``.
"""
