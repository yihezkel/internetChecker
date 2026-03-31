"""
Internet connectivity checker.

Continuously pings well-known URLs every 10 seconds and logs results to
output.csv.  Prevents the computer from sleeping while running.  Sounds an
audible alert when two consecutive checks fail.

Usage:
    python checker.py
"""

import collections
import csv
import ctypes
import datetime
import itertools
import os
import signal
import socket
import struct
import sys
import time
import winsound

import requests

# ── Configuration ────────────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 10
RETRY_INTERVAL_SECONDS = 3
REQUEST_TIMEOUT_SECONDS = 5
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.csv")

QUARANTINE_FAIL_THRESHOLD = 5      # failures needed to quarantine
QUARANTINE_WINDOW = 10             # out of last N attempts
QUARANTINE_PEER_PASS_RATE = 0.70   # peers must be this healthy
QUARANTINE_HOURS = 6               # hours to bench the endpoint

URLS = [
    "https://www.google.com",
    "https://www.bing.com",
    "https://www.microsoft.com",
    "https://www.apple.com",
    "https://www.who.int",
    "https://www.cloudflare.com",
    "https://www.wikipedia.org",
    "https://www.github.com",
    "https://www.youtube.com",
    "https://www.reddit.com",
    "https://www.yahoo.com",
    "https://www.facebook.com",
    "https://www.w3.org",
    "https://www.linkedin.com",
    "https://www.instagram.com",
    "https://www.netflix.com",
    "https://www.cnn.com",
    "https://www.bbc.com",
    "https://www.stackoverflow.com",
    "https://www.archive.org",
]

DNS_SERVERS = [
    ("8.8.8.8", "Google DNS"),
    ("8.8.4.4", "Google DNS 2"),
    ("1.1.1.1", "Cloudflare DNS"),
    ("1.0.0.1", "Cloudflare DNS 2"),
    ("9.9.9.9", "Quad9"),
    ("149.112.112.112", "Quad9 2"),
    ("208.67.222.222", "OpenDNS"),
    ("208.67.220.220", "OpenDNS 2"),
    ("76.76.2.0", "Control D"),
    ("76.76.10.0", "Control D 2"),
]

# ── Windows sleep prevention ────────────────────────────────────────────────

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def prevent_sleep():
    """Tell Windows to keep the system awake."""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    print("[INFO] Sleep prevention enabled.")


def allow_sleep():
    """Restore normal Windows sleep behaviour."""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    print("[INFO] Sleep prevention disabled.")


# ── Core helpers ─────────────────────────────────────────────────────────────

def check_tcp(url: str) -> bool:
    """Return True if a GET to *url* succeeds within the timeout."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
        return resp.status_code < 500
    except requests.RequestException:
        return False


def check_udp(server: str, domain: str = "google.com") -> bool:
    """Send a raw DNS A-record query over UDP and return True on response."""
    try:
        tid = struct.pack(">H", 0x1234)
        flags = struct.pack(">H", 0x0100)          # standard query, recursion desired
        counts = struct.pack(">HHHH", 1, 0, 0, 0)  # 1 question
        qname = b""
        for part in domain.split("."):
            qname += bytes([len(part)]) + part.encode()
        qname += b"\x00"
        qtype = struct.pack(">HH", 1, 1)            # type A, class IN
        query = tid + flags + counts + qname + qtype

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(REQUEST_TIMEOUT_SECONDS)
        sock.sendto(query, (server, 53))
        data, _ = sock.recvfrom(512)
        sock.close()
        return len(data) > 0
    except (socket.timeout, socket.error, OSError):
        return False


def ensure_csv(path: str) -> None:
    """Create the CSV with a header row if it doesn't already exist."""
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "success", "url", "protocol"])


# In-memory buffer for rows that couldn't be flushed (e.g. file open in Excel)
_pending_rows: list[list] = []


def flush_rows(path: str, rows: list[list]) -> bool:
    """Try to append *rows* to the CSV. Return True on success."""
    try:
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return True
    except PermissionError:
        return False


def append_result(path: str, timestamp: str, success: bool, url: str, protocol: str) -> None:
    """Buffer a data-point and flush everything we can to disk."""
    _pending_rows.append([timestamp, success, url, protocol])
    if flush_rows(path, _pending_rows):
        _pending_rows.clear()
    else:
        print(f"[WARN] File locked — buffered {len(_pending_rows)} row(s) in memory")


def alert_sound() -> None:
    """Play an unmistakable alert tone (three rising beeps)."""
    for freq in (800, 1000, 1200):
        winsound.Beep(freq, 300)
        time.sleep(0.05)


# ── Quarantine tracker ───────────────────────────────────────────────────────

class QuarantineTracker:
    """Track per-endpoint results and auto-quarantine bad endpoints."""

    def __init__(self):
        # endpoint_key -> deque of booleans (recent results, newest last)
        self._history: dict[str, collections.deque] = {}
        # endpoint_key -> datetime when quarantine expires
        self._quarantined: dict[str, datetime.datetime] = {}

    def _ensure(self, key: str) -> None:
        if key not in self._history:
            self._history[key] = collections.deque(maxlen=QUARANTINE_WINDOW)

    def is_quarantined(self, key: str) -> bool:
        """Return True if *key* is currently quarantined."""
        if key not in self._quarantined:
            return False
        if datetime.datetime.now() >= self._quarantined[key]:
            del self._quarantined[key]
            print(f"[INFO] Quarantine expired for {key}")
            return False
        return True

    def record(self, key: str, success: bool, protocol: str) -> None:
        """Record a result and quarantine the endpoint if warranted."""
        self._ensure(key)
        self._history[key].append(success)

        history = self._history[key]
        if len(history) < QUARANTINE_WINDOW:
            return

        fail_count = sum(1 for r in history if not r)
        if fail_count < QUARANTINE_FAIL_THRESHOLD:
            return

        # Check whether peers of the same protocol are healthy
        peer_results = []
        for other_key, other_hist in self._history.items():
            if other_key == key:
                continue
            if not other_key.endswith(f"|{protocol}"):
                continue
            if len(other_hist) == 0:
                continue
            # Use the last QUARANTINE_WINDOW results (or fewer if not enough)
            peer_results.append(sum(other_hist) / len(other_hist))

        if not peer_results:
            return

        avg_peer_pass = sum(peer_results) / len(peer_results)
        if avg_peer_pass >= QUARANTINE_PEER_PASS_RATE:
            expires = datetime.datetime.now() + datetime.timedelta(hours=QUARANTINE_HOURS)
            self._quarantined[key] = expires
            self._history[key].clear()
            print(
                f"[QUARANTINE] {key} benched until {expires.isoformat(timespec='seconds')}"
                f" ({fail_count}/{QUARANTINE_WINDOW} failed, peers {avg_peer_pass:.0%} healthy)"
            )


# ── Main loop ────────────────────────────────────────────────────────────────

def main() -> None:
    ensure_csv(OUTPUT_FILE)
    prevent_sleep()

    # Graceful shutdown on Ctrl+C
    def _shutdown(signum, frame):
        print("\n[INFO] Shutting down…")
        allow_sleep()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGBREAK, _shutdown)

    url_cycle = itertools.cycle(URLS)
    dns_cycle = itertools.cycle(DNS_SERVERS)
    consecutive_failures = 0
    quarantine = QuarantineTracker()

    print(f"[INFO] Logging to {OUTPUT_FILE}")
    print(f"[INFO] Checking every {CHECK_INTERVAL_SECONDS}s (retry {RETRY_INTERVAL_SECONDS}s on failure) — press Ctrl+C to stop.\n")

    while True:
        now = datetime.datetime.now().isoformat(timespec="seconds")

        # TCP check (HTTP GET) — skip quarantined endpoints
        for _ in range(len(URLS)):
            url = next(url_cycle)
            tcp_key = f"{url}|TCP"
            if not quarantine.is_quarantined(tcp_key):
                break
        else:
            url = next(url_cycle)
            tcp_key = f"{url}|TCP"

        tcp_ok = check_tcp(url)
        append_result(OUTPUT_FILE, now, tcp_ok, url, "TCP")
        quarantine.record(tcp_key, tcp_ok, "TCP")
        tcp_status = "OK" if tcp_ok else "FAIL"
        print(f"[{now}]  {tcp_status:4s}  TCP  {url}")

        # UDP check (DNS query) — skip quarantined endpoints
        for _ in range(len(DNS_SERVERS)):
            dns_server, dns_label = next(dns_cycle)
            target = f"{dns_server} ({dns_label})"
            udp_key = f"{target}|UDP"
            if not quarantine.is_quarantined(udp_key):
                break
        else:
            dns_server, dns_label = next(dns_cycle)
            target = f"{dns_server} ({dns_label})"
            udp_key = f"{target}|UDP"

        udp_ok = check_udp(dns_server)
        append_result(OUTPUT_FILE, now, udp_ok, target, "UDP")
        quarantine.record(udp_key, udp_ok, "UDP")
        udp_status = "OK" if udp_ok else "FAIL"
        print(f"[{now}]  {udp_status:4s}  UDP  {target}")

        cycle_ok = tcp_ok and udp_ok
        if cycle_ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                print("[ALERT] Internet appears DOWN — two consecutive failures!")
                alert_sound()

        time.sleep(CHECK_INTERVAL_SECONDS if cycle_ok else RETRY_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
