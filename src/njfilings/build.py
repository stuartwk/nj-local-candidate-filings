"""Run the available extractors over the cache and write the dataset.

Reads only from `cache/`. If a declared document has not been captured, that is
reported and skipped — building must never reach for the network, or a parser
bug eventually becomes a fetch and the cache stops being the source of truth.

Output is sorted on a fixed key with a fixed column order (build plan 3.3), so a
git diff of `data/races.csv` shows what actually changed rather than rows that
moved. That diff is the review mechanism for every future parser change.

Usage:
    python -m njfilings.build
    python -m njfilings.build --county hunterdon --problems
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .capture import PROJECT_ROOT
from .model import CSV_FIELDS, Contest, sort_key, to_row
from .sources import Document, documents
from .extract import atlantic, hunterdon, morris, union

# A county appears here once it has an extractor, paired with the documents that
# extractor understands.
#
# Naming the filenames is not ceremony. Atlantic and Union each publish a
# general-election candidate list alongside the school-board one, and both are
# declared `candidate_list` because both are candidate lists — the difference is
# scope, not type. Running a school-board parser over the all-offices list
# invented 27 contests for Union and moved its candidates-per-seat from 1.28 to
# 2.20 without anything failing.
EXTRACTORS = {
    "hunterdon": (hunterdon.extract, {"school-board-candidates.pdf"}),
    # Morris 2021-2022 use a different layout and are not handled yet; build
    # reports them as extracting nothing rather than guessing.
    "morris": (morris.extract, {"school-board-candidates.pdf"}),
    "atlantic": (atlantic.extract, {"school-board-candidates.pdf"}),
    "union": (union.extract, {"school-board-candidates.pdf"}),
}


def build(root: Path = PROJECT_ROOT, counties: list[str] | None = None,
          verbose: bool = True) -> list[Contest]:
    wanted = [c for c in (counties or EXTRACTORS) if c in EXTRACTORS]
    contests: list[Contest] = []
    missing: list[Document] = []
    empty: list[Document] = []

    for doc in documents(wanted):
        extractor, filenames = EXTRACTORS[doc.county]
        if doc.doc_type != "candidate_list" or doc.filename not in filenames:
            continue
        path = root / doc.local_path
        if not path.is_file():
            missing.append(doc)
            continue
        found = extractor(path, year=doc.year, source_url=doc.url,
                          source_document=doc.filename)
        contests.extend(found)
        if verbose:
            note = "  <-- extracted nothing" if not found else ""
            print(f"{doc.county} {doc.year}: {len(found):>3} contests "
                  f"from {doc.filename}{note}")
        if not found:
            empty.append(doc)

    if empty and verbose:
        # a captured document that yields nothing is usually a format era
        # nobody has written a profile for, and it must not pass unremarked
        print("\ncaptured but extracted nothing (unhandled format?):",
              file=sys.stderr)
        for doc in empty:
            print(f"  {doc.county} {doc.year} {doc.filename}", file=sys.stderr)

    if missing and verbose:
        print("\nnot captured, skipped:", file=sys.stderr)
        for doc in missing:
            print(f"  {doc.county} {doc.year} {doc.filename}", file=sys.stderr)

    return sorted(contests, key=sort_key)


def write(contests: list[Contest], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for contest in contests:
            writer.writerow(to_row(contest))


def summarise(contests: list[Contest]) -> None:
    """Candidates per seat, the headline measure, over what was extracted.

    Computed only where seats are known — a contest with unknown seats is left
    out of both sums rather than counted as zero.
    """
    print(f"\n{'county':<12} {'year':<6} {'contests':>8} {'seats':>6} "
          f"{'cands':>6} {'unfilled':>8} {'per seat':>9}")
    cells: dict[tuple[str, str], list[Contest]] = {}
    for c in contests:
        cells.setdefault((c.county, c.year), []).append(c)
    for key in sorted(cells):
        rows = [c for c in cells[key] if c.seats_available is not None]
        seats = sum(c.seats_available for c in rows)
        cands = sum(c.candidate_count for c in rows)
        unfilled = sum(c.seats_unfilled or 0 for c in rows)
        ratio = f"{cands / seats:.2f}" if seats else "-"
        print(f"{key[0]:<12} {key[1]:<6} {len(cells[key]):>8} {seats:>6} "
              f"{cands:>6} {unfilled:>8} {ratio:>9}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m njfilings.build",
        description="Extract cached documents into data/races.csv.")
    parser.add_argument("--county", action="append", metavar="NAME",
                        choices=sorted(EXTRACTORS),
                        help=f"repeatable; default all with extractors "
                             f"({', '.join(sorted(EXTRACTORS))})")
    parser.add_argument("--problems", action="store_true",
                        help="list records that look wrong and exit non-zero")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)

    contests = build(root=args.root, counties=args.county)
    if not contests:
        print("nothing extracted", file=sys.stderr)
        return 1

    out = args.root / "data" / "races.csv"
    write(contests, out)
    summarise(contests)
    print(f"\n{len(contests)} contests -> {out}")

    flagged = [(c, c.problems()) for c in contests]
    flagged = [(c, p) for c, p in flagged if p]
    if flagged:
        print(f"\n{len(flagged)} records need a look:", file=sys.stderr)
        for contest, issues in flagged:
            where = f"{contest.county} {contest.year} {contest.municipality}"
            for issue in issues:
                print(f"  {where} p{contest.source_page}: {issue}",
                      file=sys.stderr)
        if args.problems:
            return 1
    elif args.problems:
        print("\nno records flagged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
