"""The sheet sync may only fetch from Google's sheet hosts."""

import io
import urllib.request

import pytest

from src import sheet_fetch as sf

SHEET = "https://docs.google.com/spreadsheets/d/e/abc/pub?output=csv"


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",      # cloud metadata
    "https://169.254.169.254/latest/meta-data/",
    "https://localhost:8501/",
    "https://10.0.0.5/admin.csv",
    "file:///etc/passwd",
    "http://docs.google.com/spreadsheets/x",         # not https
    "https://docs.google.com.evil.example/x.csv",    # look-alike
    "https://evilgoogleusercontent.com/x.csv",       # suffix without the dot
    "https://user:pw@docs.google.com/x",
    "https://example.com/data.csv",
])
def test_blocked(url):
    with pytest.raises(sf.BlockedURL):
        sf.check_url(url)


@pytest.mark.parametrize("url", [
    SHEET,
    "https://DOCS.GOOGLE.COM/spreadsheets/d/e/abc/pub?output=csv",
    "https://doc-0s-1c-sheets.googleusercontent.com/pub/abc",
])
def test_allowed(url):
    sf.check_url(url)


def test_owner_can_allow_another_host():
    hosts = sf.parse_hosts(" data.example.com, .cdn.example.org ,")
    assert hosts == ("data.example.com", ".cdn.example.org")
    sf.check_url("https://data.example.com/log.csv", hosts)
    sf.check_url("https://a.cdn.example.org/log.csv", hosts)
    with pytest.raises(sf.BlockedURL):
        sf.check_url("https://other.example.com/log.csv", hosts)


def test_redirect_to_a_blocked_host_is_refused():
    handler = sf._CheckedRedirects(())
    req = urllib.request.Request(SHEET)
    with pytest.raises(sf.BlockedURL):
        handler.redirect_request(req, None, 302, "Found", {},
                                 "http://169.254.169.254/latest/meta-data/")
    # Google's own hop is fine.
    ok = handler.redirect_request(req, None, 302, "Found", {},
                                  "https://doc-0s-sheets.googleusercontent.com/pub/abc")
    assert ok.full_url.startswith("https://doc-0s-sheets.googleusercontent.com/")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_never_opens_a_blocked_url(monkeypatch):
    opened = []
    monkeypatch.setattr(sf, "_open", lambda url, hosts: opened.append(url) or _Resp(b""))
    with pytest.raises(sf.BlockedURL):
        sf.fetch_csv("http://169.254.169.254/")
    assert opened == []


def test_oversized_sheet_is_refused(monkeypatch):
    monkeypatch.setattr(sf, "_open", lambda url, hosts: _Resp(b"x" * (sf.MAX_BYTES + 10)))
    with pytest.raises(ValueError, match="larger than"):
        sf.fetch_csv(SHEET)


def test_fetch_returns_the_body(monkeypatch):
    monkeypatch.setattr(sf, "_open", lambda url, hosts: _Resp(b"a,b\n1,2\n"))
    assert sf.fetch_csv(SHEET) == b"a,b\n1,2\n"
