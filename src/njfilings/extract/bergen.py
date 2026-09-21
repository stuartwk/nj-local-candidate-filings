"""Bergen County sample ballots, 2023-2025 — one PDF per municipality.

A trilingual InDesign grid (English, Spanish, Korean) with the school elections
in their own column, away from the partisan contests:

    For Membership to the Local Board of Education        <- x ~902
    (FULL THREE YEAR TERM - VOTE FOR THREE)
    Para Afiliación a la Junta de Educación Local         <- the same, twice more
    교육위원

with its candidates set to the right of it. Candidates normally sit slightly
*above* their own heading — Demarest's regional candidates are at y=317 under a
heading at y=318 — because the heading is centred against a single row of names.
Where a contest draws enough candidates to need several rows, the heading
centres among them instead and names appear on both sides, as Hackensack's do.
Nearest-heading-by-height covers both; a rule assuming one side does not.

The vertical limit matters as much as the column does. Carlstadt prints its
school contests low on the page at x=497, where a municipal candidate three
hundred points above is still to the right of the heading and would otherwise be
claimed by it.

NOT FINISHED — deliberately not registered in `build.EXTRACTORS`.
--------------------------------------------------------------
About 3% of contests come out internally inconsistent, and `Contest.problems()`
catches each one: 4 of 89 in 2023, 3 of 102 in 2024, 3 of 88 in 2025. Two causes,
and one of them is not this parser's fault.

**The heading moves between eras.** In 2025 a candidate sits a few points
*above* its heading (Alpine: names at y=309 and 317, heading at 318). In 2023 it
sits *below* (Hillsdale: heading at 576, names at 590 and 631). Nearest-by-height
therefore splits Hillsdale's two contests in the wrong place, giving one of them
a single candidate for two seats and the other four. Each year needs its own
offset, measured rather than guessed, and 2024 has not been measured at all.

**Three of the 2024 documents are contaminated at source.** `carlstadt.pdf`,
`east-rutherford.pdf` and `elmwood-park.pdf` each carry Allendale's ballot
layered underneath their own — two municipalities' footers, and names drawn at
identical coordinates (`McCARTHY` and `LAHULLIER` both at x=206, y=906). Those
three are exactly the three municipalities that report inconsistent contests in
2024. Allendale's candidates would be counted in another town's totals, which
corrupts the county's sums and not merely the attribution within it.

Worth knowing about the first cause: misplacing a candidate between two contests
of the *same* municipality does not move candidates-per-seat, which is a ratio of
two sums over the county. It does move the uncontested rate and the unfilled
count. The contaminated files move everything.

Names, as ever, are known by their typeface: `UniversLTStd-BoldCn` at 12pt for a
surname, `UniversLTStd-Cn` at 8.5pt for the given name above it, and a slogan
smaller still. Bergen and Burlington share this typesetter.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest
from .ballot import Item, items_of

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

HEADER_RE = re.compile(
    r"For Membership to the (?P<scope>Local|Regional) Board of Education", re.I)
TERM_RE = re.compile(
    r"\((?P<kind>FULL|UNEXPIRED)[^)]*?(?:(?P<years>\w+)\s+YEAR)[^)]*?"
    r"VOTE FOR\s+(?P<seats>\w+)\)", re.I)
NO_FILING_RE = re.compile(r"^(NO PETITION FILED|NO NOMINATION MADE)$", re.I)
# Column headings and section labels are set in the same bold condensed face as
# a surname, only smaller — and "smaller" moves between years (a name is 14.3pt
# in 2023, 12.9 in 2024, 12.0 in 2025), so a size threshold does not travel.
# They are excluded by what they say instead.
FURNITURE_RE = re.compile(
    r"^(SCHOOL ELECTION|PERSONAL CHOICE|GENERAL ELECTION|SELECCIÓN|ELECCIÓN"
    r"|WRITE.?IN|COLUMN|NOMINATION BY|CANDIDATO|PUBLIC QUESTION)", re.I)
# `Form 2 - Alpine - D1` in 2024-25, `Form 2 - ALPINE` in 2023
FOOTER_RE = re.compile(
    r"^Form\s+\d+\s*-\s*(?P<municipality>.+?)(?:\s*-\s*D\d+)?$", re.I)

SURNAME_FONT = "UniversLTStd-BoldCn"
GIVEN_FONT = "UniversLTStd-Cn"
SURNAME_MIN = 11.0
GIVEN_SIZE = 8.5
# how far above or below its heading a name may sit and still belong to it
REACH = 120.0

OFFICE = "Member of the Board of Education"


def municipality_of(items: list[Item]) -> str | None:
    for item in items:
        match = FOOTER_RE.match(item.text.strip())
        if match:
            return match.group("municipality").strip()
    return None


def _years(word: str | None) -> int | None:
    """`THREE` or `2`, depending on the wording of the term."""
    if not word:
        return None
    if word.isdigit():
        return int(word)
    return NUMBER_WORDS.get(word.lower())


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    import pymupdf

    contests = []
    for page_number, page in enumerate(pymupdf.open(path), 1):
        contests += parse_page(items_of(page), year=year,
                               page_number=page_number, source_url=source_url,
                               source_document=source_document,
                               election_type=election_type)
    return contests


def parse_page(items: list[Item], year: str, page_number: int, source_url: str,
               source_document: str,
               election_type: str = "general") -> list[Contest]:
    municipality = municipality_of(items)

    headings = []
    for item in items:
        match = HEADER_RE.search(item.text)
        if not match:
            continue
        term = next((i for i in items
                     if TERM_RE.search(i.text) and 0 <= i.y - item.y <= 20
                     and abs(i.x - item.x) <= 40), None)
        if term is None:
            continue
        headings.append((item, term, match.group("scope")))
    if not headings:
        return []

    def owner(thing: Item):
        """The nearest school heading, above or below, in this column."""
        near = [h for h in headings
                if h[0].x < thing.x and abs(h[0].y - thing.y) <= REACH]
        return min(near, key=lambda h: abs(h[0].y - thing.y)) if near else None

    names: dict[int, list[Item]] = {}
    unfilled: dict[int, int] = {}
    for item in items:
        text = item.text.strip()
        marker = bool(NO_FILING_RE.match(text))
        # An unfilled-seat marker is set in the surname's face but smaller than
        # a name — 10.2pt against 12.9 in 2024, 9.4 against 12.0 in 2025 — so it
        # has to be recognised before the size gate, or every marker is missed
        # and every empty seat silently looks filled.
        if not marker and not item.is_(SURNAME_FONT, SURNAME_MIN):
            continue
        if marker and SURNAME_FONT not in item.font:
            continue
        if FURNITURE_RE.match(text):
            continue
        found = owner(item)
        if found is None:
            continue
        if marker:
            unfilled[id(found[0])] = unfilled.get(id(found[0]), 0) + 1
        else:
            names.setdefault(id(found[0]), []).append(item)

    contests = []
    for heading, term, scope in headings:
        match = TERM_RE.search(term.text)
        people = []
        for item in names.get(id(heading), []):
            given = [i for i in items
                     if i.is_(GIVEN_FONT) and abs(i.size - GIVEN_SIZE) < 1.0
                     and 0 < item.y - i.y <= 14 and abs(i.x - item.x) <= 40]
            first = max(given, key=lambda i: i.y).text if given else ""
            people.append(Candidate(
                re.sub(r"\s+", " ", f"{first} {item.text}").strip()))
        contests.append(Contest(
            county="bergen", year=year, election_type=election_type,
            municipality=municipality,
            district_name=f"{scope.title()} Board of Education",
            office=OFFICE,
            term_years=_years(match.group("years")),
            is_unexpired=match.group("kind").upper() == "UNEXPIRED",
            seats_available=NUMBER_WORDS.get(match.group("seats").lower()),
            candidates_filed=tuple(people),
            seats_unfilled_stated=unfilled.get(id(heading), 0),
            source_url=source_url, source_document=source_document,
            source_page=page_number))
    return contests
