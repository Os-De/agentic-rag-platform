# Fine-Tuning (Phase 7) — QLoRA

Goal: adapt a small open model to your domain/style, track everything in MLflow, and serve it through the same `/chat` API via Ollama. See ADR-008.

## Hardware strategy

| Where | Models | Notes |
|---|---|---|
| Local consumer GPU (8–24 GB) | 1–3B full QLoRA, 7–8B with 4-bit + small batch | Windows: use WSL2 for bitsandbytes |
| Cloud GPU (Colab / Kaggle / Azure ML) | 7–8B comfortably | Same scripts, same config file |

## Workflow

```bash
pip install -r requirements-finetune.txt        # GPU machine only
python prepare_dataset.py                       # → dataset.jsonl (instruction format)
docker compose --profile mlops up -d            # MLflow at :5000
python train_qlora.py --config config.yaml      # logs to MLflow, saves LoRA adapter
```

Then serve: merge adapter → convert to GGUF (llama.cpp) → `ollama create mydomain-model -f Modelfile` → call the API with `"model": "mydomain-model"`.

**Promotion rule:** only replace the serving model if the Phase 6 RAGAS evaluation improves. No vibes-based shipping.

## Dataset format (`dataset.jsonl`)

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

Good first datasets: Q/A pairs generated from your ingested documents (use the platform itself to draft them, then curate by hand — quality over quantity, 200 curated > 20k scraped).
