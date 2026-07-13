"""Tests for session summary service."""

import pytest


def test_should_update_summary_returns_false_below_threshold():
    """Should not update summary when fewer than 10 new messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=15, last_summary_count=10) is False


def test_should_update_summary_returns_true_at_threshold():
    """Should update summary at exactly 10 new messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=20, last_summary_count=10) is True


def test_should_update_summary_returns_true_above_threshold():
    """Should update summary when more than 10 new messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=25, last_summary_count=10) is True


def test_should_update_summary_first_time():
    """Should update summary on first check after 10 messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=10, last_summary_count=0) is True


def test_should_update_summary_not_on_first_few():
    """Should not update with only a few messages."""
    from services.summary_service import should_update_summary
    assert should_update_summary(current_count=5, last_summary_count=0) is False
