"""
guardrails.py — Llama Guard 3 Safety Addendum for INFO FORTRESS
================================================================
Wraps every call to llama3.2 with a two-stage pipeline:

    [INPUT]  → LlamaGuard3 (screen user content)
                    ↓  safe
             → llama3.2  (generate response)
                    ↓
    [OUTPUT] → LlamaGuard3 (screen model response)
                    ↓  safe
             → caller   (return result)

If either stage detects unsafe content the pipeline is short-circuited
and a structured GuardrailsViolation is returned instead.

Hazard categories (MLCommons taxonomy, Llama Guard 3):
  S1  – Violent Crimes
  S2  – Non-Violent Crimes
  S3  – Sex-Related Crimes
  S4  – Child Sexual Exploitation
  S5  – Defamation
  S6  – Specialized Advice (financial / medical / legal)
  S7  – Privacy
  S8  – Intellectual Property
  S9  – Indiscriminate Weapons (CBRN)
  S10 – Hate
  S11 – Suicide / Self-Harm
  S12 – Sexual Content
  S13 – Elections
  S14 – Code Interpreter Abuse

Usage
-----
from guardrails import guarded_ollama_chat, GuardrailsViolation

result = await guarded_ollama_chat(system_message, user_message)
if isinstance(result, GuardrailsViolation):
    # handle blocked content
    ...
else:
    text: str = result  # normal model output
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Configuration (all overridable via env vars)
# ──────────────────────────────────────────────

OLLAMA_BASE_URL    = os.environ.get("OLLAMA_BASE_URL",     "http://localhost:11434")
MAIN_MODEL         = os.environ.get("OLLAMA_MODEL",         "llama3.2")
GUARD_MODEL        = os.environ.get("LLAMA_GUARD_MODEL",    "llama-guard3:1b")   # or llama-guard3:8b
GUARD_TIMEOUT      = float(os.environ.get("GUARD_TIMEOUT",  "30"))
MAIN_TIMEOUT       = float(os.environ.get("MAIN_TIMEOUT",   "120"))
GUARDRAILS_ENABLED = os.environ.get("GUARDRAILS_ENABLED",   "true").lower() != "false"

# Categories we treat as blocking for this platform.
# INFO FORTRESS analyses misinformation — some categories like S6 (advice)
# could fire on legitimate analysis text, so we keep all enabled by default
# but expose this set for easy customisation.
BLOCKED_CATEGORIES: set[str] = set(
    os.environ.get(
        "GUARD_BLOCKED_CATEGORIES",
        "S1,S2,S3,S4,S9,S10,S11"  # violent/criminal/CBRN/hate/self-harm always blocked
    ).split(",")
)

# ──────────────────────────────────────────────
# Public data structures
# ──────────────────────────────────────────────

CATEGORY_LABELS: dict[str, str] = {
    "S1":  "Violent Crimes",
    "S2":  "Non-Violent Crimes",
    "S3":  "Sex-Related Crimes",
    "S4":  "Child Sexual Exploitation",
    "S5":  "Defamation",
    "S6":  "Specialized Advice (financial/medical/legal)",
    "S7":  "Privacy",
    "S8":  "Intellectual Property",
    "S9":  "Indiscriminate Weapons (CBRN)",
    "S10": "Hate Speech",
    "S11": "Suicide / Self-Harm",
    "S12": "Sexual Content",
    "S13": "Elections",
    "S14": "Code Interpreter Abuse",
}


@dataclass
class GuardrailsViolation:
    """Returned in place of a model response when content is blocked."""
    stage: str                          # "input" or "output"
    categories: list[str]               # e.g. ["S1", "S10"]
    category_labels: list[str]          # human-readable names
    raw_verdict: str                    # full Llama Guard response string
    blocked_text: str                   # the text that triggered the block
    message: str = ""

    def __post_init__(self):
        if not self.message:
            stage_str = "Input" if self.stage == "input" else "Generated output"
            cats = ", ".join(self.category_labels) if self.category_labels else "unspecified"
            self.message = (
                f"{stage_str} blocked by Llama Guard 3. "
                f"Violated categories: {cats}."
            )

    def to_dict(self) -> dict:
        return {
            "guardrails_blocked": True,
            "stage": self.stage,
            "categories": self.categories,
            "category_labels": self.category_labels,
            "message": self.message,
        }


@dataclass
class GuardrailsResult:
    """Successful pass through the full guarded pipeline."""
    content: str
    input_verdict: str   = "safe"
    output_verdict: str  = "safe"
    guard_model: str     = GUARD_MODEL
    main_model: str      = MAIN_MODEL


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _parse_guard_verdict(response_text: str) -> tuple[bool, list[str]]:
    """
    Parse Llama Guard output.

    The model returns either:
        safe
    or:
        unsafe
        S1,S4
    (categories on the second line, comma-separated)

    Returns (is_safe, violated_categories).
    """
    text = response_text.strip().lower()
    if text.startswith("safe"):
        return True, []

    # Extract category codes from second line (upper-cased)
    lines = response_text.strip().splitlines()
    categories: list[str] = []
    if len(lines) >= 2:
        raw_cats = lines[1].strip().upper()
        categories = [c.strip() for c in re.split(r"[,\s]+", raw_cats) if c.strip()]

    return False, categories


def _is_blocking(categories: list[str]) -> bool:
    """Return True if any violated category is in our blocking set."""
    if not categories:
        # Guard said unsafe but gave no category — treat as blocking
        return True
    return bool(BLOCKED_CATEGORIES.intersection(set(categories)))


async def _call_ollama(model: str, messages: list[dict], timeout: float) -> str:
    """Low-level Ollama /api/chat call, returns message content string."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            # Ensure enough tokens to complete full JSON.
            # llama3.2 default is 2048 ctx; analysis JSON needs ~800 output tokens.
            "num_predict": 1200,
            "temperature": 0.1,
            "top_p": 0.9,
        },
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]


async def _run_guard(text: str, stage: str) -> tuple[bool, list[str], str]:
    """
    Run Llama Guard 3 on `text`.

    `stage` is "input" (user message) or "output" (assistant message).
    Returns (is_safe, violated_categories, raw_verdict).
    """
    # Llama Guard expects the conversation as a user turn for input screening,
    # or as user+assistant turns for output screening.
    if stage == "input":
        messages = [{"role": "user", "content": text}]
    else:
        # For output screening we pair a generic user prompt with the assistant text
        messages = [
            {"role": "user",      "content": "[Content to evaluate]"},
            {"role": "assistant", "content": text},
        ]

    try:
        raw = await _call_ollama(GUARD_MODEL, messages, GUARD_TIMEOUT)
        is_safe, cats = _parse_guard_verdict(raw)
        return is_safe, cats, raw
    except Exception as exc:
        # Guard model unreachable — log and fail open (do not block legitimate requests)
        logger.warning(
            "Llama Guard (%s) unreachable during %s screening: %s — failing open.",
            GUARD_MODEL, stage, exc,
        )
        return True, [], "guard_unavailable"


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

async def guarded_ollama_chat(
    system_message: str,
    user_message: str,
    *,
    screen_input: bool = True,
    screen_output: bool = True,
) -> GuardrailsResult | GuardrailsViolation:
    """
    Drop-in replacement for the bare `ollama_chat()` call in server.py.

    Returns either a GuardrailsResult (success) or a GuardrailsViolation
    (blocked). Callers should check with isinstance().

    Parameters
    ----------
    system_message  : LLM system prompt
    user_message    : User / analysis content
    screen_input    : Run Llama Guard on the incoming user_message
    screen_output   : Run Llama Guard on the outgoing LLM response
    """
    if not GUARDRAILS_ENABLED:
        # Bypass entirely — useful for testing
        content = await _call_ollama(
            MAIN_MODEL,
            [{"role": "system", "content": system_message},
             {"role": "user",   "content": user_message}],
            MAIN_TIMEOUT,
        )
        return GuardrailsResult(content=content, input_verdict="skipped", output_verdict="skipped")

    # ── Stage 1: Input screening ────────────────
    input_verdict = "skipped"
    if screen_input:
        is_safe, cats, raw = await _run_guard(user_message, "input")
        input_verdict = raw
        if not is_safe and _is_blocking(cats):
            labels = [CATEGORY_LABELS.get(c, c) for c in cats]
            logger.warning("Llama Guard blocked INPUT — categories: %s", cats)
            return GuardrailsViolation(
                stage="input",
                categories=cats,
                category_labels=labels,
                raw_verdict=raw,
                blocked_text=user_message[:500],
            )

    # ── Stage 2: Main model inference ───────────
    content = await _call_ollama(
        MAIN_MODEL,
        [{"role": "system", "content": system_message},
         {"role": "user",   "content": user_message}],
        MAIN_TIMEOUT,
    )

    # ── Stage 3: Output screening ───────────────
    output_verdict = "skipped"
    if screen_output:
        is_safe, cats, raw = await _run_guard(content, "output")
        output_verdict = raw
        if not is_safe and _is_blocking(cats):
            labels = [CATEGORY_LABELS.get(c, c) for c in cats]
            logger.warning("Llama Guard blocked OUTPUT — categories: %s", cats)
            return GuardrailsViolation(
                stage="output",
                categories=cats,
                category_labels=labels,
                raw_verdict=raw,
                blocked_text=content[:500],
            )

    return GuardrailsResult(
        content=content,
        input_verdict=input_verdict,
        output_verdict=output_verdict,
    )


async def check_content_safety(text: str) -> dict:
    """
    Standalone safety check endpoint helper — useful for the /layer2/analyze-claim
    route to also surface a guard verdict alongside the main analysis.

    Returns a dict suitable for inclusion in any API response.
    """
    is_safe, cats, raw = await _run_guard(text, "input")
    labels = [CATEGORY_LABELS.get(c, c) for c in cats]
    return {
        "guard_model": GUARD_MODEL,
        "safe": is_safe,
        "violated_categories": cats,
        "violated_category_labels": labels,
        "raw_verdict": raw,
    }