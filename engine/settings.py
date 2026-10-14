"""App settings with sensible defaults. Passwords and keys go to the system
keychain (macOS Keychain / Windows Credential Manager) when available."""

import time

import db

SECRET_KEYS = ("email_password", "anthropic_key", "openai_key", "gemini_key")
_SERVICE = "Almo outreach"

DEFAULTS = {
    # Account
    "provider": "Gmail",              # Gmail | Fastmail | Other
    "email": "",
    "smtp_host": "",
    "smtp_port": 465,
    "imap_host": "",
    "imap_port": 993,
    # Who you are
    "sender_name": "",
    "sender_title": "Outreach Specialist",
    "company": "SIA Uprankd",
    # Email apps don't show SVG, so the signature carries a PNG copy of this
    # logo inside the email itself (web/email-logo.png). Any PNG/JPG URL here
    # is linked instead.
    "logo_url": "https://uprankd.com/logo.svg",
    # Automation
    "send_mode": "off",               # off | test | live
    "running": True,
    "check_sites": True,
    "find_direct": True,              # look for a site's own contact before pitching a link builder              # skip sites that don't publish articles
    "translate": True,                # write the pitch in the site's language
    "auto_followup": True,            # reply automatically when prices are missing
    "nudge_days": 4,                  # remind once if no reply after N days
    "max_nudges": 1,
    "daily_limit": 40,
    "gap_min": 240,                   # seconds between two emails from one mailbox
    "gap_max": 600,
    "global_gap_min": 30,             # seconds between any two emails Almo sends
    "global_gap_max": 90,
    # Uprankd price = our price × multiplier, rounded up, never below the minimum
    "price_multiplier": 1.6,
    "price_minimum": 200,
    "price_round": 10,
    "work_start": 8,
    "work_end": 19,
    "inbox_every_min": 5,
    "recontact_days": 180,
    # AI
    "ai_provider": "anthropic",       # anthropic | openai | gemini
    "model_smart": "claude-sonnet-5-5",
    "model_fast": "claude-haiku-5-5",
    "anthropic_smart": "claude-sonnet-5-5",
    "anthropic_fast": "claude-haiku-5-5",
    "openai_smart": "gpt-6.1-sol",
    "openai_fast": "gpt-6-luna",
    "gemini_smart": "gemini-3.8-flash",
    "gemini_fast": "gemini-3.5-flash-lite",
    # Results file
    "results_path": "~/Desktop/Almo results.xlsx",
    "theme": "dark",
}

PROVIDERS = {
    "Gmail": {"smtp": ("smtp.gmail.com", 465), "imap": ("imap.gmail.com", 993),
              "help": "https://myaccount.google.com/apppasswords"},
    "Fastmail": {"smtp": ("smtp.fastmail.com", 465), "imap": ("imap.fastmail.com", 993),
                 "help": "https://app.fastmail.com/settings/security/apppasswords"},
    # Paid Zoho organisation accounts (you@yourdomain) use the *pro hosts; the
    # exact ones are under Zoho Mail > Settings > Mail Accounts > IMAP.
    "Zoho": {"smtp": ("smtppro.zoho.eu", 465), "imap": ("imappro.zoho.eu", 993),
             "help": "https://accounts.zoho.eu/home#security/app_password", "editable": True},
}


def _keyring():
    try:
        import keyring

        keyring.get_password(_SERVICE, "__probe__")
        return keyring
    except Exception:
        return None


def get_secret(name):
    kr = _keyring()
    if kr:
        try:
            value = kr.get_password(_SERVICE, name)
            if value:
                return value
        except Exception:
            pass
    return db.get_settings().get("_secret_" + name, "")


def set_secret(name, value):
    kr = _keyring()
    if kr:
        try:
            if value:
                kr.set_password(_SERVICE, name, value)
            else:
                try:
                    kr.delete_password(_SERVICE, name)
                except Exception:
                    pass
            db.save_settings({"_secret_" + name: ""})
            return
        except Exception:
            pass
    db.save_settings({"_secret_" + name: value})


def load(with_secrets=True):
    stored = db.get_settings()
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in stored.items() if not k.startswith("_")})
    if not stored.get("_gaps_v2"):
        # Older versions sent every 1-3 minutes per mailbox; move saved defaults
        # to the slower pace, keep anything someone chose on purpose.
        fix = {"_gaps_v2": True}
        if stored.get("gap_min", 60) == 60 and stored.get("gap_max", 180) == 180:
            fix.update(gap_min=DEFAULTS["gap_min"], gap_max=DEFAULTS["gap_max"])
            cfg.update(gap_min=DEFAULTS["gap_min"], gap_max=DEFAULTS["gap_max"])
        db.save_settings(fix)
    if "encrypted-tbn0.gstatic.com" in (cfg.get("logo_url") or ""):
        cfg["logo_url"] = DEFAULTS["logo_url"]     # the old app's placeholder logo
    if with_secrets:
        for key in SECRET_KEYS:
            cfg[key] = get_secret(key)
    p = PROVIDERS.get(cfg["provider"])
    if p:
        cfg["smtp_host"], cfg["smtp_port"] = p["smtp"]
        cfg["imap_host"], cfg["imap_port"] = p["imap"]
    return cfg


def public():
    """Settings for the browser: secrets replaced by whether they are set."""
    cfg = load()
    for key in SECRET_KEYS:
        cfg[key + "_set"] = bool(cfg.pop(key))
    cfg["ai_key_set"] = cfg.get((cfg.get("ai_provider") or "anthropic") + "_key_set", False)
    cfg["database"] = db.describe()
    cfg["mailboxes"] = public_mailboxes()
    cfg["providers"] = {k: {"smtp": v["smtp"], "imap": v["imap"], "help": v["help"],
                            "editable": bool(v.get("editable"))} for k, v in PROVIDERS.items()}
    return cfg


INT_KEYS = {"smtp_port", "imap_port", "nudge_days", "max_nudges", "daily_limit",
            "gap_min", "gap_max", "work_start", "work_end", "inbox_every_min",
            "recontact_days", "global_gap_min", "global_gap_max", "price_minimum", "price_round"}
FLOAT_KEYS = {"price_multiplier"}
BOOL_KEYS = {"running", "check_sites", "translate", "auto_followup", "find_direct"}


def save(values):
    """Validate and store. Returns a list of plain-language problems."""
    problems, clean = [], {}
    for key, value in values.items():
        if key in SECRET_KEYS:
            if value is not None and value != "":
                set_secret(key, str(value).strip().replace(" ", "") if key == "email_password"
                           else str(value).strip())
            continue
        if key not in DEFAULTS:
            continue
        if key in INT_KEYS:
            try:
                value = int(str(value).strip())
                if value < 0:
                    raise ValueError
            except ValueError:
                problems.append("%s must be a whole number" % key.replace("_", " "))
                continue
        elif key in FLOAT_KEYS:
            try:
                value = float(str(value).strip().replace(",", "."))
                if value <= 0:
                    raise ValueError
            except ValueError:
                problems.append("%s must be a number" % key.replace("_", " "))
                continue
        elif key in BOOL_KEYS:
            value = bool(value)
        elif isinstance(value, str):
            value = value.strip()
        clean[key] = value
    for lo, hi in (("gap_min", "gap_max"), ("global_gap_min", "global_gap_max")):
        if lo in clean and hi in clean and clean[hi] < clean[lo]:
            clean[hi] = clean[lo]
    if clean.get("price_round") == 0:
        clean["price_round"] = 1
    if "send_mode" in clean and clean["send_mode"] not in ("off", "test", "live"):
        clean.pop("send_mode")
    if "ai_provider" in clean and clean["ai_provider"] not in ("anthropic", "openai", "gemini"):
        clean.pop("ai_provider")
    db.save_settings(clean)
    return problems


def ready_to_send(cfg):
    """What's missing before mail can go out, in plain words."""
    boxes = mailboxes()
    if not boxes:
        return ["a sending mailbox"]
    if not any(b["active"] for b in boxes):
        return ["an active mailbox"]
    if not any(box_ready(b) for b in boxes if b["active"]):
        return ["a mailbox with an app password and a sender name"]
    return []


# --------------------------------------------------------------------------- #
# Sending mailboxes - pitches are spread across all active ones
# --------------------------------------------------------------------------- #
BOX_FIELDS = ("label", "provider", "email", "smtp_host", "smtp_port", "imap_host",
              "imap_port", "sender_name", "sender_title", "daily_limit", "active")


def _box_secret(box_id):
    return "mailbox_%d" % int(box_id)


def mailboxes(active_only=False, with_secrets=True):
    rows = db.query("SELECT * FROM mailboxes%s ORDER BY id" % (" WHERE active=1" if active_only else ""))
    for r in rows:
        r["active"] = bool(r["active"])
        if with_secrets:
            r["password"] = get_secret(_box_secret(r["id"]))
    return rows


def mailbox(box_id):
    for b in mailboxes():
        if b["id"] == box_id:
            return b
    return None


def box_ready(box):
    return bool(box.get("email") and box.get("password") and box.get("sender_name")
                and box.get("smtp_host") and box.get("imap_host"))


def box_cfg(cfg, box):
    """The settings to send as this mailbox (mail.py reads these keys)."""
    out = dict(cfg)
    out.update(email=box["email"], email_password=box.get("password", ""),
               smtp_host=box["smtp_host"], smtp_port=int(box["smtp_port"] or 465),
               imap_host=box["imap_host"], imap_port=int(box["imap_port"] or 993),
               sender_name=box.get("sender_name") or "",
               sender_title=box.get("sender_title") or cfg.get("sender_title", ""),
               mailbox_id=box["id"])
    return out


def public_mailboxes():
    out = []
    for b in mailboxes():
        b["password_set"] = bool(b.pop("password"))
        b["ready"] = b["password_set"] and bool(b["email"] and b["sender_name"])
        out.append(b)
    return out


def save_mailbox(values, box_id=None):
    """Create or update a mailbox. Returns (id, problems)."""
    clean, problems = {}, []
    for key in BOX_FIELDS:
        if key not in values:
            continue
        v = values[key]
        if key in ("smtp_port", "imap_port", "daily_limit"):
            try:
                v = int(str(v).strip())
                if v < 0:
                    raise ValueError
            except ValueError:
                problems.append("%s must be a whole number" % key.replace("_", " "))
                continue
        elif key == "active":
            v = 1 if v else 0
        else:
            v = str(v or "").strip()
        clean[key] = v
    if "email" in clean:
        clean["email"] = clean["email"].lower()
        if "@" not in clean["email"]:
            problems.append("Enter the mailbox's email address")
    p = PROVIDERS.get(clean.get("provider", ""))
    if p:
        # Fixed servers for Gmail/Fastmail; Zoho only fills them in when empty.
        if not p.get("editable") or not clean.get("smtp_host"):
            clean["smtp_host"], clean["smtp_port"] = p["smtp"]
        if not p.get("editable") or not clean.get("imap_host"):
            clean["imap_host"], clean["imap_port"] = p["imap"]
    if problems:
        return box_id, problems
    with db.tx() as conn:
        if box_id:
            if clean:
                conn.execute("UPDATE mailboxes SET %s WHERE id=?" % ", ".join("%s=?" % k for k in clean),
                             (*clean.values(), box_id))
        else:
            if not clean.get("email"):
                return None, ["Enter the mailbox's email address"]
            if conn.execute("SELECT 1 AS x FROM mailboxes WHERE email=?", (clean["email"],)).fetchone():
                return None, ["%s is already added" % clean["email"]]
            clean.setdefault("daily_limit", int(load(False).get("daily_limit") or 40))
            box_id = db.insert(conn, "INSERT INTO mailboxes (%s, created_at) VALUES (%s)" % (
                ", ".join(clean), ",".join("?" * (len(clean) + 1))), (*clean.values(), time.time()))
    pw = values.get("password")
    if pw:
        set_secret(_box_secret(box_id), str(pw).strip().replace(" ", ""))
    return box_id, []


def delete_mailbox(box_id):
    set_secret(_box_secret(box_id), "")
    with db.tx() as conn:
        conn.execute("DELETE FROM mailboxes WHERE id=?", (box_id,))


def migrate_mailbox():
    """Older versions had one mailbox in the settings - make it mailbox #1."""
    if db.one("SELECT 1 AS x FROM mailboxes LIMIT 1"):
        return
    cfg = load()
    if not cfg.get("email"):
        return
    box_id, _ = save_mailbox({
        "label": cfg.get("sender_name") or cfg["email"], "provider": cfg.get("provider") or "Other",
        "email": cfg["email"], "smtp_host": cfg.get("smtp_host"), "smtp_port": cfg.get("smtp_port"),
        "imap_host": cfg.get("imap_host"), "imap_port": cfg.get("imap_port"),
        "sender_name": cfg.get("sender_name"), "sender_title": cfg.get("sender_title"),
        "daily_limit": cfg.get("daily_limit"), "active": True,
        "password": cfg.get("email_password") or "",
    })
    if box_id:
        with db.tx() as conn:
            conn.execute("UPDATE sites SET mailbox_id=? WHERE mailbox_id IS NULL AND sent_at IS NOT NULL",
                         (box_id,))
