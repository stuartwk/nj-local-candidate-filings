`bergen_archived_stems.csv` — every Bergen sample-ballot path the Internet
Archive observed returning HTTP 200, as `directory,stem` (the URL's last two
segments, minus `.pdf`). Derived once from `cache/bergen/cdx-sample-ballots.txt`
and committed here because `cache/` is not tracked.

It is evidence, not configuration: `test_sources.py` uses it to assert that the
per-year path conventions in `sources.py` still generate URLs a server actually
answered. If a URL in `sources.py` stops matching this file, the convention was
changed without evidence for the change.
