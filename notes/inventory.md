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
