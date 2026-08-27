"""Making extracted text safe for Excel, without destroying the evidence.

Text pulled out of a PDF is not clean text. Broken encodings, embedded binary,
form feeds between pages and stray control bytes all arrive in the middle of an
otherwise perfectly good sentence. Excel's XML format cannot carry any of them,
and openpyxl refuses:

    openpyxl.utils.exceptions.IllegalCharacterError

A run that has spent half an hour gathering evidence and then dies on one
control byte in one caption has lost everything, which is not an acceptable way
for this program to behave (brief §3).

Two rules govern what happens here.

**Only the Excel representation is cleaned.** The raw extracted text stays in
the database and in `05_extracted_text/` exactly as it arrived. The workbook is
a report, not the record — so sanitising a cell loses nothing that cannot be
recovered, and the evidence a coder audits later is still the bytes the source
actually served.

**Sanitising is recorded, never silent.** Every cleaned cell is counted, and the
count reaches the completion report and the workbook's own audit sheet. A reader
who wonders why a quotation reads oddly can see that it was cleaned, how many
characters went, and which sheet it was on.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: Characters XML 1.0 cannot represent at all. Tab (09), newline (0A) and
#: carriage return (0D) are legal and are deliberately kept: a multi-line
#: quotation should stay multi-line.
ILLEGAL_XML = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x84\x86-\x9F﷐-﷯￾￿]"
)

#: Unpaired surrogates. openpyxl accepts these into a cell without complaint and
#: then dies with a UnicodeEncodeError inside `save()` — after every sheet has
#: been written, which is the worst possible moment.
SURROGATES = re.compile(r"[\ud800-\udfff]")

#: Excel's own hard limit on the characters in one cell.
MAX_CELL_CHARS = 32767

#: What a cleaned character is replaced with. A space keeps word boundaries that
#: a form feed or a stray control byte was standing in for; deleting outright
#: would run the last word of one page into the first word of the next.
REPLACEMENT = " "


@dataclass
class Sanitisation:
    """What had to be cleaned, so the report can say so."""

    cells: int = 0
    characters: int = 0
    truncated_cells: int = 0
    by_sheet: dict[str, int] = field(default_factory=dict)
    #: A few real examples, for someone reading the audit sheet.
    samples: list[str] = field(default_factory=list)

    @property
    def occurred(self) -> bool:
        return self.cells > 0 or self.truncated_cells > 0

    def note(self, sheet: str, removed: int, *, truncated: bool = False,
             sample: str = "") -> None:
        if removed:
            self.cells += 1
            self.characters += removed
            self.by_sheet[sheet] = self.by_sheet.get(sheet, 0) + 1
        if truncated:
            self.truncated_cells += 1
        if sample and len(self.samples) < 5:
            self.samples.append(sample)

    def merge(self, other: "Sanitisation") -> None:
        self.cells += other.cells
        self.characters += other.characters
        self.truncated_cells += other.truncated_cells
        for sheet, count in other.by_sheet.items():
            self.by_sheet[sheet] = self.by_sheet.get(sheet, 0) + count
        for sample in other.samples:
            if len(self.samples) < 5:
                self.samples.append(sample)

    def summary(self) -> str:
        if not self.occurred:
            return "no cell needed sanitising"
        parts = []
        if self.cells:
            parts.append(f"{self.cells} cell(s) cleaned of {self.characters} "
                         "character(s) Excel cannot store")
        if self.truncated_cells:
            parts.append(f"{self.truncated_cells} cell(s) truncated at "
                         f"{MAX_CELL_CHARS} characters")
        where = ", ".join(f"{sheet} ({n})" for sheet, n in
                          sorted(self.by_sheet.items(), key=lambda kv: -kv[1])[:5])
        text = "; ".join(parts)
        if where:
            text += f" — {where}"
        return text + ". The unmodified text remains in the database and in " \
                      "05_extracted_text/."

    def as_dict(self) -> dict[str, Any]:
        return {
            "excel_sanitized": "yes" if self.occurred else "no",
            "cells_sanitized": self.cells,
            "characters_removed": self.characters,
            "cells_truncated": self.truncated_cells,
            "by_sheet": dict(self.by_sheet),
            "samples": list(self.samples),
            "summary": self.summary(),
        }


def clean_text(text: str, *, aggressive: bool = False) -> tuple[str, int]:
    """Return the text Excel can store, and how many characters were removed.

    ``aggressive`` is the fallback used only when a normal export has already
    failed: it additionally strips anything outside the Basic Multilingual Plane
    and normalises the result, which can alter legitimate text and so is never
    the first choice.
    """
    if not text:
        return text, 0

    original_length = len(text)
    cleaned = SURROGATES.sub(REPLACEMENT, text)
    cleaned = ILLEGAL_XML.sub(REPLACEMENT, cleaned)

    if aggressive:
        # Normalise first so accented characters survive as single code points,
        # then drop anything still outside the range Excel reliably handles.
        cleaned = unicodedata.normalize("NFC", cleaned)
        cleaned = "".join(
            ch if (ch in "\t\n\r" or (" " <= ch <= "퟿") or ("" <= ch <= "�"))
            else REPLACEMENT
            for ch in cleaned
        )

    removed = sum(1 for a, b in zip(text, cleaned) if a != b)
    if len(cleaned) != original_length:      # only possible if a rule deletes
        removed += abs(original_length - len(cleaned))
    return cleaned, removed


def clean_cell(value: Any, *, aggressive: bool = False) -> tuple[Any, int, bool]:
    """Make one value safe to write. Returns (value, characters removed, truncated).

    Non-text values pass through untouched: a number, a date or ``None`` cannot
    carry an illegal character, and coercing them to text here would undo the
    exporter's careful work of writing numbers as numbers.
    """
    if value is None or isinstance(value, (int, float, bool)):
        return value, 0, False
    if not isinstance(value, str):
        value = str(value)

    cleaned, removed = clean_text(value, aggressive=aggressive)
    truncated = False
    if len(cleaned) > MAX_CELL_CHARS:
        cleaned = cleaned[: MAX_CELL_CHARS - 15] + " […truncated]"
        truncated = True
    return cleaned, removed, truncated


def sanitise_row(row: Sequence[Any], *, sheet: str = "", log: Sanitisation | None = None,
                 aggressive: bool = False) -> list[Any]:
    """Clean a whole row, recording what happened."""
    out: list[Any] = []
    for value in row:
        cleaned, removed, truncated = clean_cell(value, aggressive=aggressive)
        if log is not None and (removed or truncated):
            sample = ""
            if removed and isinstance(value, str):
                sample = _sample(value)
            log.note(sheet, removed, truncated=truncated, sample=sample)
        out.append(cleaned)
    return out


def sanitise_workbook(workbook: Any, *, log: Sanitisation | None = None,
                      aggressive: bool = False) -> Sanitisation:
    """Sweep every cell of every sheet before saving.

    The exporter cleans values as it writes them, which is what makes the
    per-sheet counts meaningful. This is the safety net underneath that: it does
    not care which code path wrote a cell, so a value that reaches the workbook
    by a route nobody remembered still cannot take the run down. Formulas are
    left exactly as they are.
    """
    result = log if log is not None else Sanitisation()
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                value = cell.value
                if not isinstance(value, str) or not value:
                    continue
                if value.startswith("="):
                    continue                    # a formula is not text to clean
                cleaned, removed, truncated = clean_cell(value, aggressive=aggressive)
                if removed or truncated:
                    cell.value = cleaned
                    result.note(sheet.title, removed, truncated=truncated,
                                sample=_sample(value) if removed else "")
    return result


def _sample(value: str) -> str:
    """A short, readable illustration of what was cleaned."""
    match = ILLEGAL_XML.search(value) or SURROGATES.search(value)
    if match is None:
        return ""
    start = max(0, match.start() - 30)
    fragment = value[start: match.start() + 30]
    shown = "".join(
        ch if (ch.isprintable() or ch in " \t") else f"\\x{ord(ch):02x}"
        for ch in fragment
    )
    return shown.strip()[:120]


def find_illegal(value: Any) -> list[str]:
    """The illegal characters in a value, named. Used by tests and diagnostics."""
    if not isinstance(value, str):
        return []
    found = []
    for match in ILLEGAL_XML.finditer(value):
        found.append(f"U+{ord(match.group()):04X}")
    for match in SURROGATES.finditer(value):
        found.append(f"U+{ord(match.group()):04X} (unpaired surrogate)")
    return found
