# Feasibility probe: uncontested school board races in New Jersey

**Recommendation: GO**, with one scope change — treat *document capture* as the
project, not document *parsing*.

Evidence: 222 school board races extracted from three counties across four
cycles; 15 records hand-checked against the source document; 100% on
`seats_available` and `candidates_filed`.

---

## 1. The crux question is resolved

`seats_available` was flagged as the highest-risk element. It is not a risk.

Every document that names candidates also states the number to be elected,
because New Jersey ballots and candidate lists are required to carry it:

- Hunterdon candidate list: `School Board Member- 3 Yr. Term-Vote for Three`
- Bergen sample ballot: `(FULL THREE YEAR TERM - VOTE FOR THREE)`
- Essex sample ballot: `Three Year Term / Vote for Three`

The staggered-term complication the brief flags is also handled at source. Every
county labels unexpired-term seats explicitly (`1 Yr. Unexpired`,
`UNEXPIRED TERM 1 YEAR`, `Unexpired Term`) and prints them as a separate contest
with their own seat count. They are never silently merged into full-term seats.

**Better than expected:** two of the three counties print unfilled seats
outright — Hunterdon `No Nomination Made`, Bergen `NO PETITION FILED`, once per
vacant seat. For those counties `seats_unfilled` is *observed*, not inferred.
Essex prints no such marker, so Essex's `seats_unfilled` is arithmetic.

## 2. What the real obstacle is

**These documents are ephemeral.** Candidate lists and sample ballots are
published for a cycle and then overwritten. Bergen's own Petitions page says the
unofficial candidate list "will be posted on our website" — it is not retained.
The Essex 2025 countywide ballot URL already returns 404. Historical depth
therefore depends on the Internet Archive, and that coverage is uneven:

- Bergen: 69–73 of ~70 municipalities archived for 2023, 2024, 2025;
  effectively nothing usable for 2019–2022.
- Essex: 2021 and 2024 have no countywide ballot PDF captured at all.
- Hunterdon: fine, because its documents sit at stable `DocumentCenter/View/<id>`
  URLs that are not overwritten.

This inverts the project's priorities. Backfill is bounded by what the archive
happens to hold and cannot be improved by more engineering. Going *forward*,
every uncaptured July–August filing window is a permanently lost cycle. A
scheduled harvester that sweeps all 21 counties each summer is the single
highest-value piece of work, and it is far cheaper than the parsers.

## 3. Second obstacle: parsers are per-county and per-era

Three counties needed three separate extractors, and format drift within a
county is as costly as the differences between counties:

| | |
|---|---|
| Essex | three font profiles for 2020 / 2022 / 2023+ — the county changed ballot typesetter. 2020 is archived but still unparsed. |
| Essex | contests appear both stacked and side-by-side on one page; contest boundaries had to be read from the drawn rules, not from text positions |
| Bergen | landscape in 2023, portrait in 2024; three different URL conventions in three years; filename spellings change (`FairLawn` → `Fair-Lawn`) |
| Hunterdon | table layout in 2022, outline in 2023–2026 |

All documents are text PDFs. **No OCR was needed anywhere**, which materially
lowers the cost estimate. What makes extraction tractable is that these are
typeset ballots where the font encodes the role — surname, given name, slogan
and contest header are each in a distinct face. That is reliable within a
county-era and worthless across them.

## 4. The denominator is not what it looks like

A rate computed from November ballots alone is wrong in a way that does not
announce itself. In Essex only 16–17 of 22 municipalities have a school board
contest in November: Newark elects its board at a separate school election with
its own document, and East Orange and Irvington are Type I districts with
appointed boards. Any published rate has to state which districts are in the
universe, and a full build needs the separate April/special school election
documents as well.

## 5. Results against the go/no-go criteria

| Criterion | Result |
|---|---|
| ≥2 of 3 counties yield seats + candidates for ≥3 cycles | **Pass** — all three. Hunterdon 4 (2023–26), Bergen 3 (2023–25), Essex 3 (2022, 2023, 2025) |
| Hand-checked accuracy ≥90% on `seats_available` and `candidates_filed` | **Pass** — 100% and 100% (n=15) |
| Per-county onboarding in hours, not days | **Pass, narrowly** — ~2h Hunterdon, ~4h Bergen, ~6h Essex, plus ~1–2h per additional format era |

### Hand-validation, 15 records

Five per county, spread across years. Hunterdon was checked by reading the
source text; Bergen and Essex by rendering the contest area of the ballot and
reading it by eye — not by re-running the parser.

| Field | Correct | Accuracy |
|---|---|---|
| `seats_available` | 15/15 | 100% |
| `candidates_filed` (exact name set) | 15/15 | 100% |
| `candidate_count` | 15/15 | 100% |
| `municipality` | 15/15 | 100% |
| `term_years` | 15/15 | 100% |
| `is_unexpired` | 15/15 | 100% |
| `is_uncontested` (derived) | 15/15 | 100% |
| `seats_unfilled` (derived) | 15/15 | 100% |
| `district_name` | 5/15 | **33%** |

`district_name` is the one weak field. For Bergen and Essex it currently holds
the ballot's contest label ("Local Board of Education"), which is not a district
identifier. The fix is a one-time municipality → district crosswalk; Hunterdon's
own 2022 document is exactly such a table. This does not touch any field the
analysis depends on.

## 6. What the numbers look like

Over the cells graded *complete* — 202 races. Bergen is excluded because this
probe pulled only 7–8 of ~70 municipalities per year, which is a sampling
artifact of the probe, not a limit of the source.

| County | Year | Races | Uncontested | Seats | Seats unfilled |
|---|---|---|---|---|---|
| Essex | 2022 | 18 | 4 (22.2%) | 41 | 0 |
| Essex | 2023 | 20 | 9 (45.0%) | 39 | 1 (2.6%) |
| Essex | 2025 | 16 | 7 (43.8%) | 38 | 0 |
| Hunterdon | 2023 | 34 | 18 (52.9%) | 67 | 4 (6.0%) |
| Hunterdon | 2024 | 40 | 24 (60.0%) | 72 | 6 (8.3%) |
| Hunterdon | 2025 | 37 | 25 (67.6%) | 70 | 12 (17.1%) |
| Hunterdon | 2026 | 37 | 30 (81.1%) | 70 | 8 (11.4%) |
| **All** | | **202** | **117 (57.9%)** | | |

Treat these as a demonstration that the pipeline computes the intended quantity,
not as a finding. Three counties is not New Jersey, and the apparent Hunterdon
trend rests on four points in one small rural county.

"Uncontested" here means candidates ≤ seats, which is the right definition: a
race with 2 candidates for 3 seats is uncontested *and* leaves a seat unfilled.

## 7. What full NJ coverage would actually cost

- **Harvester, all 21 counties, forward-looking:** 2–3 weeks. Highest value.
  Without it the dataset stops being extendable.
- **Extractors, 21 counties:** ~6h median per county-era. Assume 1.5 eras per
  county over a 5-cycle window → roughly 3–4 weeks of one person.
- **Archive triage and backfill:** 1–2 weeks, and the ceiling is fixed by what
  the Internet Archive holds. Expect several counties to have 1–3 usable cycles
  rather than 5.
- **District crosswalk and the non-November elections:** ~1 week.

Call it **8–10 weeks for one person** to get a publishable multi-cycle dataset,
with honest coverage gaps recorded rather than smoothed. The gaps are the
finding as much as the rates are.

### One thing worth checking before committing

Every county clerk holds these filings as records. A public-records request for
school board candidate filings, or a direct ask to the clerks' association,
might return in weeks what scraping recovers in months — and would reach the
years the Internet Archive missed. Worth a fortnight of asking before committing
to 21 parsers.

---

## Files

| Path | What |
|---|---|
| `notes/inventory.md` | Document inventory for the three counties |
| `data/coverage_matrix.csv` | county × year, source status vs. what this probe pulled, with reasons |
| `data/sample_school_board_races.csv` | 40-record stratified sample in the brief's schema |
| `data/extracted_full.json` | all 222 extracted races with provenance |
| `data/hand_validation.csv` | the 15 hand-checked records, per field |
| `scripts/parse_hunterdon.py` | candidate-list parser (text outline) |
| `scripts/parse_bergen_ballot.py` | sample-ballot extractor (header left of candidate grid) |
| `scripts/parse_essex_ballot.py` | sample-ballot extractor (header above candidates; 3 font profiles) |
| `scripts/build_dataset.py` | runs the extractors over `cache/`, dedups, derives fields |
| `scripts/coverage.py` | coverage matrix and rate summary |
| `cache/` | every raw document fetched, kept locally |

Scripts are throwaway probe code, as the brief allows. `build_dataset.py` and
`coverage.py` re-run offline from `cache/` with no network access.
