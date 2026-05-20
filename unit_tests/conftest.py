"""Fixtures for API unit tests (no Home Assistant test harness)."""

from __future__ import annotations

import pytest


@pytest.fixture
def login_form_html() -> str:
    """Minimal Bayrol login form."""
    return """
    <html><body>
    <form id="form_login" method="post">
      <input type="hidden" name="token" value="abc123" />
      <input type="text" name="username" value="" />
      <input type="password" name="password" value="" />
    </form>
    </body></html>
    """


@pytest.fixture
def plants_html() -> str:
    """Minimal plants page with one controller."""
    return """
    <html><body>
    <div class="tab_row">
      <div class="tab_1"><p>Pool Relax</p></div>
      <div class="tab_2" id="tab_data42">
        <div class="tab_info"><span>ID123</span><span>Pool Relax</span></div>
      </div>
    </div>
    </body></html>
    """


@pytest.fixture
def pool_data_html() -> str:
    """Minimal getdata response."""
    return """
    <html><body>
    <div class="tab_box"><span>pH</span><h1>7.2</h1></div>
    <div class="tab_box"><span>Redox</span><h1>650</h1></div>
    <div class="tab_box"><span>Temp.</span><h1>24.5</h1></div>
    </body></html>
    """


@pytest.fixture
def device_html() -> str:
    """Minimal device page with dosing item classes."""
    return """
    <html><body>
    <div class="i_item item5_42 i_active"></div>
    <div class="i_item item5_154 i_inactive"></div>
    </body></html>
    """
