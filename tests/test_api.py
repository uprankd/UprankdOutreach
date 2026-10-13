"""Mailboxes, A/B pitches, the client price list and the database columns,
through the same HTTP API the browser uses.

    python3 tests/test_api.py
"""

import io
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="almo-api-")
os.environ["ALMO_DATA_DIR"] = TMP
for k in ("ALMO_GOOGLE_CLIENT_ID", "ALMO_SERVER"):
    os.environ.pop(k, None)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import app as almo  # noqa: E402
import db  # noqa: E402
import exporter  # noqa: E402
import settings  # noqa: E402


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def main():
    db.init()
    if db.KIND == "postgres":   # a clean shared database for the test
        with db.tx() as conn:
            for t in ("sites", "messages", "events", "mailboxes", "pitches", "campaigns", "settings", "seen_mail"):
                conn.execute("DELETE FROM %s" % t)
        db.init()
    c = almo.app.test_client()

    # Mailboxes
    st = c.get("/api/settings").get_json()
    check(st["logo_url"] == "https://uprankd.com/logo.svg", "signature logo is https://uprankd.com/logo.svg")
    check(set(st["providers"]) >= {"Gmail", "Fastmail", "Zoho"}, "Gmail, Fastmail and Zoho presets")
    r = c.post("/api/mailboxes", json={"provider": "Fastmail", "email": "a@uprankd.com", "password": "p1",
                                       "sender_name": "Anna", "daily_limit": 25, "smtp_host": "evil.com"})
    a_id = r.get_json()["id"]
    a = settings.mailbox(a_id)
    check(a["smtp_host"] == "smtp.fastmail.com" and a["password"] == "p1" and a["daily_limit"] == 25,
          "Fastmail mailbox: fixed servers, password kept as a secret")
    check(c.post("/api/mailboxes", json={"provider": "Gmail", "email": "A@uprankd.com"}).status_code == 400,
          "the same mailbox can't be added twice")
    r = c.post("/api/mailboxes", json={"provider": "Zoho", "email": "z@uprankd.com", "password": "p2",
                                       "sender_name": "Zane", "smtp_host": "smtppro.zoho.com", "imap_host": "imappro.zoho.com"})
    z_id = r.get_json()["id"]
    check(settings.mailbox(z_id)["smtp_host"] == "smtppro.zoho.com", "Zoho servers can be changed (.com instead of .eu)")
    boxes = c.get("/api/mailboxes").get_json()["mailboxes"]
    check(all("password" not in b for b in boxes) and all(b["password_set"] for b in boxes),
          "passwords never reach the browser")
    c.put("/api/mailboxes/%d" % z_id, json={"active": False})
    check(not settings.mailbox(z_id)["active"], "a mailbox can be paused")
    check(c.post("/api/test/email", json={}).get_json()["error"], "testing needs a saved mailbox")
    st = c.get("/api/state").get_json()
    check(st["setup"][0]["done"] and not st["missing"], "setup: mailbox connected")
    check(c.delete("/api/mailboxes/%d" % z_id).get_json()["ok"] and settings.mailbox(z_id) is None
          and settings.get_secret("mailbox_%d" % z_id) == "", "removing a mailbox forgets its password")

    # A/B pitches
    camp = st["campaigns"][0]["id"]
    ps = c.get("/api/campaigns/%d/pitches" % camp).get_json()["pitches"]
    check(len(ps) == 1 and ps[0]["label"] == "A", "every campaign starts with pitch A")
    r = c.post("/api/campaigns/%d/pitches" % camp, json={"copy": ps[0]["id"]}).get_json()
    b_id = r["id"]
    check([p["label"] for p in r["pitches"]] == ["A", "B"], "pitch B added as a copy of A")
    c.put("/api/pitches/%d" % b_id, json={"subject": "Short one for {domain}", "body": "Hi, prices for {domain}?"})
    pv = c.get("/api/preview/%d?pitch=%d&domain=delfi.lv" % (camp, b_id)).get_json()
    check(pv["subject"] == "Short one for delfi.lv" and "data:image/png;base64," in pv["html"],
          "preview shows pitch B with the logo")
    c.put("/api/pitches/%d" % b_id, json={"active": False})
    check(c.put("/api/pitches/%d" % ps[0]["id"], json={"active": False}).status_code == 400,
          "the last active pitch can't be turned off")
    c.put("/api/pitches/%d" % b_id, json={"active": True})
    new = c.post("/api/campaigns", json={"name": "Germany"}).get_json()["id"]
    check(len(c.get("/api/campaigns/%d/pitches" % new).get_json()["pitches"]) == 1, "new campaigns get pitch A")
    db.add_sites(camp, ["sent-one.lv"])
    sid = db.sites("domain='sent-one.lv'")[0]["id"]
    db.update_site(sid, pitch_id=b_id, sent_at=1.0, status="waiting")
    check(c.delete("/api/pitches/%d" % b_id).status_code == 400, "a pitch that was sent can only be turned off")

    # Database: email + sponsored tag columns
    db.update_site(sid, email="info@sent-one.lv", sponsored_tag="No", price="100", special_price="180",
                   requirements="Dofollow, 1 link")
    db.add_sites(camp, ["noprice-two.lv"])
    rows = c.get("/api/db?sort=sponsored").get_json()["rows"]
    row = [x for x in rows if x["domain"] == "sent-one.lv"][0]
    check(row["email"] == "info@sent-one.lv" and row["sponsored_tag"] == "No", "database rows carry email and sponsored tag")

    # Client price list
    check(exporter.client_price("100", 30, 10) == 140 and exporter.client_price("99", 10, 0) == 109
          and exporter.client_price("Unknown", 30, 0) is None, "client price = cost × markup + margin, rounded up")
    cnt = c.get("/api/export/count?db=1").get_json()
    check(cnt["total"] == 2 and cnt["priced"] == 1, "export dialog knows how many have a price")
    r = c.get("/api/export?db=1&client=1&markup=30&margin=10&special=1")
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(r.data)).active
    data = list(ws.iter_rows(values_only=True))
    check(list(data[0]) == ["Website", "Price (EUR)", "Casino / crypto / loan price (EUR)", "Requirements"],
          "client file columns: website, client price, requirements")
    check(data[1] == ("sent-one.lv", 140, 244, "Dofollow, 1 link") and len(data) == 2,
          "client file: marked-up prices, no costs, no sites without a price")
    flat = " ".join(str(v) for row in data for v in row)
    check("info@" not in flat and "100" not in flat.split(), "no emails or our costs in the client file")
    r = c.get("/api/export?ids=%d" % sid)
    head = [x.value for x in load_workbook(io.BytesIO(r.data)).active[1]]
    check("Email" in head and "Marked sponsored" in head, "full export keeps everything")
    print("\nAll checks passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
