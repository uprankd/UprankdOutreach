"""App settings with sensible defaults. Passwords and keys go to the system
keychain (macOS Keychain / Windows Credential Manager) when available."""

import db

SECRET_KEYS = ("email_password", "anthropic_key")
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
    "logo_url": ("https://encrypted-tbn0.gstatic.com/images?q=tbn:AND9GcSj_J7eoaaf"
                 "C3ooB5otb0EKdktJqbzYmFyBxILNlK3xwbwJCvly-XYViTQs&s=10"),
    # Automation
    "send_mode": "off",               # off | test | live
    "running": True,
    "check_sites": True,              # skip sites that don't publish articles
    "translate": True,                # write the pitch in the site's language
    "auto_followup": True,            # reply automatically when prices are missing
    "nudge_days": 4,                  # remind once if no reply after N days
    "max_nudges": 1,
    "daily_limit": 40,
    "gap_min": 60,
    "gap_max": 180,
    "work_start": 8,
    "work_end": 19,
    "inbox_every_min": 5,
    "recontact_days": 180,
    # AI
    "model_smart": "claude-sonnet-5-5",
    "model_fast": "claude-haiku-5-5",
    # Results file
    "results_path": "~/Desktop/Almo results.xlsx",
    "theme": "dark",
}

PROVIDERS = {
    "Gmail": {"smtp": ("smtp.gmail.com", 465), "imap": ("imap.gmail.com", 993),
              "help": "https://myaccount.google.com/apppasswords"},
    "Fastmail": {"smtp": ("smtp.fastmail.com", 465), "imap": ("imap.fastmail.com", 993),
                 "help": "https://app.fastmail.com/settings/security/apppasswords"},
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
    cfg["database"] = db.describe()
    return cfg


INT_KEYS = {"smtp_port", "imap_port", "nudge_days", "max_nudges", "daily_limit",
            "gap_min", "gap_max", "work_start", "work_end", "inbox_every_min",
            "recontact_days"}
BOOL_KEYS = {"running", "check_sites", "translate", "auto_followup"}


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
        elif key in BOOL_KEYS:
            value = bool(value)
        elif isinstance(value, str):
            value = value.strip()
        clean[key] = value
    if "gap_min" in clean and "gap_max" in clean and clean["gap_max"] < clean["gap_min"]:
        clean["gap_max"] = clean["gap_min"]
    if "send_mode" in clean and clean["send_mode"] not in ("off", "test", "live"):
        clean.pop("send_mode")
    db.save_settings(clean)
    return problems


def ready_to_send(cfg):
    """What's missing before mail can go out, in plain words."""
    missing = []
    if not cfg.get("email"):
        missing.append("your email address")
    if not cfg.get("email_password"):
        missing.append("an app password")
    if not cfg.get("sender_name"):
        missing.append("your name for the signature")
    if not cfg.get("smtp_host") or not cfg.get("imap_host"):
        missing.append("mail server addresses")
    return missing
