"""LLM wrapper — Gemini free tier as primary, Groq as backup, Ollama for local dev.

Both providers are free-tier. This module wraps them behind a single `call_llm()` function
so the rest of the pipeline can be provider-agnostic. If we ever swap to Claude API or another
paid provider, only this file changes.

Free tier limits (as of 2026-07):
- Gemini 2.0 Pro:     2 RPM,  50 RPD,   32K tokens/min
- Gemini 2.0 Flash:  15 RPM, 1500 RPD,  1M tokens/min
- Groq Llama 3.3 70B: 30 RPM, ~14400 RPD

Rate limit handling: on 429 or "quota" errors, we back off exponentially up to 3 attempts.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai
from groq import Groq


@dataclass
class LLMResult:
    """Uniform return type across providers."""
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    cost_usd: float = 0.0  # always $0 on free tier


def _init_gemini() -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    genai.configure(api_key=key)


def _init_groq() -> Groq:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    return Groq(api_key=key)


def call_gemini(
    prompt: str,
    model: str = "gemini-2.0-pro-exp",
    system: str = "",
    max_tokens: int = 8000,
    temperature: float = 0.7,
) -> LLMResult:
    """Call Gemini free tier. Handles rate limits with exponential backoff."""
    _init_gemini()
    generation_config = {
        "max_output_tokens": max_tokens,
        "temperature": temperature,
    }
    m = genai.GenerativeModel(
        model_name=model,
        system_instruction=system or None,
        generation_config=generation_config,
    )
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            resp = m.generate_content(prompt)
            return LLMResult(
                text=resp.text,
                tokens_in=resp.usage_metadata.prompt_token_count,
                tokens_out=resp.usage_metadata.candidates_token_count,
                model=model,
            )
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "429" in msg or "quota" in msg or "rate" in msg:
                wait = 60 * (attempt + 1)
                print(f"[llm] Gemini rate-limited (attempt {attempt+1}/3), sleeping {wait}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Gemini failed after 3 attempts: {last_err}")


def call_groq(
    prompt: str,
    model: str = "llama-3.3-70b-versatile",
    system: str = "",
    max_tokens: int = 4000,
    temperature: float = 0.7,
) -> LLMResult:
    """Groq free tier — fast, generous limits, ideal for variants and short outputs."""
    client = _init_groq()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return LLMResult(
        text=resp.choices[0].message.content or "",
        tokens_in=resp.usage.prompt_tokens,
        tokens_out=resp.usage.completion_tokens,
        model=model,
    )


def call_llm(
    prompt: str,
    model: str,
    system: str = "",
    max_tokens: int = 8000,
    temperature: float = 0.7,
) -> LLMResult:
    """Route to correct provider based on model name prefix.

    Model naming:
      gemini-*   → Google Gemini
      groq-*     → Groq Cloud (strip prefix before sending)
      llama-*    → Groq (assumes Llama on Groq)
    """
    if model.startswith("gemini"):
        return call_gemini(prompt, model=model, system=system, max_tokens=max_tokens, temperature=temperature)
    if model.startswith("groq-"):
        actual = model.replace("groq-", "", 1)
        return call_groq(prompt, model=actual, system=system, max_tokens=max_tokens, temperature=temperature)
    if model.startswith("llama"):
        return call_groq(prompt, model=model, system=system, max_tokens=max_tokens, temperature=temperature)
    raise ValueError(f"Unknown model: {model}")


if __name__ == "__main__":
    # Smoke test — requires GEMINI_API_KEY and GROQ_API_KEY in env
    import sys

    if "--gemini" in sys.argv:
        r = call_gemini("Say hello in three words.", max_tokens=50)
        print(f"Gemini: {r.text!r} (in={r.tokens_in}, out={r.tokens_out})")
    if "--groq" in sys.argv:
        r = call_groq("Say hello in three words.", max_tokens=50)
        print(f"Groq: {r.text!r} (in={r.tokens_in}, out={r.tokens_out})")
    if not sys.argv[1:]:
        print("Usage: python llm.py [--gemini] [--groq]")
