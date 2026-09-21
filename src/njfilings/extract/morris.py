"""Morris County's school-board candidate list, 2023-2026.

The best-structured source in the project: a real table, one row per candidate,
which pymupdf emits as a fixed sequence of lines:

    Boonton Town                        <- municipality
    MEMBER OF THE BOARD OF EDUCATION    <- contest title
    3                                   <- term, years
    3 Town                              <- seats, then district
    Brianna                             <- first name
    O'HALLORAN                          <- last name
    Caring-Informed-Committed           <- slogan, optional
    720 Wootton Street
    Boonton
    NJ
    07005 mrsbriannaohalloran@gmail.com

A contest that drew nobody replaces the name block with `NO PETITION FILED`, so
unfilled seats are observed here rather than derived. Every candidate repeats
its contest's four header fields, so rows are grouped back into contests.

**The non-breaking space.** Roughly half the lines in these documents separate
words with U+00A0 rather than a space — `MEMBER\\xa0OF\\xa0THE\\xa0BOARD…`,
`Vote\\xa0For`. Which one a given line uses is not predictable and changes
between years. A parser matching ordinary spaces finds nothing, concludes the
document states no seats, and is confidently wrong. Everything here is matched
after normalising whitespace.

2021 and 2022 are a different format — term and seats interleaved mid-block by
a multi-column layout, and no unfilled-seat markers at all — and need their own
profile. They are deliberately not handled here.
"""

from __future__ import annotations

import re

from ..model import Candidate, Contest

TITLE_RE = re.compile(
    r"^MEMBER OF THE (?P<regional>REGIONAL )?BOARD OF EDUCATION"
    r"(?P<unexpired> UNEXPIRED TERM)?$", re.I)

# "3 Town" -> three seats, district "Town"
SEATS_DISTRICT_RE = re.compile(r"^(?P<seats>\d+)\s+(?P<district>.+)$")

NO_FILING_RE = re.compile(r"^NO PETITION FILED$", re.I)
EMAIL_RE = re.compile(r"[\w.\-+']+@[\w.\-]+\.\w+")

# A local district is named only by its municipality's type. `Township` is a
# kind of district, not the name of one, so it is recorded as unknown — the same
# treatment Hunterdon's local districts get, and for the same reason: inventing
# a district name the document does not give would breach ground rule 4.
GENERIC_DISTRICT = {"town", "township", "borough", "city", "village"}

OFFICE = "Member of the Board of Education"


def normalise(line: str) -> str:
    """Collapse every kind of space, including U+00A0, to one ordinary space."""
    return re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()


def district_name(raw: str) -> str | None:
    return None if raw.strip().lower() in GENERIC_DISTRICT else raw.strip()


def extract(path, year: str, source_url: str, source_document: str,
            election_type: str = "general") -> list[Contest]:
    import pymupdf

    numbered: list[tuple[int, str]] = []
    for page_number, page in enumerate(pymupdf.open(path), 1):
        for line in page.get_text().splitlines():
            numbered.append((page_number, normalise(line)))
    return parse(numbered, year=year, source_url=source_url,
                 source_document=source_document, election_type=election_type)


def parse(numbered: list[tuple[int, str]], year: str, source_url: str,
          source_document: str, election_type: str = "general") -> list[Contest]:
    """Group the table's rows back into contests.

    Lines are expected pre-normalised; `extract` does that. Split out so the
    parser can be tested against literal text.
    """
    rows: list[dict] = []
    for index, (page_number, line) in enumerate(numbered):
        title = TITLE_RE.match(line)
        if not title:
            continue
        # the four header fields sit either side of the title, at fixed offsets
        if index < 1 or index + 3 >= len(numbered):
            continue
        municipality = numbered[index - 1][1]
        term_text = numbered[index + 1][1]
        seats_text = numbered[index + 2][1]
        body = numbered[index + 3][1]

        seats_match = SEATS_DISTRICT_RE.match(seats_text)
        if not term_text.isdigit() or not seats_match:
            continue        # not a data row: a page header, or a layout we do
                            # not recognise. Recorded as nothing rather than
                            # guessed at.

        rows.append({
            "municipality": municipality,
            "is_unexpired": bool(title.group("unexpired")),
            "regional": bool(title.group("regional")),
            "term_years": int(term_text),
            "seats": int(seats_match.group("seats")),
            "district": district_name(seats_match.group("district")),
            "page": page_number,
            "unfilled": bool(NO_FILING_RE.match(body)),
            "name": _name(numbered, index + 3),
        })

    return _group(rows, year=year, election_type=election_type,
                  source_url=source_url, source_document=source_document)


def _name(numbered: list[tuple[int, str]], start: int) -> str | None:
    """First and last name, which are the two lines after the header fields."""
    first = numbered[start][1]
    if NO_FILING_RE.match(first) or not first:
        return None
    last = numbered[start + 1][1] if start + 1 < len(numbered) else ""
    # a surname line is never an address or an email
    if EMAIL_RE.search(last) or re.match(r"^\d", last):
        return first
    return f"{first} {last}".strip()


def _group(rows: list[dict], year: str, election_type: str,
           source_url: str, source_document: str) -> list[Contest]:
    """One contest per (municipality, term, seats, district, unexpired).

    Every candidate row repeats those five, which is what makes regrouping
    safe: the key comes off the page rather than from the parser's memory.
    """
    contests: dict[tuple, Contest] = {}
    order: list[tuple] = []
    for row in rows:
        key = (row["municipality"], row["is_unexpired"], row["term_years"],
               row["seats"], row["district"])
        if key not in contests:
            order.append(key)
            contests[key] = Contest(
                county="morris", year=year, election_type=election_type,
                municipality=row["municipality"] or None,
                district_name=row["district"],
                office=OFFICE + (" (Regional)" if row["regional"] else ""),
                term_years=row["term_years"], is_unexpired=row["is_unexpired"],
                seats_available=row["seats"], seats_unfilled_stated=0,
                source_url=source_url, source_document=source_document,
                source_page=row["page"])
        current = contests[key]
        from dataclasses import replace
        if row["unfilled"]:
            contests[key] = replace(
                current,
                seats_unfilled_stated=(current.seats_unfilled_stated or 0) + 1)
        elif row["name"]:
            contests[key] = replace(
                current,
                candidates_filed=current.candidates_filed
                + (Candidate(row["name"]),))
    return [contests[key] for key in order]
