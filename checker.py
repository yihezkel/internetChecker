"""
Internet connectivity checker.

Continuously pings well-known URLs every 10 seconds and logs results to
output.csv.  Prevents the computer from sleeping while running.  Sounds an
audible alert when two consecutive checks fail.

Usage:
    python checker.py
"""

import csv
import ctypes
import datetime
import itertools
import os
import signal
import sys
import time
import winsound

import requests

# ── Configuration ────────────────────────────────────────────────────────────

CHECK_INTERVAL_SECONDS = 10
REQUEST_TIMEOUT_SECONDS = 5
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.csv")

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

def check_url(url: str) -> bool:
    """Return True if a GET to *url* succeeds within the timeout."""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
        return resp.status_code < 500
    except requests.RequestException:
        return False


def ensure_csv(path: str) -> None:
    """Create the CSV with a header row if it doesn't already exist."""
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "success", "url"])


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


def append_result(path: str, timestamp: str, success: bool, url: str) -> None:
    """Buffer a data-point and flush everything we can to disk."""
    _pending_rows.append([timestamp, success, url])
    if flush_rows(path, _pending_rows):
        _pending_rows.clear()
    else:
        print(f"[WARN] File locked — buffered {len(_pending_rows)} row(s) in memory")


def alert_sound() -> None:
    """Play an unmistakable alert tone (three rising beeps)."""
    for freq in (800, 1000, 1200):
        winsound.Beep(freq, 300)
        time.sleep(0.05)


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
    consecutive_failures = 0

    print(f"[INFO] Logging to {OUTPUT_FILE}")
    print(f"[INFO] Checking every {CHECK_INTERVAL_SECONDS}s — press Ctrl+C to stop.\n")

    while True:
        url = next(url_cycle)
        now = datetime.datetime.now().isoformat(timespec="seconds")
        success = check_url(url)
        append_result(OUTPUT_FILE, now, success, url)

        status = "OK" if success else "FAIL"
        print(f"[{now}]  {status:4s}  {url}")

        if success:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                print("[ALERT] Internet appears DOWN — two consecutive failures!")
                alert_sound()

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
