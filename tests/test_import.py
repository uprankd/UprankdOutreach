"""Import an Excel database, then check Almo reuses its emails and never re-pitches.

    python3 tests/test_import.py
"""

import io
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="almo-import-")
os.environ["ALMO_DATA_DIR"] = TMP
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from openpyxl import Workbook  # noqa: E402

import db  # noqa: E402
import importer  # noqa: E402
import worker as worker_mod  # noqa: E402


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = "Latvija"
    ws.append(["Notes", "Website", "Kontakts", "Portal price", "Casino", "Crypto", "Requirments/comments"])
    ws.append(["x", '=HYPERLINK("https://www.delfi.lv","delfi.lv")', "reklama@delfi.lv", "150 EUR", "jā", "no", "Dofollow"])
    ws.append(["", "https://tvnet.lv/zinas", "", "€ 90", "250", "", ""])
    ws2 = wb.create_sheet("DE")
    ws2.append(["Domain", "E-mail", "Price"])
    ws2.append(["bild.de", "info@bild.de", "1.200,00"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main():
    db.init()
    raw = workbook()
    p = importer.preview("db.xlsx", raw)
    check(p["new"] == 3, "preview finds 3 websites over 2 sheets")
    importer.run("db.xlsx", raw, None)
    d = db.sites("domain='delfi.lv'")[0]
    check(d["email"] == "reklama@delfi.lv" and d["price"] == "150" and d["casino"] == "Yes"
          and d["crypto"] == "No" and d["requirements"] == "Dofollow" and d["country"] == "Latvia",
          "headers matched by name (Latvian too), values cleaned")
    t = db.sites("domain='tvnet.lv'")[0]
    check(t["price"] == "90" and t["casino"] == "Yes", "'€ 90' -> 90, a price in Casino -> Yes")
    b = db.sites("domain='bild.de'")[0]
    check(b["country"] == "Germany" and b["price"] == "1200", "sheet name 'DE' -> Germany, 1.200,00 -> 1200")
    check(d["status"] == "in_db", "imported sites wait in the database, nobody is emailed")

    db.update_site(d["id"], price="")
    s = importer.run("db.xlsx", raw, None)
    check(s["updated"] == 1 and db.get_site(d["id"])["price"] == "150", "re-import only fills empty fields")
    db.update_site(d["id"], price="175")
    importer.run("db.xlsx", raw, None)
    check(db.get_site(d["id"])["price"] == "175", "re-import never overwrites what Almo collected")

    camp = db.one("SELECT id FROM campaigns")["id"]
    added, known = db.add_sites(camp, ["delfi.lv", "new.lv"])
    check(known == ["delfi.lv"] and added == ["new.lv"], "pasting a known website skips it")

    db.update_site(d["id"], status="queued")
    w = worker_mod.Worker()
    w._read_one(d["id"], {"check_sites": True})
    d = db.get_site(d["id"])
    check(d["status"] == "ready" and d["email"] == "reklama@delfi.lv" and d["language"] == "lv",
          "'Ask for prices' uses the database email - no scraping")
    print("\nAll checks passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
