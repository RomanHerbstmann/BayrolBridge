"""Tests for device page HTML sanitization."""

from __future__ import annotations

import json

from custom_components.bayrol_bridge.api import _sanitize_device_html

SAMPLE_HTML = """
<html><head>
<script>alert('x')</script>
<style>.x { color: red; }</style>
</head><body>
<svg><circle/></svg>
<p>Contact user@secret.example.com</p>
<div id="tab_data42" class="tab_data outer">
  <div class="tab_box stat_warning">
    <span>pH</span>
    <h1>7.1</h1>
    <p>serial abcdef0123456789</p>
  </div>
  <div class="item5_42 i_active dosing box">
    <span>pH dosing</span>
  </div>
</div>
</body></html>
"""


def test_sanitize_device_html_structure_and_redaction() -> None:
    """Sanitized excerpt includes classes/text; strips scripts and masks secrets."""
    cid = "42"
    result = _sanitize_device_html(SAMPLE_HTML, cid=cid)

    assert isinstance(result, list)
    assert result

    tags = {entry["tag"] for entry in result}
    assert "script" not in tags
    assert "style" not in tags
    assert "svg" not in tags

    tab_boxes = [e for e in result if "tab_box" in e.get("class", [])]
    assert tab_boxes
    assert any("stat_warning" in e["class"] for e in tab_boxes)

    items = [e for e in result if any("item" in c for c in e.get("class", []))]
    assert items
    assert any("i_active" in e["class"] for e in items)

    dumped = json.dumps(result)
    assert "user@secret.example.com" not in dumped
    assert "<email>" in dumped
    assert "abcdef0123456789" not in dumped
    assert "<token>" in dumped or "<digits>" in dumped
    assert cid not in dumped
    assert "<cid>" in dumped
    assert "alert" not in dumped


def test_sanitize_device_html_truncation() -> None:
    """Output is capped by element count and total character budget."""
    blocks = []
    for i in range(200):
        blocks.append(
            f'<div class="tab_box item{i}"><span>block {i} '
            f"{'x' * 100}</span></div>"
        )
    html = "<html><body>" + "".join(blocks) + "</body></html>"
    result = _sanitize_device_html(html)

    assert len(result) <= 151
    assert result[-1]["text"] == "...truncated"
    assert len(json.dumps(result)) <= 8100
