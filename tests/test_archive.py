"""Submission is a long, flaky, resumable job against a service that rate-limits
us, so what matters is that it picks the right URLs, never loses its place, and
treats every failure as ordinary weather."""

from __future__ import annotations

import csv

import httpx
import pytest

from njfilings import archive


def manifest(tmp_path, rows):
    p = tmp_path / "data" / "manifest.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["url", "sha256", "note"])
        w.writeheader()
        w.writerows(rows)
    return p


def submissions(tmp_path):
    p = tmp_path / "data" / "archive_submissions.csv"
    if not p.exists():
        return []
    with p.open(newline="") as fh:
        return list(csv.DictReader(fh))


def responder(status=200, body=None, log=None):
    def handler(request):
        if log is not None:
            log.append(request)
        return httpx.Response(status, json=body if body is not None else {})
    return httpx.MockTransport(handler)


# --- choosing what to submit -------------------------------------------

def test_wayback_rows_are_not_resubmitted():
    """A document we got *from* the Archive is already in the Archive."""
    wayback = ("https://web.archive.org/web/20260819210457id_/"
               "https://www.morriscountyclerk.org/x.pdf")
    assert archive.original_url({"url": wayback}) == ""
    assert archive.original_url({"url": "https://clerk.example/x.pdf"}) \
        == "https://clerk.example/x.pdf"


def test_only_urls_we_hold_bytes_for_are_submitted(tmp_path):
    """A 404 row proves nothing worth preserving."""
    m = manifest(tmp_path, [
        {"url": "https://a.example/1.pdf", "sha256": "abc", "note": ""},
        {"url": "https://a.example/missing.pdf", "sha256": "", "note": "404"},
    ])
    assert archive.captured_urls(m) == ["https://a.example/1.pdf"]


def test_repeated_captures_submit_once_in_first_seen_order(tmp_path):
    m = manifest(tmp_path, [
        {"url": "https://a.example/1.pdf", "sha256": "abc", "note": ""},
        {"url": "https://a.example/2.pdf", "sha256": "def", "note": ""},
        {"url": "https://a.example/1.pdf", "sha256": "abc", "note": "held"},
    ])
    assert archive.captured_urls(m) == ["https://a.example/1.pdf",
                                        "https://a.example/2.pdf"]


def test_missing_manifest_is_not_an_error(tmp_path):
    assert archive.captured_urls(tmp_path / "nope.csv") == []


# --- resuming ------------------------------------------------------------

def test_only_saved_urls_count_as_done(tmp_path):
    """Failures must come back around on the next run; successes must not."""
    p = tmp_path / "data" / "archive_submissions.csv"
    p.parent.mkdir(parents=True)
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=archive.SUBMISSION_FIELDS)
        w.writeheader()
        w.writerow({"url": "https://a/1", "outcome": "saved", "job_id": "j1"})
        w.writerow({"url": "https://a/2", "outcome": "failed",
                    "detail": "rate limited"})
    assert archive.already_submitted(p) == {"https://a/1"}


# --- submitting ----------------------------------------------------------

def test_a_job_id_means_saved(tmp_path):
    counts = archive.submit(["https://a.example/1.pdf"], root=tmp_path, delay=0,
                            verbose=False,
                            transport=responder(200, {"job_id": "spn2-abc"}))
    assert counts == {"saved": 1, "failed": 0}
    (row,) = submissions(tmp_path)
    assert row["outcome"] == "saved" and row["job_id"] == "spn2-abc"
    assert row["submitted_at"].endswith("+00:00")


def test_200_without_a_job_id_is_a_refusal(tmp_path):
    """The Archive declines politely with a 200 and a message."""
    counts = archive.submit(["https://a.example/1.pdf"], root=tmp_path, delay=0,
                            verbose=False,
                            transport=responder(200, {"message": "host is blocked"}))
    assert counts["failed"] == 1
    (row,) = submissions(tmp_path)
    assert row["outcome"] == "failed" and "blocked" in row["detail"]


def test_401_says_what_to_do_about_it(tmp_path):
    archive.submit(["https://a.example/1.pdf"], root=tmp_path, delay=0,
                   verbose=False, transport=responder(401))
    (row,) = submissions(tmp_path)
    assert "IA_ACCESS_KEY" in row["detail"]


def test_rate_limiting_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "BACKOFF", 0.0)
    counts = archive.submit(["https://a.example/1.pdf"], root=tmp_path, delay=0,
                            verbose=False, transport=responder(429))
    assert counts["failed"] == 1
    assert submissions(tmp_path)[0]["detail"] == "rate limited"


def test_one_failure_does_not_stop_the_run(tmp_path):
    urls = [f"https://a.example/{n}.pdf" for n in range(3)]

    def handler(request):
        if request.url.path == "/save" and b"1.pdf" in request.content:
            raise httpx.ConnectError("dropped")
        return httpx.Response(200, json={"job_id": "j"})

    counts = archive.submit(urls, root=tmp_path, delay=0, verbose=False,
                            transport=httpx.MockTransport(handler))
    assert counts == {"saved": 2, "failed": 1}
    assert len(submissions(tmp_path)) == 3


def test_credentials_become_an_authorization_header(tmp_path, monkeypatch):
    monkeypatch.setenv("IA_ACCESS_KEY", "key123")
    monkeypatch.setenv("IA_SECRET_KEY", "secret456")
    seen = []
    archive.submit(["https://a.example/1.pdf"], root=tmp_path, delay=0,
                   verbose=False,
                   transport=responder(200, {"job_id": "j"}, log=seen))
    assert seen[0].headers["authorization"] == "LOW key123:secret456"


def test_without_credentials_no_authorization_header(tmp_path, monkeypatch):
    monkeypatch.delenv("IA_ACCESS_KEY", raising=False)
    monkeypatch.delenv("IA_SECRET_KEY", raising=False)
    seen = []
    archive.submit(["https://a.example/1.pdf"], root=tmp_path, delay=0,
                   verbose=False,
                   transport=responder(200, {"job_id": "j"}, log=seen))
    assert "authorization" not in seen[0].headers
