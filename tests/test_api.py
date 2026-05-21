"""Tests for API parsing."""

from __future__ import annotations

from custom_components.bayrol_bridge.api import _parse_pool_data


def test_parse_pool_data_stat_warning_not_alarm() -> None:
    """stat_warning on a tile is normal status colour, not an alarm."""
    html = """
    <html><body>
    <div class="tab_box stat_warning"><span>pH</span><h1>7.1</h1></div>
    <div class="tab_box stat_warning"><span>Temp.</span><h1>17</h1></div>
    </body></html>
    """
    data = _parse_pool_data(html)
    assert data["pH"] == 7.1
    assert data["T"] == 17.0
    assert data["pH_alarm"] is False
    assert data["T_alarm"] is False


def test_parse_pool_data_stat_alarm_is_alarm() -> None:
    """stat_alarm on a tile signals a real problem."""
    html = """
    <html><body>
    <div class="tab_box stat_alarm"><span>pH</span><h1>8.5</h1></div>
    </body></html>
    """
    data = _parse_pool_data(html)
    assert data["pH"] == 8.5
    assert data["pH_alarm"] is True
