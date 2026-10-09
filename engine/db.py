"""Storage: SQLite on this computer, or PostgreSQL on a shared server.

Every website ever added lives here, so the same site is never pitched twice,
and the automation picks up exactly where it stopped after the app is closed.

Which one is used:
  * DATABASE_URL (environment) or a database_url.txt file next to app.py or in
    ~/.almo, holding e.g. postgresql://user:pass@host:5432/almo -> PostgreSQL
  * otherwise -> SQLite, one file at ~/.almo/almo.db

The rest of the app writes plain SQL with ? placeholders; this module adapts it
for PostgreSQL, so both backends run the same code.
"""

import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager

DATA_DIR = os.environ.get("ALMO_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".almo")
DB_PATH = os.path.join(DATA_DIR, "almo.db")
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_lock = threading.RLock()
_local = threading.local()


def _read_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    for folder in (APP_DIR, DATA_DIR):
        path = os.path.join(folder, "database_url.txt")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line
    return ""


URL = _read_url()
KIND = "postgres" if URL.startswith(("postgres://", "postgresql://")) else "sqlite"


def configure(url=""):
    """Switch backend at runtime (used by tests and the move script)."""
    global URL, KIND
    URL = url
    KIND = "postgres" if url.startswith(("postgres://", "postgresql://")) else "sqlite"
    _local.__dict__.clear()


def describe():
    """Where the data lives, for the Settings page. Never shows a password."""
    if KIND == "postgres":
        m = re.match(r"postgres(?:ql)?://(?:[^@/]*@)?([^/:?]+)(?::(\d+))?/([^?]*)", URL)
        host, port, name = (m.group(1), m.group(2) or "5432", m.group(3)) if m else ("?", "", "")
        return {"kind": "PostgreSQL", "where": "%s:%s/%s" % (host, port, name)}
    home = os.path.expanduser("~")
    shown = "~" + DB_PATH[len(home):] if DB_PATH.startswith(home) else DB_PATH
    return {"kind": "SQLite", "where": shown}


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def _schema(kind):
    ident = "BIGSERIAL PRIMARY KEY" if kind == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if kind == "postgres" else "REAL"
    return [x.replace("{ID}", ident).replace("{REAL}", real) for x in (
        """CREATE TABLE IF NOT EXISTS campaigns (
            id {ID}, name TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
            created_at {REAL} NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sites (
            id {ID}, campaign_id INTEGER NOT NULL, domain TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'queued', note TEXT DEFAULT '', language TEXT DEFAULT '',
            fit TEXT DEFAULT '', fit_reason TEXT DEFAULT '', emails TEXT DEFAULT '[]',
            email TEXT DEFAULT '', tried TEXT DEFAULT '[]', subject TEXT DEFAULT '',
            sent_at {REAL}, last_out_at {REAL}, nudges INTEGER DEFAULT 0,
            followups INTEGER DEFAULT 0, replied_at {REAL}, price TEXT DEFAULT '',
            special_price TEXT DEFAULT '', casino TEXT DEFAULT '', loan TEXT DEFAULT '',
            crypto TEXT DEFAULT '', adult TEXT DEFAULT '', sponsored_tag TEXT DEFAULT '',
            link_insertion TEXT DEFAULT '', requirements TEXT DEFAULT '', draft TEXT DEFAULT '',
            attempts INTEGER DEFAULT 0, next_try_at {REAL} DEFAULT 0,
            created_at {REAL} NOT NULL, updated_at {REAL} NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS sites_status ON sites(status)",
        "CREATE INDEX IF NOT EXISTS sites_email ON sites(email)",
        """CREATE TABLE IF NOT EXISTS messages (
            id {ID}, site_id INTEGER NOT NULL, direction TEXT NOT NULL,
            kind TEXT DEFAULT 'pitch', ts {REAL} NOT NULL, from_addr TEXT DEFAULT '',
            to_addr TEXT DEFAULT '', subject TEXT DEFAULT '', body TEXT DEFAULT '',
            message_id TEXT DEFAULT '', test INTEGER DEFAULT 0)""",
        "CREATE INDEX IF NOT EXISTS messages_mid ON messages(message_id)",
        "CREATE INDEX IF NOT EXISTS messages_site ON messages(site_id)",
        "CREATE TABLE IF NOT EXISTS seen_mail (message_id TEXT PRIMARY KEY, ts {REAL} NOT NULL)",
        """CREATE TABLE IF NOT EXISTS events (
            id {ID}, ts {REAL} NOT NULL, site_id INTEGER, kind TEXT NOT NULL, text TEXT NOT NULL)""",
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    )]


# A number out of a text column ('150', ' 99.5 ') - NULL for anything else, so
# sorting and price filters never break on a stray 'Yes' or '150-200'.
_NUM_RE = re.compile(r"^\s*[0-9]+(\.[0-9]+)?\s*$")
PG_NUM = ("CREATE OR REPLACE FUNCTION num(t text) RETURNS double precision AS $f$ "
          "SELECT CASE WHEN t ~ '^\\s*[0-9]+(\\.[0-9]+)?\\s*$' THEN t::double precision END "
          "$f$ LANGUAGE sql IMMUTABLE")


def _num(value):
    if value is None:
        return None
    text = str(value)
    return float(text) if _NUM_RE.match(text) else None


# --------------------------------------------------------------------------- #
# Connections
# --------------------------------------------------------------------------- #
def _pg_sql(sql):
    return sql.replace("%", "%%").replace("?", "%s")


class _PGConn:
    """Makes a psycopg connection accept the same SQL as sqlite3."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, args=()):
        return self.raw.execute(_pg_sql(sql), tuple(args))

    def execute_raw(self, sql):
        return self.raw.execute(sql)


def _pg():
    conn = getattr(_local, "pg", None)
    if conn is not None and not conn.closed and not conn.broken:
        return conn
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(URL, autocommit=True, row_factory=dict_row, connect_timeout=15)
    _local.pg = conn
    return conn


def connect():
    """A SQLite connection (only used for SQLite)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.create_function("num", 1, _num, deterministic=True)
    return conn


@contextmanager
def tx():
    """One write transaction. Use conn.execute(sql, args) with ? placeholders."""
    with _lock:
        if KIND == "postgres":
            raw = _pg()
            with raw.transaction():
                yield _PGConn(raw)
            return
        conn = connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def query(sql, args=()):
    if KIND == "postgres":
        return [dict(r) for r in _pg().execute(_pg_sql(sql), tuple(args)).fetchall()]
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def insert(conn, sql, args=()):
    """Run an INSERT inside tx() and return the new row's id."""
    if KIND == "postgres":
        return conn.execute(sql + " RETURNING id", args).fetchone()["id"]
    return conn.execute(sql, args).lastrowid


DEFAULT_SUBJECT = "Publishing on {domain}"
DEFAULT_BODY = (
    "Hello,\n\n"
    "I'm reaching out from Uprankd, an SEO agency. We'd like to publish articles "
    "on {domain} for our clients and are putting together our list of partner sites.\n\n"
    "Could you please share:\n"
    "1. Your price for a sponsored article\n"
    "2. Whether you accept casino, crypto, loan or adult topics, and the price for those\n"
    "3. Whether articles are marked as sponsored or advertising\n"
    "4. Whether you offer link insertions into existing articles, and the price\n\n"
    "Thank you!"
)


MIGRATIONS = {
    "sites": [("country", "TEXT DEFAULT ''"), ("source", "TEXT DEFAULT 'almo'"),
              ("dr", "TEXT DEFAULT ''"), ("traffic", "TEXT DEFAULT ''"),
              ("contacted_before", "INTEGER DEFAULT 0")],
}


def init():
    with tx() as conn:
        if KIND == "postgres":
            for stmt in _schema("postgres"):
                conn.execute_raw(stmt)
            conn.execute_raw(PG_NUM)
            for table, cols in MIGRATIONS.items():
                for name, decl in cols:
                    conn.execute_raw("ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s" % (table, name, decl))
        else:
            for stmt in _schema("sqlite"):
                conn.execute(stmt)
            for table, cols in MIGRATIONS.items():
                have = {r[1] for r in conn.execute("PRAGMA table_info(%s)" % table)}
                for name, decl in cols:
                    if name not in have:
                        conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, decl))
        conn.execute("CREATE INDEX IF NOT EXISTS sites_country ON sites(country)")
        if not conn.execute("SELECT 1 AS x FROM campaigns LIMIT 1").fetchone():
            conn.execute(
                "INSERT INTO campaigns (name, subject, body, created_at) VALUES (?,?,?,?)",
                ("General", DEFAULT_SUBJECT, DEFAULT_BODY, time.time()))


# --------------------------------------------------------------------------- #
# Sites
# --------------------------------------------------------------------------- #
SITE_FIELDS = {
    "status", "note", "language", "fit", "fit_reason", "emails", "email", "tried",
    "subject", "sent_at", "last_out_at", "nudges", "followups", "replied_at",
    "price", "special_price", "casino", "loan", "crypto", "adult", "sponsored_tag",
    "link_insertion", "requirements", "draft", "attempts", "next_try_at",
    "campaign_id", "country", "source", "dr", "traffic", "contacted_before",
}


def update_site(site_id, **fields):
    bad = set(fields) - SITE_FIELDS
    if bad:
        raise ValueError("unknown fields %s" % bad)
    for key in ("emails", "tried"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key])
    fields["updated_at"] = time.time()
    cols = ", ".join("%s=?" % k for k in fields)
    with tx() as conn:
        conn.execute("UPDATE sites SET %s WHERE id=?" % cols, (*fields.values(), site_id))


def get_site(site_id):
    row = one("SELECT * FROM sites WHERE id=?", (site_id,))
    return _decode(row) if row else None


def _decode(row):
    for key in ("emails", "tried"):
        try:
            row[key] = json.loads(row.get(key) or "[]")
        except ValueError:
            row[key] = []
    return row


def sites(where="1=1", args=(), order="updated_at DESC", limit=None):
    sql = "SELECT * FROM sites WHERE %s ORDER BY %s" % (where, order)
    if limit:
        sql += " LIMIT %d" % int(limit)
    return [_decode(r) for r in query(sql, args)]


def add_sites(campaign_id, domains):
    """Insert new domains. Returns (added, already_known)."""
    import countries

    added, known = [], []
    now = time.time()
    with tx() as conn:
        for domain in domains:
            if conn.execute("SELECT 1 AS x FROM sites WHERE domain=?", (domain,)).fetchone():
                known.append(domain)
                continue
            conn.execute(
                "INSERT INTO sites (campaign_id, domain, status, country, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                (campaign_id, domain, "queued", countries.from_domain(domain), now, now))
            added.append(domain)
    return added, known


def delete_site(site_id):
    with tx() as conn:
        conn.execute("DELETE FROM messages WHERE site_id=?", (site_id,))
        conn.execute("DELETE FROM events WHERE site_id=?", (site_id,))
        conn.execute("DELETE FROM sites WHERE id=?", (site_id,))


# --------------------------------------------------------------------------- #
# Messages, events, seen mail
# --------------------------------------------------------------------------- #
def add_message(site_id, direction, kind, from_addr, to_addr, subject, body,
                message_id="", test=False, ts=None):
    with tx() as conn:
        conn.execute(
            "INSERT INTO messages (site_id, direction, kind, ts, from_addr, to_addr, "
            "subject, body, message_id, test) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (site_id, direction, kind, ts or time.time(), from_addr, to_addr, subject,
             body, message_id, 1 if test else 0))


def thread(site_id):
    return query("SELECT * FROM messages WHERE site_id=? ORDER BY ts ASC", (site_id,))


def site_for_message_ids(ids):
    ids = [i.strip() for i in ids if i and i.strip()]
    if not ids:
        return None
    marks = ",".join("?" * len(ids))
    row = one("SELECT site_id FROM messages WHERE message_id IN (%s) "
              "ORDER BY ts DESC LIMIT 1" % marks, tuple(ids))
    return row["site_id"] if row else None


def was_seen(message_id):
    return one("SELECT 1 AS x FROM seen_mail WHERE message_id=?", (message_id,)) is not None


def mark_seen(message_id):
    """Remember a message. True if this call was the first to see it."""
    with tx() as conn:
        cur = conn.execute("INSERT INTO seen_mail (message_id, ts) VALUES (?,?) "
                           "ON CONFLICT (message_id) DO NOTHING",
                           (message_id, time.time()))
        return cur.rowcount == 1


def claim(site_id, from_status, to_status):
    """Move a site from one status to another only if nobody else did first."""
    with tx() as conn:
        cur = conn.execute("UPDATE sites SET status=?, updated_at=? WHERE id=? AND status=?",
                           (to_status, time.time(), site_id, from_status))
        return cur.rowcount == 1


def claim_nudge(site_id, current, step=1):
    with tx() as conn:
        cur = conn.execute("UPDATE sites SET nudges=nudges+? WHERE id=? AND nudges=?",
                           (step, site_id, current))
        return cur.rowcount == 1


def log(kind, text, site_id=None):
    with tx() as conn:
        conn.execute("INSERT INTO events (ts, site_id, kind, text) VALUES (?,?,?,?)",
                     (time.time(), site_id, kind, text))


def events(limit=40, site_id=None):
    if site_id:
        return query("SELECT * FROM events WHERE site_id=? ORDER BY id DESC LIMIT ?",
                     (site_id, limit))
    return query("SELECT e.*, s.domain FROM events e LEFT JOIN sites s ON s.id=e.site_id "
                 "ORDER BY e.id DESC LIMIT ?", (limit,))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
def get_settings():
    return {r["key"]: json.loads(r["value"]) for r in query("SELECT * FROM settings")}


def save_settings(values):
    with tx() as conn:
        for key, value in values.items():
            conn.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, json.dumps(value)))
