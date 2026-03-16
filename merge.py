from transformers import AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL = "./mistral7b"
LORA_PATH = "./info_lora"

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype="auto",
)

model = PeftModel.from_pretrained(model, LORA_PATH)
model = model.merge_and_unload()

model.save_pretrained("./mistral_info_merged")