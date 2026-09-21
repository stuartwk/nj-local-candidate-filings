"""Reading a typeset ballot by position and typeface.

A sample ballot is a grid, and its reading order is not its meaning. Extracting
the text of one Burlington page gives three school contests' headers in a run
followed by all their candidates in another run, with nothing to say which
candidate belongs to which contest. The page itself says so by *where it puts
them*, and that is what this module reads.

Two facts do the work, and both hold for every ballot this project has opened:

  * **Typeface encodes role.** A surname is set in bold condensed at ~13pt, a
    given name in condensed at ~9.5pt, a slogan smaller still. No text rule
    substitutes for this: on Salem's ballots an all-capital-surname rule drops
    `Loretta LaROY` and `Dennis McCARRON`, and on Burlington's there is nothing
    to distinguish `Hoggan` from `Children. Community. Accountability.` except
    the type.
  * **A contest claims what is to its right.** The header sits at the left of
    its row band and its candidates run rightwards. Where a page carries several
    contests side by side, the next header begins where the previous contest's
    candidates end — so a candidate belongs to the nearest header to its left
    within the same band.

Burlington and Bergen share a typesetter (`UniversLTStd-BoldCn`), so this is
written to be shared rather than copied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# how far apart two things can sit vertically and still be the same row band
BAND = 40.0


@dataclass(frozen=True)
class Item:
    """One line of a page, with where it is and how it is set."""

    text: str
    x: float
    y: float
    font: str
    size: float

    def is_(self, font: str, min_size: float = 0.0) -> bool:
        return font in self.font and self.size >= min_size


def items_of(page) -> list[Item]:
    """Every line on a page, in position order rather than reading order."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line["spans"]
            text = "".join(s["text"] for s in spans).strip()
            if not text or not spans:
                continue
            out.append(Item(text, line["bbox"][0], line["bbox"][1],
                            spans[0]["font"], spans[0]["size"]))
    # Ballots layer text: the same line is often drawn twice at the same spot,
    # which would double a contest and its candidates.
    seen, unique = set(), []
    for item in sorted(out, key=lambda i: (i.y, i.x)):
        key = (round(item.x, 1), round(item.y, 1), item.text)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def nearest_above(items: list[Item], anchor: Item, font: str,
                  within: float = 30.0, x_tolerance: float = 60.0) -> Item | None:
    """The closest line above `anchor`, in the same column, set in `font`."""
    candidates = [i for i in items
                  if i.is_(font) and 0 < anchor.y - i.y <= within
                  and abs(i.x - anchor.x) <= x_tolerance]
    return max(candidates, key=lambda i: i.y) if candidates else None


def nearest_below(items: list[Item], anchor: Item, pattern: re.Pattern,
                  within: float = 30.0, x_tolerance: float = 60.0) -> Item | None:
    candidates = [i for i in items
                  if pattern.search(i.text) and 0 < i.y - anchor.y <= within
                  and abs(i.x - anchor.x) <= x_tolerance]
    return min(candidates, key=lambda i: i.y) if candidates else None


@dataclass(frozen=True)
class Block:
    """A contest's heading: where it sits, and how far down it reaches.

    `y` is the middle of the heading rather than its first line, because a
    contest's header is set vertically centred in its row band — Burlington's
    county commissioners have two candidates above their heading and two below.
    """

    x: float
    y: float
    label: str


def owner_of(blocks: list[Block], thing: Item,
             same_band: float = 25.0) -> Block | None:
    """Which contest a candidate belongs to.

    Two rules, and both are needed:

      * **Nothing may stand between them.** If another contest's heading lies
        between this one and the candidate, at much the same height, then the
        candidate is in that contest's column, not this one. This is what
        separates three school contests printed side by side in one band.
      * **Otherwise, nearest by height.** Where contests are stacked down the
        page their headings are only ~40pt apart while a name spans ~20pt, so
        the bands overlap and the closest heading is the right one. Ties are
        broken by the nearer heading horizontally.

    Vertical distance has to come first. Judging by horizontal distance alone
    files every candidate under whichever contest's heading happens to start
    furthest right, which put Burlington's congressional candidates under
    `United States Senator`.
    """
    left = [b for b in blocks if b.x < thing.x]
    unobstructed = [
        b for b in left
        if not any(b.x < other.x < thing.x
                   and abs(other.y - thing.y) < same_band
                   for other in left)
    ]
    candidates = unobstructed or left
    if not candidates:
        return None
    return min(candidates,
               key=lambda b: (abs(b.y - thing.y), thing.x - b.x))


def full_name(items: list[Item], surname: Item, given_font: str,
              given_size: float, within: float = 14.0,
              x_tolerance: float = 40.0) -> str:
    """A surname plus the given name set just above it.

    Returns the surname alone if nothing is above it — better a partial name
    than an invented one.
    """
    above = [i for i in items
             if i.is_(given_font) and abs(i.size - given_size) < 1.5
             and 0 < surname.y - i.y <= within
             and abs(i.x - surname.x) <= x_tolerance]
    if not above:
        return surname.text
    given = max(above, key=lambda i: i.y)
    return re.sub(r"\s+", " ", f"{given.text} {surname.text}").strip()
