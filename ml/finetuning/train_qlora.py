"""QLoRA fine-tuning — config-driven, MLflow-tracked. Run on a GPU machine (see README).

    python train_qlora.py --config config.yaml
"""

import argparse
import sys
from pathlib import Path

try:
    import mlflow
    import torch
    import yaml
    from datasets import load_dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer
except ImportError as exc:  # keep repo importable on non-GPU machines
    sys.exit(f"Missing training deps ({exc}). Run: pip install -r requirements-finetune.txt")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    mlflow.set_tracking_uri(cfg["mlflow"]["tracking_uri"])
    mlflow.set_experiment(cfg["mlflow"]["experiment"])

    quant = (
        BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        if cfg.get("load_in_4bit")
        else None
    )

    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    model = AutoModelForCausalLM.from_pretrained(
        cfg["base_model"], quantization_config=quant, device_map="auto"
    )

    lora = LoraConfig(
        r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["alpha"],
        lora_dropout=cfg["lora"]["dropout"],
        target_modules=cfg["lora"]["target_modules"],
        task_type="CAUSAL_LM",
    )

    dataset = load_dataset("json", data_files=cfg["dataset_path"], split="train")

    t = cfg["training"]
    sft_config = SFTConfig(
        output_dir=cfg["output_dir"],
        num_train_epochs=t["num_train_epochs"],
        per_device_train_batch_size=t["per_device_train_batch_size"],
        gradient_accumulation_steps=t["gradient_accumulation_steps"],
        learning_rate=float(t["learning_rate"]),
        lr_scheduler_type=t["lr_scheduler_type"],
        warmup_ratio=t["warmup_ratio"],
        max_seq_length=t["max_seq_length"],
        logging_steps=t["logging_steps"],
        seed=t["seed"],
        report_to="mlflow",
    )

    with mlflow.start_run():
        mlflow.log_params(
            {"base_model": cfg["base_model"], **cfg["lora"], **t, "4bit": bool(quant)}
        )
        trainer = SFTTrainer(
            model=model,
            processing_class=tokenizer,
            train_dataset=dataset,
            peft_config=lora,
            args=sft_config,
        )
        trainer.train()
        trainer.save_model(cfg["output_dir"])
        mlflow.log_artifacts(cfg["output_dir"], artifact_path="adapter")
        print(f"Adapter saved → {cfg['output_dir']} and logged to MLflow.")
        # Next (README): merge adapter → GGUF → `ollama create` → A/B eval with RAGAS.


if __name__ == "__main__":
    main()
