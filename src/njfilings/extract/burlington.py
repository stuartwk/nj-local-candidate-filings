"""Burlington County's countywide sample ballot, 2025-2026.

One PDF for the county, one page per municipality-district, ~44 pages. School
elections appear under `LOCAL SCHOOL DISTRICT` and `REGIONAL SCHOOL DISTRICT`
among the county and municipal contests.

A contest is three stacked lines at the left of its row band:

    Township of Bass River School District      <- the district
    Members of the / Board of Education         <- the office
    Full Term  (Vote for Three)                 <- term and seats

with its candidates running rightwards. Some pages stack contests down the page;
the bilingual ones put three side by side in a single band, their candidates
interleaved in the extracted text with nothing to say which belongs to which.
Position is the only thing that separates them, so this reads geometry through
`ballot.py` rather than lines in order.

Every contest on the page has to be found, not only the school ones. A name to
the right of a fire district's heading is not a school board candidate, and
leaving that heading out would hand its candidates to whichever school contest
sat further left.

NOT FINISHED — deliberately not registered in `build.EXTRACTORS`.
--------------------------------------------------------------
Contests are found correctly and most candidates land in the right one, but
about a fifth do not, and `Contest.problems()` catches them: 12 of 66 contests
in 2026 report a stated unfilled count that contradicts their own arithmetic.
The cause is that a contest's heading is not in a consistent place within its
cell:

  * a multi-seat contest stacks its candidates in rows, and its heading is set
    vertically *centred* among them — Burlington's county commissioners have two
    candidates above the heading and two below;
  * a contest whose candidates run down a single column has its heading at the
    *top* — Springfield's school board has four candidates below it and none
    above.

No single rule based on vertical distance satisfies both. Nearest-by-heading
files Springfield's last two candidates under the unexpired-term contest
beneath it; banding from each heading down to the next loses the commissioners'
first row. A tolerance wide enough for one is too wide for the other, and they
were measured to overlap: 18pt is needed above, 13pt is too much below.

The cell rectangles would settle it, but this PDF does not draw them. Its
drawing objects are column strips, not contest cells — which is still useful,
since the strips containing `Ofﬁ ce Title` identify each section's heading
column and so separate the three school contests printed side by side on the
bilingual pages.

Until that is resolved, wiring this in would publish wrong candidate counts for
roughly a fifth of Burlington's contests.

Terms come in four forms — `Full Term`, `Unexpired Term`, `Unexpired 1 Year
Term`, `Unexpired 2 Year Term` — and only two state a length. An unexpired term
of unstated length is recorded as unexpired with `term_years` empty, not assumed
to be one year.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest
from .ballot import (Block, Item, full_name, items_of, nearest_above,
                     nearest_below, owner_of)

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

BOARD_RE = re.compile(r"^Board of Education$", re.I)
TERM_RE = re.compile(
    r"(?P<kind>Full|Unexpired)(?:\s+(?P<years>\d+)\s*Year)?\s*Term"
    r"\s*\(Vote for\s+(?P<seats>\w+)\)", re.I)
NO_FILING_RE = re.compile(r"^No Petition Filed$", re.I)
# `Bass River D1 - Form 1`, `Chesterfield D1 - Form 9`
FOOTER_RE = re.compile(r"^(?P<municipality>.+?)\s+D\d+\s*-\s*Form\s*\d+$", re.I)
# a district names itself as one; the `Members of the` line above it does not
DISTRICT_RE = re.compile(r"School District|Regional", re.I)

HEADER_FONT = "HelveticaLTStd-Bold"
SURNAME_FONT = "UniversLTStd-BoldCn"
GIVEN_FONT = "UniversLTStd-Cn"
SURNAME_MIN = 12.0
GIVEN_SIZE = 9.5

OFFICE = "Member of the Board of Education"


def municipality_of(items: list[Item]) -> str | None:
    """The ballot names its own municipality in the footer."""
    for item in items:
        match = FOOTER_RE.match(item.text)
        if match:
            return match.group("municipality").strip()
    return None


def _district_for(items: list[Item], board: Item) -> Item | None:
    """The district named above a `Board of Education` line."""
    above = nearest_above(items, board, HEADER_FONT, within=26.0)
    if above is not None and not DISTRICT_RE.search(above.text):
        # the line directly above is `Members of the`; the district is above it
        above = nearest_above(items, above, HEADER_FONT, within=26.0)
    return above


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


def _heading_lines(items: list[Item], term: Item) -> list[Item]:
    """The heading lines belonging to one contest.

    A contest's term line has its district, office and sometimes a `Members of
    the` above it, all in the same column. They are one heading, and taking each
    as a separate contest is what first put Bass River's only candidate under
    the district line instead of under the board.
    """
    return [i for i in items
            if i.is_(HEADER_FONT) and 0 < term.y - i.y <= 30
            and abs(i.x - term.x) <= 60]


def parse_page(items: list[Item], year: str, page_number: int, source_url: str,
               source_document: str,
               election_type: str = "general") -> list[Contest]:
    """Every school contest on one ballot page."""
    municipality = municipality_of(items)

    # One block per contest, keyed on its term line — the only line a contest
    # has exactly one of. Every contest on the page is needed, not only the
    # school ones: a name to the right of a fire district's heading is not a
    # school board candidate, and omitting that heading would hand its
    # candidates to whichever school contest sat further left.
    blocks, school = [], []
    for term in items:
        if not TERM_RE.search(term.text):
            continue
        heading = _heading_lines(items, term)
        if not heading:
            continue
        block = Block(min(i.x for i in heading),
                      (min(i.y for i in heading) + term.y) / 2,
                      " / ".join(i.text for i in heading))
        blocks.append(block)
        if any(BOARD_RE.match(i.text) for i in heading):
            district = next((i for i in heading if DISTRICT_RE.search(i.text)),
                            None)
            school.append((block, term, district))

    if not school:
        return []

    claimed: dict[int, list[Item]] = {}
    for item in items:
        if not item.is_(SURNAME_FONT, SURNAME_MIN):
            continue
        owner = owner_of(blocks, item)
        if owner is not None:
            claimed.setdefault(id(owner), []).append(item)

    contests = []
    for block, term, district in school:
        match = TERM_RE.search(term.text)
        names, unfilled = [], 0
        for item in claimed.get(id(block), []):
            if NO_FILING_RE.match(item.text):
                unfilled += 1
            else:
                names.append(Candidate(full_name(items, item, GIVEN_FONT,
                                                 GIVEN_SIZE)))
        years = match.group("years")
        contests.append(Contest(
            county="burlington", year=year, election_type=election_type,
            municipality=municipality,
            district_name=district.text if district else None,
            office=OFFICE,
            term_years=int(years) if years else None,
            is_unexpired=match.group("kind").lower() == "unexpired",
            seats_available=NUMBER_WORDS.get(match.group("seats").lower()),
            candidates_filed=tuple(names), seats_unfilled_stated=unfilled,
            source_url=source_url, source_document=source_document,
            source_page=page_number))
    return contests
