"""
server.py — INFO FORTRESS API  v3.0
=====================================
Backend: Ollama (llama3.2) + Llama Guard 3 + DuckDB
All data is real — no mocks. Every analysis is performed live by the LLM.
"""

#from turtle import title

from unittest import result

from fastapi import FastAPI, APIRouter, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import duckdb
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import json
import re
import httpx
import asyncio
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# ── Guardrails ────────────────────────────────────────────────────────────────
from guardrails import (
    guarded_ollama_chat,
    check_content_safety,
    GuardrailsViolation,
    GuardrailsResult,
    GUARD_MODEL,
    MAIN_MODEL,
    GUARDRAILS_ENABLED,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

DB_PATH = os.environ.get('DUCKDB_PATH', str(ROOT_DIR / 'infofortress.duckdb'))
OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')


def get_db() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH)


def init_db() -> None:
    con = get_db()
    con.execute("""
        CREATE TABLE IF NOT EXISTS status_checks (
            id        VARCHAR PRIMARY KEY,
            client_name VARCHAR NOT NULL,
            timestamp VARCHAR NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS analyzed_documents (
            id          VARCHAR PRIMARY KEY,
            title       VARCHAR,
            content     TEXT,
            doc_type    VARCHAR,
            source      VARCHAR,
            url         VARCHAR,
            created_at  VARCHAR,
            analysis    JSON
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS analyzed_claims (
            id             VARCHAR PRIMARY KEY,
            content        TEXT,
            source_url     VARCHAR,
            source_domain  VARCHAR,
            analysis_type  VARCHAR,
            created_at     VARCHAR,
            analysis       JSON
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS monitored_narratives (
            id          VARCHAR PRIMARY KEY,
            theme       VARCHAR,
            claim_count INTEGER DEFAULT 0,
            avg_risk    FLOAT DEFAULT 0,
            first_seen  VARCHAR,
            last_seen   VARCHAR,
            top_claims  JSON,
            created_at  VARCHAR
        )
    """)
    con.close()


init_db()

# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════

class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class DocumentAnalysisRequest(BaseModel):
    title: str
    content: str
    doc_type: str  # press_release | regulatory_circular | public_advisory | other
    source: str


class URLAnalysisRequest(BaseModel):
    url: str
    analysis_type: str = "news_article"   # news_article | social_post | blog | document
    content: Optional[str] = None          # paste-override if fetch is blocked


class ClaimAnalysisRequest(BaseModel):
    content: str
    source_platform: Optional[str] = "unknown"
    source_user: Optional[str] = "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# CREDIBLE/SATIRE-SOURCE REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

CREDIBLE_NEWS_SOURCES = {
    "ndtv.com", "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com",
    "nytimes.com", "washingtonpost.com", "theguardian.com", "cnn.com",
    "aljazeera.com", "thehindu.com", "indianexpress.com", "hindustantimes.com",
    "timesofindia.indiatimes.com", "economictimes.indiatimes.com",
    "news18.com", "firstpost.com", "scroll.in", "theprint.in",
    "bloomberg.com", "ft.com", "wsj.com", "economist.com",
    "france24.com", "dw.com", "abc.net.au", "cbc.ca",
    "npr.org", "pbs.org", "cbsnews.com", "nbcnews.com", "abcnews.go.com",
    "politico.com", "axios.com", "theatlantic.com", "foreignpolicy.com",
    "time.com", "newsweek.com", "usatoday.com", "latimes.com",
    "thewire.in", "caravan magazine.in", "livemint.com", "business-standard.com",
}
KNOWN_SATIRE_SOURCES = {
    "theonion.com", "babylonbee.com", "reductress.com",
    "thebeaverton.com", "waterfordwhispersnews.com", "newsthump.com",
    "thedailymash.co.uk", "thespoof.com", "clickhole.com",
}

def is_credible_source(url: str) -> tuple[bool, str]:
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        for src in CREDIBLE_NEWS_SOURCES:
            if domain == src or domain.endswith("." + src):
                return True, domain
        return False, domain
    except Exception:
        return False, "unknown"

def is_satire_source(url: str) -> tuple[bool, str]:
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        for src in KNOWN_SATIRE_SOURCES:
            if domain == src or domain.endswith("." + src):
                return True, domain
        return False, domain
    except Exception:
        return False, "unknown"

# ══════════════════════════════════════════════════════════════════════════════
# ARTICLE FETCHER  — multi-strategy extraction
# ══════════════════════════════════════════════════════════════════════════════

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _is_js_rendered(html: str) -> bool:
    """
    Returns True if the page looks like a JS shell with no real content.
    Detects common JS-framework empty root divs and checks visible text length.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Hard signals: common JS framework root divs with no children text
    js_markers = [
        soup.find("div", id="__next"),   # Next.js
        soup.find("div", id="app"),      # Vue / React
        soup.find("div", id="root"),     # React CRA
    ]
    for marker in js_markers:
        if marker and len(marker.get_text(strip=True)) < 100:
            logger.info("[JS-detect] Found empty JS framework root — needs Playwright")
            return True

    # Remove script/style/meta/link/noscript, then measure real text
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    visible_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
    logger.info(f"[JS-detect] Visible text length after strip: {len(visible_text)}")

    # Less than 500 chars of real text = likely a JS shell
    return len(visible_text) < 500


def _parse_html_bs4(html: str, base_url: str) -> Dict[str, Any]:
    """
    Parse article HTML with BeautifulSoup using multi-strategy content extraction.
    Returns dict with: title, content, image_count, source_count, sources.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ── DEBUG: Raw HTML snapshot ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"[DEBUG] Total raw HTML length: {len(html)}")
    #print(f"[DEBUG] First 500 chars of raw HTML:\n{html[:500]}")
    print("=" * 60)

    # Remove noise tags
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "iframe"]):
        tag.decompose()

    # ── DEBUG: After stripping noise ─────────────────────────────────────────
    all_text_after_strip = soup.get_text(separator=" ", strip=True)
    #print(f"\n[DEBUG] Visible text length after stripping noise tags: {len(all_text_after_strip)}")
    #print(f"[DEBUG] First 300 chars of visible text:\n{all_text_after_strip[:300]}")

    # ── DEBUG: All tags present ───────────────────────────────────────────────
    all_tags = set(tag.name for tag in soup.find_all())
    print(f"\n[DEBUG] Tags present in cleaned HTML: {sorted(all_tags)}")

    # ── DEBUG: All classes present ────────────────────────────────────────────
    all_classes: set = set()
    for tag in soup.find_all(class_=True):
        for c in tag.get("class", []):
            all_classes.add(c)
    #print(f"\n[DEBUG] All CSS classes found ({len(all_classes)} total):")
    content_related = [c for c in sorted(all_classes) if any(
        kw in c.lower() for kw in ["article", "story", "content", "live",
                                    "blog", "body", "main", "text", "post"]
    )]
    #print(f"  Content-related classes: {content_related}")
    #print(f"  All classes (first 80): {sorted(all_classes)[:80]}")

    # ── DEBUG: All IDs present ────────────────────────────────────────────────
    all_ids = [tag.get("id") for tag in soup.find_all(id=True)]
    #print(f"\n[DEBUG] All IDs found ({len(all_ids)} total): {all_ids[:40]}")

    # ── TITLE ─────────────────────────────────────────────────────────────────
    h1_tag     = soup.find("h1")
    og_title   = soup.find("meta", property="og:title")
    page_title = soup.find("title")

# Span/div headline fallback — many sites style their article title in a
# <span> or <div> with a class containing "title", "headline" or "heading"
    span_title = soup.find(
        ["span", "div"],
        class_=re.compile(r"title|headline|heading", re.I)
    )

    #print(f"\n[DEBUG] h1 tag: {h1_tag}")
    #print(f"[DEBUG] og:title meta: {og_title}")
    #print(f"[DEBUG] <title> tag: {page_title}")
    #print(f"[DEBUG] span/div title fallback: {span_title}")

    title = ""
    if h1_tag:
        title = h1_tag.get_text(strip=True)
    elif og_title:
        title = og_title.get("content", "")
    elif span_title:
        title = span_title.get_text(strip=True)
    elif page_title:
        title = page_title.get_text(strip=True)
    title = title or "Title not found"
    print(f"[DEBUG] Final title chosen: '{title}'")

    # ── CONTENT ───────────────────────────────────────────────────────────────
    content_selectors = [
        "article",
        {"class": re.compile(r"liveblog|live[-_]blog|live[-_]feed", re.I)},
        {"class": re.compile(
            r"article[-_]body|story[-_]body|post[-_]content|entry[-_]content"
            r"|article[-_]content|articleContent|storyContent", re.I)},
        {"id": re.compile(r"article[-_]body|story[-_]body|articleContent|storyContent|liveblog", re.I)},
        "main",
        {"role": "main"},
    ]
    content_el = None
    print(f"\n[DEBUG] Trying content selectors:")
    for sel in content_selectors:
        if isinstance(sel, str):
            found = soup.find(sel)
        else:
            found = soup.find(True, sel)
        print(f"  Selector {sel!r} → {'FOUND: ' + str(found)[:80] if found else 'not found'}")
        if found and not content_el:
            content_el = found

    if content_el:
        #print(f"\n[DEBUG] Content element tag: <{content_el.name}> "
        #      f"class={content_el.get('class')} id={content_el.get('id')}")
        print(f"[DEBUG] Content element text length: {len(content_el.get_text(strip=True))}")
    else:
        print(f"\n[DEBUG] No content element matched — falling back to <body>")
        if soup.body:
            children = [
                f"<{c.name} class={c.get('class', '')!r} id={c.get('id', '')!r}>"
                for c in soup.body.children if hasattr(c, 'name') and c.name
            ]
            print(f"[DEBUG] Body direct children: {children[:20]}")

    raw_content = (content_el or soup.body or soup).get_text(separator="\n", strip=True)
    content = re.sub(r"\n{3,}", "\n\n", raw_content).strip()
    print(f"\n[DEBUG] Final content length: {len(content)}")
    #print(f"[DEBUG] First 300 chars of content:\n{content[:300]}")

    # ── IMAGES ────────────────────────────────────────────────────────────────
    all_imgs = soup.find_all("img")
    print(f"\n[DEBUG] Total <img> tags found: {len(all_imgs)}")
    images = []
    for img in all_imgs:
        src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
        width  = int(img.get("width",  0) or 0)
        height = int(img.get("height", 0) or 0)
        print(f"  IMG src={src[:60]!r} w={width} h={height}")
        if width and height and (width < 50 or height < 50):
            continue
        if any(x in src.lower() for x in ["pixel", "tracker", "1x1", "beacon"]):
            continue
        if src:
            images.append(src)
    print(f"[DEBUG] Images after filtering: {len(images)}")

    # ── EXTERNAL SOURCES ──────────────────────────────────────────────────────
    base_origin = urlparse(base_url).netloc
    all_anchors = soup.find_all("a", href=True)
    print(f"\n[DEBUG] Total <a href> tags found: {len(all_anchors)}")
    seen: set = set()
    external_links = []
    for a in all_anchors:
        href = a["href"]
        try:
            abs_url = urljoin(base_url, href)
            parsed  = urlparse(abs_url)
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc == base_origin or parsed.netloc == "":
                continue
            if abs_url not in seen:
                seen.add(abs_url)
                external_links.append(abs_url)
        except Exception:
            continue
    print(f"[DEBUG] External unique links found: {len(external_links)}")
    if external_links:
        print(f"[DEBUG] First 5 external links: {external_links[:5]}")
    print("=" * 60 + "\n")

    return {
        "title":        title[:300],
        "content":      content[:8000],
        "image_count":  len(images),
        "source_count": len(external_links),
        "sources":      external_links[:15],
    }


async def _fetch_html_httpx(url: str) -> str:
    """Primary fetch: fast httpx with manual decompression fallback."""
    # Request identity to avoid compressed responses; httpx may still get them
    headers = {**_FETCH_HEADERS, "Accept-Encoding": "identity"}

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=20.0,
        verify=False,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

        content_bytes = resp.content
        # Detect binary/compressed response despite identity request
        if len(content_bytes) > 2 and content_bytes[0] in (0x1f, 0x78, 0xce, 0x28):
            logger.info("[httpx] Response appears compressed — attempting manual decompress")
            for label, decompress_fn in [
                ("gzip",   lambda b: __import__("gzip").decompress(b)),
                ("brotli", lambda b: __import__("brotli").decompress(b)),
                ("zlib",   lambda b: __import__("zlib").decompress(b, -15)),
            ]:
                try:
                    text = decompress_fn(content_bytes).decode("utf-8", errors="replace")
                    logger.info(f"[httpx] {label} decompress succeeded, length={len(text)}")
                    return text
                except Exception:
                    continue
            raise ValueError("Response is compressed binary and could not be decompressed")

        text = resp.text
        logger.info(f"[httpx] Plain text response, length={len(text)}, starts: {text[:80]!r}")
        return text


async def _fetch_html_playwright(url: str) -> str:
    """Fallback fetch: full browser rendering via Playwright."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=_FETCH_HEADERS["User-Agent"],
            java_script_enabled=True,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()

        # Block heavy assets to speed up load
        await page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
            lambda route: route.abort()
        )

        logger.info(f"[Playwright] Navigating to {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)

        # Wait for meaningful content via common article selectors
        for sel in ["article", "h1", '[class*="article"]', '[class*="story"]',
                    '[class*="liveblog"]', '[class*="live-blog"]', "main"]:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                logger.info(f"[Playwright] Found selector: {sel}")
                break
            except Exception:
                continue

        await asyncio.sleep(3)   # allow JS hydration to settle
        html = await page.content()
        await browser.close()
        logger.info(f"[Playwright] Got HTML length: {len(html)}")
        return html


async def fetch_article(url: str) -> Dict[str, Any]:
    """
    Fetch a URL and extract structured article content.

    Fetch strategy (in order):
      1. httpx  — fast, no JS execution.
      2. If the page looks JS-rendered or httpx fails → Playwright full browser.

    Parse strategy: BeautifulSoup with multi-selector content extraction,
    including <article>, common content-wrapper class/id heuristics, and
    full <p> fallback.

    Returns a dict with keys:
      success, title, description, author, published_date, content,
      word_count, url, error, method_used, image_count, source_count, sources.
    """
    print(f"[FETCH] Start fetch_article") #url={url}
    html: Optional[str] = None
    method_used = "httpx+BeautifulSoup"

    # ── Stage 1: httpx ────────────────────────────────────────────────────────
    try:
        html = await _fetch_html_httpx(url)
        if _is_js_rendered(html):
            logger.info("[FETCH] JS-rendered page detected — switching to Playwright")
            html = None   # discard and fall through to Playwright
    except Exception as e:
        logger.info(f"[FETCH] httpx failed ({e}) — trying Playwright")

    # ── Stage 2: Playwright fallback ──────────────────────────────────────────
    if html is None:
        method_used = "Playwright+BeautifulSoup"
        try:
            html = await _fetch_html_playwright(url)
        except Exception as e:
            return {
                "success": False,
                "error": f"Both httpx and Playwright failed: {e}",
                "url": url,
                "title": "", "description": "", "author": "",
                "published_date": "", "content": "", "word_count": 0,
            }

    print(f"[FETCH] HTML acquired via {method_used}, length={len(html)}")

    # ── Stage 3: BeautifulSoup parse ─────────────────────────────────────────
    try:
        parsed = _parse_html_bs4(html, url)
    except Exception as e:
        return {
            "success": False,
            "error": f"HTML parse failed: {e}",
            "url": url,
            "title": "", "description": "", "author": "",
            "published_date": "", "content": "", "word_count": 0,
        }

    # ── Extract og:/meta fields (fresh soup — noise already stripped inside parse) ──
    meta_soup = BeautifulSoup(html, "html.parser")

    def _meta(prop: str) -> str:
        for attr, val in [("property", f"og:{prop}"), ("name", prop)]:
            tag = meta_soup.find("meta", {attr: val})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    description    = _meta("description")
    author         = _meta("author")
    published_date = _meta("article:published_time") or _meta("pubdate")

    content = parsed["content"]

    # Fallback: if body extraction was thin, use description
    if len(content) < 150:
        content = description
        #print(f"[FETCH] Thin body — falling back to og:description, len={len(content)}")

    #print(f"[FETCH] Done: title={parsed['title']!r} words={len(content.split())} "
    #      f"method={method_used}")

    return {
        "success":        True,
        "title":          parsed["title"],
        "description":    description[:500],
        "author":         author,
        "published_date": published_date,
        "content":        content,
        "word_count":     len(content.split()),
        "url":            url,
        "error":          None,
        "method_used":    method_used,
        "image_count":    parsed["image_count"],
        "source_count":   parsed["source_count"],
        "sources":        parsed["sources"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# JSON PARSE HELPER
# ══════════════════════════════════════════════════════════════════════════════

def _parse_json(text: str) -> Optional[dict]:
    # Try direct parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # Extract first {...} block
    try:
        s = text.find("{")
        e = text.rfind("}") + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# AI ANALYSIS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

async def analyze_document_with_ai(
    title: str, content: str, doc_type: str, source: str = ""
) -> Dict[str, Any]:
    """Deep analysis of an official document for misinformation markers."""

    system_msg = """You are a senior misinformation analyst with expertise in government communications,
legal language, and institutional integrity. Your job is to rigorously analyse official documents.

Rules:
- Base findings ONLY on the document text provided.
- Be specific: quote or paraphrase the exact phrases that concern you.
- risk_score: 0 (no issues) → 100 (severe fabrication/harm).
- overconfidence_score: measures unsupported absolute claims (e.g. "will definitely", "guaranteed").
- Respond with ONLY valid JSON — no markdown fences, no preamble."""

    user_msg = f"""Analyse this official {doc_type} from "{source}":

TITLE: {title}

FULL TEXT:
{content}

Return ONLY this JSON object:
{{
  "risk_score": <integer 0-100>,
  "fabrication_detected": <true|false>,
  "fabrication_details": "<specific fabricated references, non-existent laws/protocols cited, or null>",
  "legal_issues": [
    "<each specific legal or regulatory problem found>"
  ],
  "overconfidence_score": <integer 0-100>,
  "overconfident_phrases": [
    "<exact phrases that make unsupported absolute claims>"
  ],
  "harmful_claims": [
    "<claims that could cause public harm if believed>"
  ],
  "missing_disclosures": [
    "<important context or caveats the document omits>"
  ],
  "tone_analysis": "<neutral|alarmist|dismissive|manipulative|professional>",
  "credibility_markers": [
    "<positive indicators of legitimacy e.g. cited sources, official letterhead references>"
  ],
  "summary": "<2-3 sentence objective assessment>",
  "recommendations": [
    "<actionable steps for fact-checkers or the public>"
  ]
}}"""

    result = await guarded_ollama_chat(system_msg, user_msg)
    
    if isinstance(result, GuardrailsViolation):
        print(f"[644] LLM blocked stage={result.stage} cats={result.categories} msg={result.message}")
    else:
        print(f"[RISK-DEBUG][646] Raw LLM content length={len(result.content)}")
        print(f"[647] LLM output chars={len(result.content)} preview={result.content[:200]!r}")

    if isinstance(result, GuardrailsViolation):
        print("Guard blocked document analysis: %s", result.message)
        return {
            "risk_score": 0, "fabrication_detected": False, "fabrication_details": None,
            "legal_issues": [], "overconfidence_score": 0, "overconfident_phrases": [],
            "harmful_claims": [], "missing_disclosures": [], "tone_analysis": "unknown",
            "credibility_markers": [],
            "summary": f"Analysis blocked by safety guardrails: {result.message}",
            "recommendations": ["Review and resubmit content."],
            "guardrails_blocked": True,
            "guard_violation": result.to_dict(),
        }

    parsed = _parse_json(result.content)
    if parsed:
        parsed["guardrails_passed"] = True
        print(f"[RISK-DEBUG][665] risk_score in parsed: {parsed.get('risk_score', 'KEY MISSING')}")
        print(f"[RISK-DEBUG][666] veracity_assessment: {parsed.get('veracity_assessment', 'KEY MISSING')}")
        return parsed
    else:
        print(f"[RISK-DEBUG][667] _parse_json returned None — JSON parse FAILED")
        print(f"[RISK-DEBUG][668] Raw text that failed to parse:\n{result.content}")
    # LLM returned non-JSON — return raw with flag
    return {
        "risk_score": 0, "fabrication_detected": False, "fabrication_details": None,
        "legal_issues": [], "overconfidence_score": 0, "overconfident_phrases": [],
        "harmful_claims": [], "missing_disclosures": [], "tone_analysis": "unknown",
        "credibility_markers": [],
        "summary": result.content[:500] if result.content else "No analysis returned.",
        "recommendations": ["Manual review required — AI returned unstructured output."],
        "guardrails_passed": True,
        "raw_response": result.content[:1000],
    }


async def analyze_url_with_ai(
    article: Dict[str, Any],
    analysis_type: str,
    is_credible: bool,
    source_domain: str,
) -> Dict[str, Any]:
    """Full misinformation analysis of a fetched article/URL."""
    is_satire, _ = is_satire_source(article["url"])
    # ── Build credibility context ─────────────────────────────────────────
    if is_credible:
        credibility_note = (
        f"SOURCE VERDICT: {source_domain} is a VERIFIED CREDIBLE NEWS OUTLET. "
        "Standard breaking-news journalism is factual reporting — NOT manipulation. "
        "ONLY flag manipulation_indicators if you find a concrete rhetorical device "
        "designed to deceive. An empty list [] is correct when none are present."
    )
    elif source_domain in KNOWN_SATIRE_SOURCES:
        credibility_note = (
        f"SOURCE VERDICT: {source_domain} is a KNOWN SATIRE/PARODY OUTLET. "
        "Content is intentionally fictional and humorous, NOT factual reporting. "
        "risk_score should reflect how dangerous this content is if mistaken for "
        "real news — minimum 35, higher if the claims could easily fool readers."
    )
    else:
        credibility_note = (
        f"SOURCE VERDICT: {source_domain} is NOT in the verified credible-source registry. "
        "Apply careful scrutiny, but still base every finding on evidence in the text."
    )
    print("Line number 726:", is_credible, credibility_note)

    content_block = (
        f"TITLE: {article['title']}\n"
        f"AUTHOR: {article.get('author', 'Unknown')}\n"
        f"PUBLISHED: {article.get('published_date', 'Unknown')}\n"
        f"DESCRIPTION: {article.get('description', '')}\n\n"
        f"BODY TEXT ({article.get('word_count', 0)} words extracted):\n{article['content']}"
    )

    system_msg = """You are a senior fact-checker at an international wire agency.
Your job is to produce a nuanced, evidence-based risk score for every piece of content.

RISK SCORE SCALE — use the full 0-100 range:
- 0-15:  Verified factual reporting. Named official sources, cross-verified facts,
         credible outlet, no manipulative framing.
- 16-30: Mostly reliable. Minor gaps in sourcing or slightly sensational headline
         but core claims are factual and verifiable.
- 31-45: Mixed reliability. Some unverified claims, anonymous sources only,
         opinion presented alongside facts, or minor factual inaccuracies.
- 46-60: Questionable. Multiple unverified claims, misleading framing, missing
         critical context, or content from an unverified source with no corroboration.
- 61-75: Likely problematic. Demonstrably false claims, heavy emotional manipulation,
         fabricated quotes, or satire/parody that could easily be mistaken for real news.
- 76-90: High risk. Deliberate misinformation, conspiracy content, fabricated evidence,
         or content designed to deceive with specific harmful intent.
- 91-100: Critical. Dangerous health/safety misinformation, incitement, or content
          that is both demonstrably false AND likely to cause direct harm if believed.

CONTENT TYPE SCORING GUIDANCE:
- Breaking news from credible outlet with named official source: 5-20
- Breaking news from credible outlet, anonymous sources only: 20-35
- News from unverified outlet, claims plausible and internally consistent: 35-50
- News from unverified outlet, claims unverifiable or inconsistent: 50-65
- Clearly labelled satire/parody on known satire site: 40-55
- Satire that could plausibly be mistaken for real news: 60-75
- Opinion or analysis piece, clearly labelled: 25-45
- Content making specific false factual claims with evidence: 70-90
- Health/safety misinformation or incitement content: 85-100

HARD RULES:
1. You MUST pick a specific integer, not just 0 or 100. Reserve 0 for content
   that is fully verified by multiple named official sources. Reserve 100 only
   for content that is both demonstrably false AND poses immediate safety risk.
2. "manipulation_indicators" must list CONCRETE deceptive techniques found verbatim
   in the text. If you cannot cite a specific example, return [].
3. "emotional_language" means words chosen TO MANIPULATE — propaganda terms, slurs,
   deliberate fear-mongering. Words like "killed", "died", "crash" are factual
   descriptions, NOT emotional triggers. Do NOT list them.
4. Your training data has a cutoff date. Recent events you have not heard of are NOT
   automatically false.
5. Respond with ONLY valid JSON — no markdown fences, no explanation outside JSON."""

    # Keep the article snippet short so the LLM has enough token budget for the JSON response
    article_snippet = article["content"][:3000]
    if len(article["content"]) > 3000:
        article_snippet += "\n[... article continues ...]"

    content_block_trimmed = (
        f"TITLE: {article['title']}\n"
        f"AUTHOR: {article.get('author', 'Unknown')}\n"
        f"PUBLISHED: {article.get('published_date', 'Unknown')}\n"
        f"DESCRIPTION: {article.get('description', '')}\n\n"
        f"BODY (first 3000 chars):\n{article_snippet}"
    )

    user_msg = f"""Analyse this {analysis_type}.

{credibility_note}

{content_block_trimmed}

IMPORTANT: Your ENTIRE response must be a single valid JSON object. Do NOT write anything before or after the JSON. Do NOT use markdown. Close every array and object bracket. If you run out of space, use empty arrays [] rather than leaving brackets open.

Return this JSON:
{{
  "risk_score": <0-100>,
  "veracity_assessment": "<verified|likely_true|uncertain|likely_false|false>",
  "article_type": "<breaking_news|investigative|opinion|analysis|satire|press_release|misinformation|unknown>",
  "source_credibility": "<high|medium|low|unknown>",
  "headline_accuracy": "<accurate|slightly_sensational|misleading|clickbait|fabricated>",
  "sourcing_quality": {{"named_sources": <int>, "anonymous_sources": <int>, "documents_cited": <int>, "expert_quotes": <int>, "assessment": "<well-sourced|adequately-sourced|poorly-sourced|unsourced>"}},
  "claims": [{{"claim": "<claim text>", "assessment": "<verified|plausible|unverified|false|misleading>", "concern": "<concern or null>"}}],
  "manipulation_indicators": [],
  "emotional_language": [],
  "missing_context": [],
  "strengths": ["<strength 1>", "<strength 2>"],
  "concerns": [],
  "fact_check_priorities": ["<priority 1>"],
  "summary": "<3-4 sentence assessment>",
  "recommended_action": "<trust|verify|caution|flag|do_not_share>"
}}"""

    # First run a standalone safety screen on the article text. If the INPUT
    # itself violates our guardrails we skip the expensive LLM call and return a
    # high‑risk result immediately. Previously this check was only recorded in
    # the response body, which meant callers would still perform the analysis and
    # then fall back to the generic 50‑score when the LLM output was invalid. The
    # bug report described exactly that: "risk_score is not accurate, if it is a
    # violation also it is giving 50 as risk."
    safety_check = await check_content_safety(article.get("content", "") + " " + article.get("title", ""))

    # if the raw content failed the safety screen, short‑circuit with max risk
    if not safety_check.get("safe", True):
        logger.warning("Safety check flagged input for url=%s categories=%s",
                       article.get("url"), safety_check.get("violated_categories"))
        return {
            "url": article.get("url"),
            "article_title": article.get("title"),
            "article_author": article.get("author", ""),
            "article_published": article.get("published_date", ""),
            "article_description": article.get("description", ""),
            "word_count": article.get("word_count", 0),
            "source_domain": source_domain,
            "is_credible_source": is_credible,
            "safety_check": safety_check,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "risk_score": 100,
            "veracity_assessment": "blocked",
            "article_type": "unknown",
            "source_credibility": "unknown",
            "headline_accuracy": "unknown",
            "sourcing_quality": {"assessment": "unknown"},
            "claims": [],
            "manipulation_indicators": [],
            "emotional_language": [],
            "missing_context": [],
            "strengths": [],
            "concerns": [],
            "fact_check_priorities": [],
            "summary": "Input text blocked by safety guardrails.",
            "recommended_action": "do_not_share",
            "guardrails_blocked": True,
        }

    result = await guarded_ollama_chat(system_msg, user_msg)
    print(f"[DEBUG][823] LLM result type: {result}")

    base = {
        "url": article["url"],
        "article_title": article["title"],
        "article_author": article.get("author", ""),
        "article_published": article.get("published_date", ""),
        "article_description": article.get("description", ""),
        "word_count": article.get("word_count", 0),
        "source_domain": source_domain,
        "is_credible_source": is_credible,
        "safety_check": safety_check,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    if isinstance(result, GuardrailsViolation):
        return {
            **base,
            "risk_score": 100,
            "veracity_assessment": "blocked",
            "article_type": "unknown",
            "source_credibility": "unknown",
            "headline_accuracy": "unknown",
            "sourcing_quality": {"assessment": "unknown"},
            "claims": [],
            "manipulation_indicators": [],
            "emotional_language": [],
            "missing_context": [],
            "strengths": [],
            "concerns": [],
            "fact_check_priorities": [],
            "summary": f"Analysis blocked by safety guardrails: {result.message}",
            "recommended_action": "do_not_share",
            "guardrails_blocked": True,
            "guard_violation": result.to_dict(),
        }

    parsed = _parse_json(result.content)

    # Validate the parsed result has the minimum required fields and sane values.
    # llama3.2 sometimes returns truncated JSON where arrays are cut mid-string,
    # producing nonsense values. We detect this and fall back to safe defaults.
    def _is_valid_parse(p: dict) -> bool:
        if not isinstance(p, dict):
            print(f"[RISK-DEBUG][873] _is_valid_parse FAIL: not a dict, got {type(p)}")
            return False
        # Must have a numeric risk_score
        try:
            float(p.get("risk_score", "x"))
        except (TypeError, ValueError):
            print(f"[RISK-DEBUG][873] _is_valid_parse FAIL: risk_score not numeric, value={p.get('risk_score')!r}")
            return False
        # Must have a non-empty veracity string that is one of the expected values
        valid_veracity = {"verified", "likely_true", "uncertain", "likely_false",
                          "false", "requires_context", "blocked"}
        if p.get("veracity_assessment", "") not in valid_veracity:
            print("Line number 896: veracity_assessment: " , p.get("veracity_assessment"))
            return False
        # All list fields must actually be lists (not strings / None)
        for key in ("claims", "manipulation_indicators", "emotional_language",
                    "strengths", "concerns", "missing_context", "fact_check_priorities"):
            val = p.get(key)
            if val is not None and not isinstance(val, list):
                return False
        # sourcing_quality must be a dict if present
        sq = p.get("sourcing_quality")
        if sq is not None and not isinstance(sq, dict):
            return False
        # Filter garbage strings from all list fields (LLM template leakage)
        for key in ("claims", "manipulation_indicators", "emotional_language",
                    "strengths", "concerns", "missing_context", "fact_check_priorities"):
            if isinstance(p.get(key), list):
                p[key] = [
                    item for item in p[key]
                    if isinstance(item, (str, dict))
                    and (isinstance(item, dict) or (
                        len(str(item).strip()) > 3
                        and not str(item).strip().startswith("<")
                        and not str(item).strip().upper().startswith("ONLY")
                        and not str(item).strip().startswith("na.")
                        and not str(item).strip() == "null"
                    ))
                ]
        return True

    if parsed and _is_valid_parse(parsed):
        # If the standalone safety check earlier flagged the input, override the
        # model‑generated risk score to ensure we don't return a misleading low
        # value. This covers the case where the LLM produced valid JSON but the
        # content itself was unsafe (the bug report complained about a 50 risk
        # score for violations).
        if not safety_check.get("safe", True):
            parsed["risk_score"] = max(parsed.get("risk_score", 0), 100)
            parsed["recommended_action"] = "do_not_share"
            parsed["guardrails_blocked"] = True
            print(f"[Risk_Debug][918]  Final risk_score: {parsed.get("risk_score")}")
        return {**base, **parsed, "guardrails_passed": True}

    # Log raw response for debugging
    logger.warning("analyze_url_with_ai: invalid/truncated LLM JSON. Raw: %s",
                   (result.content or "")[:400])

    # choose a sensible default risk depending on safety check result.  If the
    # LLM output contained any hint of a guardrails block we bump to 100 even if
    # the safety check passed, because the analysis is effectively unusable.
    fallback_risk = 50
    fallback_action = "verify"
    raw_out = (result.content or "").lower()
    if not safety_check.get("safe", True) or "guardrails" in raw_out or "blocked" in raw_out or "unsafe" in raw_out:
        fallback_risk = 100
        fallback_action = "do_not_share"
    return {
        **base,
        "risk_score": fallback_risk,
        "veracity_assessment": "uncertain",
        "article_type": "unknown",
        "source_credibility": "unknown" if not is_credible else "medium",
        "headline_accuracy": "unknown",
        "sourcing_quality": {"assessment": "unknown"},
        "claims": [],
        "manipulation_indicators": [],
        "emotional_language": [],
        "missing_context": [],
        "strengths": [],
        "concerns": ["AI returned unstructured output — manual review required."],
        "fact_check_priorities": [],
        "summary": result.content[:600] if result.content else "No analysis returned.",
        "recommended_action": fallback_action,
        "guardrails_passed": True,
        "raw_llm_output": (result.content or "")[:500],
    }


async def analyze_claim_with_ai(
    claim_content: str,
    source_platform: str = "unknown",
    source_user: str = "unknown",   #determining risk for all categories
) -> Dict[str, Any]:
    """Analyse a short social-media claim or text snippet."""

    system_msg = """You are a senior fact-checker assessing the risk level of a piece of text.
Your job is to produce a nuanced, evidence-based risk score — not just 0 or 100.

RISK SCORE SCALE — use the full 0-100 range:
- 0-15:  Factual claim with named official source, fully verifiable, no manipulation.
- 16-30: Mostly credible. Minor sourcing gaps but core claim is plausible and consistent.
- 31-45: Mixed. Some unverified elements, vague sourcing, or minor misleading framing.
- 46-60: Questionable. Unverified claims, missing context, or from an untrusted source
         with no corroboration available.
- 61-75: Likely false or manipulative. Demonstrably incorrect elements, heavy emotional
         manipulation, or rumour presented as established fact.
- 76-90: High risk. Deliberate misinformation, fabricated claims, conspiracy narrative,
         or content designed to deceive.
- 91-100: Critical. Dangerous misinformation posing direct safety risk, incitement,
          or content that is both provably false AND immediately harmful.

CLAIM TYPE SCORING GUIDANCE:
- News report with named police/official/hospital source: 5-20
- News report with no named source but plausible claims: 25-40
- Social media post with verifiable external link: 30-50
- Social media post with unverifiable claims: 45-65
- Forwarded message with sensational unverified claim: 55-70
- Conspiracy or pseudoscience claim: 65-85
- Deliberate hoax or fabricated screenshot: 75-95

HARD RULES:
1. You MUST pick a specific integer in the range that fits the evidence.
   Do NOT default to 0 or 100 unless the content perfectly matches those
   extreme definitions above.
2. "manipulation_tactics" requires a SPECIFIC named tactic WITH a quoted example.
   If no such tactic exists, return []. Empty list is correct for factual reports.
3. "emotional_triggers" means words deliberately chosen to bypass rational thinking —
   propaganda slogans, dehumanising language. Words like "killed", "died", "crash",
   "victims" are factual descriptions — NOT emotional triggers.
4. Do NOT penalise a report for lacking information not yet available at time of writing.
5. Respond with ONLY valid JSON — no markdown, no preamble."""

    claim_snippet = claim_content[:2000]

    user_msg = f"""Assess this text posted on {source_platform} by {source_user}.

TEXT:
{claim_snippet}

IMPORTANT: Your ENTIRE response must be a single valid JSON object. Do NOT write anything before or after the JSON. Do NOT use markdown. Close every array and object bracket. If you run out of space, use empty arrays [] rather than leaving brackets open.

Return this JSON:
{{
  "risk_score": <0-100>,
  "veracity_assessment": "<likely_true|uncertain|likely_false|false|requires_context>",
  "claim_type": "<news_report|factual_claim|opinion|satire|rumour|conspiracy|propaganda|legitimate_concern>",
  "manipulation_tactics": [],
  "emotional_triggers": [],
  "red_flags": [],
  "legitimate_elements": ["<verifiable element 1>"],
  "missing_context": [],
  "fact_check_suggestion": "<what to verify>",
  "potential_harm": "<low|medium|high|critical> — <reason>",
  "summary": "<2-3 sentence assessment>",
  "recommended_action": "<ignore|monitor|flag|urgent_response>"
}}"""

    # Run an early safety screen and bail out if the claim text itself is
    # flagged. Without this we would still send the text to the LLM and then
    # potentially return the 50‑score fallback when parsing failed, which is
    # misleading for a content violation.
    safety_check = await check_content_safety(claim_content)
    if not safety_check.get("safe", True):
        logger.warning("Safety check flagged claim content platform=%s user=%s",
                       source_platform, source_user)
        return {
            "content": claim_content,
            "source_platform": source_platform,
            "source_user": source_user,
            "safety_check": safety_check,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "risk_score": 100,
            "veracity_assessment": "blocked",
            "claim_type": "unknown",
            "manipulation_tactics": [],
            "emotional_triggers": [],
            "red_flags": [],
            "legitimate_elements": [],
            "missing_context": [],
            "fact_check_suggestion": "Content blocked by safety guardrails.",
            "potential_harm": "critical",
            "summary": "Claim text blocked by safety guardrails.",
            "recommended_action": "urgent_response",
            "guardrails_blocked": True,
        }

    result = await guarded_ollama_chat(system_msg, user_msg)

    base = {
        "content": claim_content,
        "source_platform": source_platform,
        "source_user": source_user,
        "safety_check": safety_check,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }

    if isinstance(result, GuardrailsViolation):
        logger.warning(f"[L2] LLM blocked stage={result.stage} cats={result.categories}")
        print(f"[1048] LLM blocked stage={result.stage} cats={result.categories}")
        return {
            **base,
            "risk_score": 100,
            "veracity_assessment": "blocked",
            "claim_type": "unknown",
            "manipulation_tactics": [],
            "emotional_triggers": [],
            "red_flags": [],
            "legitimate_elements": [],
            "missing_context": [],
            "fact_check_suggestion": "Content blocked — do not propagate.",
            "potential_harm": "critical",
            "summary": f"Blocked by safety guardrails: {result.message}",
            "recommended_action": "urgent_response",
            "guardrails_blocked": True,
            "guard_violation": result.to_dict(),
        }
    else:
        print(f"[1067] LLM output chars={len(result.content)} preview={result.content[:100]!r}")
        

    parsed = _parse_json(result.content)

    def _is_valid_claim_parse(p: dict) -> bool:
        if not isinstance(p, dict):
            return False
        try:
            float(p.get("risk_score", "x"))
        except (TypeError, ValueError):
            return False
        valid_veracity = {"likely_true", "uncertain", "likely_false", "false",
                          "requires_context", "blocked", "verified"}
        if p.get("veracity_assessment", "") not in valid_veracity:
            return False
        for key in ("manipulation_tactics", "emotional_triggers", "red_flags",
                    "legitimate_elements", "missing_context"):
            val = p.get(key)
            if val is not None and not isinstance(val, list):
                return False
        # Clean garbage strings
        for key in ("manipulation_tactics", "emotional_triggers", "red_flags",
                    "legitimate_elements", "missing_context"):
            if isinstance(p.get(key), list):
                p[key] = [
                    item for item in p[key]
                    if isinstance(item, str)
                    and len(item.strip()) > 3
                    and not item.strip().startswith("<")
                    and not item.strip().upper().startswith("ONLY")
                    and not item.strip() == "null"
                ]
        return True

    if parsed and _is_valid_claim_parse(parsed):
        if not safety_check.get("safe", True):
            parsed["risk_score"] = max(parsed.get("risk_score", 0), 100)
            parsed["recommended_action"] = "urgent_response"
            parsed["guardrails_blocked"] = True
        return {**base, **parsed, "guardrails_passed": True}

    logger.warning("analyze_claim_with_ai: invalid/truncated LLM JSON. Raw: %s",
                   (result.content or "")[:400])

    fallback_risk = 50
    fallback_action = "verify"
    raw_out = (result.content or "").lower()
    if not safety_check.get("safe", True) or "guardrails" in raw_out or "blocked" in raw_out or "unsafe" in raw_out:
        fallback_risk = 100
        fallback_action = "urgent_response"
    return {
        **base,
        "risk_score": fallback_risk,
        "veracity_assessment": "uncertain",
        "claim_type": "unknown",
        "manipulation_tactics": [],
        "emotional_triggers": [],
        "red_flags": [],
        "legitimate_elements": [],
        "missing_context": [],
        "fact_check_suggestion": "Manual review required — AI returned unstructured output.",
        "potential_harm": "medium",
        "summary": result.content[:400] if result.content else "No analysis returned.",
        "recommended_action": fallback_action,
        "guardrails_passed": True,
        "raw_llm_output": (result.content or "")[:500],
    }


async def compute_narrative_risk_index() -> Dict[str, Any]:
    """Compute NRI from real data in the DB."""
    con = get_db()

    # Layer 1: document risk
    docs = con.execute("""
        SELECT JSON_EXTRACT(analysis, '$.risk_score') as rs
        FROM analyzed_documents
        WHERE created_at >= ?
    """, [(datetime.now(timezone.utc) - timedelta(days=7)).isoformat()]).fetchall()

    # Layer 2: claim risk
    claims = con.execute("""
        SELECT JSON_EXTRACT(analysis, '$.risk_score') as rs
        FROM analyzed_claims
        WHERE created_at >= ?
    """, [(datetime.now(timezone.utc) - timedelta(days=7)).isoformat()]).fetchall()

    con.close()

    def _avg(rows):
        vals = [float(r[0]) for r in rows if r[0] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    l1 = _avg(docs)
    l2 = _avg(claims)
    l3 = max(l1, l2) * 0.9   # systemic = blended proxy

    overall = l1 * 0.25 + l2 * 0.45 + l3 * 0.30

    alerts = []
    if l2 > 70:
        alerts.append("HIGH ALERT: Elevated public claim risk detected in last 7 days")
    if l1 > 50:
        alerts.append("WARNING: High-risk official documents detected recently")
    if overall > 60:
        alerts.append("SYSTEM ALERT: Narrative Risk Index exceeds safe threshold")
    if not docs and not claims:
        alerts.append("INFO: No recent analysis data — submit documents or URLs to populate the index")

    return {
        "overall_score":  round(overall, 1),
        "layer1_score":   round(l1, 1),
        "layer2_score":   round(l2, 1),
        "layer3_score":   round(l3, 1),
        "doc_count":      len(docs),
        "claim_count":    len(claims),
        "trend":          "rising" if overall > 60 else "stable" if overall > 30 else "low",
        "alerts":         alerts,
        "last_updated":   datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# APP & ROUTER
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="INFO FORTRESS - Misinformation Prevention Platform")
api_router = APIRouter(prefix="/api")

@app.middleware("http")
async def log_requests(request, call_next):
    start = datetime.now(timezone.utc)
    logger.debug(f"[API] -> {request.method} {request.url.path} query={dict(request.query_params)}")

    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"[API] !! Exception on {request.method} {request.url.path}: {e}")
        raise

    ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    logger.debug(f"[API] <- {request.method} {request.url.path} status={response.status_code} ms={ms:.1f}")
    return response
# ── Meta ──────────────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {
        "message": "INFO FORTRESS - Misinformation Prevention Platform",
        "version": "3.0.0",
        "llm_backend": f"Ollama ({MAIN_MODEL})",
        "guardrails_model": GUARD_MODEL,
        "guardrails_enabled": GUARDRAILS_ENABLED,
        "db_backend": "DuckDB",
    }


@api_router.get("/health")
async def health_check():
    ollama_ok, guard_ok, models = False, False, []
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{OLLAMA_BASE_URL}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                models = [m["name"] for m in r.json().get("models", [])]
                guard_ok = any(GUARD_MODEL.split(":")[0] in m for m in models)
    except Exception:
        pass
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama_connected": ollama_ok,
        "main_model": MAIN_MODEL,
        "guard_model": GUARD_MODEL,
        "guard_model_loaded": guard_ok,
        "guardrails_enabled": GUARDRAILS_ENABLED,
        "available_models": models,
    }


# ── Safety standalone ─────────────────────────────────────────────────────────

@api_router.post("/safety/check")
async def safety_check_endpoint(content: str):
    """Run Llama Guard 3 on arbitrary text."""
    return await check_content_safety(content)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@api_router.get("/dashboard/nri")
async def get_narrative_risk_index():
    """Narrative Risk Index computed from real DB data."""
    return await compute_narrative_risk_index()


@api_router.get("/dashboard/summary")
async def get_dashboard_summary():
    con = get_db()
    doc_count   = con.execute("SELECT COUNT(*) FROM analyzed_documents").fetchone()[0]
    claim_count = con.execute("SELECT COUNT(*) FROM analyzed_claims").fetchone()[0]

    high_risk_docs = con.execute("""
        SELECT COUNT(*) FROM analyzed_documents
        WHERE CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) > 60
    """).fetchone()[0]

    high_risk_claims = con.execute("""
        SELECT COUNT(*) FROM analyzed_claims
        WHERE CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) > 60
    """).fetchone()[0]

    recent_docs = con.execute("""
        SELECT id, title, url, JSON_EXTRACT(analysis,'$.risk_score') as rs,
               JSON_EXTRACT(analysis,'$.veracity_assessment') as va, created_at
        FROM analyzed_documents ORDER BY created_at DESC LIMIT 5
    """).fetchall()

    recent_claims = con.execute("""
        SELECT id, content, source_platform,
               JSON_EXTRACT(analysis,'$.risk_score') as rs,
               JSON_EXTRACT(analysis,'$.veracity_assessment') as va, created_at
        FROM analyzed_claims ORDER BY created_at DESC LIMIT 5
    """).fetchall()
    con.close()

    return {
        "total_documents_analyzed": doc_count,
        "total_claims_analyzed": claim_count,
        "high_risk_documents": high_risk_docs,
        "high_risk_claims": high_risk_claims,
        "last_update": datetime.now(timezone.utc).isoformat(),
        "guardrails_enabled": GUARDRAILS_ENABLED,
        "recent_documents": [
            {"id": r[0], "title": r[1], "url": r[2],
             "risk_score": r[3], "veracity": r[4], "created_at": r[5]}
            for r in recent_docs
        ],
        "recent_claims": [
            {"id": r[0], "content": (r[1] or "")[:120],
             "platform": r[2], "risk_score": r[3], "veracity": r[4], "created_at": r[5]}
            for r in recent_claims
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Official Document Integrity
# ══════════════════════════════════════════════════════════════════════════════

@api_router.post("/layer1/analyze")
async def analyze_official_document(request: DocumentAnalysisRequest):
    """Submit an official document text for real AI misinformation analysis."""
    analysis = await analyze_document_with_ai(
        request.title, request.content, request.doc_type, request.source
    )
    doc_id = str(uuid.uuid4())
    con = get_db()
    con.execute(
        "INSERT INTO analyzed_documents (id,title,content,doc_type,source,url,created_at,analysis) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [doc_id, request.title, request.content[:10000], request.doc_type,
         request.source, "", datetime.now(timezone.utc).isoformat(), json.dumps(analysis)]
    )
    con.close()
    return {"document_id": doc_id, **analysis}


@api_router.get("/layer1/documents")
async def list_documents(limit: int = Query(20, ge=1, le=100),
                         offset: int = Query(0, ge=0)):
    """List all previously analysed official documents."""
    con = get_db()
    rows = con.execute("""
        SELECT id, title, doc_type, source, url,
               JSON_EXTRACT(analysis,'$.risk_score')          as risk_score,
               JSON_EXTRACT(analysis,'$.fabrication_detected') as fab,
               JSON_EXTRACT(analysis,'$.summary')             as summary,
               created_at
        FROM analyzed_documents
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [limit, offset]).fetchall()
    total = con.execute("SELECT COUNT(*) FROM analyzed_documents").fetchone()[0]
    con.close()
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [
            {"id": r[0], "title": r[1], "doc_type": r[2], "source": r[3], "url": r[4],
             "risk_score": r[5], "fabrication_detected": r[6],
             "summary": (r[7] or "").strip('"'), "created_at": r[8]}
            for r in rows
        ]
    }


@api_router.get("/layer1/documents/{doc_id}")
async def get_document(doc_id: str):
    """Retrieve a single document and its full analysis."""
    con = get_db()
    row = con.execute(
        "SELECT id,title,content,doc_type,source,url,created_at,analysis "
        "FROM analyzed_documents WHERE id=?", [doc_id]
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "Document not found")
    analysis = _parse_json(row[7]) or {}
    return {"id": row[0], "title": row[1], "content": row[2][:2000],
            "doc_type": row[3], "source": row[4], "url": row[5],
            "created_at": row[6], "analysis": analysis}


@api_router.get("/layer1/stats")
async def get_layer1_stats():
    con = get_db()
    rows = con.execute("""
        SELECT
            COUNT(*) as total,
            AVG(CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT)) as avg_risk,
            SUM(CASE WHEN CAST(JSON_EXTRACT(analysis,'$.fabrication_detected') AS VARCHAR) = 'true' THEN 1 ELSE 0 END) as fabs,
            SUM(CASE WHEN CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) > 60 THEN 1 ELSE 0 END) as high_risk,
            SUM(CASE WHEN doc_type='press_release'       THEN 1 ELSE 0 END) as press_releases,
            SUM(CASE WHEN doc_type='regulatory_circular' THEN 1 ELSE 0 END) as circulars,
            SUM(CASE WHEN doc_type='public_advisory'     THEN 1 ELSE 0 END) as advisories
        FROM analyzed_documents
    """).fetchone()
    con.close()
    return {
        "total_documents":      rows[0],
        "avg_risk_score":       round(rows[1] or 0, 1),
        "fabrications_detected": rows[2],
        "high_risk_count":       rows[3],
        "by_type": {
            "press_release":       rows[4],
            "regulatory_circular": rows[5],
            "public_advisory":     rows[6],
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Public Narrative & URL Analysis
# ══════════════════════════════════════════════════════════════════════════════

@api_router.post("/layer2/analyze-url")
async def analyze_url_content(
    url_qp:           Optional[str] = Query(None, alias="url"),
    analysis_type_qp: Optional[str] = Query(None, alias="analysis_type"),
    content_qp:       Optional[str] = Query(None, alias="content"),
    request:          Optional[URLAnalysisRequest] = None,
):
    """
    Fetch a URL and run full AI misinformation analysis.
    Accepts input as query params (?url=...) OR as a JSON body.
    Paste-override: supply 'content' if the site blocks automated fetching.
    """
    #print("Line number 1158: ", url_qp, analysis_type_qp, content_qp, request)

    resolved_url  = url_qp           or (request.url           if request else None)
    resolved_type = analysis_type_qp or (request.analysis_type if request else None) or "news_article"
    resolved_body = content_qp       or (request.content       if request else None)

    #print("Line number 1164: ", resolved_url, resolved_type, len(resolved_body) if resolved_body else 0)
    if not resolved_url or not resolved_url.strip():
        raise HTTPException(status_code=422,
                            detail="'url' is required — pass it as ?url=... or in the JSON body.")

    resolved_url = resolved_url.strip()
    is_credible, source_domain = is_credible_source(resolved_url)

    #print("Line number: 1068", resolved_body, is_credible, source_domain)

    if resolved_body and len(resolved_body.strip()) > 80:
        article = {
            "success": True, "title": f"Pasted content from {source_domain}",
            "description": "", "author": "", "published_date": "",
            "content": resolved_body.strip()[:8000],
            "word_count": len(resolved_body.split()), "url": resolved_url,
        }
    else:
        article = await fetch_article(resolved_url)
        if not article["success"]:
            print(f"[L2][ERROR] URL fetch failed domain={source_domain} url={resolved_url} err={article.get('error')}")
            raise HTTPException(status_code=422, detail={
                "message": (f"Could not fetch content from {source_domain}. "
                            f"Error: {article['error']}. "
                            "Supply article text via the 'content' field as a fallback."),
                "domain": source_domain, "url": resolved_url,
            })
        if article["word_count"] < 30:
            print(f"[L2][ERROR] Too little text domain={source_domain} url={resolved_url} words={article.get('word_count')}")
        
            raise HTTPException(status_code=422, detail={
                "message": (f"Too little readable text from {source_domain} "
                            f"({article['word_count']} words). "
                            "The site may require JavaScript or block scrapers. "
                            "Paste the article text into the 'content' field."),
                "domain": source_domain, "word_count": article["word_count"],
            })

    analysis = await analyze_url_with_ai(article, resolved_type, is_credible, source_domain)

    claim_id = str(uuid.uuid4())
    con = get_db()
    con.execute(
        "INSERT INTO analyzed_claims (id,content,source_url,source_domain,analysis_type,created_at,analysis) "
        "VALUES (?,?,?,?,?,?,?)",
        [claim_id, article["content"][:5000], resolved_url, source_domain,
         resolved_type, datetime.now(timezone.utc).isoformat(), json.dumps(analysis)]
    )
    con.close()
    return {"claim_id": claim_id, **analysis}


@api_router.post("/layer2/analyze-claim")
async def analyze_public_claim(
    # ── Accept content either as a query-param OR inside a JSON body ──
    content:         Optional[str] = Query(None),
    source_platform: Optional[str] = Query(None),
    source_user:     Optional[str] = Query(None),
    request:         Optional[ClaimAnalysisRequest] = None,
):
    """
    Analyse a claim (social media post, forwarded message, news snippet, etc.).

    Accepts input three ways — use whichever is convenient:
      1. Query parameters:  POST /layer2/analyze-claim?content=...
      2. JSON body:         POST /layer2/analyze-claim  {"content": "..."}
      3. Mixed:             query params take precedence over body fields

    If the content contains a URL (http/https), the endpoint will
    automatically fetch and analyse the linked article instead of
    treating it as a plain text claim, giving a richer result.
    """
    # ── Resolve inputs (query > body) ────────────────────────────────────────
    if content is None and request is not None:
        content = request.content
    if source_platform is None:
        source_platform = (request.source_platform if request else None) or "unknown"
    if source_user is None:
        source_user = (request.source_user if request else None) or "unknown"

    if not content or not content.strip():
        raise HTTPException(
            status_code=422,
            detail="'content' is required — provide it as a query parameter or in the JSON body."
        )

    content = content.strip()

    # ── Auto-detect embedded URLs ─────────────────────────────────────────────
    url_pattern = re.compile(r'https?://[^\s\)\]\>\"\']+', re.IGNORECASE)
    found_urls  = url_pattern.findall(content)

    # Strip trailing punctuation that might have been URL-encoded or appended
    found_urls = [re.sub(r'[.,;:!?\)]+$', '', u) for u in found_urls]

    if found_urls:
        # Use the first URL found; analyse the article it points to
        target_url       = found_urls[0]
        is_credible, source_domain = is_credible_source(target_url)

        # The text before/around the URL is useful context for the LLM
        surrounding_text = url_pattern.sub("", content).strip()

        article = await fetch_article(target_url)

        if article["success"] and article["word_count"] >= 20:
            # Prepend any surrounding claim text as extra context
            if surrounding_text:
                article["content"] = (
                    f"[USER CONTEXT]: {surrounding_text}\n\n"
                    f"[ARTICLE BODY]: {article['content']}"
                )
                article["word_count"] = len(article["content"].split())

            analysis = await analyze_url_with_ai(
                article, "news_article", is_credible, source_domain
            )
            # Tag so the caller knows which path was taken
            analysis["input_type"]      = "url_extracted_from_claim"
            analysis["original_claim"]  = content
            analysis["extracted_url"]   = target_url
            final_content   = article["content"]
            analysis_type   = "url_claim"
        else:
            # Fetch failed — fall back to plain text analysis but note the URL
            logger.warning("URL fetch failed for %s (%s) — falling back to text analysis",
                           target_url, article.get("error"))
            analysis = await analyze_claim_with_ai(content, source_platform, source_user)
            analysis["input_type"]          = "text_claim_with_failed_url"
            analysis["attempted_url"]       = target_url
            analysis["fetch_error"]         = article.get("error")
            final_content   = content
            analysis_type   = "social_claim"
    else:
        # Plain text — no URL detected
        analysis          = await analyze_claim_with_ai(content, source_platform, source_user)
        analysis["input_type"] = "text_claim"
        final_content     = content
        analysis_type     = "social_claim"

    # ── Persist ───────────────────────────────────────────────────────────────
    claim_id     = str(uuid.uuid4())
    embedded_url = found_urls[0] if found_urls else ""
    domain       = urlparse(embedded_url).netloc.replace("www.", "") if embedded_url else source_platform

    con = get_db()
    con.execute(
        "INSERT INTO analyzed_claims "
        "(id,content,source_url,source_domain,analysis_type,created_at,analysis) "
        "VALUES (?,?,?,?,?,?,?)",
        [claim_id, final_content[:5000], embedded_url, domain,
         analysis_type, datetime.now(timezone.utc).isoformat(), json.dumps(analysis)]
    )
    con.close()

    return {"claim_id": claim_id, **analysis}


@api_router.get("/layer2/claims")
async def list_claims(limit: int = Query(20, ge=1, le=100),
                      offset: int = Query(0, ge=0),
                      min_risk: float = Query(0, ge=0, le=100)):
    """List all analysed claims/URLs, optionally filtered by minimum risk score."""
    con = get_db()
    rows = con.execute("""
        SELECT id, content, source_url, source_domain, analysis_type,
               JSON_EXTRACT(analysis,'$.risk_score')           as risk_score,
               JSON_EXTRACT(analysis,'$.veracity_assessment')  as veracity,
               JSON_EXTRACT(analysis,'$.recommended_action')   as action,
               JSON_EXTRACT(analysis,'$.article_title')        as article_title,
               created_at
        FROM analyzed_claims
        WHERE CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) >= ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [min_risk, limit, offset]).fetchall()
    total = con.execute(
        "SELECT COUNT(*) FROM analyzed_claims "
        "WHERE CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) >= ?",
        [min_risk]
    ).fetchone()[0]
    con.close()

    def _fmt(r):
        title = (r[8] or "").strip('"')
        snippet = (r[1] or "")[:120]
        return {
            "id": r[0],
            "snippet": title if title else snippet,
            "source_url": r[2],
            "source_domain": r[3],
            "analysis_type": r[4],
            "risk_score": r[5],
            "veracity": (r[6] or "").strip('"'),
            "recommended_action": (r[7] or "").strip('"'),
            "created_at": r[9],
        }

    return {"total": total, "limit": limit, "offset": offset,
            "items": [_fmt(r) for r in rows]}


@api_router.get("/layer2/claims/{claim_id}")
async def get_claim(claim_id: str):
    """Get full analysis for a single claim."""
    con = get_db()
    row = con.execute(
        "SELECT id,content,source_url,source_domain,analysis_type,created_at,analysis "
        "FROM analyzed_claims WHERE id=?", [claim_id]
    ).fetchone()
    con.close()
    if not row:
        raise HTTPException(404, "Claim not found")
    analysis = _parse_json(row[6]) or {}
    return {"id": row[0], "content": row[1], "source_url": row[2],
            "source_domain": row[3], "analysis_type": row[4],
            "created_at": row[5], "analysis": analysis}


@api_router.get("/layer2/stats")
async def get_layer2_stats():
    con = get_db()
    rows = con.execute("""
        SELECT
            COUNT(*) as total,
            AVG(CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT)) as avg_risk,
            SUM(CASE WHEN CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) > 60 THEN 1 ELSE 0 END) as high_risk,
            SUM(CASE WHEN JSON_EXTRACT(analysis,'$.recommended_action') = '"do_not_share"'
                          OR JSON_EXTRACT(analysis,'$.recommended_action') = '"urgent_response"'
                     THEN 1 ELSE 0 END) as flagged
        FROM analyzed_claims
    """).fetchone()
    by_domain = con.execute("""
        SELECT source_domain, COUNT(*) as cnt,
               AVG(CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT)) as avg_rs
        FROM analyzed_claims
        WHERE source_domain != '' AND source_domain IS NOT NULL
        GROUP BY source_domain ORDER BY cnt DESC LIMIT 10
    """).fetchall()
    con.close()
    return {
        "total_claims_analyzed": rows[0],
        "avg_risk_score": round(rows[1] or 0, 1),
        "high_risk_count": rows[2],
        "flagged_count": rows[3],
        "top_domains": [
            {"domain": r[0], "count": r[1], "avg_risk": round(r[2] or 0, 1)}
            for r in by_domain
        ],
    }


@api_router.get("/layer2/high-risk")
async def get_high_risk_claims(threshold: float = Query(70, ge=0, le=100),
                               limit: int = Query(10, ge=1, le=50)):
    """Return the most dangerous claims above a risk threshold."""
    con = get_db()
    rows = con.execute("""
        SELECT id, content, source_url, source_domain,
               JSON_EXTRACT(analysis,'$.risk_score')          as rs,
               JSON_EXTRACT(analysis,'$.veracity_assessment') as va,
               JSON_EXTRACT(analysis,'$.summary')             as summary,
               JSON_EXTRACT(analysis,'$.recommended_action')  as action,
               JSON_EXTRACT(analysis,'$.article_title')       as title,
               created_at
        FROM analyzed_claims
        WHERE CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) >= ?
        ORDER BY CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) DESC
        LIMIT ?
    """, [threshold, limit]).fetchall()
    con.close()
    return [
        {"id": r[0],
         "snippet": ((r[8] or "").strip('"') or (r[1] or "")[:120]),
         "source_url": r[2], "source_domain": r[3],
         "risk_score": r[4],
         "veracity": (r[5] or "").strip('"'),
         "summary": (r[6] or "").strip('"'),
         "action": (r[7] or "").strip('"'),
         "created_at": r[9]}
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — Systemic Resilience
# ══════════════════════════════════════════════════════════════════════════════

@api_router.get("/layer3/resilience-score")
async def get_resilience_score():
    """Compute resilience score from real analysis history."""
    con = get_db()
    doc_avg = con.execute(
        "SELECT AVG(CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT)) FROM analyzed_documents"
    ).fetchone()[0] or 0

    claim_avg = con.execute(
        "SELECT AVG(CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT)) FROM analyzed_claims"
    ).fetchone()[0] or 0

    doc_count   = con.execute("SELECT COUNT(*) FROM analyzed_documents").fetchone()[0]
    claim_count = con.execute("SELECT COUNT(*) FROM analyzed_claims").fetchone()[0]

    high_risk = con.execute("""
        SELECT COUNT(*) FROM analyzed_claims
        WHERE CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT) > 75
    """).fetchone()[0]
    con.close()

    composite_risk = doc_avg * 0.3 + claim_avg * 0.7
    resilience = max(0.0, 100.0 - composite_risk)

    return {
        "resilience_score": round(resilience, 1),
        "composite_risk":   round(composite_risk, 1),
        "doc_avg_risk":     round(doc_avg, 1),
        "claim_avg_risk":   round(claim_avg, 1),
        "threat_level":     "high" if resilience < 40 else "medium" if resilience < 70 else "low",
        "active_threats":   high_risk,
        "total_analysed":   doc_count + claim_count,
        "recommendation": (
            "Increase monitoring and public communication" if resilience < 40
            else "Maintain vigilance" if resilience < 70
            else "System stable — continue routine monitoring"
        ),
    }


@api_router.get("/layer3/risk-trend")
async def get_risk_trend(days: int = Query(7, ge=1, le=90)):
    """Daily average risk scores over the past N days (from real data)."""
    con = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    rows = con.execute("""
        SELECT SUBSTR(created_at, 1, 10) as day,
               AVG(CAST(JSON_EXTRACT(analysis,'$.risk_score') AS FLOAT)) as avg_rs,
               COUNT(*) as cnt
        FROM analyzed_claims
        WHERE created_at >= ?
        GROUP BY day ORDER BY day ASC
    """, [cutoff]).fetchall()
    con.close()

    return {
        "days": days,
        "data": [{"date": r[0], "avg_risk": round(r[1] or 0, 1), "count": r[2]}
                 for r in rows]
    }


@api_router.get("/layer3/stats")
async def get_layer3_stats():
    con = get_db()
    doc_count   = con.execute("SELECT COUNT(*) FROM analyzed_documents").fetchone()[0]
    claim_count = con.execute("SELECT COUNT(*) FROM analyzed_claims").fetchone()[0]

    # Distribution of veracity assessments
    veracity_dist = con.execute("""
        SELECT JSON_EXTRACT(analysis,'$.veracity_assessment') as va, COUNT(*) as cnt
        FROM analyzed_claims
        WHERE va IS NOT NULL
        GROUP BY va ORDER BY cnt DESC
    """).fetchall()

    # Recommended action distribution
    action_dist = con.execute("""
        SELECT JSON_EXTRACT(analysis,'$.recommended_action') as action, COUNT(*) as cnt
        FROM analyzed_claims
        WHERE action IS NOT NULL
        GROUP BY action ORDER BY cnt DESC
    """).fetchall()

    con.close()
    return {
        "total_documents": doc_count,
        "total_claims": claim_count,
        "veracity_distribution": {
            (r[0] or "").strip('"'): r[1] for r in veracity_dist
        },
        "action_distribution": {
            (r[0] or "").strip('"'): r[1] for r in action_dist
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# STATUS CHECKS
# ══════════════════════════════════════════════════════════════════════════════

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(inp: StatusCheckCreate):
    obj = StatusCheck(client_name=inp.client_name)
    con = get_db()
    con.execute("INSERT INTO status_checks (id,client_name,timestamp) VALUES (?,?,?)",
                [obj.id, obj.client_name, obj.timestamp.isoformat()])
    con.close()
    return obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    con = get_db()
    rows = con.execute("SELECT id,client_name,timestamp FROM status_checks ORDER BY timestamp DESC").fetchall()
    con.close()
    return [StatusCheck(id=r[0], client_name=r[1],
                        timestamp=datetime.fromisoformat(r[2])) for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
# WIRE UP
# ══════════════════════════════════════════════════════════════════════════════

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)