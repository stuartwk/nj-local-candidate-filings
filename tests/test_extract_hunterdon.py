"""The Hunterdon parser, tested against literal text.

Most of these are cases the four real documents actually contain — the
punctuation chaos, the two ways districts nest, the capitalised markers — so a
regression here means a specific document stopped parsing, not that a style
preference changed.
"""

from __future__ import annotations

import pytest

from njfilings.extract.hunterdon import candidate_name, is_heading, parse


def run(text: str, page: int = 1):
    lines = [(page, l) for l in text.strip("\n").splitlines()]
    return parse(lines, year="2026", source_url="https://clerk.example/x.pdf",
                 source_document="x.pdf")


CANDIDATE = "Andrew Sliver 16 Northwood Dr. Pittstown, NJ 08867 a@example.com"


# --- the contest line, in all its spellings -----------------------------

@pytest.mark.parametrize("line,term,unexpired,seats", [
    ("School Board Member- 3 Yr. Term – Vote for One", 3, False, 1),
    ("School Board Member-3 Yr. Term-Vote for One", 3, False, 1),
    ("School Board Member-_ 3 Yr. TERM-Vote for One", 3, False, 1),
    ("School Board Member—3 Yr. Term Vote for Two", 3, False, 2),
    ("School Board Member– 3 Yr. Term- Vote for Three", 3, False, 3),
    ("School Board Member- 3 Yr.Term-Vote for One", 3, False, 1),
    ("School Board Member- 3 Yr. Term- Term Vote for Two", 3, False, 2),
    ("School Board Member -1 Yr. Unexpired -Vote for One", 1, True, 1),
    ("School Board Member 1 Yr. Unexpired- Vote for One", 1, True, 1),
    ("School Board Member – 2 Yr. Unexpired- Vote for One", 2, True, 1),
])
def test_every_spelling_of_the_contest_line(line, term, unexpired, seats):
    (c,) = run(f"ALEXANDRIA TOWNSHIP\n{line}\n{CANDIDATE}")
    assert (c.term_years, c.is_unexpired, c.seats_available) == (term, unexpired, seats)


def test_seats_come_from_the_page_never_from_the_candidates():
    """Three candidates for a one-seat contest is a real thing that happens."""
    body = "\n".join(f"Name{n} {n} Road, NJ 08867 n{n}@example.com" for n in range(3))
    (c,) = run(f"ALEXANDRIA TOWNSHIP\nSchool Board Member-3 Yr. Term-Vote for One\n{body}")
    assert c.seats_available == 1 and c.candidate_count == 3
    assert c.is_uncontested is False


def test_an_unexpired_term_is_its_own_contest():
    contests = run("""
CLINTON TOWNSHIP
School Board Member- 3 Yr. Term Vote for Three
Andrew Clarke 12 Fawn Dr. Lebanon, NJ 08833 a@example.com
School Board Member-1 Yr. Unexpired-Vote for One
Jason M. Burns 508 Hamden Rd., Annandale, NJ 08801 j@example.com
""")
    assert [(c.term_years, c.is_unexpired, c.seats_available) for c in contests] \
        == [(3, False, 3), (1, True, 1)]
    assert all(c.municipality == "CLINTON TOWNSHIP" for c in contests)


# --- unfilled seats -------------------------------------------------------

def test_both_spellings_of_an_unfilled_seat_are_counted():
    for marker in ("No Nomination Made", "No Petition Filed"):
        (c,) = run(f"BETHLEHEM TOWNSHIP\n"
                   f"School Board Member – 3 Yr. Term -Vote for Three\n"
                   f"{CANDIDATE}\n{marker}\n{marker}")
        assert c.seats_unfilled == 2 and c.seats_unfilled_observed is True


def test_a_capitalised_marker_is_not_mistaken_for_a_heading():
    """2023 prints NO NOMINATION MADE in capitals. Reading it as a heading
    silently drops the marker and the seat looks filled."""
    (c,) = run("""
BETHLEHEM TOWNSHIP
School Board Member – 3 Yr. Term -Vote for Three
Daniel P. MacDonnell 4 Farrow Lane Asbury, NJ 08802 d@example.com
Jenny Holmes 5 Creveling Rd. Bloomsbury, NJ 08804 j@example.com
NO NOMINATION MADE
""")
    assert c.candidate_count == 2 and c.seats_unfilled == 1
    assert c.problems() == []


def test_a_contest_with_nobody_at_all():
    (c,) = run("BLOOMSBURY BOROUGH\n"
               "School Board Member- 3 Yr. Term- Vote for One\nNo Petition Filed")
    assert c.candidate_count == 0 and c.seats_unfilled == 1
    assert c.is_uncontested is True


def test_a_full_contest_records_zero_unfilled_as_observed():
    """Hunterdon prints its unfilled seats, so none printed means none — that is
    a reading, not an assumption, and must not be confused with unknown."""
    (c,) = run(f"ALEXANDRIA TOWNSHIP\n"
               f"School Board Member-3 Yr. Term-Vote for One\n{CANDIDATE}")
    assert c.seats_unfilled == 0 and c.seats_unfilled_observed is True


# --- slogans are not data -------------------------------------------------

def test_a_capitalised_slogan_does_not_end_the_contest():
    """`CHILDREN'S EDUCATION MATTERS` sits between two candidates in 2023."""
    (c,) = run("""
BETHLEHEM TOWNSHIP
School Board Member – 3 Yr. Term -Vote for Three
Daniel P. MacDonnell 4 Farrow Lane Asbury, NJ 08802 d@example.com
CHILDREN'S EDUCATION MATTERS
Jenny Holmes 5 Creveling Rd. Bloomsbury, NJ 08804 j@example.com
""")
    assert c.candidate_count == 2


def test_indented_slogans_are_ignored():
    (c,) = run(f"ALEXANDRIA TOWNSHIP\n"
               f"School Board Member-3 Yr. Term-Vote for One\n{CANDIDATE}\n"
               f"     Support Public Education")
    assert [x.name for x in c.candidates_filed] == ["Andrew Sliver"]


# --- withdrawals ----------------------------------------------------------

def test_a_withdrawal_is_kept_but_does_not_count_as_running():
    (c,) = run("ALEXANDRIA TOWNSHIP\n"
               "School Board Member-3 Yr. Term-Vote for Two\n"
               "Robert Baumgaertner 52 Hunters Cir. Lebanon, NJ 08833 r@e.com withdrew 8/18/23\n"
               "Jenny Holmes 5 Creveling Rd. Bloomsbury, NJ 08804 j@example.com")
    assert c.candidate_count == 1
    assert [(x.name, x.withdrew) for x in c.candidates_filed] \
        == [("Robert Baumgaertner", True), ("Jenny Holmes", False)]


# --- how districts nest ---------------------------------------------------

def test_a_regional_district_covers_every_town_beneath_it():
    contests = run("""
DELAWARE VALLEY REGIONAL HIGH SCHOOL
ALEXANDRIA TOWNSHP
School Board Member- 3 Yr. Term – Vote for One
Andrew Sliver 16 Northwood Dr. Pittstown, NJ 08867 a@example.com
FRENCHTOWN BOROUGH
School Board Member-3 Yr. Term-Vote for One
Thomas G. Loughlin 1 River Mills Dr., Frenchtown, NJ 08825 t@example.com
KINGWOOD TOWNSHIP
School Board Member-3 Yr. Term-Vote for One
Tanya Drake 332 County Rte 519 Stockton, NJ 08559 d@example.com
""")
    assert {c.district_name for c in contests} == {"DELAWARE VALLEY REGIONAL HIGH SCHOOL"}
    assert [c.municipality for c in contests] == [
        "ALEXANDRIA TOWNSHP", "FRENCHTOWN BOROUGH", "KINGWOOD TOWNSHIP"]


def test_in_the_local_half_a_district_covers_one_town_only():
    """Franklin Township is not part of Flemington-Raritan, and attributing it
    there is silent corruption of the kind ground rule 5 exists to prevent."""
    contests = run("""
HUNTERDON COUNTY- LOCAL DISTRICTS
FLEMINGTON-RARITAN REGIONAL SCHOOL DIST.
RARITAN TOWNSHIP
School Board Member—3 Yr. Term Vote for Three
Antoinette Hutchinson 303 Cain Rd., Flemington, NJ 08822 a@example.com
FRANKLIN TOWNSHIP
School Board Member -3 Yr. Term- Vote for Two
Jeffrey Castner 93 Sidney School Rd., Annandale, NJ 08801 j@example.com
""")
    assert [(c.municipality, c.district_name) for c in contests] == [
        ("RARITAN TOWNSHIP", "FLEMINGTON-RARITAN REGIONAL SCHOOL DIST."),
        ("FRANKLIN TOWNSHIP", None)]


def test_a_district_with_its_own_contest_does_not_reach_the_next_town():
    """Clinton Township is not part of Clinton-Glen Gardner."""
    contests = run("""
HUNTERDON COUNTY- LOCAL DISTRICTS
CLINTON -GLEN GARDNER SCHOOL DISTRICT
School Board Member– 3 Yr. Term Vote for Two
Dan Brkich 12 Alexandra Way, Clinton, NJ 08809 d@example.com
CLINTON TOWNSHIP
School Board Member- 3 Yr. Term Vote for Three
Andrew Clarke 12 Fawn Dr. Lebanon, NJ 08833 a@example.com
""")
    assert [(c.municipality, c.district_name) for c in contests] == [
        (None, "CLINTON -GLEN GARDNER SCHOOL DISTRICT"),
        ("CLINTON TOWNSHIP", None)]


def test_a_town_with_no_district_stated_gets_none_not_the_last_one_seen():
    contests = run("""
HUNTERDON COUNTY- LOCAL DISTRICTS
ALEXANDRIA TOWNSHIP
School Board Member-3 Yr. Term Vote for Three
Michael Iarkowski 12 Hilltop Rd. Milford, NJ 08848 m@example.com
""")
    assert contests[0].district_name is None


def test_a_municipality_and_its_contest_on_one_line():
    """Two 2024 lines run them together."""
    (c,) = run("HUNTERDON COUNTY- LOCAL DISTRICTS\n"
               "UNION TOWNSHIP- 3 Yr. Term- Vote for One\n" + CANDIDATE)
    assert c.municipality == "UNION TOWNSHIP" and c.seats_available == 1


# --- small pieces ---------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("Andrew Sliver 16 Northwood Dr. Pittstown, NJ 08867 a@e.com", "Andrew Sliver"),
    ("Lauren Braun-Strumfels 221 N. Union St. Lambertville, NJ 08530 d@e.com",
     "Lauren Braun-Strumfels"),
    ("Yasmin E. Hernandez-Manno 1 Woodline Way, Pittstown, NJ 08867 y@e.com",
     "Yasmin E. Hernandez-Manno"),
    ("Robert Baumgaertner 52 Hunters Cir. Lebanon, NJ 08833 r@e.com withdrew 8/18/23",
     "Robert Baumgaertner"),
])
def test_the_name_is_whatever_precedes_the_street_number(line, expected):
    assert candidate_name(line) == expected


@pytest.mark.parametrize("line,heading", [
    ("ALEXANDRIA TOWNSHP", True),
    ("DELAWARE VALLEY REGIONAL HIGH SCHOOL", True),
    ("Andrew Sliver 16 Northwood Dr. Pittstown, NJ 08867 a@e.com", False),
    ("     Support Public Education", False),
])
def test_headings_are_set_in_capitals(line, heading):
    assert is_heading(line) is heading


def test_page_numbers_are_recorded_for_provenance():
    lines = [(3, "ALEXANDRIA TOWNSHIP"),
             (3, "School Board Member-3 Yr. Term-Vote for One"),
             (3, CANDIDATE)]
    (c,) = parse(lines, year="2026", source_url="u", source_document="d.pdf")
    assert c.source_page == 3
