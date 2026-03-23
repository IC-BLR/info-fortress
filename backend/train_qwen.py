import os
import json
import random
import inspect
from typing import Any, Dict

import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    set_seed,
)
from peft import LoraConfig, TaskType
from trl import SFTTrainer, SFTConfig


# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

MODEL_PATH = os.environ.get("QWEN_MODEL_PATH", "./qwen")
TRAIN_FILE = "qwen_guardrail_train.jsonl"
EVAL_FILE = "qwen_guardrail_eval.jsonl"
OUTPUT_DIR = "./qwen_guardrail_lora"

MAX_SEQ_LENGTH = 768
SAMPLE_EVAL_PREDICTIONS = 5

LEARNING_RATE = 2e-4
NUM_TRAIN_EPOCHS = 4
TRAIN_BATCH_SIZE = 1
EVAL_BATCH_SIZE = 1
GRADIENT_ACCUMULATION_STEPS = 4
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.05
SEED = 42

# Keep this False unless you have confirmed the tokenizer chat template
# supports assistant masks for assistant-only loss.
ASSISTANT_ONLY_LOSS = False

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get_torch_dtype(device: str):
    if device == "cuda":
        return torch.float16
    if device == "mps":
        return torch.float16
    return torch.float32


def ensure_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Required file not found: {path}")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().tolist()
    return value


def extract_verdict(text: str) -> str:
    try:
        obj = json.loads(text)
        return str(obj.get("verdict", "")).strip()
    except Exception:
        return ""


def build_sft_config(device: str) -> SFTConfig:
    sig = inspect.signature(SFTConfig.__init__)

    kwargs: Dict[str, Any] = {
        "output_dir": OUTPUT_DIR,
        "per_device_train_batch_size": TRAIN_BATCH_SIZE,
        "per_device_eval_batch_size": EVAL_BATCH_SIZE,
        "gradient_accumulation_steps": GRADIENT_ACCUMULATION_STEPS,
        "learning_rate": LEARNING_RATE,
        "num_train_epochs": NUM_TRAIN_EPOCHS,
        "weight_decay": WEIGHT_DECAY,
        "warmup_ratio": WARMUP_RATIO,
        "logging_steps": 1,
        "save_strategy": "epoch",
        "save_total_limit": 2,
        "report_to": "none",
        "optim": "adamw_torch",
        "gradient_checkpointing": True,
        "max_length": MAX_SEQ_LENGTH,
        "packing": False,
        "assistant_only_loss": ASSISTANT_ONLY_LOSS,
        "fp16": device == "cuda",
        "bf16": False,
        "seed": SEED,
    }

    if "eval_strategy" in sig.parameters:
        kwargs["eval_strategy"] = "epoch"
    elif "evaluation_strategy" in sig.parameters:
        kwargs["evaluation_strategy"] = "epoch"

    return SFTConfig(**kwargs)


def main() -> None:
    set_seed(SEED)
    random.seed(SEED)

    ensure_file(TRAIN_FILE)
    ensure_file(EVAL_FILE)
    ensure_dir(OUTPUT_DIR)

    device = get_device()
    dtype = get_torch_dtype(device)

    print(f"device: {device}")
    print(f"dtype: {dtype}")
    print(f"model path: {MODEL_PATH}")
    print(f"train file: {TRAIN_FILE}")
    print(f"eval file:  {EVAL_FILE}")
    print(f"output dir: {OUTPUT_DIR}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

    # Chat models rely on the tokenizer's chat template.
    if not getattr(tokenizer, "chat_template", None):
        raise ValueError(
            "Tokenizer has no chat_template. Qwen chat fine-tuning expects a tokenizer with a chat template."
        )

    # Some chat models do not define a pad token. Use eos as fallback.
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
    )

    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()

    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    model.config.use_cache = False
    model = model.to(device)

    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        target_modules="all-linear",
    )

    dataset = load_dataset(
        "json",
        data_files={
            "train": TRAIN_FILE,
            "eval": EVAL_FILE,
        },
    )

    print(f"train rows: {len(dataset['train'])}")
    print(f"eval rows:  {len(dataset['eval'])}")

    if "messages" not in dataset["train"].column_names:
        raise ValueError("Train file must contain a 'messages' column.")
    if "messages" not in dataset["eval"].column_names:
        raise ValueError("Eval file must contain a 'messages' column.")

    sft_config = build_sft_config(device)

    trainer_kwargs: Dict[str, Any] = {
        "model": model,
        "args": sft_config,
        "train_dataset": dataset["train"],
        "eval_dataset": dataset["eval"],
        "peft_config": peft_config,
    }

    trainer_sig = inspect.signature(SFTTrainer.__init__)
    if "processing_class" in trainer_sig.parameters:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_sig.parameters:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = SFTTrainer(**trainer_kwargs)

    print("\nStarting training...\n")
    train_result = trainer.train()

    print("\nRunning final evaluation...\n")
    eval_metrics = trainer.evaluate()

    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    metrics = {
        "train_metrics": {k: to_jsonable(v) for k, v in train_result.metrics.items()},
        "eval_metrics": {k: to_jsonable(v) for k, v in eval_metrics.items()},
        "config": {
            "model_path": MODEL_PATH,
            "train_file": TRAIN_FILE,
            "eval_file": EVAL_FILE,
            "output_dir": OUTPUT_DIR,
            "max_seq_length": MAX_SEQ_LENGTH,
            "learning_rate": LEARNING_RATE,
            "num_train_epochs": NUM_TRAIN_EPOCHS,
            "train_batch_size": TRAIN_BATCH_SIZE,
            "eval_batch_size": EVAL_BATCH_SIZE,
            "gradient_accumulation_steps": GRADIENT_ACCUMULATION_STEPS,
            "assistant_only_loss": ASSISTANT_ONLY_LOSS,
        },
    }

    metrics_path = os.path.join(OUTPUT_DIR, "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print("\nSaved adapter and metrics:")
    print(f"  adapter dir: {OUTPUT_DIR}")
    print(f"  metrics:     {metrics_path}")

    # -----------------------------------------------------------------
    # Sample eval generations
    # -----------------------------------------------------------------

    print("\nSample eval predictions:\n")

    # Turn cache back on for generation
    trainer.model.config.use_cache = True
    trainer.model.eval()

    sample_count = min(SAMPLE_EVAL_PREDICTIONS, len(dataset["eval"]))
    sample_indices = list(range(len(dataset["eval"])))
    random.Random(SEED).shuffle(sample_indices)
    sample_indices = sample_indices[:sample_count]

    for idx in sample_indices:
        row = dataset["eval"][idx]
        messages = row["messages"]

        prompt_messages = messages[:-1]
        gold_text = messages[-1]["content"]

        text = tokenizer.apply_chat_template(
            prompt_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_SEQ_LENGTH,
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = trainer.model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                num_beams=1,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[-1]:]
        pred_text = tokenizer.decode(generated, skip_special_tokens=True).strip()

        print("-" * 80)
        print("USER PROMPT:")
        print(prompt_messages[-1]["content"])
        print("\nGOLD:")
        print(gold_text)
        print("\nPRED:")
        print(pred_text)
        print("\nGOLD VERDICT:", extract_verdict(gold_text))
        print("PRED VERDICT:", extract_verdict(pred_text))
        print("-" * 80)

    print("\nDone.")


if __name__ == "__main__":
    main()