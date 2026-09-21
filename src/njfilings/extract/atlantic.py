"""Atlantic County's school-board candidate list, 2026.

The cleanest table in the project. One row per candidate, columns:

    SCHOOL DISTRICT | TERM | # SEATS | CANDIDATE NAME | ADDRESS | ... | SLOGAN
    Absecon         | 3 yr | V2      | Paige Kuenzner | 1 304 SPRUCE ST | ...

Seats are stated as `V2` — vote for two — and an unfilled seat prints
`NO PETITION FILED` where the name would be, so unfilled seats are observed.

Two things the text extraction does to this document:

  * the term sometimes runs into the district cell with no space
    (`Galloway Township - Greater Egg Harbor Regiona3 yr`), taking a letter with
    it. The term is split back off, and the truncated district is repaired
    against the document's own vocabulary — never against outside knowledge.
  * the fields after the name merge unpredictably (an email and a slogan on one
    line, an address and a city on another). Nothing after the name is read, so
    it does not matter.

Rows are anchored on the seats cell rather than the district, because `V3` is
unmistakable and a district name is not.
"""

from __future__ import annotations

import re
from dataclasses import replace

from ..model import Candidate, Contest

SEATS_RE = re.compile(r"^V(\d+)$", re.I)
TERM_RE = re.compile(r"^(?P<years>\d+)\s*yr\.?(?P<unexpired>\s+Unexpired)?$", re.I)
# the same, but allowed to be glued to the end of the district cell
TERM_TAIL_RE = re.compile(
    r"^(?P<district>.*?)\s*(?P<years>\d+)\s*yr\.?(?P<unexpired>\s+Unexpired)?$",
    re.I)
NO_FILING_RE = re.compile(r"^NO PETITION FILED$", re.I)
# `Theresa Hudson*` and `Donnell Holland Sr. *` mark incumbents
INCUMBENT_RE = re.compile(r"\s*\*\s*$")

# The document states no office title anywhere; it is a school board candidate
# list throughout. This is the project's own label, not a quotation.
OFFICE = "School Board Member"


def split_place(value: str) -> tuple[str, str | None]:
    """`Northfield - Mainland Regional` -> the town and the regional district.

    A bare name means the town's own district, which the document does not name
    — so it is recorded as unknown rather than invented.
    """
    municipality, separator, district = value.partition(" - ")
    if not separator:
        return value.strip(), None
    return municipality.strip(), district.strip() or None


def repair_districts(values: list[str]) -> dict[str, str]:
    """Undo the truncation the text extraction causes, using only this
    document's own vocabulary.

    `Greater Egg Harbor Regiona` is a strict prefix of `Greater Egg Harbor
    Regional`, which the same document prints intact on another row. Where a
    district name is a strict prefix of exactly one other, the longer is meant.
    Ambiguous cases are left alone.
    """
    districts = {d for d in (split_place(v)[1] for v in values) if d}
    repairs = {}
    for short in districts:
        longer = [d for d in districts if d != short and d.startswith(short)]
        if len(longer) == 1:
            repairs[short] = longer[0]
    return repairs


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    import pymupdf

    numbered: list[tuple[int, str]] = []
    for page_number, page in enumerate(pymupdf.open(path), 1):
        for line in page.get_text().splitlines():
            numbered.append((page_number, re.sub(r"\s+", " ", line).strip()))
    return parse(numbered, year=year, source_url=source_url,
                 source_document=source_document, election_type=election_type)


def parse(numbered: list[tuple[int, str]], year: str, source_url: str,
          source_document: str, election_type: str = "general") -> list[Contest]:
    lines = [text for _, text in numbered]
    rows = []
    for index, line in enumerate(lines):
        seats = SEATS_RE.match(line)
        if not seats or index < 1:
            continue
        above = lines[index - 1]
        if TERM_RE.match(above) and index >= 2:
            term_text, place = above, lines[index - 2]
        else:
            # the term is glued to the district cell, or missing entirely
            tail = TERM_TAIL_RE.match(above)
            if not tail:
                continue
            term_text, place = f"{tail.group('years')} yr", tail.group("district")
        term = TERM_RE.match(term_text)
        body = lines[index + 1] if index + 1 < len(lines) else ""
        rows.append({
            "place": place,
            "term_years": int(term.group("years")),
            "is_unexpired": bool(term.group("unexpired")),
            "seats": int(seats.group(1)),
            "unfilled": bool(NO_FILING_RE.match(body)),
            "name": None if NO_FILING_RE.match(body) or not body
            else INCUMBENT_RE.sub("", body),
            "page": numbered[index][0],
        })

    repairs = repair_districts([row["place"] for row in rows])
    contests: dict[tuple, Contest] = {}
    order: list[tuple] = []
    for row in rows:
        municipality, district = split_place(row["place"])
        district = repairs.get(district, district)
        key = (municipality, district, row["term_years"], row["is_unexpired"],
               row["seats"])
        if key not in contests:
            order.append(key)
            contests[key] = Contest(
                county="atlantic", year=year, election_type=election_type,
                municipality=municipality or None, district_name=district,
                office=OFFICE, term_years=row["term_years"],
                is_unexpired=row["is_unexpired"], seats_available=row["seats"],
                seats_unfilled_stated=0, source_url=source_url,
                source_document=source_document, source_page=row["page"])
        current = contests[key]
        if row["unfilled"]:
            contests[key] = replace(
                current,
                seats_unfilled_stated=(current.seats_unfilled_stated or 0) + 1)
        elif row["name"]:
            contests[key] = replace(
                current,
                candidates_filed=current.candidates_filed + (Candidate(row["name"]),))
    return [contests[key] for key in order]
