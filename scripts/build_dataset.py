#!/usr/bin/env python3
"""Run the three county extractors over the local document cache and emit
the probe dataset. No network access: everything is read from cache/."""
import csv, json, os, re, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parse_hunterdon, parse_bergen_ballot, parse_essex_ballot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, "cache")

HUNTERDON = [
    ("hunterdon/sbc-2023-12466.txt", "2023",
     "https://www.co.hunterdon.nj.us/DocumentCenter/View/12466/UnOfficial-School-Board-Candidates-2023-filed-candidates-PDF",
     "UnOfficial School Board Candidates 2023 (filed candidates)"),
    ("hunterdon/sbc-2024-15174.txt", "2024",
     "https://www.co.hunterdon.nj.us/DocumentCenter/View/15174/UnOfficial--School-Board-Candidates-2024-PDF",
     "UnOfficial School Board Candidates 2024 (8/19/2024)"),
    ("hunterdon/sbc-2025b-17436.txt", "2025",
     "https://www.co.hunterdon.nj.us/DocumentCenter/View/17436/UnOfficial-School-Board-Candidates-2025-PDF",
     "Annual School Election Ballot Draw 2025 (8/11/2025)"),
    ("hunterdon/sbc-2026-20403.txt", "2026",
     "https://www.co.hunterdon.nj.us/DocumentCenter/View/20403/UnOfficial-School-Board-Candidates-2026-PDF",
     "UnOfficial School Board Candidates 2026"),
]

BERGEN_URL = ("https://www.bergencountyclerk.gov/_Content/pdf/voting/"
              "sample-ballots/{path}")
BERGEN_PATHS = {"2023": "2023/{m}.pdf", "2024": "2024-general/{m}.pdf",
                "2025": "2025/{m}-Gen25.pdf"}

ESSEX = [
    ("essex/sb-2022-general.pdf", "2022",
     "https://www.essexclerk.com/_Content/pdf/Elect%20Information/Essex-Sample-Ballots-2022g-Alphabetical.pdf"),
    ("essex/sb-2023-general.pdf", "2023",
     "https://www.essexclerk.com/_Content/pdf/Essex-Sample-Ballots-General-Election.pdf"),
    ("essex/sb-2025-general.pdf", "2025",
     "https://www.essexclerk.com/_Content/pdf/Essex-2025-General-Election-Sample-Ballots.pdf"),
]


def finish(r):
    """Derive the two computed fields. Nothing here is imputed: if seats or
    candidates are unknown the derived fields stay None."""
    seats, cands = r["seats_available"], r["candidates_filed"]
    live = [c for c in cands if not c.get("withdrew")]
    r["candidate_count"] = len(live)
    if seats is None:
        r["is_uncontested"] = None
        r["seats_unfilled"] = None
    else:
        r["is_uncontested"] = len(live) <= seats
        r["seats_unfilled"] = max(0, seats - len(live))
        # where the source states it outright, prefer the source over arithmetic
        if r.get("no_nomination_count"):
            r["seats_unfilled_stated"] = r["no_nomination_count"]
        else:
            r["seats_unfilled_stated"] = None
    return r


def main():
    recs = []

    for rel, year, url, docname in HUNTERDON:
        recs += [finish(r) for r in parse_hunterdon.parse(
            os.path.join(C, rel), "Hunterdon", year, "general", url, docname)]

    for f in sorted(glob.glob(os.path.join(C, "bergen", "*.pdf"))):
        base = os.path.basename(f)
        m = re.match(r"b(\d{4})-(.+)\.pdf$", base)
        if m:
            year, muni = m.group(1), m.group(2)
        elif base == "teaneck-2023.pdf":
            year, muni = "2023", "Teaneck"
        else:
            continue
        url = BERGEN_URL.format(path=BERGEN_PATHS[year].format(m=muni))
        pretty = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", muni).replace("-", " ")
        recs += [finish(r) for r in parse_bergen_ballot.extract(
            f, "Bergen", year, "general", pretty, url)]

    for rel, year, url in ESSEX:
        recs += [finish(r) for r in parse_essex_ballot.extract(
            os.path.join(C, rel), "Essex", year, "general", url)]

    # One race can be printed on several ballots (wards of one town, or two
    # towns in a shared regional district). Collapse those, keeping every
    # source page as provenance.
    seen, deduped = {}, []
    for r in recs:
        names = tuple(sorted(c["name"].upper() for c in r["candidates_filed"]))
        key = (r["county"], r["year"], r["seats_available"], r["term_years"],
               r["is_unexpired"], names or r["municipality"])
        if key in seen:
            prev = seen[key]
            prev["also_on"].append(f"{r['source_document']}#p{r['source_page']}"
                                   f" ({r['municipality']})")
        else:
            r["also_on"] = []
            seen[key] = r
            deduped.append(r)

    json.dump(deduped, open(os.path.join(ROOT, "data", "extracted_full.json"), "w"),
              indent=1, ensure_ascii=False)
    print(f"raw records {len(recs)} -> distinct races {len(deduped)}")
    for cty in ("Hunterdon", "Bergen", "Essex"):
        rows = [r for r in deduped if r["county"] == cty]
        yrs = sorted({r["year"] for r in rows})
        print(f"  {cty:10} {len(rows):4} races  years {yrs}")
    return deduped


if __name__ == "__main__":
    main()
