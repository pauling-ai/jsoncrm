"""Identity, schema, and deterministic-order invariants for CRM records."""

from __future__ import annotations

import json
from datetime import date
from functools import cmp_to_key
from typing import Any

from jsoncrm.utils import normalize_url


class RecordError(ValueError):
    """A record operation could not be completed safely."""


class RecordNotFoundError(RecordError):
    pass


class DuplicateRecordError(RecordError):
    pass


class RecordValidationError(RecordError):
    pass


def identity_fields(config) -> list[str]:
    fields = [config.identity_primary, *config.identity_fallback]
    return list(dict.fromkeys(fields))


def record_identity(record: dict, fields: list[str]) -> tuple[str | None, Any]:
    for field in fields:
        value = record.get(field)
        if value is not None and value != "":
            return field, value
    return None, None


def require_identity(record: dict, fields: list[str]) -> tuple[str, Any]:
    field, value = record_identity(record, fields)
    if field is None:
        choices = " or ".join(repr(field) for field in reversed(fields))
        raise RecordValidationError(f"requires at least one of {choices}")
    return field, value


def identity_matches(record: dict, field: str, value: Any) -> bool:
    if field.endswith("_url"):
        return normalize_url(record.get(field, "")) == normalize_url(value)
    return record.get(field) == value


def _duplicate(record: dict, records: list[dict], fields: list[str]) -> tuple[str, Any] | None:
    for field in fields:
        value = record.get(field)
        if value is None or value == "":
            continue
        if any(identity_matches(existing, field, value) for existing in records):
            return field, value
    return None


def ensure_unique(record: dict, records: list[dict], fields: list[str]) -> None:
    duplicate = _duplicate(record, records, fields)
    if duplicate:
        field, value = duplicate
        raise DuplicateRecordError(f"record with {field} '{value}' already exists in the pipeline")


def _is_type(value: Any, type_name: str) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "iso-date":
        return _parse_iso_date(value) is not None
    raise RecordValidationError(f"unknown field type '{type_name}'")


def _parse_iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def record_errors(record: dict, stage: dict | None) -> list[str]:
    if not isinstance(record, dict):
        return ["record is not an object"]
    if not stage:
        return []

    errors = []
    for field, rule in stage.get("fields", {}).items():
        if rule.get("forbidden"):
            if field in record:
                errors.append(f"field '{field}' is forbidden")
            continue
        value = record.get(field)
        if rule.get("required") and (field not in record or value is None):
            errors.append(f"missing required field '{field}'")
            continue
        if field not in record or value is None:
            continue
        type_name = rule.get("type")
        if type_name and not _is_type(value, type_name):
            errors.append(f"field '{field}' must be {type_name}")
        if "enum" in rule and value not in rule["enum"]:
            errors.append(f"field '{field}' must be one of {rule['enum']!r}")

    sort = stage.get("sort")
    if sort:
        value = record.get(sort["key"])
        if value is not None and not _is_type(value, sort.get("type", "string")):
            errors.append(f"sort field '{sort['key']}' must be {sort.get('type', 'string')}")
    return errors


def ensure_valid_record(record: dict, stage: dict | None) -> None:
    errors = record_errors(record, stage)
    if errors:
        raise RecordValidationError("; ".join(errors))


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _compare_values(left: Any, right: Any) -> int:
    if left == right:
        return 0
    try:
        return -1 if left < right else 1
    except TypeError:
        return -1 if str(left) < str(right) else 1


def _sort_value(record: dict, key: str, type_name: str) -> Any:
    value = record.get(key)
    if value is None:
        return None
    if type_name == "iso-date":
        parsed = _parse_iso_date(value)
        if parsed is None:
            raise RecordValidationError(f"sort field '{key}' must be iso-date")
        return parsed
    if not _is_type(value, type_name):
        raise RecordValidationError(f"sort field '{key}' must be {type_name}")
    return value


def compare_records(left: dict, right: dict, stage: dict, fields: list[str]) -> int:
    sort = stage["sort"]
    key = sort["key"]
    type_name = sort.get("type", "string")
    left_value = _sort_value(left, key, type_name)
    right_value = _sort_value(right, key, type_name)

    if (left_value is None) != (right_value is None):
        left_last = sort.get("nulls", "last") == "last"
        if left_value is None:
            return 1 if left_last else -1
        return -1 if left_last else 1
    if left_value is not None:
        result = _compare_values(left_value, right_value)
        if result:
            return -result if sort.get("direction", "asc") == "desc" else result

    tiebreak = sort.get("tiebreak", fields)
    tiebreakers = [tiebreak] if isinstance(tiebreak, str) else list(tiebreak)
    for field in tiebreakers:
        result = _compare_values(left.get(field), right.get(field))
        if result:
            return result
    return _compare_values(_canonical(left), _canonical(right))


def sort_records(records: list[dict], stage: dict | None, fields: list[str]) -> list[dict]:
    if not stage or not stage.get("sort"):
        return list(records)
    sort = stage["sort"]
    if sort.get("direction", "asc") not in ("asc", "desc"):
        raise RecordValidationError("sort direction must be 'asc' or 'desc'")
    if sort.get("nulls", "last") not in ("first", "last"):
        raise RecordValidationError("sort nulls must be 'first' or 'last'")
    return sorted(records, key=cmp_to_key(lambda a, b: compare_records(a, b, stage, fields)))


def normalize_records(records: list[dict], stage: dict | None, fields: list[str]) -> list[dict]:
    if not isinstance(records, list):
        raise RecordValidationError("database file must be a JSON array")
    if any(not isinstance(record, dict) for record in records):
        raise RecordValidationError("every record must be a JSON object")
    return sort_records(records, stage, fields)
