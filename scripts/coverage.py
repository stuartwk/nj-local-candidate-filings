#!/usr/bin/env python3
"""Coverage matrix + rate summary. Cells are graded on what the SOURCE offers
and, separately, on what this probe actually pulled. Rates are computed only
over cells marked complete; nothing is imputed."""
import csv, json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
recs = json.load(open(os.path.join(ROOT, "data", "extracted_full.json")))

# source_status: what a full build could get. pulled_status: what this probe got.
MATRIX = [
 # county, year, source_status, pulled_status, format, seats, cands, unfilled, note
 ("Hunterdon","2022","partial","none","text PDF, table layout","stated","ABSENT","n/a",
  "Only the pre-filing 'offices up' notice survives: municipality/district/term/"
  "seats, no candidates. Its table is also a clean municipality->district crosswalk."),
 ("Hunterdon","2023","complete","complete","text PDF, outline","stated","stated","stated",
  "Single countywide candidate list covers every district."),
 ("Hunterdon","2024","complete","complete","text PDF, outline","stated","stated","stated",""),
 ("Hunterdon","2025","complete","complete","text PDF, outline","stated","stated","stated",
  "Two documents exist: a May seats-only notice and an August ballot draw. "
  "Ballot draw used; it also marks withdrawals."),
 ("Hunterdon","2026","complete","complete","text PDF, outline","stated","stated","stated",""),
 ("Bergen","2019","missing","none","-","-","-","-",
  "Only 2 of ~70 municipal sample ballots archived; live site keeps current cycle only."),
 ("Bergen","2020","missing","none","-","-","-","-","Same as 2019."),
 ("Bergen","2021","missing","none","-","-","-","-","Same as 2019."),
 ("Bergen","2022","missing","none","-","-","-","-","No captures found."),
 ("Bergen","2023","complete","partial","text PDF, one ballot per municipality","stated","stated","stated",
  "69 of ~70 municipalities archived. Probe pulled 7. Archived copies carry a DRAFT watermark."),
 ("Bergen","2024","complete","partial","text PDF, one ballot per municipality","stated","stated","stated",
  "72 archived. Probe pulled 8. Portrait layout; 2023 was landscape."),
 ("Bergen","2025","complete","partial","text PDF, one ballot per municipality","stated","stated","stated",
  "73 archived. Probe pulled 8. Path/filename convention differs from 2023 and 2024."),
 ("Essex","2020","available-unparsed","none","text PDF, countywide","stated","stated","n/a",
  "Archived, but typeset in a different font family (Garamond/Gloucester); needs a third parser profile."),
 ("Essex","2021","missing","none","-","-","-","-","No countywide sample-ballot PDF captured."),
 ("Essex","2022","complete","complete","text PDF, countywide","stated","stated","n/a",
  "One PDF, one page per municipality/ward."),
 ("Essex","2023","complete","complete","text PDF, countywide","stated","stated","n/a",
  "Includes side-by-side contests (regional + local + unexpired on one page)."),
 ("Essex","2024","missing","none","-","-","-","-",
  "No countywide sample-ballot PDF captured for 2024 under any filename."),
 ("Essex","2025","complete","complete","text PDF, countywide","stated","stated","n/a",""),
]

out = os.path.join(ROOT, "data", "coverage_matrix.csv")
with open(out, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["county","year","office_type","source_status","pulled_status",
                "format","seats_available","candidates_filed","seats_unfilled_stated",
                "races_extracted","note"])
    for row in MATRIX:
        cty, yr = row[0], row[1]
        n = sum(1 for r in recs if r["county"] == cty and r["year"] == yr)
        w.writerow([cty, yr, "school board", row[2], row[3], row[4], row[5],
                    row[6], row[7], n, row[8]])
print("wrote", out)

print("\n=== uncontested rates over COMPLETE cells only ===")
complete = {(r[0], r[1]) for r in MATRIX if r[3] == "complete"}
by = collections.defaultdict(list)
for r in recs:
    if (r["county"], r["year"]) in complete:
        by[(r["county"], r["year"])].append(r)
tot_u = tot_n = 0
for k in sorted(by):
    rows = by[k]
    unc = sum(1 for r in rows if r["is_uncontested"])
    unf = sum(r["seats_unfilled"] for r in rows)
    seats = sum(r["seats_available"] for r in rows)
    print(f"  {k[0]:10}{k[1]}  races {len(rows):3}  uncontested {unc:3} "
          f"({unc/len(rows):5.1%})  seats {seats:3}  unfilled {unf:2} ({unf/seats:4.1%})")
    tot_u += unc; tot_n += len(rows)
print(f"  {'ALL':10}      races {tot_n:3}  uncontested {tot_u:3} ({tot_u/tot_n:5.1%})")

print("\n=== Bergen subsample (NOT a rate: 7-8 of ~70 municipalities per year) ===")
b = [r for r in recs if r["county"] == "Bergen"]
print(f"  races {len(b)}  uncontested {sum(1 for r in b if r['is_uncontested'])}")
