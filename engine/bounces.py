"""Mail that came back: which address does not work, and why.

"Your message could not be delivered" is not an answer from a publisher - it is
the mail system saying the address on file does not work. Those were skipped
outright (the sender is mailer-daemon or postmaster), so a dead contact stayed
white in the sheet and went on being mailed. Now the address that failed is
worked out and its contact cell goes red.

Two kinds are recognised:

  bounce  a delivery report - Gmail's "Address not found", Outlook's
          "Undeliverable:", Postfix's "Undelivered Mail Returned to Sender" and
          the like, in the sheets' languages. "Delayed - will retry" notices
          are not failures and are left alone.
  notice  an automatic reply from the mailbox itself saying it is no longer in
          use or no longer read, or that the person has left. Only its own
          text counts (never the quoted thread), and a long reply that also
          happens to mention it is left to be read as the answer it is.
"""

import re

from answer_sources import strip_quoted_html, strip_quoted_text
from mailtext import best_text

_ADDRESS = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _any(patterns):
    return re.compile("|".join("(?:%s)" % p for p in patterns), re.IGNORECASE)


# Who sends delivery reports.
_SYSTEM_SENDER = _any([
    r"mailer-?daemon", r"postmaster", r"mail\s+delivery\s+(?:subsystem|system|service)",
    r"microsoftexchange[0-9a-f]*@", r"mail\s+administrator",
])

# Addresses that are the mail system itself, never a contact.
_SYSTEM_LOCAL = re.compile(
    r"^(?:mailer-?daemon|postmaster|no-?reply|do-?not-?reply|donotreply|bounces?"
    r"|microsoftexchange[0-9a-f]*)$", re.IGNORECASE)

_FAILURE_SUBJECT = _any([
    r"delivery\s+status\s+notification\s*\(\s*failure\s*\)",
    r"\bundeliverable\b", r"\bundelivered\b", r"\bnon-?deliverable\b",
    r"\bnot\s+delivered\b", r"\bcould\s*n[o']?t\s+be\s+delivered\b",
    r"\bdelivery\s+(?:has\s+)?failed\b", r"\bdelivery\s+failure\b",
    r"\bfailure\s+notice\b", r"\breturned\s+(?:mail|to\s+sender)\b",
    r"\bmail\s+delivery\s+failed\b", r"\bdelivery\s+(?:was\s+)?unsuccessful\b",
    # German, Dutch, French, Italian, Spanish, Portuguese
    r"unzustellbar", r"nicht\s+zustellbar", r"nicht\s+zugestellt",
    r"zustellung\s+fehlgeschlagen",
    r"onbestelbaar", r"niet\s+bezorgd", r"bezorging\s+mislukt",
    r"kan\s+niet\s+worden\s+bezorgd",
    r"non\s+remis", r"non\s+distribu", r"[ée]chec\s+de\s+(?:la\s+)?(?:remise|distribution)",
    r"non\s+recapitabil", r"impossibile\s+recapitare", r"mancato\s+recapito",
    r"no\s+se\s+(?:puede|pudo)\s+entregar", r"imposible\s+entregar",
    r"entrega\s+fallida", r"no\s+entregado",
    r"n[ãa]o\s+entregue", r"falha\s+na\s+entrega",
    # Polish, Czech/Slovak, Hungarian, Romanian, Nordic, Greek, Russian
    r"niedostarcz", r"nie\s+mo[zż]na\s+dostarczy", r"nedoru[čc]",
    r"k[ée]zbes[ií]thetetlen", r"nelivrabil", r"kunne\s+ikke\s+leveres",
    r"kunde\s+inte\s+levereras", r"ei\s+voitu\s+toimittaa",
    r"αδυναμία\s+παράδοσης", r"δεν\s+ήταν\s+δυνατή\s+η\s+παράδοση",
    r"δεν\s+παραδόθηκε", r"αποτυχία\s+παράδοσης",
    r"не\s*доставлен", r"недоставляем",
])

# "Still trying" is not "failed".
_DELAY = _any([
    r"\(\s*delay\s*\)", r"\bdelayed\b", r"\bstill\s+being\s+retried\b",
    r"\bwill\s+(?:be\s+)?retr(?:y|ied)\b", r"verz[öo]gert", r"vertraagd",
    r"retard[ée]", r"ritardat", r"retrasad", r"καθυστέρηση",
])

# What a delivery report says when it failed. Only trusted from a sender that
# is plainly the mail system, or next to a failure subject.
_FAILURE_TEXT = _any([
    r"\baddress\s+(?:was\s+)?not\s+found\b",
    r"\bno\s+such\s+(?:user|mailbox|recipient|address|domain|account)\b",
    r"\b(?:user|recipient|mailbox|address|account)\s+(?:is\s+)?"
    r"(?:unknown|not\s+found|unavailable|disabled|deactivated|inactive|invalid)\b",
    r"\b(?:unknown|invalid|non-?existent)\s+(?:user|recipient|mailbox|address|e-?mail)\b",
    r"\bdoes\s*n[o']?t\s+exist\b",
    r"\brecipient\s+(?:address\s+)?rejected\b", r"\b(?:was|were)\s+rejected\b",
    r"\brejected\s+your\s+message\b",
    r"\b(?:was\s*n[o']?t|could\s*n[o']?t\s+be|cannot\s+be|can'?t\s+be)\s+delivered\b",
    r"\bdelivery\s+(?:has\s+)?failed\b",
    r"\bpermanent(?:ly)?\s+(?:error|failure|fatal|failed)\b",
    r"\b5\.\d\.\d{1,3}\b", r"\b55[0-4][ -]",
    r"\bdomain\s+(?:name\s+)?not\s+found\b",
    r"\bhost\s+(?:or\s+domain\s+name\s+)?not\s+found\b",
    r"\bmailbox\s+(?:is\s+)?full\b", r"\bover\s*quota\b", r"\bquota\s+exceeded\b",
    r"\baccount\s+(?:that\s+)?you\s+tried\s+to\s+reach\b",
    r"existiert\s+nicht", r"unbekannt", r"konnte\s+nicht\s+zugestellt",
    r"bestaat\s+niet", r"onbekend", r"kan\s+niet\s+worden\s+(?:bezorgd|afgeleverd)",
    r"n'existe\s+pas", r"inconnu", r"non\s+esiste", r"sconosciut", r"no\s+existe",
    r"desconocid", r"δεν\s+υπάρχει", r"άγνωστ",
])

# Why, in a few words for the sheet - most specific first.
_REASONS = (
    ("domain not found", _any([
        r"domain\s+(?:name\s+)?not\s+found", r"host\s+(?:or\s+domain\s+name\s+)?not\s+found",
        r"\bdns\b", r"address\s+resolution", r"\bno\s+mx\b", r"\b5\.1\.2\b",
        r"\b5\.4\.4\b", r"domain\s+does\s*n[o']?t\s+exist", r"unrouteable", r"nxdomain"])),
    ("mailbox full", _any([
        r"mailbox\s+(?:is\s+)?full", r"over\s*quota", r"quota\s+exceeded",
        r"exceeded\s+(?:the|its|their)\s+storage", r"insufficient\s+(?:storage|space)",
        r"\b5\.2\.2\b", r"postfach\s+(?:ist\s+)?voll", r"mailbox\s+(?:is\s+)?vol\b"])),
    ("mailbox disabled", _any([
        r"(?:account|mailbox|user|address)\s+(?:has\s+been\s+|is\s+)?"
        r"(?:disabled|deactivated|suspended|inactive|locked|closed)\b",
        r"tried\s+to\s+reach\s+is\s+(?:disabled|inactive)", r"\b5\.2\.1\b"])),
    ("address not found", _any([
        r"address\s+(?:was\s+)?not\s+found", r"couldn't\s+be\s+found",
        r"could\s+not\s+be\s+found",
        r"no\s+such\s+(?:user|mailbox|recipient|address|account)",
        r"(?:user|recipient|mailbox|account|address)\s+(?:is\s+)?(?:unknown|not\s+found|invalid)",
        r"does\s*n[o']?t\s+exist", r"(?:unknown|invalid|non-?existent)\s+"
        r"(?:user|recipient|mailbox|address|e-?mail)",
        r"\b5\.1\.1\b", r"\b5\.1\.10\b", r"\b5\.1\.0\b", r"\b5\.4\.1\b",
        r"account\s+(?:that\s+)?you\s+tried\s+to\s+reach", r"wasn't\s+found",
        r"existiert\s+nicht", r"unbekannt", r"bestaat\s+niet", r"onbekend",
        r"n'existe\s+pas", r"inconnu", r"no\s+existe", r"δεν\s+υπάρχει"])),
    ("blocked by their server", _any([
        r"rejected", r"blocked", r"block\s*list", r"blacklist", r"\bspam\b",
        r"\bpolicy\b", r"\b5\.7\.\d{1,3}\b", r"access\s+denied",
        r"not\s+(?:permitted|allowed|authori[sz]ed)", r"refused"])),
)
_DEFAULT_REASON = "could not be delivered"

# A mailbox saying it is dead. Self-referential on purpose ("this address",
# "I no longer work here"): "his email" or "this offer is no longer valid"
# must not turn anyone red.
_NOTICE_DEAD = _any([
    r"\b(?:this|my|the)\s+(?:e-?mail\s+)?(?:address|mailbox|inbox|account|e-?mail)\b"
    r"[^.!?\n]{0,40}?\bno\s+longer\s+(?:be\s+)?(?:in\s+use|used|active|valid|monitored|"
    r"checked|read|in\s+service|maintained|operational|exists?|available|"
    r"being\s+(?:monitored|checked|read|used))\b",
    r"\b(?:this|my|the)\s+(?:e-?mail\s+)?(?:address|mailbox|inbox|account|e-?mail)\b"
    r"[^.!?\n]{0,40}?\bis\s+not\s+(?:in\s+use|used|active|valid)\b",
    r"\b(?:this|my|the)\s+(?:e-?mail\s+)?(?:address|mailbox|inbox|account)\b"
    r"[^.!?\n]{0,40}?\b(?:has\s+been|was|is)\s+(?:deactivated|disabled|closed|deleted|"
    r"discontinued|removed|terminated|shut\s+down|retired)\b",
    r"\b(?:this|the)\s+(?:e-?mail\s+)?(?:address|e-?mail)\s+(?:you\s+(?:have\s+)?"
    r"(?:used|written\s+to|sent\s+to|emailed)\s+)?(?:is|seems)\s+"
    r"(?:invalid|not\s+valid|incorrect|wrong)\b",
    r"\bplease\s+(?:do\s+not|don't)\s+(?:use|write\s+to|send\s+(?:e-?mails?\s+)?to)"
    r"\s+this\s+(?:e-?mail\s+)?address\b",
    # German
    r"\bdies(?:e|es|er)\s+(?:e-?mail-?)?(?:adresse|postfach|mailbox|e-?mail|konto|account)\b"
    r"[^.!?\n]{0,50}?\bnicht\s+(?:mehr|länger)\b[^.!?\n]{0,30}?\b(?:aktiv|gültig|genutzt|"
    r"verwendet|benutzt|in\s+(?:gebrauch|benutzung|betrieb)|erreichbar|abgerufen|gelesen|"
    r"betreut|vorhanden)",
    r"\b(?:e-?mail-?)?adresse\b[^.!?\n]{0,30}?\b(?:ist\s+)?(?:ungültig|existiert\s+nicht\s+mehr)",
    # Dutch
    r"\bdit\s+(?:e-?mail\s*)?(?:adres|mailadres|e-?mailadres|postvak|account|mailbox)\b"
    r"[^.!?\n]{0,50}?\bniet\s+(?:meer|langer)\b[^.!?\n]{0,30}?\b(?:in\s+gebruik|actief|"
    r"geldig|gelezen|bereikbaar|bewaakt|beschikbaar|bekeken)",
    # Greek
    r"(?:διεύθυνση|θυρίδα|λογαριασμός)[^.!?\n]{0,50}?(?:δεν\s+(?:χρησιμοποιείται|"
    r"είναι\s+(?:πλέον\s+)?ενεργ|ελέγχεται)|έχει\s+απενεργοποιηθεί|δεν\s+υπάρχει\s+πλέον)",
    # French, Italian, Spanish
    r"\bcette\s+(?:adresse|bo[iî]te)\b[^.!?\n]{0,50}?\b(?:n'est\s+plus|ne\s+sera\s+plus|"
    r"n'est\s+pas)\s+(?:active|utilis[ée]e|valide|consult[ée]e|lue|relev[ée]e)",
    r"\bquest[oa]\s+(?:indirizzo|account|casella)\b[^.!?\n]{0,50}?\bnon\s+(?:è|e'|e)\s+"
    r"più\s+(?:attiv|in\s+uso|valid|utilizzat|monitorat|controllat)",
    r"\besta\s+(?:dirección|direccion|cuenta|casilla)\b[^.!?\n]{0,50}?\bya\s+no\s+"
    r"(?:está|esta|es|se)\s+(?:activa|en\s+uso|válida|valida|utiliza|usa|revisa|lee)",
])
_NOTICE_LEFT = _any([
    r"\bI\s+(?:no\s+longer|don't|do\s+not)\s+work\s+(?:at|for|with|here)\b",
    r"\bI\s+am\s+no\s+longer\s+(?:with|at|working\s+(?:at|for|with))\b",
    r"\bI\s*(?:have|'ve)\s+left\s+(?:the\s+)?(?:company|organi[sz]ation|business|firm|team)\b",
    r"\bich\s+bin\s+nicht\s+mehr\s+(?:bei|für|im\s+unternehmen|tätig)",
    r"\bik\s+(?:ben|werk)\s+niet\s+(?:meer|langer)\s+(?:werkzaam\s+)?(?:bij|voor|in\s+dienst)",
    r"δεν\s+εργάζομαι\s+(?:πλέον|πια)",
    r"\bje\s+ne\s+(?:travaille|fais)\s+plus\s+(?:chez|pour|partie)",
    r"\bnon\s+lavoro\s+più\s+(?:per|presso|con)",
    r"\bya\s+no\s+trabajo\s+(?:en|para|con)",
])
# "John is no longer with the company" is only about the sender's own address
# when John's mailbox says it automatically. Typed by a colleague, it is the
# colleague taking over - their address works, and must not turn red.
_NOTICE_LEFT_THIRD = _any([
    r"\bis\s+no\s+longer\s+(?:with\s+(?:us|the\s+company|the\s+team|our\s+company)|"
    r"employed|working\s+(?:at|for|with|here))\b",
    r"\b(?:ist|sind)\s+nicht\s+mehr\s+(?:bei\s+(?:uns|der|dem)|im\s+unternehmen|"
    r"für\s+(?:uns|die|das)\s+tätig)",
    r"\b(?:is|zijn)\s+niet\s+(?:meer|langer)\s+(?:werkzaam\s+bij|in\s+dienst)",
])

# "This address will no longer be in use from May" still works today. (German
# "wird nicht mehr gelesen" is present tense - "is no longer read" - so "wird"
# is not in here.)
_FUTURE = re.compile(r"\b(?:will|soon|from\s+next|starting|demnächst|bald|zal|binnenkort"
                     r"|vanaf)\b", re.IGNORECASE)

_AUTO_SUBJECT = re.compile(
    r"^\s*(?:automatic\s+reply|auto(?:matic)?[\s-]*(?:reply|response)|autoreply|auto\s*:|"
    r"out\s+of\s+(?:the\s+)?office|abwesenheit|automatische\s+antwort|"
    r"automatisch\s+antwoord|afwezig|réponse\s+automatique|risposta\s+automatica|"
    r"respuesta\s+automática|αυτόματη\s+απάντηση|εκτός\s+γραφείου)", re.IGNORECASE)

# A human reply longer than this that merely mentions an address is going away
# is read as the answer it is; only a short or automatic one is a "notice".
NOTICE_MAX_CHARS = 600


def _addresses(text):
    return [a.lower() for a in _ADDRESS.findall(text or "")]


def _unique(items):
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _report_recipients(report):
    """[(addresses, action, status, diagnostic)] per recipient in a delivery report."""
    found = []
    for block in re.split(r"\n\s*\n", report or ""):
        fields = {}
        for name, value in re.findall(r"^([A-Za-z][A-Za-z-]*):[ \t]*(.*)$", block,
                                      re.MULTILINE):
            fields.setdefault(name.lower(), value.strip())
        recipient = fields.get("final-recipient") or fields.get("original-recipient")
        if not recipient:
            continue
        found.append((_addresses(recipient), fields.get("action", "").lower(),
                      fields.get("status", ""), fields.get("diagnostic-code", "")))
    return found


def _near_failure(text, named):
    """The named addresses that sit on a failure line or just above one.

    "<info@site.gr>:" then "Sorry, no mailbox here by that name." on the next
    line is the usual layout; a help-desk address further down is not it.
    """
    lines = (text or "").splitlines()
    near = []
    for index, line in enumerate(lines):
        window = line + " " + (lines[index + 1] if index + 1 < len(lines) else "")
        if _FAILURE_TEXT.search(window):
            near += [a for a in _addresses(line) if a in named]
    return _unique(near)


def _own_filter(own_addresses):
    """A test for addresses that are ours or the mail system's, never a contact."""
    own = {a.strip().lower() for a in own_addresses or () if a and "@" in a}
    try:
        from response_audit import FREE_MAIL_DOMAINS
    except Exception:
        FREE_MAIL_DOMAINS = set()
    own_domains = {a.split("@", 1)[1] for a in own} - set(FREE_MAIL_DOMAINS)

    def excluded(address):
        local, _, domain = address.partition("@")
        return (address in own or domain in own_domains
                or bool(_SYSTEM_LOCAL.match(local)))
    return excluded


def _reason(blob):
    for reason, pattern in _REASONS:
        if pattern.search(blob):
            return reason
    return _DEFAULT_REASON


def _is_auto_reply(email, headers):
    submitted = headers.get("auto-submitted", "").strip().lower()
    return bool((submitted and submitted != "no")
                or "x-autoreply" in headers or "x-autorespond" in headers
                or headers.get("precedence", "").strip().lower() == "auto_reply"
                or _AUTO_SUBJECT.search(email.get("subject", "") or ""))


def analyse(email, own_addresses=()):
    """Does this message say an address does not work? None if not.

    `email` is what the mail clients hand the processor: "from", "subject",
    "headers" (lower-cased names), "report" (a delivery-status block, if any),
    "notice" (the message's own readable text, without the copy of our email a
    report usually attaches), "original_to" (who that copy - or our sent
    message in the same thread - was addressed to), and "reply_text" /
    "reply_html".

    Returns {"kind": "bounce" | "notice", "addresses": [...], "reason": str,
    "others": [...]}. `addresses` can be empty for a failure that does not
    say which address failed; `others` are addresses a notice offers instead.
    """
    headers = {str(k).lower(): str(v) for k, v in (email.get("headers") or {}).items()}
    sender = email.get("from", "") or ""
    subject = email.get("subject", "") or ""
    excluded = _own_filter(own_addresses)
    sender_addresses = _addresses(sender)

    # -- a delivery report ------------------------------------------------
    recipients = _report_recipients(email.get("report", ""))
    failed_in_report = [a for addresses, action, status, _d in recipients
                        if action == "failed" or status.startswith("5")
                        for a in addresses]
    nothing_failed = bool(recipients) and not failed_in_report
    x_failed = _addresses(headers.get("x-failed-recipients", ""))
    content_type = headers.get("content-type", "").lower().replace('"', "").replace(" ", "")
    is_report = "report-type=delivery-status" in content_type
    automated = bool(_SYSTEM_SENDER.search(sender)) or is_report or bool(x_failed)

    text = email.get("notice") or best_text(email.get("reply_text", ""),
                                            email.get("reply_html", ""))
    delayed = nothing_failed or (_DELAY.search(subject) and not x_failed
                                 and not failed_in_report)
    says_failed = bool(_FAILURE_SUBJECT.search(subject) or _FAILURE_TEXT.search(text))

    bounced = bool(x_failed or failed_in_report) or (
        not delayed and ((automated and says_failed)
                         or (_FAILURE_SUBJECT.search(subject) and _FAILURE_TEXT.search(text))))
    if bounced:
        candidates = [a for a in x_failed + failed_in_report if not excluded(a)]
        if not candidates:
            # The report's own words, preferring an address we actually wrote to.
            sent = [a for a in _addresses(" ".join(email.get("original_to") or ()))
                    if not excluded(a)]
            named = [a for a in _addresses(text)
                     if not excluded(a) and a not in sender_addresses]
            candidates = ([a for a in named if a in sent] or _near_failure(text, named)
                          or named)
            if not candidates and len(set(sent)) == 1:
                candidates = sent
        blob = "\n".join([status + " " + diagnostic
                          for _a, _act, status, diagnostic in recipients] + [text[:4000]])
        return {"kind": "bounce", "addresses": _unique(candidates),
                "reason": _reason(blob), "others": []}

    # -- a mailbox saying it is dead --------------------------------------
    if not sender_addresses or excluded(sender_addresses[0]):
        return None
    own_text = best_text(strip_quoted_text(email.get("reply_text", "")),
                         strip_quoted_html(email.get("reply_html", "")))
    automatic = _is_auto_reply(email, headers)
    dead = next((m for m in _NOTICE_DEAD.finditer(own_text)
                 if not _FUTURE.search(m.group(0))), None)
    left = None if dead else (_NOTICE_LEFT.search(own_text)
                              or (automatic and _NOTICE_LEFT_THIRD.search(own_text)))
    if not (dead or left):
        return None
    if len(own_text) > NOTICE_MAX_CHARS and not automatic:
        return None
    address = sender_addresses[0]
    others = [a for a in _addresses(own_text) if a != address and not excluded(a)]
    return {"kind": "notice", "addresses": [address],
            "reason": "no longer in use" if dead else "the person has left",
            "others": _unique(others)[:2]}
