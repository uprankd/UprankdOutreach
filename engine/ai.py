"""AI calls - Claude, OpenAI or Gemini, whichever has a key in Settings.

Every answer comes back as JSON matching a schema, so there is no free text and
nothing like a hidden <analysis> can leak into an email."""

import hashlib
import json
import time

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


PROVIDERS = {
    "anthropic": {"name": "Claude", "key": "anthropic_key"},
    "openai": {"name": "OpenAI", "key": "openai_key"},
    "gemini": {"name": "Gemini", "key": "gemini_key"},
}


def make(cfg):
    """The AI for the provider chosen in Settings, or None without a key."""
    provider = cfg.get("ai_provider") or "anthropic"
    if provider not in PROVIDERS:
        provider = "anthropic"
    key = cfg.get(PROVIDERS[provider]["key"])
    if not key:
        return None
    return AI(provider, key, cfg.get(provider + "_smart") or cfg.get("model_smart"),
              cfg.get(provider + "_fast") or cfg.get("model_fast"))


def _strict(schema):
    """OpenAI strict mode: every object closed, every property required."""
    schema = dict(schema)
    if schema.get("type") == "object":
        props = {k: _strict(v) for k, v in schema.get("properties", {}).items()}
        schema.update(properties=props, required=list(props), additionalProperties=False)
    return schema


def _openapi(schema):
    """Gemini's older responseSchema dialect: upper-case types, no extras."""
    out = {"type": schema.get("type", "string").upper()}
    for key in ("description", "enum"):
        if key in schema:
            out[key] = schema[key]
    if schema.get("type") == "object":
        out["properties"] = {k: _openapi(v) for k, v in schema.get("properties", {}).items()}
        out["required"] = list(schema.get("required") or out["properties"])
    return out


class AI:
    """One interface over Claude, OpenAI and Gemini. Every answer is JSON that
    matches a schema - no free text, nothing leaking into emails."""

    def __init__(self, provider, api_key, model_smart, model_fast):
        if not api_key:
            raise AIError("No API key for %s" % PROVIDERS.get(provider, {}).get("name", provider))
        self.provider = provider
        self.key = api_key.strip()
        self.smart = model_smart
        self.fast = model_fast
        self.client = None
        if provider == "anthropic":
            from anthropic import Anthropic

            self.client = Anthropic(api_key=self.key, max_retries=3, timeout=90)

    def _call(self, model, system, user, name, schema, max_tokens=1200):
        try:
            if self.provider == "openai":
                return self._openai(model, system, user, name, schema, max_tokens)
            if self.provider == "gemini":
                return self._gemini(model, system, user, schema, max_tokens)
            return self._claude(model, system, user, name, schema, max_tokens)
        except AIError:
            raise
        except Exception as exc:
            raise AIError(_friendly(exc, self.provider)) from exc

    # -- Claude: a forced tool call ---------------------------------------
    def _claude(self, model, system, user, name, schema, max_tokens):
        resp = self.client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{"name": name, "description": "Return the result.", "input_schema": schema}],
            tool_choice={"type": "tool", "name": name},
        )
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        raise AIError("Claude returned no answer (stop reason: %s)" % resp.stop_reason)

    # -- OpenAI: Chat Completions with a strict JSON schema ---------------
    def _openai(self, model, system, user, name, schema, max_tokens):
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": name, "strict": True, "schema": _strict(schema)}},
            "max_completion_tokens": max(max_tokens, 2000),
        }
        data = _post("https://api.openai.com/v1/chat/completions", body,
                     {"Authorization": "Bearer " + self.key}, "openai")
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        if msg.get("refusal"):
            raise AIError("OpenAI declined: %s" % msg["refusal"][:120])
        return _json(msg.get("content"), "OpenAI", choice.get("finish_reason"))

    # -- Gemini: generateContent with a JSON schema -----------------------
    def _gemini(self, model, system, user, schema, max_tokens):
        url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model
        base = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
        }
        configs = (
            {"responseMimeType": "application/json", "responseJsonSchema": schema},
            {"responseMimeType": "application/json", "responseSchema": _openapi(schema)},
        )
        last = None
        for extra in configs:
            body = dict(base, generationConfig=dict(extra, maxOutputTokens=max(max_tokens, 2000)))
            try:
                data = _post(url, body, {"x-goog-api-key": self.key}, "gemini")
            except _BadRequest as exc:          # older dialect - try the next form
                last = exc
                continue
            cand = (data.get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", [])
                           if not p.get("thought"))
            return _json(text, "Gemini", cand.get("finishReason"))
        raise AIError(_friendly(last, "gemini"))

    def test(self):
        out = self._call(self.fast, "Answer in the requested format.", "Say ok.", "answer",
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


class _BadRequest(Exception):
    pass


def _post(url, body, headers, provider):
    """POST JSON with a couple of retries on rate limits and busy servers."""
    import requests

    for attempt in range(3):
        r = requests.post(url, json=body, headers=dict(headers, **{"Content-Type": "application/json"}),
                          timeout=90)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(4 * (attempt + 1))
            continue
        try:
            detail = r.json().get("error", {})
            msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        except ValueError:
            msg = r.text[:200]
        text = "HTTP %d: %s" % (r.status_code, msg or "")
        if r.status_code == 400 and provider == "gemini" and "schema" in (msg or "").lower():
            raise _BadRequest(text)
        raise RuntimeError(text)
    raise RuntimeError("no answer")


def _json(text, who, finish):
    if not text:
        raise AIError("%s returned no answer (%s)" % (who, finish or "empty"))
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        return json.loads(text)
    except ValueError:
        if str(finish).lower() in ("length", "max_tokens"):
            raise AIError("%s's answer was cut off - try again" % who)
        raise AIError("%s returned something that isn't valid JSON" % who)


def _friendly(exc, provider="anthropic"):
    name = PROVIDERS.get(provider, {}).get("name", "The AI")
    text = str(exc)
    low = text.lower()
    if any(k in low for k in ("authentication", "401", "invalid x-api-key", "incorrect api key",
                              "api key not valid", "api_key_invalid", "permission_denied", "403")):
        return "The %s API key was rejected - check it in Settings" % name
    if ("not_found" in low or "404" in low or "does not exist" in low) and "model" in low:
        return "The %s model name in Settings doesn't exist" % name
    if any(k in low for k in ("credit", "billing", "insufficient_quota", "quota")):
        return "Your %s account is out of credit or quota" % name
    if "rate" in low and "limit" in low or "429" in low:
        return "%s rate limit hit - will retry" % name
    if any(k in low for k in ("overloaded", "529", "503", "unavailable")):
        return "%s is busy right now - will retry" % name
    if "connection" in low or "timeout" in low or "timed out" in low:
        return "Couldn't reach %s - check the internet connection" % name
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
