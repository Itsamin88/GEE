"""robots.txt parsing and per-host policy.

Responsible crawling (brief §38): the rules are obeyed, crawl-delay is honoured,
and an unreachable robots.txt is recorded rather than read as either a ban or a
licence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass
class RobotsPolicy:
    """The rules that apply to this crawler on one host."""

    host: str
    status: str = "missing"          # fetched | missing | unreachable
    allow: list[str] = field(default_factory=list)
    disallow: list[str] = field(default_factory=list)
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    raw: str = ""

    def can_fetch(self, url: str, *, always_allowed: tuple[str, ...] = ()) -> tuple[bool, str]:
        path = urlsplit(url).path or "/"
        query = urlsplit(url).query
        target = path + (f"?{query}" if query else "")
        if path in always_allowed:
            return True, "always-allowed path"
        if self.status != "fetched":
            return True, f"robots.txt {self.status}; proceeding politely"

        best_allow = _longest_match(self.allow, target)
        best_disallow = _longest_match(self.disallow, target)
        if best_disallow is None:
            return True, "not disallowed"
        if best_allow is not None and len(best_allow) >= len(best_disallow):
            return True, f"allowed by {best_allow!r}"
        return False, f"disallowed by {best_disallow!r}"


def _longest_match(rules: list[str], target: str) -> str | None:
    best: str | None = None
    for rule in rules:
        if _matches(rule, target) and (best is None or len(rule) > len(best)):
            best = rule
    return best


def _matches(rule: str, target: str) -> bool:
    if rule == "":
        return False
    pattern = re.escape(unquote(rule)).replace(r"\*", ".*")
    if pattern.endswith(r"\$"):
        pattern = pattern[:-2] + "$"
    return re.match(pattern, unquote(target)) is not None


def parse_robots(text: str, host: str, agent_tokens: tuple[str, ...]) -> RobotsPolicy:
    """Parse robots.txt, taking the most specific group that applies to us."""
    policy = RobotsPolicy(host=host, status="fetched", raw=text[:20000])
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    current_agents: list[str] = []
    current_rules: list[tuple[str, str]] = []
    starting_group = True

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if not starting_group:
                groups.append((current_agents, current_rules))
                current_agents, current_rules = [], []
                starting_group = True
            current_agents.append(value.lower())
        elif key == "sitemap":
            if value:
                policy.sitemaps.append(value)
        elif key in ("allow", "disallow", "crawl-delay"):
            starting_group = False
            current_rules.append((key, value))
    if current_agents or current_rules:
        groups.append((current_agents, current_rules))

    tokens = tuple(t.lower() for t in agent_tokens)
    chosen: list[tuple[str, str]] | None = None
    specificity = -1
    for agents, rules in groups:
        for agent in agents:
            if agent == "*":
                score = 0
            elif any(token in agent or agent in token for token in tokens):
                score = len(agent)
            else:
                continue
            if score > specificity:
                specificity, chosen = score, rules
    for key, value in chosen or []:
        if key == "allow" and value:
            policy.allow.append(value)
        elif key == "disallow":
            if value:
                policy.disallow.append(value)
        elif key == "crawl-delay":
            try:
                policy.crawl_delay = float(value.replace(",", "."))
            except ValueError:
                pass
    return policy
