"""Sending (SMTP) and reading (IMAP) with an app password.

Gmail and Fastmail both work the same way here, so there is no Google Cloud
project, credentials.json or browser sign-in any more. Reading never marks
anything as read: messages are fetched with BODY.PEEK and remembered by
Message-ID in the local database.
"""

import base64
import email
import email.utils
import html
import imaplib
import os
import re
import smtplib
import ssl
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import EmailMessage

from mailtext import best_text


class MailError(Exception):
    pass


def _ctx():
    return ssl.create_default_context()


def _friendly(exc, what):
    text = str(exc)
    low = text.lower()
    if "authenticationfailed" in low or "535" in low or "invalid credentials" in low \
            or "username and password not accepted" in low or "authentication failed" in low:
        return ("%s login failed. Use an app password (not your normal password) - "
                "see the link next to the field." % what)
    if "getaddrinfo" in low or "name or service" in low or "nodename" in low:
        return "Couldn't find the %s server - check the internet connection" % what
    if "timed out" in low:
        return "The %s server didn't answer in time" % what
    return "%s: %s" % (what, text[:160])


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
LOGO_CID = "uprankd-logo"
LOGO_PNG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "web", "email-logo.png")


def _embed_logo(cfg):
    """SVG logos are blank in Gmail and Outlook, so an .svg logo (the default
    https://uprankd.com/logo.svg) is sent as the bundled PNG inside the email."""
    logo = (cfg.get("logo_url") or "").strip()
    return bool(logo) and logo.lower().split("?")[0].endswith(".svg") and os.path.isfile(LOGO_PNG)


def logo_data_uri():
    with open(LOGO_PNG, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def signature_html(cfg, logo_src=None):
    """A plain, compact signature: logo, name, title · company, website · address.
    Tables and inline styles only, so Gmail and Outlook show it the same."""
    name = html.escape(cfg.get("sender_name") or "")
    role = " · ".join(html.escape(x) for x in (cfg.get("sender_title"), cfg.get("company")) if x)
    logo = cfg.get("logo_url") or ""
    if _embed_logo(cfg):
        src = logo_src or ("cid:" + LOGO_CID)
        img = ('<img src="%s" width="112" height="19" alt="Uprankd" style="display:block;border:0;'
               'width:112px;height:19px;">' % html.escape(src, quote=True))
    else:
        img = ('<img src="%s" height="28" alt="" style="display:block;border:0;height:28px;">'
               % html.escape(logo, quote=True)) if logo else ""
    rows = []
    if img:
        rows.append('<tr><td style="padding:0 0 12px;">%s</td></tr>' % img)
    if name:
        rows.append('<tr><td style="font-size:14px;font-weight:bold;color:#0b0f3a;'
                    'padding:0 0 2px;">%s</td></tr>' % name)
    if role:
        rows.append('<tr><td style="font-size:13px;color:#555b6e;padding:0 0 10px;">%s</td></tr>' % role)
    rows.append('<tr><td style="font-size:12px;color:#7a8091;border-top:1px solid #e3e5eb;padding:10px 0 0;">'
                '<a href="https://uprankd.com" style="color:#008dc6;text-decoration:none;">uprankd.com</a>'
                ' &nbsp;·&nbsp; Br&#299;v&#299;bas iela 40-20B, R&#299;ga, LV-1050</td></tr>')
    return ('<table cellpadding="0" cellspacing="0" border="0" style="font-family:Arial,Helvetica,'
            'sans-serif;border-collapse:collapse;">%s</table>' % "".join(rows))


def signature_text(cfg):
    lines = [x for x in (cfg.get("sender_name"), cfg.get("sender_title"),
                         cfg.get("company")) if x]
    return "\n".join(lines + ["uprankd.com · Brīvības iela 40-20B, Rīga, LV-1050"])


def build_message(cfg, to_addr, subject, body, in_reply_to="", references="",
                  with_signature=True, quote=None, logo_src=None):
    """A proper multipart email: plain text + HTML, Date, Message-ID."""
    msg = EmailMessage()
    sender = cfg["email"]
    domain = sender.split("@")[-1] if "@" in sender else "almo.local"
    msg["From"] = email.utils.formataddr((cfg.get("sender_name") or "", sender))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=domain)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip()
    text = body.strip()
    html_body = "<p>%s</p>" % html.escape(text).replace("\n", "<br>")
    if with_signature:
        text += "\n\n" + signature_text(cfg)
        html_body += "<br>" + signature_html(cfg, logo_src)
    if quote:
        q_from, q_date, q_body = quote
        text += "\n\nOn %s, %s wrote:\n%s" % (q_date, q_from, "\n".join(
            "> " + line for line in (q_body or "").splitlines()))
        html_body += ('<br><div>On %s, %s wrote:</div><blockquote style="margin:0 0 0 .8ex;'
                      'border-left:1px solid #ccc;padding-left:1ex">%s</blockquote>' % (
                          html.escape(q_date), html.escape(q_from),
                          html.escape(q_body or "").replace("\n", "<br>")))
    msg.set_content(text)
    msg.add_alternative(
        '<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#333333;">'
        '%s</body></html>' % html_body, subtype="html")
    if with_signature and not logo_src and _embed_logo(cfg):
        with open(LOGO_PNG, "rb") as f:
            msg.get_body(("html",)).add_related(f.read(), "image", "png", cid="<%s>" % LOGO_CID,
                                                 disposition="inline", filename="uprankd.png")
    return msg


class Sender:
    """One SMTP connection, reconnected on demand."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.smtp = None

    def _connect(self):
        host, port = self.cfg["smtp_host"], int(self.cfg.get("smtp_port") or 465)
        try:
            if port == 587:
                smtp = smtplib.SMTP(host, port, timeout=30)
                smtp.starttls(context=_ctx())
            else:
                smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=_ctx())
            smtp.login(self.cfg["email"], self.cfg["email_password"])
        except Exception as exc:
            raise MailError(_friendly(exc, "Sending")) from exc
        self.smtp = smtp

    def send(self, msg):
        for attempt in (1, 2):
            if self.smtp is None:
                self._connect()
            try:
                self.smtp.send_message(msg)
                return
            except smtplib.SMTPRecipientsRefused as exc:
                raise MailError("The address was refused by the mail server") from exc
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPSenderRefused,
                    ConnectionError, OSError) as exc:
                self.close()
                if attempt == 2:
                    raise MailError(_friendly(exc, "Sending")) from exc
                time.sleep(3)

    def close(self):
        if self.smtp is not None:
            try:
                self.smtp.quit()
            except Exception:
                pass
        self.smtp = None


def test_send(cfg):
    s = Sender(cfg)
    s._connect()
    s.close()


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def _dh(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def _parse(raw):
    msg = email.message_from_bytes(raw)
    plain, htmlpart, report, notice = "", "", "", ""
    original_to = []
    attachments = []
    for part in msg.walk():
        ctype = part.get_content_type()
        disp = (part.get("Content-Disposition") or "").lower()
        if ctype == "message/delivery-status":
            payload = part.get_payload()
            if isinstance(payload, list):
                report += "\n\n".join(p.as_string() for p in payload)
            else:
                report += str(payload)
            continue
        if ctype in ("message/rfc822", "text/rfc822-headers"):
            try:
                inner = part.get_payload(0) if part.is_multipart() else None
                if inner is not None:
                    original_to += [inner.get("To", "")]
                else:
                    original_to += re.findall(r"^To:\s*(.+)$", str(part.get_payload()), re.M)
            except Exception:
                pass
            continue
        if part.is_multipart():
            continue
        if "attachment" in disp:
            attachments.append(_dh(part.get_filename() or ""))
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            continue
        if ctype == "text/plain" and not plain:
            plain = text
        elif ctype == "text/html" and not htmlpart:
            htmlpart = text
    headers = {k.lower(): _dh(v) for k, v in msg.items()}
    body = best_text(plain, htmlpart)
    if report:
        notice = body
    date = msg.get("Date")
    try:
        ts = email.utils.parsedate_to_datetime(date).timestamp()
    except Exception:
        ts = time.time()
    return {
        "message_id": (msg.get("Message-ID") or "").strip(),
        "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
        "references": (msg.get("References") or "").split(),
        "from": _dh(msg.get("From")),
        "from_addr": email.utils.parseaddr(_dh(msg.get("From")))[1].lower(),
        "to": _dh(msg.get("To")),
        "subject": _dh(msg.get("Subject")),
        "date": date or "",
        "ts": ts,
        "headers": headers,
        "reply_text": plain,
        "reply_html": htmlpart,
        "body": body,
        "report": report,
        "notice": notice,
        "original_to": original_to,
        "attachments": attachments,
    }


class Inbox:
    def __init__(self, cfg):
        self.cfg = cfg
        self.imap = None

    def __enter__(self):
        try:
            self.imap = imaplib.IMAP4_SSL(self.cfg["imap_host"], int(self.cfg.get("imap_port") or 993),
                                          ssl_context=_ctx(), timeout=40)
            self.imap.login(self.cfg["email"], self.cfg["email_password"])
        except Exception as exc:
            raise MailError(_friendly(exc, "Reading mail")) from exc
        return self

    def __exit__(self, *exc):
        try:
            self.imap.logout()
        except Exception:
            pass

    def new_messages(self, days, is_known, wanted=None):
        """Parsed messages from the inbox in the last `days` that `is_known`
        doesn't recognise and `wanted(headers)` accepts. Only headers are read
        for everything else. Nothing is marked as read.

        Returns (messages, skipped_ids) - skipped ones can be remembered so
        they're never looked at again."""
        self.imap.select("INBOX", readonly=True)
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = self.imap.uid("SEARCH", None, "SINCE", since)
        if typ != "OK" or not data or not data[0]:
            return [], []
        uids = data[0].split()[-800:]
        fresh, skipped = [], []
        for chunk in range(0, len(uids), 100):
            batch = b",".join(uids[chunk:chunk + 100])
            typ, rows = self.imap.uid(
                "FETCH", batch,
                "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM IN-REPLY-TO REFERENCES SUBJECT)])")
            if typ != "OK":
                continue
            for i, row in enumerate(rows):
                if not isinstance(row, tuple):
                    continue
                m = re.search(rb"UID (\d+)", row[0])
                if not m and i + 1 < len(rows) and isinstance(rows[i + 1], bytes):
                    m = re.search(rb"UID (\d+)", rows[i + 1])
                if not m:
                    continue
                head = email.message_from_bytes(row[1])
                mid = (head.get("Message-ID") or "").strip() or \
                    "<uid-%s@%s>" % (m.group(1).decode(), self.cfg["imap_host"])
                if is_known(mid):
                    continue
                info = {
                    "message_id": mid,
                    "from_addr": email.utils.parseaddr(_dh(head.get("From")))[1].lower(),
                    "from": _dh(head.get("From")),
                    "subject": _dh(head.get("Subject")),
                    "ids": [(head.get("In-Reply-To") or "").strip()] +
                           (head.get("References") or "").split(),
                }
                if wanted is None or wanted(info):
                    fresh.append(m.group(1))
                else:
                    skipped.append(mid)
        out = []
        for uid in fresh[:200]:
            typ, rows = self.imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK":
                continue
            for row in rows:
                if isinstance(row, tuple):
                    parsed = _parse(row[1])
                    if not parsed["message_id"]:
                        parsed["message_id"] = "<uid-%s@%s>" % (uid.decode(), self.cfg["imap_host"])
                    out.append(parsed)
        out.sort(key=lambda m: m["ts"])
        return out, skipped


def test_read(cfg):
    with Inbox(cfg) as box:
        box.imap.select("INBOX", readonly=True)
