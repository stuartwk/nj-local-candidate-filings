"""Union's per-page layout, where the contest header follows the candidates."""

from __future__ import annotations

import pytest

from njfilings.extract.union import parse

BOILERPLATE = """\
REFRAIN FROM PUBLISHING LITERATURE UNTIL POSITIONS ARE CONFIRMED SEPTEMBER 1ST
8/12/2026
CLARA C. FERNÁNDEZ, UNION COUNTY DEPUTY CLERK
CANDIDATE LIST FOR THE SCHOOL BOARD ELECTION
NOVEMBER 3, 2026
"""


def page(municipality="TOWNSHIP OF CLARK", column="POSITION", body="",
         header="3 YEAR TERM – VOTE FOR THREE"):
    return (BOILERPLATE + f"{municipality}\n{column}\nCANDIDATE\nADDRESS\n"
            f"SLOGAN\nTERM\nEMAIL ADDRESS\n{body}{header}\n")


def candidate(position="1-1", name="Steven Donkersloot"):
    return f"{position}\n {name}\n317 Willow Way\n3 Yrs\ns@example.com\n"


def run(*pages):
    return parse(list(pages), year="2026", source_url="https://clerk.example/x.pdf",
                 source_document="x.pdf")


def test_a_page_is_a_contest():
    (c,) = run(page(body=candidate()))
    assert c.county == "union" and c.municipality == "TOWNSHIP OF CLARK"
    assert (c.term_years, c.seats_available, c.is_unexpired) == (3, 3, False)
    assert [x.name for x in c.candidates_filed] == ["Steven Donkersloot"]
    assert c.source_page == 1


def test_each_page_is_its_own_contest():
    contests = run(page(municipality="TOWNSHIP OF CLARK", body=candidate()),
                   page(municipality="CITY OF RAHWAY", body=candidate()))
    assert [c.municipality for c in contests] == ["TOWNSHIP OF CLARK",
                                                  "CITY OF RAHWAY"]
    assert [c.source_page for c in contests] == [1, 2]


def test_the_header_after_the_candidates_still_governs_them():
    """The contest header belongs to another column of the layout and comes out
    last. Seats must still be read from it."""
    body = candidate("1-1", "A One") + candidate("1-2", "B Two")
    (c,) = run(page(body=body, header="3 YEAR TERM – VOTE FOR TWO"))
    assert c.seats_available == 2 and c.candidate_count == 2


@pytest.mark.parametrize("position", ["1-1", "2-1", "1E", "3F"])
def test_both_spellings_of_a_ballot_position(position):
    """Most pages use `1-1`; Hillside uses `1E`."""
    (c,) = run(page(body=candidate(position, "Jo Ann Givens")))
    assert [x.name for x in c.candidates_filed] == ["Jo Ann Givens"]


def test_the_plural_column_header_is_accepted():
    """Seventeen pages say POSITION; Fanwood says POSITIONS."""
    (c,) = run(page(municipality="BOROUGH OF FANWOOD", column="POSITIONS",
                    body=candidate()))
    assert c.municipality == "BOROUGH OF FANWOOD"


def test_a_contest_nobody_filed_for():
    (c,) = run(page(municipality="BOROUGH OF FANWOOD", column="POSITIONS",
                    body="NO PETITION FILED\n",
                    header="3 YEAR TERM- VOTE FOR ONE"))
    assert c.candidate_count == 0
    assert c.seats_unfilled == 1 and c.seats_unfilled_observed is True


@pytest.mark.parametrize("header,seats", [
    ("3 YEAR TERM – VOTE FOR ONE", 1),
    ("3 YEAR TERM- VOTE FOR TWO", 2),
    ("3 YEAR TERM-VOTE FOR THREE", 3),
    ("3 YEAR TERM VOTE FOR THREE", 3),
])
def test_the_separator_in_the_header_varies(header, seats):
    assert run(page(body=candidate(), header=header))[0].seats_available == seats


def test_a_page_without_a_contest_header_yields_nothing():
    """Better to record nothing than to invent a contest with unknown seats."""
    assert run(BOILERPLATE + "TOWNSHIP OF CLARK\nPOSITION\n") == []
