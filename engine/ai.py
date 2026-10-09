"""Claude calls. Every answer comes back through a forced tool call, so it is
always valid JSON - no free text, no hidden <analysis> leaking into emails."""

import hashlib
import json

import db

FIELDS = ("price", "special_price", "casino", "loan", "crypto", "adult",
          "sponsored_tag", "link_insertion")
ESSENTIAL = ("price", "casino", "loan", "crypto", "adult", "sponsored_tag", "link_insertion")
UNKNOWN = {"", "unknown", "n/a", "na", "none", "-", "not specified", "not mentioned", "?"}

LANG_NAMES = {
    "en": "English", "lv": "Latvian", "lt": "Lithuanian", "et": "Estonian", "de": "German",
    "nl": "Dutch", "fr": "French", "it": "Italian", "es": "Spanish", "pt": "Portuguese",
    "pl": "Polish", "cs": "Czech", "sk": "Slovak", "hu": "Hungarian", "ro": "Romanian",
    "el": "Greek", "ru": "Russian", "uk": "Ukrainian", "fi": "Finnish", "sv": "Swedish",
    "da": "Danish", "no": "Norwegian", "nb": "Norwegian", "bg": "Bulgarian", "hr": "Croatian",
    "sl": "Slovenian", "sr": "Serbian", "tr": "Turkish",
}


class AIError(Exception):
    pass


def is_unknown(value):
    return str(value or "").strip().lower() in UNKNOWN


class AI:
    def __init__(self, api_key, model_smart, model_fast):
        if not api_key:
            raise AIError("No Anthropic API key")
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key, max_retries=3, timeout=90)
        self.smart = model_smart
        self.fast = model_fast

    def _call(self, model, system, user, name, schema, max_tokens=1200):
        try:
            resp = self.client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}],
                tools=[{"name": name, "description": "Return the result.",
                        "input_schema": schema}],
                tool_choice={"type": "tool", "name": name},
            )
        except Exception as exc:
            raise AIError(_friendly(exc)) from exc
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        raise AIError("Claude returned no answer (stop reason: %s)" % resp.stop_reason)

    def test(self):
        out = self._call(self.fast, "Reply via the tool.", "Say ok.", "answer",
                         {"type": "object", "properties": {"ok": {"type": "string"}},
                          "required": ["ok"]}, 50)
        return bool(out)

    # ------------------------------------------------------------------ #
    def check_site(self, domain, title, text):
        schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["yes", "no", "maybe"]},
                "reason": {"type": "string", "description": "Max 12 words, plain English."},
            },
            "required": ["verdict", "reason"],
        }
        system = (
            "You help an SEO agency decide which websites to contact about publishing "
            "sponsored articles. 'yes' = the site publishes articles, news, blog posts or "
            "other editorial content (a media site, magazine, blog, portal, news site). "
            "'no' = it clearly does not (a shop, a company brochure site with no articles, "
            "a parked/for-sale domain, an error page, a government site, a social network). "
            "'maybe' = unclear. Judge only from the text given.")
        user = "Website: %s\nTitle: %s\n\nText from the homepage:\n%s" % (
            domain, title, (text or "")[:5000])
        return self._call(self.fast, system, user, "verdict", schema, 200)

    def translate(self, subject, body, language):
        name = LANG_NAMES.get(language, language)
        key = "tr_" + hashlib.sha1(("%s|%s|%s" % (language, subject, body)).encode()).hexdigest()
        cached = db.get_settings().get(key)
        if cached:
            return cached
        schema = {"type": "object",
                  "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
                  "required": ["subject", "body"]}
        system = ("Translate this business email into natural, polite %s as a native "
                  "speaker would write it. Keep {domain} placeholders exactly as they are, "
                  "keep the numbered list and line breaks." % name)
        out = self._call(self.smart, system, "Subject: %s\n\n%s" % (subject, body),
                         "translation", schema, 1500)
        db.save_settings({key: out})
        return out

    def extract(self, thread_text):
        props = {
            "price": "Standard sponsored article / guest post price in EUR, number only (convert other currencies). 'Unknown' if not stated.",
            "special_price": "Price for casino/crypto/loan/adult content in EUR, number only, highest if several. 'Unknown' if not stated.",
            "casino": "'Yes', 'No' or 'Unknown' - do they accept casino/gambling content.",
            "loan": "'Yes', 'No' or 'Unknown' - loans/credit content.",
            "crypto": "'Yes', 'No' or 'Unknown' - crypto content.",
            "adult": "'Yes', 'No' or 'Unknown' - adult/dating content.",
            "sponsored_tag": "'Yes' if articles are marked sponsored/advertising/werbung/reklāma, 'No' if not marked, else 'Unknown'.",
            "link_insertion": "'Yes', 'No', a EUR price (number only), or 'Unknown' - links inserted into existing articles.",
            "requirements": "Short summary of other conditions (dofollow, link count, permanence, VAT, niche prices). 'None' if nothing.",
            "declined": "'Yes' if the publisher says they do not sell/publish sponsored content at all or asks not to be contacted, else 'No'.",
            "answer_elsewhere": "'Yes' if the publisher points to an attached price list / media kit / link instead of writing the answers, else 'No'.",
            "they_asked": "Questions the publisher asked us that need a reply, in one short line. Empty if none.",
            "language": "ISO 639-1 code of the language the publisher writes in.",
        }
        schema = {"type": "object",
                  "properties": {k: {"type": "string", "description": v} for k, v in props.items()},
                  "required": list(props)}
        system = (
            "You read an email thread between an SEO agency (marked US) and a website "
            "publisher (marked PUBLISHER), and extract the publisher's terms. Our first "
            "email asked for: sponsored article price, whether casino/crypto/loan/adult "
            "topics are accepted and their price, whether articles are marked sponsored, and "
            "link insertion. Only use what the PUBLISHER wrote - never take values from our "
            "own questions. If they reject 'the topics you listed' or say 'only legal/standard "
            "content', casino, crypto, loan and adult are 'No'. Later messages override earlier ones.")
        return self._call(self.smart, system, thread_text, "terms", schema, 1200)

    def followup(self, thread_text, missing, sender_name, language):
        schema = {"type": "object",
                  "properties": {"body": {"type": "string",
                                          "description": "The email body only, no subject."}},
                  "required": ["body"]}
        labels = {"price": "article price", "casino": "casino", "loan": "loans",
                  "crypto": "crypto", "adult": "adult topics",
                  "sponsored_tag": "whether articles are marked as sponsored",
                  "link_insertion": "link insertions into existing articles",
                  "special_price": "price for casino/crypto/loan/adult topics"}
        system = (
            "You write short, friendly follow-up emails for an SEO agency collecting "
            "publishing terms from website owners. Rules: answer any question they asked in "
            "a sentence if you can (we are an SEO agency placing articles for our clients; "
            "topics vary; we're collecting terms for our partner list). Then ask ONLY for the "
            "missing items. Never ask again about topics they already refused. Do not commit "
            "to buying anything. Under 80 words. No subject line. End with 'Best regards,' "
            "followed by a new line and the sender name. Write in %s." %
            LANG_NAMES.get(language or "en", "the publisher's language"))
        user = ("Sender name: %s\nStill missing: %s\n\nThread:\n%s" % (
            sender_name or "the team", ", ".join(labels.get(m, m) for m in missing), thread_text))
        out = self._call(self.smart, system, user, "email", schema, 800)
        body = (out.get("body") or "").strip()
        if not body or "<analysis" in body.lower():
            raise AIError("Follow-up draft was empty")
        return body


def _friendly(exc):
    text = str(exc)
    low = text.lower()
    if "authentication" in low or "401" in low or "invalid x-api-key" in low:
        return "The Anthropic API key was rejected - check it in Settings"
    if "not_found" in low and "model" in low:
        return "The AI model name in Settings doesn't exist"
    if "credit" in low or "billing" in low:
        return "Your Anthropic account is out of credit"
    if "rate" in low and "limit" in low:
        return "Anthropic rate limit hit - will retry"
    if "overloaded" in low or "529" in low:
        return "Claude is busy right now - will retry"
    if "connection" in low or "timeout" in low:
        return "Couldn't reach Anthropic - check the internet connection"
    return text[:160]


def format_thread(messages, limit=14000):
    """Oldest to newest, each labelled, newest kept when it's too long."""
    from answer_sources import strip_quoted_text

    parts = []
    for m in messages:
        if m["kind"] == "bounce":
            continue
        who = "US" if m["direction"] == "out" else "PUBLISHER"
        body = m["body"] or ""
        if m["direction"] == "in":
            body = strip_quoted_text(body).strip() or body
        parts.append("=== %s (%s) | Subject: %s ===\n%s" % (
            who, m.get("from_addr", ""), m.get("subject", ""), body.strip()[:6000]))
    out = []
    total = 0
    for part in reversed(parts):
        if total + len(part) > limit and out:
            break
        out.append(part)
        total += len(part)
    return "\n\n".join(reversed(out))


def missing_fields(site):
    return [f for f in ESSENTIAL if is_unknown(site.get(f))]
