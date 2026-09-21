"""Collapsing one contest printed on several ballots.

A shared district does not imply a shared contest, and getting that wrong either
doubles a county's seats or erases an unfilled one.
"""

from __future__ import annotations

from njfilings.build import merge_duplicates
from njfilings.model import Candidate, Contest


def contest(municipality, district=None, seats=3, names=("A SMITH",), unfilled=0,
            document="x.pdf", page=1):
    return Contest(
        county="salem", year="2026", election_type="general",
        municipality=municipality, district_name=district,
        office="School Board Member", term_years=3, is_unexpired=False,
        seats_available=seats,
        candidates_filed=tuple(Candidate(n) for n in names),
        seats_unfilled_stated=unfilled,
        source_url="https://clerk.example/x.pdf", source_document=document,
        source_page=page)


def test_the_same_contest_on_two_ward_ballots_becomes_one():
    """Salem City prints its board election on both ward ballots. Two rows
    would double its seats and its candidates."""
    east = contest("Salem City", "Salem City School Board",
                   document="salem-city-east.pdf")
    west = contest("Salem City", "Salem City School Board",
                   document="salem-city-west.pdf")
    (merged,) = merge_duplicates([east, west])
    assert merged.seats_available == 3 and merged.candidate_count == 1
    assert merged.also_on == ("salem-city-west.pdf#p1",)


def test_two_towns_electing_one_shared_board_become_one():
    """Pittsgrove and Elmer elect the same three members between them."""
    merged = merge_duplicates([
        contest("Pittsgrove", "Pittsgrove/Elmer School Board",
                names=("A", "B", "C", "D"), document="pittsgrove.pdf"),
        contest("Elmer", "Pittsgrove/Elmer School Board",
                names=("A", "B", "C", "D"), document="elmer.pdf")])
    assert len(merged) == 1
    assert merged[0].also_on == ("elmer.pdf#p1 (Elmer)",)


def test_a_shared_board_with_a_seat_each_stays_two_contests():
    """Penns Grove and Carneys Point share a board but elect separately, and
    Penns Grove's seat drew nobody. Merging would erase an unfilled seat."""
    merged = merge_duplicates([
        contest("Carneys Point", "Penns Grove/Carneys Point School Board",
                seats=1, names=("M TINSLEY", "R RASIN"), document="cp.pdf"),
        contest("Penns Grove", "Penns Grove/Carneys Point School Board",
                seats=1, names=(), unfilled=1, document="pg.pdf")])
    assert len(merged) == 2
    assert sum(c.seats_unfilled for c in merged) == 1


def test_a_shared_board_with_different_seat_counts_stays_two_contests():
    """Woodstown elects two to the shared board, Pilesgrove one."""
    merged = merge_duplicates([
        contest("Woodstown", "Woodstown/Pilesgrove School Board", seats=2),
        contest("Pilesgrove", "Woodstown/Pilesgrove School Board", seats=1)])
    assert len(merged) == 2


def test_identical_local_contests_in_different_towns_never_merge():
    """Two towns that each had one seat and no candidates look identical in
    every field. They are not the same contest, and the municipality is what
    says so — which is why it joins the key when no district is named."""
    merged = merge_duplicates([
        contest("Mannington", None, seats=1, names=(), unfilled=1,
                document="mannington.pdf"),
        contest("Quinton", None, seats=1, names=(), unfilled=1,
                document="quinton.pdf")])
    assert len(merged) == 2
    assert sum(c.seats_available for c in merged) == 2


def test_merging_keeps_the_order_it_first_saw():
    merged = merge_duplicates([contest("B", None), contest("A", None),
                               contest("B", None)])
    assert [c.municipality for c in merged] == ["B", "A"]
