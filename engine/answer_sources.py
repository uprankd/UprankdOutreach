"""Did a reply answer in its text, or point us at a file or link instead?

Publishers often answer an outreach email with a spreadsheet, a PDF media kit,
or a Google Sheets link rather than writing the prices out. The extractor only
reads text, so those replies look like they said nothing - and the bot used to
mark every field "Unknown" and draft a follow-up asking for information the
publisher had already sent. Such replies are now marked "Manual review".

What counts is deliberately narrow. Nearly every email carries links and
images in its signature, so only DOCUMENTS count: document attachments, and
links to document hosts or straight to a document file. Anything inside the
quoted copy of our own email is ignored, so a link we sent cannot come back
looking like their answer.
"""

import re
from urllib.parse import parse_qs, unquote, urlparse

DOCUMENT_EXTENSIONS = (
    ".xlsx", ".xls", ".xlsm", ".xlsb", ".csv", ".ods", ".numbers",
    ".pdf",
    ".doc", ".docx", ".odt", ".rtf", ".pages",
    ".ppt", ".pptx", ".odp", ".key",
)

# Places a price list or media kit is shared from. Matched on the host name,
# so a Drive link counts wherever it appears in the reply.
DOCUMENT_HOSTS = (
    "docs.google.com", "drive.google.com", "sheets.google.com",
    "onedrive.live.com", "1drv.ms", "sharepoint.com",
    "dropbox.com", "dropboxusercontent.com",
    "wetransfer.com", "we.tl", "box.com", "icloud.com",
    "notion.so", "notion.site", "airtable.com", "canva.com", "docsend.com",
)

_URL = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Where a reply stops and the quoted earlier message begins.
_HTML_QUOTE_MARKERS = (
    'class="gmail_quote', "class='gmail_quote", 'class="gmail_attr',
    'id="appendonsend"', 'id="divrplyfwdmsg"', 'class="yahoo_quoted',
    'id="mail-editor-reference-message-container"', '<blockquote type="cite"',
    'class="moz-cite-prefix"', 'id="reply-intro"',
)
_TEXT_REPLY_HEADER = re.compile(
    r"^[ \t]*(?:"
    r"On\b.{0,300}?wrote:|"                          # English
    r"Am\b.{0,300}?schrieb.{0,100}?:|"                # German
    r"Op\b.{0,300}?schreef.{0,100}?:|"                # Dutch
    r"Στις\b.{0,300}?έγραψε:|"                        # Greek
    r"Le\b.{0,300}?a écrit\s*:|"                     # French
    r"-{2,}\s*(?:Original Message|Ursprüngliche Nachricht|"
    r"Oorspronkelijk bericht|Αρχικό μήνυμα)\s*-{2,}|"
    r"(?:From|Von|Van|Από)\s*:[^\n]*@[^\n]*$"         # an address, not "From: 150 EUR"
    r")",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def document_attachments(names):
    """Attachment names that hold answers - documents, never logos or invites."""
    found = []
    for name in names or ():
        clean = str(name or "").strip()
        if clean and clean.lower().endswith(DOCUMENT_EXTENSIONS):
            found.append(clean)
    return found


def strip_quoted_html(html):
    """The reply's own HTML, with the quoted earlier message cut off."""
    if not html:
        return ""
    lowered = html.lower()
    cut = len(html)
    for marker in _HTML_QUOTE_MARKERS:
        at = lowered.find(marker)
        if at < 0:
            continue
        # cut at the start of the tag that carries the marker
        tag_start = at if marker.startswith("<") else lowered.rfind("<", 0, at)
        cut = min(cut, tag_start if tag_start >= 0 else at)
    return html[:cut]


def strip_quoted_text(text):
    """The reply's own text: stops at the first reply header, drops '>' lines."""
    if not text:
        return ""
    match = _TEXT_REPLY_HEADER.search(text)
    if match:
        text = text[:match.start()]
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(">"))


def _unwrap(url):
    """Outlook SafeLinks and Google redirect wrappers hide the real address."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query)
    if host.endswith("safelinks.protection.outlook.com") and query.get("url"):
        return unquote(query["url"][0])
    if host in ("www.google.com", "google.com") and parsed.path == "/url":
        target = query.get("q") or query.get("url")
        if target:
            return unquote(target[0])
    return url


def is_document_link(url):
    """A link to somewhere a document lives, not just any web page."""
    url = _unwrap(url.strip().rstrip(".,;:!?"))
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if any(host == h or host.endswith("." + h) for h in DOCUMENT_HOSTS):
        return True
    return unquote(parsed.path).lower().endswith(DOCUMENT_EXTENSIONS)


def document_links(html="", text=""):
    """Document links in the reply itself - its HTML hrefs and bare URLs."""
    own_html = strip_quoted_html(html or "")
    candidates = _HREF.findall(own_html) + _URL.findall(own_html)
    candidates += _URL.findall(strip_quoted_text(text or ""))

    found, seen = [], set()
    for raw in candidates:
        url = _unwrap(raw.strip().rstrip(".,;:!?"))
        key = url.lower()
        if key in seen or not is_document_link(url):
            continue
        seen.add(key)
        found.append(url)
    return found


def answer_sources(email, ai_says_elsewhere=False):
    """Where a reply put its answers, if not in its text. [] means in the text.

    `email` carries "attachments" (names), "reply_html" and "reply_text" - the
    reply's own content, not the quoted thread. `ai_says_elsewhere` is the
    extractor's own judgement, which catches "our rates are on our website" or
    "see the attached screenshot" that no filename or host rule can see.
    """
    pointers = document_attachments(email.get("attachments"))
    pointers += document_links(email.get("reply_html", ""), email.get("reply_text", ""))

    unique, seen = [], set()
    for pointer in pointers:
        if pointer.lower() not in seen:
            seen.add(pointer.lower())
            unique.append(pointer)
    if not unique and ai_says_elsewhere:
        unique = ["an attachment or link in the reply"]
    return unique
