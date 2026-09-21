"""A validator that cannot fail is worse than no validator, so most of these
tests corrupt a known-good dataset and insist the corruption is noticed.

The four failure modes below are not hypothetical: a dropped candidate and a
lost unfilled marker are both bugs that were actually in the Hunterdon parser,
and the marker one was silent — the seat simply looked filled.
"""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from njfilings.extract.hunterdon import parse
from njfilings.validate import (check_record, enumerate_document,
                                enumerate_municipalities)

DOCUMENT = """\
HUNTERDON COUNTY
ANNUAL SCHOOL ELECTION
DELAWARE VALLEY REGIONAL HIGH SCHOOL
ALEXANDRIA TOWNSHP
School Board Member- 3 Yr. Term - Vote for One
Andrew Sliver 16 Northwood Dr. Pittstown, NJ 08867 andrew@example.com
     Support Public Education
FRENCHTOWN BOROUGH
School Board Member-3 Yr. Term-Vote for Two
Thomas G. Loughlin 1 River Mills Dr., Frenchtown, NJ 08825 thomas@example.com
NO NOMINATION MADE
HUNTERDON COUNTY- LOCAL DISTRICTS
BETHLEHEM TOWNSHIP
School Board Member – 3 Yr. Term -Vote for Three
Daniel P. MacDonnell 4 Farrow Ln. Asbury, NJ 08802 daniel@example.com
Jenny Holmes 5 Creveling Rd. Bloomsbury, NJ 08804 jenny@example.com
No Petition Filed
"""


@pytest.fixture
def contests():
    lines = [(1, l) for l in DOCUMENT.splitlines()]
    return parse(lines, year="2026", source_url="https://clerk.example/x.pdf",
                 source_document="x.pdf")


def test_the_fixture_parses_the_way_the_tests_assume(contests):
    assert len(contests) == 3
    assert sum(len(c.candidates_filed) for c in contests) == 4
    assert sum(c.seats_unfilled_stated or 0 for c in contests) == 2


# --- enumeration notices corruption --------------------------------------

def test_a_clean_dataset_raises_no_complaints(contests):
    assert enumerate_document(DOCUMENT, contests) == []


def test_a_dropped_candidate_is_noticed(contests):
    """Every email belongs to exactly one candidate, so losing one shows up."""
    broken = list(contests)
    i = next(i for i, c in enumerate(broken) if len(c.candidates_filed) > 1)
    broken[i] = replace(broken[i],
                        candidates_filed=broken[i].candidates_filed[:-1])
    assert any("email" in issue for issue in enumerate_document(DOCUMENT, broken))


def test_a_lost_unfilled_marker_is_noticed(contests):
    """The 2023 bug exactly: a capitalised marker read as a heading, so the
    seat looked filled and nothing complained."""
    broken = list(contests)
    j = next(j for j, c in enumerate(broken) if (c.seats_unfilled_stated or 0) > 0)
    broken[j] = replace(broken[j], seats_unfilled_stated=0)
    assert any("marker" in issue for issue in enumerate_document(DOCUMENT, broken))


def test_an_invented_candidate_is_noticed(contests):
    from njfilings.model import Candidate
    broken = list(contests)
    broken[0] = replace(broken[0],
                        candidates_filed=broken[0].candidates_filed
                        + (Candidate("Nobody At All"),))
    assert any("email" in issue for issue in enumerate_document(DOCUMENT, broken))


def test_a_duplicated_contest_is_noticed(contests):
    issues = enumerate_document(DOCUMENT, contests + contests[:1])
    assert any("contest-shaped" in issue for issue in issues)


def test_a_town_given_the_wrong_number_of_contests_is_noticed(contests):
    """The enumeration arm proper: what the source says a town has, versus
    what the dataset gives it."""
    broken = [c for c in contests if c.municipality != "BETHLEHEM TOWNSHIP"]
    issues = enumerate_municipalities(DOCUMENT, broken, how_many=99,
                                      rng=random.Random(0))
    assert any("BETHLEHEM TOWNSHIP" in issue for issue in issues)


# --- transcription notices corruption -------------------------------------

def test_a_record_agrees_with_the_page_it_cites(contests):
    result = check_record(contests[0], [DOCUMENT])
    assert result["verdict"] == "ok"
    assert all(result[k] for k in ("municipality_on_page", "term_on_page",
                                   "seats_on_page", "names_on_page"))


def test_a_record_citing_a_page_it_is_not_on_is_flagged(contests):
    pages = ["nothing relevant here", DOCUMENT]
    assert check_record(replace(contests[0], source_page=1), pages)["verdict"] \
        == "CHECK"


def test_an_altered_seat_count_is_flagged(contests):
    """Seats must be on the page, not inferred from the candidate count."""
    result = check_record(replace(contests[0], seats_available=3), [DOCUMENT])
    assert result["seats_on_page"] is False and result["verdict"] == "CHECK"


def test_an_invented_name_is_flagged(contests):
    from njfilings.model import Candidate
    broken = replace(contests[0],
                     candidates_filed=(Candidate("Fabricated Person"),))
    assert check_record(broken, [DOCUMENT])["names_on_page"] is False


def test_the_excerpt_shows_the_source(contests):
    row = check_record(contests[0], [DOCUMENT])
    assert "Andrew Sliver" in row["source_excerpt"]
