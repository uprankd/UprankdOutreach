"""The three AI providers, against fake HTTP answers (no keys or network needed).

    python3 tests/test_ai.py
"""

import json
import os
import shutil
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="almo-ai-")
os.environ["ALMO_DATA_DIR"] = TMP
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

import requests  # noqa: E402

import ai  # noqa: E402
import db  # noqa: E402

CALLS = []


class Resp:
    def __init__(self, code, data):
        self.status_code, self._data, self.text = code, data, json.dumps(data)

    def json(self):
        return self._data


TERMS = {"price": "150", "special_price": "Unknown", "casino": "No", "loan": "No", "crypto": "No",
         "adult": "No", "sponsored_tag": "Yes", "link_insertion": "80", "requirements": "None",
         "declined": "No", "answer_elsewhere": "No", "they_asked": "", "language": "lv"}


def fake_post(url, json=None, headers=None, timeout=None):
    CALLS.append((url, json, headers))
    if "openai.com" in url:
        if headers.get("Authorization") != "Bearer sk-good":
            return Resp(401, {"error": {"message": "Incorrect API key provided"}})
        return Resp(200, {"choices": [{"finish_reason": "stop", "message": {"content": _dumps(TERMS)}}]})
    if "generativelanguage" in url:
        if headers.get("x-goog-api-key") != "AIza-good":
            return Resp(400, {"error": {"message": "API key not valid. Please pass a valid API key."}})
        if "responseJsonSchema" in json["generationConfig"] and "old-model" in url:
            return Resp(400, {"error": {"message": "Invalid JSON payload: unknown field responseJsonSchema in schema"}})
        return Resp(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": _dumps(TERMS)}]}}]})
    raise AssertionError(url)


def _dumps(d):
    return json_module.dumps(d)


json_module = __import__("json")
requests.post = fake_post


def check(cond, label):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        raise SystemExit(1)


def main():
    db.init()
    check(ai.make({"ai_provider": "openai"}) is None, "no key -> no AI (Almo still runs)")

    o = ai.make({"ai_provider": "openai", "openai_key": "sk-good", "openai_smart": "gpt-x", "openai_fast": "gpt-y"})
    out = o.extract("=== PUBLISHER ===\nCena 150")
    url, body, _ = CALLS[-1]
    fmt = body["response_format"]["json_schema"]
    check(out["price"] == "150" and "chat/completions" in url and body["model"] == "gpt-x",
          "OpenAI: terms extracted with the reply model")
    check(fmt["strict"] and fmt["schema"]["additionalProperties"] is False
          and set(fmt["schema"]["required"]) == set(fmt["schema"]["properties"]),
          "OpenAI: strict JSON schema (closed, all fields required)")
    o.check_site("x.lv", "X", "news")
    check(CALLS[-1][1]["model"] == "gpt-y", "OpenAI: site checks use the fast model")

    g = ai.make({"ai_provider": "gemini", "gemini_key": "AIza-good", "gemini_smart": "gem-a", "gemini_fast": "gem-b"})
    out = g.extract("thread")
    url, body, headers = CALLS[-1]
    check(out["link_insertion"] == "80" and "gem-a:generateContent" in url
          and body["generationConfig"]["responseJsonSchema"]["type"] == "object",
          "Gemini: terms extracted via generateContent + JSON schema")
    g2 = ai.AI("gemini", "AIza-good", "old-model", "old-model")
    n = len(CALLS)
    out = g2.extract("thread")
    check(out["price"] == "150" and len(CALLS) == n + 2
          and CALLS[-1][1]["generationConfig"]["responseSchema"]["type"] == "OBJECT",
          "Gemini: falls back to the older responseSchema form")

    for provider, key, word in (("openai", "sk-bad", "OpenAI"), ("gemini", "AIza-bad", "Gemini")):
        try:
            ai.make({"ai_provider": provider, provider + "_key": key, provider + "_smart": "m",
                     provider + "_fast": "m"}).test()
            check(False, "%s bad key" % provider)
        except ai.AIError as exc:
            check("%s API key was rejected" % word in str(exc), "%s: bad key -> plain message" % word)

    check(ai._json('```json\n{"a": 1}\n```', "X", "stop") == {"a": 1}, "JSON in a code fence is read")
    print("\nAll checks passed.")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
