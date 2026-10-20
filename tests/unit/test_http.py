"""Retrying directory listings when the server is slow or failing."""

import httpx
import pytest

from dwdopen._fileserver import http as http_module
from dwdopen._fileserver.http import HttpClient
from dwdopen.exceptions import CatalogueUnavailableError


def client_answering(answers, monkeypatch):
    """An HttpClient whose server gives the answers in order. An answer is a
    status code, or an exception to raise as if the network failed.
    """
    monkeypatch.setattr(http_module, "LISTING_BACKOFF", 0.0)
    calls = []

    def handler(request):
        calls.append(request.url.path)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, text="listing")

    client = HttpClient("https://example.test")
    client._client = httpx.Client(
        base_url="https://example.test", transport=httpx.MockTransport(handler)
    )
    return client, calls


def test_a_timeout_is_retried(monkeypatch):
    timeout = httpx.ConnectTimeout("The handshake operation timed out")
    client, calls = client_answering([timeout, 200], monkeypatch)
    assert client.get_listing("/m/") == "listing"
    assert len(calls) == 2


def test_a_server_error_is_retried(monkeypatch):
    client, calls = client_answering([503, 502, 200], monkeypatch)
    assert client.get_listing("/m/") == "listing"
    assert len(calls) == 3


def test_a_missing_directory_is_not_retried(monkeypatch):
    # An expired run answers 404, and latest_run() must move on quickly.
    client, calls = client_answering([404], monkeypatch)
    with pytest.raises(CatalogueUnavailableError):
        client.get_listing("/m/")
    assert len(calls) == 1


def test_retrying_gives_up_after_a_few_attempts(monkeypatch):
    client, calls = client_answering([503, 503, 503, 200], monkeypatch)
    with pytest.raises(CatalogueUnavailableError, match="503"):
        client.get_listing("/m/")
    assert len(calls) == 3
