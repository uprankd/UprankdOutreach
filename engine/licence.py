"""Does a site take casino articles for brands without a gambling licence?
Read from what the site wrote (notes, replies). "Yes", "No" or "" (unknown)."""

import re

L = r"lic[ae]?n?[cs]e?[sd]?"
YES = [
    L + r"\s*(is\s+|are\s+)?not\s+(required|needed|necessary|mandatory)",
    r"no\s+" + L + r"\s*(is\s+|are\s+)?(required|needed|necessary)",
    r"(does\s*n[o']?t|do\s*n[o']?t|doesnt|dont)\s+(need|require)\s+(a\s+|any\s+)?" + L,
    r"without\s+(a\s+|any\s+)?(gambling\s+|casino\s+)?" + L,
    r"no\s+need\s+(for|of)\s+(a\s+)?" + L,
    r"(accept|allow|take|ok|fine|welcome)\w*\s+(\w+\s+){0,3}unlicen[cs]ed",
    r"unlicen[cs]ed\s+(casinos?|brands?|operators?)?\s*(are\s+|is\s+)?(ok|fine|accepted|allowed|welcome)",
    r"bez\s+licen",
]
# Checked first: "we do not allow unlicensed casinos" is a no, not a yes.
NOT_UNLICENSED = [
    r"(not|n't|never|no)\s+(\w+\s+){0,4}?unlicen[cs]ed",
    r"unlicen[cs]ed\s+(\w+\s+){0,3}?(are\s+|is\s+)?(not|never)\b",
]
NO = [
    r"with\s+(a\s+)?(valid|local|proper|official)\s+(\w+\s+)?" + L,
    r"(must|should|has\s+to|have\s+to)\s+(have|hold|be|possess)\s+(\w+\s+){0,3}?(licensed|" + L + ")",
    r"(who|that|which)\s+(have|has|hold|holds|possess)\s+(\w+\s+){0,3}?" + L,
    r"(is|are|be)\s+(officially\s+|properly\s+|fully\s+)?licen[cs]ed\s+(in|by|to)",
    r"(gambling\s+|casino\s+|valid\s+)?" + L + r"\s*(is\s+)?(required|necessary|needed|mandatory|obligatory)",
    r"(only|just)\s+(for\s+|with\s+)?(\w+\s+){0,2}?(licensed|" + L + ")",
    r"with\s+(a\s+)?(valid\s+|local\s+)?(\w+\s+)?" + L + r"\s+only",
    r"(needs?|requires?|required)\s+(\w+\s+){0,3}?" + L,
    r"licensed\s+(casinos?|operators?|brands?)\s+only",
    r"ar\s+licenci",
]
YES_RE = [re.compile(p, re.I) for p in YES]
NO_RE = [re.compile(p, re.I) for p in NO]
NOT_UNLICENSED_RE = [re.compile(p, re.I) for p in NOT_UNLICENSED]


def from_text(text):
    t = " ".join(str(text or "").split())
    if not t or not re.search(r"lic[ae]?n?[cs]", t, re.I):
        return ""
    if any(p.search(t) for p in NOT_UNLICENSED_RE):
        return "No"
    if any(p.search(t) for p in YES_RE):
        return "Yes"
    if any(p.search(t) for p in NO_RE):
        return "No"
    return ""


def clean(raw):
    v = str(raw or "").strip().lower()
    if v in ("yes", "y", "jā", "ja", "x", "true", "1", "+", "ok", "accept", "accepted", "allowed",
             "not required", "no license needed", "no licence needed"):
        return "Yes"
    if v in ("no", "n", "nē", "ne", "false", "0", "-", "required", "license required",
             "licence required", "only licensed", "licensed only"):
        return "No"
    return from_text(raw)
