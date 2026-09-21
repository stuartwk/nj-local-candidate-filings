"""The record type's job is to make the forbidden inferences impossible, so the
tests are mostly about what it refuses to conclude."""

from __future__ import annotations

import pytest

from njfilings.model import CSV_FIELDS, Candidate, Contest, sort_key, to_row


def contest(**kw) -> Contest:
    base = dict(
        county="hunterdon", year="2026", election_type="general",
        municipality="Clinton Township", district_name="Clinton Twp School",
        office="School Board Member", term_years=3, is_unexpired=False,
        seats_available=3,
        candidates_filed=(Candidate("ALICE ROE"), Candidate("BOB DOE")),
        source_url="https://clerk.example/list.pdf",
        source_document="school-board-candidates.pdf", source_page=1,
    )
    base.update(kw)
    return Contest(**base)


# --- what it refuses to infer -------------------------------------------

def test_unknown_seats_poison_every_derived_field():
    """A contest with two candidates is not thereby a two-seat contest."""
    c = contest(seats_available=None)
    assert c.candidate_count == 2          # this much we did observe
    assert c.is_uncontested is None
    assert c.seats_unfilled is None
    assert c.seats_unfilled_observed is None


def test_a_district_nobody_stated_stays_none():
    assert contest(district_name=None).district_name is None


def test_none_is_written_as_empty_not_as_zero_or_false():
    """An absent value must not read as a real one in the CSV."""
    row = to_row(contest(seats_available=None, term_years=None,
                         district_name=None, municipality=None))
    for key in ("seats_available", "term_years", "district_name",
                "municipality", "is_uncontested", "seats_unfilled",
                "seats_unfilled_observed"):
        assert row[key] == "", key


# --- the two permitted derivations --------------------------------------

def test_withdrawn_candidates_are_not_running():
    c = contest(candidates_filed=(Candidate("ALICE ROE"),
                                  Candidate("BOB DOE", withdrew=True)))
    assert c.candidate_count == 1
    assert c.seats_unfilled == 2
    assert "BOB DOE [withdrew]" in to_row(c)["candidates_filed"]


def test_uncontested_means_candidates_at_most_seats():
    assert contest(seats_available=3).is_uncontested is True      # 2 for 3
    assert contest(seats_available=2).is_uncontested is True      # 2 for 2
    assert contest(seats_available=1).is_uncontested is False     # 2 for 1


def test_under_filled_is_also_uncontested():
    """Two candidates for three seats is both, and neither is an error."""
    c = contest(seats_available=3)
    assert c.is_uncontested is True and c.seats_unfilled == 1


def test_arithmetic_never_goes_negative():
    c = contest(seats_available=1)
    assert c.seats_unfilled == 0


# --- observed beats derived ----------------------------------------------

def test_a_stated_count_is_preferred_and_flagged_as_observed():
    c = contest(seats_available=3,
                candidates_filed=(Candidate("ALICE ROE"),),
                seats_unfilled_stated=2)
    assert c.seats_unfilled == 2
    assert c.seats_unfilled_observed is True


def test_arithmetic_is_flagged_as_not_observed():
    c = contest(seats_available=3, seats_unfilled_stated=None)
    assert c.seats_unfilled == 1
    assert c.seats_unfilled_observed is False


def test_a_stated_zero_is_a_statement_not_a_missing_value():
    """`0` and `None` mean different things and must not collapse."""
    c = contest(seats_available=2, seats_unfilled_stated=0)
    assert c.seats_unfilled == 0 and c.seats_unfilled_observed is True


# --- coherence ------------------------------------------------------------

def test_a_healthy_record_has_no_complaints():
    assert contest().problems() == []


def test_stated_and_derived_disagreeing_is_reported():
    """Usually means the parse dropped a candidate."""
    c = contest(seats_available=3,
                candidates_filed=(Candidate("A"), Candidate("B")),
                seats_unfilled_stated=2)           # arithmetic says 1
    assert any("disagree" in p or "gives" in p for p in c.problems())


def test_duplicate_candidates_are_reported():
    c = contest(candidates_filed=(Candidate("ALICE ROE"),
                                  Candidate("alice roe")))
    assert any("twice" in p for p in c.problems())


def test_missing_provenance_is_reported():
    assert any("source_url" in p for p in contest(source_url="").problems())


@pytest.mark.parametrize("seats", [0, -1])
def test_impossible_seat_counts_are_reported(seats):
    assert any("seats_available" in p for p in contest(seats_available=seats).problems())


# --- merging duplicate printings -----------------------------------------

def test_merging_keeps_the_other_printing_as_a_citation():
    a = contest(municipality="Alpine")
    b = contest(municipality="Closter", source_page=7,
                source_document="b2025-closter.pdf")
    merged = a.merged_with(b)
    assert merged.municipality == "Alpine"
    assert merged.also_on == ("b2025-closter.pdf#p7 (Closter)",)
    assert to_row(merged)["also_on"] == "b2025-closter.pdf#p7 (Closter)"


# --- the shape of the output ---------------------------------------------

def test_every_column_is_populated_and_no_others():
    assert list(to_row(contest())) == CSV_FIELDS


def test_sort_is_deterministic_and_tolerates_missing_fields():
    rows = [
        contest(municipality="Union Twp", district_name=None),
        contest(municipality="Alpine", is_unexpired=True),
        contest(municipality="Alpine", is_unexpired=False),
    ]
    order = [(c.municipality, c.is_unexpired) for c in sorted(rows, key=sort_key)]
    assert order == [("Alpine", False), ("Alpine", True), ("Union Twp", False)]
