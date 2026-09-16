import pytest

from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.listing import parse_listing

pytestmark = pytest.mark.live


def test_model_listing_is_readable():
    http = HttpClient("https://opendata.dwd.de")
    try:
        entries = parse_listing(http.get_listing("weather/nwp/v1/m/"))
    finally:
        http.close()

    assert "icon-eu" in [e.name for e in entries]