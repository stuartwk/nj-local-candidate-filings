"""Capture is a ledger with a downloader attached, and the ledger is the part
worth testing: what gets written, what gets skipped, and — above all — that a
single bad document never stops a run. Every test here drives the real loop
through a mock transport; none touches the network.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from njfilings.capture import (MANIFEST_FIELDS, Counts, capture,
                               import_file, sha256_bytes)
from njfilings.sources import Document

PDF = b"%PDF-1.4 pretend this is a ballot\n%%EOF\n"


def doc(name: str = "a.pdf", url: str = "https://clerk.example/a.pdf",
        county: str = "testshire", year: str = "2026") -> Document:
    return Document(county, year, "sample_ballot", url, name)


def responder(status: int = 200, body: bytes = PDF,
              content_type: str = "application/pdf", log: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(str(request.url))
        return httpx.Response(status, content=body,
                              headers={"content-type": content_type})
    return httpx.MockTransport(handler)


def manifest_rows(root: Path) -> list[dict[str, str]]:
    directory = root / "data" / "manifest"
    rows = []
    for path in sorted(directory.glob("*.csv")) if directory.is_dir() else []:
        with path.open(newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def run(docs, root, **kw) -> Counts:
    kw.setdefault("delay", 0.0)
    kw.setdefault("verbose", False)
    kw.setdefault("transport", responder())
    return capture(docs, root=root, **kw)


# --- the happy path ------------------------------------------------------

def test_fetch_writes_bytes_and_one_manifest_row(tmp_path):
    counts = run([doc()], tmp_path)

    assert (counts.fetched, counts.skipped, counts.failed) == (1, 0, 0)
    cached = tmp_path / "cache" / "testshire" / "2026" / "a.pdf"
    assert cached.read_bytes() == PDF

    (row,) = manifest_rows(tmp_path)
    assert row["url"] == "https://clerk.example/a.pdf"
    assert row["local_path"] == "cache/testshire/2026/a.pdf"
    assert row["http_status"] == "200"
    assert row["content_type"] == "application/pdf"
    assert row["bytes"] == str(len(PDF))
    assert row["county"] == "testshire" and row["year"] == "2026"
    assert row["doc_type"] == "sample_ballot"


def test_recorded_sha256_is_the_hash_of_the_bytes_on_disk(tmp_path):
    import hashlib
    run([doc()], tmp_path)
    (row,) = manifest_rows(tmp_path)
    on_disk = (tmp_path / row["local_path"]).read_bytes()
    assert row["sha256"] == hashlib.sha256(on_disk).hexdigest()


def test_fetched_at_is_utc_iso8601(tmp_path):
    run([doc()], tmp_path)
    (row,) = manifest_rows(tmp_path)
    stamp = datetime.fromisoformat(row["fetched_at"])
    assert stamp.tzinfo is not None
    assert stamp.utcoffset() == timezone.utc.utcoffset(None)


def test_manifest_columns_are_stable_and_header_written_once(tmp_path):
    run([doc()], tmp_path)
    run([doc("b.pdf", "https://clerk.example/b.pdf")], tmp_path)
    text = (tmp_path / "data" / "manifest" / "2026.csv").read_text()
    assert text.splitlines()[0] == ",".join(MANIFEST_FIELDS)
    assert text.count("url,sha256") == 1
    assert len(manifest_rows(tmp_path)) == 2


def test_no_partial_file_is_left_behind(tmp_path):
    run([doc()], tmp_path)
    assert list(tmp_path.rglob("*.part")) == []


# --- failure is data -----------------------------------------------------

def test_http_error_is_recorded_and_caches_nothing(tmp_path):
    counts = run([doc()], tmp_path,
                 transport=responder(404, b"<html>not found</html>", "text/html"))

    assert (counts.fetched, counts.failed) == (0, 1)
    assert not (tmp_path / "cache").exists()

    (row,) = manifest_rows(tmp_path)
    assert row["http_status"] == "404"
    assert row["sha256"] == "" and row["local_path"] == "" and row["bytes"] == ""


def test_transport_error_is_recorded_without_raising(tmp_path):
    def handler(request):
        raise httpx.ConnectError("name does not resolve")

    counts = run([doc()], tmp_path, transport=httpx.MockTransport(handler))

    assert counts.failed == 1
    (row,) = manifest_rows(tmp_path)
    assert row["http_status"] == ""
    assert "ConnectError" in row["note"]


def test_a_url_that_keeps_failing_the_same_way_adds_one_row(tmp_path):
    """Several of these URLs are permanently dead and get asked on every run.
    The first 404 is news; the twentieth is not."""
    for _ in range(5):
        run([doc()], tmp_path, transport=responder(404, b"", "text/html"))

    rows = manifest_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["http_status"] == "404"


def test_a_changed_failure_status_is_recorded(tmp_path):
    run([doc()], tmp_path, transport=responder(404, b"", "text/html"))
    run([doc()], tmp_path, transport=responder(500, b"", "text/html"))
    run([doc()], tmp_path, transport=responder(500, b"", "text/html"))

    assert [r["http_status"] for r in manifest_rows(tmp_path)] == ["404", "500"]


def test_a_document_that_stops_working_is_recorded(tmp_path):
    """success -> failure is the most important change of all: it means the
    clerk pulled the document and the cached copy is now the only one."""
    run([doc()], tmp_path, transport=responder())
    run([doc()], tmp_path, refetch=True,
        transport=responder(404, b"", "text/html"))

    rows = manifest_rows(tmp_path)
    assert [r["http_status"] for r in rows] == ["200", "404"]


def test_a_repeated_transport_error_adds_one_row(tmp_path):
    def handler(request):
        raise httpx.ConnectError("name does not resolve")

    for _ in range(3):
        run([doc()], tmp_path, transport=httpx.MockTransport(handler))

    rows = manifest_rows(tmp_path)
    assert len(rows) == 1
    assert "ConnectError" in rows[0]["note"]


def test_a_transport_error_after_an_http_error_is_recorded(tmp_path):
    run([doc()], tmp_path, transport=responder(404, b"", "text/html"))

    def handler(request):
        raise httpx.ReadTimeout("too slow")

    run([doc()], tmp_path, transport=httpx.MockTransport(handler))
    rows = manifest_rows(tmp_path)
    assert len(rows) == 2
    assert "ReadTimeout" in rows[1]["note"]


def test_one_failure_does_not_stop_the_run(tmp_path):
    """The whole reason capture exists in this shape: a dead URL in the middle
    of a 200-document Bergen run must not cost the other 199."""
    bad = "https://clerk.example/missing.pdf"

    def handler(request):
        if str(request.url) == bad:
            raise httpx.ReadTimeout("too slow")
        return httpx.Response(200, content=PDF,
                              headers={"content-type": "application/pdf"})

    docs = [doc("first.pdf", "https://clerk.example/first.pdf"),
            doc("missing.pdf", bad),
            doc("last.pdf", "https://clerk.example/last.pdf")]
    counts = run(docs, tmp_path, transport=httpx.MockTransport(handler))

    assert (counts.fetched, counts.failed) == (2, 1)
    assert (tmp_path / "cache/testshire/2026/last.pdf").exists()
    assert len(manifest_rows(tmp_path)) == 3


# --- holding what we already have ---------------------------------------

def test_an_unchanged_document_makes_no_request_and_adds_no_row(tmp_path):
    """The ledger records changes, not heartbeats: re-running over a document
    nothing has happened to must leave the manifest exactly as it was, or a
    daily scheduled capture buries every real event in no-ops."""
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(log=seen))
    before = manifest_rows(tmp_path)
    assert len(before) == 1

    counts = run([doc()], tmp_path, transport=responder(log=seen))

    assert len(seen) == 1                       # no second request
    assert (counts.fetched, counts.skipped) == (0, 1)
    assert manifest_rows(tmp_path) == before    # and no second row


def test_many_quiet_runs_stay_quiet(tmp_path):
    seen: list[str] = []
    for _ in range(10):
        run([doc()], tmp_path, transport=responder(log=seen))
    assert len(seen) == 1
    assert len(manifest_rows(tmp_path)) == 1


def test_recovery_after_a_failure_is_recorded(tmp_path):
    """A document we hold, whose last recorded outcome was a failure, is a
    state change — that one does earn a row."""
    run([doc()], tmp_path, transport=responder())
    run([doc()], tmp_path, refetch=True,
        transport=responder(503, b"", "text/html"))
    assert [r["http_status"] for r in manifest_rows(tmp_path)] == ["200", "503"]

    counts = run([doc()], tmp_path, transport=responder())

    rows = manifest_rows(tmp_path)
    assert counts.skipped == 1
    assert len(rows) == 3
    assert rows[2]["http_status"] == ""         # nothing was asked of the server
    assert rows[2]["sha256"] == rows[0]["sha256"]
    assert "held" in rows[2]["note"]


def test_changed_local_file_is_fetched_again(tmp_path):
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(log=seen))
    (tmp_path / "cache/testshire/2026/a.pdf").write_bytes(b"corrupted")

    run([doc()], tmp_path, transport=responder(log=seen))

    assert len(seen) == 2
    assert (tmp_path / "cache/testshire/2026/a.pdf").read_bytes() == PDF


def test_deleted_local_file_is_fetched_again(tmp_path):
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(log=seen))
    (tmp_path / "cache/testshire/2026/a.pdf").unlink()

    run([doc()], tmp_path, transport=responder(log=seen))
    assert len(seen) == 2


def test_refetch_ignores_what_we_hold(tmp_path):
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(log=seen))

    counts = run([doc()], tmp_path, refetch=True, transport=responder(log=seen))

    assert len(seen) == 2
    assert counts.fetched == 1


def test_a_failed_fetch_leaves_nothing_to_hold(tmp_path):
    """A 404 row must never satisfy the skip check on the next run."""
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(404, b"", "text/html", log=seen))
    run([doc()], tmp_path, transport=responder(log=seen))
    assert len(seen) == 2


# --- pacing --------------------------------------------------------------

def test_requests_to_one_host_are_paced(tmp_path):
    docs = [doc("a.pdf", "https://clerk.example/a.pdf"),
            doc("b.pdf", "https://clerk.example/b.pdf")]
    start = time.monotonic()
    run(docs, tmp_path, delay=0.5)
    assert time.monotonic() - start >= 0.45


def test_separate_hosts_do_not_wait_on_each_other(tmp_path):
    docs = [doc("a.pdf", "https://one.example/a.pdf"),
            doc("b.pdf", "https://two.example/b.pdf")]
    start = time.monotonic()
    run(docs, tmp_path, delay=0.5)
    assert time.monotonic() - start < 0.4


# --- capture stays out of the documents ---------------------------------

def test_capture_never_opens_what_it_saves(tmp_path):
    """Bytes land exactly as served, even when they are not a PDF at all."""
    junk = b"\x00\x01 this is not a PDF and capture must not care"
    run([doc()], tmp_path, transport=responder(body=junk))
    assert (tmp_path / "cache/testshire/2026/a.pdf").read_bytes() == junk


# --- documents a human had to fetch -------------------------------------

def test_import_caches_the_bytes_and_records_where_they_came_from(tmp_path):
    src = tmp_path / "downloaded.pdf"
    src.write_bytes(PDF)
    d = Document("monmouth", "2026", "candidate_list",
                 "https://clerk.example/boe.pdf", "school-board-candidates.pdf")

    digest = import_file(src, d, root=tmp_path, verbose=False)

    cached = tmp_path / "cache/monmouth/2026/school-board-candidates.pdf"
    assert cached.read_bytes() == PDF
    assert digest == sha256_bytes(PDF)

    (row,) = manifest_rows(tmp_path)
    assert row["url"] == "https://clerk.example/boe.pdf"   # where it came from
    assert row["http_status"] == ""                        # we never asked
    assert row["note"] == "manually downloaded"            # and we say so
    assert row["sha256"] == digest
    assert row["bytes"] == str(len(PDF))


def test_an_imported_document_counts_as_held(tmp_path):
    """Having been hand-downloaded does not make it less ours: a later run must
    not try to re-fetch what is already on disk."""
    src = tmp_path / "downloaded.pdf"
    src.write_bytes(PDF)
    d = Document("monmouth", "2026", "candidate_list",
                 "https://clerk.example/boe.pdf", "school-board-candidates.pdf")
    import_file(src, d, root=tmp_path, verbose=False)

    seen: list[str] = []
    counts = capture([d], root=tmp_path, delay=0, verbose=False,
                     transport=responder(log=seen))

    assert seen == []                     # no request went out
    assert counts.skipped == 1
    assert len(manifest_rows(tmp_path)) == 1   # and no heartbeat row


# --- the mode a scheduled run needs ---------------------------------------

def test_new_only_trusts_the_ledger_and_asks_for_nothing_it_records(tmp_path):
    """A scheduled run starts on a fresh machine with no cache at all. The
    ordinary rule checks the disk, finds nothing, and re-downloads the whole
    corpus from county servers every night."""
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(log=seen))
    assert len(seen) == 1

    # the cache is gone, as it would be on a new runner
    (tmp_path / "cache/testshire/2026/a.pdf").unlink()

    counts = capture([doc()], root=tmp_path, delay=0, verbose=False,
                     new_only=True, transport=responder(log=seen))

    assert len(seen) == 1              # nothing re-requested
    assert counts.skipped == 1


def test_new_only_still_fetches_what_the_ledger_has_never_seen(tmp_path):
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(log=seen))
    fresh = doc("new.pdf", "https://clerk.example/new.pdf")

    counts = capture([doc(), fresh], root=tmp_path, delay=0, verbose=False,
                     new_only=True, transport=responder(log=seen))

    assert seen[-1] == "https://clerk.example/new.pdf"
    assert (counts.fetched, counts.skipped) == (1, 1)


def test_new_only_retries_a_url_that_only_ever_failed(tmp_path):
    """A 404 leaves no sha256, so the document is still unseen and a later run
    must try again — that is how a document posted late gets caught."""
    seen: list[str] = []
    run([doc()], tmp_path, transport=responder(404, b"", "text/html", log=seen))

    capture([doc()], root=tmp_path, delay=0, verbose=False, new_only=True,
            transport=responder(log=seen))
    assert len(seen) == 2


def test_the_ledger_is_split_by_election_cycle(tmp_path):
    """One file per cycle, so a cycle's provenance stays readable once this
    runs nightly across 21 counties."""
    run([doc(year="2025"), doc("b.pdf", "https://clerk.example/b.pdf",
                               year="2026")], tmp_path)
    shards = sorted(p.name for p in (tmp_path / "data" / "manifest").glob("*.csv"))
    assert shards == ["2025.csv", "2026.csv"]


def test_every_shard_is_read_back(tmp_path):
    run([doc(year="2025")], tmp_path)
    run([doc("b.pdf", "https://clerk.example/b.pdf", year="2026")], tmp_path)
    assert len(manifest_rows(tmp_path)) == 2
    # and a document recorded in an older shard is still known
    seen: list[str] = []
    capture([doc(year="2025")], root=tmp_path, delay=0, verbose=False,
            new_only=True, transport=responder(log=seen))
    assert seen == []


# --- noticing a county that has stopped working ---------------------------

def test_a_document_that_used_to_work_and_stopped_is_reported(tmp_path):
    """The failure a schedule exists to catch. Capture treats a 404 as data and
    carries on, which is right for one document and wrong for a whole county."""
    from njfilings.capture import Manifest, regressions
    run([doc()], tmp_path, transport=responder())
    run([doc()], tmp_path, refetch=True,
        transport=responder(404, b"", "text/html"))

    found = regressions(Manifest(tmp_path / "data" / "manifest"))
    assert [(c, u) for c, u, _ in found] == [
        ("testshire", "https://clerk.example/a.pdf")]


def test_a_document_that_never_worked_is_not_a_regression(tmp_path):
    """Essex's dead URLs have never returned anything. That is a known gap, and
    reporting it nightly would train everyone to ignore the report."""
    from njfilings.capture import Manifest, regressions
    run([doc()], tmp_path, transport=responder(404, b"", "text/html"))
    assert regressions(Manifest(tmp_path / "data" / "manifest")) == []


def test_a_document_that_recovered_is_not_a_regression(tmp_path):
    from njfilings.capture import Manifest, regressions
    run([doc()], tmp_path, transport=responder(404, b"", "text/html"))
    run([doc()], tmp_path, transport=responder())
    assert regressions(Manifest(tmp_path / "data" / "manifest")) == []


def test_a_transport_failure_counts_as_a_regression(tmp_path):
    from njfilings.capture import Manifest, regressions
    run([doc()], tmp_path, transport=responder())

    def handler(request):
        raise httpx.ConnectError("dropped")

    capture([doc()], root=tmp_path, delay=0, verbose=False, refetch=True,
            transport=httpx.MockTransport(handler))
    (found,) = regressions(Manifest(tmp_path / "data" / "manifest"))
    assert "ConnectError" in found[2]
