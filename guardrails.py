"""
guardrails.py — Local Mistral Base + LoRA (Hardened Compare-Ready)
===================================================================
Fully local.
Supports:
- guarded_chat (LoRA)
- generate_with_model (base or LoRA)
- base_model
- lora_model

Improvements:
- Extract first valid schema JSON only
- Enforce indicator evidence must be literal substring
- Prevent hallucinated URL attribution
"""

import logging
import os
from dataclasses import dataclass
from typing import List, Dict, Any
import copy
import json

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

BASE_MODEL_PATH = os.environ.get("BASE_MODEL_PATH", "./mistral7b")
LORA_PATH = os.environ.get("LORA_PATH", "./info_lora")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ──────────────────────────────────────────────
# Load tokenizer
# ──────────────────────────────────────────────

print("Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH)

# ──────────────────────────────────────────────
# Load base model
# ──────────────────────────────────────────────

print("Loading Base Mistral...")
base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_PATH,
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    device_map="auto"
)
base_model.eval()
print("Base model ready.")

# ──────────────────────────────────────────────
# Load LoRA model
# ──────────────────────────────────────────────

print("Loading LoRA adapter...")
lora_model = PeftModel.from_pretrained(
    copy.deepcopy(base_model),
    LORA_PATH
)
lora_model.eval()
print("LoRA model ready.")

# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────

@dataclass
class GuardrailsViolation:
    stage: str
    categories: List[str]
    category_labels: List[str]
    raw_verdict: str
    blocked_text: str
    message: str = "Guardrails disabled."

    def to_dict(self):
        return {
            "guardrails_blocked": False,
            "message": "Guardrails disabled."
        }

@dataclass
class GuardrailsResult:
    content: str
    input_verdict: str = "skipped"
    output_verdict: str = "skipped"
    main_model: str = "local-mistral-lora"

# ──────────────────────────────────────────────
# Prompt Rendering
# ──────────────────────────────────────────────

def render_messages(messages):
    out = []
    for m in messages:
        role = m["role"].strip().lower()
        content = m["content"].strip()
        if role == "system":
            out.append(f"<<SYSTEM>>\n{content}\n<</SYSTEM>>")
        elif role == "user":
            out.append(f"<<USER>>\n{content}\n<</USER>>")
        elif role == "assistant":
            out.append(f"<<ASSISTANT>>\n{content}\n<</ASSISTANT>>")
    return "\n\n".join(out)

# ──────────────────────────────────────────────
# JSON Extraction + Enforcement
# ──────────────────────────────────────────────

REQUIRED_KEYS = {
    "risk_score",
    "veracity_assessment",
    "article_type",
    "confidence",
    "indicators",
    "org_guardrail",
    "summary"
}

def extract_first_valid_schema_json(text: str) -> Dict[str, Any]:
    """
    Extract first JSON object that matches required schema.
    Prevents helper blocks (e.g. url_check) from being accepted.
    """
    text = text.strip()
    n = len(text)

    for i in range(n):
        if text[i] != "{":
            continue
        for j in range(n, i, -1):
            if text[j - 1] != "}":
                continue
            candidate = text[i:j]
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict) and REQUIRED_KEYS.issubset(parsed.keys()):
                return parsed

    raise ValueError("No valid schema JSON found.")

def enforce_literal_evidence(obj: Dict[str, Any], input_text: str) -> Dict[str, Any]:
    """
    Enforces:
    - indicator evidence must be literal substring
    - no hallucinated URLs
    """
    indicators = obj.get("indicators", [])
    clean = []

    for ind in indicators:
        if not isinstance(ind, dict):
            continue
        evidence = ind.get("evidence", "")
        if not isinstance(evidence, str):
            continue
        evidence = evidence.strip()

        # Must be literal substring
        if evidence and evidence in input_text:
            clean.append({
                "name": ind.get("name", "Signal"),
                "evidence": evidence,
                "severity": ind.get("severity", "low")
            })

    # If nothing survived, downgrade
    if not clean:
        snippet = input_text.strip()
        if len(snippet) > 120:
            snippet = snippet[:120]
        clean = [{
            "name": "No Attribution",
            "evidence": snippet,
            "severity": "low"
        }]
        obj["risk_score"] = min(float(obj.get("risk_score", 50)), 35)

    obj["indicators"] = clean
    return obj

# ──────────────────────────────────────────────
# Generation Core
# ──────────────────────────────────────────────

def generate_with_model(model_instance, system_message: str, user_message: str) -> str:

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": ""},
    ]

    prompt = render_messages(messages) + "\n\n<<ASSISTANT>>\n"
    inputs = tokenizer(prompt, return_tensors="pt").to(model_instance.device)

    with torch.no_grad():
        outputs = model_instance.generate(
            **inputs,
            max_new_tokens=600,
            temperature=0.0,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
        )

    gen_ids = outputs[0][inputs["input_ids"].shape[-1]:]
    decoded = tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

    try:
        parsed = extract_first_valid_schema_json(decoded)
        parsed = enforce_literal_evidence(parsed, user_message)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception:
        # fallback safe
        return json.dumps({
            "risk_score": 50,
            "veracity_assessment": "uncertain",
            "article_type": "unknown",
            "confidence": 0.5,
            "indicators": [{
                "name": "Parse Failure",
                "evidence": user_message[:120],
                "severity": "low"
            }],
            "org_guardrail": {
                "sharing_policy": "caution",
                "reason": "Model returned invalid structured output.",
                "recommended_next_step": "Manual review required."
            },
            "summary": decoded[:500]
        }, ensure_ascii=False)

# ──────────────────────────────────────────────
# LoRA default path
# ──────────────────────────────────────────────

async def guarded_chat(system_message: str, user_message: str):
    content = generate_with_model(lora_model, system_message, user_message)
    return GuardrailsResult(content=content)

# Backwards compatibility
guarded_ollama_chat = guarded_chat

async def check_content_safety(text: str):
    return {
        "guard_model": None,
        "safe": True,
        "violated_categories": [],
        "violated_category_labels": [],
        "raw_verdict": "guardrails_disabled"
    }

GUARD_MODEL = None
MAIN_MODEL = "local-mistral-lora"

__all__ = [
    "guarded_chat",
    "generate_with_model",
    "base_model",
    "lora_model",
    "tokenizer",
]