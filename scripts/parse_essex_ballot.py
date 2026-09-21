#!/usr/bin/env python3
"""Extract Board of Education contests from Essex County countywide sample
ballot PDFs (one page per municipality/ward).

Essex stacks the contest header ABOVE its candidate columns (Bergen puts it to
the left), so this is a separate extractor. Font again encodes role:
    municipality / section title  HelveticaNeueLT-107XBlkCn  20pt
    surname                       HelveticaNeueLT-107XBlkCn  13pt
    given name                    HelveticaNeueLT-57Cn       10pt
    contest header                HelveticaNeueLT-87HvCn     13pt
    term + "Vote for n"           HelveticaNeueLT-37ThCn     10pt
    slogan                        HelveticaNeueLT-47LtCnObl  7.5pt
"""
import re, sys, json, os
import pdfplumber

NUMWORD = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
           "eight":8,"nine":9,"ten":10}
BOE_RE = re.compile(r"Board\s+of\s+Education", re.I)

# Essex re-typeset its ballots between cycles, so role->font mapping is not
# stable across years. Each era needs its own profile; the right one is chosen
# per document by whichever yields the most BOE contest headers.
PROFILES = [
    dict(name="helv-2023",                       # 2023, 2025
         title=(r"107XBlkCn", 17, 99),
         hdr=(r"87HvCn", 12, 15),     thin=(r"37ThCn\b", 9.5, 11),
         sur=(r"107XBlkCn", 10.5, 15), giv=(r"57Cn", 8.5, 11.5)),
    dict(name="helv-2022",                       # 2022
         title=(r"HelveticaNeueLT-95Blk", 11, 14),
         hdr=(r"87HvCn", 11, 13),     thin=(r"37ThCn\b", 8.5, 9.5),
         sur=(r"107XBlkCn", 9.5, 13), giv=(r"57Cn", 8.5, 11)),
    dict(name="garamond-2020",                   # 2020 (different vendor)
         title=(r"TimesNewRomanPS-BoldMT|AGaramondPro-Bold", 13, 99),
         hdr=(r"GloucesterMT", 9, 12), thin=(r"AGaramondPro-Regular", 7.5, 8.5),
         sur=(r"AGaramondPro-Bold", 10.5, 11.5),
         giv=(r"AGaramondPro-Regular", 8.5, 9.5)),
]


def pick(words, spec):
    face, lo, hi = spec
    return [w for w in words
            if re.search(face, w["fontname"]) and lo <= w["size"] <= hi]


def lines_of(words, tol=3.0):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(w["top"] - out[-1][0]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    return [(t, sorted(ws, key=lambda w: w["x0"])) for t, ws in out]


BOILERPLATE = (r"School Election|Elecci|Official|Sample Ballot|Mail-?In|"
               r"Ejemplo|Papeleta|Tuesday|martes|Primary|Durkin|County Clerk|"
               r"Secretario")

SPANISH = re.compile(r"Miembros?|Consejo|Educaci|T.rmino|Vote por|Municipio|"
                     r"Inexpirado|Para ", re.I)


def blocks_of(words, dx=30, dy=20):
    """Connected-component grouping. A ballot header can wrap onto a second
    line and several contests can sit side by side on the same line, so
    neither a pure line grouping nor a pure column grouping is enough."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    parent = list(range(len(ws)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i

    for i, a in enumerate(ws):
        for j in range(i + 1, len(ws)):
            b = ws[j]
            if b["top"] - a["top"] > dy + 10:
                break
            same_line = abs(a["top"] - b["top"]) < 4
            gap = max(b["x0"] - a["x1"], a["x0"] - b["x1"])
            overlap = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
            if (same_line and gap <= dx) or \
               (not same_line and abs(a["top"] - b["top"]) <= dy and overlap > -dx):
                parent[find(i)] = find(j)

    groups = {}
    for i, w in enumerate(ws):
        groups.setdefault(find(i), []).append(w)
    out = []
    for g in groups.values():
        g.sort(key=lambda w: (w["top"], w["x0"]))
        out.append(dict(words=g, text=" ".join(w["text"] for w in g),
                        x0=min(w["x0"] for w in g), x1=max(w["x1"] for w in g),
                        top=min(w["top"] for w in g),
                        bottom=max(w["top"] for w in g)))
    return sorted(out, key=lambda b: (b["top"], b["x0"]))


def split_cols(ws, gap=18):
    col, cols = [ws[0]], []
    for w in ws[1:]:
        if w["x0"] - col[-1]["x1"] > gap:
            cols.append(col); col = [w]
        else:
            col.append(w)
    cols.append(col)
    return cols


def choose_profile(pdf):
    best, best_n = PROFILES[0], -1
    for prof in PROFILES:
        n = 0
        for page in pdf.pages[:12]:
            words = [w for w in page.extract_words(
                         extra_attrs=["fontname", "size", "upright"])
                     if w.get("upright", True)]
            # a profile only counts on a page where it resolves BOTH the
            # contest header and the municipality title, otherwise a profile
            # that half-matches a later era's ballots would win
            title = [w for w in pick(words, prof["title"])
                     if w["top"] < page.height * 0.30]
            if not any(not re.search(BOILERPLATE, " ".join(w["text"] for w in ws))
                       for _, ws in lines_of(title)):
                continue
            hdr = pick(words, prof["hdr"])
            n += sum(1 for b in blocks_of(hdr)
                     if BOE_RE.search(b["text"]) and not SPANISH.search(b["text"]))
        if n > best_n:
            best, best_n = prof, n
    return best


def extract(path, county, year, election_type, source_url):
    doc = os.path.basename(path)
    recs = []
    with pdfplumber.open(path) as pdf:
        prof = choose_profile(pdf)
        for pno, page in enumerate(pdf.pages, 1):
            words = [w for w in page.extract_words(
                         extra_attrs=["fontname", "size", "upright"])
                     if w.get("upright", True)]
            if not words:
                continue

            title = [w for w in pick(words, prof["title"])
                     if w["top"] < page.height * 0.30]
            muni = None
            for top, ws in lines_of(title):
                t = " ".join(w["text"] for w in ws)
                if re.search(BOILERPLATE, t, re.I):
                    continue
                muni = t
                break
            if not muni:
                continue

            hdr  = pick(words, prof["hdr"])
            thin = pick(words, prof["thin"])
            sur  = pick(words, prof["sur"])
            giv  = pick(words, prof["giv"])

            # Contest boundaries are drawn: a thin full-height rule separates
            # contests, while shorter rules only separate candidate columns
            # inside one contest. Using the drawn rules beats guessing midpoints
            # between header texts, which are not centred on their contests.
            vrects = [r for r in page.rects
                      if (r["x1"] - r["x0"]) < 4 and (r["bottom"] - r["top"]) > 40]

            hdr_blocks = [b for b in blocks_of(hdr) if not SPANISH.search(b["text"])]
            boe_blocks = [b for b in hdr_blocks if BOE_RE.search(b["text"])]
            if not boe_blocks:
                continue

            for b in boe_blocks:
                cx = (b["x0"] + b["x1"]) / 2

                sect = [r for r in vrects if r["top"] < b["top"] + 10
                        and r["bottom"] > b["bottom"] + 60]
                if sect:
                    depth = max(r["bottom"] for r in sect)
                    seps = sorted(r["x0"] for r in sect
                                  if r["bottom"] > depth - 30)
                else:
                    seps = []
                lo_x = max((x for x in seps if x < cx), default=0)
                hi_x = min((x for x in seps if x > cx), default=page.width)
                if hi_x - lo_x < 40:          # no usable rules: fall back to
                    row = [o for o in hdr_blocks                 # header gaps
                           if abs(o["top"] - b["top"]) < 25 and o is not b]
                    lo_x = max((o["x1"] for o in row if o["x1"] < b["x0"]),
                               default=0)
                    hi_x = min((o["x0"] for o in row if o["x0"] > b["x1"]),
                               default=page.width)

                # Candidate rows start below everything that belongs to the
                # header: the English detail lines and, when present, the whole
                # Spanish repeat. A fixed offset is wrong because some ballots
                # are English-only.
                detail, floor = "", b["bottom"] + 4
                for tb in blocks_of(thin, dx=25, dy=14):
                    if not (0 < tb["top"] - b["bottom"] < 45):
                        continue
                    if not (lo_x < (tb["x0"] + tb["x1"]) / 2 < hi_x):
                        continue
                    floor = max(floor, tb["bottom"] + 4)
                    if SPANISH.search(tb["text"]):
                        continue
                    detail = (detail + " " + tb["text"]).strip()
                for sb in blocks_of(hdr):
                    if SPANISH.search(sb["text"]) and 0 < sb["top"] - b["bottom"] < 45 \
                       and lo_x < (sb["x0"] + sb["x1"]) / 2 < hi_x:
                        floor = max(floor, sb["bottom"] + 4)

                seats = None
                m = re.search(r"Vote\s+for\s+(\w+)", detail, re.I)
                if m:
                    seats = NUMWORD.get(m.group(1).lower())
                    if seats is None:
                        try: seats = int(m.group(1))
                        except ValueError: pass
                tm = re.search(r"(\d+|\w+)\s+Year\s+(?:Term|Unexpired)", detail, re.I)
                term_years = (int(tm.group(1)) if tm and tm.group(1).isdigit()
                              else NUMWORD.get(tm.group(1).lower()) if tm else None)
                unexpired = bool(re.search(r"unexpired", detail, re.I))
                dm = re.sub(r"(Three|Two|One|Four|Five)\s+Year\s+Term|"
                            r"Unexpired\s+Term|Vote\s+for\s+\w+", "",
                            detail, flags=re.I).strip()

                # a contest stacked below this one ends its candidate block
                nxt = min((o["top"] for o in hdr_blocks
                           if o["top"] > b["bottom"] + 45
                           and lo_x < (o["x0"] + o["x1"]) / 2 < hi_x),
                          default=page.height)

                cands = []
                for t, ws2 in lines_of(giv):
                    if not (floor < t < nxt):
                        continue
                    for g in split_cols(ws2):
                        gx0, gx1 = min(w["x0"] for w in g), max(w["x1"] for w in g)
                        gcx = (gx0 + gx1) / 2
                        if not (lo_x < gcx < hi_x):
                            continue
                        given = " ".join(w["text"] for w in g)
                        sw = [w for w in sur
                              if 5 < w["top"] - t < 30
                              and abs((w["x0"] + w["x1"]) / 2 - gcx) < 40]
                        sw.sort(key=lambda w: (w["top"], w["x0"]))
                        surname = " ".join(w["text"] for w in sw).replace("- ", "-")
                        if not surname:
                            continue
                        cands.append(dict(name=f"{given} {surname}".strip(), cx=gcx))

                recs.append(dict(
                    county=county, year=year, election_type=election_type,
                    municipality=muni, district_name=dm or b["text"].strip(),
                    office="School Board Member",
                    term_years=term_years, is_unexpired=unexpired,
                    seats_available=seats,
                    candidates_filed=[{"name": c["name"], "withdrew": False}
                                      for c in sorted(cands, key=lambda c: c["cx"])],
                    no_nomination_count=None,
                    source_url=source_url, source_document=doc, source_page=pno,
                    header_text=b["text"].strip(), header_detail=detail))
    return recs


if __name__ == "__main__":
    json.dump(extract(*sys.argv[1:6]), sys.stdout, indent=1)
