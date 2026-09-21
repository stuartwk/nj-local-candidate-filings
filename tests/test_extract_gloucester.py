"""Gloucester's ballots, where the district is printed below its contests."""

from __future__ import annotations

import pytest

from njfilings.extract.gloucester import parse_page

SURNAME = ("UniversLTStd-Cn", 12.0)
GIVEN = ("ArialNarrow", 11.0)
BOLD = ("ArialNarrow,Bold", 11.0)
SLOGAN = ("ArialNarrow,Bold", 8.0)
ITALIC = ("ArialNarrow,Italic", 10.0)
DISTRICT = ("ArialBlack", 11.0)
PLAIN = ("ArialNarrow", 11.0)


def line(text, face=BOLD):
    return (text, face[0], face[1])


def contest_lines(seats="THREE", term="FULL TERM THREE (3) YEARS", people=(),
                  unfilled=0):
    out = [line("MEMBERSHIP TO"), line("BOARD OF EDUCATION"),
           line(term), line(seats and f"VOTE FOR {seats}", ITALIC)]
    for given, surname, slogan in people:
        out.append(line(given, GIVEN))
        out.append(line(surname, SURNAME))
        if slogan:
            out.append(line(slogan, SLOGAN))
    out += [line("NO PETITION FILED", BOLD)] * unfilled
    return out


def run(lines):
    return parse_page(lines, year="2026", page_number=2,
                      source_url="https://clerk.example/x.pdf",
                      source_document="x.pdf")


HEADER = [line("Harrison Twp - Dist 1", PLAIN)]


def test_a_contest_is_read_with_its_candidates():
    (c,) = run(HEADER + contest_lines(
        people=[("MATTHEW", "DECHEN", "PARENTS NOT POLITICIANS")])
        + [line("TOWNSHIP OF HARRISON SCHOOL DISTRICT", DISTRICT)])
    assert c.county == "gloucester" and c.municipality == "Harrison Twp"
    assert c.district_name == "TOWNSHIP OF HARRISON SCHOOL DISTRICT"
    assert (c.term_years, c.seats_available, c.is_unexpired) == (3, 3, False)
    assert [x.name for x in c.candidates_filed] == ["MATTHEW DECHEN"]


def test_the_district_is_read_from_below_its_contests():
    """It is printed after them, not before — inheriting one from above would
    label the first contest with the previous section's district."""
    lines = (HEADER
             + contest_lines(seats="ONE", people=[("SEAN", "HENDERSON", None)])
             + [line("CLEARVIEW REGIONAL HIGH SCHOOL DISTRICT", DISTRICT)]
             + contest_lines(people=[("ALEXIS", "RUBINO", "UNITED")])
             + [line("TOWNSHIP OF HARRISON SCHOOL DISTRICT", DISTRICT)])
    regional, local = run(lines)
    assert regional.district_name == "CLEARVIEW REGIONAL HIGH SCHOOL DISTRICT"
    assert regional.seats_available == 1
    assert local.district_name == "TOWNSHIP OF HARRISON SCHOOL DISTRICT"


def test_several_contests_share_the_district_printed_under_them():
    lines = (HEADER
             + contest_lines(people=[("ALEXIS", "RUBINO", None)])
             + contest_lines(seats="ONE", term="UNEXPIRED TERM ONE (1) YEAR",
                             people=[("VINCENT", "FERRIGNO", None)])
             + [line("TOWNSHIP OF HARRISON SCHOOL DISTRICT", DISTRICT)])
    full, unexpired = run(lines)
    assert full.district_name == unexpired.district_name
    assert (full.is_unexpired, unexpired.is_unexpired) == (False, True)
    assert (unexpired.term_years, unexpired.seats_available) == (1, 1)


@pytest.mark.parametrize("term,years,unexpired", [
    ("FULL TERM THREE (3) YEARS", 3, False),
    ("UNEXPIRED TERM ONE (1) YEAR", 1, True),
    ("UNEXPIRED TERM TWO (2) YEARS", 2, True),
])
def test_every_term_form(term, years, unexpired):
    (c,) = run(HEADER + contest_lines(term=term))
    assert (c.term_years, c.is_unexpired) == (years, unexpired)


# --- typography again decides who is a person -----------------------------

def test_a_slogan_is_not_a_candidate():
    """Both are upper case; only the typeface separates them."""
    (c,) = run(HEADER + contest_lines(
        people=[("CRYSTAL", "GREENE", "INTEGRITY VISION COLLABORATION")]))
    assert [x.name for x in c.candidates_filed] == ["CRYSTAL GREENE"]


def test_a_line_not_set_as_a_surname_is_not_one():
    lines = HEADER + contest_lines() + [line("SOMEBODY ELSE", SLOGAN)]
    assert run(lines)[0].candidate_count == 0


def test_no_petition_filed_is_an_observed_unfilled_seat():
    (c,) = run(HEADER + contest_lines(
        people=[("CRYSTAL", "GREENE", None), ("STEVEN", "LANTZ", None)],
        unfilled=1))
    assert c.candidate_count == 2
    assert c.seats_unfilled == 1 and c.seats_unfilled_observed is True
    assert c.problems() == []


def test_a_marker_is_not_taken_as_a_given_name():
    """`NO PETITION FILED` sits where a name would, and the line after it is a
    real candidate whose given name must not become 'NO PETITION FILED ...'."""
    lines = HEADER + [line("MEMBERSHIP TO"), line("BOARD OF EDUCATION"),
                      line("FULL TERM THREE (3) YEARS"),
                      line("VOTE FOR THREE", ITALIC),
                      line("NO PETITION FILED"),
                      line("LANTZ", SURNAME)]
    (c,) = run(lines)
    assert [x.name for x in c.candidates_filed] == ["LANTZ"]
    assert c.seats_unfilled == 1


def test_the_municipality_comes_from_the_ballot_identifier():
    (c,) = run([line("West Deptford Twp - Dist 2", PLAIN)] + contest_lines())
    assert c.municipality == "West Deptford Twp"


def test_a_page_with_no_board_contest_yields_nothing():
    assert run(HEADER + [line("TOWNSHIP COMMITTEE"), line("VOTE FOR TWO", ITALIC)]) == []
