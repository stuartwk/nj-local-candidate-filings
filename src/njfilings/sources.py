"""Declarative description of what each county publishes and where it lives.

This module is data, not behaviour: it resolves to a flat list of `Document`
records, each naming one URL to fetch and one place to put it. Nothing here
touches the network and nothing here parses a document. `capture.py` consumes
the list; the parsers in `scripts/` consume the cache it fills.

The three counties publish in three different shapes, and the shape is the
reason each one is modelled the way it is:

  Hunterdon  One countywide candidate list per cycle behind a stable
             `DocumentCenter/View/<id>` URL. Ids never move, so the years are
             written out literally.
  Bergen     No countywide list at all — one sample ballot per municipality per
             election. The directory, the filename suffix and the spelling of
             the municipality all change between years, so a year is a layout
             rule plus its exceptions, applied over one canonical town list.
  Essex      One countywide sample-ballot PDF per general election, under a
             filename the clerk picks fresh each cycle. Written out literally,
             because there is no convention to extrapolate from.

Every URL below was observed serving a document; none is extrapolated from a
site's navigation. Cycles that exist but whose URL is not known are recorded in
KNOWN_GAPS rather than guessed at.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

__all__ = ["Document", "CountySource", "COUNTIES", "KNOWN_GAPS", "documents"]


@dataclass(frozen=True)
class Document:
    """One fetchable document and its resting place in the cache."""

    county: str       # cache/<county>/...
    year: str
    doc_type: str     # candidate_list | seats_notice | sample_ballot
    url: str
    filename: str     # basename under cache/<county>/<year>/
    label: str = ""   # human note, e.g. the municipality; never parsed

    @property
    def local_path(self) -> str:
        return f"cache/{self.county}/{self.year}/{self.filename}"


@dataclass(frozen=True)
class CountySource:
    name: str
    label: str
    note: str
    build: Callable[[], list[Document]] = field(repr=False)


# --------------------------------------------------------------------------
# Hunterdon — countywide candidate lists, stable DocumentCenter ids
# --------------------------------------------------------------------------
# Two documents can exist per cycle: a pre-filing notice of the offices up for
# election (seats only) and a post-filing ballot draw (seats and candidates).
# Which one survives varies by year, so both are captured where both are known.

_HUNTERDON_BASE = "https://www.co.hunterdon.nj.us/DocumentCenter/View"

_HUNTERDON = [
    # year, doc_type, url path, local filename
    ("2023", "candidate_list",
     "12466/UnOfficial-School-Board-Candidates-2023-filed-candidates-PDF",
     "school-board-candidates.pdf"),
    ("2024", "candidate_list",
     "15174/UnOfficial--School-Board-Candidates-2024-PDF",
     "school-board-candidates.pdf"),
    # 2025 published both halves of the cycle.
    ("2025", "seats_notice", "17067", "seats-notice.pdf"),
    ("2025", "candidate_list",
     "17436/UnOfficial-School-Board-Candidates-2025-PDF",
     "school-board-candidates.pdf"),
    ("2026", "candidate_list",
     "20403/UnOfficial-School-Board-Candidates-2026-PDF",
     "school-board-candidates.pdf"),
]


def hunterdon_documents() -> list[Document]:
    return [
        Document("hunterdon", year, doc_type, f"{_HUNTERDON_BASE}/{path}", filename)
        for year, doc_type, path, filename in _HUNTERDON
    ]


# --------------------------------------------------------------------------
# Bergen — one sample ballot per municipality, per election
# --------------------------------------------------------------------------
# The canonical spelling is hyphenated ("Fair-Lawn"); each year's layout maps it
# onto that year's actual path. 2023 and 2024 run the parts together
# ("FairLawn"), 2025 keeps the hyphens and appends "-Gen25". The overrides below
# are towns the year's own rule gets wrong — they are observed exceptions, one
# entry per town the clerk spelled differently.

BERGEN_MUNICIPALITIES = (
    "Allendale", "Alpine", "Bergenfield", "Bogota", "Carlstadt", "Cliffside-Park",
    "Closter", "Cresskill", "Demarest", "Dumont", "East-Rutherford", "Edgewater",
    "Elmwood-Park", "Emerson", "Englewood", "Englewood-Cliffs", "Fair-Lawn",
    "Fairview", "Fort-Lee", "Franklin-Lakes", "Garfield", "Glen-Rock",
    "Hackensack", "Harrington-Park", "Hasbrouck-Heights", "Haworth", "Hillsdale",
    "Ho-Ho-Kus", "Leonia", "Little-Ferry", "Lodi", "Lyndhurst", "Mahwah",
    "Maywood", "Midland-Park", "Montvale", "Moonachie", "New-Milford",
    "North-Arlington", "Northvale", "Norwood", "Oakland", "Old-Tappan", "Oradell",
    "Palisades-Park", "Paramus", "Park-Ridge", "Ramsey", "Ridgefield",
    "Ridgefield-Park", "Ridgewood", "River-Edge", "River-Vale", "Rochelle-Park",
    "Rockleigh", "Rutherford", "Saddle-Brook", "Saddle-River", "South-Hackensack",
    "Teaneck", "Tenafly", "Teterboro", "Township-of-Washington",
    "Upper-Saddle-River", "Waldwick", "Wallington", "Westwood", "Wood-Ridge",
    "Woodcliff-Lake", "Wyckoff",
)


def _run_together(name: str) -> str:
    """2023 / 2024 convention: 'Fair-Lawn' -> 'FairLawn'."""
    return name.replace("-", "")


def _keep_hyphens(name: str) -> str:
    """2025 convention: 'Fair-Lawn' -> 'Fair-Lawn'."""
    return name


@dataclass(frozen=True)
class BergenLayout:
    """How one election year spells its sample-ballot paths."""

    directory: str
    stem: Callable[[str], str]
    suffix: str = ""
    # municipality -> the stems actually used that year. A town maps to several
    # stems when its ballot is split (Englewood is printed by ward in 2025).
    overrides: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def stems_for(self, municipality: str) -> tuple[str, ...]:
        if municipality in self.overrides:
            return self.overrides[municipality]
        return (self.stem(municipality),)


BERGEN_LAYOUTS: dict[str, BergenLayout] = {
    "2023": BergenLayout(
        directory="2023",
        stem=_run_together,
        overrides={
            # towns the run-together rule does not reach
            "Elmwood-Park": ("Elmwoodpark",),
            "South-Hackensack": ("South-Hackensack",),
            "Township-of-Washington": ("Township-of-Washington",),
            "Upper-Saddle-River": ("Upper-Saddle-River",),
            "Woodcliff-Lake": ("Woodcliff-Lake",),
        },
    ),
    "2024": BergenLayout(
        directory="2024-general",
        stem=_run_together,
        overrides={
            "Elmwood-Park": ("Elmwoodpark",),
            "South-Hackensack": ("South-Hackensack",),
            "Township-of-Washington": ("Township-of-Washington",),
            "Upper-Saddle-River": ("Upper-Saddle-River",),
            "Woodcliff-Lake": ("Woodcliff-Lake",),
        },
    ),
    "2025": BergenLayout(
        directory="2025",
        stem=_keep_hyphens,
        suffix="-Gen25",
        overrides={
            # Englewood is posted as four ward ballots in 2025, one file each.
            "Englewood": ("Englewood-W1-Gen25", "Englewood-W2-Gen25",
                          "Englewood-W3-Gen25", "Englewood-W4-Gen25"),
        },
    ),
}

_BERGEN_BASE = "https://www.bergencountyclerk.gov/_Content/pdf/voting/sample-ballots"


def bergen_documents() -> list[Document]:
    docs = []
    for year, layout in BERGEN_LAYOUTS.items():
        for municipality in BERGEN_MUNICIPALITIES:
            stems = layout.stems_for(municipality)
            for stem in stems:
                # an override supplies the whole stem; the rule needs the suffix
                if municipality not in layout.overrides:
                    stem = f"{stem}{layout.suffix}"
                url = f"{_BERGEN_BASE}/{layout.directory}/{stem}.pdf"
                # local names stay canonical so a town lines up across years,
                # however the clerk spelled it that cycle
                # a split ballot keeps the clerk's own distinguishing part
                # (W1, W2, ...); everything else keeps the canonical town name
                if len(stems) > 1:
                    local = stem[:-len(layout.suffix)].lower() if layout.suffix \
                        else stem.lower()
                else:
                    local = municipality.lower()
                docs.append(Document("bergen", year, "sample_ballot", url,
                                     f"{local}.pdf", label=municipality))
    return docs


# --------------------------------------------------------------------------
# Essex — one countywide sample-ballot PDF per general election
# --------------------------------------------------------------------------
# Filenames are reused and inconsistent between cycles, and the live site keeps
# only the current one, so older URLs are expected to 404. That is recorded in
# the manifest rather than treated as an error.

_ESSEX = [
    ("2022", "https://www.essexclerk.com/_Content/pdf/Elect%20Information/"
             "Essex-Sample-Ballots-2022g-Alphabetical.pdf"),
    ("2023", "https://www.essexclerk.com/_Content/pdf/"
             "Essex-Sample-Ballots-General-Election.pdf"),
    ("2025", "https://www.essexclerk.com/_Content/pdf/"
             "Essex-2025-General-Election-Sample-Ballots.pdf"),
    ("2026", "https://www.essexclerk.com/_Content/pdf/"
             "Essex-2026-Sample-Ballots.pdf"),
]


def essex_documents() -> list[Document]:
    return [
        Document("essex", year, "sample_ballot", url, "sample-ballots.pdf")
        for year, url in _ESSEX
    ]


COUNTIES: dict[str, CountySource] = {
    "hunterdon": CountySource(
        "hunterdon", "Hunterdon",
        "Countywide school-board candidate list, stable DocumentCenter ids.",
        hunterdon_documents),
    "bergen": CountySource(
        "bergen", "Bergen",
        "Per-municipality sample ballots; path convention changes each year.",
        bergen_documents),
    "essex": CountySource(
        "essex", "Essex",
        "One countywide sample-ballot PDF per general election.",
        essex_documents),
}


# Cycles known to exist from the inventory whose URL has not been established.
# Listed so they are visibly absent rather than silently missing; no URL here is
# a guess.
KNOWN_GAPS = [
    ("hunterdon", "2022", "'2022GeneralSchoolcandidates.pdf' — seen, "
                          "DocumentCenter id not recorded"),
    ("essex", "2017", "archived only; live URL gone"),
    ("essex", "2018", "archived only; live URL gone"),
    ("essex", "2020", "archived only; live URL gone"),
    ("essex", "2021", "no countywide PDF found"),
    ("essex", "2024", "no countywide PDF found under any filename"),
    ("bergen", "2019", "only 2 of ~70 municipalities archived"),
    ("bergen", "2020", "archived copies redirect"),
    ("bergen", "2021", "archived copies redirect"),
    ("bergen", "2022", "no captures found"),
]


def documents(counties: Iterable[str] | None = None,
              years: Iterable[str] | None = None) -> list[Document]:
    """Every declared document, optionally narrowed to counties and/or years."""
    wanted = list(counties) if counties else list(COUNTIES)
    unknown = [c for c in wanted if c not in COUNTIES]
    if unknown:
        raise KeyError(f"unknown county: {', '.join(unknown)}")
    years = set(years) if years else None
    out = []
    for name in wanted:
        for doc in COUNTIES[name].build():
            if years is None or doc.year in years:
                out.append(doc)
    return out
