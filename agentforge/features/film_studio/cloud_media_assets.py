"""Shared HTTPS media download and 720p/24fps video normalization."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit
from uuid import uuid4

from agentforge.features.media import mp4, render
from agentforge.paths import ensure_local_root


def _public_addresses(host):
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast
                            for ip in addresses):
        raise ValueError("Cloud media download host must resolve exclusively to public addresses.")
    return sorted(addresses)


def download_to(url, stream, max_bytes):
    if not isinstance(url, str):
        raise ValueError("Invalid Cloud media download URL.")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443} or not parsed.path or parsed.fragment
            or any(ord(c) < 33 for c in url)):
        raise ValueError("Unsafe Cloud media download URL.")
    # Pin the validated address, but verify TLS against the original host.
    # No authorization header and no redirects to arbitrary destinations.
    address = _public_addresses(parsed.hostname)[0]
    conn = http.client.HTTPSConnection(parsed.hostname, timeout=30)
    try:
        with socket.create_connection((address, 443), timeout=30) as sock:
            conn.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
            conn.request("GET", parsed.path + ("?" + parsed.query if parsed.query else ""))
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError("Cloud media download unavailable.")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Cloud media output exceeds size limit.")
                stream.write(chunk)
    except (OSError, http.client.HTTPException):
        raise ValueError("Cloud media download failed.") from None
    finally:
        conn.close()


def _download(url, target):
    with target.open("xb") as stream:
        download_to(url, stream, mp4.MAX_VIDEO_BYTES)


def download_normalized(url, target, seconds):
    raw = ensure_local_root(target.with_name(uuid4().hex + ".raw.mp4"))
    try:
        _download(url, raw)
        # Normalize provider FPS / dimensions; never synthesize missing duration.
        # Native audio is not advertised until verified against the real provider.
        render._run_process([render._ffmpeg(), "-nostdin", "-n", "-v", "error", "-xerror",
            "-protocol_whitelist", "file,pipe", "-f", "mov", "-i", str(raw), "-map", "0:v:0", "-an",
            "-vf", "fps=24,scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1",
            "-frames:v", str(seconds * 24), "-c:v", "libx264", "-threads", "2",
            "-pix_fmt", "yuv420p", str(target)], cwd=target.parent, timeout=150)
    finally:
        raw.unlink(missing_ok=True)
