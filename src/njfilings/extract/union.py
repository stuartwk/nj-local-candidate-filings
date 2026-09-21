"""Union County's school-board candidate list, 2026.

One municipality per page, and exactly one contest on each:

    TOWNSHIP OF CLARK
    POSITION | CANDIDATE | ADDRESS | SLOGAN | TERM | EMAIL ADDRESS
    1-1
     Steven Donkersloot
    317 Willow Way
    3 Yrs
    sdonkers@comcast.net
    ...
    3 YEAR TERM - VOTE FOR THREE

The contest header sits at the *end* of the page rather than the top, because
it belongs to a different column of the layout. That is harmless here — the page
is the contest — but it is why the seats cannot be read by looking above a
candidate.

Candidates are anchored on the ballot-position cell, which comes in two
spellings: `1-1` (column and place) on most pages and `1E`, `2F` on Hillside.
The column header is `POSITION` on seventeen pages and `POSITIONS` on Fanwood.
Neither variation means anything; both have to be accepted.

A seat nobody filed for prints `NO PETITION FILED` in place of the whole row, so
unfilled seats are observed. The captured document is watermarked
"REFRAIN FROM PUBLISHING LITERATURE UNTIL POSITIONS ARE CONFIRMED SEPTEMBER 1ST"
and dated 8/12/2026 — it is a provisional list, and a later one may exist.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

CONTEST_RE = re.compile(
    r"(?P<years>\d+)\s*YEAR\s*TERM\s*[-–—]?\s*"
    r"(?P<unexpired>UNEXPIRED\s*)?VOTE\s*FOR\s+(?P<seats>[A-Z]+)", re.I)
# `1-1` on most pages, `1E` on Hillside
POSITION_RE = re.compile(r"^\d+\s*(?:-\s*\d+|[A-Z])$")
NO_FILING_RE = re.compile(r"^NO PETITION FILED", re.I)
COLUMN_HEADER = "POSITION"

OFFICE = "School Board Member"


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    import pymupdf

    pages = [page.get_text() for page in pymupdf.open(path)]
    return parse(pages, year=year, source_url=source_url,
                 source_document=source_document, election_type=election_type)


def parse(pages: list[str], year: str, source_url: str, source_document: str,
          election_type: str = "general") -> list[Contest]:
    """One contest per page. A page without a contest header yields nothing."""
    contests = []
    for page_number, page in enumerate(pages, 1):
        lines = [re.sub(r"\s+", " ", l).strip() for l in page.splitlines()]
        lines = [l for l in lines if l]

        header = next((CONTEST_RE.search(l) for l in lines
                       if CONTEST_RE.search(l)), None)
        if header is None:
            continue
        municipality = next(
            (lines[i - 1] for i, l in enumerate(lines)
             if i and l.rstrip("S") == COLUMN_HEADER), None)

        candidates = []
        unfilled = 0
        for index, line in enumerate(lines):
            if NO_FILING_RE.match(line):
                unfilled += 1
            elif POSITION_RE.match(line) and index + 1 < len(lines):
                candidates.append(Candidate(lines[index + 1]))

        contests.append(Contest(
            county="union", year=year, election_type=election_type,
            municipality=municipality, district_name=None, office=OFFICE,
            term_years=int(header.group("years")),
            is_unexpired=bool(header.group("unexpired")),
            seats_available=NUMBER_WORDS.get(header.group("seats").lower()),
            candidates_filed=tuple(candidates),
            seats_unfilled_stated=unfilled,
            source_url=source_url, source_document=source_document,
            source_page=page_number))
    return contests
