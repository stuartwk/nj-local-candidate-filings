# Feasibility probe: uncontested down-ballot races in New Jersey

## What this is

A scoping investigation, not a build. The goal is to determine whether it is
possible to compute, from publicly published New Jersey county clerk documents,
the share of local offices that go uncontested — and to do it reliably enough
to publish as a dataset.

**Deliverable: a go/no-go recommendation with evidence.** Do not build a
production pipeline. Do not build a web app. Throwaway scripts are expected and
fine.

## Background

New Jersey's Division of Elections does not centralize local election data. It
directs people to individual county clerk websites. There are 21 county clerks.
Each publishes its own archive, mostly as PDFs, many going back to the 2010s.

Critically: **this should be built on candidate filing lists, not results.**
Whether a race is uncontested is a filing fact (seats available vs. candidates
filed), not a results fact. Several counties publish candidate lists as separate
documents from results — e.g. "Official List of School Board Candidates,"
"Unofficial List of County and Local Candidates." Sample ballots are also
published by some counties and are valuable because they state the number of
seats directly ("Vote for two").

Known starting points:
- https://www.nj.gov/state/elections/election-night-results.shtml (links to all 21 county sites)
- https://www.essexclerk.com/election/
- https://www.mercercounty.org/government/county-clerk-/elections/archived-election-results
- https://www.bergencountyclerk.gov/Election/
- https://www.co.hunterdon.nj.us/994/ElectionVoter-History
- https://www.passaiccountynj.org/residents/election-and-voting-information/county-clerk-elections-division

## The core question

For a given county and election year, can you reliably obtain:

1. The list of **offices up for election** (municipality, body, district)
2. The **number of seats** available for each office
3. The **candidates who filed** for each office

If all three are obtainable, uncontested rate is computable. Item 2 is the
highest-risk element and the main thing this probe needs to resolve.

## Scope

**Office type:** School board only. It is the highest-volume local office, most
likely to be uncontested, and most likely to be published as a discrete
candidate list.

**Counties:** Sample three, chosen for *variance* rather than convenience. One
large urban (Essex), one suburban (Mercer or Bergen), one small/rural
(Hunterdon, Salem, or Cape May). The point is to find out how different counties
are from each other, so do not pick three easy ones.

**Years:** Target five cycles. Accept fewer if archives are shallow; record what
is actually available.

## Tasks

1. **Inventory.** For each sample county, catalogue what documents exist, for
   which years, in what format (HTML table, text PDF, scanned PDF, portal like
   Clarity/SCYTL). Note whether candidate lists exist separately from results,
   and whether sample ballots are published.

2. **Extract.** Pull a small sample — roughly 30 school board races across the
   three counties and several years — into this schema:

   ```
   county, year, election_type, municipality, district_name,
   office, seats_available, candidates_filed (list),
   is_uncontested, seats_unfilled,
   source_url, source_document, source_page
   ```

   Every record carries provenance. Nothing is inferred without being marked as
   inferred.

3. **Solve or fail on `seats_available`.** This is the crux. Investigate which
   sources actually state it: sample ballots ("Vote for two"), the candidate
   list itself, board composition pages, prior results. Note the complication
   that NJ school boards typically run staggered three-year terms and often have
   separate "unexpired term" seats on the same ballot, which must not be
   conflated with full-term seats.

4. **Validate by hand.** Manually verify at least 15 of the extracted records
   against the source document. Report accuracy per field. Do not report an
   accuracy figure that was not hand-checked.

5. **Build a coverage matrix.** county × year × office type, each cell marked
   complete / partial / missing, with the reason for anything not complete.
   Counties will differ wildly; record that difference rather than smoothing it.
   Never impute missing data. Compute rates only over covered cells.

6. **Report.** Go/no-go, with the evidence above.

## Go / no-go criteria

Proceed to a full build only if:

- At least 2 of 3 sample counties yield seats + candidates for at least 3 cycles
- Hand-checked extraction accuracy on `seats_available` and `candidates_filed`
  is at or above 90%
- The per-county work to onboard a new county looks like hours, not days

If `seats_available` cannot be reliably determined, say so plainly and stop.
That is a valid and useful outcome for this probe.

## Method notes

- Structured extraction into a typed schema, not summarization. Every field
  should trace to a source span or document location.
- Deterministic parsing first where documents are HTML or structured; LLM
  extraction as the fallback for prose and PDFs.
- Cache every raw document locally on first fetch. Do not re-hit county sites
  repeatedly. Rate limit politely; these are small government servers.
- Some counties use hosted portals (Clarity/SCYTL). Check whether those expose
  JSON endpoints before scraping rendered pages.
- Scanned PDFs may need OCR. Note which counties require it, since that
  materially changes the cost of full coverage.

## Explicit non-goals

- No web app, dashboard, or UI
- No coverage beyond the three sample counties
- No office types beyond school board
- No production data pipeline or scheduler
- No publishing infrastructure

## What to hand back

1. The coverage inventory for the three counties
2. The ~30-record sample dataset as CSV
3. Hand-validation results with per-field accuracy
4. The coverage matrix
5. A short written recommendation: is this viable, what is the main obstacle,
   and what would full NJ coverage actually cost in effort
