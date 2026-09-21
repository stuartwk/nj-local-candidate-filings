#!/usr/bin/env python3
"""Draw a stratified ~36-record sample (4 per county x year cell) from the
full extraction and write it in the schema the brief specifies."""
import csv, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
recs = json.load(open(os.path.join(ROOT, "data", "extracted_full.json")))

cells = {}
for r in recs:
    cells.setdefault((r["county"], r["year"]), []).append(r)

sample = []
for key in sorted(cells):
    rows = sorted(cells[key], key=lambda r: (r["municipality"], r["is_unexpired"],
                                             r["source_page"]))
    n = min(4, len(rows))
    # evenly spaced through the cell rather than the first four alphabetically
    idx = [round(i * (len(rows) - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]
    for i in sorted(set(idx)):
        sample.append(rows[i])

FIELDS = ["county", "year", "election_type", "municipality", "district_name",
          "office", "term_years", "is_unexpired", "seats_available",
          "candidates_filed", "candidate_count", "is_uncontested",
          "seats_unfilled", "seats_unfilled_stated",
          "source_url", "source_document", "source_page", "also_on"]

out = os.path.join(ROOT, "data", "sample_school_board_races.csv")
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in sample:
        row = dict(r)
        row["candidates_filed"] = "; ".join(
            c["name"] + (" [withdrew]" if c.get("withdrew") else "")
            for c in r["candidates_filed"])
        row["also_on"] = " | ".join(r.get("also_on", []))
        w.writerow(row)

print(f"wrote {len(sample)} records to {out}")
for key in sorted(cells):
    print(f"  {key[0]:10} {key[1]}  cell size {len(cells[key]):3}  sampled "
          f"{sum(1 for s in sample if (s['county'], s['year']) == key)}")
