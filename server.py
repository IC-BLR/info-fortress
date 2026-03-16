"""
server.py — INFO FORTRESS API (Compare-only)
===========================================
Backend: Local Mistral Base + LoRA (no guard model).
Provides ONLY one endpoint: POST /api/compare

Key upgrades vs your current compare:
- Extracts the *first valid schema JSON* (not "first { .. last }")
- Hard schema validation
- Enforces: indicator evidence MUST be exact substring of input content
- Removes hallucinated URL/domain attribution unless it appears in input
"""

from fastapi import FastAPI, APIRouter, HTTPException
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import json

# ── Local models (your existing guardrails.py) ────────────────────────────────
from guardrails import (
    generate_with_model,
    base_model,
    lora_model,
)

# ── Prompt (use your strict unified system prompt) ───────────────────────────
UNIFIED_SYSTEM_PROMPT = r"""
You are an information integrity analyst.

Return ONLY valid JSON with this schema:

{
  "risk_score": <0-100>,
  "veracity_assessment": "likely_true|uncertain|likely_false|satire|opinion",
  "article_type": "conspiracy_theory|analysis|rhetorical|breaking_news|satire|unknown",
  "confidence": <0-1>,
  "indicators": [
    {"name": "<short label>", "evidence": "<exact phrase from input>", "severity": "<low|med|high>"}
  ],
  "org_guardrail": {
    "sharing_policy": "<allow|caution|do_not_share>",
    "reason": "<one sentence>",
    "recommended_next_step": "<what to verify / do next>"
  },
  "summary": "<2-3 sentences. Must mention strongest indicator and evidence (exact quote).>"
}
NOTE ABOUT URLS: If the user's input contains a URL (http:// or https://), treat the URL as a valid attribution cue. If the URL's domain matches a known mainstream outlet in the input (e.g., straitstimes.com, mas.gov.sg, ndtv.com), record an indicator "Authority Referenced" whose evidence may be either the exact outlet name found in the input OR the exact URL substring. Do NOT invent the mapping; only use domains actually present in the input text or provided by preprocessing. If the URL is present but the claim shows hedging words like "alleged", "reportedly", "sources say", prefer "No Attribution" or "Authority Referenced" with lower severity based on hedging.
Rules:
- If input mentions a named mainstream outlet (e.g. "Straits Times", "NDTV", "MAS", "MOH") treat that as authority attribution unless the claim text itself shows uncertainty (words like "alleged" or "reportedly").
- indicators.evidence must be an exact substring from the input.
- Do not invent sources or claim web verification.
- Use your best judgment to assess manipulation/deception risk.
- Indicators must be manipulation/deception signals, not content facts.
Disallowed: policy measures, country actions, economic impacts, quotes of normal reporting.
Allowed: urgency framing, call-to-share, anonymous sourcing, conspiracy framing, absolutist claims, time pressure, lack of attribution, implausibility, safety guidance abuse, impersonation/scam cues.

HARD BAN:
- Do NOT add any keys beyond the schema.
- Do NOT generate or infer URLs/domains. Only quote URLs if they appear literally in the claim text.
- Never output helper blocks like "url_check", "claim_check", "sources", "references".
""".strip()

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="INFO FORTRESS - Compare Only")
api_router = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    content: str = Field(..., min_length=1)

class CompareResponse(BaseModel):
    base_output: Dict[str, Any]
    lora_output: Dict[str, Any]
    comparison_metrics: Dict[str, Any]
    base_raw: Optional[str] = None
    lora_raw: Optional[str] = None

# ─────────────────────────────────────────────────────────────────────────────
# JSON extraction + validation (THE FIX)
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_TOP_KEYS = {
    "risk_score", "veracity_assessment", "article_type", "confidence",
    "indicators", "org_guardrail", "summary"
}
REQUIRED_GUARD_KEYS = {"sharing_policy", "reason", "recommended_next_step"}

def extract_first_valid_schema_json(decoded: str) -> str:
    """
    Finds the first JSON object in `decoded` that matches the expected schema shape.
    This prevents "url_check" JSON blocks and other helper JSON from being extracted.
    """
    decoded = decoded.strip()
    n = len(decoded)
    for i in range(n):
        if decoded[i] != "{":
            continue
        for j in range(n, i, -1):
            if decoded[j - 1] != "}":
                continue
            candidate = decoded[i:j]
            try:
                obj = json.loads(candidate)
            except Exception:
                continue
            if isinstance(obj, dict) and REQUIRED_TOP_KEYS.issubset(obj.keys()):
                return candidate
    raise ValueError("No valid schema JSON found in model output.")

def coerce_float(x: Any, default: float) -> float:
    try:
        return float(x)
    except Exception:
        return default

def coerce_int(x: Any, default: int) -> int:
    try:
        v = int(float(x))
        return v
    except Exception:
        return default

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def sanitize_to_schema(obj: Dict[str, Any], input_text: str) -> Dict[str, Any]:
    """
    Enforces schema + the critical rule:
    - every indicator.evidence MUST be an exact substring of the user input.
    - removes hallucinated attribution (urls/domains) unless present in input.
    """
    # ---- hard schema defaults
    out: Dict[str, Any] = {
        "risk_score": clamp(coerce_float(obj.get("risk_score", 50), 50), 0, 100),
        "veracity_assessment": obj.get("veracity_assessment", "uncertain"),
        "article_type": obj.get("article_type", "unknown"),
        "confidence": clamp(coerce_float(obj.get("confidence", 0.5), 0.5), 0, 1),
        "indicators": [],
        "org_guardrail": {
            "sharing_policy": "caution",
            "reason": "Insufficient structured evidence to fully validate; treat with care.",
            "recommended_next_step": "Check for primary sources or official statements linked in the input."
        },
        "summary": str(obj.get("summary", ""))[:600],
    }

    # ---- guardrail object
    og = obj.get("org_guardrail") if isinstance(obj.get("org_guardrail"), dict) else {}
    if REQUIRED_GUARD_KEYS.issubset(set(og.keys())):
        out["org_guardrail"] = {
            "sharing_policy": str(og.get("sharing_policy", "caution")),
            "reason": str(og.get("reason", ""))[:240],
            "recommended_next_step": str(og.get("recommended_next_step", ""))[:240],
        }

    # ---- indicators: enforce substring evidence
    inds = obj.get("indicators", [])
    clean_inds: List[Dict[str, str]] = []
    if isinstance(inds, list):
        for ind in inds:
            if not isinstance(ind, dict):
                continue
            name = str(ind.get("name", "")).strip()[:60]
            evidence = ind.get("evidence", "")
            severity = str(ind.get("severity", "low")).strip().lower()
            if severity not in {"low", "med", "high"}:
                severity = "low"
            if not isinstance(evidence, str):
                continue
            evidence = evidence.strip()
            if not evidence:
                continue
            # CRITICAL: must be exact substring from input
            if evidence in input_text:
                clean_inds.append({"name": name or "Signal", "evidence": evidence, "severity": severity})

    # If model produced none, add a safe minimum indicator with exact substring
    if not clean_inds:
        snippet = input_text.strip()
        if len(snippet) > 140:
            snippet = snippet[:140]
        # keep it EXACT substring: the snippet is taken directly from input_text
        clean_inds = [{"name": "No Attribution", "evidence": snippet, "severity": "low"}]
        # Also downgrade risk to avoid "high risk with no indicators"
        out["risk_score"] = min(out["risk_score"], 35)

    out["indicators"] = clean_inds

    # ---- if summary mentions evidence, it must be exact quote; we can't reliably enforce,
    # but we can keep it short and not "invent". If empty, generate minimal summary from strongest indicator.
    if not out["summary"].strip():
        top = out["indicators"][0]
        out["summary"] = (
            f"Strongest indicator: {top['name']} with evidence \"{top['evidence']}\". "
            "Assess sharing based on whether the claim provides verifiable attribution and avoids manipulation cues."
        )

    return out

def run_model(model_instance, system_prompt: str, content: str) -> Dict[str, Any]:
    """
    Calls your local generator and returns a sanitized schema JSON dict.
    """
    raw = generate_with_model(model_instance, system_prompt, content)

    # 1) Extract correct schema JSON (avoid helper JSON blocks)
    try:
        schema_json_text = extract_first_valid_schema_json(raw)
        parsed = json.loads(schema_json_text)
    except Exception:
        # fallback: attempt naive parse; will still be sanitized
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}

    # 2) Enforce schema + evidence substring rule
    sanitized = sanitize_to_schema(parsed if isinstance(parsed, dict) else {}, content)
    return {"raw": raw, "sanitized": sanitized}

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: compare
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default
    
def indicators_list(ind_obj):
    """Normalize indicators list from sanitized object."""
    if not ind_obj or not isinstance(ind_obj, list):
        return []
    out = []
    for it in ind_obj:
        if isinstance(it, dict):
            name = it.get("name", "").strip()
            evidence = it.get("evidence", "").strip()
            severity = it.get("severity", "").strip().lower()
            out.append({"name": name, "evidence": evidence, "severity": severity})
    return out
 
def indicator_evidence_set(inds):
    """Return set of exact evidence strings for comparison (sanitized ensures exact substrings)."""
    return set(it["evidence"] for it in inds if it.get("evidence"))

def detect_authority_evidence(indicators, content):
    """
    Very small provenance check:
    - sees if any indicator evidence contains a known domain-like token or exact substring that
      also exists in the original input content. (Sanitizer ensures evidence must be substring.)
    Returns list of evidences that look like authority presence.
    """
    out = []
    for it in indicators:
        ev = it.get("evidence", "")
        # treat evidence as authority if it contains 'http' or common outlet tokens or uppercase id tokens
        if "http://" in ev or "https://" in ev or any(tok in ev.lower() for tok in ["str/straitstimes", "straitstimes", "ndtv", "mas", "moh", "times of india", "toi", "bbc", "reuters", ".com"]):
            if ev in content:
                out.append(ev)
    return out

def compute_comparison_metrics(base_s, lora_s, content):
    """
    Input: sanitized base & lora dicts and original content string.
    Returns a dictionary of comparison metrics.
    """
    metrics = {}
 
    # numeric deltas
    base_risk = safe_float(base_s.get("risk_score", 0.0), 0.0)
    lora_risk = safe_float(lora_s.get("risk_score", 0.0), 0.0)
    metrics["risk_delta"] = round(lora_risk - base_risk, 1)
    metrics["base_risk"] = round(base_risk, 1)
    metrics["lora_risk"] = round(lora_risk, 1)
 
    base_conf = safe_float(base_s.get("confidence", 0.0), 0.0)
    lora_conf = safe_float(lora_s.get("confidence", 0.0), 0.0)
    metrics["confidence_delta"] = round(lora_conf - base_conf, 3)
    metrics["base_confidence"] = round(base_conf, 3)
    metrics["lora_confidence"] = round(lora_conf, 3)
 
    # indicators
    base_inds = indicators_list(base_s.get("indicators", []))
    lora_inds = indicators_list(lora_s.get("indicators", []))
    base_set = indicator_evidence_set(base_inds)
    lora_set = indicator_evidence_set(lora_inds)
 
    shared = base_set.intersection(lora_set)
    added = lora_set.difference(base_set)
    removed = base_set.difference(lora_set)
 
    metrics["indicator_counts"] = {
        "base_count": len(base_inds),
        "lora_count": len(lora_inds),
        "indicators_delta": len(lora_inds) - len(base_inds),
        "shared_indicator_count": len(shared),
        "new_indicators": list(added)[:10],
        "removed_indicators": list(removed)[:10],
    }
 
    # summary length
    base_summary_len = len((base_s.get("summary") or "").strip())
    lora_summary_len = len((lora_s.get("summary") or "").strip())
    metrics["summary_length_delta"] = lora_summary_len - base_summary_len
    metrics["base_summary_length"] = base_summary_len
    metrics["lora_summary_length"] = lora_summary_len
 
    # provenance: detect authority evidence presence in each
    base_auth = detect_authority_evidence(base_inds, content)
    lora_auth = detect_authority_evidence(lora_inds, content)
    metrics["provenance_change"] = {
        "base_authority_evidence": base_auth,
        "lora_authority_evidence": lora_auth,
        "authority_added": [a for a in lora_auth if a not in base_auth],
        "authority_removed": [a for a in base_auth if a not in lora_auth],
    }
 
    # improvement heuristics (simple)
    reasons = []
    improved = False
    # 1) lower risk is better (significant threshold)
    if metrics["risk_delta"] <= -10:
        improved = True
        reasons.append("Risk decreased significantly")
    elif metrics["risk_delta"] < 0:
        improved = True
        reasons.append("Risk moderately lower")
 
    # 2) more structured indicators and shared overlap suggests richer reasoning
    if metrics["indicator_counts"]["indicators_delta"] > 0:
        improved = True
        reasons.append("More indicators detected by LoRA")
    if metrics["indicator_counts"]["shared_indicator_count"] > 0:
        reasons.append("Shared indicators between base and LoRA")
 
    # 3) longer summary usually indicates richer explanation (heuristic)
    if metrics["summary_length_delta"] > 40:
        improved = True
        reasons.append("LoRA provided longer summary")
 
    # assemble final flags
    metrics["improved"] = improved
    metrics["improvement_reasons"] = reasons or ["No clear improvement detected"]
 
    # calibration flag: if base risk was high but LoRA reduced it by >20
    metrics["calibration_change"] = ""
    if base_risk >= 60 and metrics["risk_delta"] <= -20:
        metrics["calibration_change"] = "Reduced likely false positives (calibration)"
 
    return metrics
 
# -------------------- Endpoint: compare (replacement) ----------------------
 
@api_router.post("/compare", response_model=CompareResponse)
async def compare_models(req: CompareRequest):
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="content required")
 
    # Run models (these functions already return {"raw": raw_text, "sanitized": sanitized_dict})
    base = run_model(base_model, UNIFIED_SYSTEM_PROMPT, content)
    lora = run_model(lora_model, UNIFIED_SYSTEM_PROMPT, content)
 
    base_s = base["sanitized"]
    lora_s = lora["sanitized"]
 
    # Compute comparison metrics
    metrics = compute_comparison_metrics(base_s, lora_s, content)
 
    # Return enriched response
    return {
        "base_output": base_s,
        "lora_output": lora_s,
        "comparison_metrics": metrics,
        "base_raw": base["raw"][:4000] if isinstance(base["raw"], str) else None,
        "lora_raw": lora["raw"][:4000] if isinstance(lora["raw"], str) else None,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Wire up router
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(api_router)

@api_router.get("/")
async def root():
    return {"message": "INFO FORTRESS Compare-Only API", "endpoints": ["/api/compare"]}