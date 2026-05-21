"""Tests for diagnostic sanitization helpers."""

from __future__ import annotations

from custom_components.bayrol_bridge.diagnostics import _sanitize_obj, _sanitize_text


def test_sanitize_text_masks_sensitive_values() -> None:
    """Emails, CID, tokens, and sessions are masked."""
    cid = "42"
    text = (
        "user@pool.example.com "
        f"device={cid} "
        "token abcdef0123456789 "
        "PHPSESSID=deadbeefcafe"
    )
    result = _sanitize_text(text, cid=cid, max_len=500)

    assert "user@pool.example.com" not in result
    assert "<email>" in result
    assert cid not in result
    assert "<cid>" in result
    assert "abcdef0123456789" not in result
    assert "<token>" in result
    assert "deadbeefcafe" not in result
    assert "<session>" in result


def test_sanitize_text_truncates_long_output() -> None:
    """Oversized text is truncated with a marker."""
    result = _sanitize_text("x" * 7000, max_len=100)
    assert result.endswith("...truncated")
    assert len(result) <= 100


def test_sanitize_obj_recurses() -> None:
    """Nested structures have all string leaves sanitized."""
    obj = {
        "sent": {"action": "getItems"},
        "body_excerpt": "mail@test.de abcdef0123456789",
        "nested": ["PHPSESSID=secret"],
    }
    result = _sanitize_obj(obj, cid="42", max_len=2000)

    dumped = str(result)
    assert "mail@test.de" not in dumped
    assert "<email>" in dumped
    assert "abcdef0123456789" not in dumped
    assert "PHPSESSID=secret" not in dumped
    assert "<session>" in dumped
