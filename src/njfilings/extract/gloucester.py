"""Gloucester County's mail-in ballots, 2026 — one PDF per voting district.

229 documents, the finest granularity of any county here, and the easiest ballot
to read. The school election has a page to itself and its contests come out in
reading order, so unlike Burlington there is no need to reconstruct the grid:

    Harrison Twp - Dist 1                    <- the municipality
    MEMBERSHIP TO / BOARD OF EDUCATION
    FULL TERM THREE (3) YEARS
    VOTE FOR ONE
    SEAN / HENDERSON                         <- given name, then surname
    WRITE-IN (And Fill In Oval)
    CLEARVIEW REGIONAL HIGH SCHOOL DISTRICT  <- the district, AFTER its contests

The district is printed *below* the contests it governs, not above, and one page
can carry two districts — a regional board and the town's own. So contests are
collected and then labelled when their district arrives, rather than inheriting
one from above.

These pages are rotated, so position order runs backwards through the ballot
and cannot be used for structure. `get_text()` gives the reading order the
layout intends, so the parse follows that and looks up each line's typeface
separately.

Typography again does the work a text rule cannot: a surname is set in
`UniversLTStd-Cn` at 12pt and a slogan in `ArialNarrow,Bold` at 8pt, and both
are upper case. The district labels are `ArialBlack` at 11pt, which is what
distinguishes the one that closes a section from the list of districts in the
page's masthead.

229 ballots describe far fewer contests: every district of a municipality
carries the same ones, so most of these collapse in `build.merge_duplicates`.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

BOARD_RE = re.compile(r"^BOARD OF EDUCATION$", re.I)
TERM_RE = re.compile(
    r"^(?P<kind>FULL|UNEXPIRED)\s+TERM\s+\w+\s*\((?P<years>\d+)\)\s*YEARS?$",
    re.I)
SEATS_RE = re.compile(r"^VOTE FOR\s+(?P<seats>\w+)$", re.I)
NO_FILING_RE = re.compile(r"^(NO PETITION FILED|NO NOMINATION MADE)$", re.I)
# `Harrison Twp - Dist 1`, `West Deptford Twp - Dist 2`
BALLOT_ID_RE = re.compile(r"^(?P<municipality>.+?)\s+-\s+Dist\s+\d+$", re.I)
DISTRICT_TEXT_RE = re.compile(r"SCHOOL DISTRICT", re.I)

SURNAME_FONT = "UniversLTStd-Cn"
SURNAME_MIN = 11.0
DISTRICT_FONT = "ArialBlack"

OFFICE = "Membership to Board of Education"


def lines_with_fonts(page) -> list[tuple[str, str, float]]:
    """Every line in reading order, with the typeface it is set in.

    The two are read separately on purpose: `get_text()` knows the order the
    ballot intends, which position order does not on a rotated page, while only
    the span data knows a surname from a slogan.
    """
    faces: dict[str, tuple[str, float]] = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            text = "".join(s["text"] for s in spans).strip()
            if not text or not spans:
                continue
            face = (spans[0]["font"], spans[0]["size"])
            # where a line repeats, the larger setting wins: a name is never
            # smaller than the boilerplate that happens to share its words
            if text not in faces or face[1] > faces[text][1]:
                faces[text] = face
    out = []
    for raw in page.get_text().splitlines():
        text = raw.strip()
        if not text:
            continue
        font, size = faces.get(text, ("", 0.0))
        out.append((text, font, size))
    return out


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    import pymupdf

    for page_number, page in enumerate(pymupdf.open(path), 1):
        if "BOARD OF EDUCATION" not in page.get_text().upper():
            continue
        found = parse_page(lines_with_fonts(page), year=year,
                           page_number=page_number, source_url=source_url,
                           source_document=source_document,
                           election_type=election_type)
        if found:
            return found
    return []


def parse_page(lines: list[tuple[str, str, float]], year: str, page_number: int,
               source_url: str, source_document: str,
               election_type: str = "general") -> list[Contest]:
    """The school contests on one ballot's school page."""
    municipality = None
    for text, _, _ in lines:
        match = BALLOT_ID_RE.match(text)
        if match:
            municipality = match.group("municipality").strip()
            break

    contests: list[Contest] = []
    pending: list[int] = []          # contests still waiting for their district
    current: dict | None = None
    previous = ""

    def close() -> None:
        nonlocal current
        if current is None:
            return
        pending.append(len(contests))
        contests.append(Contest(
            county="gloucester", year=year, election_type=election_type,
            municipality=municipality, district_name=None, office=OFFICE,
            term_years=current["years"], is_unexpired=current["unexpired"],
            seats_available=current["seats"],
            candidates_filed=tuple(current["names"]),
            seats_unfilled_stated=current["unfilled"],
            source_url=source_url, source_document=source_document,
            source_page=page_number))
        current = None

    for text, font, size in lines:
        if BOARD_RE.match(text):
            close()
            current = {"years": None, "unexpired": False, "seats": None,
                       "names": [], "unfilled": 0}
        elif current is not None and TERM_RE.match(text):
            term = TERM_RE.match(text)
            current["years"] = int(term.group("years"))
            current["unexpired"] = term.group("kind").upper() == "UNEXPIRED"
        elif current is not None and SEATS_RE.match(text):
            current["seats"] = NUMBER_WORDS.get(
                SEATS_RE.match(text).group("seats").lower())
        elif current is not None and NO_FILING_RE.match(text):
            current["unfilled"] += 1
        elif current is not None and SURNAME_FONT in font and size >= SURNAME_MIN:
            given = "" if NO_FILING_RE.match(previous) else previous
            current["names"].append(
                Candidate(re.sub(r"\s+", " ", f"{given} {text}").strip()))
        elif DISTRICT_FONT in font and DISTRICT_TEXT_RE.search(text):
            # a district is printed below the contests it governs
            close()
            from dataclasses import replace
            for index in pending:
                contests[index] = replace(contests[index], district_name=text)
            pending.clear()
        previous = text

    close()
    return contests
