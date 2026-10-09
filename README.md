# Almo

Paste a list of websites. Almo checks each site, finds the right email, sends your pitch, reads the replies, asks for anything missing and collects the prices.

## Start

Double-click **Start Almo.command**. The first start takes about a minute. The app opens in its own window.

If macOS says it can't be opened: right-click the file → **Open** → **Open**.

## First time

1. **Settings → Email**: Gmail or Fastmail address and an app password, then *Save and test*.
2. **Settings → AI**: pick Claude, OpenAI or Gemini, paste that API key, then *Save and test*.
3. **Pitch email**: check the text.
4. **Add websites**.
5. **Settings → Sending → Test**: every email goes to you. Reply to one with some prices to see the whole loop. Then switch to **Live**.

Almo only works while the window is open. Your data stays in `~/.almo`. Passwords are kept in the macOS Keychain.

## Database

**Database → All websites** always shows every website, whichever campaign is selected. It holds every website you know, with prices and terms. Use **Import** to bring in your existing Excel or CSV file. Every sheet is read, and columns are found by their names, in English or Latvian.

Importing never overwrites what Almo collected. It only fills in fields that are empty.

You can filter by country, price, casino, crypto, loans, adult and link insertion. Select websites and press **Ask for prices** to have Almo write to them. If a website already has an email in the database, Almo uses it instead of searching the site.

Websites already in the database are skipped when you add a list, so nobody is emailed twice.

## Shared database (PostgreSQL)

By default Almo keeps everything on this computer in SQLite (`~/.almo/almo.db`). To share one database with the team, for example on outreach.uprankd.com:

1. Create an empty PostgreSQL database.
2. Optionally, copy what you already have into it:
   `.venv/bin/python tools/move_to_postgres.py postgresql://user:password@host:5432/almo`
3. Copy `database_url.txt.example` to `database_url.txt` and put the same address in it.
4. Restart Almo. **Settings → Advanced → Database** shows which one is in use.

Running on a RunCloud server (shared database and/or Almo as a website): see [docs/RUNCLOUD.md](docs/RUNCLOUD.md).

Several computers can run Almo on the same database. A website is claimed before it is pitched, so it is only ever emailed once. Each person sends from their own mailbox and Almo reads the replies there.

## What happens to each website

Queued → Checking site → Ready to send → Waiting for reply → Reply received → Prices collected

Along the way:

- **Not a fit**: the site doesn't publish articles.
- **No email found**: no contact address on the site.
- **Followed up**: the reply was missing something, so Almo asked for it.
- **Needs you**: they sent a file or link, or asked something only you can answer.
- **No reply**: still silent after one reminder.
- **Bounced**: the address doesn't work, and there was no other address to try.

## For developers

`python3 tests/test_flow.py`, `tests/test_import.py` and `tests/test_ai.py` run the automation, the import and the three AI providers against a fake mailbox and fake AI answers.

The same tests run against PostgreSQL when `DATABASE_URL` is set.
