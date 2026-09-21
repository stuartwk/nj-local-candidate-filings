"""Salem's ballots — the project's first, where a name is known by its typeface."""

from __future__ import annotations

import pytest

from njfilings.extract.salem import municipality_of, parse_page

SECTION = """\
OFFICIAL SCHOOL ELECTION
ELECCIÓN OFICIAL DE LA ESCUELA
Alloway School Board
3 Year Term - Vote for Three
Junta de Educación
de Alloway
Término de 3 Años - Votar por Tres
Richard C. MORRIS, Jr.
NO PETITION FILED
NO PETITION FILED
write-in vote / por escrito
write-in vote / por escrito
write-in vote / por escrito
Alloway - District 1
Form 1
"""


def run(text, names, page=1):
    lines = [l.strip() for l in text.strip("\n").splitlines() if l.strip()]
    return parse_page(lines, set(names), year="2026", page_number=page,
                      source_url="https://clerk.example/x.pdf",
                      source_document="x.pdf")


def test_the_school_section_becomes_a_contest():
    (c,) = run(SECTION, {"Richard C. MORRIS, Jr."})
    assert c.county == "salem" and c.municipality == "Alloway"
    assert c.district_name == "Alloway School Board"
    assert (c.term_years, c.seats_available) == (3, 3)
    assert [x.name for x in c.candidates_filed] == ["Richard C. MORRIS, Jr."]
    assert c.seats_unfilled == 2 and c.seats_unfilled_observed is True


def test_only_the_school_section_is_read():
    """The municipal contests above it use the same wording and print their own
    unfilled-seat markers."""
    municipal = """\
Alloway
Township Committee
3 Year Term - Vote for One
Chuck ANGELUS
NO NOMINATION MADE
write-in vote / por escrito
"""
    (c,) = run(municipal + SECTION, {"Richard C. MORRIS, Jr.", "Chuck ANGELUS"})
    assert c.seats_available == 3          # not the Township Committee's one
    assert [x.name for x in c.candidates_filed] == ["Richard C. MORRIS, Jr."]
    assert c.seats_unfilled == 2           # not three


# --- typography decides who is a person -----------------------------------

def test_a_slogan_is_not_a_candidate():
    text = SECTION.replace("Richard C. MORRIS, Jr.\n",
                           "Michael TINSLEY\nServe. Unite. Transform.\n")
    (c,) = run(text, {"Michael TINSLEY"})
    assert [x.name for x in c.candidates_filed] == ["Michael TINSLEY"]


@pytest.mark.parametrize("name", ["Loretta LaROY", "Dennis McCARRON",
                                  "Jeanna DuBOIS"])
def test_a_surname_with_a_lowercase_letter_is_still_a_name(name):
    """These three are why the rule is typographic. A text rule looking for an
    all-capital surname drops them silently, and the seat looks contested by
    fewer people than it was."""
    text = SECTION.replace("Richard C. MORRIS, Jr.", name)
    (c,) = run(text, {name})
    assert [x.name for x in c.candidates_filed] == [name]


def test_a_line_the_ballot_does_not_set_as_a_name_is_not_one():
    """The set comes from the PDF's fonts; nothing else may add to it."""
    (c,) = run(SECTION, set())
    assert c.candidate_count == 0
    assert c.seats_unfilled == 2          # the markers are still read


# --- the ballot names its own municipality --------------------------------

@pytest.mark.parametrize("footer,expected", [
    ("Alloway - District 1", "Alloway"),
    ("Lower Alloways Creek - District 1", "Lower Alloways Creek"),
    ("Salem City - East Ward - District 1", "Salem City"),
    ("Salem City - West Ward - District 1", "Salem City"),
])
def test_the_municipality_comes_from_the_footer(footer, expected):
    assert municipality_of(["something", footer, "Form 1"]) == expected


def test_a_district_title_split_over_two_lines_is_rejoined():
    text = SECTION.replace("Alloway School Board",
                           "Penns Grove/Carneys Point\nSchool Board")
    (c,) = run(text, {"Richard C. MORRIS, Jr."})
    assert c.district_name == "Penns Grove/Carneys Point School Board"


def test_a_ballot_with_no_school_election_yields_nothing():
    assert run("Alloway\nTownship Committee\n3 Year Term - Vote for One\n"
               "Chuck ANGELUS\nAlloway - District 1", {"Chuck ANGELUS"}) == []
