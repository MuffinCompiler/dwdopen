from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from dwdopen._fileserver.download import HttpDownloader
from dwdopen._fileserver.naming import local_name, temp_name
from dwdopen.exceptions import DownloadError
from dwdopen.nwp.request import Asset, ResolvedRequest
from dwdopen.nwp.run import Run

RUN = Run.coerce("2026-09-22T06:00")
RESOLVED_AT = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)

# A GRIB2 message is self-delimiting: it opens with "GRIB" and closes with
# "7777". These stand in for real messages; only the framing matters here.
def message(body: bytes) -> bytes:
    return b"GRIB" + body + b"7777"


def asset(parameter: str, hours: int, payload: bytes) -> Asset:
    step = f"PT{hours:03d}H00M.grib2"
    keys = (
        ("m", "icon-eu"),
        ("p", parameter),
        ("r", "2026-09-22T06:00"),
        ("s", step),
    )
    return Asset(
        keys=keys,
        run=RUN,
        step=timedelta(hours=hours),
        path="/".join(f"{k}/{v}" for k, v in keys),
        size=len(payload),
    )


class FakeHttp:
    """Serves a payload per path and can be told to fail a few times first."""

    def __init__(
        self,
        payloads: dict[str, bytes],
        failures: dict[str, list] | None = None,
    ):
        self.payloads = payloads
        self.failures = failures or {}
        self.requested: list[str] = []

    def get_asset(self, path: str) -> bytes:
        self.requested.append(path)
        queued = self.failures.get(path)
        if queued:
            raise queued.pop(0)
        return self.payloads[path]


def build(assets, failures=None):
    """Wire a downloader to a fake server, and to assets that agree with it.

    The advertised size has to match what the server serves, the way a real
    asset's size comes from the same listing the file does. Otherwise the
    already-downloaded check can never match and the fixture, not the code,
    decides the result.
    """
    payloads = {a.path: message(a.parameter.encode() + str(a.step).encode())
                for a in assets}
    sized = [replace(a, size=len(payloads[a.path])) for a in assets]
    assets[:] = sized
    http = FakeHttp(payloads, failures)
    return HttpDownloader(http, max_workers=4, backoff=0.0), http, payloads


# --- naming ---------------------------------------------------------------

def test_a_name_is_built_from_the_path_keys():
    name = local_name((("m", "icon-eu"), ("p", "T_2M"), ("s", "PT000H00M.grib2")))
    assert name == "m-icon-eu_p-T_2M_s-PT000H00M.grib2"


def test_a_colon_is_escaped_because_windows_rejects_it():
    name = local_name((("r", "2026-09-22T06:00"),))
    assert ":" not in name
    assert name == "r-2026-09-22T06%3A00"


def test_distinct_tokens_never_collapse_onto_one_name():
    assert local_name((("r", "a:b"),)) != local_name((("r", "a-b"),))


def test_a_temp_name_is_unique_per_writer():
    # Two writers must not stream into the same partial file.
    assert temp_name("x.grib2") != temp_name("x.grib2")
    assert temp_name("x.grib2").startswith("x.grib2.")


# --- layout ---------------------------------------------------------------

def test_combine_none_writes_one_named_file_per_asset(tmp_path):
    assets = [asset("T_2M", 0, b""), asset("PMSL", 3, b"")]
    downloader, _, payloads = build(assets)

    result = downloader.fetch(assets, tmp_path, combine="none")

    assert len(result.files) == 2
    on_disk = sorted(p.name for p in tmp_path.iterdir())
    assert on_disk == [
        "m-icon-eu_p-PMSL_r-2026-09-22T06%3A00_s-PT003H00M.grib2",
        "m-icon-eu_p-T_2M_r-2026-09-22T06%3A00_s-PT000H00M.grib2",
    ]
    assert result.files[0].read_bytes() == payloads[assets[0].path]


def test_combine_all_concatenates_in_the_given_order(tmp_path):
    assets = [asset("T_2M", 0, b""), asset("PMSL", 0, b""), asset("T_2M", 3, b"")]
    downloader, _, payloads = build(assets)

    result = downloader.fetch(assets, tmp_path / "out.grib2", combine="all")

    merged = result.files[0].read_bytes()
    assert merged == b"".join(payloads[a.path] for a in assets)
    assert merged.startswith(b"GRIB") and merged.endswith(b"7777")


def test_combine_all_leaves_no_staging_behind(tmp_path):
    assets = [asset("T_2M", 0, b"")]
    downloader, _, _ = build(assets)
    downloader.fetch(assets, tmp_path / "out.grib2", combine="all")
    assert [p.name for p in tmp_path.iterdir()] == ["out.grib2"]


def test_combine_all_ignores_files_it_did_not_download(tmp_path):
    """Another process may be writing the same directory at the same time."""
    stranger = tmp_path / "m-icon-eu_p-STRANGER_s-PT000H00M.grib2"
    stranger.write_bytes(message(b"not mine"))

    assets = [asset("T_2M", 0, b"")]
    downloader, _, payloads = build(assets)
    result = downloader.fetch(assets, tmp_path / "out.grib2", combine="all")

    assert result.files[0].read_bytes() == payloads[assets[0].path]
    assert b"not mine" not in result.files[0].read_bytes()
    assert stranger.exists()


def test_nothing_to_do_is_not_an_error(tmp_path):
    downloader, _, _ = build([])
    result = downloader.fetch([], tmp_path / "out.grib2", combine="all")
    assert result.files == () and result.bytes_downloaded == 0


# --- retries --------------------------------------------------------------

def test_a_server_error_is_retried():
    assets = [asset("T_2M", 0, b"")]
    failures = {assets[0].path: [DownloadError("boom", status=503)]}
    downloader, http, _ = build(assets, failures)

    downloader._get_with_retries(assets[0])
    assert len(http.requested) == 2


def test_a_forbidden_response_is_not_retried():
    assets = [asset("T_2M", 0, b"")]
    failures = {assets[0].path: [DownloadError("nope", status=403)]}
    downloader, http, _ = build(assets, failures)

    with pytest.raises(DownloadError):
        downloader._get_with_retries(assets[0])
    assert len(http.requested) == 1


def test_a_missing_asset_is_retried_but_not_forever():
    # 404 is ambiguous: the asset was in a listing moments ago, so it is either
    # expired or this request hit one of the servers behind opendata.dwd.de
    # that has not caught up. Treated as transient, but still bounded.
    assets = [asset("T_2M", 0, b"")]
    failures = {assets[0].path: [DownloadError("gone", status=404)] * 9}
    downloader, http, _ = build(assets, failures)

    with pytest.raises(DownloadError):
        downloader._get_with_retries(assets[0])
    assert len(http.requested) == 4  # max_attempts, not unbounded


def test_a_timeout_without_a_status_is_retried():
    assets = [asset("T_2M", 0, b"")]
    failures = {assets[0].path: [DownloadError("timeout")] * 2}
    downloader, http, _ = build(assets, failures)

    downloader._get_with_retries(assets[0])
    assert len(http.requested) == 3


# --- the domain side ------------------------------------------------------

def test_sorting_puts_time_first_so_cdo_can_read_the_result():
    # CDO drops variables from a file whose messages are not in time order.
    assets = [asset("T_2M", 3, b""), asset("PMSL", 0, b""), asset("T_2M", 0, b"")]
    ordered = sorted(assets, key=Asset.sort_key)
    assert [(a.step.seconds // 3600, a.parameter) for a in ordered] == [
        (0, "PMSL"), (0, "T_2M"), (3, "T_2M"),
    ]


def test_a_plan_without_a_downloader_says_so(tmp_path):
    plan = ResolvedRequest(run=RUN, assets=(), resolved_at=RESOLVED_AT)
    with pytest.raises(DownloadError, match="without a downloader"):
        plan.download(tmp_path / "out.grib2")


def test_the_downloader_is_not_part_of_a_plan_identity():
    downloader, _, _ = build([])
    a = ResolvedRequest(run=RUN, assets=(), resolved_at=RESOLVED_AT)
    b = ResolvedRequest(
        run=RUN, assets=(), resolved_at=RESOLVED_AT, downloader=downloader
    )
    assert a == b


def test_a_query_carries_no_run():
    """The run belongs to resolve()/download(), never to the selection.

    Two ways to name a run would mean silent precedence, and would leave
    combining two queries with different runs undefined.
    """
    import inspect

    from dwdopen.nwp.model import Model
    from dwdopen.nwp.query import Query

    assert "run" not in inspect.signature(Model.select).parameters
    assert "run" not in inspect.signature(Query.__init__).parameters
    assert "run" in inspect.signature(Query.resolve).parameters
    assert "run" in inspect.signature(Query.download).parameters


def test_a_finished_download_says_where_it_went(tmp_path, caplog):
    """A long transfer otherwise finishes in silence, leaving nothing in an
    unattended run's log to say it worked or where the file is.
    """
    import logging

    assets = [asset("T_2M", 0, b""), asset("T_2M", 3, b"")]
    downloader, _, _ = build(assets)

    with caplog.at_level(logging.INFO, logger="dwdopen"):
        downloader.fetch(assets, tmp_path / "out.grib2", combine="all")
    assert "saved" in caplog.text
    assert "out.grib2" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="dwdopen"):
        downloader.fetch(assets, tmp_path / "many", combine="none")
    assert "saved 2 files" in caplog.text
    assert "many" in caplog.text


# --- skipping what is already downloaded ----------------------------------

def test_a_correct_file_is_recognised(tmp_path):
    from dwdopen._fileserver.naming import already_complete

    good = tmp_path / "g.grib2"
    good.write_bytes(message(b"payload"))
    assert already_complete(good, good.stat().st_size)


def test_a_file_truncated_to_the_right_length_is_not_trusted(tmp_path):
    """The case a size check alone cannot catch.

    A download cut short by a full disk or a killed process can land on
    exactly the expected length; the GRIB terminator is what gives it away.
    """
    from dwdopen._fileserver.naming import already_complete

    body = message(b"payload")
    cut = tmp_path / "t.grib2"
    cut.write_bytes(b"GRIB" + b"\0" * (len(body) - 4))
    assert cut.stat().st_size == len(body)
    assert not already_complete(cut, len(body))


def test_a_wrong_size_or_missing_file_is_not_trusted(tmp_path):
    from dwdopen._fileserver.naming import already_complete

    small = tmp_path / "s.grib2"
    small.write_bytes(message(b"x"))
    assert not already_complete(small, 9999)
    assert not already_complete(tmp_path / "absent.grib2", 10)


def test_an_unknown_expected_size_means_fetch_it_again(tmp_path):
    # Nothing to compare against, so guessing would be worse than refetching.
    from dwdopen._fileserver.naming import already_complete

    good = tmp_path / "g.grib2"
    good.write_bytes(message(b"payload"))
    assert not already_complete(good, None)


def test_a_second_run_transfers_nothing(tmp_path):
    assets = [asset("T_2M", 0, b""), asset("T_2M", 3, b"")]
    downloader, http, _ = build(assets)

    first = downloader.fetch(assets, tmp_path, combine="none")
    assert first.skipped == 0
    assert len(http.requested) == 2

    second = downloader.fetch(assets, tmp_path, combine="none")
    assert second.skipped == 2
    assert second.bytes_downloaded == 0
    assert len(http.requested) == 2  # no further requests at all


def test_only_the_missing_file_comes_back(tmp_path):
    assets = [asset("T_2M", 0, b""), asset("T_2M", 3, b"")]
    downloader, http, _ = build(assets)

    result = downloader.fetch(assets, tmp_path, combine="none")
    result.files[0].unlink()
    before = len(http.requested)

    again = downloader.fetch(assets, tmp_path, combine="none")
    assert again.skipped == 1
    assert len(http.requested) == before + 1


def test_an_explicitly_named_combined_file_is_never_skipped(tmp_path):
    """A path the caller chose could hold anything, so it is always rewritten.

    Only a generated name carries the plan fingerprint that proves the file
    came from this exact selection.
    """
    from datetime import UTC, datetime

    from dwdopen.nwp.request import ResolvedRequest

    assets = [asset("T_2M", 0, b"")]
    downloader, http, _ = build(assets)
    plan = ResolvedRequest(
        run=RUN,
        assets=tuple(assets),
        resolved_at=datetime.now(UTC),
        downloader=downloader,
    )

    target = tmp_path / "mine.grib2"
    plan.download(target)
    before = len(http.requested)

    result = plan.download(target)
    assert result.assets_skipped == 0
    assert len(http.requested) > before


def test_a_generated_combined_name_is_skipped_on_a_second_run(tmp_path):
    from datetime import UTC, datetime

    from dwdopen.nwp.request import ResolvedRequest

    assets = [asset("T_2M", 0, b""), asset("T_2M", 3, b"")]
    downloader, http, _ = build(assets)
    plan = ResolvedRequest(
        run=RUN,
        assets=tuple(assets),
        resolved_at=datetime.now(UTC),
        downloader=downloader,
    )

    first = plan.download(tmp_path)
    assert first.assets_skipped == 0
    before = len(http.requested)

    second = plan.download(tmp_path)
    assert second.assets_skipped == 2
    assert second.assets_downloaded == 0
    assert second.files == first.files
    assert len(http.requested) == before  # nothing fetched
