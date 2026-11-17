import argparse
import http.client
import json
import ipaddress
import re
import socket
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from lxml import html


from agentforge.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT
REPORTS = ROOT / "data" / "research"

ALLOWED_HOSTS = frozenset({
    "quanlynhanuoc.vn",
    "www.quanlynhanuoc.vn",
    "advertisingvietnam.com",
    "www.advertisingvietnam.com",
    "mps.gov.vn",
    "www.mps.gov.vn",
    "klmarketing.vn",
    "www.klmarketing.vn",
    "metric.vn",
    "www.metric.vn",
    "zonetech.com.vn",
    "www.zonetech.com.vn",
    "wpro.vn",
    "www.wpro.vn",
    "exceltudonghoa.com",
    "www.exceltudonghoa.com",
})

MAX_BYTES = 400_000
IPV6_GLOBAL_UNICAST = ipaddress.IPv6Network("2000::/3")


HOST_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:[.][a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
)


def validate_public_https_url(url):
    if (
        not isinstance(url, str)
        or not 1 <= len(url) <= 2048
        or url != url.strip()
        or "\\" in url
        or any(ord(char) < 32 or ord(char) == 127 for char in url)
    ):
        raise ValueError("Invalid URL")

    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc

    if (
        parsed.scheme != "https"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or not HOST_RE.fullmatch(host)
    ):
        raise ValueError("Only public HTTPS hostnames are allowed")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP literals are not allowed")

    if host.endswith(
        (".local", ".internal", ".localhost", ".test", ".invalid")
    ):
        raise ValueError("Reserved hostname is not allowed")

    return host



class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _public_socket(address, timeout, source_address):
    """Resolve once and connect using only the validated numeric address."""
    host, port = address
    records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM,
                                 proto=socket.IPPROTO_TCP)
    if not records or len(records) > 16:
        raise OSError("Unexpected DNS result count")
    for family, _, _, _, peer in records:
        ip = ipaddress.ip_address(peer[0])
        if (family not in (socket.AF_INET, socket.AF_INET6)
                or not ip.is_global or ip.is_multicast
                or (isinstance(ip, ipaddress.IPv6Address) and (
                    ip not in IPV6_GLOBAL_UNICAST or ip.sixtofour is not None))):
            raise PermissionError("Non-public DNS address refused")
    deadline = time.monotonic() + timeout
    for family, kind, proto, _, peer in records:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        conn = socket.socket(family, kind, proto)
        try:
            conn.settimeout(remaining)
            if source_address:
                conn.bind(source_address)
            conn.connect(peer)
        except OSError:
            conn.close()
        except BaseException:
            conn.close()
            raise
        else:
            return conn
    raise OSError("Could not connect to a validated public address")


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep the original hostname for SNI and certificate verification.
        self._create_connection = _public_socket


class _PublicHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req, context=self._context)


OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}), _PublicHTTPSHandler(), NoRedirect())


def fetch_page(url: str, *, allowed_hosts=None) -> dict:
    host = validate_public_https_url(url)

    allowlist = ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts

    if not isinstance(allowlist, (set, frozenset, list, tuple)):
        raise ValueError("Invalid host allowlist")

    if not all(isinstance(item, str) for item in allowlist):
        raise ValueError("Invalid host allowlist entries")

    if host not in allowlist:
        raise PermissionError(
            "URL is not on the approved HTTPS allowlist"
        )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AgentForgeResearch/0.1"}
    )

    with OPENER.open(request, timeout=15) as response:
        if response.headers.get_content_type() != "text/html":
            raise ValueError("Not an HTML page")

        raw = response.read(MAX_BYTES + 1)

        if len(raw) > MAX_BYTES:
            raise ValueError("Page exceeds size limit")

    parser = html.HTMLParser(encoding="utf-8")
    document = html.fromstring(raw, parser=parser)

    title_parts = document.xpath("//title/text()")
    title = title_parts[0].strip() if title_parts else ""

    for element in document.xpath(
        "//script | //style | //nav | //footer | //header | //svg"
    ):
        element.drop_tree()

    selectors = [
        "//*[@itemprop='articleBody']",
        "//article",
        "//div[contains(@class, 'entry-content')]",
        "//div[contains(@class, 'post-content')]",
        "//main",
        "//body",
    ]

    text = ""

    for selector in selectors:
        candidates = []

        for element in document.xpath(selector):
            parts = element.xpath(".//text()[normalize-space()]")

            candidate = " ".join(
                " ".join(
                    part.strip()
                    for part in parts
                    if part.strip()
                ).split()
            )

            if len(candidate) >= 300:
                candidates.append(candidate)

        if candidates:
            text = max(candidates, key=len)
            break

    if len(text) < 100:
        raise ValueError("Insufficient extracted page text")

    return {
        "title": title,
        "text_excerpt": text[:15000],
        "extracted_characters": len(text),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("research_id")
    args = parser.parse_args()

    research_id = args.research_id.lower()

    if len(research_id) != 32 or any(
        char not in "0123456789abcdef" for char in research_id
    ):
        raise SystemExit("Invalid research ID")

    report_path = REPORTS / f"{research_id}.json"

    with report_path.open("r", encoding="utf-8") as file:
        report = json.load(file)

    pages = []

    for source in report["sources"]:
        print("FETCHING:", source["source_id"], source["url"])

        record = {
            "source_id": source["source_id"],
            "url": source["url"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            result = fetch_page(source["url"])
            record.update(result)
            record["status"] = "FETCHED_NOT_FACT_CHECKED"

            print(
                "  FETCH: PASS",
                "| Characters:",
                result["extracted_characters"]
            )

        except Exception as error:
            record["status"] = "FETCH_FAILED"
            record["error"] = (
                f"{type(error).__name__}: {str(error)[:200]}"
            )
            print("  FETCH: FAILED", record["error"])

        pages.append(record)

    REPORTS.mkdir(parents=True, exist_ok=True)

    output = REPORTS / f"{research_id}_pages.json"

    output.write_text(
        json.dumps(
            {"research_id": research_id, "pages": pages},
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    successful = sum(
        item["status"] == "FETCHED_NOT_FACT_CHECKED"
        for item in pages
    )

    print("\nSOURCE READER COMPLETED")
    print("PAGES FETCHED:", successful, "/", len(pages))
    print("SAVED:", output)


if __name__ == "__main__":
    main()