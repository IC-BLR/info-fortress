import os
import sys
import json
import time
import math
import re

import pandas as pd
from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = "gemini-3.1-flash-lite-preview"
BATCH_SIZE = 3
REQUEST_DELAY_SECONDS = 5
MAX_RETRIES_PER_BATCH = 6

PROMPT = r"""
You are generating structured training data for a misinformation detection system.

You will receive a JSON array of articles. Each article contains:
- title
- body (full article text)
- url
- veracity_assessment (already provided — DO NOT CHANGE IT)

Your task is to analyze EACH article independently and return a JSON array of results
IN THE EXACT SAME ORDER as the input array.

IMPORTANT RULES:
- DO NOT change "veracity_assessment"
- DO NOT invent facts not present in the article
- Use ONLY the allowed values listed below
- Be consistent and realistic
- Return ONLY valid JSON (no explanations, no extra text)
- Return a JSON ARRAY, one object per input article
- Preserve title, body, and source_url exactly

---------------------------------------
OUTPUT FORMAT (STRICT)
---------------------------------------

[
  {
    "instruction": "Analyze this article for misinformation and narrative risk signals.",
    "input": {
      "title": "<copy exactly>",
      "body": "<copy exactly>",
      "source_url": "<copy exactly>"
    },
    "output": {
      "veracity_assessment": "<copy exactly from input>",
      "narrative_category": "",
      "article_type": "",
      "tone_profile": [],
      "misinfo_prob": 0.0,
      "source_risk": 0.0,
      "evidence_weakness": 0.0,
      "sensationalism": 0.0,
      "confidence": 0.0,
      "indicators": [],
      "summary": "",
      "institutional_impact": "",
      "operational_sensitivity": "",
      "public_panic_potential": "",
      "coordination_risk_hint": ""
    }
  }
]

---------------------------------------
ALLOWED VALUES + HOW TO DECIDE
---------------------------------------

1. narrative_category (choose ONE):
defense_security, politics_governance, geopolitics, finance_economy, business_corporate,
cybersecurity, technology_science, health_medicine, environment_climate, law_regulation,
crime_public_safety, energy_infrastructure, education, social_cultural, religion_identity,
media_information, international_affairs, transport_aviation_maritime, celebrity_entertainment,
sports, humanitarian_disaster, general_news, satire_parody, other

2. article_type (choose ONE):
news_report, opinion_editorial, analysis_explainer, blog_post, press_release,
government_alert, advisory_notice, investigative_report, satire, rumor_claim_post,
promotional_content, personal_commentary, other

3. tone_profile (choose 1-3):
neutral, serious, alarmist, fear_inducing, urgent, speculative, authoritative,
persuasive, accusatory, corrective, satirical, emotional, sensational, instructional

4. indicators (choose 3-6 ONLY from list):
neutral_reporting_style, official_source_reference, institutional_reference,
named_sources_present, attributed_claims, supporting_context_present,
structured_journalistic_format, verifiable_event_details, multi_source_corroboration,
lack_of_sources, anonymous_sources, unverified_claim, sensational_headline,
fear_based_language, speculative_assertion, conspiracy_framing,
misleading_certainty, weak_evidence, missing_context, unverified_statistics,
clickbait_style, impersonates_official_tone, satirical_or_parodic_style,
high_emotional_manipulation, single_source_dependency,
source_reputation_concern, headline_body_mismatch

5. SCORING FIELDS (0.0 to 1.0)
misinfo_prob
source_risk
evidence_weakness
sensationalism

confidence:
0.60 to 0.99

6. institutional_impact (choose ONE):
low, medium, high, critical

7. operational_sensitivity:
low, medium, high

8. public_panic_potential:
low, medium, high

9. coordination_risk_hint:
low, medium, high

10. summary:
1-2 sentences explaining:
- what the article claims
- why it appears low/high integrity

---------------------------------------
TASK
---------------------------------------

Analyze every article in the provided JSON array and return the structured JSON array only.
"""

ALLOWED_NARRATIVE_CATEGORY = {
    "defense_security", "politics_governance", "geopolitics", "finance_economy",
    "business_corporate", "cybersecurity", "technology_science", "health_medicine",
    "environment_climate", "law_regulation", "crime_public_safety",
    "energy_infrastructure", "education", "social_cultural", "religion_identity",
    "media_information", "international_affairs", "transport_aviation_maritime",
    "celebrity_entertainment", "sports", "humanitarian_disaster", "general_news",
    "satire_parody", "other"
}

ALLOWED_ARTICLE_TYPE = {
    "news_report", "opinion_editorial", "analysis_explainer", "blog_post",
    "press_release", "government_alert", "advisory_notice", "investigative_report",
    "satire", "rumor_claim_post", "promotional_content", "personal_commentary", "other"
}

ALLOWED_TONE_PROFILE = {
    "neutral", "serious", "alarmist", "fear_inducing", "urgent", "speculative",
    "authoritative", "persuasive", "accusatory", "corrective", "satirical",
    "emotional", "sensational", "instructional"
}

ALLOWED_INDICATORS = {
    "neutral_reporting_style", "official_source_reference", "institutional_reference",
    "named_sources_present", "attributed_claims", "supporting_context_present",
    "structured_journalistic_format", "verifiable_event_details", "multi_source_corroboration",
    "lack_of_sources", "anonymous_sources", "unverified_claim", "sensational_headline",
    "fear_based_language", "speculative_assertion", "conspiracy_framing",
    "misleading_certainty", "weak_evidence", "missing_context", "unverified_statistics",
    "clickbait_style", "impersonates_official_tone", "satirical_or_parodic_style",
    "high_emotional_manipulation", "single_source_dependency",
    "source_reputation_concern", "headline_body_mismatch"
}

ALLOWED_IMPACT = {"low", "medium", "high", "critical"}
ALLOWED_SENSITIVITY = {"low", "medium", "high"}
ALLOWED_VERACITY = {"credible", "likely_misinformation"}

DEFAULT_OUTPUT_BY_VERACITY = {
    "credible": {
        "narrative_category": "general_news",
        "article_type": "news_report",
        "tone_profile": ["neutral"],
        "misinfo_prob": 0.18,
        "source_risk": 0.18,
        "evidence_weakness": 0.22,
        "sensationalism": 0.10,
        "confidence": 0.75,
        "indicators": [
            "structured_journalistic_format",
            "supporting_context_present",
            "neutral_reporting_style"
        ],
        "summary": "The article presents a reportable event or claim in a relatively structured format. The available signals suggest lower misinformation risk, though the assessment is limited by automated enrichment.",
        "institutional_impact": "low",
        "operational_sensitivity": "low",
        "public_panic_potential": "low",
        "coordination_risk_hint": "low"
    },
    "likely_misinformation": {
        "narrative_category": "general_news",
        "article_type": "rumor_claim_post",
        "tone_profile": ["speculative"],
        "misinfo_prob": 0.82,
        "source_risk": 0.72,
        "evidence_weakness": 0.80,
        "sensationalism": 0.68,
        "confidence": 0.75,
        "indicators": [
            "unverified_claim",
            "weak_evidence",
            "missing_context"
        ],
        "summary": "The article appears to present claims with limited supporting evidence or verification cues. The available signals suggest elevated misinformation risk under the provided ground-truth label.",
        "institutional_impact": "medium",
        "operational_sensitivity": "low",
        "public_panic_potential": "medium",
        "coordination_risk_hint": "medium"
    }
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for col in df.columns:
        c = col.strip().lower()
        if c in ("urls", "url", "source_url"):
            mapping[col] = "url"
        elif c in ("headline", "title"):
            mapping[col] = "title"
        elif c in ("body", "text", "content", "article"):
            mapping[col] = "body"
        elif c == "veracity_assessment":
            mapping[col] = "veracity_assessment"
    return df.rename(columns=mapping)


def extract_json_array(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Model did not return valid JSON array.")


def clamp_float(value, low, high, default):
    try:
        value = float(value)
    except Exception:
        value = default
    return round(max(low, min(high, value)), 2)


def clean_list_str(values):
    if not isinstance(values, list):
        return []
    cleaned = []
    for item in values:
        if isinstance(item, str):
            s = item.strip()
            if s:
                cleaned.append(s)
    return cleaned


def build_batch_payload(batch_df: pd.DataFrame):
    items = []
    for _, row in batch_df.iterrows():
        items.append({
            "title": str(row["title"]),
            "body": str(row["body"]),
            "url": str(row["url"]),
            "veracity_assessment": str(row["veracity_assessment"]).strip()
        })
    return items


def default_record(title: str, body: str, url: str, veracity: str):
    base = DEFAULT_OUTPUT_BY_VERACITY[veracity]
    return {
        "instruction": "Analyze this article for misinformation and narrative risk signals.",
        "input": {
            "title": title,
            "body": body,
            "source_url": url
        },
        "output": {
            "veracity_assessment": veracity,
            "narrative_category": base["narrative_category"],
            "article_type": base["article_type"],
            "tone_profile": list(base["tone_profile"]),
            "misinfo_prob": base["misinfo_prob"],
            "source_risk": base["source_risk"],
            "evidence_weakness": base["evidence_weakness"],
            "sensationalism": base["sensationalism"],
            "confidence": base["confidence"],
            "indicators": list(base["indicators"]),
            "summary": base["summary"],
            "institutional_impact": base["institutional_impact"],
            "operational_sensitivity": base["operational_sensitivity"],
            "public_panic_potential": base["public_panic_potential"],
            "coordination_risk_hint": base["coordination_risk_hint"]
        }
    }


def validate_and_repair_item(item, source_item):
    title = source_item["title"]
    body = source_item["body"]
    url = source_item["url"]
    veracity = source_item["veracity_assessment"]

    fallback = default_record(title, body, url, veracity)

    if not isinstance(item, dict):
        return fallback

    result = {
        "instruction": "Analyze this article for misinformation and narrative risk signals.",
        "input": {
            "title": title,
            "body": body,
            "source_url": url
        },
        "output": {}
    }

    output = item.get("output", {})
    if not isinstance(output, dict):
        output = {}

    narrative_category = output.get("narrative_category", fallback["output"]["narrative_category"])
    if narrative_category not in ALLOWED_NARRATIVE_CATEGORY:
        narrative_category = fallback["output"]["narrative_category"]

    article_type = output.get("article_type", fallback["output"]["article_type"])
    if article_type not in ALLOWED_ARTICLE_TYPE:
        article_type = fallback["output"]["article_type"]

    tone_profile = clean_list_str(output.get("tone_profile", fallback["output"]["tone_profile"]))
    tone_profile = [x for x in tone_profile if x in ALLOWED_TONE_PROFILE][:3]
    if not tone_profile:
        tone_profile = fallback["output"]["tone_profile"]

    indicators = clean_list_str(output.get("indicators", fallback["output"]["indicators"]))
    indicators = [x for x in indicators if x in ALLOWED_INDICATORS]
    deduped = []
    for ind in indicators:
        if ind not in deduped:
            deduped.append(ind)
    indicators = deduped[:6]
    if len(indicators) < 3:
        indicators = fallback["output"]["indicators"]

    institutional_impact = output.get("institutional_impact", fallback["output"]["institutional_impact"])
    if institutional_impact not in ALLOWED_IMPACT:
        institutional_impact = fallback["output"]["institutional_impact"]

    operational_sensitivity = output.get("operational_sensitivity", fallback["output"]["operational_sensitivity"])
    if operational_sensitivity not in ALLOWED_SENSITIVITY:
        operational_sensitivity = fallback["output"]["operational_sensitivity"]

    public_panic_potential = output.get("public_panic_potential", fallback["output"]["public_panic_potential"])
    if public_panic_potential not in ALLOWED_SENSITIVITY:
        public_panic_potential = fallback["output"]["public_panic_potential"]

    coordination_risk_hint = output.get("coordination_risk_hint", fallback["output"]["coordination_risk_hint"])
    if coordination_risk_hint not in ALLOWED_SENSITIVITY:
        coordination_risk_hint = fallback["output"]["coordination_risk_hint"]

    summary = output.get("summary", fallback["output"]["summary"])
    if not isinstance(summary, str) or not summary.strip():
        summary = fallback["output"]["summary"]
    else:
        summary = summary.strip()

    result["output"] = {
        "veracity_assessment": veracity,
        "narrative_category": narrative_category,
        "article_type": article_type,
        "tone_profile": tone_profile,
        "misinfo_prob": clamp_float(output.get("misinfo_prob"), 0.0, 1.0, fallback["output"]["misinfo_prob"]),
        "source_risk": clamp_float(output.get("source_risk"), 0.0, 1.0, fallback["output"]["source_risk"]),
        "evidence_weakness": clamp_float(output.get("evidence_weakness"), 0.0, 1.0, fallback["output"]["evidence_weakness"]),
        "sensationalism": clamp_float(output.get("sensationalism"), 0.0, 1.0, fallback["output"]["sensationalism"]),
        "confidence": clamp_float(output.get("confidence"), 0.60, 0.99, fallback["output"]["confidence"]),
        "indicators": indicators,
        "summary": summary,
        "institutional_impact": institutional_impact,
        "operational_sensitivity": operational_sensitivity,
        "public_panic_potential": public_panic_potential,
        "coordination_risk_hint": coordination_risk_hint
    }

    return result


def call_gemini_batch(client, batch_payload):
    contents = PROMPT + "\n\nINPUT_JSON_ARRAY:\n" + json.dumps(batch_payload, ensure_ascii=False)

    last_error = None

    for attempt in range(MAX_RETRIES_PER_BATCH):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents
            )
            parsed = extract_json_array(response.text)
            if not isinstance(parsed, list):
                raise ValueError("Model output was not a JSON array.")
            return parsed

        except Exception as e:
            last_error = e
            err = str(e)

            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", err, re.IGNORECASE)
                wait_time = float(match.group(1)) + 2 if match else 65.0
                print(f"Rate limit hit. Sleeping for {wait_time:.1f}s before retry...")
                time.sleep(wait_time)
                continue

            raise

    raise RuntimeError(f"Max retries exceeded for this batch: {last_error}")


def process_dataset(input_csv, output_jsonl):
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not found.")

    client = genai.Client(api_key=api_key)

    df = pd.read_csv(input_csv, dtype=str, keep_default_na=False)
    df = normalize_columns(df)

    required_columns = ["title", "body", "url", "veracity_assessment"]
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[df["veracity_assessment"].isin(ALLOWED_VERACITY)].copy()
    df.reset_index(drop=True, inplace=True)

    # Start from row 610 onward (0-based index 609)
    start_row = 609
    if start_row >= len(df):
        print(f"Start row {start_row + 1} exceeds dataset size {len(df)}. Nothing to process.")
        return

    df = df.iloc[start_row:].copy()
    df.reset_index(drop=True, inplace=True)

    total_rows = len(df)
    total_batches = math.ceil(total_rows / BATCH_SIZE)

    with open(output_jsonl, "a", encoding="utf-8") as outfile:
        for batch_index in range(total_batches):
            start = batch_index * BATCH_SIZE
            end = min(start + BATCH_SIZE, total_rows)
            batch_df = df.iloc[start:end].copy()
            batch_payload = build_batch_payload(batch_df)

            original_start = start_row + start + 1
            original_end = start_row + end

            try:
                raw_results = call_gemini_batch(client, batch_payload)

                repaired_results = []
                for i, source_item in enumerate(batch_payload):
                    if i < len(raw_results):
                        repaired = validate_and_repair_item(raw_results[i], source_item)
                    else:
                        repaired = default_record(
                            source_item["title"],
                            source_item["body"],
                            source_item["url"],
                            source_item["veracity_assessment"]
                        )
                    repaired_results.append(repaired)

                for item in repaired_results:
                    outfile.write(json.dumps(item, ensure_ascii=False) + "\n")

                print(f"Processed batch {batch_index + 1}/{total_batches} (original rows {original_start}-{original_end})")
                time.sleep(REQUEST_DELAY_SECONDS)

            except Exception as e:
                print(f"Batch {batch_index + 1}/{total_batches} failed: {e}")
                for source_item in batch_payload:
                    fallback = default_record(
                        source_item["title"],
                        source_item["body"],
                        source_item["url"],
                        source_item["veracity_assessment"]
                    )
                    outfile.write(json.dumps(fallback, ensure_ascii=False) + "\n")
                print(f"Wrote fallback records for original rows {original_start}-{original_end}")
                time.sleep(REQUEST_DELAY_SECONDS)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python generate.py input.csv output.jsonl")
        sys.exit(1)

    process_dataset(sys.argv[1], sys.argv[2])