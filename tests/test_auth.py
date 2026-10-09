"""Google sign-in, limited to @uprankd.com - against a fake Google (no network).

    python3 tests/test_auth.py
"""

import base64
import json
import os
import shutil
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

TMP = tempfile.mkdtemp(prefix="almo-auth-")
os.environ.update(ALMO_DATA_DIR=TMP, ALMO_GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com",
                  ALMO_GOOGLE_CLIENT_SECRET="shh", ALMO_INSECURE_COOKIES="1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import requests  # noqa: E402

import app as almo  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

NEXT_TOKEN = {}


class Resp:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def fake_post(url, data=None, timeout=None, **kw):
    assert url == auth.TOKEN_URL and data["client_secret"] == "shh"
    body = base64.urlsafe_b64encode(json.dumps(NEXT_TOKEN).encode()).decode().rstrip("=")
    return Resp({"id_token": "h." + body + ".sig"})


requests.post = fake_post


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def sign_in(c, claims, base="http://localhost", headers=None):
    r = c.get("/auth/google", base_url=base, headers=headers or {})
    q = parse_qs(urlparse(r.headers["Location"]).query)
    NEXT_TOKEN.clear()
    NEXT_TOKEN.update({"iss": "https://accounts.google.com", "aud": "cid.apps.googleusercontent.com",
                       "exp": 9999999999, "nonce": q["nonce"][0], "email_verified": True,
                       "hd": "uprankd.com", "email": "kristians@uprankd.com", "name": "Kristiāns"})
    NEXT_TOKEN.update(claims)
    return c.get("/auth/callback?code=abc&state=" + q["state"][0], base_url=base, headers=headers or {}), q


def main():
    db.init()
    c = almo.app.test_client()

    r = c.get("/")
    check(r.status_code == 302 and r.headers["Location"].startswith("/login"), "not signed in -> login page")
    r = c.get("/api/state")
    check(r.status_code == 401 and r.get_json()["login"], "API answers 401 without a session")
    check(c.get("/web/app.js").status_code == 302, "app code is behind the login too")
    check(c.get("/web/app.css").status_code == 200, "login page styles load without a session")

    r = c.get("/login")
    page = r.get_data(as_text=True)
    check(r.status_code == 200 and "Continue with Google" in page and "@uprankd.com" in page,
          "login page: Continue with Google, @uprankd.com")

    r = c.get("/auth/google")
    q = parse_qs(urlparse(r.headers["Location"]).query)
    check(r.headers["Location"].startswith(auth.AUTH_URL) and q["hd"] == ["uprankd.com"]
          and q["scope"] == ["openid email profile"], "Google is asked for uprankd.com accounts only")

    r = c.get("/auth/callback?code=abc&state=wrong")
    check("error=expired" in r.headers["Location"], "a forged or stale sign-in is refused")

    for label, claims, err in (
        ("a @gmail.com account", {"email": "someone@gmail.com", "hd": ""}, "domain"),
        ("another company's Workspace", {"email": "x@other.com", "hd": "other.com"}, "domain"),
        ("a spoofed hd with a foreign address", {"email": "x@other.com"}, "domain"),
        ("an unverified address", {"email_verified": False}, "domain"),
        ("a token for another app", {"aud": "someone-else"}, "failed"),
        ("a replayed token (wrong nonce)", {"nonce": "old"}, "expired"),
    ):
        c2 = almo.app.test_client()
        r, _ = sign_in(c2, claims)
        check("error=" + err in r.headers["Location"] and c2.get("/").status_code == 302,
              "refused: " + label)
    r, _ = sign_in(almo.app.test_client(), {"email": "someone@gmail.com", "hd": ""})
    check("someone%40gmail.com" in r.headers["Location"], "the refusal names the account that tried")

    r, _ = sign_in(c, {})
    check(r.status_code == 302 and r.headers["Location"] == "/", "@uprankd.com account signs in")
    check(c.get("/").status_code == 200, "app opens after sign-in")
    st = c.get("/api/state").get_json()
    check(st["user"]["email"] == "kristians@uprankd.com", "the app knows who is signed in")

    os.environ["ALMO_ALLOWED_EMAILS"] = "boss@uprankd.com"
    check(c.get("/api/state").status_code == 401, "removing a person from the list locks them out at once")
    r, _ = sign_in(almo.app.test_client(), {})
    check("error=person" in r.headers["Location"], "only listed people get in when a list is set")
    del os.environ["ALMO_ALLOWED_EMAILS"]

    r, _ = sign_in(c, {})
    r = c.get("/logout")
    check("signed_out=1" in r.headers["Location"] and c.get("/").status_code == 302, "sign out works")

    c3 = almo.app.test_client()
    hdrs = {"X-Forwarded-For": "1.2.3.4", "X-Forwarded-Proto": "https", "X-Forwarded-Host": "outreach.uprankd.com"}
    r = c3.get("/auth/google", base_url="http://127.0.0.1:8765", headers=hdrs)
    q = parse_qs(urlparse(r.headers["Location"]).query)
    check(q["redirect_uri"] == ["https://outreach.uprankd.com/auth/callback"],
          "behind NGINX the return address is https://outreach.uprankd.com")
    r = c.get("/auth/google?next=//evil.com")
    check(c.get("/login?next=//evil.com").status_code == 200, "next= can't send people to other sites")

    # No Google client configured
    del os.environ["ALMO_GOOGLE_CLIENT_ID"]
    c4 = almo.app.test_client()
    check(c4.get("/").status_code == 200, "no sign-in set up: still opens on this computer")
    check(c4.get("/", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 403,
          "no sign-in set up: refuses over the network")
    check(c4.get("/", base_url="http://outreach.uprankd.com").status_code == 403,
          "no sign-in set up: refuses on a public domain")
    check(c4.get("/", headers={"X-Real-IP": "1.2.3.4"}).status_code == 403,
          "no sign-in set up: refuses a proxy that only sends X-Real-IP")
    os.environ["ALMO_SERVER"] = "1"
    check(c4.get("/").status_code == 403, "ALMO_SERVER=1: never opens without sign-in, even locally")
    del os.environ["ALMO_SERVER"]
    print("\nAll checks passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
