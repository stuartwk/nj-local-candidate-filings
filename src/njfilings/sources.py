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

__all__ = ["Document", "CountySource", "COUNTIES", "KNOWN_GAPS",
           "documents", "archived"]


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



# --------------------------------------------------------------------------
# Atlantic — a discrete school-board candidate list, Hunterdon-class
# --------------------------------------------------------------------------
# The clerk posts candidate lists as dated WordPress uploads. The school-board
# list is its own document, which makes Atlantic one of the few counties where
# seats and filings can be read without going through a ballot.
# The general-office list is captured alongside it: it is out of the current
# school-board scope, but it is equally ephemeral and costs one small fetch.

_ATLANTIC = [
    ("2026", "candidate_list",
     "https://www.atlanticcountyclerk.org/wp-content/uploads/2026/08/"
     "Official-2026-School-Board-Candidates-List-8-13-26.pdf",
     "school-board-candidates.pdf"),
    ("2026", "candidate_list",
     "https://www.atlanticcountyclerk.org/wp-content/uploads/2026/08/"
     "Candidates-List-2026-General-8-12-26-1.pdf",
     "general-candidates.pdf"),
]


def atlantic_documents() -> list[Document]:
    return [Document("atlantic", year, doc_type, url, filename)
            for year, doc_type, url, filename in _ATLANTIC]


# --------------------------------------------------------------------------
# Burlington — one countywide sample-ballot PDF per election, with an archive
# --------------------------------------------------------------------------
# Essex-shaped (one big countywide PDF) but, unlike Essex, the clerk keeps prior
# cycles on the live site. Note the host: the DocumentCenter answers on
# co.burlington.nj.us, while the www site redirects to burlingtoncountynj.gov
# and 404s these same ids.

_BURLINGTON_BASE = "https://www.co.burlington.nj.us/DocumentCenter/View"

_BURLINGTON = [
    ("2026", "26096/Burlington-Samples-ALL-Gen26"),
    ("2025", "22581/Burlington-County-2025-General-Election-Sample-Ballots-PDF"),
]


def burlington_documents() -> list[Document]:
    return [Document("burlington", year, "sample_ballot",
                     f"{_BURLINGTON_BASE}/{path}", "sample-ballots.pdf")
            for year, path in _BURLINGTON]



# --------------------------------------------------------------------------
# Union — school-board candidate list, same shape as Atlantic
# --------------------------------------------------------------------------
# Dated WordPress uploads, "as of" the date in the filename, so the clerk may
# post a revised list later in the cycle under a new name. The captured copy is
# whatever was current when we asked; the manifest records when that was.

_UNION = [
    ("2026", "candidate_list",
     "https://unioncountyvotes.com/wp-content/uploads/2026/08/"
     "School-Board-2026-Candidate-List-8-12-26_.pdf",
     "school-board-candidates.pdf"),
    ("2026", "candidate_list",
     "https://unioncountyvotes.com/wp-content/uploads/2026/09/"
     "GENERAL-2026-CANDIDATE-LIST-9-3.pdf",
     "general-candidates.pdf"),
]


def union_documents() -> list[Document]:
    return [Document("union", year, doc_type, url, filename)
            for year, doc_type, url, filename in _UNION]



# --------------------------------------------------------------------------
# Salem — per-municipality ballots, one dated upload directory per cycle
# --------------------------------------------------------------------------
# Filenames carry a per-cycle form number (`Alloway-F01`), so the stems are
# recorded literally rather than generated: the numbering is assigned fresh each
# election and cannot be predicted from the municipality.

_SALEM_BASE = "https://salemcountyclerk.org/wp-content/uploads"

_SALEM_STEMS = {
    "2026": ("2026/08", """\
Alloway-F01
Carneys-Point-F02
Elmer-F03
Elsinboro-F04
Lower-Alloways-Creek-F05
Mannington-F06
Oldmans-F07
Penns-Grove-F08
Pennsville-F09
Pilesgrove-F10
Pittsgrove-F11
Quinton-F12
Salem-City-East-F13
Salem-City-West-F14
Upper-Pittsgrove-F15
Woodstown-F16"""),
}


def salem_documents() -> list[Document]:
    docs = []
    for year, (directory, stems) in _SALEM_STEMS.items():
        for stem in stems.split():
            municipality = stem.rsplit("-F", 1)[0]
            docs.append(Document(
                "salem", year, "sample_ballot",
                f"{_SALEM_BASE}/{directory}/{stem}_Optimized.pdf",
                f"{municipality.lower()}.pdf", label=municipality))
    return docs


# --------------------------------------------------------------------------
# Gloucester — one ballot per voting district, behind opaque DocumentCenter ids
# --------------------------------------------------------------------------
# The finest granularity of any county so far: 229 ballots, one per district
# rather than per municipality. The ids are arbitrary integers with no derivable
# relationship to the district, so the mapping is recorded verbatim as
# `<id> <slug>` pairs — regenerate it by re-reading the clerk's index page.
#
# These are the UOCAVA (overseas and military) ballots, the only set the clerk
# publishes as documents. One was opened to confirm the school elections survive
# on them: it carries a `BOARD OF EDUCATION` contest with `VOTE FOR` stated.

_GLOUCESTER_BASE = "https://www.gloucestercountynj.gov/DocumentCenter/View"

_GLOUCESTER = {
    "2026": ("UOCAVA-GENERAL-26", """\
19494 West-Deptford-Township-District-2
19495 West-Deptford-Township-District-3
19496 West-Deptford-Township-District-4
19497 West-Deptford-Township-District-5
19498 West-Deptford-Township-District-6
19499 West-Deptford-Township-District-7
19500 West-Deptford-Township-District-8
19501 West-Deptford-Township-District-9
19502 West-Deptford-Township-District-17
19503 West-Deptford-Township-District-18
19504 West-Deptford-Township-District-19
19505 West-Deptford-Township-District-1
19506 West-Deptford-Township-District-10
19507 West-Deptford-Township-District-11
19508 West-Deptford-Township-District-12
19509 West-Deptford-Township-District-13
19510 West-Deptford-Township-District-14
19511 West-Deptford-Township-District-15
19512 West-Deptford-Township-District-16
19513 Westville-Borough-District-1
19514 Westville-Borough-District-2
19515 Westville-Borough-District-3
19516 Woodbury-Heights-Borough-District-1
19517 Woodbury-Heights-Borough-District-2
19518 Woodbury-Heights-Borough-District-3
19519 Woodbury-Heights-Borough-District-4
19520 Woodbury-City-Ward-1-District-1
19521 Woodbury-City-Ward-1-District-2
19522 Woodbury-City-Ward-1-District-3
19523 Woodbury-City-Ward-2-District-1
19524 Woodbury-City-Ward-2-District-2
19525 Woodbury-City-Ward-2-District-3
19526 Woodbury-City-Ward-3-District-1
19527 Woodbury-City-Ward-3-District-2
19528 Woodbury-City-Ward-3-District-3
19529 Woodbury-City-Ward-3-District-4
19530 Woolwich-Township-District-1
19531 Woolwich-Township-District-2
19532 Woolwich-Township-District-3
19533 Woolwich-Township-District-4
19534 Woolwich-Township-District-5
19535 Woolwich-Township-District-6
19536 Woolwich-Township-District-7
19537 Woolwich-Township-District-8
19538 Monroe-Township-Ward-4-District-3
19539 Monroe-Township-Ward-4-District-4
19540 Monroe-Township-Ward-4-District-5
19541 Monroe-Township-Ward-4-District-8
19542 Monroe-Township-Ward-4-District-11
19543 Monroe-Township-Ward-4-District-15
19544 Monroe-Township-Ward-4-District-21
19545 Monroe-Township-Ward-4-District-25
19546 National-Park-Borough-District-1
19547 National-Park-Borough-District-2
19548 National-Park-Borough-District-3
19549 National-Park-Borough-District-4
19550 Newfield-Borough-District-1
19551 Paulsboro-Borough-District-1
19552 Paulsboro-Borough-District-2
19553 Paulsboro-Borough-District-3
19554 Paulsboro-Borough-District-4
19555 Paulsboro-Borough-District-5
19556 Pitman-Borough-District-1
19557 Pitman-Borough-District-2
19558 Pitman-Borough-District-3
19559 Pitman-Borough-District-4
19560 Pitman-Borough-District-5
19561 Pitman-Borough-District-6
19562 Pitman-Borough-District-7
19563 South-Harrison-Township-District-1
19564 South-Harrison-Township-District-2
19565 South-Harrison-Township-District-3
19566 Swedesboro-Borough-District-1
19567 Swedesboro-Borough-District-2
19568 Washington-Township-District-1
19569 Washington-Township-District-2
19570 Washington-Township-District-3
19571 Washington-Township-District-4
19572 Washington-Township-District-5
19573 Washington-Township-District-6
19574 Washington-Township-District-7
19575 Washington-Township-District-8
19576 Washington-Township-District-9
19577 Washington-Township-District-10
19578 Washington-Township-District-11
19579 Washington-Township-District-12
19580 Washington-Township-District-13
19581 Washington-Township-District-14
19582 Washington-Township-District-15
19583 Washington-Township-District-16
19584 Washington-Township-District-17
19585 Washington-Township-District-18
19586 Washington-Township-District-19
19587 Washington-Township-District-20
19588 Washington-Township-District-21
19589 Washington-Township-District-22
19590 Washington-Township-District-23
19591 Washington-Township-District-24
19592 Washington-Township-District-25
19593 Washington-Township-District-26
19594 Washington-Township-District-27
19595 Washington-Township-District-28
19596 Washington-Township-District-29
19597 Washington-Township-District-30
19598 Washington-Township-District-31
19599 Washington-Township-District-32
19600 Washington-Township-District-33
19601 Washington-Township-District-34
19602 Washington-Township-District-35
19603 Washington-Township-District-36
19604 Washington-Township-District-37
19605 Washington-Township-District-38
19606 Washington-Township-District-39
19607 Wenonah-Borough-District-1
19608 Wenonah-Borough-District-2
19609 Wenonah-Borough-District-3
19610 East-Greenwich-Township-District-4
19611 East-Greenwich-Township-District-5
19612 East-Greenwich-Township-District-6
19613 East-Greenwich-Township-District-7
19614 East-Greenwich-Township-District-8
19615 East-Greenwich-Township-District-1
19616 East-Greenwich-Township-District-2
19617 East-Greenwich-Township-District-3
19618 Elk-Township-District-1
19619 Elk-Township-District-2
19620 Elk-Township-District-3
19621 Elk-Township-District-4
19622 Franklin-Township-District-1
19623 Franklin-Township-District-2
19624 Franklin-Township-District-3
19625 Franklin-Township-District-4
19626 Franklin-Township-District-5
19627 Franklin-Township-District-6
19628 Franklin-Township-District-7
19629 Franklin-Township-District-8
19630 Franklin-Township-District-9
19631 Franklin-Township-District-10
19632 Franklin-Township-District-11
19633 Glassboro-Borough-District-1
19634 Glassboro-Borough-District-2
19635 Glassboro-Borough-District-3
19636 Glassboro-Borough-District-4
19637 Glassboro-Borough-District-5
19638 Glassboro-Borough-District-6
19639 Glassboro-Borough-District-7
19640 Glassboro-Borough-District-8
19641 Glassboro-Borough-District-9
19642 Glassboro-Borough-District-10
19643 Glassboro-Borough-District-11
19644 Glassboro-Borough-District-12
19645 Glassboro-Borough-District-13
19646 Greenwich-Township-District-1
19647 Greenwich-Township-District-2
19648 Greenwich-Township-District-3
19649 Greenwich-Township-District-4
19650 Greenwich-Township-District-5
19651 Greenwich-Township-District-6
19652 Harrison-Township-District-1
19653 Harrison-Township-District-2
19654 Harrison-Township-District-3
19655 Harrison-Township-District-4
19656 Harrison-Township-District-5
19657 Harrison-Township-District-6
19658 Harrison-Township-District-7
19659 Harrison-Township-District-8
19660 Harrison-Township-District-9
19661 Logan-Township-District-1
19662 Logan-Township-District-2
19663 Logan-Township-District-3
19664 Logan-Township-District-4
19665 Mantua-Township-District-1
19666 Mantua-Township-District-2
19667 Mantua-Township-District-3
19668 Mantua-Township-District-4
19669 Mantua-Township-District-5
19670 Mantua-Township-District-6
19671 Mantua-Township-District-7
19672 Mantua-Township-District-8
19673 Mantua-Township-District-9
19674 Mantua-Township-District-10
19675 Mantua-Township-District-11
19676 Mantua-Township-District-12
19677 Monroe-Township-Ward-1-District-7
19678 Monroe-Township-Ward-1-District-17
19679 Monroe-Township-Ward-1-District-22
19680 Monroe-Township-Ward-1-District-23
19681 Monroe-Township-Ward-1-District-24
19682 Monroe-Township-Ward-2-District-1
19683 Monroe-Township-Ward-2-District-9
19684 Monroe-Township-Ward-2-District-10
19685 Monroe-Township-Ward-2-District-13
19686 Monroe-Township-Ward-2-District-14
19687 Monroe-Township-Ward-2-District-16
19688 Monroe-Township-Ward-2-District-20
19689 Monroe-Township-Ward-3-District-6
19690 Monroe-Township-Ward-3-District-2
19691 Monroe-Township-Ward-3-District-12
19692 Monroe-Township-Ward-3-District-18
19693 Monroe-Township-Ward-3-District-19
19694 Monroe-Township-Ward-3-District-26
19695 Clayton-Borough-District-1
19696 Clayton-Borough-District-2
19697 Clayton-Borough-District-3
19698 Clayton-Borough-District-4
19699 Clayton-Borough-District-5
19700 Clayton-Borough-District-6
19701 Deptford-Township-District-1
19702 Deptford-Township-District-2
19703 Deptford-Township-District-3
19704 Deptford-Township-District-4
19705 Deptford-Township-District-5
19706 Deptford-Township-District-6
19707 Deptford-Township-District-7
19708 Deptford-Township-District-8
19709 Deptford-Township-District-9
19710 Deptford-Township-District-10
19711 Deptford-Township-District-11
19712 Deptford-Township-District-12
19713 Deptford-Township-District-13
19714 Deptford-Township-District-14
19715 Deptford-Township-District-15
19716 Deptford-Township-District-16
19717 Deptford-Township-District-17
19718 Deptford-Township-District-18
19719 Deptford-Township-District-19
19720 Deptford-Township-District-20
19721 Deptford-Township-District-21
19722 Deptford-Township-District-22"""),
}


def gloucester_documents() -> list[Document]:
    docs = []
    for year, (suffix, table) in _GLOUCESTER.items():
        for line in table.strip().splitlines():
            doc_id, slug = line.split(" ", 1)
            docs.append(Document(
                "gloucester", year, "sample_ballot",
                f"{_GLOUCESTER_BASE}/{doc_id}/{slug}-{suffix}",
                f"{slug.lower()}.pdf", label=slug.replace("-", " ")))
    return docs


# --------------------------------------------------------------------------
# Fetching through the Internet Archive
# --------------------------------------------------------------------------
# Eleven of the twenty-one county sites refuse HTTP clients outright — Akamai
# and Cloudflare answer 403, and three AWS-fronted sites answer 202 with an
# empty body. The refusal is not User-Agent based: a current browser UA is
# turned away identically, so no client we can write will get through.
#
# The Internet Archive crawled most of those hosts before they were locked down,
# and archive.org serves us happily. The `id_` modifier asks Wayback for the
# original bytes rather than its rewritten page, so what lands in the cache is
# byte-for-byte what the clerk published.
#
# The manifest records the URL we actually requested — the Wayback one, because
# that is the honest provenance of those bytes — and carries the clerk's own URL
# alongside it in the note.

WAYBACK = "https://web.archive.org/web/{timestamp}id_/{url}"


def archived(county: str, year: str, doc_type: str, timestamp: str,
             url: str, filename: str) -> Document:
    """A document obtained through the Internet Archive rather than from the
    county, because the county's host refuses us. `timestamp` is the Wayback
    capture to pin to; without one, Wayback resolves to "latest", which would
    make the fetch non-reproducible."""
    return Document(county, year, doc_type,
                    WAYBACK.format(timestamp=timestamp, url=url), filename,
                    label=f"via web.archive.org; original: {url}")


# --------------------------------------------------------------------------
# Morris — school-board candidate list, six cycles, all through the Archive
# --------------------------------------------------------------------------
# The best single source found in the state. A two-page text PDF with one row
# per candidate and explicit columns:
#
#   Municipality | CONTEST TITLE | Term (Yrs) | Vote For | District | Name | ...
#
# Seats are stated in their own column, unexpired terms are labelled, and seats
# that drew nobody print `NO PETITION` — so unfilled seats are observed, not
# arithmetic. 2021-2026 are archived, deeper than any county we can reach
# directly. The live 2026 file (082126) is a few days newer than the archived
# one (081726) but sits behind the Akamai block.

_MORRIS_BASE = "https://www.morriscountyclerk.org/files/sharedassets/clerk"

_MORRIS = [
    # year, wayback timestamp, path under the clerk's asset tree
    ("2021", "20230923004419", "v/4/elections/past-results/2021-general-school-candidates.pdf"),
    ("2022", "20230923012636", "v/19/elections/past-results/2022-general-school-candidates.pdf"),
    ("2023", "20240221043227", "v/22/elections/past-results/2023-general-school-candidates.pdf"),
    ("2024", "20250903213218", "v/16/elections/past-results/2024-general-school-candidates.pdf"),
    ("2025", "20260709224018", "v/20/elections/past-results/2025-general-school-candidates.pdf"),
    ("2026", "20260819210457", "v/13/elections/past-results/2026-general-school-candidates-081726.pdf"),
]


def morris_documents() -> list[Document]:
    return [archived("morris", year, "candidate_list", timestamp,
                     f"{_MORRIS_BASE}/{path}", "school-board-candidates.pdf")
            for year, timestamp, path in _MORRIS]


# --------------------------------------------------------------------------
# Cape May — countywide sample ballots, through the Archive
# --------------------------------------------------------------------------
# The clerk's site answers 202 with an empty body (a JS challenge), so the live
# 2024/2025/2026 documents are out of reach. The Archive holds the 2022 and 2023
# general-election ballots, which are single countywide PDFs like Essex's.
# Filenames are freeform and change every cycle, so these are literal.

_CAPE_MAY_BASE = "https://www.capemaycountyvotes.com/wp-content/uploads"

_CAPE_MAY = [
    ("2022", "20221104130109", "2022/10/22-Sample-General-CM-Web-Final.pdf"),
    ("2023", "20231101094436", "2023/10/23-Sample-General-CM_Sample-Proof-v2-FINAL.pdf"),
]


def cape_may_documents() -> list[Document]:
    return [archived("cape-may", year, "sample_ballot", timestamp,
                     f"{_CAPE_MAY_BASE}/{path}", "sample-ballots.pdf")
            for year, timestamp, path in _CAPE_MAY]


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
    "atlantic": CountySource(
        "atlantic", "Atlantic",
        "Discrete school-board candidate list, posted as a dated upload.",
        atlantic_documents),
    "burlington": CountySource(
        "burlington", "Burlington",
        "One countywide sample-ballot PDF per election; prior cycles retained.",
        burlington_documents),
    "union": CountySource(
        "union", "Union",
        "Discrete school-board candidate list, dated upload.",
        union_documents),
    "salem": CountySource(
        "salem", "Salem",
        "Per-municipality ballots; form numbers reassigned each cycle.",
        salem_documents),
    "gloucester": CountySource(
        "gloucester", "Gloucester",
        "One UOCAVA ballot per voting district, 229 per cycle.",
        gloucester_documents),
    "morris": CountySource(
        "morris", "Morris",
        "School-board candidate list, 2021-2026; reached via the Archive.",
        morris_documents),
    "cape-may": CountySource(
        "cape-may", "Cape May",
        "Countywide sample ballots, 2022-2023; reached via the Archive.",
        cape_may_documents),
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
