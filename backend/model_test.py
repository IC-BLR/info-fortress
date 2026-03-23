import json
import re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL = r"C:\Users\santo\Desktop\IC\info-fortress-main\info-fortress-main\backend\model"
LORA_PATH  = r"C:\Users\santo\Desktop\IC\info-fortress-main\info-fortress-main\backend\tinyllama-lora-output2"

MAX_NEW_TOKENS = 300

print("[INFO] Loading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print("[INFO] Loading base model...")
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True,
)

print("[INFO] Loading LoRA adapter...")
model = PeftModel.from_pretrained(model, LORA_PATH)
model.eval()


def build_prompt(title: str, body: str, url: str) -> str:
    """
    Matches the chat-template format used during training.
    """
    messages = [
        {
            "role": "system",
            "content": "You are an expert media analyst."
        },
        {
            "role": "user",
            "content": (
                "Analyze this article for misinformation and narrative risk signals.\n\n"
                f"Article:\n{json.dumps({'title': title, 'body': body, 'source_url': url}, ensure_ascii=False)}"
            )
        }
    ]

    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True   # lets model know it should now respond
        )

    # Fallback if no chat template
    return (
        f"SYSTEM:\nYou are an expert media analyst.\n\n"
        f"USER:\nAnalyze this article for misinformation and narrative risk signals.\n\n"
        f"Article:\n{json.dumps({'title': title, 'body': body, 'source_url': url}, ensure_ascii=False)}\n\n"
        f"ASSISTANT:\n"
    )


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Could not parse valid JSON from model output.")


def generate_output(title: str, body: str, url: str) -> str:
    prompt = build_prompt(title, body, url)

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
    ).to(model.device)

    input_len = inputs["input_ids"].shape[1]
    print(f"[INFO] Prompt token count: {input_len}")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.1,
        )

    # Decode only the newly generated tokens
    generated_ids = outputs[0][input_len:]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


if __name__ == "__main__":
    title ="Trump Threatens Airstrikes On U.S. Gas Stations"
    body ="WASHINGTON—In a promise to address the pain Americans were feeling at the pump as his war with Iran approached its fourth week, President Donald Trump threatened Friday to launch airstrikes against U.S. gas stations if they did not lower their prices. “These terrible places must stop overcharging Americans every time they put fuel in their car, or I will have no choice but to unleash a massive bombing campaign against them,” Trump said during a White House press briefing, stating that he had already asked the U.S. Navy to send aircraft carriers to regions where American gas stations operate. “Someone told me the price of unleaded gasoline in our country has risen 32% in the past month. Can you believe that? So I have instructed our intelligence community to provide me with a list of targets among the QuikTrips, 7-Elevens, and Kum & Go’s, and Casey’s General Stores responsible for this outrageous situation, and if they do not comply immediately, they will face total destruction.” The president went on to criticize gas stations for raising prices at a time when the nation was engaged in a major military operation overseas, saying there would be no war profiteering on his watch."
    url = "https://theonion.com/trump-threatens-airstrikes-on-u-s-gas-stations/"

    print("\n[INFO] Running inference...\n")
    raw_output = generate_output(title, body, url)

    print("========== RAW MODEL OUTPUT ==========\n")
    print(raw_output)
    print()

    try:
        parsed = extract_json(raw_output)
        print("========== PARSED JSON OUTPUT ==========\n")
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"[WARNING] Could not parse JSON: {e}")
        print("Raw output printed above is the full model response.")