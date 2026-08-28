"""Undoing the text damage in the original export.

The export was decoded as cp1252 and re-encoded as UTF-8 - twice for some
rows - and two further things happened on the way:

* non-breaking spaces produced by the first pass were flattened to ordinary
  spaces, so an a-grave shows as U+00C3 followed by *two* spaces rather than
  U+00C3 followed by NBSP and a space;
* one smart quote was HTML-escaped, so an en dash shows as U+00E2 U+20AC
  followed by `&quot;`.

Both are put back before ftfy runs, because ftfy reverses the encoding damage
and cannot reverse damage done after it. Every repair is recorded: the master
file keeps the original string alongside the repaired one.
"""
from __future__ import annotations

import html
import re

import ftfy

#: U+00C3 / U+00C2 followed by two spaces is the character, a flattened
#: no-break space, and a real space. Putting the NBSP back lets the cp1252
#: round-trip consume it and keep the space that belongs to the name.
_NBSP_ARTEFACT = re.compile("([ÃÂ])  ")

#: U+00E2 U+20AC followed by an escaped double quote is the byte sequence
#: E2 80 93 - an en dash. The escaper mapped cp1252 0x93, a left smart quote,
#: onto `&quot;`, which `html.unescape` would turn into a straight quote and
#: ftfy could then no longer decode.
_ESCAPED_DASH = re.compile("â€(?:&quot;|&#34;)")

#: What the en dash above looks like before the round-trip: U+00E2 U+20AC
#: U+201C, whose cp1252 bytes are E2 80 93.
_DASH_MOJIBAKE = "â€“"


def repair(text: str) -> str:
    """Return `text` with mojibake and HTML escaping undone.

    Idempotent: a clean string is returned unchanged, so it is safe to run
    over every name rather than only the ones that look damaged.
    """
    out = text
    for _ in range(3):
        before = out
        out = _ESCAPED_DASH.sub(_DASH_MOJIBAKE, out)
        out = _NBSP_ARTEFACT.sub(lambda m: m.group(1) + "  ", out)
        out = html.unescape(out)
        out = ftfy.fix_text(out, normalization="NFC")
        if out == before:
            break
    out = out.replace(" ", " ")
    return re.sub(r"\s+", " ", out).strip()
