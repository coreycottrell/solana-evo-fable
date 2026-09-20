"""Invariant 5: no question without a computable label declaration."""

from __future__ import annotations

from evobot.questions import (
    LABEL_FACTORIES,
    QUESTION_SET,
    every_question_declares_computable_label,
    resolve_label_factory,
)


def test_every_question_declares_a_computable_label():
    bad = every_question_declares_computable_label(QUESTION_SET)
    assert bad == [], bad
    for qid, q in QUESTION_SET.items():
        factory = q["label"]["factory"]
        fn = resolve_label_factory(factory)
        assert callable(fn)
        assert factory in LABEL_FACTORIES
