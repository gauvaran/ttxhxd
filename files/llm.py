"""
llm.py - LLM provider chain with model auto-discovery and per-run health stats.

Order is controlled by LLM_ORDER (default "groq,gemini,fallback"):
  groq     — GROQ_API_KEY; model from GROQ_MODEL or auto-picked from /models
  gemini   — GEMINI_API_KEY; GEMINI_MODEL (default gemini-flash-latest)
  fallback — any OpenAI-compatible endpoint (e.g. OpenRouter, a paid tier):
             FALLBACK_LLM_URL (…/chat/completions), FALLBACK_LLM_KEY, FALLBACK_LLM_MODEL

A provider that fails with an auth/permission/model error is disabled for the
rest of the run, so one dead key costs one request, not one per article.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; TTXHXDBot/1.0)"

GROQ_BASE = "https://api.groq.com/openai/v1"
# Preference order when GROQ_MODEL is not set; first one the key can see wins.
GROQ_PREFERRED = [
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct-0905",
    "moonshotai/kimi-k2-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
]
_NON_CHAT = ("whisper", "guard", "tts", "playai", "orpheus", "compound", "distil")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

STATS = {"ok": 0, "fail": 0, "by_provider": {}, "disabled": {}, "groq_model": ""}
_disabled = set()
_groq_candidates = None


def _log(msg):
    print(msg, file=sys.stderr)


def _http_json(url, payload=None, headers=None, timeout=45):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _disable(provider, reason):
    _disabled.add(provider)
    STATS["disabled"][provider] = reason[:160]
    _log(f"[llm] disabling {provider} for this run: {reason[:160]}")


def _clean(text):
    # Reasoning models (qwen3, deepseek-r1) may inline their chain of thought.
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


# ── Groq ──────────────────────────────────────────────────────────────────────
def _groq_models(key):
    """Ordered list of chat models to try: GROQ_MODEL first, then preferred ∩ available."""
    global _groq_candidates
    if _groq_candidates is not None:
        return _groq_candidates
    pinned = os.environ.get("GROQ_MODEL", "").strip()
    try:
        avail = [m["id"] for m in _http_json(f"{GROQ_BASE}/models",
                                             headers={"Authorization": f"Bearer {key}"},
                                             timeout=15).get("data", [])]
    except Exception as e:
        _log(f"[llm] groq /models failed ({e}); using static list")
        avail = []
    if avail:
        chat = [m for m in avail if not any(t in m.lower() for t in _NON_CHAT)]
        ordered = [m for m in GROQ_PREFERRED if m in chat] + sorted(m for m in chat if m not in GROQ_PREFERRED)
        _log(f"[llm] groq models available: {', '.join(sorted(chat))}")
    else:
        ordered = list(GROQ_PREFERRED)
    if pinned:
        ordered = [pinned] + [m for m in ordered if m != pinned]
    _groq_candidates = ordered
    return ordered


def _openai_compat(url, key, model, prompt, max_tokens, temperature, provider):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temperature}
    if "gpt-oss" in model:
        body["reasoning_effort"] = "low"
        body["max_tokens"] = max_tokens + 1024  # reasoning tokens count toward the budget
    for attempt in range(3):
        try:
            data = _http_json(url, body, headers={"Authorization": f"Bearer {key}"}, timeout=60)
            return _clean(data["choices"][0]["message"].get("content", ""))
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")[:300]
            if e.code == 429:
                wait = 15 * (attempt + 1)
                _log(f"[llm] {provider} 429 — wait {wait}s")
                time.sleep(wait)
                continue
            raise _ProviderError(e.code, msg)
        except Exception as e:
            _log(f"[llm] {provider} error: {e}")
            time.sleep(3)
    return ""


class _ProviderError(Exception):
    def __init__(self, code, msg):
        super().__init__(f"HTTP {code}: {msg}")
        self.code, self.msg = code, msg


def _groq(prompt, max_tokens, temperature):
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        return ""
    models = _groq_models(key)
    while models:
        model = models[0]
        try:
            out = _openai_compat(f"{GROQ_BASE}/chat/completions", key, model,
                                 prompt, max_tokens, temperature, f"groq:{model}")
            STATS["groq_model"] = model
            return out
        except _ProviderError as e:
            if e.code in (401, 403):
                _disable("groq", str(e))
                return ""
            if e.code in (400, 404) and ("model" in e.msg.lower()):
                _log(f"[llm] groq model {model} unusable ({e.code}); trying next")
                models.pop(0)
                continue
            _log(f"[llm] groq {e}")
            return ""
    _disable("groq", "no usable model")
    return ""


def _gemini(prompt, max_tokens, temperature):
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return ""
    model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"maxOutputTokens": max_tokens + 512, "temperature": temperature,
                                    "thinkingConfig": {"thinkingBudget": 512}}}
    for attempt in range(3):
        try:
            data = _http_json(f"{GEMINI_BASE}/{model}:generateContent?key={key}", payload)
            return _clean(data["candidates"][0]["content"]["parts"][0]["text"])
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")[:300]
            if e.code == 429:
                if "per day" in msg.lower() or "daily" in msg.lower():
                    _disable("gemini", "daily quota exhausted")
                    return ""
                time.sleep(15 * (attempt + 1))
                continue
            if e.code in (400, 401, 403, 404):
                _disable("gemini", f"HTTP {e.code}: {msg}")
            return ""
        except Exception as e:
            _log(f"[llm] gemini error: {e}")
            return ""
    return ""


def _fallback(prompt, max_tokens, temperature):
    url, key, model = (os.environ.get(k, "") for k in
                       ("FALLBACK_LLM_URL", "FALLBACK_LLM_KEY", "FALLBACK_LLM_MODEL"))
    if not (url and key and model):
        return ""
    try:
        return _openai_compat(url, key, model, prompt, max_tokens, temperature, "fallback")
    except _ProviderError as e:
        if e.code in (401, 402, 403, 404):
            _disable("fallback", str(e))
        return ""


_PROVIDERS = {"groq": _groq, "gemini": _gemini, "fallback": _fallback}


def available():
    """True if at least one provider is configured and not yet disabled."""
    env = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "fallback": "FALLBACK_LLM_KEY"}
    return any(os.environ.get(env[p]) and p not in _disabled for p in _order())


def _order():
    return [p.strip() for p in os.environ.get("LLM_ORDER", "groq,gemini,fallback").split(",")
            if p.strip() in _PROVIDERS]


def call(prompt, max_tokens=600, temperature=0.7):
    for name in _order():
        if name in _disabled:
            continue
        out = _PROVIDERS[name](prompt, max_tokens, temperature)
        if out:
            STATS["ok"] += 1
            STATS["by_provider"][name] = STATS["by_provider"].get(name, 0) + 1
            return out
    STATS["fail"] += 1
    return ""


def call_json(prompt, max_tokens=800, temperature=0.4):
    """Call and parse a JSON object/array from the reply (tolerates ```json fences)."""
    raw = call(prompt, max_tokens, temperature)
    if not raw:
        return None
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    text = m.group(1) if m else raw
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        return None
    try:
        return json.loads(text[start:text.rfind("]" if text[start] == "[" else "}") + 1])
    except Exception:
        _log(f"[llm] JSON parse failed: {raw[:200]}")
        return None
