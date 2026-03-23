import json
import re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL = r"C:\Users\santo\Desktop\IC\info-fortress-main\info-fortress-main\backend\model"
LORA_PATH = r"C:\Users\santo\Desktop\IC\info-fortress-main\info-fortress-main\backend\tinyllama-lora-output2"

MAX_NEW_TOKENS = 300
CFG_MAX_INPUT_LEN = 1600  # prompt budget before generation


print("[INFO] Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print("[INFO] Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True,
)

print("[INFO] Loading LoRA adapter...")
model = PeftModel.from_pretrained(model, LORA_PATH)
model.eval()


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_prompt(title, body, url):
    input_payload = {
        "title": title,
        "body": body,
        "source_url": url
    }

    prompt = (
        "<|system|>\nYou are an expert media analyst.\n</s>\n"
        "<|user|>\nAnalyze this article for misinformation and narrative risk signals.\n\n"
        f"Article:\n{json.dumps(input_payload, ensure_ascii=False)}\n</s>\n"
        "<|assistant|>\n"
    )
    return prompt


def fit_body_to_token_budget(title: str, body: str, url: str, max_input_len: int) -> str:
    """
    Keeps prompt format unchanged, but trims the article body until the full prompt
    fits within the desired token budget.
    """
    body = normalize_text(body)

    # Fast path
    prompt = build_prompt(title, body, url)
    token_count = len(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    if token_count <= max_input_len:
        return body

    # Trim body progressively from the end until prompt fits
    low = 0
    high = len(body)
    best = ""

    while low <= high:
        mid = (low + high) // 2
        candidate_body = body[:mid]
        candidate_prompt = build_prompt(title, candidate_body, url)
        candidate_tokens = len(tokenizer(candidate_prompt, add_special_tokens=False)["input_ids"])

        if candidate_tokens <= max_input_len:
            best = candidate_body
            low = mid + 1
        else:
            high = mid - 1

    return best


def extract_json(text: str):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Could not parse valid JSON from model output.")


def get_output_block(parsed_json: dict) -> dict:
    if isinstance(parsed_json, dict):
        if "output" in parsed_json and isinstance(parsed_json["output"], dict):
            return parsed_json["output"]
        return parsed_json
    return {}


def clamp(value, low=0.0, high=1.0):
    try:
        value = float(value)
    except Exception:
        value = 0.0
    return max(low, min(high, value))


def compute_risk_score(parsed_json: dict) -> float:
    output = get_output_block(parsed_json)

    misinfo_prob = clamp(output.get("misinfo_prob", 0.0))
    source_risk = clamp(output.get("source_risk", 0.0))
    evidence_weakness = clamp(output.get("evidence_weakness", 0.0))
    sensationalism = clamp(output.get("sensationalism", 0.0))

    risk_score = (
        0.4 * misinfo_prob +
        0.3 * source_risk +
        0.2 * evidence_weakness +
        0.1 * sensationalism
    )
    return round(risk_score, 4)


def build_final_output(parsed_json: dict) -> dict:
    output = get_output_block(parsed_json)

    return {
        "risk_score": compute_risk_score(parsed_json),
        "veracity_assessment": output.get("veracity_assessment", ""),
        "article_type": output.get("article_type", ""),
        "tone_profile": output.get("tone_profile", []),
        "summary": output.get("summary", "")
    }


def generate_output(title, body, url):
    # Fit body to token budget BEFORE building final prompt
    fitted_body = fit_body_to_token_budget(title, body, url, CFG_MAX_INPUT_LEN)
    prompt = build_prompt(title, fitted_body, url)

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=CFG_MAX_INPUT_LEN,
    ).to(model.device)

    input_token_count = inputs["input_ids"].shape[1]
    print(f"[INFO] Prompt token count after body fitting: {input_token_count}")
    print(f"[INFO] Body chars used: {len(fitted_body)} / {len(body)}")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.1,
        )

    generated_ids = outputs[0][input_token_count:]
    decoded = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    return decoded


if __name__ == "__main__":

    title ="Trump Threatens Airstrikes On U.S. Gas Stations"
    body ="WASHINGTON—In a promise to address the pain Americans were feeling at the pump as his war with Iran approached its fourth week, President Donald Trump threatened Friday to launch airstrikes against U.S. gas stations if they did not lower their prices. “These terrible places must stop overcharging Americans every time they put fuel in their car, or I will have no choice but to unleash a massive bombing campaign against them,” Trump said during a White House press briefing, stating that he had already asked the U.S. Navy to send aircraft carriers to regions where American gas stations operate. “Someone told me the price of unleaded gasoline in our country has risen 32% in the past month. Can you believe that? So I have instructed our intelligence community to provide me with a list of targets among the QuikTrips, 7-Elevens, and Kum & Go’s, and Casey’s General Stores responsible for this outrageous situation, and if they do not comply immediately, they will face total destruction.” The president went on to criticize gas stations for raising prices at a time when the nation was engaged in a major military operation overseas, saying there would be no war profiteering on his watch."
    url = "https://theonion.com/trump-threatens-airstrikes-on-u-s-gas-stations/"
    print("\n[INFO] Running inference...\n")
    raw_output = generate_output(title, body, url)

    print("========== RAW MODEL OUTPUT ==========\n")
    print(raw_output)

    try:
        parsed = extract_json(raw_output)
        final_output = build_final_output(parsed)

        print("\n========== FINAL MODEL OUTPUT ==========\n")
        print(json.dumps(final_output, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"\n[WARNING] Failed to parse JSON or compute final output: {e}")