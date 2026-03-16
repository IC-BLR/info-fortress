
import torch
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer

MODEL_NAME = "meta-llama/Meta-Llama-3-3B-Instruct"

# Load model + tokenizer
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16,
    device_map="auto"
)

# LoRA config
lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, lora_config)

dataset = load_dataset("json", data_files="info_war.jsonl")

training_args = TrainingArguments(
    output_dir="./info_lora",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    num_train_epochs=3,
    logging_steps=10,
    save_strategy="epoch",
    fp16=True
)

trainer = SFTTrainer(
    model=model,
    train_dataset=dataset["train"],
    dataset_text_field="messages",
    args=training_args
)

trainer.train()
model.save_pretrained("./info_lora")

print("Training complete. LoRA adapter saved to ./info_lora")
