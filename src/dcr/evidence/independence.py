"""Source independence: the rule the whole multi-address protocol turns on.

Two sources are independent only if neither derives from the other and neither
derives from a third source they share. Ten copied pages are not ten sources
(brief §8; register "The independence rule").

Copying is detected three ways: near-identical text (simhash + shingle
overlap), explicit attribution markers ("press release", "source:"), and
structural relationships (a directory listing of the community's own site).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Mapping

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "") if len(w) > 1]


def shingles(tokens: list[str], size: int = 5) -> set[int]:
    """Hashed word n-grams. Robust to boilerplate around a copied passage."""
    if len(tokens) < size:
        return {_hash64(" ".join(tokens))} if tokens else set()
    return {
        _hash64(" ".join(tokens[i: i + size]))
        for i in range(len(tokens) - size + 1)
    }


def _hash64(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def simhash(tokens: list[str], *, bits: int = 64) -> int:
    """A 64-bit fingerprint whose Hamming distance tracks textual similarity."""
    if not tokens:
        return 0
    vector = [0] * bits
    weights: dict[str, int] = {}
    for token in tokens:
        weights[token] = weights.get(token, 0) + 1
    for token, weight in weights.items():
        value = _hash64(token)
        for bit in range(bits):
            if value >> bit & 1:
                vector[bit] += weight
            else:
                vector[bit] -= weight
    fingerprint = 0
    for bit in range(bits):
        if vector[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def jaccard(a: set[int], b: set[int]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def containment(a: set[int], b: set[int]) -> float:
    """How much of the SMALLER text appears in the larger one.

    A directory listing that copies three paragraphs from a large website has a
    low Jaccard score but near-total containment — which is what copying is.
    """
    if not a or not b:
        return 0.0
    smaller, larger = (a, b) if len(a) <= len(b) else (b, a)
    return len(smaller & larger) / len(smaller)


@dataclass
class TextProfile:
    ref_id: str
    source_id: str | None
    fingerprint: int
    shingle_set: set[int]
    chars: int
    text_sample: str = ""


@dataclass
class CopyVerdict:
    is_copy: bool
    similarity: float
    method: str
    detail: str


def compare(a: TextProfile, b: TextProfile, *, simhash_threshold: int = 8,
            jaccard_threshold: float = 0.72, containment_threshold: float = 0.6) -> CopyVerdict:
    distance = hamming(a.fingerprint, b.fingerprint)
    overlap = jaccard(a.shingle_set, b.shingle_set)
    contained = containment(a.shingle_set, b.shingle_set)

    if overlap >= jaccard_threshold:
        return CopyVerdict(True, round(overlap, 3), "shingle_jaccard",
                           f"{overlap:.0%} of the text n-grams are shared")
    if contained >= containment_threshold and min(len(a.shingle_set), len(b.shingle_set)) >= 20:
        return CopyVerdict(True, round(contained, 3), "shingle_containment",
                           f"{contained:.0%} of the shorter text appears in the longer one")
    if distance <= simhash_threshold and a.chars > 400 and b.chars > 400:
        return CopyVerdict(True, round(1 - distance / 64, 3), "simhash",
                           f"fingerprints differ in {distance} of 64 bits")
    return CopyVerdict(False, round(max(overlap, contained), 3), "distinct",
                       f"jaccard {overlap:.2f}, containment {contained:.2f}, "
                       f"simhash distance {distance}")


def has_attribution_marker(text: str, markers: Iterable[str]) -> str | None:
    """Explicit evidence that a text was reproduced from somewhere else."""
    lowered = (text or "").lower()
    for marker in markers:
        if marker.lower() in lowered:
            return marker
    return None


@dataclass
class GroupAssignment:
    source_id: str
    group: str
    reason: str
    similarity: float = 0.0
    related_to: str | None = None


class IndependenceResolver:
    """Assigns G1, G2, G3 ... to sources, and explains every assignment."""

    def __init__(self, config: Mapping[str, object] | None = None):
        cfg = dict(config or {})
        self.simhash_threshold = int(cfg.get("simhash_threshold", 8))
        self.jaccard_threshold = float(cfg.get("jaccard_threshold", 0.72))
        self.shingle_size = int(cfg.get("shingle_size", 5))
        self.min_chars = int(cfg.get("min_chars_for_comparison", 400))
        self.press_markers = list(cfg.get("press_release_markers", []))
        self.promotion_max_jaccard = float(cfg.get("promotion_max_jaccard", 0.35))
        self._next_group = 1
        self.assignments: dict[str, GroupAssignment] = {}
        self._group_profiles: dict[str, list[TextProfile]] = {}

    def new_group(self) -> str:
        group = f"G{self._next_group}"
        self._next_group += 1
        return group

    def profile(self, ref_id: str, source_id: str | None, text: str) -> TextProfile:
        tokens = tokenize(text)
        return TextProfile(
            ref_id=ref_id,
            source_id=source_id,
            fingerprint=simhash(tokens),
            shingle_set=shingles(tokens, self.shingle_size),
            chars=len(text or ""),
            text_sample=(text or "")[:600],
        )

    def assign(
        self,
        *,
        source_id: str,
        platform_type: str,
        source_class: str,
        registrable: str,
        profile: TextProfile | None,
        community_domains: set[str],
        text: str = "",
        editorial_signals: bool = False,
    ) -> GroupAssignment:
        """Place one source in an independence group, with the reason recorded."""
        # 1. The community's own voice: its website, its social accounts, its
        #    former domains. One organisation writing about itself.
        own_voice_platforms = {
            "own website", "secondary or former website", "Facebook", "Instagram",
            "YouTube", "Vimeo", "LinkedIn", "blog platform",
        }
        if platform_type in own_voice_platforms or registrable in community_domains:
            assignment = GroupAssignment(
                source_id=source_id,
                group=self._community_group(),
                reason=f"the community's own voice ({platform_type})",
            )
            self._record(assignment, profile)
            return assignment

        # 2. Explicit reproduction markers: a press release and its reprints.
        marker = has_attribution_marker(text, self.press_markers)

        # 3. Textual copying of anything already grouped.
        best: tuple[float, str, str, str] | None = None
        if profile is not None and profile.chars >= self.min_chars:
            for group, profiles in self._group_profiles.items():
                for other in profiles:
                    verdict = compare(
                        profile, other,
                        simhash_threshold=self.simhash_threshold,
                        jaccard_threshold=self.jaccard_threshold,
                    )
                    if verdict.is_copy and (best is None or verdict.similarity > best[0]):
                        best = (verdict.similarity, group, verdict.method, verdict.detail)

        if best is not None:
            similarity, group, method, detail = best
            if platform_type == "directory listing" and similarity < self.promotion_max_jaccard \
                    and editorial_signals:
                assignment = GroupAssignment(
                    source_id=source_id, group=self.new_group(),
                    reason="directory listing with independent editorial content "
                           f"(similarity {similarity:.2f} below the copy threshold)",
                    similarity=similarity,
                )
            else:
                assignment = GroupAssignment(
                    source_id=source_id, group=group,
                    reason=f"derives from an existing source — {method}: {detail}",
                    similarity=similarity,
                )
            self._record(assignment, profile)
            return assignment

        # 4. A directory listing defaults to the community's group (DCR-D010).
        if platform_type == "directory listing" and not editorial_signals:
            read = profile is not None and profile.chars >= self.min_chars
            assignment = GroupAssignment(
                source_id=source_id, group=self._community_group(),
                reason=(
                    "directory listing whose text shows no editorial signals; the same voice "
                    "as the community's own material"
                    if read else
                    "directory listing, not yet read: listings are self-submitted, so the "
                    "default is the community's own group until the text says otherwise"
                ),
            )
            self._record(assignment, profile)
            return assignment

        if marker:
            assignment = GroupAssignment(
                source_id=source_id, group=self._community_group(),
                reason=f"carries a reproduction marker ({marker!r}); not independent reporting",
            )
            self._record(assignment, profile)
            return assignment

        # 5. Independent origin: an academic source, a registry, a newspaper
        #    that did its own reporting.
        assignment = GroupAssignment(
            source_id=source_id, group=self.new_group(),
            reason=f"independent origin ({source_class}, {platform_type}); "
                   "no derivation from an existing group detected",
        )
        self._record(assignment, profile)
        return assignment

    def _community_group(self) -> str:
        if "G1" not in self._group_profiles:
            self._group_profiles["G1"] = []
            self._next_group = max(self._next_group, 2)
        return "G1"

    def _record(self, assignment: GroupAssignment, profile: TextProfile | None) -> None:
        self.assignments[assignment.source_id] = assignment
        bucket = self._group_profiles.setdefault(assignment.group, [])
        if profile is not None and profile.chars >= self.min_chars and len(bucket) < 25:
            bucket.append(profile)

    def group_count(self) -> int:
        return len({a.group for a in self.assignments.values()})

    def groups(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for assignment in self.assignments.values():
            out.setdefault(assignment.group, []).append(assignment.source_id)
        return out


def editorial_signals_present(text: str) -> bool:
    """Signs that a listing carries its own reporting rather than a submission."""
    markers = (
        "we visited", "our reviewer", "reviewed by", "site visit", "verified by",
        "assessment", "inspection", "interview with", "nous avons visité",
        "wij bezochten", "bezoekverslag", "redactie", "editor's note", "rapport de visite",
    )
    lowered = (text or "").lower()
    return any(marker in lowered for marker in markers)
