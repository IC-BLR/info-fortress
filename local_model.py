import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "./mistral7b"
LORA_PATH = "./info_lora"

print("Loading base model...")

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="auto"
)

model = PeftModel.from_pretrained(model, LORA_PATH)

model.eval()

print("Model loaded successfully.")

def generate_response(system_message: str, user_message: str) -> str:
    prompt = f"""<s>[INST] <<SYS>>
{system_message}
<</SYS>>

{user_message} [/INST]"""

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=800,
            temperature=0.2,
            top_p=0.9,
            do_sample=True
        )

    return tokenizer.decode(outputs[0], skip_special_tokens=True)