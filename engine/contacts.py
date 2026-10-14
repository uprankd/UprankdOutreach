"""Is a website's email its own, or a link builder's / agency's address?

Imported databases often hold the address of a reseller (e.g. one agency email
for 500 websites). Pitching that gets agency prices, so Almo can look for the
site's own contact instead and keep the agency address as a fallback.
"""

import db

FREE_MAIL = (
    "gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com", "msn.com",
    "yahoo.com", "icloud.com", "me.com", "proton.me", "protonmail.com", "aol.com",
    "gmx.de", "gmx.net", "gmx.at", "web.de", "t-online.de", "mail.ru", "yandex.ru",
    "inbox.lv", "inbox.lt", "one.lt", "wp.pl", "o2.pl", "interia.pl", "onet.pl",
    "seznam.cz", "libero.it", "orange.fr", "free.fr", "laposte.net", "hotmail.fr",
    "hotmail.it", "yahoo.fr", "yahoo.it", "yahoo.es", "yahoo.co.uk", "hotmail.co.uk",
)
SHARED_LIMIT = 3          # the same address on 3+ websites = someone who sells many


def own_address(domain, email):
    """True when the address is on the website's own domain (or a sibling like
    news.site.lv / site-media.lv)."""
    edom = (email or "").split("@")[-1].lower()
    domain = (domain or "").lower()
    if not edom or not domain:
        return False
    if edom == domain or edom.endswith("." + domain) or domain.endswith("." + edom):
        return True
    base = domain.split(".")[0]
    if edom.split(".")[0] == base:          # site.lv and site.com
        return True
    return len(base) >= 4 and base in edom


def shared_counts():
    """{email: number of websites using it} for addresses on 2+ websites."""
    return {r["email"]: r["n"] for r in db.query(
        "SELECT email, COUNT(*) AS n FROM sites WHERE email<>'' GROUP BY email HAVING COUNT(*)>1")}


def is_link_builder(domain, email, shared=0):
    """A third party: not the site's own address, and either a company domain
    or a free-mail address used for several websites."""
    if not email or own_address(domain, email):
        return False
    if shared >= SHARED_LIMIT:
        return True
    edom = email.split("@")[-1].lower()
    return edom not in FREE_MAIL
