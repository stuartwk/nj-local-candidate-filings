"""Hunterdon County's countywide school-board candidate list, 2023-2026.

The document is a text PDF laid out as an outline:

    DELAWARE VALLEY REGIONAL HIGH SCHOOL          <- district header
    ALEXANDRIA TOWNSHP                            <- municipality header
    School Board Member- 3 Yr. Term - Vote for One    <- contest
    Andrew Sliver 16 Northwood Dr. Pittstown, NJ 08867 andrew@example.com
         Support Public Education                 <- slogan, ignored

Three things about this source make it worth doing first, and one makes it
harder than it looks.

Worth doing: seats are stated on every contest line, unexpired terms are
labelled, and seats nobody filed for are printed outright — so `seats_unfilled`
is observed rather than arithmetic.

Harder than it looks: the punctuation is not consistent in any respect. Across
four documents there are 68 distinct spellings of the contest line, varying in
hyphen (`-`, `–`, `—`), spacing, capitalisation (`Term`/`TERM`), and occasional
duplication (`3 Yr. Term- Term Vote for Two`). Everything here matches loosely
on purpose. The marker for an unfilled seat also changed: `No Nomination Made`
through 2025, `No Petition Filed` in 2026.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# The term and the seat count, allowed to be separated by any amount of the
# clerk's punctuation. Anchored on the two things every spelling does contain:
# "<n> Yr" and "Vote for <word>".
CONTEST_RE = re.compile(
    r"(?P<term>\d+)\s*Yr\.?\s*(?P<kind>Term|Unexpired)\b"
    r".{0,40}?Vote\s*for\s+(?P<seats>[A-Za-z]+)",
    re.IGNORECASE | re.DOTALL)

# Seats nobody filed for. The wording changed in 2026; both are the same fact.
NO_FILING_RE = re.compile(r"No\s+(?:Nomination\s+Made|Petition\s+Filed)", re.I)

WITHDREW_RE = re.compile(r"\bwithdrew\b|\bwithdrawn\b", re.I)
EMAIL_RE = re.compile(r"[\w.\-+']+@[\w.\-]+\.\w+")

# A municipality names itself; a district says it is a district.
MUNICIPALITY_RE = re.compile(
    r"\b(TOWNSHIP|TOWNSHP|TWP|BOROUGH|BORO|TOWN|CITY|VILLAGE)\b", re.I)
DISTRICT_RE = re.compile(r"\b(SCHOOL|DISTRICT|REGIONAL)\b", re.I)
# page furniture and the one structural marker in the document
SECTION_RE = re.compile(
    r"HUNTERDON COUNTY|ANNUAL SCHOOL ELECTION|Poll Hours|LOCAL DISTRICTS"
    r"|^\s*\w+ \d{1,2}, \d{4}", re.I)
# The document has two halves, and they nest differently. See `extract`.
LOCAL_SECTION_RE = re.compile(r"LOCAL DISTRICTS", re.I)

OFFICE = "School Board Member"


def is_heading(line: str) -> bool:
    """A heading is set in capitals. Slogans and names are not."""
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.85


def candidate_name(line: str) -> str:
    """The name is whatever precedes the street number.

    Every candidate line is `Name <number> <street>, <town>, NJ <zip> <email>`,
    and no name in four cycles contains a digit.
    """
    line = WITHDREW_RE.split(line)[0]
    head = re.split(r"\s+\d", line.strip(), maxsplit=1)[0]
    return re.sub(r"\s+", " ", head).strip(" ,-")


def _seats(word: str) -> int | None:
    return NUMBER_WORDS.get(word.lower())


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    """Every contest in one Hunterdon candidate list."""
    import pymupdf

    numbered: list[tuple[int, str]] = []
    for page_number, page in enumerate(pymupdf.open(path), 1):
        for line in page.get_text().splitlines():
            numbered.append((page_number, line.rstrip()))
    return parse(numbered, year=year, source_url=source_url,
                 source_document=source_document, election_type=election_type)


def parse(numbered: list[tuple[int, str]], year: str, source_url: str,
          source_document: str, election_type: str = "general") -> list[Contest]:
    """The whole parser, over `(page number, line)` pairs.

    Split out from `extract` so it can be tested against literal text rather
    than against PDFs, and so a failure is attributable to the parse rather than
    to text extraction.
    """
    contests: list[Contest] = []
    district: str | None = None
    municipality: str | None = None
    # How far a district header reaches. This is the one place the parser
    # carries state across blocks — the exact hazard ground rule 5 warns about —
    # so the scope is drawn as tightly as the document allows.
    #
    # The list has two halves that nest differently. In the regional half, one
    # district header covers every municipality beneath it:
    #
    #     DELAWARE VALLEY REGIONAL HIGH SCHOOL
    #     ALEXANDRIA TOWNSHP        <- Delaware Valley
    #     FRENCHTOWN BOROUGH        <- also Delaware Valley
    #     KINGWOOD TOWNSHIP         <- also Delaware Valley
    #
    # After `HUNTERDON COUNTY- LOCAL DISTRICTS`, each district is listed once
    # and covers exactly one block — either a single municipality, or a contest
    # of its own. Whatever follows is unrelated:
    #
    #     FLEMINGTON-RARITAN REGIONAL SCHOOL DIST.
    #     RARITAN TOWNSHIP          <- Flemington-Raritan
    #     FRANKLIN TOWNSHIP         <- NOT Flemington-Raritan; its own district
    #
    #     CLINTON -GLEN GARDNER SCHOOL DISTRICT
    #     School Board Member - 3 Yr. Term Vote for Two   <- the district's own
    #     CLINTON TOWNSHIP          <- NOT Clinton-Glen Gardner
    #
    # So a district is spent once it has produced a contest, unless we are in
    # the regional half and that contest belonged to a municipality. Reading it
    # any less carefully mislabels Franklin Township and Clinton Township — two
    # towns silently attributed to a district they do not belong to.
    section = "regional"
    district_spent = False
    open_contest: Contest | None = None

    def close() -> None:
        nonlocal open_contest
        if open_contest is not None:
            contests.append(open_contest)
            open_contest = None

    for page_number, raw in numbered:
        line = raw.strip()
        if not line:
            continue

        # Unfilled seats first. 2023 prints `NO NOMINATION MADE` in capitals,
        # which otherwise reads as a heading — and a heading closes the contest
        # it belongs to, so the marker would be dropped and the seat would look
        # filled. Silently, which is the worst way for this to be wrong.
        if NO_FILING_RE.search(line):
            if open_contest is not None:
                open_contest = _add_unfilled(open_contest)
            continue

        match = CONTEST_RE.search(line)
        before = line[:match.start()].strip(" -–—_") if match else ""

        # A heading: district, municipality, or page furniture. It must say
        # which it is — slogans are set in capitals too (`CHILDREN'S EDUCATION
        # MATTERS`), and treating one as a heading would close the contest its
        # remaining candidates belong to.
        if match is None and is_heading(line):
            if SECTION_RE.search(line):
                close()
                if LOCAL_SECTION_RE.search(line):
                    section = "local"
                district = municipality = None
                district_spent = False
            elif DISTRICT_RE.search(line):
                close()
                district, municipality = line, None
                district_spent = False
            elif MUNICIPALITY_RE.search(line):
                close()
                if district_spent:
                    district = None
                municipality = line
            # otherwise it is a slogan in capitals: not data, and not a boundary
            continue

        if match:
            # Two 2024 lines put the municipality and the contest together:
            # `UNION TOWNSHIP- 3 Yr. Term- Vote for One`
            if before and is_heading(before) and MUNICIPALITY_RE.search(before):
                close()
                if district_spent:
                    district = None
                municipality = before
            close()
            seats = _seats(match.group("seats"))
            if section == "local" or municipality is None:
                district_spent = True
            open_contest = Contest(
                county="hunterdon", year=year, election_type=election_type,
                municipality=municipality, district_name=district,
                office=OFFICE, term_years=int(match.group("term")),
                is_unexpired=match.group("kind").lower() == "unexpired",
                seats_available=seats, seats_unfilled_stated=0,
                source_url=source_url, source_document=source_document,
                source_page=page_number)
            continue

        if open_contest is None:
            continue

        if EMAIL_RE.search(line):
            open_contest = _add_candidate(
                open_contest,
                Candidate(candidate_name(line), bool(WITHDREW_RE.search(line))))
        # anything else under a contest is a slogan, and slogans are not data

    close()
    return contests


def _add_candidate(contest: Contest, candidate: Candidate) -> Contest:
    from dataclasses import replace
    return replace(contest,
                   candidates_filed=contest.candidates_filed + (candidate,))


def _add_unfilled(contest: Contest) -> Contest:
    from dataclasses import replace
    return replace(contest,
                   seats_unfilled_stated=(contest.seats_unfilled_stated or 0) + 1)
