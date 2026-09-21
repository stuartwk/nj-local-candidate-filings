"""The two validation arms from build plan 3.4.

The rule that shapes this module: **a check that reuses the parser's logic
proves nothing.** If the validator asked the same regex the same question it
would agree with itself on every document, including the ones it got wrong. So
everything here works from raw page text and deliberately simpler rules than the
extractor uses, and where a check cannot be made independently it prints the
source for a human instead of returning a verdict.

**Enumeration** — the arm the plan says is not optional, because transcription
cannot catch a race that should not exist, a duplicate, or a contest filed under
the wrong municipality. Two document-wide invariants do it exhaustively rather
than for three towns:

  * every email address in the document belongs to exactly one candidate, so the
    count of emails must equal the number of filings extracted. A dropped
    candidate, a doubled one, or a slogan read as a person all break it.
  * every `No Nomination Made` / `No Petition Filed` marker is one unfilled
    seat, so the count must equal the unfilled seats recorded.

Neither uses the parser. Both were found to hold exactly across 2023-2026 —
which is how the capitalised-marker bug was proven fixed rather than assumed.

**Transcription** — a sample of records, each checked field by field against the
page it cites, and written out with the source text beside it so a person can
read both. Automated agreement is necessary, not sufficient; the CSV exists to
be read.

Usage:
    python -m njfilings.validate
    python -m njfilings.validate --sample 12 --seed 7
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from pathlib import Path

from .build import EXTRACTORS, build
from .capture import PROJECT_ROOT
from .model import Contest
from .sources import documents

# Deliberately looser than any extractor's: county documents contain malformed
# addresses (`joiurato3@gmail` with no domain, one with two `@`, one using a
# non-ASCII hyphen). A strict pattern under-counts them and reports a phantom
# discrepancy. The asymmetry is the point — a strict extractor drops such a
# candidate, and this notices that it did.
EMAIL_RE = re.compile(r"\S+@\S+")
MARKER_RE = re.compile(r"No\s+(?:Nomination\s+Made|Petition\s+Filed)", re.I)
# deliberately cruder than the extractor's pattern: a contest line says how many
# years and how many votes, and is not an email address
CONTEST_ISH = re.compile(r"\d\s*Yr.{0,40}?Vote\s*for", re.I | re.DOTALL)
MUNICIPALITY_HINT = re.compile(
    r"\b(TOWNSHIP|TOWNSHP|TWP|BOROUGH|BORO|TOWN|CITY|VILLAGE)\b", re.I)
DISTRICT_HINT = re.compile(r"\b(SCHOOL|DISTRICT|REGIONAL)\b", re.I)
CROSSREF_HINT = re.compile(r"[-\s]SEE\s+[A-Z]", re.I)

SEAT_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
              6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}

VALIDATION_FIELDS = [
    "county", "year", "municipality", "district_name", "term_years",
    "is_unexpired", "seats_available", "candidate_count", "seats_unfilled",
    "source_document", "source_page",
    "municipality_on_page", "term_on_page", "seats_on_page", "names_on_page",
    "verdict", "source_excerpt",
]


def page_texts(path: Path) -> list[str]:
    import pymupdf
    return [page.get_text() for page in pymupdf.open(path)]


# --- enumeration ---------------------------------------------------------

MORRIS_TITLE_RE = re.compile(
    r"MEMBER OF THE (?:REGIONAL )?BOARD OF EDUCATION", re.I)
ATLANTIC_SEATS_RE = re.compile(r"^V\d+$", re.I | re.M)
SALEM_SECTION_RE = re.compile(r"OFFICIAL SCHOOL ELECTION", re.I)
UNION_HEADER_RE = re.compile(
    r"\d+\s*YEAR\s*TERM\s*[-–—]?\s*(?:UNEXPIRED\s*)?VOTE\s*FOR\s+[A-Z]+", re.I)


def _flatten(text: str) -> str:
    """Morris separates words with U+00A0 about half the time."""
    return re.sub(r"[ \t\xa0]+", " ", text)


def enumerate_morris(text: str, contests: list[Contest]) -> list[str]:
    """Morris prints one row per candidate, each repeating its contest's
    heading, so the row count is exactly checkable: every contest title is one
    filing or one unfilled seat, and nothing else."""
    flat = _flatten(text)
    issues = []
    titles = len(MORRIS_TITLE_RE.findall(flat))
    rows = sum(len(c.candidates_filed) for c in contests) \
        + sum(c.seats_unfilled_stated or 0 for c in contests)
    if titles != rows:
        issues.append(f"{titles} contest-title rows in the document but "
                      f"{rows} filings and unfilled seats recorded")

    # per town, the same count
    for town in sorted({c.municipality for c in contests if c.municipality}):
        expected = sum(1 for i, line in enumerate(flat.splitlines())
                       if MORRIS_TITLE_RE.match(line.strip())
                       and i and flat.splitlines()[i - 1].strip() == town)
        got = sum(len(c.candidates_filed) + (c.seats_unfilled_stated or 0)
                  for c in contests if c.municipality == town)
        if expected != got:
            issues.append(f"{town}: source shows {expected} rows, "
                          f"dataset has {got}")
    return issues


def enumerate_rows(county: str, text: str, contests: list[Contest]) -> list[str]:
    """One count per county, of whatever unit that county's document repeats.

    Each list is built from a different unit — a contest sentence, a table row,
    a seats cell, a page — so the check has to know which. Getting this wrong
    produces a confident complaint about a correct dataset, which is worse than
    no check at all.
    """
    flat = _flatten(text)
    filings = sum(len(c.candidates_filed) for c in contests)
    unfilled = sum(c.seats_unfilled_stated or 0 for c in contests)

    if county == "morris":
        return _compare(len(MORRIS_TITLE_RE.findall(flat)), filings + unfilled,
                        "contest-title rows", "filings and unfilled seats")
    if county == "atlantic":
        return _compare(len(ATLANTIC_SEATS_RE.findall(flat)), filings + unfilled,
                        "seat cells (V1/V2/V3)", "filings and unfilled seats")
    if county == "salem":
        # Every ballot prints one school section, and a contest shared by two
        # municipalities is printed on both. So the sections must equal the
        # contests plus the duplicate printings they were merged from — which
        # checks the merge as well as the parse.
        printings = len(contests) + sum(len(c.also_on) for c in contests)
        return _compare(len(SALEM_SECTION_RE.findall(flat)), printings,
                        "school sections across the ballots",
                        "contests and merged duplicates")
    if county == "union":
        return _compare(len(UNION_HEADER_RE.findall(flat)), len(contests),
                        "contest headers", "contests")
    # a county whose document puts each contest on its own line
    lines = [l for l in text.splitlines() if CONTEST_ISH.search(l)
             and not EMAIL_RE.search(l)]
    return _compare(len(lines), len(contests), "contest-shaped lines", "contests")


def _compare(found: int, recorded: int, what: str, against: str) -> list[str]:
    if found == recorded:
        return []
    return [f"{found} {what} in the document but {recorded} {against} recorded"]


def enumerate_document(text: str, contests: list[Contest]) -> list[str]:
    """Document-wide counts that must agree. Returns complaints.

    Both checks here assume the document is entirely about school boards. A
    sample ballot is not — it carries every office on it — so each is skipped
    where the document shows it is a ballot. `enumerate_rows` carries the weight
    for those counties instead.

    Takes the text rather than a path so it can be tested against literal
    documents, and so a failure is attributable to the check rather than to
    text extraction.
    """
    issues = []

    emails = len(EMAIL_RE.findall(text))
    filed = sum(len(c.candidates_filed) for c in contests)
    # A ballot lists nobody's email, so the invariant simply does not apply
    # there. Applying it anyway would report every ballot county as broken.
    if emails and emails != filed:
        issues.append(f"{emails} email addresses in the document but {filed} "
                      f"filings extracted")

    # On a ballot the school election is one section among the municipal
    # contests, and those print unfilled-seat markers of their own — Salem's
    # ballots carry 30 where the school contests account for 8. A document-wide
    # count only means something where the whole document is about school
    # boards, which is to say a candidate list.
    if not SALEM_SECTION_RE.search(text):
        markers = len(MARKER_RE.findall(text))
        unfilled = sum(c.seats_unfilled_stated or 0 for c in contests)
        if markers != unfilled:
            issues.append(f"{markers} unfilled-seat markers but "
                          f"{unfilled} recorded")

    return issues


def _town_heading(line: str) -> str | None:
    """The municipality this line introduces, if it introduces one.

    Note the limit of this arm: recognising a heading means understanding the
    document the same way the extractor does, so the town-count check is less
    independent than the email and marker counts above. Those two are the ones
    that would catch a parser rewritten from scratch getting it wrong.

    A heading is usually a line of its own, but the clerk sometimes runs the
    town and its contest together: `UNION TOWNSHIP- 3 Yr. Term- Vote for One`.
    Such a line is both a boundary and a contest, and missing that under-counts
    the town it names and over-counts the one above it.
    """
    if EMAIL_RE.search(line) or CROSSREF_HINT.search(line):
        return None            # `X -SEE Y` points elsewhere; it is not a town
    match = CONTEST_ISH.search(line)
    head = line[:match.start()] if match else line
    # the town is sometimes inside the office, in mixed case:
    # `School Board Member - Raritan Township- 3 Yr. Term-Vote for Three`
    head = re.sub(r"^\s*School\s+Board\s+Member", "", head,
                  flags=re.I).strip(" -–—_,")
    if head and MUNICIPALITY_HINT.search(head):
        return head.upper()
    return None


def enumerate_municipalities(text: str, contests: list[Contest],
                             how_many: int, rng: random.Random) -> list[str]:
    """The plan's own arm: pick towns, count what the source gives each one,
    compare with what the dataset gave it."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Towns come from the SOURCE, never from the dataset. Taking them from the
    # dataset would make a town that was dropped wholesale invisible — the check
    # would never think to ask about it, and that is exactly the "race that
    # should exist but does not" case no other check can see.
    towns = sorted({t for t in (_town_heading(l) for l in lines) if t})
    if not towns:
        return []

    issues = []
    for town in rng.sample(towns, min(how_many, len(towns))):
        expected = 0
        inside = False
        for line in lines:
            heading = _town_heading(line)
            is_contest = bool(CONTEST_ISH.search(line)) and not EMAIL_RE.search(line)
            if heading == town:
                inside = True
                if is_contest:          # town and contest on the same line
                    expected += 1
                continue
            if heading is not None or (
                    line.isupper() and not is_contest and not EMAIL_RE.search(line)
                    and DISTRICT_HINT.search(line)):
                inside = False          # some other town or district begins
                continue
            if inside and is_contest:
                expected += 1
        got = sum(1 for c in contests if c.municipality == town)
        if expected != got:
            issues.append(f"{town}: source shows {expected} contests, "
                          f"dataset has {got}")
    return issues


# --- transcription --------------------------------------------------------

def check_record(contest: Contest, pages: list[str]) -> dict[str, object]:
    """Confirm each field against the page the record cites.

    The probes differ by county because the documents differ: Hunterdon writes
    a contest as a sentence (`3 Yr. Term - Vote for Three`), Morris as columns
    of a table. A single probe would either pass vacuously on one or fail
    wrongly on the other.
    """
    index = (contest.source_page or 1) - 1
    page = pages[index] if 0 <= index < len(pages) else ""
    if contest.county == "morris":
        # A contest's rows are contiguous but can run over a page break — six
        # Montville candidates, five on page 1 and one on page 2. Checking only
        # the cited page reports a correct record as wrong.
        following = pages[index + 1] if index + 1 < len(pages) else ""
        return _check_tabular(contest, page, following)
    if contest.county in ("atlantic", "union", "salem"):
        return _check_by_presence(contest, page)
    return _check_outline(contest, page)


def _check_by_presence(contest: Contest, page: str) -> dict[str, object]:
    """Atlantic, Union and Salem: confirm the record's values appear on its page.

    Weaker than the block-scoped checks, deliberately. Atlantic states seats as
    `V3` and Union as `VOTE FOR THREE`, neither of which sits next to the
    candidate it governs, so there is no block to scope to. The enumeration
    counts carry the weight for these two.
    """
    flat = re.sub(r"\s+", " ", page.replace("\xa0", " "))
    municipality_ok = (contest.municipality is None
                       or contest.municipality in flat)
    if contest.county == "atlantic":
        seats_ok = re.search(rf"\bV{contest.seats_available}\b", flat) is not None
        term_ok = re.search(rf"{contest.term_years}\s*yr", flat, re.I) is not None
    elif contest.county == "salem":
        word = SEAT_WORDS.get(contest.seats_available, "")
        seats_ok = re.search(rf"Vote for\s+{word}\b", flat, re.I) is not None
        term_ok = re.search(rf"{contest.term_years}\s*Year\s*Term", flat,
                            re.I) is not None
    else:
        word = SEAT_WORDS.get(contest.seats_available, "")
        seats_ok = re.search(rf"VOTE\s*FOR\s+{word}\b", flat, re.I) is not None
        term_ok = re.search(rf"{contest.term_years}\s*YEAR\s*TERM", flat,
                            re.I) is not None
    names_ok = all(c.name in flat for c in contest.candidates_filed)
    checks = [municipality_ok, term_ok, seats_ok, names_ok]
    return {
        "municipality_on_page": municipality_ok,
        "term_on_page": term_ok,
        "seats_on_page": seats_ok,
        "names_on_page": names_ok,
        "verdict": "ok" if all(checks) else "CHECK",
        "source_excerpt": " / ".join(
            l.strip() for l in page.splitlines() if l.strip())[:420],
    }


def _check_tabular(contest: Contest, page: str,
                   following: str = "") -> dict[str, object]:
    """Morris: the four header fields sit on consecutive lines above the
    candidate, so the check is that the row exists in that order."""
    lines = [_flatten(l).strip() for l in page.splitlines()]
    # A candidate's given and family names are on separate lines of the table,
    # so the page has to be flattened across newlines before looking for a whole
    # name — otherwise every Morris record fails for a formatting reason.
    flat = re.sub(r"\s+", " ", (page + "\n" + following).replace("\xa0", " "))

    municipality_ok = bool(contest.municipality) and contest.municipality in flat
    row_ok = False
    for i, line in enumerate(lines[:-3]):
        if line != contest.municipality or not MORRIS_TITLE_RE.match(lines[i + 1]):
            continue
        if lines[i + 2] != str(contest.term_years):
            continue
        seats, _, district = lines[i + 3].partition(" ")
        if seats != str(contest.seats_available):
            continue
        if contest.district_name and district.strip() != contest.district_name:
            continue
        row_ok = True
        break

    names_ok = all(c.name in flat for c in contest.candidates_filed)
    checks = [municipality_ok, row_ok, names_ok]
    return {
        "municipality_on_page": municipality_ok,
        "term_on_page": row_ok,
        "seats_on_page": row_ok,
        "names_on_page": names_ok,
        "verdict": "ok" if all(checks) else "CHECK",
        "source_excerpt": " / ".join(
            l for l in lines[:6] if l)[:420] if not municipality_ok
        else _tabular_excerpt(lines, contest),
    }


def _tabular_excerpt(lines: list[str], contest: Contest, width: int = 420) -> str:
    start = next((i for i, l in enumerate(lines)
                  if l == contest.municipality), 0)
    return " / ".join(l for l in lines[start:start + 10] if l)[:width]


def _check_outline(contest: Contest, page: str) -> dict[str, object]:
    # Check inside this contest's own block, not the whole page. A real page
    # carries a dozen contests, so "the phrase appears somewhere on the page"
    # would pass for a seat count belonging to a different town.
    block = re.sub(r"\s+", " ", _block(page, contest))

    # The extractor normalises a town's capitalisation, because the clerk's own
    # varies within one document (`Stockton Borough-`). Comparing case-sensitively
    # here reports those records as missing from their own page.
    municipality_ok = (contest.municipality is None
                       or contest.municipality.upper() in page.upper())
    term_ok = (contest.term_years is None
               or re.search(rf"{contest.term_years}\s*Yr", block, re.I) is not None)
    seats_ok = (contest.seats_available is None
                or re.search(rf"Vote\s*for\s+{SEAT_WORDS[contest.seats_available]}\b",
                             block, re.I) is not None)
    names_ok = all(c.name in block for c in contest.candidates_filed)

    checks = [municipality_ok, term_ok, seats_ok, names_ok]
    return {
        "municipality_on_page": municipality_ok,
        "term_on_page": term_ok,
        "seats_on_page": seats_ok,
        "names_on_page": names_ok,
        "verdict": "ok" if all(checks) else "CHECK",
        "source_excerpt": excerpt(page, contest),
    }


def _block(page: str, contest: Contest, span: int = 60) -> str:
    """The lines on the page belonging to this record's heading.

    Anchored on the heading the record claims and running to the next heading.
    It must run that far: a town often carries two contests — a full term and an
    unexpired one — separated by a dozen candidates and slogans, and a fixed
    short window would find only the first and flag the second as wrong.

    Only a line naming a municipality or a district ends the block. All-caps
    slogans (`FOR TRADITIONAL VALUES`) sit between the two contests and must not
    be mistaken for a boundary.
    """
    lines = [l.strip() for l in page.splitlines() if l.strip()]
    anchor = (contest.municipality or contest.district_name or "").upper()
    start = next((i for i, l in enumerate(lines)
                  if anchor and anchor in l.upper()), None)
    if start is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1:start + 1 + span]:
        if line.isupper() and not CONTEST_ISH.search(line) \
                and not EMAIL_RE.search(line) \
                and (MUNICIPALITY_HINT.search(line) or DISTRICT_HINT.search(line)):
            break
        out.append(line)
    return "\n".join(out)


def excerpt(page: str, contest: Contest, width: int = 420) -> str:
    """The source text around this contest, for a human to read."""
    return " / ".join(_block(page, contest).splitlines())[:width]


def transcription_sample(contests: list[Contest], root: Path, size: int,
                         rng: random.Random) -> list[dict[str, object]]:
    sample = rng.sample(contests, min(size, len(contests)))
    sample.sort(key=lambda c: (c.county, c.year, c.source_page or 0,
                               c.municipality or ""))
    cache: dict[str, list[str]] = {}
    rows = []
    for contest in sample:
        path = _path_for(contest, root)
        if path is None:
            continue
        if str(path) not in cache:
            cache[str(path)] = page_texts(path)
        row = {f: getattr(contest, f, "") for f in
               ("county", "year", "municipality", "district_name", "term_years",
                "is_unexpired", "seats_available", "source_document",
                "source_page")}
        row["candidate_count"] = contest.candidate_count
        row["seats_unfilled"] = contest.seats_unfilled
        row.update(check_record(contest, cache[str(path)]))
        rows.append(row)
    return rows


def _paths_for(contests: list[Contest], root: Path) -> list[Path]:
    """Every cached document the contests in a cell were read from, including
    the ones duplicates were merged away from."""
    wanted = {c.source_document for c in contests}
    for contest in contests:
        wanted.update(citation.split("#")[0] for citation in contest.also_on)
    paths = []
    for doc in documents([contests[0].county], [contests[0].year]):
        if doc.filename in wanted and (root / doc.local_path).is_file():
            paths.append(root / doc.local_path)
    return paths


def _path_for(contest: Contest, root: Path) -> Path | None:
    for doc in documents([contest.county], [contest.year]):
        if doc.filename == contest.source_document:
            path = root / doc.local_path
            return path if path.is_file() else None
    return None


# --- driver ---------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m njfilings.validate",
        description="Validate the dataset against its sources (plan 3.4).")
    parser.add_argument("--county", action="append", metavar="NAME",
                        choices=sorted(EXTRACTORS))
    parser.add_argument("--sample", type=int, default=10,
                        help="records to check field by field (default 10)")
    parser.add_argument("--municipalities", type=int, default=3,
                        help="towns to enumerate per document (default 3)")
    parser.add_argument("--seed", type=int, default=0,
                        help="fixed so a run is reproducible")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args(argv)

    contests = build(root=args.root, counties=args.county, verbose=False)
    if not contests:
        print("nothing to validate", file=sys.stderr)
        return 1
    rng = random.Random(args.seed)

    print("=== enumeration ===")
    failures = 0
    by_document: dict[tuple[str, str], list[Contest]] = {}
    for contest in contests:
        by_document.setdefault((contest.county, contest.year), []).append(contest)

    for key in sorted(by_document):
        group = by_document[key]
        paths = _paths_for(group, args.root)
        if not paths:
            print(f"  {key[0]} {key[1]}: source not cached, skipped")
            continue
        # a per-municipality county is dozens of documents per cell, and the
        # counts have to be taken over all of them
        text = "\n".join(t for path in paths for t in page_texts(path))
        issues = enumerate_document(text, group)
        issues += enumerate_rows(key[0], text, group)
        if key[0] == "morris":
            issues += enumerate_morris(text, group)
        elif key[0] == "hunterdon":
            issues += enumerate_municipalities(text, group,
                                               args.municipalities, rng)
        if issues:
            failures += len(issues)
            print(f"  {key[0]} {key[1]}: {len(issues)} problem(s)")
            for issue in issues:
                print(f"      {issue}")
        else:
            print(f"  {key[0]} {key[1]}: {len(group)} contests, "
                  f"{sum(len(c.candidates_filed) for c in group)} filings, "
                  f"counts agree with the source")

    print("\n=== transcription ===")
    rows = transcription_sample(contests, args.root, args.sample, rng)
    out = args.root / "data" / "validation.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=VALIDATION_FIELDS,
                                extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    flagged = [r for r in rows if r["verdict"] != "ok"]
    for row in rows:
        mark = " " if row["verdict"] == "ok" else "!"
        print(f" {mark} {row['county']} {row['year']} p{row['source_page']} "
              f"{str(row['municipality'] or row['district_name'])[:34]:<34} "
              f"seats={row['seats_available']} cands={row['candidate_count']} "
              f"{row['verdict']}")
    failures += len(flagged)
    print(f"\n{len(rows) - len(flagged)}/{len(rows)} checked records agree "
          f"with their cited page  ->  {out}")
    print("Automated agreement is necessary, not sufficient: read the "
          "source_excerpt column.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
