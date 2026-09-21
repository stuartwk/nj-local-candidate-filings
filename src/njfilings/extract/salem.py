"""Salem County sample ballots, 2026 — one PDF per municipality.

The project's first ballot, and a different problem from a candidate list. A
ballot is a typeset grid, trilingual in part, with the school election as one
section among the municipal contests:

    OFFICIAL SCHOOL ELECTION
    ELECCIÓN OFICIAL DE LA ESCUELA
    Alloway School Board                  <- the district
    3 Year Term - Vote for Three          <- term and seats
    Junta de Educación / de Alloway       <- the same in Spanish
    Término de 3 Años - Votar por Tres
    Richard C. MORRIS, Jr.                <- a candidate
    NO PETITION FILED                     <- a seat nobody filed for
    NO PETITION FILED
    write-in vote / por escrito           <- one per seat
    Alloway - District 1                  <- footer: the municipality

**Candidates are identified by typography, not by text.** On these ballots a
name is set in bold condensed at 13pt and a slogan in small caps at 7pt, and
nothing else distinguishes them — there is no email to anchor on as there is in
a candidate list. A text rule looking for an all-capital surname seems to work
and then quietly drops `Loretta LaROY`, `Dennis McCARRON` and `Jeanna DuBOIS`,
because those surnames carry a lowercase letter. Font is what the clerk actually
used to mean "this is a person".

**Two municipalities can share a district without sharing a contest.** Penns
Grove and Carneys Point both print `Penns Grove/Carneys Point School Board`,
3-year term, vote for one — but Carneys Point's seat drew two candidates and
Penns Grove's drew nobody. They are separate seats on a shared board, and
merging them would erase an unfilled seat. Salem City's east and west ward
ballots, by contrast, print the identical contest twice. The municipality from
the ballot footer is what tells those cases apart.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

SCHOOL_SECTION_RE = re.compile(r"OFFICIAL SCHOOL ELECTION", re.I)
CONTEST_RE = re.compile(
    r"(?P<years>\d+)\s*Year\s*Term\s*[-–—]\s*Vote for\s+(?P<seats>\w+)"
    r"|(?P<unexpired>Unexpired).*?Vote for\s+(?P<useats>\w+)", re.I)
WRITE_IN_RE = re.compile(r"write-in vote", re.I)
NO_FILING_RE = re.compile(r"^(NO PETITION FILED|NO NOMINATION MADE)$", re.I)
# the Spanish half of the ballot, which restates everything already read
SPANISH_RE = re.compile(r"ELECCIÓN|Junta de|Término|por escrito|^de\s", re.I)
FOOTER_RE = re.compile(r"^(?P<municipality>.+?)\s+-\s+(East|West|North|South)?\s*"
                       r"(Ward\s*\d*\s*-\s*)?District\s+\d+$", re.I)

OFFICE = "School Board Member"

# A name is set in bold condensed type, far larger than a slogan.
NAME_FONT = "BdCn"
NAME_MIN_SIZE = 10.0


def names_by_typography(page) -> set[str]:
    """Every line the ballot sets as a candidate's name."""
    found = set()
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            text = "".join(s["text"] for s in spans).strip()
            if not text or not spans:
                continue
            first = spans[0]
            if NAME_FONT in first["font"] and first["size"] >= NAME_MIN_SIZE:
                found.add(text)
    return found


def municipality_of(lines: list[str]) -> str | None:
    """The ballot names its own municipality in the footer."""
    for line in reversed(lines):
        match = FOOTER_RE.match(line)
        if match:
            return match.group("municipality").strip()
    return None


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    import pymupdf

    document = pymupdf.open(path)
    contests = []
    for page_number, page in enumerate(document, 1):
        lines = [re.sub(r"\s+", " ", l).strip() for l in page.get_text().splitlines()]
        lines = [l for l in lines if l]
        contests += parse_page(lines, names_by_typography(page), year=year,
                               page_number=page_number, source_url=source_url,
                               source_document=source_document,
                               election_type=election_type)
    return contests


def parse_page(lines: list[str], names: set[str], year: str, page_number: int,
               source_url: str, source_document: str,
               election_type: str = "general") -> list[Contest]:
    """The school section of one ballot page.

    `names` is the set of lines the page sets in a candidate's typeface; it is
    passed in so the parse can be tested without a PDF.
    """
    start = next((i for i, l in enumerate(lines)
                  if SCHOOL_SECTION_RE.search(l)), None)
    if start is None:
        return []          # this municipality has no school election in November

    contest_at = next((i for i, l in enumerate(lines[start:], start)
                       if CONTEST_RE.search(l)), None)
    if contest_at is None:
        return []
    match = CONTEST_RE.search(lines[contest_at])
    seats_word = match.group("seats") or match.group("useats") or ""

    district = " ".join(l for l in lines[start + 1:contest_at]
                        if not SPANISH_RE.search(l)) or None

    end = next((i for i, l in enumerate(lines[contest_at:], contest_at)
                if WRITE_IN_RE.search(l)), len(lines))
    body = lines[contest_at + 1:end]

    return [Contest(
        county="salem", year=year, election_type=election_type,
        municipality=municipality_of(lines), district_name=district,
        office=OFFICE,
        term_years=int(match.group("years")) if match.group("years") else None,
        is_unexpired=bool(match.group("unexpired")),
        seats_available=NUMBER_WORDS.get(seats_word.lower()),
        candidates_filed=tuple(Candidate(l) for l in body if l in names),
        seats_unfilled_stated=sum(1 for l in body if NO_FILING_RE.match(l)),
        source_url=source_url, source_document=source_document,
        source_page=page_number)]
