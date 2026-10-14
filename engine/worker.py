"""The automation. One background thread that moves every website along:

  queued -> reading -> ready -> waiting -> replied -> complete
                  `-> not_fit / no_email      `-> followed_up / needs_you / declined
                                   waiting -> (nudge) -> no_reply
                                   waiting -> bounced (or next address)

Everything is stored as it happens, so closing the app loses nothing and a
website is never pitched twice.
"""

import random
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import ai as ai_mod
import bounces
import contacts
import countries
import db
import exporter
import finder
import mail
import settings

STATUS = {
    "in_db": "In database",
    "queued": "Queued",
    "reading": "Checking site",
    "not_fit": "Not a fit",
    "no_email": "No email found",
    "ready": "Ready to send",
    "sending": "Sending",
    "waiting": "Waiting for reply",
    "followed_up": "Followed up",
    "replied": "Reply received",
    "needs_you": "Needs you",
    "complete": "Prices collected",
    "declined": "Declined",
    "own": "Uprankd website",
    "no_reply": "No reply",
    "bounced": "Bounced",
    "error": "Error",
}
CONTACTED = ("waiting", "followed_up", "replied", "needs_you", "complete", "declined",
             "no_reply", "bounced")

NUDGE = {
    "en": "Hi again,\n\nJust following up on my message below - could you share your "
          "conditions for publishing a sponsored article on {domain}?\n\nThank you!",
}


class Worker:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="read")
        self.reading = set()
        self.lock = threading.Lock()
        self.next_send_at = {}        # mailbox id -> earliest next send
        self.last_sent = {}           # mailbox id -> when it last sent
        self.last_inbox = {}          # mailbox id -> last inbox check
        self.box_errors = {}          # mailbox id -> {"send": .., "inbox": ..}
        self._smtp = {}
        self.inbox_error = ""
        self.send_error = ""
        self.ai_error = ""
        self.last_inbox_ok = 0
        self.dirty = True
        self.last_export = 0
        self.wake = threading.Event()
        self.thread = None

    # ------------------------------------------------------------------ #
    def start(self):
        with db.tx() as conn:
            # Only rows stuck for 10+ minutes: with a shared database another
            # computer may be in the middle of them right now.
            stale = time.time() - 600
            conn.execute("UPDATE sites SET status='queued' WHERE status='reading' AND updated_at<?", (stale,))
            conn.execute("UPDATE sites SET status='ready' WHERE status='sending' AND updated_at<?", (stale,))
            conn.execute("UPDATE sites SET lookup=1 WHERE lookup=2 AND updated_at<?", (stale,))
        self.last_unstick = time.time()
        self.thread = threading.Thread(target=self._loop, name="almo-worker", daemon=True)
        self.thread.start()

    def poke(self):
        self.wake.set()

    def check_inbox_now(self):
        self.last_inbox = {}
        self.poke()

    def reset_connections(self):
        for s in list(self._smtp.values()):
            s.close()
        self._smtp = {}
        self.box_errors = {}
        self.poke()

    def _loop(self):
        while True:
            try:
                self._tick()
            except Exception:
                traceback.print_exc()
            self.wake.wait(2)
            self.wake.clear()

    def _unstick(self):
        """A check or send that hasn't finished in 10 minutes (lost connection,
        a computer that went to sleep mid-way) goes back in line - without
        waiting for a restart. Sites this process is still working on are left alone."""
        if time.time() - getattr(self, "last_unstick", 0) < 120:
            return
        self.last_unstick = time.time()
        stale = time.time() - 600
        with self.lock:
            busy = set(self.reading)
        for row in db.query("SELECT id, status, lookup FROM sites WHERE updated_at<? AND "
                            "(status IN ('reading','sending') OR lookup=2)", (stale,)):
            if row["id"] in busy:
                continue
            if row["status"] == "reading" and db.claim(row["id"], "reading", "queued"):
                db.log("warn", "Site check took too long - trying again", row["id"])
            elif row["status"] == "sending":
                db.claim(row["id"], "sending", "ready")
            if row["lookup"] == 2:
                with db.tx() as conn:
                    conn.execute("UPDATE sites SET lookup=1 WHERE id=? AND lookup=2", (row["id"],))
            self.dirty = True

    def _tick(self):
        self._unstick()
        cfg = settings.load()
        if cfg.get("running", True):
            self._stage_read(cfg)
            self._stage_lookup(cfg)
            if cfg["send_mode"] != "off":
                boxes = self.boxes()
                if boxes:
                    self._stage_inbox(cfg, boxes)
                    self._stage_send(cfg, boxes)
            self._stage_timeouts(cfg)
        self._stage_export(cfg)

    def _ai(self, cfg):
        try:
            return ai_mod.make(cfg)
        except Exception as exc:
            self.ai_error = str(exc)
            return None

    # ------------------------------------------------------------------ #
    # 1. Read each website: is it a fit, what language, which address
    # ------------------------------------------------------------------ #
    def _stage_read(self, cfg):
        with self.lock:
            free = 4 - len(self.reading)
        if free <= 0:
            return
        now = time.time()
        rows = db.sites("status='queued' AND next_try_at<=?", (now,), "id ASC", free)
        for site in rows:
            with self.lock:
                if site["id"] in self.reading:
                    continue
                self.reading.add(site["id"])
            if not db.claim(site["id"], "queued", "reading"):
                with self.lock:
                    self.reading.discard(site["id"])
                continue
            self.pool.submit(self._read_one, site["id"], cfg)

    # ------------------------------------------------------------------ #
    # Link builders: find the website's own contact
    # ------------------------------------------------------------------ #
    def _is_link_builder(self, site):
        row = db.one("SELECT COUNT(*) AS n FROM sites WHERE email=?", (site["email"],))
        return contacts.is_link_builder(site["domain"], site["email"], row["n"] if row else 0)

    def _direct_contact(self, site):
        """Addresses on the site's own domain, best first ([] when none)."""
        info = finder.read_site(site["domain"])
        own = [e for e in info["emails"] if contacts.own_address(site["domain"], e)]
        return own, info

    def _stage_lookup(self, cfg):
        with self.lock:
            free = 4 - len(self.reading)
        if free <= 0:
            return
        for site in db.sites("lookup=1", (), "id ASC", free):
            with db.tx() as conn:
                if conn.execute("UPDATE sites SET lookup=2 WHERE id=? AND lookup=1",
                                (site["id"],)).rowcount != 1:
                    continue        # another computer took it
            with self.lock:
                self.reading.add(site["id"])
            self.pool.submit(self._lookup_one, site["id"])

    def _lookup_one(self, site_id):
        try:
            site = db.get_site(site_id)
            direct, info = self._direct_contact(site)
            emails = site.get("emails") or ([site["email"]] if site["email"] else [])
            if direct:
                emails = list(dict.fromkeys(direct + emails))
                if site.get("sent_at") and site["email"]:
                    # Already writing to the old address - don't switch mid-conversation.
                    db.update_site(site_id, emails=emails, lookup=0,
                                   note="Own address found: %s (not used - a conversation is open)" % direct[0])
                else:
                    old = site["email"]
                    db.update_site(site_id, email=direct[0], emails=emails, lookup=0,
                                   note=("Own address found - %s kept as a backup" % old) if old else "")
                db.log("find", "Found the site's own address %s" % direct[0], site_id)
            else:
                db.update_site(site_id, lookup=0, note="No own address on the website" +
                               ("" if info["ok"] else " (the site didn't load)"))
                db.log("warn", "No own address found on the website", site_id)
        except Exception as exc:
            traceback.print_exc()
            db.update_site(site_id, lookup=0, note="Couldn't check the site: %s" % str(exc)[:120])
        finally:
            with self.lock:
                self.reading.discard(site_id)
            self.dirty = True

    def _read_one(self, site_id, cfg):
        try:
            site = db.get_site(site_id)
            if site.get("email"):
                # Already in the database with a contact - no need to re-check
                # the site. Only when that contact is a link builder's address
                # does Almo first look for the site's own one.
                email, note = site["email"], "Email from the database"
                emails = site.get("emails") or [email]
                if email not in emails:
                    emails = [email] + emails
                if cfg.get("find_direct", True) and self._is_link_builder(site):
                    direct, _info = self._direct_contact(site)
                    if direct:
                        emails = list(dict.fromkeys(direct + emails))
                        db.log("find", "Found the site's own address %s instead of %s" % (direct[0], email), site_id)
                        email, note = direct[0], "Own address found - %s kept as a backup" % site["email"]
                    else:
                        note = "Only a link builder's address is known"
                db.update_site(site_id, status="ready", email=email, emails=emails,
                               tried=list(dict.fromkeys((site.get("tried") or []) + [email])),
                               language=site.get("language") or countries.language_for(site["domain"]),
                               note=note)
                db.log("find", "Using %s" % email, site_id)
                return
            info = finder.read_site(site["domain"])
            fields = {"language": info["language"], "emails": info["emails"]}
            client = self._ai(cfg) if cfg.get("check_sites") else None
            if client and info["ok"] and info["text"]:
                try:
                    v = client.check_site(site["domain"], info["title"], info["text"])
                    fields["fit"] = v.get("verdict", "maybe")
                    fields["fit_reason"] = v.get("reason", "")
                    self.ai_error = ""
                except ai_mod.AIError as exc:
                    self.ai_error = str(exc)
                    fields["fit"] = "maybe"
                    fields["fit_reason"] = "Not checked: %s" % exc
            elif not info["ok"]:
                fields["fit_reason"] = "Website didn't load"

            if fields.get("fit") == "no":
                fields["status"] = "not_fit"
                db.update_site(site_id, **fields)
                db.log("skip", "Not a fit: %s" % fields.get("fit_reason", ""), site_id)
                return
            if not info["emails"]:
                attempts = site["attempts"] + 1
                if not info["ok"] and attempts < 3:
                    fields.update(status="queued", attempts=attempts,
                                  next_try_at=time.time() + 1800 * attempts,
                                  note="Website didn't load (try %d of 3)" % attempts)
                    db.update_site(site_id, **fields)
                    return
                fields["status"] = "no_email"
                fields["note"] = "Website didn't load" if not info["ok"] else \
                    "No contact address on the site"
                db.update_site(site_id, **fields)
                db.log("warn", fields["note"], site_id)
                return
            fields.update(status="ready", email=info["emails"][0], tried=[info["emails"][0]],
                          note="")
            db.update_site(site_id, **fields)
            db.log("find", "Found %s" % info["emails"][0], site_id)
        except Exception as exc:
            traceback.print_exc()
            db.update_site(site_id, status="error", note=str(exc)[:200])
        finally:
            with self.lock:
                self.reading.discard(site_id)
            self.dirty = True
            self.poke()

    # ------------------------------------------------------------------ #
    # 2. Send: pitches, nudges - paced, capped, inside working hours
    # ------------------------------------------------------------------ #
    # Every mailbox with a password can read replies and continue its own
    # conversations; only active ones take new pitches. Pitches rotate so each
    # mailbox sends about the same number a day, each within its own limit.
    def boxes(self):
        return [b for b in settings.mailboxes() if settings.box_ready(b)]

    def _box_for_site(self, site, boxes):
        """The mailbox that wrote to this site - replies stay in one thread."""
        for b in boxes:
            if b["id"] == site.get("mailbox_id"):
                return b
        active = [b for b in boxes if b["active"]]
        return active[0] if active else None

    def _err(self, box, kind, text):
        if box:
            self.box_errors.setdefault(box["id"], {})[kind] = text
        if kind == "send":
            self.send_error = text
        else:
            self.inbox_error = text

    def sent_today(self, address=None):
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        if address:
            row = db.one("SELECT COUNT(*) AS n FROM messages WHERE direction='out' AND ts>=? "
                         "AND lower(from_addr)=?", (start, address.lower()))
        else:
            row = db.one("SELECT COUNT(*) AS n FROM messages WHERE direction='out' AND ts>=?",
                         (start,))
        return row["n"] if row else 0

    def _in_hours(self, cfg):
        if cfg["send_mode"] == "test":
            return True
        hour = datetime.now().hour
        return int(cfg["work_start"]) <= hour < int(cfg["work_end"])

    def _box_free(self, box):
        return time.time() >= self.next_send_at.get(box["id"], 0) and \
            self.sent_today(box["email"]) < int(box.get("daily_limit") or 0)

    def can_send_now(self, cfg, boxes=None):
        boxes = self.boxes() if boxes is None else boxes
        active = [b for b in boxes if b["active"]]
        if not active:
            return False, "no active mailbox"
        if all(self.sent_today(b["email"]) >= int(b.get("daily_limit") or 0) for b in active):
            return False, "daily limit reached"
        if not self._in_hours(cfg):
            return False, "outside working hours"
        if not any(self._box_free(b) for b in active):
            return False, "pacing"
        return True, ""

    def _schedule_next(self, cfg, box):
        if cfg["send_mode"] == "test":
            gap = random.randint(5, 12)
        else:
            gap = random.randint(int(cfg["gap_min"]), max(int(cfg["gap_min"]), int(cfg["gap_max"])))
        self.next_send_at[box["id"]] = time.time() + gap
        self.last_sent[box["id"]] = time.time()
        # And a pause before Almo sends anything else, from any mailbox, so
        # several mailboxes never fire at the same moment.
        if cfg["send_mode"] != "test":
            lo = int(cfg.get("global_gap_min") or 0)
            self.global_next = time.time() + random.randint(lo, max(lo, int(cfg.get("global_gap_max") or 0)))

    def _stage_send(self, cfg, boxes):
        if not self._in_hours(cfg):
            return
        if time.time() < getattr(self, "global_next", 0):
            return
        free = [b for b in boxes if self._box_free(b)]
        if not free:
            return
        free_ids = {b["id"] for b in free}
        # Reminders first - they finish conversations that are already open,
        # always from the mailbox that started them.
        for site in self._due_nudges(cfg):
            box = self._box_for_site(site, boxes)
            if box and box["id"] in free_ids:
                self._send_nudge(settings.box_cfg(cfg, box), site)
                self._schedule_next(cfg, box)
                return
        active = [b for b in free if b["active"]]
        if not active:
            return
        rows = db.sites("status='ready'", (), "id ASC", 1)
        if rows:
            box = min(active, key=lambda b: (self.sent_today(b["email"]),
                                             self.last_sent.get(b["id"], 0), b["id"]))
            self._send_pitch(settings.box_cfg(cfg, box), rows[0])
            self._schedule_next(cfg, box)

    def _sender(self, cfg):
        key = cfg.get("mailbox_id") or cfg["email"]
        s = self._smtp.get(key)
        if s is None or s.cfg.get("email") != cfg["email"] or \
                s.cfg.get("email_password") != cfg["email_password"] or \
                s.cfg.get("smtp_host") != cfg["smtp_host"]:
            if s:
                s.close()
            s = mail.Sender(cfg)
            self._smtp[key] = s
        s.cfg = cfg
        return s

    def _deliver(self, cfg, site, subject, body, kind, reply_to=None):
        """Send one message for a site as cfg's mailbox and store it."""
        box = {"id": cfg.get("mailbox_id")} if cfg.get("mailbox_id") else None
        test = cfg["send_mode"] == "test"
        to_addr = cfg["email"] if test else site["email"]
        shown_subject = ("[TEST → %s] " % site["domain"] + subject) if test and \
            not subject.startswith("[TEST") else subject
        in_reply_to, refs, quote = "", "", None
        if reply_to:
            in_reply_to = reply_to.get("message_id", "")
            refs = " ".join(m["message_id"] for m in db.thread(site["id"]) if m["message_id"]
                            and m["message_id"] != in_reply_to)
            quote = (reply_to.get("from_addr") or "", datetime.fromtimestamp(
                reply_to["ts"]).strftime("%a, %d %b %Y %H:%M"), reply_to.get("body", ""))
        msg = mail.build_message(cfg, to_addr, shown_subject, body, in_reply_to, refs,
                                 quote=quote)
        try:
            self._sender(cfg).send(msg)
        except mail.MailError as exc:
            self._err(box, "send", "%s: %s" % (cfg["email"], exc))
            db.log("error", "Couldn't send from %s: %s" % (cfg["email"], exc), site["id"])
            if "refused" in str(exc):
                return self._bounce(site, "address refused", [])
            return False
        self._err(box, "send", "")
        db.add_message(site["id"], "out", kind, cfg["email"], to_addr, shown_subject, body,
                       msg["Message-ID"], test)
        return True

    def compose_pitch(self, cfg, site, pitch=None):
        if pitch is None and site.get("pitch_id"):
            pitch = db.one("SELECT * FROM pitches WHERE id=?", (site["pitch_id"],))
        if pitch is None:
            camp = db.one("SELECT id FROM campaigns WHERE id=?", (site.get("campaign_id"),)) or \
                db.one("SELECT id FROM campaigns ORDER BY id LIMIT 1")
            pitch = db.pick_pitch(camp["id"])
        subject, body = pitch["subject"], pitch["body"]
        lang = (site.get("language") or "").lower()
        if cfg.get("translate") and lang and lang != "en":
            client = self._ai(cfg)
            if client:
                try:
                    t = client.translate(subject, body, lang)
                    subject, body = t["subject"], t["body"]
                except ai_mod.AIError as exc:
                    self.ai_error = str(exc)
        fill = lambda s: s.replace("{domain}", site["domain"]).replace("{website}", site["domain"])
        return fill(subject), fill(body)

    def _send_pitch(self, cfg, site):
        # Claim it first, so two computers on one shared database can never
        # both send the pitch.
        if not db.claim_pitch(site["id"], cfg.get("mailbox_id")):
            return
        pitch = None
        if site.get("pitch_id"):
            pitch = db.one("SELECT * FROM pitches WHERE id=?", (site["pitch_id"],))
        pitch = pitch or db.pick_pitch(site["campaign_id"]) or \
            db.pick_pitch(db.one("SELECT id FROM campaigns ORDER BY id LIMIT 1")["id"])
        subject, body = self.compose_pitch(cfg, site, pitch)
        if not self._deliver(cfg, site, subject, body, "pitch"):
            db.claim(site["id"], "sending", "ready")   # a bounce may have moved it on already
            return
        now = time.time()
        db.update_site(site["id"], status="waiting", subject=subject, sent_at=now,
                       last_out_at=now, note="", pitch_id=pitch["id"])
        db.log("send", "Pitch %s sent to %s from %s%s" % (
            pitch["label"], site["email"], cfg["email"],
            " (test: to you)" if cfg["send_mode"] == "test" else ""), site["id"])
        self.dirty = True

    def _due_nudges(self, cfg):
        days = int(cfg["nudge_days"])
        if days <= 0:
            return []
        limit = time.time() - days * 86400
        return db.sites("status IN ('waiting','followed_up') AND last_out_at<? AND nudges<?",
                        (limit, int(cfg["max_nudges"])), "last_out_at ASC", 20)

    def _send_nudge(self, cfg, site):
        body = NUDGE["en"]
        lang = site.get("language") or "en"
        if cfg.get("translate") and lang != "en":
            client = self._ai(cfg)
            if client:
                try:
                    body = client.translate("", body, lang)["body"]
                except ai_mod.AIError:
                    pass
        body = body.replace("{domain}", site["domain"])
        last_out = [m for m in db.thread(site["id"]) if m["direction"] == "out"]
        ref = last_out[-1] if last_out else None
        subject = "Re: " + (site["subject"] or "")
        if ref:
            ref = dict(ref)
            ref["from_addr"] = cfg["email"]
        if not db.claim_nudge(site["id"], site["nudges"]):
            return
        if not self._deliver(cfg, site, subject, body, "nudge", ref):
            db.claim_nudge(site["id"], site["nudges"] + 1, -1)
            return
        db.update_site(site["id"], last_out_at=time.time())
        db.log("send", "Reminder sent", site["id"])
        self.dirty = True

    def _stage_timeouts(self, cfg):
        days = max(int(cfg["nudge_days"]), 1)
        limit = time.time() - days * 86400
        rows = db.sites("status IN ('waiting','followed_up') AND last_out_at<? AND nudges>=?",
                        (limit, int(cfg["max_nudges"])))
        for site in rows:
            db.update_site(site["id"], status="no_reply")
            db.log("warn", "No reply after %d reminder(s)" % site["nudges"], site["id"])
            self.dirty = True

    # ------------------------------------------------------------------ #
    # 3. Inbox: replies, bounces, out-of-office
    # ------------------------------------------------------------------ #
    def _stage_inbox(self, cfg, boxes):
        every = max(int(cfg["inbox_every_min"]), 1) * 60
        if cfg["send_mode"] == "test":
            every = 60
        own = {b["email"].lower() for b in boxes}
        for box in boxes:
            if time.time() - self.last_inbox.get(box["id"], 0) < every:
                continue
            self.last_inbox[box["id"]] = time.time()
            if not db.one("SELECT 1 AS x FROM messages WHERE direction='out' AND lower(from_addr)=? "
                          "LIMIT 1", (box["email"].lower(),)):
                continue
            bcfg = settings.box_cfg(cfg, box)
            try:
                with mail.Inbox(bcfg) as inbox:
                    known = lambda mid: db.was_seen(mid) or \
                        db.site_for_message_ids([mid]) is not None
                    messages, skipped = inbox.new_messages(45, known, self._wanted(bcfg, own))
                self._err(box, "inbox", "")
                self.last_inbox_ok = time.time()
            except mail.MailError as exc:
                self._err(box, "inbox", "%s: %s" % (box["email"], exc))
                continue
            except Exception as exc:
                self._err(box, "inbox", "%s: reading mail: %s" % (box["email"], str(exc)[:160]))
                continue
            for mid in skipped:
                db.mark_seen(mid)
            for m in messages:
                if not db.mark_seen(m["message_id"]):
                    continue          # another computer already handled it
                try:
                    self._handle_incoming(bcfg, m, own)
                except Exception:
                    traceback.print_exc()

    def _wanted(self, cfg, own_set=None):
        """Decide from headers alone whether a message could be ours to read."""
        own = own_set or {cfg["email"].lower()}
        test = cfg["send_mode"] == "test"
        contacted = None

        def wanted(h):
            nonlocal contacted
            if db.site_for_message_ids(h["ids"]):
                return True
            sender = h["from_addr"]
            if bounces._SYSTEM_SENDER.search(h["from"]) or \
                    bounces._FAILURE_SUBJECT.search(h["subject"] or ""):
                return True
            if sender in own and not test:
                return False
            if contacted is None:
                contacted = set()
                for r in db.query("SELECT domain, email FROM sites WHERE sent_at IS NOT NULL"):
                    contacted.add(r["domain"])
                    if r["email"]:
                        contacted.add(r["email"])
            if sender in contacted:
                return True
            dom = sender.split("@")[-1]
            parts = dom.split(".")
            return any(".".join(parts[i:]) in contacted for i in range(len(parts) - 1))
        return wanted

    def _match_site(self, cfg, m, own_set=None):
        own = m["from_addr"] in (own_set or {cfg["email"].lower()})
        sid = db.site_for_message_ids([m["in_reply_to"]] + m["references"])
        if sid:
            return db.get_site(sid)
        if own:
            return None
        rows = db.sites("email=? AND sent_at IS NOT NULL", (m["from_addr"],), limit=1)
        if rows:
            return rows[0]
        domain = m["from_addr"].split("@")[-1]
        for row in db.sites("sent_at IS NOT NULL AND (domain=? OR ?=('www.'||domain))",
                            (domain, domain), limit=1):
            return row
        # A colleague at the site's own domain, e.g. sales@ answering info@
        parts = domain.split(".")
        for i in range(1, len(parts) - 1):
            parent = ".".join(parts[i:])
            rows = db.sites("domain=? AND sent_at IS NOT NULL", (parent,), limit=1)
            if rows:
                return rows[0]
        return None

    def _handle_incoming(self, cfg, m, own_set=None):
        own_set = own_set or {cfg["email"].lower()}
        result = bounces.analyse(m, own_addresses=sorted(own_set))
        if result:
            targets = []
            for addr in result["addresses"]:
                targets += db.sites("email=? AND sent_at IS NOT NULL", (addr,), limit=1)
            if not targets:
                sid = db.site_for_message_ids([m["in_reply_to"]] + m["references"])
                if sid:
                    targets = [db.get_site(sid)]
            if not targets and result["kind"] == "bounce":
                for to in m.get("original_to") or []:
                    sid = None
                    for row in db.sites("email=? AND sent_at IS NOT NULL",
                                        (to.strip().lower(),), limit=1):
                        targets.append(row)
            if not targets and cfg["send_mode"] == "test":
                # Test mail goes to you, so a bounce can't happen - nothing to do.
                return
            for site in targets:
                db.add_message(site["id"], "in", "bounce", m["from_addr"], cfg["email"],
                               m["subject"], m["body"][:4000], m["message_id"], ts=m["ts"])
                self._bounce(site, result["reason"], result.get("others") or [])
            return

        site = self._match_site(cfg, m, own_set)
        if not site or not site.get("sent_at"):
            return
        if m["from_addr"] in own_set and cfg["send_mode"] != "test":
            return
        db.add_message(site["id"], "in", "reply", m["from_addr"], m["to"], m["subject"],
                       m["body"], m["message_id"], ts=m["ts"])
        headers = m["headers"]
        if bounces._is_auto_reply(m, headers) and len(m["body"]) < 1500:
            db.log("info", "Automatic reply (out of office) - still waiting", site["id"])
            return
        db.update_site(site["id"], status="replied", replied_at=time.time())
        db.log("reply", "Reply from %s" % m["from_addr"], site["id"])
        self.dirty = True
        self.process_reply(cfg, site["id"], m)

    def _bounce(self, site, reason, others):
        site = db.get_site(site["id"])
        tried = list(site.get("tried") or [])
        candidates = [e for e in (site.get("emails") or []) + list(others)
                      if e and e not in tried and finder.useful(e)]
        if candidates:
            nxt = candidates[0]
            db.update_site(site["id"], status="ready", email=nxt, tried=tried + [nxt],
                           note="%s bounced (%s) - trying %s" % (site["email"], reason, nxt))
            db.log("warn", "%s bounced (%s) - will try %s" % (site["email"], reason, nxt), site["id"])
        else:
            db.update_site(site["id"], status="bounced", note="%s: %s" % (site["email"], reason))
            db.log("error", "Bounced: %s" % reason, site["id"])
        self.dirty = True
        return False

    # ------------------------------------------------------------------ #
    # 4. Understand a reply and answer it
    # ------------------------------------------------------------------ #
    def process_reply(self, cfg, site_id, last_msg=None):
        client = self._ai(cfg)
        if not client:
            db.update_site(site_id, status="needs_you",
                           note="Reply received - add an AI key in Settings to read replies automatically")
            return
        site = db.get_site(site_id)
        messages = db.thread(site_id)
        text = ai_mod.format_thread(messages)
        try:
            terms = client.extract(text)
            self.ai_error = ""
        except ai_mod.AIError as exc:
            self.ai_error = str(exc)
            db.update_site(site_id, status="needs_you", note="Couldn't read the reply: %s" % exc)
            return
        update = {}
        for field in ai_mod.FIELDS + ("requirements",):
            new = (terms.get(field) or "").strip()
            if field == "requirements" and new.lower() == "none":
                new = ""
            if new and not ai_mod.is_unknown(new):
                update[field] = new
            elif not site.get(field):
                update[field] = "Unknown" if field != "requirements" else ""
        if terms.get("language"):
            update["language"] = terms["language"][:5].lower()
        db.update_site(site_id, **update)
        site = db.get_site(site_id)
        self.dirty = True

        if str(terms.get("declined", "")).lower() == "yes":
            db.update_site(site_id, status="declined", note="They don't publish sponsored content")
            db.log("info", "Declined", site_id)
            return
        missing = ai_mod.missing_fields(site)
        if not missing:
            db.update_site(site_id, status="complete", note="", draft="")
            db.log("done", "Prices collected: %s EUR" % site.get("price"), site_id)
            return
        if str(terms.get("answer_elsewhere", "")).lower() == "yes":
            db.update_site(site_id, status="needs_you",
                           note="They sent a price list or link - open the email and fill in the prices")
            return
        box = self._box_for_site(site, self.boxes())
        sender_name = (box or {}).get("sender_name") or cfg.get("sender_name")
        try:
            draft = client.followup(text, missing, sender_name,
                                    terms.get("language") or site.get("language") or "en")
        except ai_mod.AIError as exc:
            db.update_site(site_id, status="needs_you", note="Couldn't write the follow-up: %s" % exc)
            return
        if cfg.get("auto_followup") and site["followups"] < 2 and cfg["send_mode"] != "off":
            if self.send_followup(cfg, site_id, draft):
                return
        db.update_site(site_id, status="needs_you", draft=draft,
                       note="Missing: %s - follow-up ready to send" % ", ".join(
                           m.replace("_", " ") for m in missing))

    def send_followup(self, cfg, site_id, body):
        site = db.get_site(site_id)
        box = self._box_for_site(site, self.boxes())
        if not box:
            self.send_error = "No mailbox to send from - add one in Settings"
            return False
        cfg = settings.box_cfg(cfg, box)
        incoming = [m for m in db.thread(site_id) if m["direction"] == "in" and m["kind"] == "reply"]
        ref = incoming[-1] if incoming else None
        subject = (ref["subject"] if ref else site["subject"]) or site["subject"]
        if not subject.lower().startswith(("re:", "aw:", "sv:", "atb:")):
            subject = "Re: " + subject
        if self._deliver(cfg, site, subject, body, "followup", ref):
            db.update_site(site_id, status="followed_up", followups=site["followups"] + 1,
                           last_out_at=time.time(), draft="", note="Asked for the missing details")
            db.log("send", "Follow-up sent asking for missing details", site_id)
            self.dirty = True
            return True
        return False

    # ------------------------------------------------------------------ #
    def _stage_export(self, cfg):
        path = cfg.get("results_path")
        if not path or not self.dirty or time.time() - self.last_export < 20:
            return
        self.last_export = time.time()
        try:
            exporter.write(path)
            self.dirty = False
        except Exception as exc:
            print("export failed:", exc)

    def status(self, cfg):
        boxes = self.boxes()
        ok, why = self.can_send_now(cfg, boxes) if cfg["send_mode"] != "off" else (False, "")
        active = [b for b in boxes if b["active"]]
        waits = [max(0, int(self.next_send_at.get(b["id"], 0) - time.time())) for b in active]
        per_box = []
        for b in settings.mailboxes(with_secrets=False):
            errs = self.box_errors.get(b["id"], {})
            per_box.append({"id": b["id"], "email": b["email"], "sent_today": self.sent_today(b["email"]),
                            "limit": b["daily_limit"], "active": b["active"],
                            "send_error": errs.get("send", ""), "inbox_error": errs.get("inbox", "")})
        send_errors = [p["send_error"] for p in per_box if p["send_error"]]
        inbox_errors = [p["inbox_error"] for p in per_box if p["inbox_error"]]
        return {
            "send_error": send_errors[0] if send_errors else "",
            "inbox_error": inbox_errors[0] if inbox_errors else "",
            "ai_error": self.ai_error,
            "last_inbox_ok": self.last_inbox_ok,
            "sent_today": self.sent_today(),
            "daily_limit": sum(int(b["daily_limit"] or 0) for b in active),
            "next_send_in": min(waits) if waits else 0,
            "send_wait": why,
            "reading": len(self.reading),
            "mailboxes": per_box,
        }
