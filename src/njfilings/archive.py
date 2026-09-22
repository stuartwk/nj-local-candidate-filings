"""Ask the Internet Archive to keep its own copy of everything we captured.

Build plan 2.3. Capture proves to *us* that a URL served certain bytes; this
proves it to everyone else. The manifest's claim is only as good as the cache
backing it, and the cache is one gitignored directory on one machine. A Save
Page Now submission puts an independent, citable copy somewhere that outlives
both this repo and the county's own retention policy — which, for most of these
clerks, is "until the next election".

It is also self-serving: Morris and Cape May are in this dataset *only* because
somebody archived them before those sites started refusing HTTP clients. Every
submission here is a bet that some future county will do the same.

**This needs an archive.org account.** Anonymous submission is no longer
practical: `GET /save/<url>` answers 429 immediately, and the JSON API answers
401. Both were verified against a live URL. Make a free account, take the S3-style
keys from https://archive.org/account/s3.php, and put them in the environment:

    export IA_ACCESS_KEY=...
    export IA_SECRET_KEY=...

Submissions are recorded in `data/archive_submissions.csv` so a re-run picks up
where the last one stopped. Save Page Now is slow and rate-limited even when
authenticated, so this is expected to take several runs.

Usage:
    python -m njfilings.archive --dry-run
    python -m njfilings.archive --limit 50
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .capture import PROJECT_ROOT, USER_AGENT, utc_now

SAVE_URL = "https://web.archive.org/save"
WAYBACK_PREFIX = "https://web.archive.org/web/"

SUBMISSION_FIELDS = ["url", "submitted_at", "outcome", "detail", "job_id"]

# Save Page Now throttles hard and answers 429 when pushed. This is slower than
# it needs to be on a good day and about right on a bad one.
DEFAULT_DELAY = 8.0
DEFAULT_TIMEOUT = 120.0
# how long to wait out a 429 before carrying on with the next URL
BACKOFF = 60.0


def credentials() -> tuple[str, str] | None:
    """The archive.org S3-style keys, if the environment has them."""
    key = os.environ.get("IA_ACCESS_KEY", "").strip()
    secret = os.environ.get("IA_SECRET_KEY", "").strip()
    return (key, secret) if key and secret else None


def original_url(row: dict[str, str]) -> str:
    """The clerk's own URL for a manifest row.

    Rows fetched through the Archive record the Wayback URL — that is what we
    requested — and carry the original in the note. Those are already archived
    by definition, so they are not resubmitted; this returns "" for them.
    """
    url = row.get("url", "")
    if url.startswith(WAYBACK_PREFIX):
        return ""
    return url


def captured_urls(manifest: Path) -> list[str]:
    """Every distinct URL we hold bytes for, in the order first captured.

    `manifest` is the ledger directory; every cycle's shard is read.
    """
    shards = sorted(manifest.glob("*.csv")) if manifest.is_dir() else []
    seen: dict[str, None] = {}
    for shard in shards:
        with shard.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if not row.get("sha256"):
                    continue        # a failed fetch proves nothing worth saving
                url = original_url(row)
                if url:
                    seen.setdefault(url, None)
    return list(seen)


def already_submitted(path: Path) -> set[str]:
    """URLs the Archive has already accepted. Failures are left out so they are
    retried on the next run."""
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as fh:
        return {row["url"] for row in csv.DictReader(fh)
                if row.get("outcome") == "saved"}


def record(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUBMISSION_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in SUBMISSION_FIELDS})


def submit(urls: list[str], root: Path = PROJECT_ROOT,
           delay: float = DEFAULT_DELAY, timeout: float = DEFAULT_TIMEOUT,
           verbose: bool = True,
           transport: httpx.BaseTransport | None = None) -> dict[str, int]:
    """Submit each URL to Save Page Now. Like capture, a single failure is
    recorded and the run continues — the Archive being slow, rate-limiting us,
    or offline entirely are all ordinary weather."""
    out = root / "data" / "archive_submissions.csv"
    counts = {"saved": 0, "failed": 0}
    width = len(str(len(urls)))

    creds = credentials()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if creds:
        headers["Authorization"] = f"LOW {creds[0]}:{creds[1]}"

    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers,
                      transport=transport) as client:
        for i, url in enumerate(urls, 1):
            started = time.monotonic()
            job_id = ""
            try:
                response = client.post(SAVE_URL, data={"url": url})
                status = response.status_code
                if status == 200:
                    try:
                        body = response.json()
                    except ValueError:
                        body = {}
                    job_id = str(body.get("job_id", ""))
                    if job_id:
                        outcome, detail = "saved", ""
                    else:
                        # a 200 with no job is the Archive declining politely
                        outcome = "failed"
                        detail = str(body.get("message", "no job id"))[:80]
                elif status == 429:
                    outcome, detail = "failed", "rate limited"
                elif status == 401:
                    outcome, detail = "failed", "unauthorized - set IA_ACCESS_KEY/IA_SECRET_KEY"
                else:
                    outcome, detail = "failed", f"http {status}"
            except Exception as exc:               # noqa: BLE001
                outcome, detail = "failed", f"{type(exc).__name__}: {exc}"

            counts[outcome] += 1
            record(out, {"url": url, "submitted_at": utc_now(),
                         "outcome": outcome, "detail": detail, "job_id": job_id})
            if verbose:
                print(f"[{i:>{width}}/{len(urls)}] {outcome:<7} {detail:<18} "
                      f"{url[-68:]}", flush=True)

            if detail == "rate limited":
                # pushing harder makes it worse; wait it out once, then carry on
                time.sleep(BACKOFF)
            elif i < len(urls):
                time.sleep(max(0.0, delay - (time.monotonic() - started)))

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m njfilings.archive",
        description="Submit captured URLs to the Internet Archive (plan 2.3).")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="submit at most N this run")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        metavar="SECONDS", help="between submissions (default 8)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        metavar="SECONDS", help="Save Page Now is slow")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be submitted")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)

    if not credentials():
        print("No archive.org credentials. Anonymous Save Page Now is refused "
              "(429 on GET, 401 on the API).\n"
              "Make a free account, take the keys from "
              "https://archive.org/account/s3.php, then:\n"
              "    export IA_ACCESS_KEY=...\n"
              "    export IA_SECRET_KEY=...", file=sys.stderr)
        if not args.dry_run:
            return 1

    manifest = args.root / "data" / "manifest"
    done = already_submitted(args.root / "data" / "archive_submissions.csv")
    pending = [u for u in captured_urls(manifest) if u not in done]

    if not pending:
        print(f"nothing pending — {len(done)} URLs already saved")
        return 0
    if args.limit:
        pending = pending[:args.limit]

    if args.dry_run:
        for url in pending:
            print(url)
        mins = len(pending) * args.delay / 60
        print(f"\n{len(pending)} to submit, {len(done)} already saved "
              f"(~{mins:.0f} min at {args.delay}s apart)")
        return 0

    counts = submit(pending, root=args.root, delay=args.delay,
                    timeout=args.timeout)
    print(f"\n{counts['saved']} saved, {counts['failed']} failed  ->  "
          f"{args.root / 'data' / 'archive_submissions.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
