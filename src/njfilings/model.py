"""One record per contest, and the rules about what may and may not be inferred.

This module holds no parsing. It exists so that every county extractor produces
the same shape, and so that the two derivations this project allows — how many
candidates are running, and how many seats nobody filed for — happen in exactly
one place, under rules a reader can check.

The rules, restated from the build plan because this is where they bite:

  * Seats are read, never derived. If a document does not state how many seats a
    contest fills, `seats_available` is None and everything downstream of it is
    None too. A contest with one candidate is not thereby a one-seat contest.
  * A district nobody stated is None, not the last district seen. Extractors
    must never carry state forward implicitly; this type has no way to express
    "same as above" precisely so that nobody is tempted.
  * Where a document prints its unfilled seats — `No Nomination Made`,
    `NO PETITION FILED` — that count is preferred over arithmetic, and
    `seats_unfilled_observed` says which one you got. A rate mixing observed and
    derived figures without saying so is a misleading rate.
  * Every record carries where it came from, down to the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

__all__ = ["Candidate", "Contest", "CSV_FIELDS", "sort_key"]


@dataclass(frozen=True)
class Candidate:
    """One filing. `withdrew` matters because some counties annotate
    withdrawals rather than removing the candidate, and a withdrawn candidate
    is not running."""

    name: str
    withdrew: bool = False

    def __str__(self) -> str:
        return f"{self.name} [withdrew]" if self.withdrew else self.name


@dataclass(frozen=True)
class Contest:
    """One race: a set of seats, and whoever filed for them."""

    # where and when
    county: str
    year: str
    election_type: str                 # general | school | special

    # what the contest is
    municipality: str | None
    district_name: str | None          # None when the document does not say
    office: str
    term_years: int | None
    is_unexpired: bool

    # the numbers
    seats_available: int | None
    candidates_filed: tuple[Candidate, ...] = ()
    # what the document printed for seats nobody filed for, if it printed one
    seats_unfilled_stated: int | None = None

    # provenance — every record, always
    source_url: str = ""
    source_document: str = ""
    source_page: int | None = None
    # other pages this same contest was printed on (shared regional districts,
    # a town split across wards); kept so a merge never loses a citation
    also_on: tuple[str, ...] = field(default_factory=tuple)

    # --- the only two derivations this project permits -------------------

    @property
    def candidate_count(self) -> int:
        """Candidates actually running. Withdrawals do not count."""
        return sum(1 for c in self.candidates_filed if not c.withdrew)

    @property
    def is_uncontested(self) -> bool | None:
        """Candidates <= seats. Two candidates for three seats is uncontested
        *and* under-filled; both are true at once and neither is an error."""
        if self.seats_available is None:
            return None
        return self.candidate_count <= self.seats_available

    @property
    def seats_unfilled(self) -> int | None:
        """Seats that drew nobody.

        Prefers the document's own count where it printed one. Falls back to
        arithmetic only when seats are known. Returns None rather than guessing.
        """
        if self.seats_unfilled_stated is not None:
            return self.seats_unfilled_stated
        if self.seats_available is None:
            return None
        return max(0, self.seats_available - self.candidate_count)

    @property
    def seats_unfilled_observed(self) -> bool | None:
        """True when `seats_unfilled` was read off the page, False when it was
        computed, None when it is unknown. Never publish a rate over a mix of
        the first two without saying so."""
        if self.seats_unfilled_stated is not None:
            return True
        if self.seats_available is None:
            return None
        return False

    # --- coherence -------------------------------------------------------

    def problems(self) -> list[str]:
        """Complaints about this record, for the validation arms in 3.4.

        These are not exceptions: a contest can be odd and still be true, and
        the point is to put a human in front of the odd ones rather than to
        drop them. An empty list means nothing looked wrong, not that the record
        is correct.
        """
        issues = []
        if self.seats_available is not None and self.seats_available <= 0:
            issues.append(f"seats_available is {self.seats_available}")
        if self.term_years is not None and not 1 <= self.term_years <= 6:
            issues.append(f"term_years is {self.term_years}")
        if not self.source_url:
            issues.append("no source_url")
        if not self.office:
            issues.append("no office")

        names = [c.name.strip().upper() for c in self.candidates_filed]
        if any(not n for n in names):
            issues.append("a candidate has no name")
        if len(set(names)) != len(names):
            issues.append("the same candidate is filed twice")

        # a stated count and the arithmetic disagreeing means one of them is
        # wrong, and it is usually the parse
        if self.seats_unfilled_stated is not None and self.seats_available is not None:
            derived = max(0, self.seats_available - self.candidate_count)
            if derived != self.seats_unfilled_stated:
                issues.append(
                    f"document states {self.seats_unfilled_stated} unfilled but "
                    f"{self.seats_available} seats minus {self.candidate_count} "
                    f"candidates gives {derived}")
        if (self.seats_available is not None
                and self.candidate_count > self.seats_available
                and self.seats_unfilled_stated):
            issues.append("more candidates than seats, yet seats are unfilled")
        return issues

    def merged_with(self, other: Contest) -> Contest:
        """Absorb a duplicate printing of the same contest, keeping its page as
        provenance. One race can appear on several ballots — the wards of one
        town, or two towns sharing a regional district."""
        citation = f"{other.source_document}#p{other.source_page}"
        if other.municipality and other.municipality != self.municipality:
            citation += f" ({other.municipality})"
        return replace(self, also_on=self.also_on + (citation,))


# Fixed column order. Changing this changes every row of every diff, so it
# changes only when the schema does.
CSV_FIELDS = [
    "county", "year", "election_type", "municipality", "district_name",
    "office", "term_years", "is_unexpired",
    "seats_available", "candidates_filed", "candidate_count",
    "is_uncontested", "seats_unfilled", "seats_unfilled_observed",
    "source_url", "source_document", "source_page", "also_on",
]


def to_row(contest: Contest) -> dict[str, str]:
    """A Contest as CSV cells. None becomes empty — an absent value must not
    read as a zero or a False."""
    def cell(value: object) -> str:
        return "" if value is None else str(value)

    return {
        "county": contest.county,
        "year": contest.year,
        "election_type": contest.election_type,
        "municipality": cell(contest.municipality),
        "district_name": cell(contest.district_name),
        "office": contest.office,
        "term_years": cell(contest.term_years),
        "is_unexpired": str(contest.is_unexpired),
        "seats_available": cell(contest.seats_available),
        "candidates_filed": "; ".join(str(c) for c in contest.candidates_filed),
        "candidate_count": str(contest.candidate_count),
        "is_uncontested": cell(contest.is_uncontested),
        "seats_unfilled": cell(contest.seats_unfilled),
        "seats_unfilled_observed": cell(contest.seats_unfilled_observed),
        "source_url": contest.source_url,
        "source_document": contest.source_document,
        "source_page": cell(contest.source_page),
        "also_on": " | ".join(contest.also_on),
    }


def sort_key(contest: Contest) -> tuple:
    """Deterministic order (build plan 3.3) so a git diff shows real changes
    rather than reshuffled rows. None sorts before any string."""
    return (
        contest.county,
        contest.year,
        contest.municipality or "",
        contest.district_name or "",
        contest.is_unexpired,
        contest.office,
        contest.source_page or 0,
    )
