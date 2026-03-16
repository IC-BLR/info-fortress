import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "./mistral7b"

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="auto"
)

prompt = """
Should we increase leverage to 3.5x EBITDA for expansion?
"""

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

outputs = model.generate(
    **inputs,
    max_new_tokens=200,
    temperature=0.7
)

print("\n--- BASE MODEL OUTPUT ---\n")
print(tokenizer.decode(outputs[0], skip_special_tokens=True))