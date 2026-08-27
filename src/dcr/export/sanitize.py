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

import datetime as _datetime
import decimal
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

#: Excel's limit on a worksheet name, and the characters it forbids in one.
#: A title is not a cell, so `sanitise_workbook`'s cell sweep never saw it — and
#: an illegal one fails inside `save()`, after every sheet has been written,
#: which is the same late failure the original bug had.
MAX_SHEET_TITLE = 31
ILLEGAL_SHEET_TITLE = re.compile(r"[\[\]:*?/\\]")

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

    Three kinds of value can kill an export, and only the first announces itself
    at assignment. The other two get all the way into `save()` — after every
    sheet has been written — which is precisely the failure mode that lost a
    run's work in the first place (brief §11, §13).

    **Text with characters XML cannot carry.** Raises `IllegalCharacterError`
    the moment it is assigned to a cell.

    **A timezone-aware datetime.** Assigns without complaint; raises
    ``Excel does not support timezones in datetimes`` inside `save()`. A
    retrieval timestamp is the obvious way one arrives. The moment is kept and
    only the `tzinfo` is dropped, because the alternative — converting to UTC
    and shifting the clock — would silently change a recorded date.

    **A type Excel has no idea about.** A dict, a list, a Path from a code path
    that expected a string: ``Cannot convert {...} to Excel``, again at
    assignment. Turned into its text and cleaned like any other text.

    Numbers pass through as numbers. Coercing them to text here would undo the
    exporter's careful work of writing an area as a number a formula can use.
    """
    if value is None or isinstance(value, (int, float, bool)):
        return value, 0, False

    if isinstance(value, decimal.Decimal):
        # A managed area must stay a number: the workbook's own formulas read it.
        try:
            return float(value), 0, False
        except (ValueError, ArithmeticError):
            value = str(value)

    if isinstance(value, (_datetime.datetime, _datetime.time)):
        if value.tzinfo is not None:
            return value.replace(tzinfo=None), 0, False
        return value, 0, False
    if isinstance(value, _datetime.date):
        return value, 0, False

    if not isinstance(value, str):
        value = str(value)

    cleaned, removed = clean_text(value, aggressive=aggressive)
    truncated = False
    if len(cleaned) > MAX_CELL_CHARS:
        cleaned = cleaned[: MAX_CELL_CHARS - 15] + " […truncated]"
        truncated = True
    return cleaned, removed, truncated


def safe_sheet_title(title: Any, *, fallback: str = "Sheet") -> str:
    """A worksheet name Excel will accept.

    Control characters fail inside `save()`; the six characters Excel reserves
    for cell references fail there too. Both are replaced rather than dropped
    where a reader would otherwise lose a word boundary.
    """
    text = "" if title is None else str(title)
    text, _ = clean_text(text)
    text = text.replace(REPLACEMENT, "")
    text = ILLEGAL_SHEET_TITLE.sub("-", text)
    text = text.strip().strip("'")
    if not text:
        return fallback
    return text[:MAX_SHEET_TITLE]


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
    """Sweep everything that can fail at save time, before saving.

    The exporter writes through :class:`SafeSheet`, which is what makes the
    per-sheet counts meaningful. This is the net underneath that, and it does
    not care which code path produced a value — so something arriving by a route
    nobody remembered still cannot take a run's work down at the last step.

    Worksheet TITLES are swept as well as cells. A title is not a cell, so the
    cell sweep never saw one, and an illegal character in a title fails inside
    `save()` exactly as the original bug did.
    """
    result = log if log is not None else Sanitisation()
    for sheet in workbook.worksheets:
        title = sheet.title
        safe = safe_sheet_title(title)
        if safe != title:
            # Assigning through `.title` re-validates and would raise; the
            # private attribute is the only way to repair a title that is
            # already wrong.
            try:
                sheet.title = safe
            except Exception:
                sheet._WorkbookChild__title = safe          # noqa: SLF001
            result.note(safe, len(title) - len(safe) if len(title) > len(safe) else 1,
                        sample=f"sheet title {title!r} renamed to {safe!r}")
        for row in sheet.iter_rows():
            for cell in row:
                value = cell.value
                if value is None:
                    continue
                if isinstance(value, str):
                    if not value or value.startswith("="):
                        continue          # a formula is not text to clean
                elif isinstance(value, (int, float, bool)):
                    continue
                cleaned, removed, truncated = clean_cell(value, aggressive=aggressive)
                if cleaned is value:
                    continue
                if removed or truncated or cleaned != value:
                    cell.value = cleaned
                    result.note(sheet.title, removed, truncated=truncated,
                                sample=_sample(value) if isinstance(value, str) and removed
                                else f"{type(value).__name__} made Excel-safe")
    return result


class SafeCell:
    """One cell that cannot be given a value Excel will refuse.

    Everything the exporter writes goes through here, which is the point: the
    original failure arrived through a writer that did not clean, and the only
    reliable defence against that happening again is to make the unclean route
    not exist.

    Everything that is NOT a value — fonts, fills, alignment, number formats,
    the coordinate — is forwarded straight to the real cell, so the exporter's
    formatting works exactly as it did.
    """

    __slots__ = ("_cell", "_log", "_sheet", "_aggressive")

    def __init__(self, cell: Any, log: Sanitisation | None, sheet: str,
                 aggressive: bool):
        object.__setattr__(self, "_cell", cell)
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "_sheet", sheet)
        object.__setattr__(self, "_aggressive", aggressive)

    def __getattr__(self, name: str) -> Any:
        # Reached only for names not in __slots__, `value` among them.
        return getattr(self._cell, name)

    def __setattr__(self, name: str, new: Any) -> None:
        if name == "value":
            cleaned, removed, truncated = clean_cell(new, aggressive=self._aggressive)
            if self._log is not None and (removed or truncated):
                self._log.note(self._sheet, removed, truncated=truncated,
                               sample=_sample(new) if isinstance(new, str) else "")
            self._cell.value = cleaned
            return
        if name in SafeCell.__slots__:
            object.__setattr__(self, name, new)
            return
        setattr(self._cell, name, new)


class SafeSheet:
    """A worksheet whose cells are always cleaned before they are written.

    A thin proxy: anything not about writing a value is passed straight through
    to the real worksheet, so the exporter uses it exactly as it used the
    worksheet, and nothing about the template's formulas, validations or
    dimensions changes.
    """

    __slots__ = ("_sheet", "_log", "_aggressive")

    def __init__(self, sheet: Any, *, log: Sanitisation | None = None,
                 aggressive: bool = False):
        object.__setattr__(self, "_sheet", sheet)
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "_aggressive", aggressive)

    def __setattr__(self, name: str, value: Any) -> None:
        # Freeze panes, column widths, the title: everything that is not a cell
        # value belongs to the real worksheet and is set there.
        if name in SafeSheet.__slots__:
            object.__setattr__(self, name, value)
        elif name == "title":
            self._sheet.title = safe_sheet_title(value)
        else:
            setattr(self._sheet, name, value)

    @property
    def raw(self) -> Any:
        """The underlying worksheet, for the few reads that need it."""
        return self._sheet

    def cell(self, *args: Any, **kwargs: Any) -> SafeCell:
        if "value" in kwargs:
            cleaned, removed, truncated = clean_cell(kwargs["value"],
                                                     aggressive=self._aggressive)
            if self._log is not None and (removed or truncated):
                self._log.note(self._sheet.title, removed, truncated=truncated,
                               sample=_sample(kwargs["value"])
                               if isinstance(kwargs["value"], str) else "")
            kwargs["value"] = cleaned
        return SafeCell(self._sheet.cell(*args, **kwargs), self._log,
                        self._sheet.title, self._aggressive)

    def __getitem__(self, key: Any) -> Any:
        target = self._sheet[key]
        if hasattr(target, "value"):
            return SafeCell(target, self._log, self._sheet.title, self._aggressive)
        return target

    def __setitem__(self, key: Any, value: Any) -> None:
        cleaned, removed, truncated = clean_cell(value, aggressive=self._aggressive)
        if self._log is not None and (removed or truncated):
            self._log.note(self._sheet.title, removed, truncated=truncated,
                           sample=_sample(value) if isinstance(value, str) else "")
        self._sheet[key] = cleaned

    def append(self, row: Iterable[Any]) -> None:
        self._sheet.append(sanitise_row(list(row), sheet=self._sheet.title,
                                        log=self._log, aggressive=self._aggressive))

    def iter_rows(self, *args: Any, **kwargs: Any) -> Any:
        return self._sheet.iter_rows(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sheet, name)


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
