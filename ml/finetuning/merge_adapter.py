"""Merge a trained LoRA adapter into the base model (Phase 7, step 2 of serving).

    python merge_adapter.py --config config.yaml --out outputs/merged

Then convert to GGUF and serve with Ollama (see README / Modelfile.template):
    python llama.cpp/convert_hf_to_gguf.py outputs/merged --outfile domain.gguf
    ollama create domain-model -f Modelfile
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
except ImportError as exc:
    sys.exit(f"Missing training deps ({exc}). Run: pip install -r requirements-finetune.txt")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="outputs/merged")
    args = parser.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    print(f"Loading base model {cfg['base_model']} (fp16, no quantization for merging)…")
    base = AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype="auto")
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])

    print(f"Applying adapter from {cfg['output_dir']}…")
    model = PeftModel.from_pretrained(base, cfg["output_dir"])
    merged = model.merge_and_unload()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(out)
    tokenizer.save_pretrained(out)
    print(f"Merged model saved → {out}")
    print("Next: convert to GGUF (llama.cpp) → ollama create → A/B eval (Phase 6 gate).")


if __name__ == "__main__":
    main()
