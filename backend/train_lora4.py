import os
import json
import time
import math
import torch
from datetime import datetime
from dataclasses import dataclass, field

from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    TrainerCallback,
    TrainerState,
    TrainerControl,
    BitsAndBytesConfig,
)
from peft import LoraConfig, TaskType, prepare_model_for_kbit_training
from trl import SFTTrainer


# ---------------------------------------------
# 1. CONFIG
# ---------------------------------------------

@dataclass
class TrainConfig:
    # Model
    model_name: str = r"C:\Users\santo\Desktop\IC\info-fortress-main\info-fortress-main\backend\model"
    use_4bit: bool = False

    # Data
    data_path: str = r"C:\Users\santo\Desktop\IC\info-fortress-main\info-fortress-main\backend\data\structural_integrity_500.jsonl"
    max_seq_length: int = 1024

    # LoRA
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    lora_target_modules: list = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ])

    # Training
    output_dir: str = "./tinyllama-lora-output4"
    num_train_epochs: int = 6
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_steps: int = 30
    weight_decay: float = 0.01
    max_grad_norm: float = 0.3
    fp16: bool = True
    bf16: bool = False
    logging_steps: int = 10
    save_strategy: str = "epoch"
    save_total_limit: int = 2
    seed: int = 42

    # Log file
    log_file: str = "training_log4.txt"


cfg = TrainConfig()


# ---------------------------------------------
# 2. FORMAT DATA INTO SINGLE TEXT FIELD
# ---------------------------------------------

def build_text_from_messages(record: dict, tokenizer) -> str:
    messages = record.get("messages", [])
    if not messages:
        raise ValueError("Missing 'messages' field")

    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False
        )

    parts = []
    for msg in messages:
        role = msg["role"].strip().upper()
        content = msg["content"].strip()
        parts.append(f"{role}:\n{content}")

    return "\n\n".join(parts)


# ---------------------------------------------
# 3. DATA LOADING — TRAIN ONLY
# ---------------------------------------------

def load_train_only(path: str, seed: int, tokenizer):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                raw = json.loads(line)
                text = build_text_from_messages(raw, tokenizer)
                records.append({"text": text})

    train_dataset = Dataset.from_list(records)

    print(f"[INFO] Total / Train samples : {len(train_dataset)}")
    print(f"[INFO] Sample preview:\n{train_dataset[0]['text'][:800]}\n")

    return train_dataset


# ---------------------------------------------
# 4. PER-EPOCH LOG CALLBACK
# ---------------------------------------------

class EpochLoggerCallback(TrainerCallback):
    def __init__(self, log_file: str):
        self.log_file = log_file
        self._epoch_start = None
        self._step_logs = []

        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write("TinyLlama LoRA Training Log\n")
            f.write(f"Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

    def _write(self, text: str):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def on_epoch_begin(self, args, state: TrainerState, control: TrainerControl, **kwargs):
        self._epoch_start = time.time()
        self._step_logs = []
        epoch_num = int(state.epoch) + 1 if state.epoch else "?"
        self._write(f"\n{'─'*60}")
        self._write(f"  EPOCH {epoch_num} started -- {datetime.now().strftime('%H:%M:%S')}")
        self._write(f"{'─'*60}")

    def on_log(self, args, state: TrainerState, control: TrainerControl, logs=None, **kwargs):
        if logs is None:
            return

        if "loss" in logs:
            entry = {
                "step": state.global_step,
                "loss": round(logs.get("loss", 0), 4),
                "lr": f"{logs.get('learning_rate', 0):.2e}",
                "grad_norm": round(logs.get("grad_norm", 0), 4) if logs.get("grad_norm") is not None else 0.0,
            }
            self._step_logs.append(entry)
            self._write(
                f"  step {entry['step']:>6} | train_loss {entry['loss']:.4f} "
                f"| lr {entry['lr']} | grad_norm {entry['grad_norm']:.4f}"
            )

    def on_epoch_end(self, args, state: TrainerState, control: TrainerControl, **kwargs):
        elapsed = time.time() - self._epoch_start if self._epoch_start else 0
        epoch_num = math.ceil(state.epoch) if state.epoch else "?"

        train_losses = [s["loss"] for s in self._step_logs]
        avg_train = round(sum(train_losses) / len(train_losses), 4) if train_losses else "N/A"
        min_train = round(min(train_losses), 4) if train_losses else "N/A"

        self._write(f"\n  -- Epoch {epoch_num} Summary --")
        self._write(f"  Avg train loss : {avg_train}")
        self._write(f"  Min train loss : {min_train}")
        self._write(f"  Total steps    : {state.global_step}")
        self._write(f"  Elapsed        : {elapsed:.1f}s  ({elapsed/60:.1f} min)")
        self._write(f"  Timestamp      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write("")


# ---------------------------------------------
# 5. MODEL + TOKENIZER
# ---------------------------------------------

def load_model_and_tokenizer(cfg: TrainConfig):
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name, trust_remote_code=True)

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    tokenizer.model_max_length = cfg.max_seq_length

    if cfg.use_4bit:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
        )

    model.config.use_cache = False
    model.config.pretraining_tp = 1
    return model, tokenizer


# ---------------------------------------------
# 6. LORA CONFIG
# ---------------------------------------------

def validate_lora_targets(model, target_modules: list):
    module_names = [name for name, _ in model.named_modules()]
    found = {target: False for target in target_modules}

    for name in module_names:
        for target in target_modules:
            if name.endswith(target):
                found[target] = True

    print("[INFO] LoRA target module check:")
    for k, v in found.items():
        print(f"  - {k}: {'FOUND' if v else 'NOT FOUND'}")

    missing = [k for k, v in found.items() if not v]
    if missing:
        raise ValueError(f"LoRA target modules not found in model: {missing}")


def build_lora_config(cfg: TrainConfig) -> LoraConfig:
    return LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=cfg.lora_target_modules,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )


# ---------------------------------------------
# 7. TRAINING ARGUMENTS — NO EVAL
# ---------------------------------------------

def build_training_args(cfg: TrainConfig) -> TrainingArguments:
    return TrainingArguments(
        output_dir=cfg.output_dir,
        num_train_epochs=cfg.num_train_epochs,
        per_device_train_batch_size=cfg.per_device_train_batch_size,
        gradient_accumulation_steps=cfg.gradient_accumulation_steps,
        learning_rate=cfg.learning_rate,
        lr_scheduler_type=cfg.lr_scheduler_type,
        warmup_steps=cfg.warmup_steps,
        weight_decay=cfg.weight_decay,
        max_grad_norm=cfg.max_grad_norm,
        fp16=cfg.fp16,
        bf16=cfg.bf16,
        logging_steps=cfg.logging_steps,
        save_strategy=cfg.save_strategy,
        eval_strategy="no",          # no evaluation
        save_total_limit=cfg.save_total_limit,
        gradient_checkpointing=True,
        optim="paged_adamw_32bit",
        report_to="none",
        seed=cfg.seed,
        dataloader_pin_memory=False,
        remove_unused_columns=False,
    )


# ---------------------------------------------
# 8. TRAINER
# ---------------------------------------------

def make_trainer(model, tokenizer, args, train_dataset, peft_config, callbacks):
    return SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=None,
        peft_config=peft_config,
        processing_class=tokenizer,
        args=args,
        callbacks=callbacks,
    )


# ---------------------------------------------
# 9. MAIN
# ---------------------------------------------

def main():
    print("[INFO] Loading model and tokenizer...")
    model, tokenizer = load_model_and_tokenizer(cfg)

    print(f"[INFO] Loading dataset from: {cfg.data_path}")
    train_dataset = load_train_only(cfg.data_path, cfg.seed, tokenizer)

    print("[INFO] Validating LoRA target modules...")
    validate_lora_targets(model, cfg.lora_target_modules)

    print("[INFO] Building LoRA config and training args...")
    lora_config = build_lora_config(cfg)
    training_args = build_training_args(cfg)

    epoch_logger = EpochLoggerCallback(log_file=cfg.log_file)

    trainer = make_trainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=train_dataset,
        peft_config=lora_config,
        callbacks=[epoch_logger],
    )

    trainer.model.print_trainable_parameters()

    print(f"[INFO] Starting training -- logs -> {cfg.log_file}")
    trainer.train()

    print("[INFO] Saving final adapter weights...")
    trainer.model.save_pretrained(cfg.output_dir)
    tokenizer.save_pretrained(cfg.output_dir)

    print(f"[INFO] Done. Model saved to : {cfg.output_dir}")
    print(f"[INFO] Training log saved to: {cfg.log_file}")


if __name__ == "__main__":
    main()