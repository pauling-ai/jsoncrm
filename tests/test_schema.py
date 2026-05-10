"""Unit tests for jsoncrm.schema constants and helpers."""

import sys
from pathlib import Path


from jsoncrm.schema import (
    ACTIVE_COMPETITOR_COMPANY_KEYS,
    ACTIVE_COMPETITOR_PERSON_KEYS,
    COMPETITOR_COMPANY_KEYS,
    COMPETITOR_PERSON_KEYS,
    SCORE_ORDER,
    SKIPPED_COMPETITOR_COMPANY_KEYS,
    SKIPPED_COMPETITOR_PERSON_KEYS,
    score_value,
)


def test_score_order_mappings():
    assert SCORE_ORDER["⭐⭐⭐⭐⭐"] == 5
    assert SCORE_ORDER["⭐⭐⭐⭐"] == 4
    assert SCORE_ORDER["⭐⭐⭐"] == 3
    assert SCORE_ORDER["⭐⭐"] == 2
    assert SCORE_ORDER["⭐"] == 1


def test_score_value_happy_path():
    assert score_value("⭐⭐⭐⭐⭐") == 5
    assert score_value("⭐⭐") == 2


def test_score_value_unknown_returns_zero():
    assert score_value("not-a-score") == 0
    assert score_value("") == 0


def test_score_value_none_returns_zero():
    assert score_value(None) == 0


def test_competitor_key_unions():
    assert COMPETITOR_COMPANY_KEYS == ACTIVE_COMPETITOR_COMPANY_KEYS + SKIPPED_COMPETITOR_COMPANY_KEYS
    assert COMPETITOR_PERSON_KEYS == ACTIVE_COMPETITOR_PERSON_KEYS + SKIPPED_COMPETITOR_PERSON_KEYS
