# Document inventory — Essex, Bergen, Hunterdon

What exists, where, in what format. Everything below was fetched and opened;
nothing is inferred from a site's navigation labels.

## Statewide entry point

`nj.gov/state/elections/election-night-results.shtml` links all 21 counties, but
it is a **results** index. 14 of the 21 links point at hosted Clarity/SCYTL
result portals. Results cannot answer the question: they state neither the
number of seats nor the existence of a contest that drew no candidates. The
brief's instinct to build on filings rather than results is correct, and the
state's own index is no help in finding them.

## Hunterdon — best case

County clerk publishes a **single countywide school-board candidate list** per
cycle through a Laserfiche-style `DocumentCenter/View/<id>` URL.

| Year | Document | Format | Seats | Candidates | Unfilled |
|---|---|---|---|---|---|
| 2022 | `2022GeneralSchoolcandidates.pdf` | text PDF, 4-column table | stated | **absent** | n/a |
| 2023 | DocumentCenter/View/12466 | text PDF, outline | stated | stated | stated |
| 2024 | DocumentCenter/View/15174 | text PDF, outline | stated | stated | stated |
| 2025 | DocumentCenter/View/17067 (May, seats only) and /17436 (Aug, ballot draw) | text PDF, outline | stated | stated | stated |
| 2026 | DocumentCenter/View/20403 | text PDF, outline | stated | stated | stated |

- Seats are stated as `Vote for One` / `Vote for Three` on every contest line.
- Term length is stated and unexpired seats are labelled (`1 Yr. Unexpired`),
  so they are never conflated with full terms.
- **Unfilled seats are printed outright** as `No Nomination Made`, once per
  vacant seat. `seats_unfilled` is observed, not derived.
- The August 2025 document also annotates withdrawals (`withdrew 8/14/25`).
- Two documents per cycle: a pre-filing "offices up for election" notice and a
  post-filing ballot draw. Which one survives varies by year — 2022 left only
  the notice, so 2022 has seats but no candidates.
- The 2022 table is a clean **municipality → school district crosswalk**, which
  is what the later outline-format years lack.

## Bergen — good coverage, no archive of its own

No candidate list is published as a durable document. The Petitions page states
"Unofficial Candidate Lists are updated as petitions are received and will be
posted on our website", but nothing is retained after the cycle.

What is usable is the **per-municipality sample ballot**, one text PDF per
municipality per election, at predictable paths:

- 2023 `/_Content/pdf/voting/sample-ballots/2023/<Municipality>.pdf`
- 2024 `/_Content/pdf/voting/sample-ballots/2024-general/<Municipality>.pdf`
- 2025 `/_Content/pdf/voting/sample-ballots/2025/<Municipality>-Gen25.pdf`

The path convention, the filename convention (`FairLawn` vs `Fair-Lawn`) and the
page orientation all change between years.

Internet Archive coverage, counting distinct municipalities with HTTP 200:

| Year | Municipalities archived (~70 exist) |
|---|---|
| 2019 | 2 |
| 2020 | 0 usable (redirects only) |
| 2021 | 0 usable |
| 2022 | 0 |
| 2023 | 69 |
| 2024 | 72 |
| 2025 | 73 |

Ballot content: `For Membership to the Local Board of Education / (FULL THREE
YEAR TERM - VOTE FOR THREE)`, trilingual English/Spanish/Korean. Unfilled seats
print as **`NO PETITION FILED`** in the candidate column.

Caveat: the archived copies carry a **DRAFT** or **SAMPLE** watermark — they are
pre-certification proofs, so a late withdrawal would not be reflected.

## Essex — one big file, patchy archive

No candidate list document. The clerk publishes one **countywide sample-ballot
PDF** per general election, one page per municipality (or ward), with the school
election as a section on the page.

| Year | Status | Note |
|---|---|---|
| 2017, 2018 | archived | not parsed |
| 2019 | redirect only | |
| 2020 | archived | different typesetter (Garamond/Gloucester); needs a third parser profile |
| 2021 | **missing** | no countywide PDF captured |
| 2022 | archived, parsed | |
| 2023 | archived, parsed | |
| 2024 | **missing** | no countywide PDF captured under any filename |
| 2025 | archived, parsed | |

Filenames are reused and inconsistent (`Essex-Sample-Ballots.pdf`,
`SAMPLE-BALLOTS-2022.pdf`, `Essex-Sample-Ballots-General-Election.pdf`), and the
live site keeps only the current cycle — the 2025 URL already 404s.

Ballot content states `Three Year Term / Vote for Three` and labels
`Unexpired Term`. Essex does **not** print a marker for seats that drew no
candidates, so for Essex `seats_unfilled` is arithmetic (seats minus filings),
not an observed value.

**Denominator caveat:** only 16–17 of Essex's 22 municipalities have a school
board contest on the November ballot. Newark elects its board at a separate
school election with its own document; East Orange and Irvington are Type I
districts with appointed boards. A rate built from November ballots alone
silently drops them.

---

# Stage 2 discovery — remaining 18 counties

Status as of 2026-09-21. Same rule as above: every URL recorded here was
requested and its response inspected. Nothing is inferred from a nav label, and
a document nobody has fetched is marked as such.

## Headline finding: discrete school-board candidate lists are common

Hunterdon was assumed to be the lucky exception. It is not. **Atlantic, Morris,
Monmouth and Cumberland each publish a school-board candidate list as its own
document**, separate from any ballot. These are far cheaper to parse than sample
ballots — no typography heuristics, no ward de-duplication — and they state
seats directly.

Atlantic's is the best-structured source seen in this project so far. It is a
3-page text PDF with explicit columns:

    SCHOOL DISTRICT | TERM | # SEATS | CANDIDATE NAME | ADDRESS | EMAIL | SLOGAN
    Absecon         | 3 yr | V2      | Paige Kuenzner | ...

`V2`/`V3` is the seat count; `*` marks an incumbent. Seats are stated, not
derived. Whether unfilled seats are printed is still unverified.

This changes the Stage 5 ordering: counties publishing candidate lists should be
extracted before counties that only publish ballots, regardless of size.

## Captured

| County | Year | Document | Size | Notes |
|---|---|---|---|---|
| Atlantic | 2026 | school-board candidate list | 140 KB | text PDF, tabular, seats stated as `V2`/`V3` |
| Atlantic | 2026 | general candidate list | 152 KB | all offices; out of current scope, captured as it is equally ephemeral |
| Burlington | 2026 | countywide sample ballots | 8.9 MB | **2026 general already posted** |
| Burlington | 2025 | countywide sample ballots | 12.5 MB | prior cycles retained on the live site, unlike Essex |

Burlington's DocumentCenter answers on `co.burlington.nj.us`. The `www` host
redirects to `burlingtoncountynj.gov`, which 404s the same ids — the redirect is
a trap.

| Union | 2026 | school-board candidate list | 251 KB | 18 pp, per-municipality sections |
| Union | 2026 | general candidate list | 458 KB | all offices |

**Union states seats — resolved.** An earlier note here doubted it, having
looked only at page 1. Each contest carries a header `3 YEAR TERM - VOTE FOR
THREE` (18 of them in the 2026 file), and a district that drew nobody prints
`NO PETITION FILED`. So Union gives seats stated *and* unfilled seats observed,
putting it in the same class as Hunterdon rather than Essex.

Parser note: the separator between term and seats is inconsistent within a
single document - `TERM - VOTE FOR`, `TERM- VOTE FOR`, `TERM-VOTE FOR`, with the
dash sometimes an en-dash. Match loosely.

**Union is also provisional.** The captured file is headed "REFRAIN FROM
PUBLISHING LITERATURE UNTIL POSITIONS ARE CONFIRMED SEPTEMBER 1ST" and dated
8/12/2026. A confirmed list probably exists by now (today is 9/21) under a
different filename. Worth re-checking the page before relying on this copy.

## Blocked: document located, not fetchable over plain HTTP

These are not missing. The URL is known and a browser can open it; an HTTP
client cannot. Tested from the project's own IP, with both the project
User-Agent and a current Chrome User-Agent — the block is not UA-based.

| County | Document | Symptom |
|---|---|---|
| Morris | `2026-general-school-candidates-082126.pdf` | 403 from Akamai edge, both UAs |
| Cumberland | school-board candidates page; 2026 general ballots page | 403 on both `cumberlandcountyclerknj.gov` and mirror `ccclerknj.com` |
| Cape May | 2025/2024 general sample ballots; 2026 ballot draw results | HTTP 202 with an empty body — JS challenge |

Morris URL (confirmed to exist, blocked):
`https://www.morriscountyclerk.org/files/sharedassets/clerk/v/14/elections/past-results/2026-general-school-candidates-082126.pdf`

Cape May, confirmed to exist, blocked:
`https://www.capemaycountyvotes.com/wp-content/uploads/2026/08/1.-2026-Ballot-Draw-Results-EG-WEB-Final-1.pdf`
`https://www.capemaycountyvotes.com/wp-content/uploads/2025/09/Cape-May-Sample-Ballots-2025-General-Election.pdf`

This is a capture-architecture problem, not a discovery gap. See "Open
questions" below.

## Structure known, enumeration outstanding

| County | Shape | What is still needed |
|---|---|---|
| Camden | per-municipality PDFs, `wp-content/elections/primary2026/Sample-Ballots/<MUNI>.pdf` (~30 munis, some by ward) | 2026 **general** not yet posted; only the primary directory exists |
| Gloucester | 229 per-**district** ballots via `DocumentCenter/View/<id>`, labelled "UOCAVA GENERAL 26" | the 229 ids; also whether UOCAVA ballots differ from the regular sample ballot |
| Hudson | one page per election, `/<year>-general-election-sample-ballots/`, 15–36 ballot "form versions" per cycle | index is JS-driven and fetched empty; needs a browser |
| Monmouth | has an "Official Board of Education Candidates List" | site is JS-driven, fetched empty; document URL not yet obtained |
| Mercer | sample-ballot page identified | 403 on fetch |
| Middlesex | sample-ballot page identified | not yet fetched |
| Ocean | ballots on `co.ocean.nj.us/WebContentFiles/<guid>.pdf` | GUID filenames are unpredictable; needs an index page. **Ocean ballots print `NO PETITION FILED`**, so unfilled seats are observed, not derived |

## Located, not yet fetched

| County | Page | Note |
|---|---|---|
| Passaic | `/our-county/elections-and-voting/candidates/list-of-candidates` and a Sample Ballots service-directory page | 403 on fetch |
| Somerset | `/county-clerk/election-division/election-results` — candidate lists, sample ballots and winners **organised by year** | 403 on fetch; the by-year structure suggests a real archive, worth a browser visit |
| Salem | `salemcountyclerk.org/ballot-draw-results/` and `/see-whos-on-the-ballot/` | ballot-draw results are a candidate-list equivalent |
| Sussex | `sussexcountyclerk.org/212/Elections`, `/246/Sample-Ballots` (CivicPlus, so DocumentCenter ids are likely) | |
| Warren | `warrencountyvotes.com/candidates/elections-candidates-list` and `/elections/sample-ballots` | |

## Calendar, confirmed from county sources

- **Warren mails sample ballots 21 October 2026.** Other counties cluster around
  the same point, which puts the ballot-capture window in the last ten days of
  October — after the documents are posted, before the election.
- School-board candidate lists are already published (filing closed late July);
  Atlantic's is dated 8/13, Union's 8/12, Morris's 8/21.
- So there are two sweeps, not one: candidate lists **now**, sample ballots
  **late October**.

## Open questions

1. **Bot-protected counties.** Three so far, likely more. Options: drive a real
   browser for those hosts; have a human download and register the file into the
   manifest by hand; or fetch via the Internet Archive, which does not block us
   and which 2.3 already requires we populate. The Archive route is the only one
   that keeps capture unattended, but it only works for URLs already archived.
2. **UOCAVA vs regular ballots** (Gloucester). Overseas ballots may omit or
   reorder contests. Needs one document opened before trusting the source.
3. **Camden's general-election directory name** is unknown until it is posted.

---

## Sweep complete — status of all 21 counties (2026-09-21)

### Capturable and captured (8 counties, 473 documents declared)

| County | Shape | 2026 status |
|---|---|---|
| Hunterdon | countywide candidate list, stable DocumentCenter ids | captured |
| Bergen | 70 municipal ballots/cycle, convention changes yearly | 2026 general not yet posted |
| Essex | countywide ballot PDF, filenames inconsistent | captured |
| Atlantic | **school-board candidate list**, tabular, seats stated | captured |
| Burlington | countywide ballot PDF, prior cycles retained | captured, incl. 2026 general |
| Union | **school-board candidate list**, seats possibly absent | captured (provisional copy) |
| Salem | 16 municipal ballots, per-cycle form numbers (`Alloway-F01`) | captured |
| Gloucester | **229 per-district** UOCAVA ballots | captured |

Gloucester is the finest granularity encountered: one ballot per voting
district, not per municipality. A sample was opened and confirmed to carry a
`BOARD OF EDUCATION` contest with `VOTE FOR` stated, so the UOCAVA set is usable.

### Blocked by CDN / bot protection (11 counties)

The single biggest obstacle to Stage 2, and it is not a discovery problem: for
most of these the document URL is already known. Probed from the project's own
IP with both the project User-Agent and a current Chrome User-Agent.

| Mechanism | Counties | Symptom |
|---|---|---|
| Akamai (`AkamaiGHost`) | Morris, Warren, Passaic, Somerset, Mercer, Middlesex, Cumberland | HTTP 403, ~450-byte "Access Denied" page |
| Cloudflare | Sussex | HTTP 403 |
| AWS ELB + JS challenge | Hudson, Monmouth, Cape May | HTTP 202, empty body |

Not User-Agent gating — a browser UA is refused identically. The block keys on
something a plain HTTP client cannot present (TLS fingerprint, or a prior
session), so httpx will not get through either.

Known-good URLs sitting behind these blocks:
- Morris 2026 school candidates:
  `morriscountyclerk.org/files/sharedassets/clerk/v/14/elections/past-results/2026-general-school-candidates-082126.pdf`
- Cape May 2026 ballot draw:
  `capemaycountyvotes.com/wp-content/uploads/2026/08/1.-2026-Ballot-Draw-Results-EG-WEB-Final-1.pdf`
- Somerset: candidate lists and ballots organised **by year** — the best archive
  found anywhere, and entirely out of reach over HTTP.

Monmouth and Cumberland are known to publish discrete school-board candidate
lists, which makes them high-value targets despite the block.

### Waiting on publication (2 counties)

| County | Note |
|---|---|
| Camden | per-municipality PDFs; only `wp-content/elections/primary2026/` exists so far. The general-election directory name is unknown until posted |
| Bergen | 2026 general not yet posted; four plausible conventions all 404 |

### Unreachable (1 county)

| County | Note |
|---|---|
| Ocean | both `oceancountyclerk.com` and `co.ocean.nj.us` fail to connect outright (curl exit, no HTTP status) — distinct from the 403/202 blocks. Retry from another network before concluding anything. Ocean ballots are known to print `NO PETITION FILED`, so it is worth the effort |

### What this means for Stage 2

Capture-by-HTTP reaches 10 of 21 counties. Half the state needs a different
acquisition path, and the Archive route in 2.3 is now load-bearing rather than a
nice-to-have.

---

## The Archive route — what it did and did not solve

`sources.archived()` fetches through `web.archive.org/web/<timestamp>id_/<url>`.
The `id_` modifier returns the original bytes rather than Wayback's rewritten
page, so the cache holds exactly what the clerk published. The pinned timestamp
matters: without one Wayback resolves to "latest", and the fetch stops being
reproducible. The manifest records the Wayback URL as `url` (that is the honest
provenance of those bytes) and carries the clerk's own URL in the note.

Coverage of the blocked hosts is real — Morris 3,751 archived files, Sussex
3,423, Hudson 2,570, Warren 1,870, Cape May 652 — but **coverage is not the same
as usefulness**, and the yield varied enormously.

### Morris — the best source in the state

Six cycles, 2021-2026, all school-board candidate lists. Deeper than any county
reachable directly. Two format eras:

- **2021-2022**: one block per candidate, seats inline as `(Vote for 3)` and
  term as `(For 3 yrs.)`
- **2023-2026**: tabular, columns `Municipality | CONTEST TITLE | Term (Yrs) |
  Vote For | District | ...`

Both state seats. 2023 and 2026 print `NO PETITION`, so unfilled seats are
observed. Unexpired terms are labelled throughout.

**Parser trap, found the hard way.** The column header is `Vote\xa0For` — a
non-breaking space, not a space. A parser matching `Vote For` finds nothing and
concludes the document does not state seats, which is the worst kind of failure:
silently wrong rather than loudly broken. The same file uses an ordinary space
between `(Yrs)` and `Vote`. Normalise `\xa0` to a space before matching anything
in these documents.

### Cape May — two cycles recovered

2022 and 2023 general sample ballots, countywide single PDFs, Essex-shaped.
2024/2025/2026 are not archived and the live site is blocked.

### The rest — archived, but the wrong documents

| County | What is archived | Usable? |
|---|---|---|
| Sussex | per-municipality **primary** sample ballots; school **results** back to 2004 | No — primaries carry no school board race, and results state neither seats nor unfilled contests |
| Warren | 2020 primary ballots; school election **results** 2004-2009 | No, same reason |
| Hudson | per-municipality primary ballots; one 2024 BOE sample | Marginal |
| Somerset | essentially nothing under the clerk's path | No |
| Cumberland | one primary candidate list (`.xlsx`) | No |
| Monmouth | nothing relevant; the Archive's own crawl of the site records **403** | No — the Archive is blocked too |

That last row is the important one: Wayback is subject to the same refusals we
are. Where a host started blocking before the Archive crawled it, there is
nothing to recover.

**Operational note:** archive.org returned "Temporarily Offline" partway through
this sweep. It recovered within minutes, but it is a single point of failure for
every county reached this way, and a scheduled capture will hit it eventually.
Capture already records that correctly as a failed fetch and moves on.

### Still unreached

Monmouth, Cumberland, Passaic, Mercer, Middlesex, Somerset, Sussex, Warren,
Hudson. For these the only remaining routes are a real browser, or a human
downloading by hand. Monmouth and Cumberland are the ones worth the effort: both
publish discrete school-board candidate lists.
