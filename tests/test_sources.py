"""The URL conventions are the fragile part of `sources.py`.

Bergen respells its municipalities and moves its directories every cycle, so the
tests that matter are the ones pinning generated URLs to paths the Internet
Archive actually saw return 200. The fixture is that evidence.
"""

from __future__ import annotations

import collections
import csv
from pathlib import Path

import pytest

from njfilings import sources

FIXTURES = Path(__file__).parent / "fixtures"

# 2023 and 2024 use different directories for the same election-year key
BERGEN_DIRECTORY = {"2023": "2023", "2024": "2024-general", "2025": "2025"}


@pytest.fixture(scope="module")
def archived_stems() -> dict[str, set[str]]:
    stems: dict[str, set[str]] = collections.defaultdict(set)
    with (FIXTURES / "bergen_archived_stems.csv").open(newline="") as fh:
        for row in csv.DictReader(fh):
            stems[row["directory"]].add(row["stem"])
    return stems


# --- shape ---------------------------------------------------------------

def test_every_document_is_fully_specified():
    for doc in sources.documents():
        assert doc.url.startswith("https://"), doc
        assert doc.filename.endswith(".pdf"), doc
        assert doc.county in sources.COUNTIES, doc
        assert doc.year.isdigit() and len(doc.year) == 4, doc
        assert doc.doc_type in {"candidate_list", "seats_notice",
                                "sample_ballot"}, doc


def test_local_path_follows_the_cache_convention():
    for doc in sources.documents():
        assert doc.local_path == \
            f"cache/{doc.county}/{doc.year}/{doc.filename}"


def test_no_two_documents_claim_the_same_local_path():
    """A collision would have one document silently overwrite another — the
    2025 Englewood ward ballots are the case that nearly caused it."""
    paths = [doc.local_path for doc in sources.documents()]
    duplicates = [p for p, n in collections.Counter(paths).items() if n > 1]
    assert duplicates == []


def test_no_two_documents_share_a_url():
    urls = [doc.url for doc in sources.documents()]
    duplicates = [u for u, n in collections.Counter(urls).items() if n > 1]
    assert duplicates == []


# --- Bergen: the conventions that change every year ----------------------

def test_bergen_urls_match_paths_the_archive_observed(archived_stems):
    """Every generated Bergen URL should be one a server answered, with one
    documented exception: Englewood Cliffs 2023 follows the year's rule but was
    never archived (the 2023 archive covers 69 of ~70 towns)."""
    unmatched = []
    for doc in sources.documents(["bergen"]):
        stem = doc.url.rsplit("/", 1)[1][: -len(".pdf")]
        if stem not in archived_stems[BERGEN_DIRECTORY[doc.year]]:
            unmatched.append((doc.year, stem))
    assert unmatched == [("2023", "EnglewoodCliffs")]


@pytest.mark.parametrize("year,municipality,expected", [
    # the run-together years
    ("2023", "Fair-Lawn", ".../2023/FairLawn.pdf"),
    ("2024", "Fair-Lawn", ".../2024-general/FairLawn.pdf"),
    ("2023", "Ho-Ho-Kus", ".../2023/HoHoKus.pdf"),
    # towns the run-together rule does not reach
    ("2023", "Elmwood-Park", ".../2023/Elmwoodpark.pdf"),
    ("2024", "Township-of-Washington", ".../2024-general/Township-of-Washington.pdf"),
    ("2023", "Woodcliff-Lake", ".../2023/Woodcliff-Lake.pdf"),
    # the hyphens-plus-suffix year
    ("2025", "Fair-Lawn", ".../2025/Fair-Lawn-Gen25.pdf"),
    ("2025", "Township-of-Washington", ".../2025/Township-of-Washington-Gen25.pdf"),
])
def test_bergen_spelling_per_year(year, municipality, expected):
    urls = [d.url for d in sources.documents(["bergen"], [year])
            if d.label == municipality]
    assert [u.replace(sources._BERGEN_BASE, "...") for u in urls] == [expected]


def test_bergen_splits_englewood_into_wards_in_2025_only():
    def englewood(year):
        return sorted(d.local_path for d in sources.documents(["bergen"], [year])
                      if d.label == "Englewood")

    assert englewood("2023") == ["cache/bergen/2023/englewood.pdf"]
    assert englewood("2025") == [f"cache/bergen/2025/englewood-w{n}.pdf"
                                 for n in (1, 2, 3, 4)]


def test_bergen_covers_every_municipality_every_year():
    for year in sources.BERGEN_LAYOUTS:
        covered = {d.label for d in sources.documents(["bergen"], [year])}
        assert covered == set(sources.BERGEN_MUNICIPALITIES)


# --- the literal counties ------------------------------------------------

def test_hunterdon_captures_both_halves_of_the_2025_cycle():
    """2025 published a seats-only notice in May and a ballot draw in August;
    they are different documents and must not collide."""
    docs = sources.documents(["hunterdon"], ["2025"])
    assert {d.doc_type for d in docs} == {"seats_notice", "candidate_list"}
    assert len({d.local_path for d in docs}) == 2


def test_hunterdon_urls_are_document_center_ids():
    for doc in sources.documents(["hunterdon"]):
        assert "/DocumentCenter/View/" in doc.url


def test_essex_is_one_countywide_document_per_year():
    docs = sources.documents(["essex"])
    years = [d.year for d in docs]
    assert years == sorted(set(years))       # exactly one per year
    assert all(d.filename == "sample-ballots.pdf" for d in docs)


# --- selection and gaps --------------------------------------------------

def test_documents_filters_by_county_and_year():
    docs = sources.documents(["bergen"], ["2025"])
    assert docs and all(d.county == "bergen" and d.year == "2025" for d in docs)


def test_unknown_county_is_refused():
    with pytest.raises(KeyError):
        sources.documents(["camden"])


def test_gaps_name_only_cycles_that_are_not_declared():
    """A gap is a cycle we cannot fetch. If one ever becomes fetchable the
    entry has to move, and this is what notices."""
    declared = {(d.county, d.year) for d in sources.documents()}
    for county, year, _note in sources.KNOWN_GAPS:
        assert (county, year) not in declared
