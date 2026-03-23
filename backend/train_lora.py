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
    data_path: str = "data/data_train.jsonl"
    val_split: float = 0.20         # 70/20/10 split
    test_split: float = 0.10
    max_seq_length: int = 2048

    # LoRA — reduced to combat overfitting
    lora_r: int = 8                 # was 16
    lora_alpha: int = 16            # was 32
    lora_dropout: float = 0.05
    lora_target_modules: list = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj"
    ])

    # Training
    output_dir: str = "./tinyllama-lora-output3"
    num_train_epochs: int = 8           # was 10
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    lr_scheduler_type: str = "cosine"
    warmup_steps: int = 50
    weight_decay: float = 0.01          # was 0.001
    max_grad_norm: float = 0.3
    fp16: bool = True
    bf16: bool = False
    logging_steps: int = 10
    save_strategy: str = "epoch"
    seed: int = 42

    # Log file
    log_file: str = "training_log3.txt"

cfg = TrainConfig()

# ---------------------------------------------
# 2. PROMPT TEMPLATE
# ---------------------------------------------

def build_prompt(sample: dict) -> str:
    instruction = sample.get("instruction", "").strip()
    inp = sample.get("input", "")
    output = sample.get("output", "")

    if isinstance(inp, dict):
        url = inp.get("source_url", "").strip()
        url_line = f"\nSource URL: {url}" if url and url != "not provided" else ""
        inp = f"Title: {inp.get('title', '')}\n\n{inp.get('body', '')}{url_line}"

    if isinstance(output, dict):
        output = json.dumps(output, ensure_ascii=False)

    return (
        f"<|system|>\nYou are an expert media analyst.\n</s>\n"
        f"<|user|>\n{instruction}\n\nArticle:\n{inp}\n</s>\n"
        f"<|assistant|>\n{output}\n</s>"
    )


# ---------------------------------------------
# 3. DATA LOADING WITH 70/20/10 SPLIT
# ---------------------------------------------

def load_and_split(path: str, val_split: float, test_split: float, seed: int):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    texts = [build_prompt(r) for r in records]
    full_dataset = Dataset.from_dict({"text": texts})

    # First split off the test set (10%)
    temp_split = full_dataset.train_test_split(
        test_size=test_split,
        seed=seed,
        shuffle=True
    )
    test_dataset = temp_split["test"]
    remaining    = temp_split["train"]          # 90% remaining

    # Split remaining into train (70%) and val (20%)
    # val is 20/90 ≈ 0.2222 of the remaining 90%
    val_ratio = val_split / (1.0 - test_split)
    train_val_split = remaining.train_test_split(
        test_size=val_ratio,
        seed=seed,
        shuffle=True
    )
    train_dataset = train_val_split["train"]
    val_dataset   = train_val_split["test"]

    print(f"[INFO] Total samples : {len(full_dataset)}")
    print(f"[INFO] Train samples : {len(train_dataset)}  ({len(train_dataset)/len(full_dataset)*100:.1f}%)")
    print(f"[INFO] Val samples   : {len(val_dataset)}   ({len(val_dataset)/len(full_dataset)*100:.1f}%)")
    print(f"[INFO] Test samples  : {len(test_dataset)}  ({len(test_dataset)/len(full_dataset)*100:.1f}%)")

    return train_dataset, val_dataset, test_dataset


# ---------------------------------------------
# 4. PER-EPOCH LOG CALLBACK
# ---------------------------------------------

class EpochLoggerCallback(TrainerCallback):

    def __init__(self, log_file: str):
        self.log_file = log_file
        self._epoch_start = None
        self._step_logs: list = []

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
                "grad_norm": round(logs.get("grad_norm", 0), 4),
            }
            self._step_logs.append(entry)
            self._write(
                f"  step {entry['step']:>6} | train_loss {entry['loss']:.4f} "
                f"| lr {entry['lr']} | grad_norm {entry['grad_norm']:.4f}"
            )
        if "eval_loss" in logs:
            self._write(
                f"  step {state.global_step:>6} | val_loss   {logs['eval_loss']:.4f}"
            )

    def on_epoch_end(self, args, state: TrainerState, control: TrainerControl, **kwargs):
        elapsed = time.time() - self._epoch_start if self._epoch_start else 0
        epoch_num = math.ceil(state.epoch) if state.epoch else "?"

        train_losses = [s["loss"] for s in self._step_logs if "loss" in s]
        avg_train = round(sum(train_losses) / len(train_losses), 4) if train_losses else "N/A"
        min_train = round(min(train_losses), 4) if train_losses else "N/A"

        eval_entries = [l for l in state.log_history if "eval_loss" in l]
        val_loss_str = f"{eval_entries[-1]['eval_loss']:.4f}" if eval_entries else "N/A"

        self._write(f"\n  -- Epoch {epoch_num} Summary --")
        self._write(f"  Avg train loss : {avg_train}")
        self._write(f"  Min train loss : {min_train}")
        self._write(f"  Val loss       : {val_loss_str}")
        self._write(f"  Total steps    : {state.global_step}")
        self._write(f"  Elapsed        : {elapsed:.1f}s  ({elapsed/60:.1f} min)")
        self._write(f"  Timestamp      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write("")

    def on_train_end(self, args, state: TrainerState, control: TrainerControl, **kwargs):
        self._write("\n" + "=" * 60)
        self._write(f"TRAINING COMPLETE -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"Best metric  : {state.best_metric}")
        self._write(f"Total steps  : {state.global_step}")
        self._write("=" * 60 + "\n")


# ---------------------------------------------
# 5. CONVERGENCE CALLBACK (monitors val_loss)
# ---------------------------------------------

class ConvergenceCallback(TrainerCallback):
    """
    Monitors validation loss after each epoch.
    - Never stops before min_epochs
    - Stops after patience epochs with no improvement > min_delta
    - Falls back to train loss if val loss is unavailable
    """

    def __init__(
        self,
        min_epochs: int = 4,
        patience: int = 3,
        min_delta: float = 0.005,
        log_file: str = "training_log3.txt"
    ):
        self.min_epochs = min_epochs
        self.patience = patience
        self.min_delta = min_delta
        self.log_file = log_file
        self.best_loss = float("inf")
        self.patience_counter = 0
        self.epoch_count = 0

    def _write(self, text: str):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def on_epoch_end(self, args, state: TrainerState, control: TrainerControl, **kwargs):
        self.epoch_count += 1

        eval_entries  = [l for l in state.log_history if "eval_loss" in l]
        train_entries = [l for l in state.log_history if "loss" in l and "eval_loss" not in l]

        if eval_entries:
            current_loss = eval_entries[-1]["eval_loss"]
            loss_label = "val_loss"
        elif train_entries:
            current_loss = train_entries[-1]["loss"]
            loss_label = "train_loss (no val available)"
        else:
            return

        improvement = self.best_loss - current_loss

        if improvement > self.min_delta:
            self.best_loss = current_loss
            self.patience_counter = 0
            status = f"  Improved -- best {loss_label} now {self.best_loss:.4f}"
        else:
            self.patience_counter += 1
            status = (
                f"  No improvement (delta={improvement:.4f} < {self.min_delta}) "
                f"| patience {self.patience_counter}/{self.patience}"
            )

        self._write(f"\n  [Convergence Monitor -- Epoch {self.epoch_count}]")
        self._write(f"  Monitoring     : {loss_label}")
        self._write(f"  Current loss   : {current_loss:.4f}")
        self._write(f"  Best loss      : {self.best_loss:.4f}")
        self._write(status)

        if self.epoch_count < self.min_epochs:
            self._write(f"  Continuing -- min_epochs ({self.min_epochs}) not reached yet")
            return

        if self.patience_counter >= self.patience:
            self._write(
                f"\n  EARLY STOP -- no improvement for {self.patience} "
                f"consecutive epochs after epoch {self.epoch_count}."
            )
            control.should_training_stop = True


# ---------------------------------------------
# 6. MODEL + TOKENIZER
# ---------------------------------------------

def load_model_and_tokenizer(cfg: TrainConfig):
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name, trust_remote_code=True)
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
            device_map={"": 0},
            trust_remote_code=True,
        )
        model = prepare_model_for_kbit_training(model)
    else:
        model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name,
            torch_dtype=torch.float16,
            device_map={"": 0},
            trust_remote_code=True,
        )

    model.config.use_cache = False
    model.config.pretraining_tp = 1
    return model, tokenizer


# ---------------------------------------------
# 7. LORA CONFIG
# ---------------------------------------------

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
# 8. TRAINING ARGUMENTS
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
        eval_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        gradient_checkpointing=True,
        optim="paged_adamw_32bit",
        report_to="none",
        seed=cfg.seed,
        dataloader_pin_memory=False,
        remove_unused_columns=False,
    )


# ---------------------------------------------
# 9. TEST SET EVALUATION
# ---------------------------------------------

def evaluate_test_set(trainer: SFTTrainer, test_dataset: Dataset, log_file: str):
    print("[INFO] Evaluating on held-out test set...")
    test_results = trainer.evaluate(eval_dataset=test_dataset, metric_key_prefix="test")
    test_loss = test_results.get("test_loss", "N/A")

    print(f"[INFO] Test Loss: {test_loss}")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 60 + "\n")
        f.write("TEST SET EVALUATION\n")
        f.write(f"  Test Loss : {test_loss:.4f}\n" if isinstance(test_loss, float) else f"  Test Loss : {test_loss}\n")
        f.write("=" * 60 + "\n")

    return test_results


# ---------------------------------------------
# 10. MAIN
# ---------------------------------------------

def main():
    print(f"[INFO] Loading dataset from: {cfg.data_path}")
    train_dataset, val_dataset, test_dataset = load_and_split(
        cfg.data_path, cfg.val_split, cfg.test_split, cfg.seed
    )
    print(f"[INFO] Sample prompt preview:\n{train_dataset[0]['text'][:300]}...\n")

    print("[INFO] Loading model and tokenizer...")
    model, tokenizer = load_model_and_tokenizer(cfg)

    print("[INFO] Building LoRA config and training args...")
    lora_config   = build_lora_config(cfg)
    training_args = build_training_args(cfg)

    epoch_logger = EpochLoggerCallback(log_file=cfg.log_file)
    convergence_monitor = ConvergenceCallback(
        min_epochs=4,
        patience=3,
        min_delta=0.005,
        log_file=cfg.log_file
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        peft_config=lora_config,
        processing_class=tokenizer,
        args=training_args,
        callbacks=[epoch_logger, convergence_monitor],
        formatting_func=lambda x: x["text"],
    )

    trainer.model.print_trainable_parameters()

    print(f"[INFO] Starting training -- logs -> {cfg.log_file}")
    trainer.train()

    # Evaluate on held-out test set after training
    evaluate_test_set(trainer, test_dataset, cfg.log_file)

    print("[INFO] Saving final adapter weights...")
    trainer.model.save_pretrained(cfg.output_dir)
    tokenizer.save_pretrained(cfg.output_dir)
    print(f"[INFO] Done. Model saved to : {cfg.output_dir}")
    print(f"[INFO] Training log saved to: {cfg.log_file}")


if __name__ == "__main__":
    main()