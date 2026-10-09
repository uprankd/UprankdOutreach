"""Copy everything from this computer's Almo (SQLite) into a PostgreSQL database.

    python3 tools/move_to_postgres.py postgresql://user:password@host:5432/almo

Websites, prices, email threads, campaigns, activity and settings are copied.
The PostgreSQL database must be empty (Almo creates its tables). Your local
file is not changed, so you can run this again into a fresh database.

Afterwards, put the same address in database_url.txt next to app.py (or set
DATABASE_URL) and start Almo - it will use PostgreSQL from then on.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))

import db  # noqa: E402

TABLES = ("campaigns", "sites", "messages", "seen_mail", "events", "settings")


def main():
    if len(sys.argv) != 2 or not sys.argv[1].startswith(("postgres://", "postgresql://")):
        print(__doc__)
        return 2
    url = sys.argv[1]
    if not os.path.isfile(db.DB_PATH):
        print("No local Almo data found at %s" % db.DB_PATH)
        return 1

    db.configure("")                       # read the local SQLite file
    db.init()                              # bring it up to the current layout first
    data = {t: db.query("SELECT * FROM %s" % t) for t in TABLES}

    db.configure(url)
    db.init()
    if db.one("SELECT COUNT(*) AS n FROM sites")["n"]:
        print("That PostgreSQL database already has websites in it - use an empty one.")
        return 1
    with db.tx() as conn:
        conn.execute("DELETE FROM campaigns")     # the default one init() made
        for table in TABLES:
            for row in data[table]:
                cols = list(row)
                conn.execute("INSERT INTO %s (%s) VALUES (%s)" % (
                    table, ", ".join(cols), ",".join("?" * len(cols))), [row[c] for c in cols])
            if table in ("campaigns", "sites", "messages", "events"):
                # Continue ids after the copied ones.
                conn.execute_raw(
                    "SELECT setval(pg_get_serial_sequence('%s','id'), "
                    "GREATEST((SELECT COALESCE(MAX(id), 0) FROM %s), 1))" % (table, table))
            print("  %-10s %6d rows" % (table, len(data[table])))
    print("\nDone. Now put this in database_url.txt next to app.py:\n  %s" % url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
