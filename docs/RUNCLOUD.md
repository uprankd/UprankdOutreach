# Almo uz RunCloud servera

Instrukcija, kā Almo uzlikt un uzturēt uz RunCloud pārvaldīta servera (piemēram, `outreach.uprankd.com`).

Ir divi veidi, un tos var apvienot:

| | Ko dara | Kad izvēlēties |
| --- | --- | --- |
| **A. Kopīga datubāze** | Uz servera ir tikai PostgreSQL. Katrs komandas biedrs palaiž Almo savā datorā, un visi lieto vienu datubāzi. | Katrs sūta no sava e-pasta. |
| **B. Almo kā mājaslapa** | Almo darbojas uz servera, un to atver pārlūkā `https://outreach.uprankd.com`. | Vienam kopīgam outreach e-pastam, un nevienam nekas nav jāinstalē. |

> **Drošība.** B variantā Almo atveras tikai pēc pieteikšanās ar @uprankd.com Google kontu (5. solis). Kamēr tas nav iestatīts, Almo uz servera neatveras vispār.

---

## 0. Kas vajadzīgs

- Serveris RunCloud panelī ar Ubuntu 22.04 vai 24.04.
- SSH piekļuve kā `root` (vai lietotājs ar `sudo`) un kā `runcloud`.
- Domēns, piemēram `outreach.uprankd.com`, kura DNS A ieraksts rāda uz servera IP.
- Piekļuve GitHub repozitorijam `uprankd/UprankdOutreach`.

Komandas zemāk pieņem:

```
Lietotājs:   runcloud
Almo mape:   /home/runcloud/apps/almo
Dati:        /home/runcloud/almo-data
Ports:       8765 (tikai iekšēji, uz 127.0.0.1)
Datubāze:    almo (lietotājs almo)
```

---

## 1. PostgreSQL uzstādīšana (A un B)

RunCloud panelis pārvalda tikai MySQL/MariaDB, tāpēc PostgreSQL uzliek caur SSH kā `root`:

```bash
apt update
apt install -y postgresql
systemctl enable --now postgresql
```

Izveido datubāzi un lietotāju (paroli nomaini uz garu, nejaušu):

```bash
sudo -u postgres psql <<'SQL'
CREATE USER almo WITH PASSWORD 'NOMAINI-SO-PAROLI';
CREATE DATABASE almo OWNER almo;
SQL
```

Almo tabulas izveido pats pirmajā palaišanas reizē.

### Tikai A variantam: atvērt datubāzi komandas datoriem

Ja komandas biedri pieslēdzas no saviem datoriem, PostgreSQL jāklausās arī ārpusē. Atļauj **tikai jūsu biroja / komandas IP adreses**.

1. `/etc/postgresql/<versija>/main/postgresql.conf`:
   ```
   listen_addresses = '*'
   ssl = on
   ```
2. `/etc/postgresql/<versija>/main/pg_hba.conf`, beigās (katram atļautajam IP sava rinda):
   ```
   hostssl  almo  almo  203.0.113.10/32  scram-sha-256
   ```
3. `systemctl restart postgresql`
4. RunCloud panelī: **Server → Security (Firewall)** → atver portu **5432** tikai tiem pašiem IP.

Katrs komandas biedrs savā Almo mapē izveido `database_url.txt`:

```
postgresql://almo:PAROLE@outreach.uprankd.com:5432/almo?sslmode=require
```

Ja ar B variantu pietiek, šo daļu izlaid. Tad datubāze paliek pieejama tikai pašam serverim, un tā ir drošāk.

---

## 2. Almo kods uz servera (B)

Kā `runcloud` lietotājs:

```bash
sudo apt install -y python3-venv git     # vienreiz, kā root
mkdir -p /home/runcloud/apps /home/runcloud/almo-data
cd /home/runcloud/apps
git clone https://github.com/uprankd/UprankdOutreach.git almo
cd almo
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Repozitorijs ir privāts, tāpēc `git clone` paprasīs GitHub lietotāju un **personal access token** (nevis paroli). Vai arī: GitHub repo → **Settings → Deploy keys** → pievieno servera SSH atslēgu (read-only) un klonē ar `git@github.com:uprankd/UprankdOutreach.git`.

Pieslēdz datubāzi:

```bash
echo 'postgresql://almo:NOMAINI-SO-PAROLI@127.0.0.1:5432/almo' > database_url.txt
chmod 600 database_url.txt
```

Ja kādreiz vajag pārnest datus no kāda datora Almo (SQLite), to dara **tajā datorā**:

```bash
.venv/bin/python tools/move_to_postgres.py postgresql://almo:PAROLE@outreach.uprankd.com:5432/almo
```

Tas strādā tikai ar tukšu datubāzi un pieejamu 5432 portu (1. solis, A daļa).

---

## 3. Almo kā pastāvīgs process: Supervisor (B)

RunCloud panelī: **Server → Supervisor → Create Job**.

| Lauks | Vērtība |
| --- | --- |
| Name | `almo` |
| User | `runcloud` |
| Directory | `/home/runcloud/apps/almo` |
| Command | `/home/runcloud/apps/almo/.venv/bin/python app.py` |
| Auto start / Auto restart | ieslēgts |
| Processes | **1** (Almo jādarbojas tieši vienā eksemplārā) |
| Additional config | skat. zemāk |

Additional config:

```
environment=ALMO_SERVER="1",ALMO_NO_BROWSER="1",ALMO_PORT="8765",ALMO_DATA_DIR="/home/runcloud/almo-data"
stopasgroup=true
killasgroup=true
```

Ja RunCloud prasa **Vendor Binary**, izvēlies variantu bez binary vai `none`. Python atrodas pašā Command rindā.

`ALMO_SERVER="1"` nozīmē, ka Almo bez Google pieteikšanās (5. solis) neatvērsies nevienam.

Pārbaude caur SSH (pirms 5. soļa tam jāatbild 403, pēc tam 401):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/api/settings
```

> Ja Supervisor forma Python komandu nepieņem, tas pats strādā ar systemd. Skat. pielikumu A.

---

## 4. Domēns, NGINX un SSL (B)

1. **Web Application → Create Web Application → Custom Web App**, domēns `outreach.uprankd.com`, lietotājs `runcloud`.
2. Web app → **Settings** → Web Application Stack: **Native NGiNX + Custom Config** → **Update Stack**.
3. Web app → **NGiNX Config → Add a New Config** → **Predefined Config → Proxy**. Saturā norādi Almo portu:

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

   Nospied **Run and Debug**, tad **Create Config**.
4. Web app → **SSL/TLS** → Let's Encrypt → ieslēdz **HTTPS redirect**.

---

## 5. Pieteikšanās ar Google (B, obligāti)

Almo ir pieteikšanās lapa kā reports.uprankd.com: **Continue with Google**. Iekšā tiek tikai **@uprankd.com** Google konti. Gmail un citu uzņēmumu konti tiek atraidīti.

Kamēr pieteikšanās nav iestatīta, Almo uz servera **neatveras vispār**. Tas atbild "Sign-in isn't set up", tāpēc nejauši atstāt to vaļā nevar.

### 5.1 Google OAuth klients (vienreiz, ~5 min)

To dara kāds ar uprankd.com Google Workspace admin vai Google Cloud piekļuvi:

1. Atver [console.cloud.google.com](https://console.cloud.google.com/), izveido projektu, piemēram `Uprankd Outreach`.
2. **APIs & Services → OAuth consent screen** (vai **Google Auth Platform → Branding / Audience**):
   - App name: `Uprankd Outreach`
   - User type / Audience: **Internal**. Tad Google pats ielaiž tikai uprankd.com kontus.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Web application**
   - Name: `Almo`
   - Authorized redirect URIs: `https://outreach.uprankd.com/auth/callback`
4. Spied **Create**, tad **Download JSON**.

### 5.2 Uzliec to uz servera

Lejupielādēto failu augšupielādē Almo mapē ar nosaukumu `google_oauth.json` (piem., ar SFTP kā `runcloud` lietotājs):

```bash
cd /home/runcloud/apps/almo
# augšupielādē failu šeit kā google_oauth.json, tad:
chmod 600 google_oauth.json
supervisorctl restart almo        # vai Supervisor → almo → Restart
```

Atver `https://outreach.uprankd.com`. Jāparādās pieteikšanās lapai.

- Fails satur slepenu atslēgu. Tas ir `.gitignore` sarakstā, un to nedrīkst likt GitHub vai sūtīt čatā.
- Sesija ilgst 30 dienas. **Sign out** ir apakšā kreisajā pusē.
- Pieteikšanās strādā tikai caur **HTTPS** (4. solis), jo sesijas sīkdatne ir drošā režīmā.

### 5.3 Ja jāierobežo konkrētiem cilvēkiem (nav obligāti)

Pēc noklusējuma iekšā tiek visi @uprankd.com. Lai ielaistu tikai dažus, Supervisor darba **Additional config** `environment=` rindai pievieno:

```
ALMO_ALLOWED_EMAILS="kristians@uprankd.com,ieva@uprankd.com"
```

Pēc restartēšanas izņemtais cilvēks tiek izlogots uzreiz.

### 5.4 Papildu aizsardzība (nav obligāti)

Ja gribi, lai lapa vispār atveras tikai no biroja, 4. soļa `location /` blokā pievieno:

```nginx
    allow 203.0.113.10;   # birojs
    deny all;
```

> Nelabo `/etc/nginx-rc/conf.d/<app>.conf` un `main.conf` ar roku. RunCloud tos pārraksta. Izmaiņas dari tikai caur **NGiNX Config** paneli.

---

## 6. Ikdienas pārvaldība

### Jaunas versijas uzlikšana

```bash
cd /home/runcloud/apps/almo
git pull
.venv/bin/pip install -r requirements.txt
```

Tad RunCloud panelī **Supervisor → almo → Restart** (vai `supervisorctl restart almo`).

Datubāze tiek atjaunināta automātiski palaišanas brīdī, un dati paliek.

### Restartēt, apturēt

| Darbība | Kā |
| --- | --- |
| Restartēt | Supervisor → almo → Restart |
| Pauzēt sūtīšanu, neapturot lapu | Almo augšā spied **Running** (kļūst **Paused**) |
| Apturēt pavisam | Supervisor → almo → Stop |

### Žurnāli (logs)

- Almo process: Supervisor → almo → **Logs** (vai `supervisorctl tail -f almo`)
- NGINX: Web app → **Logs**
- PostgreSQL: `/var/log/postgresql/`

### Rezerves kopijas (backup)

Cron darbs RunCloud panelī (**Server → Cron Jobs**, lietotājs `root`), katru nakti 03:15:

```
15 3 * * *  sudo -u postgres pg_dump -Fc almo > /var/backups/almo-$(date +\%F).dump && find /var/backups -name 'almo-*.dump' -mtime +14 -delete
```

Atjaunošana (uz tukšu datubāzi):

```bash
sudo -u postgres pg_restore -d almo /var/backups/almo-2026-10-09.dump
```

Ieteicams kopijas reizi nedēļā aizsūtīt arī ārpus servera.

---

## 7. Iestatījumi uz servera

- Almo ar servera pārlūkā atver tieši tāpat kā datorā: **Settings → Email, AI, Sending**.
- **Paroles un API atslēgas.** Uz servera nav Mac Keychain, tāpēc Almo tās glabā datubāzes `settings` tabulā. Tāpēc datubāzei nedrīkst būt publiskas piekļuves (1. solis), un backup faili jāglabā drošā vietā.
- **Viens serveris = viens e-pasts.** B variantā visi, kas atver lapu, sūta no Settings norādītā e-pasta.
- **Datora un servera Almo kopā.** Ja kāds vienlaikus lieto datora Almo ar to pašu datubāzi (A variants), tas ir droši: viena mājaslapa nekad nesaņems e-pastu divreiz. Atbildes Almo lasa tajā pastkastē, no kuras sūtīts.
- **Laiks.** "Sending hours" skatās servera laiku. Iestati Rīgas laiku: `timedatectl set-timezone Europe/Riga`, tad restartē Almo.

---

## 8. Problēmas

| Pazīme | Ko pārbaudīt |
| --- | --- |
| Lapa rāda **502 Bad Gateway** | Almo nedarbojas → Supervisor → almo → Logs; restartē. |
| `Couldn't reach ...` / DB kļūda logā | `systemctl status postgresql`; pareiza parole `database_url.txt`. |
| Settings → Advanced → Database rāda **SQLite** | `database_url.txt` nav lietotnes mapē, vai tajā ir kļūda. |
| Lapa saka "Sign-in isn't set up" | `google_oauth.json` nav Almo mapē vai nav restartēts (5.2). |
| Google rāda `redirect_uri_mismatch` | Google Cloud klientā redirect URI jābūt tieši `https://outreach.uprankd.com/auth/callback`. |
| Pēc Google pieteikšanās atkal atgriež uz login | Lapa atvērta caur `http://`, nevis `https://` (4. solis, HTTPS redirect). |
| Imports beidzas ar kļūdu lieliem failiem | Palielini `client_max_body_size` NGINX konfigurācijā. |
| E-pasti netiek sūtīti | Almo augšā: Paused? Settings → Sending ir **Live**? Overview sarkanie paziņojumi. |
| Pēc `git pull` nekas nemainījās | Aizmirsts restartēt Supervisor darbu. |

---

## Pielikums A: systemd Supervisor vietā

`/etc/systemd/system/almo.service`:

```ini
[Unit]
Description=Almo outreach
After=network.target postgresql.service

[Service]
User=runcloud
WorkingDirectory=/home/runcloud/apps/almo
Environment=ALMO_SERVER=1
Environment=ALMO_NO_BROWSER=1
Environment=ALMO_PORT=8765
Environment=ALMO_DATA_DIR=/home/runcloud/almo-data
ExecStart=/home/runcloud/apps/almo/.venv/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now almo
systemctl restart almo          # pēc atjaunināšanas
journalctl -u almo -f           # žurnāls
```

---

## Ātrā atmiņa

```bash
# atjaunināt
cd /home/runcloud/apps/almo && git pull && .venv/bin/pip install -r requirements.txt && supervisorctl restart almo
# vai Almo dzīvs? (302 = strādā un prasa pieteikšanos)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/
# backup tagad
sudo -u postgres pg_dump -Fc almo > /var/backups/almo-manual.dump
```
