import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer

MODEL_PATH = "./mistral7b"  # <-- your local folder

import os

print("MODEL_PATH:", MODEL_PATH)
print("Files inside folder:", os.listdir(MODEL_PATH))
# ----------------------------
# Load tokenizer
# ----------------------------
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
tokenizer.pad_token = tokenizer.eos_token

# ----------------------------
# Load model in 4-bit (recommended)
# ----------------------------
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4"
)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    quantization_config=bnb_config,
    device_map="auto",
    dtype=torch.float16
)
#model = AutoModelForCausalLM.from_pretrained(
#    MODEL_PATH,
#    torch_dtype=torch.float16,
#    load_in_4bit=True,
#    device_map="auto"
#)

model.gradient_checkpointing_enable()
model.enable_input_require_grads()

# ----------------------------
# LoRA configuration
# ----------------------------
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],  # Mistral attention modules
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, lora_config)

model.print_trainable_parameters()

# ----------------------------
# Load dataset
# ----------------------------
dataset = load_dataset("json", data_files="info_war.jsonl", split="train")

# Format messages → text
def format_chat(example):
    text = ""
    for msg in example["messages"]:
        text += f"<|{msg['role']}|>\n{msg['content']}\n"
    return {"text": text}

dataset = dataset.map(format_chat)

# ----------------------------
# Training args
# ----------------------------
training_args = TrainingArguments(
    output_dir="./info_lora",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    num_train_epochs=3,
    logging_steps=10,
    save_strategy="epoch",
    bf16=True,
    optim="adamw_torch"
)

# ----------------------------
# Trainer
# ----------------------------
from trl import SFTTrainer, SFTConfig

# ----------------------------
# SFT Config (replaces TrainingArguments)
# ----------------------------
sft_config = SFTConfig(
    output_dir="./info_lora",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    num_train_epochs=3,
    logging_steps=10,
    save_strategy="epoch",
    max_length=2048,
    optim="adamw_torch",
)

# ----------------------------
# Trainer
# ----------------------------
trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    args=sft_config,
)

trainer.train()

model.save_pretrained("./info_lora")
tokenizer.save_pretrained("./info_lora")

print("LoRA training complete.")
