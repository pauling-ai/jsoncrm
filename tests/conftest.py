"""Shared test fixtures for jsoncrm tests."""

from pathlib import Path

import pytest


def _cleanup_pending_files():
    """Remove any .pending_update.json files that tests may have left behind."""
    # repo root
    Path(".pending_update.json").unlink(missing_ok=True)
    # test directory
    Path(__file__).parent.joinpath(".pending_update.json").unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _cleanup_pending_after_test():
    yield
    _cleanup_pending_files()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_pending_after_session():
    yield
    _cleanup_pending_files()
