from datetime import UTC, datetime

from dwdopen._fileserver.listing import parse_listing

RUNS = """<pre><a href="../">../</a>
<a href="2026-09-15T06%3A00/">2026-09-15T06:00/</a>   15-Sep-2026 08:42:25   -
<a href="2026-09-16T00%3A00/">2026-09-16T00:00/</a>   16-Sep-2026 02:40:29   -
</pre>"""

STEPS = """<pre><a href="../">../</a>
<a href="PT000H00M.grib2">PT000H00M.grib2</a>   16-Sep-2026 02:40:29   877797
<a href="PT120H00M.grib2">PT120H00M.grib2</a>   16-Sep-2026 03:15:22   864536
</pre>"""


def test_parent_is_skipped_and_hrefs_are_decoded():
    assert [e.name for e in parse_listing(RUNS)] == [
        "2026-09-15T06:00",
        "2026-09-16T00:00",
    ]


def test_long_names_come_from_the_href():
    long_name = "A_VERY_LONG_PARAMETER_NAME_THAT_NGINX_WILL_TRUNCATE_IN_DISPLAY"
    html = (
        f'<pre><a href="{long_name}/">'
        "A_VERY_LONG_PARAMETER_NAME_THAT_NGINX_WILL_TRUNCA..&gt;</a>"
        "   24-Aug-2026 09:55:26   -</pre>"
    )
    assert parse_listing(html)[0].name == long_name


def test_parameter_names_may_contain_a_dot():
    html = '<pre><a href="SYNMSG_BT_CL_IR10.8/">x</a>   24-Aug-2026 09:55:26   -</pre>'
    assert parse_listing(html)[0].name == "SYNMSG_BT_CL_IR10.8"


def test_directories_have_no_size():
    assert all(e.is_dir and e.size is None for e in parse_listing(RUNS))


def test_files_have_a_size():
    entries = parse_listing(STEPS)
    assert not any(e.is_dir for e in entries)
    assert [e.size for e in entries] == [877797, 864536]


def test_timestamps_are_utc():
    assert parse_listing(STEPS)[0].modified == datetime(
        2026, 9, 16, 2, 40, 29, tzinfo=UTC
    )


def test_empty_page():
    assert parse_listing("") == []