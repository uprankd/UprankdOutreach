"""Read a website: its text, language, and the best contact address.

Based on the old email_finder, with the false positives fixed:
  * "follow us at Facebook.com" is no longer turned into us@facebook.com - only
    bracketed forms like name [at] site [dot] com are rebuilt;
  * script/style contents are dropped before reading text, so tracking
    addresses (Sentry, Wix) don't leak in, and junk domains match subdomains;
  * contact pages are tried even when the homepage is blocked, and http:// /
    www. are tried when https:// fails.
"""

import html as html_module
import re
from urllib.parse import urljoin, urlparse

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,24}")
SUBPAGE_WORDS = (
    "contact", "kontakt", "kontakti", "impressum", "about", "advertis", "adverteren",
    "werbung", "reklama", "reklam", "sadarbiba", "sadarbība", "contacto", "contatti",
    "redaktion", "redakcija", "media-kit", "mediakit", "partner", "imprint",
)
BLIND_SLUGS = ("/contact", "/kontakt", "/kontakti", "/impressum", "/about",
               "/contact-us", "/reklama", "/advertise")
JUNK_LOCAL = re.compile(r"^(noreply|no-reply|donotreply|do-not-reply|postmaster|"
                        r"mailer-daemon|abuse|privacy|gdpr|dpo|webmaster|wordpress|"
                        r"example|test|user|name|email|your|you)$", re.I)
JUNK_DOMAINS = ("example.com", "example.org", "sentry.io", "sentry-next.wixpress.com",
                "wixpress.com", "wix.com", "sentry.wixpress.com", "domain.com",
                "email.com", "yourdomain.com", "test.com", "ingest.sentry.io",
                "cloudflare.com", "w3.org", "schema.org", "godaddy.com", "squarespace.com")
FILE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".ico",
            ".css", ".js", ".bmp", ".tif")
PREFERRED = (
    "redaktion", "redactie", "redakcija", "redaktsia", "editor", "editorial",
    "advert", "adverteren", "reklama", "reklame", "werbung", "anzeigen", "ads",
    "sales", "marketing", "media", "partner", "presse", "press", "news",
    "kontakt", "contact", "info", "office", "hello", "hi", "mail",
)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")


def clean_domain(raw):
    """'https://www.Site.lv/page' -> 'site.lv'. '' when it isn't a website."""
    if raw is None:
        return ""
    text = str(raw).strip().strip(",;\"'<>()[]")
    if not text or " " in text:
        return ""
    if "@" in text and "://" not in text:
        return ""
    text = re.sub(r"^[a-z]+://", "", text, flags=re.I)
    text = text.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
    text = re.sub(r"^www\.", "", text, flags=re.I).lower().strip(".")
    if not re.match(r"^[a-z0-9¡-￿-]+(\.[a-z0-9¡-￿-]+)+$", text):
        return ""
    return text


def parse_list(text):
    """Every distinct domain in a pasted block (lines, commas, tabs...)."""
    seen, out = set(), []
    for token in re.split(r"[\s,;|]+", text or ""):
        d = clean_domain(token)
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _session():
    try:
        import cloudscraper

        s = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "darwin", "desktop": True})
    except Exception:
        import requests

        s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en,lv;q=0.8,de;q=0.6"})
    return s


def _get(session, url, timeout):
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ("html" in ctype or not ctype):
            return r
    except Exception:
        pass
    return None


def _cf_decode(hexstr):
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except Exception:
        return ""


def useful(address, site_domain=""):
    address = address.strip().strip(".").lower()
    local, _, domain = address.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if domain.endswith(FILE_EXT) or re.search(r"@\d+x\.", address):
        return False
    if JUNK_LOCAL.match(local):
        return False
    if any(domain == j or domain.endswith("." + j) for j in JUNK_DOMAINS):
        return False
    if re.fullmatch(r"[0-9a-f]{16,}", local):          # tracking ids
        return False
    if len(local) > 40:
        return False
    return True


def emails_in_html(raw_html):
    from bs4 import BeautifulSoup

    found = set()
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.find_all(attrs={"data-cfemail": True}):
        addr = _cf_decode(tag.get("data-cfemail", ""))
        if EMAIL_RE.fullmatch(addr or ""):
            found.add(addr.lower())
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            addr = html_module.unescape(addr)
            for m in EMAIL_RE.findall(addr):
                found.add(m.lower())
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = html_module.unescape(soup.get_text(" "))
    # Only clearly obfuscated forms: name [at] domain [dot] com / name(at)domain.com
    text = re.sub(r"\s*[\[\(\{]\s*(?:at|@|ät)\s*[\]\)\}]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*[\[\(\{]\s*(?:dot|punkts|punkt)\s*[\]\)\}]\s*", ".", text, flags=re.I)
    for m in EMAIL_RE.findall(text):
        found.add(m.lower())
    return found, soup


def best_address(domain, emails):
    """The single address to pitch: the site's own editorial/ads inbox first."""
    if not emails:
        return ""
    base = domain.split(".")[0]
    own = [e for e in emails if e.split("@")[1] == domain or e.split("@")[1].endswith("." + domain)]
    near = [e for e in emails if base and base in e.split("@")[1]]
    pool = own or near or list(emails)

    def rank(addr):
        local = addr.split("@")[0]
        for i, hint in enumerate(PREFERRED):
            if local.startswith(hint):
                return (0, i, len(addr))
        return (1, 0, len(addr))

    return sorted(pool, key=rank)[0]


def read_site(domain, timeout=12):
    """{'ok', 'text', 'language', 'emails', 'title'} for one website. Never raises."""
    session = _session()
    result = {"ok": False, "text": "", "language": "", "emails": [], "title": "", "blocked": False}
    home = None
    base = None
    for candidate in ("https://%s" % domain, "https://www.%s" % domain, "http://%s" % domain):
        home = _get(session, candidate, timeout)
        if home is not None:
            base = home.url
            break
    found = set()
    links = []
    if home is not None:
        result["ok"] = True
        try:
            from bs4 import BeautifulSoup

            raw = home.text
            soup_full = BeautifulSoup(raw, "html.parser")
            html_tag = soup_full.find("html")
            if html_tag and html_tag.get("lang"):
                result["language"] = html_tag["lang"].split("-")[0].lower()[:5]
            if soup_full.title and soup_full.title.string:
                result["title"] = soup_full.title.string.strip()[:160]
            for a in soup_full.find_all("a", href=True):
                href = a["href"]
                label = (a.get_text() or "").lower()
                if any(w in href.lower() or w in label for w in SUBPAGE_WORDS):
                    full = urljoin(base, href)
                    host = urlparse(full).netloc.lower().replace("www.", "")
                    if host.endswith(domain) and full not in links:
                        links.append(full)
            emails, soup = emails_in_html(raw)
            found |= emails
            result["text"] = re.sub(r"\s+", " ", soup.get_text(" "))[:6000]
        except Exception:
            pass
    else:
        base = "https://%s" % domain
        result["blocked"] = True

    if not any(useful(e) for e in found):
        tried = 0
        for url in links[:5] + [urljoin(base, s) for s in BLIND_SLUGS]:
            if tried >= 7:
                break
            tried += 1
            page = _get(session, url, timeout)
            if page is None:
                continue
            try:
                emails, _ = emails_in_html(page.text)
                found |= emails
            except Exception:
                continue
            if any(useful(e) for e in found):
                break

    good = sorted({e for e in found if useful(e)})
    pick = best_address(domain, good)
    if pick:
        good.remove(pick)
        good.insert(0, pick)
    result["emails"] = good
    return result
