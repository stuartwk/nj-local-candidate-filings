# New Jersey local candidate filings

How many candidates filed for how many available seats in New Jersey school
board elections.

The headline measure is **candidates per seat**: candidates filed divided by
seats available, for a county and year. A value near 1.0 means voters had
essentially no choice.

**Current coverage: 5 of New Jersey's 21 counties, 400 contests.** This is not a
statewide dataset and nothing here should be described as a New Jersey figure.

| | |
|---|---|
| `data/races.csv` | one row per contest — the dataset |
| `data/coverage.csv` | what is covered, what is not, and why |
| `data/manifest.csv` | every document fetched: URL, sha256, timestamp |
| `data/validation.csv` | sampled records checked against their source page |

## What was counted

Every school board contest on the November general election ballot in the
counties listed below, taken from two kinds of document and never from results.

**Candidate filing lists** (Atlantic, Hunterdon, Morris, Union) are what county
clerks publish after the July filing deadline. **Sample ballots** (Salem) are
what voters receive, one per municipality, with the school election as one
section among the municipal contests.

Both state the number of seats up for election independently of how many people
ran, and both print the seats nobody filed for. Results can do neither: they
cannot tell you a contest existed that drew no candidates, and they cannot tell
you three people ran for five seats.

```
county       year   contests  seats  cands  per seat  uncontested
atlantic     2026         30     59     62      1.05          73%
hunterdon    2023         34     67     88      1.31          53%
hunterdon    2024         40     72     94      1.31          57%
hunterdon    2025         37     70     80      1.14          68%
hunterdon    2026         37     70     72      1.03          81%
morris       2023         46    102    155      1.52          48%
morris       2024         47    104    129      1.24          57%
morris       2025         49    109    131      1.20          61%
morris       2026         48    105    128      1.22          71%
salem        2026         14     32     27      0.84          79%
union        2026         18     48     59      1.23          61%
```

Salem is the first county below 1.0: **fewer candidates than seats**, with a
quarter of its school board seats drawing nobody at all.

Over the two counties covered in **every** year, candidates per seat falls
1.44 → 1.27 → 1.18 → 1.14 from 2023 to 2026, while the share of uncontested
contests rises 50% → 75%. Restricting to those two counties is deliberate:
pooling whatever happens to be covered each year would confound a change in
candidates with a change in which counties were read.

### What is not counted

- **Districts that do not elect in November.** Some boards elect at a separate
  annual school election in April with its own documents. Newark is the largest.
- **Type I districts**, whose boards are appointed by the mayor rather than
  elected. East Orange and Irvington are examples.
- **Every office other than school board.** Two counties publish a general
  candidate list covering all offices; those documents are captured, because
  they vanish too, but they are not read.

## Definitions

**Uncontested** means `candidates ≤ seats`. Two candidates for three seats is
uncontested *and* under-filled; both are true at once and neither is an error.

**Seats available** is always read from the document, never inferred from the
number of candidates. Where a document does not state it, the field is empty and
every measure derived from it is empty too — a contest with one candidate is
never treated as a one-seat contest.

**Seats unfilled** is preferred from the document where it prints one
(`No Nomination Made`, `NO PETITION FILED`) and computed as `seats − candidates`
only where it does not. `seats_unfilled_observed` records which you are looking
at. **Every record in the current dataset is observed**; nothing is arithmetic.
That will stop being true when counties that publish only ballots are added, and
a rate mixing the two without saying so would be misleading.

**Withdrawals** are kept with the candidate and excluded from the count — a
withdrawn candidate is not running. Five appear in the current data.

## Known limitations

- **Coverage is uneven and small.** Five counties, and only 2026 for three of
  them. `data/coverage.csv` gives every county-year a status and a reason.
- **2026 lists are unofficial.** Hunterdon's is headed "UnOfficial"; Union's is
  watermarked "REFRAIN FROM PUBLISHING LITERATURE UNTIL POSITIONS ARE CONFIRMED
  SEPTEMBER 1ST" and dated 8/12/2026. Late withdrawals and corrections may not
  be reflected, so 2026 is not strictly comparable with settled years.
- **Morris comes through the Internet Archive.** Its clerk's site refuses HTTP
  clients, so all six Morris cycles were fetched from web.archive.org. The
  manifest records the Wayback URL that was requested and the clerk's own URL
  alongside it. The live 2026 file is a few days newer than the archived one.
- **Office titles differ by county** because the documents differ. Morris says
  "Member of the Board of Education" and distinguishes regional boards;
  Atlantic's document states no office title at all, so the label there is this
  project's, not a quotation.
- **448 captured documents are not yet read.** Bergen, Gloucester, Burlington,
  Cape May and Essex have no extractor at all, and Morris 2021-2022 use an older
  layout its extractor does not handle. They are absent from the dataset, not
  empty in it.
- **A shared school district is not always a shared contest.** Where two
  municipalities elect one board between them, the contest is printed on both
  ballots and recorded once, with the second printing cited in `also_on`. Where
  they each elect their own seat to a shared board, those are two contests. Salem
  contains both arrangements; the distinction is made on the contest's contents,
  not on its district's name.
- **Eleven of the twenty-one county sites refuse HTTP clients** outright. See
  `notes/inventory.md`.

## Reproducing it

```
uv run capture      # fetch declared documents into cache/, record in the manifest
uv run build        # extract cache/ into data/races.csv
uv run validate     # check the dataset against its sources
uv run coverage     # rebuild data/coverage.csv and print the rates
uv run pytest -q
```

`cache/` is not in this repository — it is 173 MB of county PDFs — but every
document in it can be re-fetched from the URL and checked against the sha256 in
`data/manifest.csv`. `build` reads only from `cache/` and never the network.

`data/races.csv` is sorted on a fixed key with fixed columns, so a diff shows
what actually changed rather than rows that moved. That diff is the review
mechanism when a parser changes.

## How it is checked

Two independent checks, because they catch different failures.

**Enumeration** counts the document's own repeating unit — every email address
belongs to exactly one candidate, every unfilled-seat marker is one unfilled
seat — and compares with the dataset. None of it reuses the parser, so a parser
that is confidently wrong does not get to grade itself.

**Transcription** samples records and checks every field against the page it
cites, writing the source text alongside in `data/validation.csv`.

The enumeration arm is the one that matters. Transcription cannot catch a
contest filed under the wrong municipality, and in this project it did not:
ten sampled records passed cleanly while three towns were attributed wrongly.

## Licence

Code MIT. Data CC-BY-4.0. The source documents are public records of the
respective county clerks.
