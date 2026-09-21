"""The Morris parser, tested against literal table rows.

Morris prints one row per candidate, each repeating its contest's heading, so
most of the work is regrouping — and most of the risk is in the separators,
which are non-breaking spaces about half the time.
"""

from __future__ import annotations

import pytest

from njfilings.extract.morris import district_name, extract, normalise, parse


def run(text: str, page: int = 1):
    lines = [(page, normalise(l)) for l in text.strip("\n").splitlines()]
    return parse(lines, year="2026", source_url="https://clerk.example/x.pdf",
                 source_document="x.pdf")


ROW = """\
Boonton Town
MEMBER OF THE BOARD OF EDUCATION
3
3 Town
Brianna
O'HALLORAN
Caring-Informed-Committed
720 Wootton Street
Boonton
NJ
07005 brianna@example.com
"""


def test_a_single_row_becomes_a_contest_with_one_candidate():
    (c,) = run(ROW)
    assert c.municipality == "Boonton Town"
    assert (c.term_years, c.seats_available, c.is_unexpired) == (3, 3, False)
    assert [x.name for x in c.candidates_filed] == ["Brianna O'HALLORAN"]
    assert c.county == "morris"


def test_rows_sharing_a_heading_group_into_one_contest():
    """Every candidate repeats the contest's four header fields; the key comes
    off the page rather than from the parser's memory."""
    second = ROW.replace("Brianna\nO'HALLORAN\nCaring-Informed-Committed",
                         "Jennifer\nDARLING")
    (c,) = run(ROW + second)
    assert c.seats_available == 3
    assert [x.name for x in c.candidates_filed] == ["Brianna O'HALLORAN",
                                                    "Jennifer DARLING"]


def test_a_slogan_between_the_name_and_the_address_is_ignored():
    """The slogan is optional, so the fields after the name are not at fixed
    offsets — only the name's own two lines are."""
    without = ROW.replace("Caring-Informed-Committed\n", "")
    assert [x.name for x in run(without)[0].candidates_filed] \
        == ["Brianna O'HALLORAN"]


# --- the non-breaking space ----------------------------------------------

def test_non_breaking_spaces_are_matched_the_same_as_ordinary_ones():
    """Roughly half these documents separate words with U+00A0. A parser
    matching ordinary spaces finds nothing and concludes the document states no
    seats — wrong, and quietly so."""
    nbsp = ROW.replace("MEMBER OF THE BOARD OF EDUCATION",
                       "MEMBER\xa0OF\xa0THE\xa0BOARD\xa0OF\xa0EDUCATION")
    (c,) = run(nbsp)
    assert c.seats_available == 3 and c.candidate_count == 1


def test_normalise_collapses_every_kind_of_space():
    assert normalise("MEMBER\xa0OF\xa0THE  BOARD\tOF EDUCATION ") \
        == "MEMBER OF THE BOARD OF EDUCATION"


# --- seats, districts, terms ---------------------------------------------

def test_seats_are_read_from_the_column_never_from_the_candidates():
    rows = ROW
    for name in ("Ann\nCICCARELLI", "Bob\nSMITH", "Cara\nJONES"):
        rows += ROW.replace("Brianna\nO'HALLORAN\nCaring-Informed-Committed", name)
    (c,) = run(rows)
    assert c.seats_available == 3 and c.candidate_count == 4
    assert c.is_uncontested is False


@pytest.mark.parametrize("raw,expected", [
    ("Township", None), ("Borough", None), ("Town", None), ("City", None),
    ("Watchung Hills Regional", "Watchung Hills Regional"),
    ("Chester School District", "Chester School District"),
])
def test_a_district_type_is_not_a_district_name(raw, expected):
    """`Township` says what kind of district it is, not which one. Recording it
    as a name would invent something the document does not state."""
    assert district_name(raw) == expected


def test_a_regional_contest_is_separate_from_the_local_one():
    """Long Hill Township has both, with different seats and districts."""
    regional = """\
Long Hill Township
MEMBER OF THE REGIONAL BOARD OF EDUCATION
3
1 Watchung Hills Regional
Carol
PRASA
1 Road
Long Hill
NJ
07933 carol@example.com
"""
    local = """\
Long Hill Township
MEMBER OF THE BOARD OF EDUCATION
3
3 Township
Kim
CASE
2 Road
Long Hill
NJ
07933 kim@example.com
"""
    contests = run(regional + local)
    assert len(contests) == 2
    assert [(c.seats_available, c.district_name) for c in contests] == [
        (1, "Watchung Hills Regional"), (3, None)]
    assert contests[0].office.endswith("(Regional)")


def test_an_unexpired_term_is_its_own_contest():
    unexpired = ROW.replace("MEMBER OF THE BOARD OF EDUCATION",
                            "MEMBER OF THE BOARD OF EDUCATION UNEXPIRED TERM")
    contests = run(ROW + unexpired)
    assert [c.is_unexpired for c in contests] == [False, True]


# --- unfilled seats --------------------------------------------------------

EMPTY_ROW = """\
Boonton Town
MEMBER OF THE BOARD OF EDUCATION
3
3 Town
NO PETITION FILED
"""


def test_no_petition_filed_is_an_observed_unfilled_seat():
    """One marker per unfilled seat: three seats with one candidate prints two.
    """
    (c,) = run(ROW + EMPTY_ROW + EMPTY_ROW)
    assert c.candidate_count == 1
    assert c.seats_unfilled == 2 and c.seats_unfilled_observed is True
    assert c.problems() == []


def test_markers_disagreeing_with_the_arithmetic_are_flagged():
    """One marker where the seats imply two means a row was lost. The count is
    still reported as the document stated it — and the record complains."""
    (c,) = run(ROW + EMPTY_ROW)
    assert c.seats_unfilled == 1 and c.seats_unfilled_observed is True
    assert any("gives 2" in p for p in c.problems())


def test_a_contest_nobody_filed_for():
    empty = """\
Boonton Town
MEMBER OF THE BOARD OF EDUCATION
1
1 Town
NO PETITION FILED
"""
    (c,) = run(empty)
    assert c.candidate_count == 0 and c.seats_unfilled == 1


# --- things that are not rows ---------------------------------------------

def test_page_headers_are_not_mistaken_for_rows():
    header = """\
General Election, November 3, 2026
County of Morris, New Jersey
Candidates for School Board
Municipality
CONTEST TITLE
Term (Yrs) Vote For District
First Name and Middle Initial
Last Name and Suffix
Slogan
Street Address
City
State Zip
Email
"""
    assert run(header + ROW) and len(run(header + ROW)) == 1


def test_a_malformed_email_does_not_lose_the_candidate():
    """Real documents contain `joiurato3@gmail` with no domain, and one address
    with two `@`. The candidate is still a candidate."""
    broken = ROW.replace("07005 brianna@example.com", "07005 brianna@gmail")
    assert run(broken)[0].candidate_count == 1


def test_an_unrecognised_layout_yields_nothing_rather_than_a_guess():
    """2021-2022 use another format entirely. Extracting nothing is correct;
    inventing a contest from an unfamiliar shape would not be."""
    assert run("Boonton Town\nMember of Bd. of Ed.\nIrene LeFebvre\n"
               "180 South Terrace, Boonton 07005\n(Vote for 3)") == []
