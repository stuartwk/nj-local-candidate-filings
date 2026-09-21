# Build plan — nj-local-candidate-filings

A staged plan for one person. Each stage is independently useful and ends with
something real. Stop after any stage and you still have a complete artifact.

**Read this whole file before starting a stage.** Do only the stage you are on.

---

## What we are building

A public dataset recording how many candidates filed for how many available
seats in New Jersey local elections, starting with school boards.

The headline measure is **candidates per seat**: total candidates filed divided
by total seats available, for a county and year. A value near 1.0 means voters
had essentially no choice. It is deliberately simple and robust — it is a ratio
of two sums, so it survives the parsing errors that would distort a per-race
"uncontested rate".

A secondary measure is the **uncontested rate**: the share of contests where
candidates ≤ seats. More intuitive, more fragile, reported with caveats.

The final product is a git repository containing CSVs, a README explaining what
was counted, and eventually a small static site. Not a database, not an API.

## Why the architecture looks like this

Source documents are **ephemeral**. County clerks overwrite candidate lists and
sample ballots each cycle and retain nothing. Some 2025 URLs already 404.
Historical recovery depends on the Internet Archive, which is patchy.

That single fact drives everything:

- **Capture is urgent; parsing is not.** A document not captured this cycle is
  gone forever. A document parsed wrongly can be reparsed from the cache.
- **Capture must never depend on parsing.** Capture has to succeed against a
  county whose format nobody has seen. If the two ever couple, a parser bug
  becomes permanent data loss.
- **Raw bytes are the source of truth.** Everything downstream is derived and
  regenerable.

## Ground rules

1. `capture` never imports from `extract`. Not once, not for convenience.
2. Never rebuild file contents from a truncated tool output. Open the file.
3. County differences live in `sources.py` as data, never as `if county ==`
   branches in logic.
4. Never infer a value that a document states. If the document says
   "Vote for Three", read it; do not derive it from the candidate count.
5. Never carry parser state forward implicitly. If a contest block does not
   state its district, record `None`, not the last district seen. (This exact
   bug silently corrupted an earlier prototype.)
6. Missing data is recorded as missing. Never imputed, never interpolated.
7. Every extracted record carries provenance: source URL, document, page.

---

# Stage 1 — Capture, three counties

**Goal:** raw documents on disk with a manifest proving where each came from.

**Why first:** it is the only urgent work, and it requires no decisions about
what counts as a race.

### 1.1 Project setup

- `uv init --package` in the existing directory; confirm branch is `main`
- Rename the package under `src/` to `njfilings`, updating `pyproject.toml`
- `uv add httpx`
- `.gitignore`: `cache/`, `.venv/`, `__pycache__/`, `*.pyc`
- Add `cache/.gitkeep`

### 1.2 `src/njfilings/sources.py`

Declarative definitions only. No fetching logic. Each county entry describes:

- county name and slug
- for each known year: how to build the document URL(s)
- document type (`candidate_list`, `sample_ballot`, `ballot_draw`, `seats_notice`)
- whether documents are per-county or per-municipality

Start with the three counties documented in `notes/inventory.md`:

- **Hunterdon** — one countywide candidate list per cycle at stable
  `DocumentCenter/View/<id>` URLs. IDs are listed in the inventory.
- **Bergen** — one sample ballot PDF per municipality. Path convention changes
  every year; filename spellings change (`FairLawn` vs `Fair-Lawn`). Needs a
  municipality list.
- **Essex** — one countywide sample-ballot PDF per general election. Filenames
  are inconsistent and reused across years.

Where a URL pattern is unknown for a given year, record the year as unknown
rather than guessing.

### 1.3 `src/njfilings/capture.py`

One job: fetch documents named by `sources.py`, save bytes, record what
happened.

Behaviour:

- Save to `cache/<county-slug>/<year>/<filename>`
- Append to `data/manifest.csv`: `url`, `sha256`, `fetched_at` (UTC ISO 8601),
  `county`, `year`, `doc_type`, `local_path`, `http_status`, `content_type`,
  `bytes`
- Skip the fetch entirely if a file with that sha256 is already cached
- Record changes, not heartbeats: a held document adds a manifest row only when
  its outcome differs from the last one recorded for that URL — first sight, or
  recovery after a failed fetch. An unchanged document on an unchanged run adds
  nothing. Every run still prints what it saw. (Stage 6 runs this daily for
  months across ~1,500 documents; a row per document per night would bury every
  real event in no-ops.)
- Rate limit to roughly 1 request/second per host
- Never raise on a single document's failure — record the status and continue.
  A 404 is data, not an error.
- Set a descriptive User-Agent identifying the project and a contact address
- No parsing. Do not open the PDFs.

### 1.4 Verify

- Run it. Confirm documents land in `cache/` and rows land in `data/manifest.csv`
- Re-run it. Confirm nothing re-downloads and the manifest is unchanged
- Delete one cached file and re-run. Confirm only that document is fetched again
- Manually open two cached PDFs and confirm they are what the manifest says

**Stage 1 is done when:** `uv run capture` fetches all known documents for three
counties, is safely re-runnable, and the manifest is committed.

---

# Stage 2 — Source discovery, remaining 18 counties

**Goal:** know what every New Jersey county publishes, and capture the 2026
cycle everywhere possible.

**Why now:** the 2026 documents are live on county sites right now. This is the
last chance to capture this cycle at full coverage.

### 2.1 Discovery

For each of the remaining 18 county clerks, find and record in
`notes/inventory.md`:

- URL of the elections/candidates page
- Whether a candidate filing list is published as a discrete document
- Whether sample ballots are published, and at what granularity
- Format: text PDF, scanned PDF (needs OCR), HTML, or hosted portal
  (Clarity/SCYTL)
- How far back the archive goes on the live site
- Whether seat counts ("Vote for Three") appear in the documents

Note: `nj.gov/state/elections/election-night-results.shtml` links all 21
counties but mostly to **results** portals, which cannot answer this question.
The clerk's own elections page is the target.

This is largely manual browsing. Do not try to automate discovery.

### 2.2 Extend sources and capture

- Add every county with usable documents to `sources.py`
- Run capture for 2026 across all of them
- Record counties with nothing usable, with the reason

### 2.3 Archive submission

For each captured URL, submit it to the Internet Archive's Save Page Now so a
public, citable copy exists independent of this repo.

**Stage 2 is done when:** `notes/inventory.md` covers all 21 counties and the
2026 cycle is captured wherever it exists.

---

# Stage 3 — First extractor

**Goal:** turn cached Hunterdon documents into structured records.

**Why Hunterdon first:** stable URLs, a single countywide document, seats stated
per contest, unfilled seats printed explicitly as `No Nomination Made`, and
withdrawals annotated. It is the easiest county and the best teacher.

### 3.1 `src/njfilings/model.py`

One record type per contest:

```
county, year, election_type, municipality, district_name,
office, term_years, is_unexpired,
seats_available, candidates_filed (list of name + withdrew flag),
seats_unfilled, seats_unfilled_observed (bool — stated vs derived),
source_url, source_document, source_page
```

`seats_unfilled_observed` matters: some counties print unfilled seats, others
require arithmetic. Never publish a figure mixing the two without saying so.

### 3.2 `src/njfilings/extract/hunterdon.py`

- Reads only from `cache/`. Never touches the network.
- `uv add pymupdf`
- Parse the outline format used 2023–2026
- Read seats from the stated "Vote for N", never derive it
- Treat unexpired-term contests as separate contests
- District name: read per contest block. If a block does not state one, emit
  `None`. **Do not inherit the previous block's district.**
- Preserve withdrawal annotations

### 3.3 `src/njfilings/build.py`

- Runs available extractors over `cache/`
- Writes `data/races.csv`
- **Sort deterministically** on `(county, year, municipality, district_name,
  is_unexpired, office)` and fix column order, so git diffs show real changes
  rather than reshuffled rows

### 3.4 Validate — two arms, both required

**Transcription:** pick 10 records at random, open the source PDF, confirm every
field. Record results in `data/validation.csv`.

**Enumeration:** pick 3 municipalities. From the source document, list every
contest that municipality should have. Confirm the dataset has exactly those,
no more and no fewer.

The second arm is not optional. Transcription checks cannot catch a race that
should not exist, a duplicate, or a contest attributed to the wrong
municipality — and those are the failures that actually occurred in the earlier
prototype.

**Stage 3 is done when:** `data/races.csv` contains Hunterdon 2023–2026, both
validation arms pass, and both are committed.

---

# Stage 4 — The first number

**Goal:** publish something.

### 4.1 `src/njfilings/coverage.py`

- Coverage matrix: county × year × office type, each cell complete / partial /
  missing, with a reason for anything not complete
- Candidates per seat, per county-year, computed only over complete cells
- Uncontested rate alongside it, clearly secondary

### 4.2 README

Written for someone who has never seen the project. Must state:

- What the dataset contains and where it came from
- **What was counted**: every school board contest appearing on the November
  general election ballot in the covered counties. Districts electing at other
  times (e.g. Newark) and Type I districts with appointed boards (e.g. East
  Orange, Irvington) are not included.
- How "uncontested" is defined: candidates ≤ seats. Two candidates for three
  seats is both uncontested and under-filled.
- Known limitations: some sources are pre-certification proofs marked DRAFT;
  some candidate lists are marked unofficial; coverage is uneven by county and
  year
- Licence: MIT for code, CC-BY-4.0 for data

That README section *is* the methodology. It does not need to be longer.

### 4.3 Publish

- Push to GitHub
- Optionally connect to Zenodo for a citable DOI

**Stage 4 is done when:** the repo is public and a stranger could reproduce the
numbers from what is written.

---

# Stage 5 — Remaining extractors

Repeat Stage 3 per county, in order of how much data each unlocks. Expect
roughly 2–6 hours each, plus 1–2 hours for every additional format era within a
county.

Formats drift *within* a county as much as between them. Essex changed ballot
typesetter and needs separate font profiles per era; Bergen changed page
orientation, URL convention and filename spelling in three consecutive years.
Treat each era as its own parser profile.

Run both validation arms per county. Do not skip the enumeration arm.

---

# Stage 6 — Scheduled capture

**Goal:** never lose another cycle.

- GitHub Actions workflow running `capture` on a schedule
- Frequent (daily) June–November, rare otherwise: NJ filing closes in late July
  and the general election is early November
- Commits new manifest rows and pushes new documents to storage
- Opens an issue on repeated fetch failures for a county — a silent failure here
  is how a cycle gets lost

Before switching capture to a schedule, shard the ledger: `data/manifest/<year>.csv`
rather than one growing `data/manifest.csv`. Change-only logging (1.3) keeps the
row count proportional to real events rather than to run frequency, but a
multi-year, 21-county ledger still belongs in per-cycle files — a cycle's
provenance should stay a file a person can open, and git history should stay
reviewable. Cheap to do before the first scheduled run; a migration afterwards.

Capture is automated. Extraction stays supervised: a county will break its
parser every few cycles and a human needs to notice.

---

# Stage 7 — Static site (optional)

Only if the data turns out to be interesting.

- Astro in `site/`, in this same repo, building from `data/races.csv`
- Static page per county for speed and search visibility
- Ship the dataset as JSON and filter client-side — it is about a megabyte, so
  no query engine, no Parquet, no DuckDB
- Same GitHub Action regenerates data then builds the site

There is no backend. The data is a build input, not a runtime dependency.

---

# Explicitly out of scope for now

- OPRA public-records requests (only needed for pre-2023 history)
- Offices other than school boards
- Any database
- Any API
- Any user accounts or saved state
