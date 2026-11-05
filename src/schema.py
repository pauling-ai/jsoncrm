"""Shared constants for JSONCRM records and competitor lists."""

JSON_DB_ENCODING = "utf-8"

ACTIVE_COMPETITOR_COMPANY_KEYS = ("companies",)
ACTIVE_COMPETITOR_PERSON_KEYS = ("people",)
SKIPPED_COMPETITOR_COMPANY_KEYS = ("skipped_companies",)
SKIPPED_COMPETITOR_PERSON_KEYS = ("skipped_people",)
COMPETITOR_COMPANY_KEYS = ACTIVE_COMPETITOR_COMPANY_KEYS + SKIPPED_COMPETITOR_COMPANY_KEYS
COMPETITOR_PERSON_KEYS = ACTIVE_COMPETITOR_PERSON_KEYS + SKIPPED_COMPETITOR_PERSON_KEYS

SCORE_ORDER = {
    "⭐⭐⭐⭐⭐": 5,
    "⭐⭐⭐⭐": 4,
    "⭐⭐⭐": 3,
    "⭐⭐": 2,
    "⭐": 1,
}


def score_value(score):
    return SCORE_ORDER.get(score or "", 0)
