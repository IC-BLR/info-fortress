import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_MODEL = "./mistral7b"
LORA_PATH = "./cfo_lora"   # your saved adapter folder

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="auto"
)

model = PeftModel.from_pretrained(model, LORA_PATH)

prompt = """
Proposal: 3.7x leverage, IRR 18%, DSCR 1.9.
"""

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

outputs = model.generate(
    **inputs,
    max_new_tokens=150,
    temperature=0.2,
    top_p=0.9,
    repetition_penalty=1.2,
    do_sample=True
)

print("\n--- LORA MODEL OUTPUT ---\n")
print(tokenizer.decode(outputs[0], skip_special_tokens=True))