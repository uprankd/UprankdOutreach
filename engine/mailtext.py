"""Turn a received message into readable text.

Both mail clients used to take text/plain and nothing else. Plenty of real mail
carries no plain-text part at all - newsletters, anything written in a webmail
composer, most out-of-office autoresponders - so those messages arrived with an
empty body and the processor discarded them as "not valid", reporting an empty
inbox while the inbox was plainly not empty.
"""

import re

_BLOCK_END = re.compile(
    r"</\s*(p|div|br|tr|li|h[1-6]|table|blockquote)\s*/?>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_DROP = re.compile(r"<(script|style|head)[^>]*>.*?</\1\s*>",
                   re.IGNORECASE | re.DOTALL)
_SPACES = re.compile(r"[ \t\f\v]+")
_BLANKS = re.compile(r"\n\s*\n\s*\n+")


def html_to_text(html: str) -> str:
    """Readable text from an HTML message body.

    Uses BeautifulSoup when it is importable and falls back to a regex strip,
    so this keeps working in a build where bs4 was not collected.
    """
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "head"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception:
        text = _DROP.sub(" ", html)
        text = _BLOCK_END.sub("\n", text)
        text = _TAG.sub(" ", text)

    import html as html_module

    text = html_module.unescape(text)
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _BLANKS.sub("\n\n", text).strip()


def best_text(plain: str = "", html: str = "") -> str:
    """Plain text when there is any, otherwise the HTML rendered down to text."""
    if plain and plain.strip():
        return plain.strip()
    return html_to_text(html)
