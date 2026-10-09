"""Sign in with Google, only for accounts on the company's Google Workspace domain.

Turned on by a Google OAuth client, from either:
  * google_oauth.json next to app.py or in ~/.almo - the JSON file Google Cloud
    lets you download for an OAuth client ({"web": {"client_id": ..., ...}}),
    or a plain {"client_id": ..., "client_secret": ..., "allowed_domain": ...}
  * environment: ALMO_GOOGLE_CLIENT_ID, ALMO_GOOGLE_CLIENT_SECRET

Only verified addresses @ALMO_ALLOWED_DOMAIN (default uprankd.com) get in.
ALMO_ALLOWED_EMAILS (comma separated) can narrow that to named people.

Without a client, Almo has no login and only answers its own computer - the
way it runs on a Mac. Behind a proxy (a server) it refuses to open instead.
"""

import base64
import json
import os
import secrets
import time
from urllib.parse import urlencode

import db

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def config():
    """{client_id, client_secret, domain, emails} or None when sign-in is off."""
    cid = os.environ.get("ALMO_GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("ALMO_GOOGLE_CLIENT_SECRET", "").strip()
    domain = os.environ.get("ALMO_ALLOWED_DOMAIN", "").strip()
    if not cid:
        for folder in (db.APP_DIR, db.DATA_DIR):
            path = os.path.join(folder, "google_oauth.json")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                inner = data.get("web") or data.get("installed") or data
                cid = (inner.get("client_id") or "").strip()
                secret = (inner.get("client_secret") or "").strip()
                domain = domain or (data.get("allowed_domain") or "").strip()
                break
    if not cid or not secret:
        return None
    emails = {e.strip().lower() for e in os.environ.get("ALMO_ALLOWED_EMAILS", "").split(",") if e.strip()}
    return {"client_id": cid, "client_secret": secret,
            "domain": (domain or "uprankd.com").lower().lstrip("@"), "emails": emails}


def enabled():
    return config() is not None


def secret_key():
    """A random key that signs the session cookie, kept between restarts."""
    os.makedirs(db.DATA_DIR, exist_ok=True)
    path = os.path.join(db.DATA_DIR, "secret_key")
    if not os.path.isfile(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def authorize_url(cfg, redirect_uri, state, nonce):
    return AUTH_URL + "?" + urlencode({
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "hd": cfg["domain"],          # Google shows only that domain's accounts
        "prompt": "select_account",
    })


class AuthError(Exception):
    """`code` is shown on the login page; `email` when we know who tried."""

    def __init__(self, code, email=""):
        super().__init__(code)
        self.code = code
        self.email = email


def _payload(id_token):
    try:
        part = id_token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception as exc:
        raise AuthError("failed") from exc


def exchange(cfg, code, redirect_uri):
    """Swap the code for Google's ID token. It comes straight from Google over
    TLS, so (per OpenID Connect) its claims can be trusted without re-checking
    the signature; every claim that matters is still checked below."""
    import requests

    try:
        r = requests.post(TOKEN_URL, data={
            "code": code, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }, timeout=20)
    except Exception as exc:
        raise AuthError("failed") from exc
    if r.status_code != 200:
        raise AuthError("failed")
    token = (r.json() or {}).get("id_token")
    if not token:
        raise AuthError("failed")
    return _payload(token)


def check(cfg, claims, nonce):
    """The signed-in user, or AuthError saying why not."""
    email = str(claims.get("email") or "").lower()
    if claims.get("iss") not in ISSUERS or claims.get("aud") != cfg["client_id"]:
        raise AuthError("failed", email)
    if float(claims.get("exp") or 0) < time.time() - 60:
        raise AuthError("expired", email)
    if not nonce or claims.get("nonce") != nonce:
        raise AuthError("expired", email)
    if claims.get("email_verified") not in (True, "true"):
        raise AuthError("domain", email)
    # Both the Workspace claim and the address itself must be the company's.
    if claims.get("hd", "").lower() != cfg["domain"] or not email.endswith("@" + cfg["domain"]):
        raise AuthError("domain", email)
    if cfg["emails"] and email not in cfg["emails"]:
        raise AuthError("person", email)
    return {"email": email, "name": claims.get("name") or email.split("@")[0],
            "picture": claims.get("picture") or ""}


def allowed(cfg, user):
    """Re-checked on every request, so removing someone takes effect at once."""
    email = (user or {}).get("email", "")
    if not email.endswith("@" + cfg["domain"]):
        return False
    return not cfg["emails"] or email in cfg["emails"]
