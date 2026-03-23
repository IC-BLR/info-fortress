"""
server.py — INFO FORTRESS API (Compare-only)
============================================
Backend: Local Qwen Base + LoRA guardrail compare.
Provides:
- POST /api/compare
- GET  /api/

Notes:
- Assumes guardrails.generate_with_model(...) returns RAW model text
- Supports either:
  1) legacy `content`
  2) structured `url`, `title`, `body`
  3) `content` already formatted as SOURCE_URL / TITLE / BODY
- Adds a deterministic source pre-check before inference
"""

from typing import Any, Dict, List, Optional, Tuple
import json
import re
import unicodedata
from urllib.parse import urlparse

from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import trafilatura
from guardrails import (
    generate_with_model,
    base_model,
    lora_model,
)

# ---------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------

UNIFIED_SYSTEM_PROMPT = """
You are a news guardrail assistant.

Return valid JSON only with exactly these keys:
verdict, confidence, sharing_policy, signals, evidence_spans, description, report

Rules:
- verdict must be one of: likely_false, uncertain, likely_true
- confidence must be a number from 0 to 1
- sharing_policy must be one of: allow, caution, do_not_share
- signals must be a JSON array of short strings
- evidence_spans must be a JSON array of exact substrings copied from INPUT
- description must be 1 sentence
- report must be 2-3 short sentences
- Use only the provided INPUT
- Do not invent sources, URLs, domains, or facts
- SOURCE_REPUTATION and SOURCE_TYPE are useful signals, but they do not prove truth by themselves
- Weakly sourced, hedged, screenshot-only, anonymous, or urgency-framed items should often be uncertain or likely_false
- Official or well-attributed items with concrete details can be likely_true
""".strip()

# ---------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------

app = FastAPI(title="INFO FORTRESS - Compare Only")
api_router = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------

URL_RE = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", flags=re.IGNORECASE)

ALLOWED_VERDICTS = {"likely_false", "uncertain", "likely_true"}
ALLOWED_POLICIES = {"allow", "caution", "do_not_share"}

HIGH_TRUST_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "nytimes.com",
    "theguardian.com",
    "washingtonpost.com",
    "cnbc.com",
    "cnn.com",
    "dw.com",
}

MEDIUM_TRUST_DOMAINS = {
    "indiatimes.com",
    "timesofindia.indiatimes.com",
    "ndtv.com",
    "thehindu.com",
    "hindustantimes.com",
    "indianexpress.com",
    "economictimes.indiatimes.com",
    "aljazeera.com",
    "news18.com",
    "abcnews.go.com",
}

FACT_CHECK_DOMAINS = {
    "snopes.com",
    "factcheck.org",
    "politifact.com",
    "fullfact.org",
}

OFFICIAL_GOV_DOMAINS = {
    "gov.sg",
    "mas.gov.sg",
    "moh.gov.sg",
}

SOCIAL_DOMAINS = {
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "reddit.com",
    "telegram.org",
    "whatsapp.com",
    "linkedin.com",
}

SHORTENER_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "rb.gy",
    "rebrand.ly",
    "ow.ly",
    "buff.ly",
    "lnkd.in",
    "goo.gl",
    "cutt.ly",
    "shorturl.at",
}

BLOG_LIKE_DOMAINS = {
    "medium.com",
    "substack.com",
    "blogspot.com",
    "wordpress.com",
    "tumblr.com",
    "ghost.io",
}


MAX_FETCH_CHARS = 4000
HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

def extract_first_url_from_text(text: str) -> str:
    if not text:
        return ""
    m = URL_RE.search(text)
    if not m:
        return ""
    return m.group(1).rstrip(".,);]>")

def normalize_url_for_fetch(url: str) -> str:
    url = preprocess_text(url or "")
    if not url:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        url = "https://" + url
    return url

def is_safe_public_url(url: str) -> bool:
    """
    Basic SSRF guard:
    - allow only http/https
    - block localhost / private / loopback / link-local / multicast / reserved IPs
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"}:
        return False

    host = parsed.hostname
    if not host:
        return False

    host_l = host.lower()
    if host_l in {"localhost"} or host_l.endswith(".local"):
        return False

    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False

    for info in infos:
        ip = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            return False

        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
        ):
            return False

    return True

async def fetch_article_from_url(url: str) -> Dict[str, Any]:
    """
    Fetch HTML, extract main text with trafilatura, return normalized fields.
    """
    url = normalize_url_for_fetch(url)
    if not url:
        return {
            "fetch_status": "no_url",
            "fetched_url": "",
            "fetched_title": "",
            "fetched_body": "",
            "fetch_error": "",
        }

    if not is_safe_public_url(url):
        return {
            "fetch_status": "blocked_url",
            "fetched_url": url,
            "fetched_title": "",
            "fetched_body": "",
            "fetch_error": "URL blocked by SSRF/public-host checks",
        }

    headers = {
        "User-Agent": "INFO-FORTRESS/1.0",
        "Accept": "text/html,application/xhtml+xml",
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                return {
                    "fetch_status": "unsupported_content_type",
                    "fetched_url": str(resp.url),
                    "fetched_title": "",
                    "fetched_body": "",
                    "fetch_error": f"Unsupported content-type: {content_type}",
                }

            html = resp.text
    except Exception as e:
        return {
            "fetch_status": "fetch_failed",
            "fetched_url": url,
            "fetched_title": "",
            "fetched_body": "",
            "fetch_error": str(e)[:240],
        }

    # Try JSON output first so we can pull title/text cleanly.
    fetched_title = ""
    fetched_body = ""

    try:
        extracted_json = trafilatura.extract(html, output_format="json")
        if extracted_json:
            data = json.loads(extracted_json)
            fetched_title = preprocess_text(data.get("title") or "")
            fetched_body = preprocess_text(data.get("text") or "")
    except Exception:
        pass

    if not fetched_body:
        try:
            fetched_body = preprocess_text(trafilatura.extract(html) or "")
        except Exception:
            fetched_body = ""

    if len(fetched_body) > MAX_FETCH_CHARS:
        fetched_body = fetched_body[:MAX_FETCH_CHARS]

    return {
        "fetch_status": "ok" if fetched_body else "extract_failed",
        "fetched_url": url,
        "fetched_title": fetched_title,
        "fetched_body": fetched_body,
        "fetch_error": "",
    }
# ---------------------------------------------------------------------
# Input preprocessing
# ---------------------------------------------------------------------

def preprocess_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_first_url(text: str) -> str:
    if not text:
        return ""
    m = URL_RE.search(text)
    if not m:
        return ""
    return m.group(1).rstrip(".,);]>")


def parse_structured_content(content: str) -> Dict[str, str]:
    content = content.strip()

    url_match = re.search(r"^SOURCE_URL:\s*(.+)$", content, flags=re.MULTILINE)
    title_match = re.search(r"^TITLE:\s*(.+)$", content, flags=re.MULTILINE)
    body_match = re.search(r"^BODY:\s*([\s\S]*)$", content, flags=re.MULTILINE)

    return {
        "url": url_match.group(1).strip() if url_match else "",
        "title": title_match.group(1).strip() if title_match else "",
        "body": body_match.group(1).strip() if body_match else "",
    }


def normalize_domain(domain: str) -> str:
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def matches_domain(domain: str, candidates: set) -> bool:
    return any(domain == c or domain.endswith("." + c) for c in candidates)


def normalize_url(url: str) -> str:
    url = preprocess_text(url)
    if not url:
        return ""

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", url):
        url = "https://" + url

    return url


def assess_source(url: str) -> Dict[str, Any]:
    url = normalize_url(url)

    source = {
        "source_present": False,
        "source_url": "",
        "source_domain": "",
        "source_type": "none",
        "source_reputation": "unknown",
        "credible_source": False,
        "url_flags": [],
    }

    if not url:
        return source

    try:
        parsed = urlparse(url)
    except Exception:
        source["url_flags"] = ["invalid_url"]
        return source

    domain = normalize_domain(parsed.netloc)
    if not domain:
        source["url_flags"] = ["invalid_url"]
        return source

    flags: List[str] = []
    if parsed.scheme and parsed.scheme.lower() != "https":
        flags.append("no_https")
    if "@" in url:
        flags.append("userinfo_in_url")
    if "xn--" in domain:
        flags.append("punycode_domain")
    if domain.count("-") >= 3:
        flags.append("many_hyphens")
    if re.search(r"\d", domain):
        flags.append("digits_in_domain")

    source_type = "unknown"
    source_reputation = "unknown"

    if matches_domain(domain, SHORTENER_DOMAINS):
        source_type = "shortener"
        source_reputation = "low"
        flags.append("shortened_url")
    elif matches_domain(domain, SOCIAL_DOMAINS):
        source_type = "social"
        source_reputation = "low"
    elif matches_domain(domain, BLOG_LIKE_DOMAINS):
        source_type = "blog"
        source_reputation = "low"
    elif domain.endswith(".gov") or ".gov." in domain or domain.endswith(".mil") or ".mil." in domain or matches_domain(domain, {"gov.sg", "mas.gov.sg", "moh.gov.sg"}):
        source_type = "official_gov"
        source_reputation = "high"
    elif domain.endswith(".edu") or ".edu." in domain or domain.endswith(".ac.uk"):
        source_type = "official_institution"
        source_reputation = "high"
    elif matches_domain(domain, HIGH_TRUST_DOMAINS):
        source_type = "major_news"
        source_reputation = "high"
    elif matches_domain(domain, MEDIUM_TRUST_DOMAINS):
        source_type = "major_news"
        source_reputation = "medium"

    source["source_present"] = True
    source["source_url"] = url
    source["source_domain"] = domain
    source["source_type"] = source_type
    source["source_reputation"] = source_reputation
    source["credible_source"] = source_reputation in {"high", "medium"} and source_type in {
        "official_gov",
        "official_institution",
        "major_news",
    }
    source["url_flags"] = sorted(set(flags))

    return source


def build_model_content(
    url: str = "",
    title: str = "",
    body: str = "",
    fallback_content: str = "",
    fetched: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    url = preprocess_text(url) if url else ""
    title = preprocess_text(title) if title else ""
    body = preprocess_text(body) if body else ""
    fallback_content = preprocess_text(fallback_content) if fallback_content else ""
    fetched = fetched or {}

    inferred_url = url or extract_first_url_from_text(body) or extract_first_url_from_text(fallback_content)
    source = assess_source(inferred_url)

    # Attach fetch metadata to source_precheck so the response can show it
    source["fetch_status"] = fetched.get("fetch_status", "not_attempted")
    source["fetch_error"] = fetched.get("fetch_error", "")
    source["fetched_title"] = fetched.get("fetched_title", "")
    source["fetched_chars"] = len(fetched.get("fetched_body", "") or "")

    parts: List[str] = [
        f"SOURCE_PRESENT: {str(source['source_present']).lower()}",
        f"SOURCE_DOMAIN: {source['source_domain'] or 'none'}",
        f"SOURCE_TYPE: {source['source_type']}",
        f"SOURCE_REPUTATION: {source['source_reputation']}",
        f"CREDIBLE_SOURCE: {str(source['credible_source']).lower()}",
        f"URL_FLAGS: {', '.join(source['url_flags']) if source['url_flags'] else 'none'}",
        f"FETCH_STATUS: {source['fetch_status']}",
    ]

    if source["source_url"]:
        parts.append(f"SOURCE_URL: {source['source_url']}")

    if title:
        parts.append(f"USER_TITLE: {title}")
    if body:
        parts.append(f"USER_BODY: {body}")
    elif fallback_content:
        parts.append(f"USER_BODY: {fallback_content}")

    fetched_title = preprocess_text(fetched.get("fetched_title", "") or "")
    fetched_body = preprocess_text(fetched.get("fetched_body", "") or "")

    if fetched_title:
        parts.append(f"FETCHED_TITLE: {fetched_title}")
    if fetched_body:
        parts.append(f"FETCHED_BODY: {fetched_body}")

    return "\n".join(parts).strip(), source


async def normalize_request_content(req: "CompareRequest") -> Tuple[str, Dict[str, Any]]:
    url = (req.url or "").strip()
    title = (req.title or "").strip()
    body = (req.body or "").strip()
    raw_content = (req.content or "").strip()

    # Explicit structured fields
    if url or title or body:
        candidate_url = url or extract_first_url_from_text(body)
        fetched = await fetch_article_from_url(candidate_url) if candidate_url else None
        content, source = build_model_content(
            url=url,
            title=title,
            body=body,
            fetched=fetched,
        )
        if content:
            return content, source

    # Already structured content
    if raw_content:
        parsed = parse_structured_content(raw_content)
        if parsed["url"] or parsed["title"] or parsed["body"]:
            candidate_url = parsed["url"] or extract_first_url_from_text(parsed["body"])
            fetched = await fetch_article_from_url(candidate_url) if candidate_url else None
            return build_model_content(
                url=parsed["url"],
                title=parsed["title"],
                body=parsed["body"],
                fetched=fetched,
            )

        # Plain text content that may contain a URL
        candidate_url = extract_first_url_from_text(raw_content)
        fetched = await fetch_article_from_url(candidate_url) if candidate_url else None
        return build_model_content(
            fallback_content=raw_content,
            fetched=fetched,
        )

    raise HTTPException(status_code=422, detail="Provide content or at least one of url/title/body.")


def body_or_fallback_snippet(input_text: str, limit: int = 140) -> str:
    m = re.search(r"^BODY:\s*([\s\S]*)$", input_text, flags=re.MULTILINE)
    if m:
        body = m.group(1).strip()
        return body[:limit]
    return input_text.strip()[:limit]


# ---------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------

class CompareRequest(BaseModel):
    content: Optional[str] = Field(default=None)
    url: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None)
    body: Optional[str] = Field(default=None)


class CompareResponse(BaseModel):
    base_output: Dict[str, Any]
    lora_output: Dict[str, Any]
    comparison_metrics: Dict[str, Any]
    source_precheck: Dict[str, Any]
    normalized_content: str
    base_raw: Optional[str] = None
    lora_raw: Optional[str] = None


# ---------------------------------------------------------------------
# JSON extraction + validation
# ---------------------------------------------------------------------

REQUIRED_TOP_KEYS = {
    "verdict",
    "confidence",
    "sharing_policy",
    "signals",
    "evidence_spans",
    "description",
    "report",
}


def extract_first_valid_schema_json(decoded: str) -> str:
    decoded = decoded.strip()
    n = len(decoded)

    for i in range(n):
        if decoded[i] != "{":
            continue

        depth = 0
        in_string = False
        escape = False

        for j in range(i, n):
            ch = decoded[j]

            if escape:
                escape = False
                continue

            if ch == "\\":
                escape = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = decoded[i:j + 1]
                    try:
                        obj = json.loads(candidate)
                    except Exception:
                        continue
                    if isinstance(obj, dict) and REQUIRED_TOP_KEYS.issubset(obj.keys()):
                        return candidate
                    break

    raise ValueError("No valid schema JSON found in model output.")


def coerce_float(x: Any, default: float) -> float:
    try:
        return float(x)
    except Exception:
        return default


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def policy_from_verdict(verdict: str) -> str:
    if verdict == "likely_false":
        return "do_not_share"
    if verdict == "likely_true":
        return "allow"
    return "caution"


def sanitize_signals(signals: Any, source_precheck: Dict[str, Any]) -> List[str]:
    out: List[str] = []

    if isinstance(signals, list):
        for s in signals:
            if isinstance(s, str):
                cleaned = re.sub(r"[^a-zA-Z0-9_\- ]+", "", s).strip().replace(" ", "_").lower()
                if cleaned and cleaned not in out:
                    out.append(cleaned[:40])

    if not out:
        if not source_precheck.get("source_present"):
            out.append("no_source_url")
        elif source_precheck.get("source_reputation") in {"low", "unknown"}:
            out.append("weak_source")
        else:
            out.append("source_present")

    return out[:6]


def sanitize_evidence_spans(evidence_spans: Any, input_text: str) -> List[str]:
    out: List[str] = []

    if isinstance(evidence_spans, list):
        for ev in evidence_spans:
            if not isinstance(ev, str):
                continue
            ev = ev.strip()
            if not ev:
                continue
            if ev in input_text and ev not in out:
                out.append(ev[:160])

    if not out:
        snippet = body_or_fallback_snippet(input_text)
        if snippet:
            out.append(snippet)

    return out[:6]


def sanitize_to_schema(obj: Dict[str, Any], input_text: str, source_precheck: Dict[str, Any]) -> Dict[str, Any]:
    verdict = str(obj.get("verdict", "uncertain")).strip().lower()
    if verdict not in ALLOWED_VERDICTS:
        verdict = "uncertain"

    confidence = clamp(coerce_float(obj.get("confidence", 0.5), 0.5), 0, 1)

    sharing_policy = str(obj.get("sharing_policy", policy_from_verdict(verdict))).strip()
    if sharing_policy not in ALLOWED_POLICIES:
        sharing_policy = policy_from_verdict(verdict)

    signals = sanitize_signals(obj.get("signals", []), source_precheck)
    evidence_spans = sanitize_evidence_spans(obj.get("evidence_spans", []), input_text)

    description = preprocess_text(str(obj.get("description", "")))[:280]
    report = preprocess_text(str(obj.get("report", "")))[:900]

    if not description:
        description = (
            f"This item is assessed as {verdict} based on the available sourcing signals and text evidence."
        )

    if not report:
        report = (
            f"The model assessed this item as {verdict}. "
            f'Key evidence includes "{evidence_spans[0]}". '
            f"The recommended sharing policy is {sharing_policy}."
        )

    return {
        "verdict": verdict,
        "confidence": confidence,
        "sharing_policy": sharing_policy,
        "signals": signals,
        "evidence_spans": evidence_spans,
        "description": description,
        "report": report,
    }


def run_model(
    model_instance,
    system_prompt: str,
    content: str,
    source_precheck: Dict[str, Any],
) -> Dict[str, Any]:
    raw = generate_with_model(model_instance, system_prompt, content)
    valid_json = False

    try:
        schema_json_text = extract_first_valid_schema_json(raw)
        parsed = json.loads(schema_json_text)
        valid_json = True
    except Exception:
        try:
            parsed = json.loads(raw)
            valid_json = isinstance(parsed, dict)
        except Exception:
            parsed = {}

    sanitized = sanitize_to_schema(parsed if isinstance(parsed, dict) else {}, content, source_precheck)
    return {"raw": raw, "sanitized": sanitized, "valid_json": valid_json}


# ---------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------

def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def safe_list(x: Any) -> List[str]:
    if not isinstance(x, list):
        return []
    out: List[str] = []
    for item in x:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                out.append(cleaned)
    return out


def list_set(items: List[str]) -> set:
    return set(x for x in items if x)


def policy_rank(policy: str) -> int:
    return {"allow": 0, "caution": 1, "do_not_share": 2}.get(policy, 1)


def compute_comparison_metrics(
    base_s: Dict[str, Any],
    lora_s: Dict[str, Any],
    source_precheck: Dict[str, Any],
    base_valid_json: bool,
    lora_valid_json: bool,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}

    base_verdict = str(base_s.get("verdict", ""))
    lora_verdict = str(lora_s.get("verdict", ""))
    metrics["base_verdict"] = base_verdict
    metrics["lora_verdict"] = lora_verdict
    metrics["verdict_changed"] = base_verdict != lora_verdict

    base_conf = safe_float(base_s.get("confidence", 0.0), 0.0)
    lora_conf = safe_float(lora_s.get("confidence", 0.0), 0.0)
    metrics["base_confidence"] = round(base_conf, 3)
    metrics["lora_confidence"] = round(lora_conf, 3)
    metrics["confidence_delta"] = round(lora_conf - base_conf, 3)

    base_policy = str(base_s.get("sharing_policy", ""))
    lora_policy = str(lora_s.get("sharing_policy", ""))
    metrics["base_sharing_policy"] = base_policy
    metrics["lora_sharing_policy"] = lora_policy
    metrics["sharing_policy_changed"] = base_policy != lora_policy
    metrics["policy_delta"] = policy_rank(lora_policy) - policy_rank(base_policy)

    base_signals = safe_list(base_s.get("signals", []))
    lora_signals = safe_list(lora_s.get("signals", []))
    base_signal_set = list_set(base_signals)
    lora_signal_set = list_set(lora_signals)

    metrics["signal_counts"] = {
        "base_count": len(base_signals),
        "lora_count": len(lora_signals),
        "shared": sorted(list(base_signal_set.intersection(lora_signal_set)))[:10],
        "added_by_lora": sorted(list(lora_signal_set.difference(base_signal_set)))[:10],
        "removed_by_lora": sorted(list(base_signal_set.difference(lora_signal_set)))[:10],
    }

    base_evidence = safe_list(base_s.get("evidence_spans", []))
    lora_evidence = safe_list(lora_s.get("evidence_spans", []))
    base_ev_set = list_set(base_evidence)
    lora_ev_set = list_set(lora_evidence)

    metrics["evidence_counts"] = {
        "base_count": len(base_evidence),
        "lora_count": len(lora_evidence),
        "shared": sorted(list(base_ev_set.intersection(lora_ev_set)))[:10],
        "added_by_lora": sorted(list(lora_ev_set.difference(base_ev_set)))[:10],
        "removed_by_lora": sorted(list(base_ev_set.difference(lora_ev_set)))[:10],
    }

    metrics["json_validity"] = {
        "base_valid_json": base_valid_json,
        "lora_valid_json": lora_valid_json,
    }

    reasons: List[str] = []
    improved = False

    weak_source = (not source_precheck.get("source_present")) or source_precheck.get("source_reputation") in {"low", "unknown"}
    strong_source = source_precheck.get("source_reputation") == "high"

    if weak_source and base_verdict in {"likely_false", "likely_true"} and lora_verdict == "uncertain":
        improved = True
        reasons.append("LoRA softened judgment on weakly sourced content")

    if weak_source and policy_rank(lora_policy) > policy_rank(base_policy):
        improved = True
        reasons.append("LoRA applied a stricter policy on weak or unknown source input")

    if strong_source and base_verdict == "likely_false" and lora_verdict in {"uncertain", "likely_true"}:
        improved = True
        reasons.append("LoRA reduced over-rejection on stronger source input")

    if len(lora_evidence) > len(base_evidence):
        improved = True
        reasons.append("LoRA surfaced more grounded evidence spans")

    if (not base_valid_json) and lora_valid_json:
        improved = True
        reasons.append("LoRA improved JSON validity")

    metrics["improved"] = improved
    metrics["improvement_reasons"] = reasons or ["No clear improvement detected"]

    return metrics


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

@api_router.post("/compare", response_model=CompareResponse)
async def compare_models(req: CompareRequest):
    content, source_precheck = await normalize_request_content(req)

    base = run_model(base_model, UNIFIED_SYSTEM_PROMPT, content, source_precheck)
    lora = run_model(lora_model, UNIFIED_SYSTEM_PROMPT, content, source_precheck)

    base_s = base["sanitized"]
    lora_s = lora["sanitized"]

    metrics = compute_comparison_metrics(
        base_s,
        lora_s,
        source_precheck,
        base["valid_json"],
        lora["valid_json"],
    )

    return {
        "base_output": base_s,
        "lora_output": lora_s,
        "comparison_metrics": metrics,
        "source_precheck": source_precheck,
        "normalized_content": content,
        "base_raw": base["raw"][:8000] if isinstance(base["raw"], str) else None,
        "lora_raw": lora["raw"][:8000] if isinstance(lora["raw"], str) else None,
    }


@api_router.get("/")
async def root():
    return {
        "message": "INFO FORTRESS Compare-Only API",
        "endpoints": ["/api/compare"],
    }


app.include_router(api_router)