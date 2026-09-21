#!/usr/bin/env python3
"""Extract Board of Education contests from Bergen County sample ballot PDFs.

Bergen ballots are InDesign-typeset grids. Font encodes role, which is what
makes deterministic extraction possible:
    surname       UniversLTStd-BoldCn   ~13.6pt
    given name    UniversLTStd-Cn       ~9.7pt
    slogan        HelveticaNeueLTStd-Cn ~6.9pt
    write-in      HelveticaNeueLTStd-Cn ~4.9pt
The contest header sits vertically centred in its own row band, to the LEFT of
the candidate columns, so candidates are assigned to the nearest header by y.
"""
import re, sys, json, os
import pdfplumber

NUMWORD = {"ONE":1,"TWO":2,"THREE":3,"FOUR":4,"FIVE":5,"SIX":6,"SEVEN":7,
           "EIGHT":8,"NINE":9,"TEN":10}
BOE_RE  = re.compile(r"board\s+of\s+education", re.I)
# bold-condensed type is also used for ballot boilerplate; reject those runs
NOT_A_NAME = re.compile(
    r"personal choice|selecci|write[- ]in|escriba|ballot|balota|elecciones|"
    r"m.quinas|voting machines|sample|muestra|instruction|column|columna|"
    r"vote for|vote por|official|oficial|school election|elecci.n escolar|non-?partisan|no partidaria", re.I)
VOTEFOR_RE = re.compile(r"VOTE\s+FOR\s+([A-Z]+)", re.I)


def lines_of(words, tol=3.0):
    """Group words into visual lines."""
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if out and abs(w["top"] - out[-1][0]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    return [(top, sorted(ws, key=lambda w: w["x0"])) for top, ws in out]


def extract(path, county, year, election_type, municipality, source_url):
    doc = os.path.basename(path)
    recs = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            words = [w for w in page.extract_words(
                         extra_attrs=["fontname", "size", "upright"])
                     if w.get("upright", True)]
            rows = lines_of(words)
            texts = [(top, " ".join(w["text"] for w in ws), ws) for top, ws in rows]

            # --- locate BOE contest headers (English line) ---
            headers = []
            for i, (top, txt, ws) in enumerate(texts):
                if not BOE_RE.search(txt):
                    continue
                if re.search(r"Junta de Educaci|교육위원", txt):
                    continue
                # header detail line(s): term + "VOTE FOR n", within ~30pt below
                detail = ""
                for top2, txt2, _ in texts:
                    if not (0 <= top2 - top <= 40):
                        continue
                    for grp in re.findall(r"\(([^()]*)\)", txt2):
                        if VOTEFOR_RE.search(grp) and "VOTE POR" not in grp.upper():
                            detail = "(" + grp.strip() + ")"
                            break
                    if detail:
                        break
                m = VOTEFOR_RE.search(detail)
                seats = NUMWORD.get(m.group(1).upper()) if m else None
                # the header phrase only: contiguous run of words around
                # "Board of Education", broken by x-gaps > 25pt. Otherwise the
                # write-in legend further right gets swallowed into the header.
                anchor = next(i for i, w in enumerate(ws)
                              if w["text"].lower().startswith("educat"))
                face = ws[anchor]["fontname"]
                lo = hi = anchor
                while (lo > 0 and ws[lo]["x0"] - ws[lo-1]["x1"] <= 25
                       and ws[lo-1]["fontname"] == face):
                    lo -= 1
                while (hi < len(ws)-1 and ws[hi+1]["x0"] - ws[hi]["x1"] <= 25
                       and ws[hi+1]["fontname"] == face):
                    hi += 1
                run = ws[lo:hi+1]
                headers.append(dict(top=top,
                                    text=" ".join(w["text"] for w in run),
                                    detail=detail,
                                    seats=seats,
                                    x0=min(w["x0"] for w in run),
                                    x1=max(w["x1"] for w in run)))
            if not headers:
                continue

            # --- left edge of the school-election candidate grid ---
            # The ballot draws one long vertical rule separating the partisan
            # section from the non-partisan school section; that rule is the
            # exact boundary. Fall back to the "CANDIDATE / Column n" label row,
            # then to the header block's right edge.
            hdr_top = min(h["top"] for h in headers)
            rules = [l["x0"] for l in page.lines
                     if abs(l["x0"] - l["x1"]) < 1
                     and l["bottom"] - l["top"] > 100
                     and l["x0"] > page.width * 0.35
                     and l["top"] < hdr_top]
            col_labels = [w for w in words
                          if w["text"].upper() in ("CANDIDATE", "CANDIDATO")]
            if rules:
                hx_right = max(rules) - 3
            elif col_labels:
                hx_right = min(w["x0"] for w in col_labels) - 20
            else:
                hx_right = max(h["x1"] for h in headers)
            surnames = [w for w in words
                        if "BoldCn" in w["fontname"] and w["size"] > 11
                        and w["x0"] > hx_right]
            givens = [w for w in words
                      if "UniversLTStd-Cn" in w["fontname"] and 8 < w["size"] < 11
                      and w["x0"] > hx_right]

            # surname tokens on the same visual line + same column = one surname
            # Tokens of one name sit 2-6pt apart; adjacent ballot columns are
            # >30pt apart. A 20pt gap therefore splits columns cleanly, which a
            # synthetic grid does not (column labels are not column edges).
            def split_cols(ws, gap=20):
                col, cols = [ws[0]], []
                for w in ws[1:]:
                    if w["x0"] - col[-1]["x1"] > gap:
                        cols.append(col); col = [w]
                    else:
                        col.append(w)
                cols.append(col)
                return cols

            given_groups = []
            for gtop, gws in lines_of(givens, tol=2.5):
                for g in split_cols(gws):
                    given_groups.append(dict(
                        top=gtop, text=" ".join(w["text"] for w in g),
                        cx=(min(w["x0"] for w in g) + max(w["x1"] for w in g)) / 2))

            candidates = []
            no_petition = []
            for top, ws in lines_of(surnames, tol=2.5):
                for c in split_cols(ws):
                    sur = " ".join(w["text"] for w in c)
                    cx0, cx1 = min(w["x0"] for w in c), max(w["x1"] for w in c)
                    cx = (cx0 + cx1) / 2
                    if re.search(r"no petition|no nomination", sur, re.I):
                        no_petition.append(dict(top=top, x0=cx0)); continue
                    if (len(c) > 3 or len(sur) > 32
                            or NOT_A_NAME.search(sur)
                            or not re.search(r"[A-Za-z]{2}", sur)):
                        continue
                    # given names: the group just above, centred on the same column
                    gv = [g for g in given_groups
                          if 4 < top - g["top"] < 18 and abs(g["cx"] - cx) < 22]
                    given = " ".join(g["text"] for g in
                                     sorted(gv, key=lambda g: g["cx"]))
                    candidates.append(dict(name=(given + " " + sur).strip(),
                                           top=top, x0=cx0))

            for h in headers:
                h["cands"] = []
            # a candidate belongs to the header it is vertically nearest, but
            # only inside that header's own row band
            tops = sorted(h["top"] for h in headers)
            for c in candidates:
                h = min(headers, key=lambda h: abs(h["top"] - c["top"]))
                i = tops.index(h["top"])
                lo = (h["top"] + tops[i-1]) / 2 if i > 0 else h["top"] - 120
                hi = (h["top"] + tops[i+1]) / 2 if i < len(tops)-1 else h["top"] + 120
                if lo <= c["top"] <= hi:
                    h["cands"].append(c)
            for h in headers:
                h["nopet"] = 0
            for c in no_petition:
                h = min(headers, key=lambda h: abs(h["top"] - c["top"]))
                h["nopet"] += 1

            for h in headers:
                term = h["detail"]
                unexpired = bool(re.search(r"unexpired", term, re.I))
                tm = re.search(r"(\d+|ONE|TWO|THREE|FOUR|FIVE)\s+YEAR", term, re.I)
                recs.append(dict(
                    county=county, year=year, election_type=election_type,
                    municipality=municipality,
                    district_name=re.sub(r"^For (Members?h?i?p? (to|of) the )?", "",
                                         h["text"]).strip(),
                    office="School Board Member",
                    term_years=(int(tm.group(1)) if tm and tm.group(1).isdigit()
                                else NUMWORD.get(tm.group(1).upper()) if tm else None),
                    is_unexpired=unexpired,
                    seats_available=h["seats"],
                    candidates_filed=[{"name": c["name"], "withdrew": False}
                                      for c in sorted(h["cands"],
                                                      key=lambda c: (c["x0"], c["top"]))],
                    no_nomination_count=h["nopet"],
                    source_url=source_url, source_document=doc, source_page=pno,
                    header_text=h["text"], header_detail=h["detail"]))
    return recs


if __name__ == "__main__":
    json.dump(extract(*sys.argv[1:7]), sys.stdout, indent=1)
