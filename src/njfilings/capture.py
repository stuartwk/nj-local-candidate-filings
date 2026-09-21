"""Fetch the declared documents and record what came back.

This is the only module that touches the network, and it is deliberately dumb:
it fetches bytes, writes them to `cache/<county>/<year>/<filename>`, and appends
one row per attempt to `data/manifest.csv`. It does not open, decode, or
interpret a single document — every file lands byte-for-byte as served, and
whether it is a usable PDF is a question for the parsers.

Three rules shape the loop:

  * A document already held byte-identical is not re-fetched: if the manifest's
    sha256 for a URL still matches the file on disk, no request goes out. The
    manifest records the *change*, not the run — a held document whose last
    recorded outcome was the same sha256 adds no row, while a first sight or a
    recovery after a failed fetch does. Every run still prints what it saw.
    (A document revised upstream under the same URL is therefore not noticed;
    `--refetch` is how you look.)
  * Requests are paced at roughly one per second per host, counted from the end
    of one request to the start of the next, so a slow response never buys a
    faster follow-up.
  * A failure is data. Any one document may 404, time out, or refuse to
    resolve; that outcome is written to the manifest and the run continues.
    Nothing a single document does raises out of this module. Failures follow
    the same change-only rule: a URL that failed the same way last time adds no
    row, while a new failure, a changed status, or a document that has stopped
    working does.

Usage:
    python -m njfilings.capture                          # everything declared
    python -m njfilings.capture --county bergen --year 2025
    python -m njfilings.capture --dry-run                # plan only, no network
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .sources import COUNTIES, KNOWN_GAPS, Document, documents

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_FIELDS = [
    "url", "sha256", "fetched_at", "county", "year", "doc_type",
    "local_path", "http_status", "content_type", "bytes", "note",
]

USER_AGENT = ("nj-local-candidate-filings/0.1 (research; contact via repository)")

DEFAULT_DELAY = 1.0     # seconds between requests to one host
DEFAULT_TIMEOUT = 30.0


def utc_now() -> str:
    """Timestamp for the manifest: UTC, ISO 8601, second resolution."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class HostThrottle:
    """One request per `delay` seconds per host, measured request-to-request."""

    def __init__(self, delay: float = DEFAULT_DELAY):
        self.delay = delay
        self._ready_at: dict[str, float] = {}

    def wait(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        now = time.monotonic()
        ready = self._ready_at.get(host, 0.0)
        if now < ready:
            time.sleep(ready - now)
        # the clock starts when the request goes out, and is pushed back again
        # once it returns, so a slow response does not shorten the next gap
        self._ready_at[host] = time.monotonic() + self.delay

    def done(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        self._ready_at[host] = time.monotonic() + self.delay


class Manifest:
    """Append-only record of every fetch attempt."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict[str, str]] = []
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                self.rows = list(csv.DictReader(fh))

    def held(self, doc: Document, root: Path) -> str | None:
        """The sha256 we already hold for this document, or None.

        A previous row counts only if the file it named is still on disk and
        still hashes to what the row recorded.
        """
        for row in reversed(self.rows):
            if row.get("url") != doc.url or not row.get("sha256"):
                continue
            local = root / (row.get("local_path") or "")
            if local.is_file() and sha256_file(local) == row["sha256"]:
                return row["sha256"]
            return None        # the newest record for this URL no longer holds
        return None

    def last_row(self, url: str) -> dict[str, str] | None:
        """The most recent row for this URL, whatever its outcome."""
        for row in reversed(self.rows):
            if row.get("url") == url:
                return row
        return None

    def append(self, row: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        out = {k: ("" if row.get(k) is None else str(row.get(k)))
               for k in MANIFEST_FIELDS}
        # written and flushed per row: an interrupted run keeps its record
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(out)
        self.rows.append(out)


def _failure_outcome(row: dict[str, str] | None) -> str | None:
    """How the last recorded run for a URL failed, or None if it did not.

    Distinguishing the three shapes of row matters here: a held row carries a
    sha256 and no status, a transport error carries neither, and an HTTP failure
    carries a status.
    """
    if row is None:
        return None
    status = (row.get("http_status") or "").strip()
    if status:
        return f"http {status}" if status != "200" else None
    if row.get("sha256"):
        return None                      # held: we have the bytes
    return (row.get("note") or "error").split(":")[0]


@dataclass
class Counts:
    fetched: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (f"{self.fetched} fetched, {self.skipped} already held, "
                f"{self.failed} failed")


def _write_atomically(path: Path, data: bytes) -> None:
    """Write via a temp file so an interrupted run leaves no half document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def capture(docs: list[Document], root: Path = PROJECT_ROOT,
            delay: float = DEFAULT_DELAY, timeout: float = DEFAULT_TIMEOUT,
            refetch: bool = False, verbose: bool = True,
            transport: httpx.BaseTransport | None = None) -> Counts:
    """Fetch each document once, recording every outcome. Never raises for a
    single document's failure."""
    manifest = Manifest(root / "data" / "manifest.csv")
    throttle = HostThrottle(delay)
    counts = Counts()
    width = len(str(len(docs)))

    def log(i: int, doc: Document, outcome: str, detail: str = "") -> None:
        if verbose:
            name = f"{doc.county} {doc.year} {doc.filename}"
            print(f"[{i:>{width}}/{len(docs)}] {name:<52} {outcome:<9} {detail}",
                  flush=True)

    with httpx.Client(follow_redirects=True, timeout=timeout,
                      headers={"User-Agent": USER_AGENT},
                      transport=transport) as client:
        for i, doc in enumerate(docs, 1):
            base = dict(url=doc.url, county=doc.county, year=doc.year,
                        doc_type=doc.doc_type, note=doc.label)

            if not refetch:
                held = manifest.held(doc, root)
                if held:
                    counts.skipped += 1
                    previous = manifest.last_row(doc.url)
                    # The ledger records changes, not heartbeats. Scheduled
                    # capture runs daily for months across ~1,500 documents; a
                    # row every night saying nothing happened would bury the
                    # nights something did. So a row goes in only when this
                    # outcome differs from the last one recorded for the URL —
                    # first sight, or recovery after a failed fetch. An empty
                    # http_status marks a row as "nothing was asked of the
                    # server".
                    if previous is None or previous.get("sha256") != held:
                        manifest.append({
                            **base, "sha256": held, "fetched_at": utc_now(),
                            "local_path": doc.local_path,
                            "bytes": (root / doc.local_path).stat().st_size,
                            "note": f"held, not re-fetched{'; ' + doc.label if doc.label else ''}",
                        })
                    log(i, doc, "held", held[:12])
                    continue

            throttle.wait(doc.url)
            try:
                response = client.get(doc.url)
            except Exception as exc:                  # noqa: BLE001 — see docstring
                throttle.done(doc.url)
                counts.failed += 1
                # a URL that failed the same way last time is not news
                if _failure_outcome(manifest.last_row(doc.url)) != type(exc).__name__:
                    manifest.append({**base, "fetched_at": utc_now(),
                                     "note": f"{type(exc).__name__}: {exc}"})
                log(i, doc, "error", type(exc).__name__)
                continue
            throttle.done(doc.url)

            fetched_at = utc_now()
            content_type = response.headers.get("content-type", "")
            row = {**base, "fetched_at": fetched_at,
                   "http_status": response.status_code,
                   "content_type": content_type}

            if response.status_code != 200:
                # nothing is cached for a non-200: the body is an error page,
                # not a document, and recording its bytes would misreport it.
                # As with a held document, only a change earns a row — some of
                # these URLs are permanently dead and get asked every run.
                counts.failed += 1
                previous = _failure_outcome(manifest.last_row(doc.url))
                if previous != f"http {response.status_code}":
                    manifest.append(row)
                log(i, doc, "http", str(response.status_code))
                continue

            body = response.content
            digest = sha256_bytes(body)
            local = root / doc.local_path
            _write_atomically(local, body)
            counts.fetched += 1
            manifest.append({**row, "sha256": digest,
                             "local_path": doc.local_path, "bytes": len(body)})
            log(i, doc, "fetched", f"{len(body):>9,} bytes  {digest[:12]}")

    return counts


def plan(docs: list[Document]) -> None:
    for doc in docs:
        print(f"{doc.county:<10} {doc.year}  {doc.doc_type:<15} "
              f"{doc.local_path:<44} {doc.url}")
    print(f"\n{len(docs)} documents declared")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m njfilings.capture",
        description="Fetch declared county documents into the local cache.")
    parser.add_argument("--county", action="append", metavar="NAME",
                        choices=sorted(COUNTIES), help="repeatable; default all")
    parser.add_argument("--year", action="append", metavar="YYYY",
                        help="repeatable; default all")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="stop after N documents")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        metavar="SECONDS", help="per-host pacing (default 1.0)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        metavar="SECONDS")
    parser.add_argument("--refetch", action="store_true",
                        help="fetch even where the held copy still matches")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan; touch neither network nor manifest")
    parser.add_argument("--gaps", action="store_true",
                        help="list known cycles with no established URL, and exit")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT,
                        help="project root holding cache/ and data/")
    args = parser.parse_args(argv)

    if args.gaps:
        for county, year, note in KNOWN_GAPS:
            print(f"{county:<10} {year}  {note}")
        return 0

    docs = documents(args.county, args.year)
    if args.limit:
        docs = docs[:args.limit]
    if not docs:
        print("nothing matches that selection", file=sys.stderr)
        return 1

    if args.dry_run:
        plan(docs)
        return 0

    counts = capture(docs, root=args.root, delay=args.delay,
                     timeout=args.timeout, refetch=args.refetch)
    print(f"\n{counts}  ->  {args.root / 'data' / 'manifest.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
