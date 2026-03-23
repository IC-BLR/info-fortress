"""
server2.py — INFO FORTRESS local compare backend
"""

from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
import os
import json
import re
import httpx
import asyncio
import logging
from bs4 import BeautifulSoup

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

# All fixed pipeline logic lives here — extraction, parsing, normalization, metrics
from fetch_fixes import (
    extract_article_text,
    clean_for_prompt,
    parse_model_json,
    normalize_output,
    build_comparison_metrics,
    MAX_INPUT_CHARS,
    MAX_PROMPT_CHARS,
)

# ============================================================================
# SETUP
# ============================================================================

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_MODEL_PATH   = os.environ.get("BASE_MODEL_PATH",   r"C:\path\to\base-model")
LORA_ADAPTER_PATH = os.environ.get("LORA_ADAPTER_PATH", r"C:\path\to\lora-adapter")
MAX_NEW_TOKENS    = int(os.environ.get("MAX_NEW_TOKENS", "300"))

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"\n Base model path : {BASE_MODEL_PATH}")
print(f" LoRA adapter    : {LORA_ADAPTER_PATH}")
print(f" Device          : {DEVICE}\n")

tokenizer  = None
base_model = None
lora_model = None


# ============================================================================
# REQUEST MODEL
# ============================================================================

class CompareRequest(BaseModel):
    content:       Optional[str] = None
    url:           Optional[str] = None
    analysis_type: str           = "news_article"


# ============================================================================
# SOURCE REGISTRY
# ============================================================================

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
    "thewire.in", "livemint.com", "business-standard.com",
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


# ============================================================================
# ARTICLE FETCHER
# ============================================================================

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT":             "1",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _is_js_rendered(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for marker in [soup.find("div", id="__next"),
                   soup.find("div", id="app"),
                   soup.find("div", id="root")]:
        if marker and len(marker.get_text(strip=True)) < 100:
            logger.info("[JS-detect] Empty JS root — needs Playwright")
            return True
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()
    visible = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True)).strip()
    return len(visible) < 500


def _parse_html(html: str, base_url: str) -> Dict[str, Any]:
    """Parse HTML using the fixed extract_article_text from pipeline_fixes.py."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise tags before extraction
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "iframe"]):
        tag.decompose()

    # Title
    title = ""
    for cand in [soup.find("h1"),
                 soup.find("meta", property="og:title"),
                 soup.find("title")]:
        if cand:
            title = (cand.get("content") or cand.get_text()).strip()
            if title:
                break
    title = title or "Title not found"
    print(f"[HTML] title={title!r}")

    # Content — uses the fixed extractor
    content = extract_article_text(soup, base_url)
    print(f"[HTML] raw content length={len(content)}")

    # Images
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        w   = int(img.get("width",  0) or 0)
        h   = int(img.get("height", 0) or 0)
        if w and h and (w < 50 or h < 50):
            continue
        if any(x in src.lower() for x in ["pixel","tracker","1x1","beacon"]):
            continue
        if src:
            images.append(src)

    # External links
    base_origin = urlparse(base_url).netloc
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        try:
            abs_url = urljoin(base_url, a["href"])
            p       = urlparse(abs_url)
            if p.scheme not in ("http","https") or p.netloc == base_origin:
                continue
            if abs_url not in seen:
                seen.add(abs_url)
                links.append(abs_url)
        except Exception:
            continue

    return {
        "title":        title[:300],
        "content":      content[:MAX_INPUT_CHARS],
        "image_count":  len(images),
        "source_count": len(links),
        "sources":      links[:15],
    }


async def _fetch_httpx(url: str) -> str:
    headers = {**_FETCH_HEADERS, "Accept-Encoding": "identity"}
    async with httpx.AsyncClient(
        headers=headers, follow_redirects=True, timeout=20.0, verify=False
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        b = resp.content
        if len(b) > 2 and b[0] in (0x1f, 0x78, 0xce, 0x28):
            for label, fn in [
                ("gzip",   lambda x: __import__("gzip").decompress(x)),
                ("brotli", lambda x: __import__("brotli").decompress(x)),
                ("zlib",   lambda x: __import__("zlib").decompress(x, -15)),
            ]:
                try:
                    return fn(b).decode("utf-8", errors="replace")
                except Exception:
                    continue
            raise ValueError("Could not decompress response")
        return resp.text


async def _fetch_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("pip install playwright && playwright install chromium")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx     = await browser.new_context(
            user_agent=_FETCH_HEADERS["User-Agent"],
            java_script_enabled=True, viewport={"width":1280,"height":800}, locale="en-US"
        )
        page = await ctx.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}",
                         lambda r: r.abort())
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        for sel in ["article","h1",'[class*="article"]','[class*="story"]',"main"]:
            try:
                await page.wait_for_selector(sel, timeout=5000)
                break
            except Exception:
                continue
        await asyncio.sleep(3)
        html = await page.content()
        await browser.close()
        return html


async def fetch_article(url: str) -> Dict[str, Any]:
    print(f"[FETCH] {url}")
    html        = None
    method_used = "httpx"

    try:
        html = await _fetch_httpx(url)
        if _is_js_rendered(html):
            html = None
    except Exception as e:
        logger.info("[FETCH] httpx failed: %s", e)

    if html is None:
        method_used = "playwright"
        try:
            html = await _fetch_playwright(url)
        except Exception as e:
            return {"success": False, "error": str(e), "url": url,
                    "title":"","description":"","author":"","published_date":"",
                    "content":"","word_count":0}

    print(f"[FETCH] got HTML len={len(html)} via {method_used}")

    try:
        parsed = _parse_html(html, url)
    except Exception as e:
        return {"success": False, "error": f"Parse error: {e}", "url": url,
                "title":"","description":"","author":"","published_date":"",
                "content":"","word_count":0}

    meta_soup = BeautifulSoup(html, "html.parser")
    def _meta(prop):
        for attr, val in [("property",f"og:{prop}"),("name",prop)]:
            t = meta_soup.find("meta",{attr:val})
            if t and t.get("content"):
                return t["content"].strip()
        return ""

    description = _meta("description")
    author      = _meta("author")
    published   = _meta("article:published_time") or _meta("pubdate")
    content     = parsed["content"] if len(parsed["content"]) >= 150 else description

    return {
        "success":        True,
        "title":          parsed["title"],
        "description":    description[:500],
        "author":         author,
        "published_date": published,
        "content":        content,
        "word_count":     len(content.split()),
        "url":            url,
        "error":          None,
        "method_used":    method_used,
        "image_count":    parsed["image_count"],
        "source_count":   parsed["source_count"],
        "sources":        parsed["sources"],
    }


# ============================================================================
# MODEL LOADING
# ============================================================================

def load_local_models() -> None:
    global tokenizer, base_model, lora_model

    print(f"\n[MODEL] Loading tokenizer from {BASE_MODEL_PATH}")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    has_template = bool(getattr(tok, "chat_template", None))
    print(f"[MODEL] vocab={tok.vocab_size} chat_template={'YES' if has_template else 'NO'}")

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    print("[MODEL] Loading base model...")
    bm = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_PATH, torch_dtype=dtype, device_map="auto", trust_remote_code=True
    )
    bm.eval()

    print("[MODEL] Loading LoRA model...")
    lora_base = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_PATH, torch_dtype=dtype, device_map="auto", trust_remote_code=True
    )
    lm = PeftModel.from_pretrained(lora_base, LORA_ADAPTER_PATH)
    lm.eval()

    tokenizer  = tok
    base_model = bm
    lora_model = lm
    print("[MODEL] Both models ready.\n")


def run_model(prompt: str, model_obj, max_new_tokens: int = MAX_NEW_TOKENS) -> str:
    inputs = tokenizer(
        prompt, return_tensors="pt", truncation=True, max_length=1600, padding=True
    )
    try:
        device = model_obj.device
    except Exception:
        device = next(model_obj.parameters()).device

    inputs     = {k: v.to(device) for k, v in inputs.items()}
    prompt_len = inputs["input_ids"].shape[1]
    print(f"[INFER] {type(model_obj).__name__} | prompt_tokens={prompt_len}")

    with torch.no_grad():
        output = model_obj.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            min_new_tokens=40,
            do_sample=False,
            repetition_penalty=1.12,
            no_repeat_ngram_size=4,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            use_cache=True,
        )

    new_tokens = output[0][prompt_len:]
    decoded    = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    if not decoded:
        full    = tokenizer.decode(output[0], skip_special_tokens=True).strip()
        decoded = full[len(prompt):].strip() if full.startswith(prompt) else full

    print(f"[INFER] new_tokens={len(new_tokens)} | output={decoded[:200]!r}")
    return decoded.strip()


# ============================================================================
# PROMPTS
# ============================================================================

def build_base_prompt(content: str, source_hint: str = "unknown") -> str:
    trimmed = clean_for_prompt(content, max_chars=MAX_PROMPT_CHARS)
    system_msg = "You are a fact-checking assistant. Return JSON only. No prose."
    user_msg = (
        f"SOURCE: {source_hint}\n\n"
        f"Article:\n{trimmed}\n\n"
        'Return ONLY: {"risk_score":<integer 0-100>,'
        '"veracity_assessment":"<likely_true|likely_false|likely_misinformation|uncertain>",'
        '"confidence":<float 0.0-1.0>,'
        '"summary":"<one sentence>"}'
    )
    if getattr(tokenizer, "chat_template", None):
        prompt = tokenizer.apply_chat_template(
            [{"role": "system", "content": system_msg},
             {"role": "user",   "content": user_msg}],
            tokenize=False, add_generation_prompt=True
        )
        print(f"[PROMPT/BASE] len={len(prompt)}")
        return prompt
    return f"SYSTEM:\n{system_msg}\n\nUSER:\n{user_msg}\n\nASSISTANT:\n{{"


def build_lora_prompt(title: str, body: str, url: str) -> str:
    # Clean and trim body BEFORE building JSON dict
    trimmed_body = clean_for_prompt(body, max_chars=MAX_PROMPT_CHARS)

    article_json = json.dumps(
        {"title": title, "body": trimmed_body, "source_url": url},
        ensure_ascii=False
    )

    messages = [
        {"role": "system", "content": "You are an expert media analyst."},
        {"role": "user",   "content": (
            "Analyze this article for misinformation and narrative risk signals.\n\n"
            f"Article:\n{article_json}"
        )},
    ]

    if getattr(tokenizer, "chat_template", None):
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        print(f"[PROMPT/LORA] len={len(prompt)}")
        return prompt

    return (
        f"SYSTEM:\nYou are an expert media analyst.\n\n"
        f"USER:\nAnalyze this article for misinformation and narrative risk signals.\n\n"
        f"Article:\n{article_json}\n\nASSISTANT:\n"
    )


# ============================================================================
# APP
# ============================================================================

app        = FastAPI(title="INFO FORTRESS")
api_router = APIRouter(prefix="/api")


@app.on_event("startup")
async def startup_event():
    load_local_models()


@app.middleware("http")
async def log_requests(request, call_next):
    start = datetime.now(timezone.utc)
    logger.info("[API] -> %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception("[API] Exception: %s", e)
        raise
    ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
    logger.info("[API] <- %s %s %s %.1fms",
                request.method, request.url.path, response.status_code, ms)
    return response


@api_router.get("/health")
async def health():
    return {
        "status":            "healthy",
        "base_model_loaded": base_model is not None,
        "lora_model_loaded": lora_model is not None,
        "device":            DEVICE,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }


@api_router.post("/compare")
async def compare_models(request: CompareRequest):
    resolved_content = (request.content or "").strip()
    resolved_url     = (request.url     or "").strip()

    if not resolved_url and resolved_content.startswith(("http://","https://")):
        resolved_url     = resolved_content
        resolved_content = ""

    if not resolved_content and not resolved_url:
        raise HTTPException(status_code=422, detail="Provide 'content' or 'url'.")

    source_hint   = "text_input"
    source_domain = "unknown"
    is_credible   = False
    is_satire     = False

    if resolved_url:
        is_credible, source_domain = is_credible_source(resolved_url)
        is_satire,   _             = is_satire_source(resolved_url)

        article = await fetch_article(resolved_url)
        if not article["success"]:
            raise HTTPException(status_code=422, detail={
                "message": f"Could not fetch {source_domain}: {article['error']}",
                "domain":  source_domain, "url": resolved_url,
            })
        if article["word_count"] < 30:
            raise HTTPException(status_code=422, detail={
                "message":    f"Too little text ({article['word_count']} words) from {source_domain}.",
                "word_count": article["word_count"],
            })
        resolved_content = article["content"]
        source_hint      = f"url:{source_domain}"
    else:
        article = {
            "title":"Direct input","description":"","author":"","published_date":"",
            "content":resolved_content[:MAX_INPUT_CHARS],
            "word_count":len(resolved_content.split()),
            "url":"","method_used":"direct_input",
            "image_count":0,"source_count":0,"sources":[],
        }

    print(f"\n[COMPARE] source={source_hint} content_len={len(resolved_content)}")

    # Build prompts (both use clean_for_prompt internally)
    base_prompt = build_base_prompt(content=resolved_content, source_hint=source_hint)
    lora_prompt = build_lora_prompt(
        title=article.get("title",""),
        body=resolved_content,
        url=article.get("url",""),
    )

    # Base inference
    print("\n[COMPARE] BASE...")
    try:
        base_raw = run_model(base_prompt, base_model)
    except Exception as e:
        logger.exception("Base inference failed")
        base_raw = json.dumps({"risk_score":0,"veracity_assessment":"error",
                               "confidence":0.0,"summary":f"Base failed: {e}"})

    # LoRA inference
    print("\n[COMPARE] LORA...")
    try:
        lora_raw = run_model(lora_prompt, lora_model)
    except Exception as e:
        logger.exception("LoRA inference failed")
        lora_raw = json.dumps({"risk_score":0,"veracity_assessment":"error",
                               "confidence":0.0,"summary":f"LoRA failed: {e}"})

    print(f"\n[BASE RAW]\n{base_raw}\n")
    print(f"\n[LORA RAW]\n{lora_raw}\n")

    # Normalize — now with parse_failed state
    base_output = normalize_output(base_raw, model_label="base")
    lora_output = normalize_output(lora_raw, model_label="lora")

    # Compare — parse failure never = improvement
    comparison_metrics = build_comparison_metrics(base_output, lora_output)

    print(f"\n[FINAL] base parse_failed={base_output['parse_failed']} "
          f"risk={base_output['risk_score']}")
    print(f"[FINAL] lora parse_failed={lora_output['parse_failed']} "
          f"risk={lora_output['risk_score']}")
    print(f"[FINAL] improved={comparison_metrics['improved']}")

    return {
        "base_output":        base_output,
        "lora_output":        lora_output,
        "comparison_metrics": comparison_metrics,
        "base_raw":           base_raw,
        "lora_raw":           lora_raw,
        "input_type":         "url" if resolved_url else "content",
        "resolved_url":       resolved_url,
        "source_domain":      source_domain,
        "is_credible_source": is_credible,
        "is_satire_source":   is_satire,
        "article_meta": {
            "title":          article.get("title",""),
            "word_count":     article.get("word_count",0),
            "url":            article.get("url",""),
            "author":         article.get("author",""),
            "published_date": article.get("published_date",""),
            "method_used":    article.get("method_used",""),
        },
    }


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)