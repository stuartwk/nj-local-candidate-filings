"""What the dataset covers, what it does not, and why (build plan 4.1).

The point of this module is that **a rate is only as honest as its
denominator**. `data/races.csv` says what was read; it cannot say what was never
captured, never published, or captured and not yet parsed. Publishing
candidates-per-seat without that distinction would quietly imply the dataset
covers New Jersey, when it covers four counties out of twenty-one.

So every county-year gets a cell with one of these states, and rates are
computed over `complete` cells and nothing else:

    complete        contests extracted from the documents held
    unread-format   documents held, an extractor exists, this era is unhandled
    no-extractor    documents held, nobody has written this county's parser
    not-captured    documents declared, none on disk
    gap             no document known to exist, or none reachable

The first is data. The rest are all reasons, and each cell carries its own.

`seats_unfilled_observed` matters here too. A county that prints its unfilled
seats and one that requires subtracting are not the same measurement, and mixing
them without saying so is the failure this column exists to prevent — so the
summary reports how much of each cell is observed.
"""

from __future__ import annotations

import argparse
import collections
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from .build import EXTRACTORS, build
from .capture import PROJECT_ROOT
from .model import Contest
from .sources import KNOWN_GAPS, documents

COVERAGE_FIELDS = [
    "county", "year", "status", "documents_declared", "documents_held",
    "contests", "seats", "candidates", "seats_unfilled",
    "candidates_per_seat", "uncontested_rate", "unfilled_observed", "reason",
]


@dataclass
class Cell:
    county: str
    year: str
    status: str
    declared: int
    held: int
    contests: list[Contest]
    reason: str = ""

    @property
    def seats(self) -> int:
        return sum(c.seats_available for c in self.contests
                   if c.seats_available is not None)

    @property
    def candidates(self) -> int:
        return sum(c.candidate_count for c in self.contests
                   if c.seats_available is not None)

    @property
    def unfilled(self) -> int:
        return sum(c.seats_unfilled or 0 for c in self.contests
                   if c.seats_available is not None)

    @property
    def candidates_per_seat(self) -> float | None:
        """The headline measure: a ratio of two sums, which is why it survives
        the odd parsing error that a per-contest rate would not."""
        return self.candidates / self.seats if self.seats else None

    @property
    def uncontested_rate(self) -> float | None:
        """Secondary, and more fragile: one contest misparsed moves it, where
        candidates-per-seat barely notices."""
        known = [c for c in self.contests if c.is_uncontested is not None]
        if not known:
            return None
        return sum(1 for c in known if c.is_uncontested) / len(known)

    @property
    def unfilled_observed(self) -> str:
        """Whether unfilled seats were read off the page or subtracted."""
        flags = {c.seats_unfilled_observed for c in self.contests
                 if c.seats_unfilled_observed is not None}
        if not flags:
            return ""
        if flags == {True}:
            return "all"
        return "none" if flags == {False} else "mixed"


def matrix(root: Path = PROJECT_ROOT) -> list[Cell]:
    contests = build(root=root, verbose=False)
    by_cell: dict[tuple[str, str], list[Contest]] = collections.defaultdict(list)
    for contest in contests:
        by_cell[(contest.county, contest.year)].append(contest)

    declared: dict[tuple[str, str], list] = collections.defaultdict(list)
    for doc in documents():
        if doc.school_board:
            declared[(doc.county, doc.year)].append(doc)

    cells = []
    for key in sorted(set(declared) | set(by_cell)):
        docs = declared.get(key, [])
        held = [d for d in docs if (root / d.local_path).is_file()]
        found = by_cell.get(key, [])
        partial = f" ({len(docs) - len(held)} of {len(docs)} not captured)" \
            if len(held) < len(docs) else ""

        if found:
            status, reason = "complete", partial.strip(" ()")
        elif not held:
            status = "not-captured"
            reason = f"{len(docs)} document(s) declared, none on disk"
        elif key[0] not in EXTRACTORS:
            status = "no-extractor"
            kinds = sorted({d.doc_type for d in held})
            reason = f"{len(held)} {'/'.join(kinds)} held; no extractor yet{partial}"
        else:
            status = "unread-format"
            reason = (f"{len(held)} document(s) held; this county's extractor "
                      f"does not handle this era{partial}")
        cells.append(Cell(key[0], key[1], status, len(docs), len(held),
                          found, reason))

    for county, year, note in KNOWN_GAPS:
        cells.append(Cell(county, year, "gap", 0, 0, [], note))
    return sorted(cells, key=lambda c: (c.county, c.year))


def write(cells: list[Cell], path: Path) -> None:
    def number(value, places=2):
        return "" if value is None else f"{value:.{places}f}"

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COVERAGE_FIELDS)
        writer.writeheader()
        for cell in cells:
            writer.writerow({
                "county": cell.county, "year": cell.year, "status": cell.status,
                "documents_declared": cell.declared,
                "documents_held": cell.held,
                "contests": len(cell.contests), "seats": cell.seats,
                "candidates": cell.candidates, "seats_unfilled": cell.unfilled,
                "candidates_per_seat": number(cell.candidates_per_seat),
                "uncontested_rate": number(cell.uncontested_rate),
                "unfilled_observed": cell.unfilled_observed,
                "reason": cell.reason,
            })


def report(cells: list[Cell]) -> None:
    complete = [c for c in cells if c.status == "complete"]

    print(f"{'county':<12} {'year':<6} {'contests':>8} {'seats':>6} "
          f"{'cands':>6} {'unfilled':>8} {'per seat':>9} {'uncont':>7} {'obs':>6}")
    for cell in complete:
        print(f"{cell.county:<12} {cell.year:<6} {len(cell.contests):>8} "
              f"{cell.seats:>6} {cell.candidates:>6} {cell.unfilled:>8} "
              f"{cell.candidates_per_seat:>9.2f} "
              f"{cell.uncontested_rate:>6.0%} {cell.unfilled_observed:>6}")

    seats = sum(c.seats for c in complete)
    candidates = sum(c.candidates for c in complete)
    if seats:
        counties = sorted({c.county for c in complete})
        print(f"\nAll complete cells pooled: {candidates} candidates for "
              f"{seats} seats = {candidates / seats:.2f} per seat")
        print(f"  {len(complete)} cells, {len(counties)} of 21 counties "
              f"({', '.join(counties)}).")
        print("  Not a state figure, and not a trend: which counties are "
              "complete\n  changes from year to year, so the pooled value "
              "moves with coverage\n  as much as with elections.")

    _panel(complete)


def _panel(complete: list[Cell]) -> None:
    """Year on year over the counties complete in *every* year.

    Pooling whatever happens to be complete each year confounds a change in
    candidates with a change in which counties were read. Restricting to the
    counties present throughout is the only comparison this dataset can honestly
    make over time.
    """
    years = sorted({c.year for c in complete})
    by_county: dict[str, set[str]] = collections.defaultdict(set)
    for cell in complete:
        by_county[cell.county].add(cell.year)
    panel = sorted(county for county, seen in by_county.items()
                   if seen == set(years))
    if not panel or len(years) < 2:
        return

    print(f"\nLike-for-like, {', '.join(panel)} in every year "
          f"{years[0]}-{years[-1]}:")
    print(f"  {'year':<6} {'seats':>6} {'cands':>6} {'per seat':>9} {'uncontested':>12}")
    for year in years:
        cells = [c for c in complete if c.year == year and c.county in panel]
        seats = sum(c.seats for c in cells)
        candidates = sum(c.candidates for c in cells)
        known = [x for c in cells for x in c.contests
                 if x.is_uncontested is not None]
        rate = sum(1 for x in known if x.is_uncontested) / len(known) if known else 0
        print(f"  {year:<6} {seats:>6} {candidates:>6} "
              f"{candidates / seats:>9.2f} {rate:>11.0%}")
    excluded = sorted({c.county for c in complete} - set(panel))
    if excluded:
        print(f"  (excludes {', '.join(excluded)}: not complete in every year)")

    print("\nnot counted:")
    for status in ("unread-format", "no-extractor", "not-captured", "gap"):
        group = [c for c in cells if c.status == status]
        if not group:
            continue
        held = sum(c.held for c in group)
        print(f"  {status:<14} {len(group):>3} cells, {held:>4} documents held")
        for cell in group[:3]:
            print(f"      {cell.county} {cell.year}: {cell.reason[:78]}")
        if len(group) > 3:
            print(f"      ... and {len(group) - 3} more")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m njfilings.coverage",
        description="Coverage matrix and the headline rate (plan 4.1).")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)

    cells = matrix(root=args.root)
    out = args.root / "data" / "coverage.csv"
    write(cells, out)
    report(cells)
    print(f"\n{len(cells)} cells -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
