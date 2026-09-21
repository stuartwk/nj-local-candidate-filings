"""Coverage exists to stop a rate being quoted wider than its denominator.

So the tests are mostly about what is *excluded*: cells that were never read,
contests whose seats are unknown, and years where the set of counties changed.
"""

from __future__ import annotations

import csv

import pytest

from njfilings.coverage import COVERAGE_FIELDS, Cell, write
from njfilings.model import Candidate, Contest


def contest(seats=3, candidates=2, unfilled=0, observed=True, county="hunterdon",
            year="2026"):
    return Contest(
        county=county, year=year, election_type="general",
        municipality="Somewhere", district_name=None,
        office="School Board Member", term_years=3, is_unexpired=False,
        seats_available=seats,
        candidates_filed=tuple(Candidate(f"Person {n}") for n in range(candidates)),
        seats_unfilled_stated=unfilled if observed else None,
        source_url="https://clerk.example/x.pdf", source_document="x.pdf",
        source_page=1)


def cell(status="complete", contests=None, **kw):
    return Cell(kw.pop("county", "hunterdon"), kw.pop("year", "2026"), status,
                kw.pop("declared", 1), kw.pop("held", 1),
                contests if contests is not None else [contest()], **kw)


# --- the measures ---------------------------------------------------------

def test_candidates_per_seat_is_a_ratio_of_two_sums():
    """Deliberately robust: one misparsed contest barely moves it."""
    c = cell(contests=[contest(seats=3, candidates=4),
                       contest(seats=1, candidates=1)])
    assert c.seats == 4 and c.candidates == 5
    assert c.candidates_per_seat == pytest.approx(1.25)


def test_a_contest_with_unknown_seats_is_in_neither_sum():
    """Counting it as zero seats would inflate the rate; counting its
    candidates alone would too."""
    c = cell(contests=[contest(seats=2, candidates=2),
                       contest(seats=None, candidates=5)])
    assert c.seats == 2 and c.candidates == 2
    assert c.candidates_per_seat == pytest.approx(1.0)


def test_a_cell_with_no_known_seats_has_no_rate():
    assert cell(contests=[contest(seats=None)]).candidates_per_seat is None
    assert cell(contests=[]).candidates_per_seat is None


def test_uncontested_rate_counts_contests_not_seats():
    c = cell(contests=[contest(seats=3, candidates=2),     # uncontested
                       contest(seats=1, candidates=3)])    # contested
    assert c.uncontested_rate == pytest.approx(0.5)


def test_uncontested_rate_ignores_contests_it_cannot_judge():
    c = cell(contests=[contest(seats=3, candidates=2),
                       contest(seats=None, candidates=9)])
    assert c.uncontested_rate == pytest.approx(1.0)


# --- observed versus derived ---------------------------------------------

def test_a_cell_says_whether_its_unfilled_seats_were_read_or_subtracted():
    """Publishing a rate over a mix of the two without saying so is the failure
    this column exists to prevent."""
    assert cell(contests=[contest(unfilled=1)]).unfilled_observed == "all"
    assert cell(contests=[contest(observed=False)]).unfilled_observed == "none"
    assert cell(contests=[contest(unfilled=1),
                          contest(observed=False)]).unfilled_observed == "mixed"


def test_a_cell_with_nothing_in_it_claims_nothing():
    assert cell(contests=[]).unfilled_observed == ""


# --- the matrix as a file -------------------------------------------------

def test_every_column_is_written_and_absent_rates_stay_empty(tmp_path):
    out = tmp_path / "coverage.csv"
    write([cell(), cell(status="gap", contests=[], declared=0, held=0,
                        reason="no document known to exist")], out)
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0]) == COVERAGE_FIELDS
    assert rows[0]["candidates_per_seat"] == "0.67"
    # a cell with no data must not report a rate of zero
    assert rows[1]["candidates_per_seat"] == ""
    assert rows[1]["uncontested_rate"] == ""
    assert rows[1]["status"] == "gap"
    assert rows[1]["reason"] == "no document known to exist"


def test_a_reason_is_recorded_for_everything_not_complete(tmp_path):
    out = tmp_path / "coverage.csv"
    write([cell(status="no-extractor", contests=[], held=73,
                reason="73 sample_ballot held; no extractor yet")], out)
    (row,) = list(csv.DictReader(out.open()))
    assert row["status"] == "no-extractor" and row["documents_held"] == "73"
    assert "no extractor" in row["reason"]
