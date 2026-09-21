"""Atlantic's table, and the two things text extraction does to it."""

from __future__ import annotations

import pytest

from njfilings.extract.atlantic import (extract, parse, repair_districts,
                                        split_place)


def run(text: str, page: int = 1):
    return parse([(page, l.strip()) for l in text.strip("\n").splitlines()],
                 year="2026", source_url="https://clerk.example/x.pdf",
                 source_document="x.pdf")


def row(place="Absecon", term="3 yr", seats="V2", name="Paige Kuenzner",
        slogan="Education Family"):
    return (f"{place}\n{term}\n{seats}\n{name}\n1 304 SPRUCE ST\n"
            f"ABSECON NJ 08201-1726\np@example.com\n{slogan}\n")


def test_a_row_becomes_a_contest():
    (c,) = run(row())
    assert c.county == "atlantic" and c.municipality == "Absecon"
    assert (c.term_years, c.seats_available, c.is_unexpired) == (3, 2, False)
    assert [x.name for x in c.candidates_filed] == ["Paige Kuenzner"]


def test_rows_sharing_a_heading_group_into_one_contest():
    (c,) = run(row(name="Paige Kuenzner") + row(name="Eric Neal"))
    assert c.seats_available == 2 and c.candidate_count == 2


@pytest.mark.parametrize("cell,seats", [("V1", 1), ("V2", 2), ("V3", 3)])
def test_seats_are_read_from_the_v_cell(cell, seats):
    assert run(row(seats=cell))[0].seats_available == seats


def test_an_incumbent_marker_is_not_part_of_the_name():
    (c,) = run(row(name="Theresa Hudson*"))
    assert [x.name for x in c.candidates_filed] == ["Theresa Hudson"]
    (c,) = run(row(name="Donnell Holland Sr. *"))
    assert [x.name for x in c.candidates_filed] == ["Donnell Holland Sr."]


def test_an_unexpired_term_is_its_own_contest():
    contests = run(row() + row(term="1 yr Unexpired", seats="V1"))
    assert [(c.term_years, c.is_unexpired) for c in contests] == [(3, False),
                                                                  (1, True)]


def test_no_petition_filed_is_an_observed_unfilled_seat():
    empty = "Estell Manor\n3 yr\nV1\nNO PETITION FILED\n"
    (c,) = run(empty)
    assert c.candidate_count == 0
    assert c.seats_unfilled == 1 and c.seats_unfilled_observed is True


# --- the district column --------------------------------------------------

@pytest.mark.parametrize("value,municipality,district", [
    ("Absecon", "Absecon", None),
    ("Egg Harbor Township", "Egg Harbor Township", None),
    ("Northfield - Mainland Regional", "Northfield", "Mainland Regional"),
    ("Buena Borough - Buena Regional", "Buena Borough", "Buena Regional"),
])
def test_a_compound_cell_is_a_town_and_its_regional_district(
        value, municipality, district):
    assert split_place(value) == (municipality, district)


def test_a_truncated_district_is_repaired_from_the_document_itself():
    """Text extraction eats a letter when the term runs into the district cell.
    `Greater Egg Harbor Regiona` is a strict prefix of a name the same document
    prints intact elsewhere."""
    repairs = repair_districts([
        "Galloway Township - Greater Egg Harbor Regiona",
        "Mullica Township - Greater Egg Harbor Regional",
    ])
    assert repairs == {"Greater Egg Harbor Regiona": "Greater Egg Harbor Regional"}


def test_an_ambiguous_truncation_is_left_alone():
    """Repairing against two candidates would be a guess."""
    assert repair_districts([
        "A - Regional", "B - Regional North", "C - Regional South",
    ]) == {}


def test_a_term_glued_to_the_district_cell_is_split_back_off():
    """`Galloway Township - Greater Egg Harbor Regiona3 yr` is one line."""
    glued = ("Galloway Township - Greater Egg Harbor Regiona3 yr\nV1\n"
             "Ann Smith\n1 Road\nGALLOWAY NJ 08205\na@example.com\nSlogan\n")
    intact = row(place="Mullica Township - Greater Egg Harbor Regional",
                 term="3 yr", seats="V1", name="Bob Jones")
    contests = run(glued + intact)
    assert contests[0].term_years == 3
    assert contests[0].municipality == "Galloway Township"
    assert contests[0].district_name == "Greater Egg Harbor Regional"


def test_nothing_after_the_name_is_read():
    """The address, city, email and slogan merge unpredictably; none is used."""
    merged = ("Absecon\n3 yr\nV2\nTheresa Hudson*\n"
              "2 4 STONE CIR ABSECON NJ 08201-1727\n"
              "theresahudson811@yahoo.comStudent First. Always.\n")
    (c,) = run(merged)
    assert [x.name for x in c.candidates_filed] == ["Theresa Hudson"]
