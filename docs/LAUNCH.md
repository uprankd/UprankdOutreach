# Launching Almo on the RunCloud VPS

A checklist for putting Almo live at **https://outreach.uprankd.com** on the RunCloud managed VPS: PostgreSQL, Google sign-in for @uprankd.com accounts only, and HTTPS. The steps are in launch order. The full reference (in Latvian) is [RUNCLOUD.md](RUNCLOUD.md).

Time needed: about 45 minutes, plus DNS and Google setup.

```
Server user:   runcloud
Almo folder:   /home/runcloud/apps/almo
Data folder:   /home/runcloud/almo-data
Almo port:     8765 (internal only, 127.0.0.1)
Database:      almo (user almo)
Domain:        outreach.uprankd.com
```

---

## Before you start

- [ ] A server in RunCloud running Ubuntu 22.04 or 24.04, with SSH access as `root` and as `runcloud`.
- [ ] A DNS **A record** `outreach.uprankd.com` → the server's IP. Check it with `dig +short outreach.uprankd.com`.
- [ ] Access to the GitHub repo `uprankd/UprankdOutreach`, either a personal access token or a deploy key.
- [ ] Someone with access to Google Cloud for uprankd.com (needed in step 6).
- [ ] The mailboxes Almo will send from, each with an **app password**: Gmail, Fastmail or Zoho.
- [ ] An AI API key: Anthropic, OpenAI or Gemini.

---

## 1. Server basics (as root)

```bash
apt update
apt install -y postgresql python3-venv git
systemctl enable --now postgresql
timedatectl set-timezone Europe/Riga        # "Sending hours" use the server clock
```

## 2. Database (as root)

Replace the password with a long random one, for example from `openssl rand -base64 24`:

```bash
sudo -u postgres psql <<'SQL'
CREATE USER almo WITH PASSWORD 'CHANGE-THIS-PASSWORD';
CREATE DATABASE almo OWNER almo;
SQL
```

Almo creates its tables on first start. The database only listens on the server itself, and nothing else needs to be opened.

## 3. Code (as runcloud)

```bash
mkdir -p /home/runcloud/apps /home/runcloud/almo-data
cd /home/runcloud/apps
git clone https://github.com/uprankd/UprankdOutreach.git almo
cd almo
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

`git clone` asks for your GitHub username and a **personal access token**, not your password. You can instead add the server's SSH key as a read-only deploy key and clone `git@github.com:uprankd/UprankdOutreach.git`.

## 4. Settings file `.env` (as runcloud)

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

```ini
ALMO_SERVER=1
ALMO_NO_BROWSER=1
ALMO_PORT=8765
ALMO_DATA_DIR=/home/runcloud/almo-data
ALMO_PUBLIC_URL=https://outreach.uprankd.com
DATABASE_URL=postgresql://almo:CHANGE-THIS-PASSWORD@127.0.0.1:5432/almo

# Google sign-in (step 6). Leave empty for now.
ALMO_GOOGLE_CLIENT_ID=
ALMO_GOOGLE_CLIENT_SECRET=
ALMO_ALLOWED_DOMAIN=uprankd.com
# Optional: only these people (empty = everyone @uprankd.com)
ALMO_ALLOWED_EMAILS=
```

Never commit `.env` to GitHub or paste it into a chat. Mailbox passwords and the AI key don't go in `.env`; you enter them inside Almo (step 8).

## 5. Keep Almo running: Supervisor

In RunCloud, go to **Server → Supervisor → Create Job**:

| Field | Value |
| --- | --- |
| Name | `almo` |
| User | `runcloud` |
| Directory | `/home/runcloud/apps/almo` |
| Command | `/home/runcloud/apps/almo/.venv/bin/python app.py` |
| Auto start / Auto restart | on |
| Processes | **1** (Almo must run exactly once) |
| Additional config | `stopasgroup=true` and `killasgroup=true`, one per line |

If the form asks for a Vendor Binary, pick none. If Supervisor won't accept the command, use systemd instead (RUNCLOUD.md, appendix A).

Check over SSH:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/api/settings
```

- **403** means it works. Almo refuses everyone until Google sign-in is set up, as it should.
- No answer means Almo isn't running. Check **Supervisor → almo → Logs**.

## 6. Domain, proxy and HTTPS

1. **Web Application → Create Web Application → Custom Web App**: domain `outreach.uprankd.com`, user `runcloud`.
2. Web app → **Settings** → stack **Native NGiNX + Custom Config** → **Update Stack**.
3. Web app → **NGiNX Config → Add a New Config → Predefined Config → Proxy**, with this content:

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8765;
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_read_timeout 300s;
       client_max_body_size 50m;     # Excel imports
   }
   ```

   Click **Run and Debug**, then **Create Config**.
4. Web app → **SSL/TLS** → Let's Encrypt, and turn on **HTTPS redirect**.

Opening https://outreach.uprankd.com should now show "Sign-in isn't set up".

## 7. Google sign-in (@uprankd.com only)

In [Google Cloud Console](https://console.cloud.google.com/):

1. Create a project called `Uprankd Outreach`.
2. **OAuth consent screen** (or **Google Auth Platform → Branding / Audience**): app name `Uprankd Outreach`, audience **Internal**.
3. **Credentials → Create credentials → OAuth client ID**:
   - Type: **Web application**
   - Authorized redirect URI: `https://outreach.uprankd.com/auth/callback`
4. Copy the **Client ID** and **Client secret** into `.env`:

   ```ini
   ALMO_GOOGLE_CLIENT_ID=1234567890-xxxx.apps.googleusercontent.com
   ALMO_GOOGLE_CLIENT_SECRET=GOCSPX-xxxx
   ```

5. Restart Almo: **Supervisor → almo → Restart**, or `supervisorctl restart almo`.

Open https://outreach.uprankd.com. You should see **Continue with Google**. Sign in with your @uprankd.com account. A Gmail or other company account must be refused; test that once.

## 8. First setup inside Almo

1. **Settings → Mailboxes → Add mailbox** for each sending address.
   - **Gmail / Fastmail**: email address and app password.
   - **Zoho**: the servers default to `smtppro.zoho.eu` / `imappro.zoho.eu`, which suit paid accounts on uprankd.com. If the account lives on zoho.com, change `.eu` to `.com`. The exact servers are in Zoho Mail → Settings → Mail Accounts → IMAP.
   - Fill in the sender name and job title. They go in that mailbox's signature.
   - Set a daily limit: **20–30 for a new mailbox**, raised slowly over a few weeks.
   - Each mailbox shows **✓ Connected** once it's added.
2. **Settings → AI**: pick Claude, OpenAI or Gemini, paste the key and click **Save and test**.
3. **All websites → Import**: your Excel database. Websites marked as own or closed are never pitched.
4. **Pitch email**: check pitch A. To A/B test, add a version with **+ A/B version**.
5. **Settings → Sending → Test**: emails go to your own mailbox instead of the websites. Add 2–3 websites and check how the pitch, signature and logo look in Gmail and Outlook.
6. When it looks right, switch **Sending → Live**.

## 9. Email deliverability (before going Live)

For every domain you send from, check these DNS records. Your DNS host and mail provider set them; RunCloud doesn't.

- [ ] **SPF**: one TXT record on the domain that includes every provider you use. Examples: `include:_spf.google.com`, `include:spf.messagingengine.com` (Fastmail), `include:zoho.eu`. Only one SPF record per domain.
- [ ] **DKIM**: turned on in each provider's admin panel, with its DNS record added.
- [ ] **DMARC**: a TXT record `_dmarc.uprankd.com`, starting with `v=DMARC1; p=none; rua=mailto:you@uprankd.com`.
- [ ] Send a test to https://www.mail-tester.com and aim for 9/10 or better.

## 10. Backups

In RunCloud, go to **Server → Cron Jobs** and add a job as user `root` that runs every night at 03:15:

```
15 3 * * *  mkdir -p /var/backups && sudo -u postgres pg_dump -Fc almo > /var/backups/almo-$(date +\%F).dump && find /var/backups -name 'almo-*.dump' -mtime +14 -delete
```

Mailbox app passwords and AI keys are stored in the database on the server, so keep backups private. Copy one off the server weekly.

---

## Launch checklist

- [ ] https://outreach.uprankd.com opens over HTTPS, and http redirects to https.
- [ ] Only @uprankd.com accounts can sign in. Others are refused.
- [ ] **Settings → Advanced → Database** shows **PostgreSQL**, not SQLite.
- [ ] Every mailbox shows ✓ Connected, and SPF, DKIM and DMARC pass.
- [ ] The AI test passes.
- [ ] A test-mode pitch arrives with the Uprankd logo in the signature.
- [ ] A reply to that test pitch shows up in Almo within a few minutes.
- [ ] The nightly backup job exists, and one manual dump works.
- [ ] Sending is switched to **Live**.

---

## Updating to a new version

```bash
cd /home/runcloud/apps/almo
git pull
.venv/bin/pip install -r requirements.txt
supervisorctl restart almo        # or Supervisor → almo → Restart
```

Database changes apply automatically when Almo starts. Your data stays.

## When something's wrong

| Symptom | Check |
| --- | --- |
| 502 Bad Gateway | Almo isn't running. Check Supervisor → almo → Logs, then restart. |
| "Sign-in isn't set up" | The Google ID or secret is missing in `.env`, or Almo wasn't restarted. |
| Google shows `redirect_uri_mismatch` | The redirect URI must be exactly `https://outreach.uprankd.com/auth/callback`. |
| After signing in you land on the login page again | The site was opened over `http://`. Turn on the HTTPS redirect. |
| Database shows SQLite | `.env` is missing from the Almo folder, or `DATABASE_URL` is wrong. |
| A mailbox has a red dot | Check its message under Settings → Mailboxes. Usually it's a wrong app password or the wrong Zoho server (.eu vs .com). |
| Nothing is sent | Almo is paused (top bar), Sending isn't Live, outside sending hours, or every mailbox hit its daily limit. |
| A large Excel import fails | Raise `client_max_body_size` in the NGINX config. |
