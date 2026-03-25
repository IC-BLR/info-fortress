"""
output_mapper.py
================
Maps the normalize_output() schema from fetch_fixes.py
to the field names the new AnalysisPage.jsx UI expects.
 
Import and call map_to_ui() on both base_output and lora_output
before returning the final response in compare_models().
 
Also contains the improved base model prompt that tries to produce
structured JSON closer to the new schema.
"""
 
from typing import Any, Dict, Optional
 
 
# ============================================================================
# FIELD DERIVATION HELPERS
# ============================================================================
 
def _derive_verdict(veracity: Optional[str]) -> str:
    """Map veracity_assessment → verdict (UI enum)."""
    if not veracity:
        return "uncertain"
    v = veracity.lower()
    if "misinformation" in v or "false" in v:
        return "likely_false"
    if "true" in v or "credible" in v:
        return "likely_true"
    return "uncertain"
 
 
def _derive_confidence_band(confidence: Optional[float]) -> str:
    """Map float confidence → low/medium/high band."""
    if confidence is None:
        return "low"
    if confidence >= 0.70:
        return "high"
    if confidence >= 0.40:
        return "medium"
    return "low"
 
 
def _derive_narrative_risk(risk_score: Optional[int]) -> str:
    """Map 0-100 risk_score → low/medium/high."""
    if risk_score is None:
        return "low"
    if risk_score >= 67:
        return "high"
    if risk_score >= 34:
        return "medium"
    return "low"
 
 
def _derive_sharing_policy(risk_score: Optional[int], veracity: Optional[str]) -> str:
    """
    Derive sharing policy from risk score and veracity.
    - Known satire / high misinformation → do_not_share
    - Uncertain / medium risk → caution
    - Credible / low risk → allow
    """
    if risk_score is None:
        return "caution"
    v = (veracity or "").lower()
    if risk_score >= 70 or "misinformation" in v or "false" in v:
        return "do_not_share"
    if risk_score >= 35 or "uncertain" in v:
        return "caution"
    return "allow"
 
 
def _derive_tone_mode(sensationalism: Optional[float], sharing_policy: str) -> str:
    """
    Derive tone_mode from sensationalism score and sharing policy.
    harden  = content needs firm pushback
    soften  = content is credible, reduce alarm
    neutral = no strong tone adjustment needed
    """
    if sharing_policy == "do_not_share":
        return "harden"
    if sharing_policy == "allow":
        return "soften"
    if sensationalism is not None and sensationalism >= 0.6:
        return "harden"
    return "neutral"
 
 
def _derive_verification_needed(indicators: list, veracity: Optional[str]) -> list:
    """
    Derive verification_needed list from indicators.
    Maps indicator names to actionable verification steps.
    """
    if not indicators:
        return []
 
    mapping = {
        "lack of sources":           "verify with primary source",
        "unverified claim":          "cross-check with at least 2 credible outlets",
        "single source dependency":  "find independent corroboration",
        "source reputation concern": "check outlet credibility rating",
        "official source reference": "confirm via official government/org channel",
        "institutional reference":   "verify institutional statement directly",
        "sensationalism":            "check if language matches facts",
        "missing context":           "seek full context before sharing",
        "unverified claim":          "check if claim has been fact-checked",
    }
 
    result = []
    for ind in indicators:
        name = (ind.get("name") if isinstance(ind, dict) else str(ind)).lower()
        for key, action in mapping.items():
            if key in name and action not in result:
                result.append(action)
 
    # Add generic check if nothing specific matched
    v = (veracity or "").lower()
    if not result and ("uncertain" in v or "misinformation" in v or "false" in v):
        result.append("independent fact-check recommended")
 
    return result
 
 
def _derive_phase1_behavior(lora_output: Dict[str, Any]) -> dict:
    """
    Derive the phase1_behavior flags the UI TopImpactStrip expects.
    These detect qualitative properties of the LoRA's analysis.
    """
    conclusion  = (lora_output.get("conclusion") or "").lower()
    summary     = (lora_output.get("summary")    or "").lower()
    indicators  = lora_output.get("indicators", []) or []
    ind_names   = " ".join(
        (i.get("name") if isinstance(i, dict) else str(i)).lower()
        for i in indicators
    )
    full_text = conclusion + " " + summary + " " + ind_names
 
    authority_words   = ["verify", "official", "government", "authorit", "institution",
                         "check with", "confirm via"]
    boundary_words    = ["do not share", "do not spread", "avoid sharing",
                         "exercise caution", "should not be shared", "independent verification"]
    rumor_hard_words  = ["rumor", "unverified claim", "speculation", "alleged",
                         "single source", "screenshot"]
 
    return {
        "lora_authority_verification_present": any(w in full_text for w in authority_words),
        "lora_boundary_language_present":      any(w in full_text for w in boundary_words),
        "lora_sensitive_rumor_hardening":      any(w in full_text for w in rumor_hard_words),
    }
 
 
def _derive_safe_user_response(output: Dict[str, Any], model_label: str) -> str:
    """
    Build a safe user-facing response string.
    LoRA uses conclusion (full paragraph), base uses report field.
    """
    if model_label == "lora":
        return output.get("conclusion") or output.get("summary") or "No analysis available."
    
    # Base model uses "report" field from its JSON schema
    text = output.get("report", "").strip()
    if text:
        return text
    
    # Fallback to description
    text = output.get("description", "").strip()
    if text:
        return text
    
    # Generate fallback from available data if verdict/confidence exist
    verdict = output.get("veracity_assessment", "").strip()
    confidence = output.get("confidence")
    if verdict and verdict != "unknown" and confidence is not None:
        verdict_display = verdict.replace("_", " ").title()
        conf_pct = int(confidence * 100)
        risk_score = output.get("risk_score", 0)
        
        if risk_score >= 70:
            sharing = "Do not share without independent verification."
        elif risk_score >= 40:
            sharing = "Verify with credible sources before sharing."
        else:
            sharing = "Content appears credible based on available signals."
        
        return f"Classified as {verdict_display} with {conf_pct}% confidence. {sharing}"
    
    # Final fallback
    return "No analysis available."
 
 
def _extract_risk_signals(indicators: list) -> list:
    """Convert indicators list to flat string list for UI chip display."""
    result = []
    for ind in (indicators or []):
        if isinstance(ind, dict):
            name = ind.get("name", "").strip()
            if name:
                result.append(name)
        elif isinstance(ind, str) and ind.strip():
            result.append(ind.strip())
    return result
 
 
# ============================================================================
# MAIN MAPPER
# ============================================================================
 
def map_to_ui(output: Dict[str, Any], model_label: str) -> Dict[str, Any]:
    """
    Convert normalize_output() result → AnalysisPage.jsx UI schema.
 
    Input fields (from fetch_fixes.normalize_output):
        parse_failed, parse_method, risk_score, veracity_assessment,
        article_type, confidence, indicators, summary, misinfo_prob,
        source_risk, evidence_weakness, sensationalism,
        institutional_impact, operational_sensitivity,
        public_panic_potential, coordination_risk_hint, conclusion
 
    Output fields (what AnalysisPage.jsx SnapshotCard expects):
        verdict, confidence_band, narrative_risk, sharing_policy,
        tone_mode, safe_user_response, risk_signals, verification_needed
    """
    if not output:
        return {}
 
    parse_failed = output.get("parse_failed", False)
 
    # If completely failed, return minimal shape with nulls
    if parse_failed:
        return {
            "parse_failed":       True,
            "verdict":            None,
            "confidence_band":    None,
            "narrative_risk":     None,
            "sharing_policy":     None,
            "tone_mode":          None,
            "safe_user_response": "Analysis could not be parsed from model output.",
            "risk_signals":       [],
            "verification_needed": [],
            # Pass through raw fields for debug
            "article_type":       None,
            "misinfo_prob":       None,
            "source_risk":        None,
            "evidence_weakness":  None,
            "sensationalism":     None,
            "institutional_impact":     None,
            "operational_sensitivity":  None,
            "public_panic_potential":   None,
            "coordination_risk_hint":   None,
            "summary":            output.get("summary", ""),
            "conclusion":         "",
            "parse_method":       output.get("parse_method", "failed"),
        }
 
    risk_score   = output.get("risk_score")
    veracity     = output.get("veracity_assessment")
    confidence   = output.get("confidence")
    sensational  = output.get("sensationalism")
    indicators   = output.get("indicators", []) or []
 
    verdict         = _derive_verdict(veracity)
    confidence_band = _derive_confidence_band(confidence)
    narrative_risk  = _derive_narrative_risk(risk_score)
    sharing_policy  = _derive_sharing_policy(risk_score, veracity)
    tone_mode       = _derive_tone_mode(sensational, sharing_policy)
    risk_signals    = _extract_risk_signals(indicators)
    verification    = _derive_verification_needed(indicators, veracity)
    safe_response   = _derive_safe_user_response(output, model_label)
    
    # DEBUG: Track safe_response generation
    print(f"[map_to_ui/{model_label}] safe_response = {safe_response[:70] if safe_response else 'EMPTY'}")
    print(f"[map_to_ui/{model_label}] input report = {output.get('report', 'MISSING')[:60] if output.get('report') else 'EMPTY'}")
    print(f"[map_to_ui/{model_label}] input desc = {output.get('description', 'MISSING')[:60]}")

    return {
        "parse_failed":        parse_failed,
        "parse_method":        output.get("parse_method", "unknown"),
        # ── UI primary fields ─────────────────────────────────────────────
        "verdict":             verdict,
        "confidence_band":     confidence_band,
        "narrative_risk":      narrative_risk,
        "sharing_policy":      sharing_policy,
        "tone_mode":           tone_mode,
        "safe_user_response":  safe_response,
        "risk_signals":        risk_signals,
        "verification_needed": verification,
        # ── Pass-through for raw panel / debugging ────────────────────────
        "article_type":              output.get("article_type"),
        "misinfo_prob":              output.get("misinfo_prob"),
        "source_risk":               output.get("source_risk"),
        "evidence_weakness":         output.get("evidence_weakness"),
        "sensationalism":            output.get("sensationalism"),
        "institutional_impact":      output.get("institutional_impact"),
        "operational_sensitivity":   output.get("operational_sensitivity"),
        "public_panic_potential":    output.get("public_panic_potential"),
        "coordination_risk_hint":    output.get("coordination_risk_hint"),
        "summary":                   output.get("summary", ""),
        "conclusion":                output.get("conclusion", ""),
        "confidence":                confidence,
        "risk_score":                risk_score,
    }
 
 
def build_comparison_ui_metrics(
    base_ui:    Dict[str, Any],
    lora_ui:    Dict[str, Any],
    raw_metrics: Dict[str, Any],
    lora_output: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build the comparison_metrics shape AnalysisPage.jsx expects,
    combining raw_metrics from fetch_fixes with UI-level delta flags.
    """
    def _changed(field):
        return base_ui.get(field) != lora_ui.get(field)
 
    base_signals  = base_ui.get("risk_signals", []) or []
    lora_signals  = lora_ui.get("risk_signals", []) or []
    base_verif    = base_ui.get("verification_needed", []) or []
    lora_verif    = lora_ui.get("verification_needed", []) or []
 
    base_sig_set  = set(base_signals)
    lora_sig_set  = set(lora_signals)
    base_ver_set  = set(base_verif)
    lora_ver_set  = set(lora_verif)
 
    phase1 = _derive_phase1_behavior(lora_output)
 
    return {
        # ── Raw numeric deltas (from fetch_fixes) ─────────────────────────
        "base_failed":       raw_metrics.get("base_failed", False),
        "lora_failed":       raw_metrics.get("lora_failed", False),
        "base_risk":         raw_metrics.get("base_risk"),
        "lora_risk":         raw_metrics.get("lora_risk"),
        "risk_delta":        raw_metrics.get("risk_delta"),
        "base_confidence":   raw_metrics.get("base_confidence"),
        "lora_confidence":   raw_metrics.get("lora_confidence"),
        "confidence_delta":  raw_metrics.get("confidence_delta"),
        "improved":          raw_metrics.get("improved", False),
        "improvement_reasons": raw_metrics.get("improvement_reasons", []),
        # ── UI-level change flags ─────────────────────────────────────────
        "verdict_changed":         _changed("verdict"),
        "sharing_policy_changed":  _changed("sharing_policy"),
        "confidence_band_changed": _changed("confidence_band"),
        "risk_changed":            _changed("narrative_risk"),
        "tone_changed":            _changed("tone_mode"),
        # ── Signal / verification counts ─────────────────────────────────
        "signal_counts": {
            "base_count":    len(base_signals),
            "lora_count":    len(lora_signals),
            "added_by_lora": sorted(lora_sig_set - base_sig_set),
            "removed_by_lora": sorted(base_sig_set - lora_sig_set),
            "shared":        sorted(base_sig_set & lora_sig_set),
        },
        "verification_counts": {
            "base_count":    len(base_verif),
            "lora_count":    len(lora_verif),
            "added_by_lora": sorted(lora_ver_set - base_ver_set),
            "removed_by_lora": sorted(base_ver_set - lora_ver_set),
            "shared":        sorted(base_ver_set & lora_ver_set),
        },
        # ── Phase 1 qualitative behavior flags ───────────────────────────
        "phase1_behavior": phase1,
        # ── Indicator counts (legacy, kept for compatibility) ─────────────
        "indicator_counts": raw_metrics.get("indicator_counts", {}),
    }
 
 

IMPROVED_BASE_SYSTEM = "You are a misinformation analysis assistant. Respond ONLY with valid JSON. Never write explanations or comments outside the JSON."
 
def build_improved_base_user_msg(content: str, source_hint: str = "unknown") -> str:
    """
    Improved base model prompt attempting the new UI schema fields.
    Based on the prompt spec provided, adapted for TinyLlama's limitations:
    - Removed evidence_spans (model hallucinates these badly)
    - Kept signals, verdict, confidence, sharing_policy, description, report
    - Added explicit enum constraints on every field
    - SOURCE_HINT replaces the original SOURCE_REPUTATION/SOURCE_TYPE
    """
    return f"""Analyze this content from source: {source_hint}

CONTENT:
{content}

Provide your analysis as valid JSON starting with {{ immediately.

Example format:
{{
  "verdict": "uncertain",
  "confidence": 0.6,
  "sharing_policy": "caution",
  "signals": ["no sources cited", "single claim"],
  "description": "Political claim lacking verification.",
  "report": "This content makes unverified political claims without citing credible sources. The assertions lack independent corroboration. Cross-check with reputable news outlets before sharing."
}}

Your analysis:
- verdict: "likely_false" OR "uncertain" OR "likely_true"
- confidence: number between 0.0 and 1.0
- sharing_policy: "do_not_share" OR "caution" OR "allow"
- signals: list of detected issues like "no sources", "unverified claim", "official statement", etc.
- description: one sentence summarizing the content
- report: 2-3 sentences explaining why verdict was assigned and what verification is needed

Start with {{ now:"""
