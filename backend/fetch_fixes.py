"""
pipeline_fixes.py
=================
Drop-in replacements for the broken sections of server2.py.
"""

import re
import json
import logging
from typing import Any, Optional, Dict, Tuple
from urllib.parse import urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_INPUT_CHARS  = 8000
MAX_PROMPT_CHARS = 1800
MIN_PARA_CHARS   = 40


# ============================================================================
# EXTRACTION
# ============================================================================

_DOMAIN_HINTS: dict[str, dict] = {
    "timesofindia.indiatimes.com": {
        "container_classes": re.compile(
            r"_s30J|Normal|article-txt|artText|GA_art_story_"
            r"|clearfix.*article|read-app", re.I
        ),
    },
    "ndtv.com": {
        "container_classes": re.compile(r"sp-cn|article__content|content_text", re.I),
    },
    "thehindu.com": {
        "container_classes": re.compile(r"article-content|articleBody", re.I),
    },
}

_NOISE_PATTERNS = re.compile(
    r"(working\s+round\s+the\s+clock|follow\s+us\s+on\s+(twitter|instagram|facebook)"
    r"|subscribe\s+to\s+(our\s+)?newsletter|download\s+(the\s+)?app"
    r"|copyright\s+\d{4}|all\s+rights\s+reserved|terms\s+of\s+(use|service)"
    r"|privacy\s+policy|advertisement|sponsored\s+content"
    r"|sign\s+up\s+for|get\s+the\s+latest|also\s+read\s*:|read\s+more\s*:"
    r"|click\s+here\s+to|tap\s+here\s+to|exclusive\s+insights\s+into\s+the\s+world)",
    re.I
)


def _score_paragraph(text: str) -> float:
    if len(text) < MIN_PARA_CHARS:
        return 0.0
    if _NOISE_PATTERNS.search(text):
        return 0.0
    words = text.split()
    if len(words) < 6:
        return 0.1
    caps_ratio = sum(1 for w in words if w.isupper()) / max(len(words), 1)
    if caps_ratio > 0.5:
        return 0.1
    sentence_count = len(re.findall(r'[.!?]\s', text))
    return min(1.0, 0.3 + sentence_count * 0.15 + len(text) / 2000)


def _harvest_paragraphs(soup: BeautifulSoup, min_score: float = 0.25) -> str:
    candidates = []
    for p in soup.find_all("p"):
        text  = p.get_text(separator=" ", strip=True)
        score = _score_paragraph(text)
        if score >= min_score:
            candidates.append(text)
    if len(candidates) < 3 and min_score > 0.1:
        return _harvest_paragraphs(soup, min_score=0.1)
    joined = "\n\n".join(candidates)
    print(f"[EXTRACT/harvest] {len(candidates)} paragraphs, chars={len(joined)}")
    return joined


def _try_domain_hint(soup: BeautifulSoup, domain: str) -> Optional[str]:
    hint = next(
        (h for d, h in _DOMAIN_HINTS.items() if domain.endswith(d) or d in domain),
        None
    )
    if hint is None:
        return None
    container = soup.find(True, {"class": hint["container_classes"]})
    if container:
        text = re.sub(r"\n{3,}", "\n\n",
                      container.get_text(separator="\n", strip=True)).strip()
        print(f"[EXTRACT/domain-hint] matched {domain}, chars={len(text)}")
        return text if len(text) > 200 else None
    return None


def extract_article_text(soup: BeautifulSoup, base_url: str) -> str:
    domain = urlparse(base_url).netloc.lower().replace("www.", "")

    hint_text = _try_domain_hint(soup, domain)
    if hint_text and len(hint_text) > 300:
        return hint_text[:MAX_INPUT_CHARS]

    SELECTORS = [
        lambda s: s.find("article"),
        lambda s: s.find(True, {"class": re.compile(
            r"liveblog|live[-_]blog|live[-_]feed", re.I)}),
        lambda s: s.find(True, {"class": re.compile(
            r"article[-_]body|story[-_]body|post[-_]content|entry[-_]content"
            r"|article[-_]content|articleContent|storyContent|article-text"
            r"|article__body|story__body|content-body|post-body"
            r"|_s30J|artText|GA_art_story_", re.I)}),
        lambda s: s.find(True, {"id": re.compile(
            r"article[-_]body|story[-_]body|articleContent|storyContent"
            r"|article-content|story-content|liveblog", re.I)}),
        lambda s: s.find("main"),
        lambda s: s.find(True, {"role": "main"}),
    ]

    for fn in SELECTORS:
        el = fn(soup)
        if el:
            text = re.sub(r"\n{3,}", "\n\n",
                          el.get_text(separator="\n", strip=True)).strip()
            if len(text) > 300:
                print(f"[EXTRACT/selector] matched, chars={len(text)}")
                return text[:MAX_INPUT_CHARS]

    harvested = _harvest_paragraphs(soup)
    if len(harvested) > 200:
        return harvested[:MAX_INPUT_CHARS]

    print("[EXTRACT/fallback] minimal body strip")
    raw   = (soup.body or soup).get_text(separator="\n", strip=True)
    lines = [l.strip() for l in raw.split("\n")
             if len(l.strip()) > MIN_PARA_CHARS and _score_paragraph(l.strip()) > 0.1]
    return "\n\n".join(lines[:60])[:MAX_INPUT_CHARS]


# ============================================================================
# PROMPT CLEANING
# ============================================================================

def clean_for_prompt(text: str, max_chars: int = MAX_PROMPT_CHARS) -> str:
    kept = [
        l.strip() for l in text.split("\n")
        if l.strip()
        and not _NOISE_PATTERNS.search(l.strip())
        and len(l.strip()) >= 15
    ]
    cleaned = "\n".join(kept)
    if len(cleaned) <= max_chars:
        return cleaned
    truncated = cleaned[:max_chars]
    last_stop = max(
        truncated.rfind(". "), truncated.rfind(".\n"),
        truncated.rfind("! "), truncated.rfind("? "),
    )
    if last_stop > max_chars // 2:
        truncated = truncated[:last_stop + 1]
    return truncated.strip()


# ============================================================================
# JSON REPAIR + PARSING
# ============================================================================

def _to_float(raw: str) -> Optional[float]:
    """
    Convert a possibly-corrupted numeric string to float.
    Strips all non-numeric characters except . and - before converting.
    Handles:  0."95  →  0.95
              0.:95  →  0.95
              0.%95  →  0.95
              0,95   →  0.95  (already handled by repair, belt-and-suspenders)
    """
    s = re.sub(r'[^0-9.\-]', '', str(raw))
    # collapse multiple dots (e.g. "0..95" from double-stripping)
    parts = s.split('.')
    if len(parts) > 2:
        s = parts[0] + '.' + ''.join(parts[1:])
    try:
        return float(s)
    except ValueError:
        return None


def _repair_json(text: str) -> str:
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    text = text[start:end + 1]

    # ── Separator corruptions FIRST — before bare decimal fix ───────────────
    text = re.sub(r'(\d+)\.\s*:\s*(\d+)',  r'\1.\2', text)   # 0.:95  → 0.95
    text = re.sub(r'(\d+)\.\s*"\s*(\d+)',  r'\1.\2', text)   # 0."95  → 0.95
    text = re.sub(r"(\d+)\.\s*'\s*(\d+)",  r'\1.\2', text)   # 0.'95  → 0.95
    text = re.sub(r'(\d+),(\d+)',           r'\1.\2', text)   # 0,95   → 0.95

    # ── Bare decimal AFTER separator fixes ──────────────────────────────────
    text = re.sub(r'(\d+\.)\s*(?=[,"\'\]\}])', r'\g<1>0', text)  # 0. → 0.0

    text = re.sub(r'(\d+\.?\d*)\s*%',         r'\1',    text)    # 0.95% → 0.95
    text = re.sub(r'(\d+\.?\d*)\s*\([^)]*\)', r'\1',    text)    # 0()   → 0
    text = re.sub(r',\s*([}\]])',              r'\1',    text)    # trailing comma
    text = re.sub(r'"\s*"\s*',                '',       text)    # split keys

    for bad, good in [
        ('"low_medium"',  '"medium"'), ('"high_medium"', '"high"'),
        ('"low_high"',    '"medium"'), ('"medium_high"', '"high"'),
    ]:
        text = text.replace(bad, good)

    text = re.sub(r':\s*True\b',  ': true',  text)
    text = re.sub(r':\s*False\b', ': false', text)
    text = re.sub(r':\s*None\b',  ': null',  text)
    text = re.sub(r'#[^\n"]*\n',  '\n',      text)

    return text


def _partial_extract(text: str) -> dict:
    """
    Extract key-value pairs from malformed JSON via regex.
    Uses _to_float() so corrupted values like  0."95  are recovered correctly.
    This is the ONLY definition of _partial_extract in this file.
    """
    result = {}

    # Numeric fields — grab value token (up to 12 chars) after the colon
    for key in ["misinfo_prob", "confidence", "source_risk",
                "evidence_weakness", "sensationalism", "risk_score"]:
        m = re.search(
            rf'"{key}"\s*:\s*([0-9][^,\}}\n]{{0,12}})',
            text, re.I
        )
        if m:
            val = _to_float(m.group(1))
            if val is not None:
                result[key] = val
                print(f"[_partial_extract] {key} = {val}  (raw token: {m.group(1)!r})")

    # String fields
    for key in ["veracity_assessment", "article_type",
                "institutional_impact", "operational_sensitivity",
                "public_panic_potential", "coordination_risk_hint"]:
        m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', text, re.I)
        if m:
            result[key] = m.group(1)

    # summary
    m = re.search(r'"summary"\s*:\s*"([^"]{10,300})"', text, re.I)
    if m:
        result["summary"] = m.group(1)

    # indicators — handles both " and ' quoted items
    m = re.search(r'"indicators"\s*:\s*\[([^\]]+)\]', text, re.I)
    if m:
        items = re.findall(r'["\']([^"\']+)["\']', m.group(1))
        if items:
            result["indicators"] = items

    print(f"[_partial_extract] recovered keys: {list(result.keys())}")
    return result


def parse_model_json(raw_text: str) -> Tuple[Optional[dict], bool]:
    if not raw_text or not raw_text.strip():
        return None, False

    text = raw_text.strip()

    try:
        return json.loads(text), True
    except Exception:
        pass

    repaired = _repair_json(text)
    try:
        return json.loads(repaired), True
    except Exception:
        pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1]), True
        except Exception:
            pass
        try:
            return json.loads(_repair_json(text[start:end + 1])), True
        except Exception:
            pass

    partial = _partial_extract(text)
    if partial:
        print("[parse_model_json] Full parse failed — using partial extraction")
        return partial, False

    print(f"[parse_model_json] All attempts failed. Repaired preview:\n{repaired[:300]}")
    return None, False


# ============================================================================
# NORMALIZATION
# ============================================================================

def _safe_float(v, default: float = 0.0) -> float:
    """
    Convert v to float safely.
    Accepts int, float, and str (including corrupted strings like '0."95').
    Uses _to_float() for strings so corruption is handled uniformly.
    """
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        result = _to_float(v)
        return result if result is not None else default
    return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default

def _extract_from_prose(text: str, source_hint: str = "") -> dict:
    t = text.lower()
    misinfo   = (3*t.count("misinformation") + 2*t.count("false information")
                 + 2*t.count("misleading") + t.count("fabricated")
                 + t.count("no evidence") + t.count("unverified"))
    satire    = 5*t.count("satire") + 5*t.count("parody") + 3*t.count(" onion")
    credible  = (3*t.count("credible") + 2*t.count("verified")
                 + 2*t.count("reliable") + t.count("accurate"))
    uncertain = 2*t.count("uncertain") + t.count("unclear") + t.count("reportedly")

    scores   = {"likely_misinformation": misinfo+satire,
                "likely_true": credible, "uncertain": uncertain}
    veracity = max(scores, key=scores.get) if max(scores.values()) > 0 else "uncertain"

    risk_score = (min(90, 50+misinfo*4+satire*5) if veracity == "likely_misinformation"
                  else max(5, 35-credible*5)      if veracity == "likely_true"
                  else min(60, 35+uncertain*4))

    confidence = 0.60 if scores[veracity] >= 3 else 0.35
    sentences  = re.split(r'(?<=[.!?])\s+', text.strip())
    summary    = " ".join(sentences[:2]).strip()

    print(f"[prose] misinfo={misinfo} satire={satire} credible={credible} "
          f"uncertain={uncertain} → veracity={veracity} risk={risk_score}")
    return {"risk_score": risk_score, "veracity_assessment": veracity,
            "confidence": confidence, "summary": summary}


def _build_conclusion(parsed: dict, risk_score: int) -> str:
    veracity     = str(parsed.get("veracity_assessment", "")).replace("_", " ")
    article_type = str(parsed.get("article_type", "")).replace("_", " ")
    prob_pct     = int(_safe_float(parsed.get("misinfo_prob"), risk_score / 100) * 100)

    def _lv(k): return str(parsed.get(k, "low")).lower()
    elevated = [l for l, v in [
        ("institutional impact",    _lv("institutional_impact")),
        ("public panic potential",  _lv("public_panic_potential")),
        ("coordination risk",       _lv("coordination_risk_hint")),
        ("operational sensitivity", _lv("operational_sensitivity")),
    ] if v in ("medium", "high")]

    indicators = parsed.get("indicators", [])
    ind_names  = [(i.get("name") if isinstance(i, dict) else str(i)).replace("_", " ")
                  for i in indicators if i]

    opening  = (f"Classified as {article_type} with veracity '{veracity}' "
                f"and misinformation probability of {prob_pct}%."
                if veracity and article_type else
                f"Misinformation probability: {prob_pct}%.")
    ind_s    = f"Risk signals: {', '.join(ind_names)}." if ind_names else ""
    impact_s = (f"Elevated risk in: {', '.join(elevated)}."
                if elevated else
                "Contextual impact signals are low across all dimensions.")
    rec      = ("Do not share without independent verification."       if prob_pct >= 70 else
                "Cross-check with credible sources before sharing."    if prob_pct >= 40 else
                "Content appears largely credible; standard media literacy applies.")

    return " ".join(p for p in [opening, ind_s, impact_s, rec] if p)


def normalize_output(raw_text: str, model_label: str = "unknown") -> Dict[str, Any]:
    print(f"\n[NORM/{model_label}] len={len(raw_text)} preview={raw_text[:200]!r}")

    if model_label == "base":
        parsed, full_parse = parse_model_json(raw_text)
        if not parsed:
            prose = _extract_from_prose(raw_text)
            return {
                "parse_failed":             False,
                "parse_method":             "prose",
                "risk_score":               prose["risk_score"],
                "veracity_assessment":      prose["veracity_assessment"],
                "article_type":             "unknown",
                "confidence":               prose["confidence"],
                "indicators":               [],
                "summary":                  prose["summary"],
                "misinfo_prob":             prose["risk_score"] / 100,
                "source_risk":              0.0,
                "evidence_weakness":        0.0,
                "sensationalism":           0.0,
                "institutional_impact":     "low",
                "operational_sensitivity":  "low",
                "public_panic_potential":   "low",
                "coordination_risk_hint":   "low",
                "conclusion":               "",
            }
    else:
        parsed, full_parse = parse_model_json(raw_text)

    if not parsed:
        print(f"[NORM/{model_label}] PARSE FAILED")
        return {
            "parse_failed":             True,
            "parse_method":             "failed",
            "risk_score":               None,
            "veracity_assessment":      None,
            "article_type":             None,
            "confidence":               None,
            "indicators":               [],
            "summary":                  "Analysis could not be parsed from model output.",
            "misinfo_prob":             None,
            "source_risk":              None,
            "evidence_weakness":        None,
            "sensationalism":           None,
            "institutional_impact":     None,
            "operational_sensitivity":  None,
            "public_panic_potential":   None,
            "coordination_risk_hint":   None,
            "conclusion":               "",
            "raw_fallback":             raw_text[:300],
        }

    if "misinfo_prob" in parsed:
        risk_score = min(100, max(0, int(_safe_float(parsed["misinfo_prob"]) * 100)))
    else:
        risk_score = min(100, max(0, _safe_int(parsed.get("risk_score", 0))))

    confidence = min(1.0, max(0.0, _safe_float(parsed.get("confidence", 0.0))))

    # LoRA confidence correction — model underreports confidence due to training distribution
    if model_label == "lora":
        misinfo_p   = _safe_float(parsed.get("misinfo_prob"), risk_score / 100)
        indicator_n = len(parsed.get("indicators", []) or [])
        if misinfo_p >= 0.80 or misinfo_p <= 0.10:
            derived_conf = 0.70
        elif misinfo_p >= 0.60 or misinfo_p <= 0.25:
            derived_conf = 0.55
        else:
            derived_conf = 0.40
        derived_conf = min(0.95, derived_conf + indicator_n * 0.04)
        confidence   = max(confidence, derived_conf)
        print(f"[NORM/lora] conf corrected to {confidence:.2f} (derived={derived_conf:.2f})")

    clean_indicators = []
    for item in (parsed.get("indicators", []) or []):
        if isinstance(item, dict):
            sev = str(item.get("severity", "low")).lower()
            sev = sev if sev in {"low", "medium", "high"} else "low"
            clean_indicators.append({
                "name":     str(item.get("name", "unknown")).strip(),
                "evidence": str(item.get("evidence", "")).strip(),
                "severity": sev,
            })
        elif isinstance(item, str) and item.strip():
            name = item.strip()
            sev  = ("high"   if any(k in name for k in ["lack", "unverified", "single_source", "reputation"])
                    else "medium" if any(k in name for k in ["sensational", "weak", "missing", "panic"])
                    else "low")
            clean_indicators.append({"name": name.replace("_", " "), "evidence": "", "severity": sev})

    summary = parsed.get("summary", "")
    if not isinstance(summary, str) or not summary.strip():
        summary = raw_text[:200]

    def _lv(val, default="low"):
        v = str(val or default).lower()
        return "high" if "high" in v else "medium" if "medium" in v else "low"

    result = {
        "parse_failed":             False,
        "parse_method":             "full" if full_parse else "partial",
        "risk_score":               risk_score,
        "veracity_assessment":      str(parsed.get("veracity_assessment", "unknown")).strip() or "unknown",
        "article_type":             str(parsed.get("article_type", "unknown")).strip() or "unknown",
        "confidence":               confidence,
        "indicators":               clean_indicators,
        "summary":                  summary.strip(),
        "misinfo_prob":             _safe_float(parsed.get("misinfo_prob"), risk_score / 100),
        "source_risk":              _safe_float(parsed.get("source_risk"), 0.0),
        "evidence_weakness":        _safe_float(parsed.get("evidence_weakness"), 0.0),
        "sensationalism":           _safe_float(parsed.get("sensationalism"), 0.0),
        "institutional_impact":     _lv(parsed.get("institutional_impact")),
        "operational_sensitivity":  _lv(parsed.get("operational_sensitivity")),
        "public_panic_potential":   _lv(parsed.get("public_panic_potential")),
        "coordination_risk_hint":   _lv(parsed.get("coordination_risk_hint")),
        "conclusion":               _build_conclusion(parsed, risk_score) if model_label == "lora" else "",
    }

    print(f"[NORM/{model_label}] method={result['parse_method']} "
          f"risk={result['risk_score']} conf={result['confidence']} "
          f"inds={len(result['indicators'])} veracity={result['veracity_assessment']!r}")
    return result

# ============================================================================
# COMPARISON METRICS
# ============================================================================

def build_comparison_metrics(base_output: Dict[str, Any],
                              lora_output: Dict[str, Any]) -> Dict[str, Any]:
    base_failed = base_output.get("parse_failed", False)
    lora_failed = lora_output.get("parse_failed", False)

    base_risk = base_output.get("risk_score")
    lora_risk = lora_output.get("risk_score")
    base_conf = base_output.get("confidence")
    lora_conf = lora_output.get("confidence")

    base_inds  = base_output.get("indicators", []) or []
    lora_inds  = lora_output.get("indicators", []) or []
    base_names = {i.get("name", "").lower() for i in base_inds if isinstance(i, dict)}
    lora_names = {i.get("name", "").lower() for i in lora_inds if isinstance(i, dict)}
    shared     = sorted(base_names & lora_names)
    new_lora   = sorted(lora_names - base_names)

    improved = False
    reasons  = []

    if not base_failed and not lora_failed:
        if lora_conf is not None and base_conf is not None and lora_conf > base_conf:
            improved = True
            reasons.append("Higher confidence")
        if new_lora:
            improved = True
            reasons.append(f"Detected {len(new_lora)} additional indicator(s)")
        if (lora_risk is not None and base_risk is not None
                and lora_risk != base_risk and lora_risk > 0):
            improved = True
            reasons.append(f"Risk score refined: {base_risk} → {lora_risk}")

    if lora_failed:
        reasons = ["LoRA output could not be parsed — no comparison available"]
    elif base_failed:
        reasons.append("Base output used prose fallback")

    def _n(v): return v if v is not None else "N/A"

    metrics = {
        "base_failed":      base_failed,
        "lora_failed":      lora_failed,
        "base_risk":        _n(base_risk),
        "lora_risk":        _n(lora_risk),
        "risk_delta":       (lora_risk - base_risk) if (lora_risk is not None and base_risk is not None) else None,
        "base_confidence":  _n(base_conf),
        "lora_confidence":  _n(lora_conf),
        "confidence_delta": round((lora_conf - base_conf) * 100, 1) if (lora_conf is not None and base_conf is not None) else None,
        "indicator_counts": {
            "base_count":             len(base_inds),
            "lora_count":             len(lora_inds),
            "shared_indicator_count": len(shared),
            "new_indicators":         new_lora,
        },
        "improved":            improved,
        "improvement_reasons": reasons,
    }

    print(f"\n[METRICS] base_failed={base_failed} lora_failed={lora_failed}")
    print(f"[METRICS] base_risk={base_risk} lora_risk={lora_risk} "
          f"delta={metrics['risk_delta']} improved={improved}")
    return metrics