"""The .env file: values, quotes, comments, and real environment winning.

    python3 tests/test_env.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

import envfile  # noqa: E402


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def main():
    d = tempfile.mkdtemp()
    try:
        with open(os.path.join(d, ".env"), "w") as f:
            f.write('# comment\nT_A=plain\nT_B="quoted value"\nT_C=\'single\'\n'
                    'export T_D=exported\nT_E=value   # note\nT_F=\nT_G=from-file\nnot a line\n')
        os.environ["T_G"] = "from-environment"
        envfile.load(d)
        check(os.environ["T_A"] == "plain", "plain value")
        check(os.environ["T_B"] == "quoted value" and os.environ["T_C"] == "single", "quotes removed")
        check(os.environ["T_D"] == "exported", "'export KEY=' works")
        check(os.environ["T_E"] == "value", "trailing comment ignored")
        check(os.environ["T_F"] == "", "empty value allowed")
        check(os.environ["T_G"] == "from-environment", "real environment wins over .env")
        check(envfile.load(tempfile.gettempdir() + "/nope-almo") == [], "no .env file is fine")
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
