#!/usr/bin/env python3
"""Deterministic parser for Hunterdon County 'School Board Candidates' PDFs.

These are text PDFs in a flat outline:
    <DISTRICT HEADER, all caps>
    <MUNICIPALITY, all caps>
    School Board Member - <term> - Vote for <N>
    <candidate name> <address> <email>
    [slogan, indented]
    ...
`No Nomination Made` marks a seat with no filing.
"""
import re, sys, json

NUMWORD = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
           "eight":8,"nine":9,"ten":10}

CONTEST_RE = re.compile(r"vote\s*for\s+(\w+)", re.I)
TERM_RE    = re.compile(r"(\d+)\s*yr\.?\s*(term|unexpired)", re.I)
DISTRICT_HDR = re.compile(r"REGIONAL|SCHOOL DIST|HIGH SCHOOL|LOCAL DISTRICTS", re.I)
# every NJ municipality name carries one of these; ballot slogans do not
MUNI_RE  = re.compile(r"\b(TOWNSHIP|TOWNSHP|TWP|BOROUGH|BORO|TOWN|CITY|VILLAGE)\b", re.I)
CROSSREF = re.compile(r"-?\s*SEE\s", re.I)
LOCAL_RE = re.compile(r"LOCAL DISTRICTS", re.I)
EMAIL_RE   = re.compile(r"[\w.\-+']+@[\w.\-]+\.\w+")
SKIP       = re.compile(r"HUNTERDON COUNTY$|ANNUAL SCHOOL ELECTION|Poll Hours|^\d{1,2}/\d{1,2}/\d{2,4}$|Italic-Joint|BALLOT DRAW", re.I)


def is_caps(line):
    letters = [c for c in line if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.85


def parse(path, county, year, election_type, source_url, source_doc):
    raw = open(path, encoding="utf-8", errors="replace").read()
    lines = [l.rstrip() for l in raw.splitlines()]

    district = None          # regional section header (centred in the source)
    group = None             # local-section group label, e.g. FLEMINGTON-RARITAN
    group_fresh = False
    local_mode = False
    municipality = None
    records = []
    cur = None

    def flush():
        if cur and cur["seats_available"]:
            records.append(cur)

    for raw_line in lines:
        line = raw_line.strip()
        if not line or SKIP.search(line):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())

        m = CONTEST_RE.search(line)
        if m and re.search(r"school board member|yr\.?\s*(term|unexpired)", line, re.I):
            flush()
            seats = NUMWORD.get(m.group(1).lower())
            if seats is None:
                try: seats = int(m.group(1))
                except ValueError: seats = None
            tm = TERM_RE.search(line)
            term_years = int(tm.group(1)) if tm else None
            unexpired = bool(tm and tm.group(2).lower() == "unexpired") or \
                        bool(re.search(r"unexpired", line, re.I))
            # municipality sometimes prefixes the contest line
            head = re.split(r"school board member|\s[–-]\s*\d+\s*yr", line, flags=re.I)[0]
            head = head.strip(" -–—_")
            if head and len(head) > 2:
                municipality = head.upper()
            if district:
                dname, dconf = district.title(), "stated"
            elif group and group_fresh:
                dname, dconf = group.title(), "stated"
            elif group:
                dname, dconf = group.title(), "uncertain"
            else:
                dname, dconf = f"{(municipality or '').title()} School District", "inferred"
            cur = dict(county=county, year=year, election_type=election_type,
                       municipality=(municipality or "").title(),
                       district_name=dname, district_name_confidence=dconf,
                       office="School Board Member",
                       term_years=term_years, is_unexpired=unexpired,
                       seats_available=seats, candidates_filed=[],
                       no_nomination_count=0,
                       source_url=source_url, source_document=source_doc,
                       source_page=1)
            continue

        if re.fullmatch(r"no nomination made\.?", line, re.I):
            if cur: cur["no_nomination_count"] += 1
            continue

        # a few municipality headings are set in mixed case ("Stockton Borough-")
        if (not is_caps(line) and not EMAIL_RE.search(line)
                and not re.search(r"\d", line) and len(line) < 60
                and MUNI_RE.search(line) and not CROSSREF.search(line)
                and not re.search(r"school board member", line, re.I)):
            flush(); cur = None
            municipality = line.strip(" -–—_").upper()
            continue

        if is_caps(line) and not EMAIL_RE.search(line):
            # A cross-reference line ("RARITAN TOWNSHIP-SEE FLEMINGTON-RARITAN
            # ...") is a pointer, not a heading: it carries no contest.
            if CROSSREF.search(line):
                continue
            is_heading = bool(MUNI_RE.search(line) or DISTRICT_HDR.search(line))
            if not is_heading:
                continue            # an all-caps ballot slogan, not a heading
            flush(); cur = None
            if LOCAL_RE.search(line):
                local_mode, district, group = True, None, None
                continue
            if indent >= 10 and not local_mode:
                district, group = line, None       # centred regional header
            elif DISTRICT_HDR.search(line) and not MUNI_RE.search(line):
                group, group_fresh, district = line, True, None
            else:
                municipality = line
                if group and not group_fresh:
                    pass            # still possibly inside the group; uncertain
                group_fresh = False if group else group_fresh
            continue

        # candidate line: has an email, or looks like "Name <number> <street>"
        if cur is not None:
            if EMAIL_RE.search(line) or re.search(r"^[A-Z][A-Za-z.'\-]+ .*\b\d+\b.*(Rd|St|Ave|Dr|Ln|Ct|Ter|Way|Cir|Pl|Blvd|Tr|Rte|Road|Street)\b", line):
                withdrew = bool(re.search(r"withdrew", line, re.I))
                name = EMAIL_RE.sub("", line)
                name = re.split(r"\s\d", name, maxsplit=1)[0].strip()
                name = re.sub(r"\s*withdrew.*$", "", name, flags=re.I).strip()
                if name:
                    cur["candidates_filed"].append(
                        {"name": name, "withdrew": withdrew})
    flush()
    return records


if __name__ == "__main__":
    recs = parse(*sys.argv[1:7])
    json.dump(recs, sys.stdout, indent=1)
