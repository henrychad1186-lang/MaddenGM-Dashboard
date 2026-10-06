"""
Fetch a published Google Sheet as CSV, and nothing else.

The sidebar's "Google Sheet CSV URL" box used to hand whatever a visitor
typed to urlopen, so on a public deployment the server would fetch any
http(s) address on the visitor's behalf (cloud metadata at
169.254.169.254, services on the private network) and show the reply in
the Raw Data tab. Requests now go only to Google's sheet hosts, over
https, including every redirect, and the body is capped.

Other CSV hosts can be allowed by the app owner with the
SHEET_ALLOWED_HOSTS setting (env var or Streamlit secret): a
comma-separated list of hostnames, where a leading dot (".example.com")
also allows subdomains.
"""

import urllib.parse
import urllib.request

# docs.google.com serves the "Publish to web" link and redirects to a
# per-request host under googleusercontent.com.
DEFAULT_HOSTS = ("docs.google.com", ".googleusercontent.com")
MAX_BYTES = 5 * 1024 * 1024  # a season's log is a few KB
TIMEOUT = 20


class BlockedURL(ValueError):
    """The URL (or a redirect it led to) is not an allowed sheet host."""


def parse_hosts(setting) -> "tuple[str, ...]":
    """'a.com, .b.com' -> ('a.com', '.b.com'); blanks dropped."""
    if not setting:
        return ()
    return tuple(h.strip().lower() for h in str(setting).split(",") if h.strip())


def _host_allowed(host: str, allowed: "tuple[str, ...]") -> bool:
    host = (host or "").lower().rstrip(".")
    for rule in allowed:
        if rule.startswith("."):
            if host.endswith(rule) or host == rule[1:]:
                return True
        elif host == rule:
            return True
    return False


def check_url(url: str, extra_hosts: "tuple[str, ...]" = ()) -> None:
    """Raise BlockedURL unless `url` is https on an allowed host."""
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme.lower() != "https":
        raise BlockedURL("Sheet URL must start with https://")
    if parts.username or parts.password:
        raise BlockedURL("Sheet URL must not carry a username or password.")
    allowed = DEFAULT_HOSTS + tuple(extra_hosts)
    if not _host_allowed(parts.hostname or "", allowed):
        raise BlockedURL(
            f"Only Google Sheets links are accepted ({parts.hostname or 'no host'} "
            "isn't one). Use File → Share → Publish to web → CSV.")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Re-applies check_url to every hop, so an allowed host can't bounce
    the request somewhere that isn't."""

    def __init__(self, extra_hosts):
        super().__init__()
        self.extra_hosts = extra_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.extra_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, extra_hosts: "tuple[str, ...]"):
    opener = urllib.request.build_opener(_CheckedRedirects(extra_hosts))
    return opener.open(url, timeout=TIMEOUT)


def fetch_csv(url: str, extra_hosts: "tuple[str, ...]" = ()) -> bytes:
    """The CSV body at `url`. Raises BlockedURL, OSError, or ValueError
    (too large)."""
    check_url(url, extra_hosts)
    with _open(url.strip(), tuple(extra_hosts)) as resp:
        payload = resp.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"Sheet is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    return payload
