"""
guardrails.py — Local Qwen Base + LoRA (Compare-Ready)
======================================================
Fully local.
Supports:
- guarded_chat (LoRA)
- generate_with_model (base or LoRA)
- base_model
- lora_model

Qwen changes:
- Uses AutoModelForCausalLM instead of AutoModelForSeq2SeqLM
- Loads LoRA onto a second Qwen base model
- Uses tokenizer.apply_chat_template(...) for chat formatting
- Keeps the same exported API expected by server.py
"""

import logging
import os
from dataclasses import dataclass
from typing import List
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

BASE_MODEL_PATH = os.environ.get("BASE_MODEL_PATH", "./qwen")
LORA_PATH = os.environ.get("LORA_PATH", "./qwen_guardrail_lora")

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

if torch.cuda.is_available():
    DEVICE = "cuda"
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"

if DEVICE in {"cuda", "mps"}:
    DTYPE = torch.float16
else:
    DTYPE = torch.float32


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _load_causal_model(path: str):
    """
    Load Qwen as a causal LM.
    """
    try:
        model = AutoModelForCausalLM.from_pretrained(
            path,
            torch_dtype=DTYPE,
            low_cpu_mem_usage=True,
        )
    except TypeError:
        model = AutoModelForCausalLM.from_pretrained(path)

    model = model.to(DEVICE)
    model.eval()
    return model


def _model_device(model_instance):
    return next(model_instance.parameters()).device


# ---------------------------------------------------------------------
# Load tokenizer
# ---------------------------------------------------------------------

print("Loading tokenizer...")
print("BASE_MODEL_PATH =", BASE_MODEL_PATH)
print("LORA_PATH =", LORA_PATH)
print("DEVICE =", DEVICE)

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token


# ---------------------------------------------------------------------
# Load base model
# ---------------------------------------------------------------------

print("Loading Base Qwen...")
base_model = _load_causal_model(BASE_MODEL_PATH)
print("Base model ready.")


# ---------------------------------------------------------------------
# Load LoRA model
# ---------------------------------------------------------------------

print("Loading LoRA adapter...")
lora_base_model = _load_causal_model(BASE_MODEL_PATH)
lora_model = PeftModel.from_pretrained(lora_base_model, LORA_PATH)
lora_model = lora_model.to(DEVICE)
lora_model.eval()
print("LoRA model ready.")


# ---------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------

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
    main_model: str = "local-qwen-guardrail-lora"


# ---------------------------------------------------------------------
# Generation Core
# ---------------------------------------------------------------------

def generate_with_model(model_instance, system_message: str, user_message: str) -> str:
    """
    Generate RAW model text from either base_model or lora_model.
    server.py is responsible for parsing/sanitizing the JSON.
    """
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message},
    ]

    prompt_text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(
        prompt_text,
        return_tensors="pt",
        truncation=True,
        max_length=2048,
    )

    model_device = _model_device(model_instance)
    inputs = {k: v.to(model_device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model_instance.generate(
            **inputs,
            max_new_tokens=384,
            do_sample=False,
            num_beams=1,
            repetition_penalty=1.05,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated = outputs[0][inputs["input_ids"].shape[-1]:]
    decoded = tokenizer.decode(generated, skip_special_tokens=True).strip()

    print("\n===== RAW MODEL OUTPUT =====")
    print(decoded[:2000])
    print("===== END RAW MODEL OUTPUT =====\n")

    return decoded


# ---------------------------------------------------------------------
# LoRA default path
# ---------------------------------------------------------------------

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
        "raw_verdict": "guardrails_disabled",
    }


GUARD_MODEL = None
MAIN_MODEL = "local-qwen-guardrail-lora"

__all__ = [
    "guarded_chat",
    "generate_with_model",
    "base_model",
    "lora_model",
    "tokenizer",
]