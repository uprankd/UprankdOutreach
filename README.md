# Almo

Paste a list of websites. Almo checks each site, finds the right email, sends your pitch, reads the replies, asks for anything missing and collects the prices.

## Start

Double-click **Start Almo.command**. The first start takes about a minute. The app opens in its own window.

If macOS says it can't be opened: right-click the file → **Open** → **Open**.

## First time

1. **Settings → Mailboxes**: *Add mailbox* - Gmail, Fastmail, Zoho or any IMAP/SMTP account, with an app password. Add as many as you like: pitches are shared evenly between active ones (each with its own daily limit), and every conversation stays in the mailbox that started it.
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

Server settings go in a `.env` file next to `app.py` - see `.env.example`. Running on a RunCloud server (shared database and/or Almo as a website): see [docs/RUNCLOUD.md](docs/RUNCLOUD.md). On a server Almo asks people to sign in with their @uprankd.com Google account, and it won't open over the network until that's set up.

Several computers can run Almo on the same database. A website is claimed before it is pitched, so it is only ever emailed once. Each computer sends only from the mailboxes whose app password it has, and reads the replies there.

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

`python3 tests/test_flow.py`, `tests/test_import.py`, `tests/test_ai.py`, `tests/test_auth.py` and `tests/test_env.py` run the automation, the import, the three AI providers and Google sign-in against fakes - no accounts or network needed.

The same tests run against PostgreSQL when `DATABASE_URL` is set.

## A/B testing pitches

*Pitch email* → **+ A/B version** adds pitch B (C, D…) to a campaign. Active pitches take turns, so each gets the same share of sends; the A/B table shows sent, replies, reply rate and prices per pitch. Turn a pitch off to stop sending it - its results stay.

## Client price lists

*Export* → **Price list for a client**: set a markup % and/or a fixed margin € per website. The file has only the website, the client price (our price × (1 + markup) + margin, rounded up) and the requirements - no costs, emails or notes. It follows the current filters or selection.

## Email logo

The signature uses https://uprankd.com/logo.svg. Gmail and Outlook don't show SVG images, so Almo sends a PNG copy (`web/email-logo.png`) inside each email instead.
