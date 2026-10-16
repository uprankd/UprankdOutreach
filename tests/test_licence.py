"""Reading 'casino without a licence' out of what websites wrote."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

import licence  # noqa: E402

CASES = {
    "License not required. 1 year publication.": "Yes",
    "GAMBLING LICENSE NOT NEEDED.": "Yes",
    "Gamblig license not required": "Yes",
    "Licese not required. no word limit": "Yes",
    "Doesnt need licanse. depends on the site": "Yes",
    "No licenses are required to run gambling sites.": "Yes",
    "unlicensed casinos are ok": "Yes",
    "Kazino bez licences OK": "Yes",
    "Gambling license necessary": "No",
    "License required. 2 dofollow links.": "No",
    "Must have a license": "No",
    "Must have local licence for Sweden.": "No",
    "Needs to have licens and be within EU": "No",
    "only licensed casinos are allowed": "No",
    "Casinos with a valid Dutch license; max three links": "No",
    "We publish topics of clients who have a license to operate": "No",
    "They do not allow links to unlicensed casinos.": "No",
    "for unlicensed casinos need to double-check with the site": "",
    "1 embedded image (royalty-free/licensed, max 800px)": "",
    "Dofollow, 500 words": "",
    "": "",
}


def main():
    bad = 0
    for text, want in CASES.items():
        got = licence.from_text(text)
        ok = got == want
        bad += not ok
        print("  %s %-55s -> %s" % ("ok  " if ok else "FAIL", text[:55], got or "(unknown)"))
    for raw, want in (("Yes", "Yes"), ("no", "No"), ("Not required", "Yes"), ("Licensed only", "No"), ("", "")):
        ok = licence.clean(raw) == want
        bad += not ok
        print("  %s column value %r -> %r" % ("ok  " if ok else "FAIL", raw, licence.clean(raw)))
    if bad:
        raise SystemExit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
