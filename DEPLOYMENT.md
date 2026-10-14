# Uprankd Outreach: RunCloud deployment

This is a deployment add-on for the supplied UprankdOutreach source. Copy server.py,
requirements-server.txt and deploy/ into the repository root, then commit them to GitHub.
The app remains Flask/Python; no Node, PM2, Supabase or application rewrite is needed.
The original app.py remains available for local desktop use.

## Isolation on the shared VPS

Proposed domain: outreach.uprankd.com. Confirm DNS points to this VPS.
Use a separate RunCloud system user named outreach and a Custom Web Application
named uprankd-outreach owned by that user. Use the following paths consistently:

- Git checkout: /home/outreach/webapps/uprankd-outreach
- Private runtime files: /home/outreach/outreach-data
- Database: uprankd_outreach, database role: outreach
- HTTP backend: 127.0.0.1:8765
- Service: outreach.service

The domain and user are proposed values, not verified server settings. If RunCloud
creates a different checkout path, update the unit file and commands before use.
Do not put .env or runtime data under a publicly served directory. Use RunCloud's
Custom Config proxy stack before making the domain reachable.

Run these read-only checks as a sudo-capable user before changing anything:

```bash
lsb_release -a
free -h
df -h /
sudo ss -ltnp
sudo systemctl status postgresql --no-pager
sudo -u postgres psql -c 'SELECT version();'
```

Confirm port 8765 is unused. The screenshot does not reveal occupied ports,
PostgreSQL versions, free memory or SSH access. If the port is occupied, select
another unused port and update both .env and deploy/nginx.conf.
If PostgreSQL exists, reuse the existing cluster with a new role and database.
Do not reinstall, upgrade, restart or change its global configuration for this app.
Do not restart other apps, modify their proxy blocks or change the global timezone.

## Server packages and database

Install Python tooling if missing (sudo-capable user):

```bash
sudo apt update
sudo apt install python3-venv git
```

Only if PostgreSQL is absent, install it separately:

```bash
sudo apt install postgresql
sudo systemctl enable --now postgresql
```

Create a distinct non-superuser role and its database. Do not rerun these creation
commands against an existing role/database. Set the password interactively:

```bash
sudo -u postgres createuser --no-superuser --no-createdb --no-createrole outreach
sudo -u postgres psql
```

Inside psql:

```text
\password outreach
\q
```

Use a long random hexadecimal password so it needs no URL encoding. Then:

```bash
sudo -u postgres createdb --owner=outreach uprankd_outreach
```

Connect over 127.0.0.1 using this role. Do not open 5432 in the firewall or change
listen_addresses to '*'. If the existing PostgreSQL cluster uses another port,
put that port in DATABASE_URL. No global pg_hba changes should be needed for a
normal local password-authenticated setup; inspect existing rules if login fails.

## GitHub and Python environment

Upload the supplied app source plus these deployment files to a private GitHub
repository. Exclude .env, google_oauth.json, database_url.txt, .venv and runtime data.
Configure RunCloud Git deployment using a repository-specific read-only SSH deploy
key. Deploy main to the checkout path above. Do not put a GitHub token in a clone URL.

Run as the outreach user after the checkout exists:

```bash
cd /home/outreach/webapps/uprankd-outreach
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-server.txt
install -d -m 700 /home/outreach/outreach-data
cp deploy/server.env.example .env
chmod 600 .env
nano .env
```

Fill in the database password and real Google OAuth values. Keep secrets on the VPS.
Dependencies are range constrained, not fully locked; establish a tested dependency
lock before relying on unattended upgrades.

## Google sign-in

Create a Google OAuth Web Application client for your Workspace, with Internal
audience where available. Configure this exact authorized redirect URI:

https://outreach.uprankd.com/auth/callback

Put its Client ID and secret in .env. ALMO_ALLOWED_DOMAIN=uprankd.com restricts
Workspace access. ALMO_ALLOWED_EMAILS optionally narrows access to named employees.
Remove ALMO_INSECURE_COOKIES if it is present. Set ALMO_SERVER=1.
The production launcher refuses missing OAuth, SQLite and non-local database URLs.
Do not use placeholder OAuth values for launch.

## Production process

The original guide runs python app.py, which starts Flask's development server.
Use server.py instead: it initializes tables, starts the app's background worker
and serves HTTP through Waitress in one process. A local file lock prevents two
copies of this launcher from using the same runtime directory.
Do not start app.py, a desktop client or another worker against this database in
parallel. Do not use waitress-serve app:app directly: it bypasses worker startup.

As a sudo-capable user:

```bash
sudo cp /home/outreach/webapps/uprankd-outreach/deploy/outreach.service /etc/systemd/system/outreach.service
sudo systemctl daemon-reload
sudo systemctl enable --now outreach.service
sudo systemctl status outreach.service --no-pager
sudo journalctl -u outreach.service -n 80 --no-pager
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/api/settings
```

With OAuth configured, an unauthenticated API request should return 401.
The service sets TZ=Europe/Riga for this app only.
Choose systemd OR RunCloud Supervisor, never both. For Supervisor use the same
Python server.py command, directory and user, one process, auto restart, and
stopasgroup=true / killasgroup=true. Do not create the systemd unit in that case.

## RunCloud NGINX and HTTPS

For this web app only: Settings -> Native NGiNX + Custom Config. In NGiNX Config,
use the predefined Proxy configuration and replace its location block with
 deploy/nginx.conf. Do not create two location / blocks or duplicate proxy_pass.
Use Run and Debug before saving. Leave RunCloud-managed NGINX files untouched.

Issue Let's Encrypt for outreach.uprankd.com and enable HTTPS redirect.
Do not add www.outreach.uprankd.com unless you configure its DNS too.
The backend binds only to 127.0.0.1; leave port 8765 closed to external traffic.

## Launch acceptance checks

1. HTTPS login page loads; the API rejects anonymous access.
2. A permitted @uprankd.com account signs in; an unapproved account cannot.
3. Settings -> Advanced -> Database displays PostgreSQL and the intended database.
4. Add mailboxes and AI credentials. Keep sending in Test mode initially.
5. Use your own test recipient to verify sending, reply reading and price extraction.
6. Restart only outreach.service; confirm login, settings and records persist.
7. Verify a database backup and test restore into a separate temporary database.
8. Verify existing VPS websites still respond and monitor memory during site checks.

No live outreach has been authorized or sent by this deployment preparation.
The uploaded code includes multiple mailbox support. Its older RunCloud document
claims one shared mailbox, which no longer matches the source.

## Updating from GitHub

Use RunCloud Git deployment for code changes. Keep .env and outreach-data intact.
During the first deployments, use a controlled update window:

1. Pause outreach in the UI and wait for active sending to finish.
2. Take a backup using the procedure below.
3. Stop only outreach.service.
4. Deploy the chosen GitHub commit through RunCloud.
5. As outreach, install requirements-server.txt in the existing virtual environment.
6. Start outreach.service and check logs plus the unauthenticated API response.
7. Sign in, verify data and resume outreach deliberately.

The worker has no graceful shutdown API; stopping it mid-send can leave an uncertain
send result. Wait for active work rather than relying on service stop to drain it.
Tables and columns are initialized at startup; a code rollback does not undo schema
changes. Keep a pre-update backup and review schema changes before deploying them.
Do not run the bundled tests with DATABASE_URL pointing to production: several tests
delete all rows in the configured database.

For the first launch, avoid automatically deploying every push. Add a RunCloud
webhook only after the manual process and backup/restore checks succeed.

## Backups

Install the backup script outside the checkout as a root-owned script:

```bash
sudo install -m 700 /home/outreach/webapps/uprankd-outreach/deploy/backup.sh /usr/local/sbin/outreach-backup
sudo /usr/local/sbin/outreach-backup
```

In RunCloud Cron Jobs, choose root, command /usr/local/sbin/outreach-backup,
schedule 15 3 * * *. Cron follows the existing server timezone; this is deliberately
not changed. Backups include the database, .env and persistent session/runtime files.
They are private and retained locally for 14 days. Copy them to protected off-server
storage; local backups alone do not cover VPS loss.

For a restore drill, create a separate empty database owned by outreach and restore
with pg_restore --no-owner --role=outreach into that database as postgres. Do not
restore over the running production database. Database and file backups are taken
sequentially; pause sending for a coordinated pre-deployment snapshot.

Mailbox passwords and AI keys fall back to plaintext database settings on headless
Linux. Protect the database, environment file and backups accordingly.

## Evidence and limits

Reviewed: app.py, PostgreSQL adapter, auth, settings, worker, requirements and the
existing RunCloud guide in the supplied ZIP. No VPS or GitHub access was available;
no server changes or deployment were performed. Static checks and automated checks
are reported in VALIDATION.txt. This preparation is not a full application security
audit or a live PostgreSQL integration test.

Official references:
- https://runcloud.io/docs/nginx-reverse-proxy
- https://flask.palletsprojects.com/en/stable/deploying/waitress/
- https://flask.palletsprojects.com/en/stable/deploying/
