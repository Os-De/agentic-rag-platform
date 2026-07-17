"""Calibrated LLM-as-judge (Program Phases 3–4) for fuzzy metrics.

Judge rule: never trust an uncalibrated judge. Run `calibrate()` against
practitioner labels first; use the judge only where within-one agreement ≥ 0.8,
route the rest to human review.

Backends: local Ollama (free) or OpenAI (set OPENAI_API_KEY). Judge model should
differ from the model under test to reduce self-preference bias.
"""

import json
import os
import re

import httpx

FAITHFULNESS_RUBRIC = """\
You are a strict evaluator. Score how faithful the ANSWER is to the CONTEXT.
5 = every claim supported by the context; 3 = minor unsupported details;
1 = contradicts or invents facts. Reply with ONLY JSON: {{"score": <1-5>, "reason": "<short>"}}

QUESTION: {question}
CONTEXT:
{context}
ANSWER:
{answer}

JSON:"""

QUALITY_RUBRIC = """\
You are a strict evaluator. Score the ANSWER's overall quality for the QUESTION:
correctness of focus, completeness, clarity, appropriate length.
5 = excellent; 3 = acceptable; 1 = useless.
Reply with ONLY JSON: {{"score": <1-5>, "reason": "<short>"}}

QUESTION: {question}
ANSWER:
{answer}

JSON:"""


def _parse_verdict(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            score = int(data.get("score", 0))
            if 1 <= score <= 5:
                return {"score": score, "reason": str(data.get("reason", ""))[:300]}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return {"score": 0, "reason": f"unparseable: {raw[:120]}"}  # 0 = judge failure


def _ollama(prompt: str, model: str, base_url: str) -> str:
    r = httpx.post(
        f"{base_url}/api/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "stream": False, "options": {"temperature": 0}},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _openai(prompt: str, model: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": model, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def judge(
    kind: str,  # "faithfulness" | "quality"
    question: str,
    answer: str,
    context: str = "",
    backend: str = "ollama",
    model: str | None = None,
    ollama_base_url: str | None = None,
) -> dict:
    rubric = FAITHFULNESS_RUBRIC if kind == "faithfulness" else QUALITY_RUBRIC
    prompt = rubric.format(question=question, context=context[:6000], answer=answer[:4000])
    if backend == "openai":
        raw = _openai(prompt, model or "gpt-4o-mini")
    else:
        raw = _ollama(prompt, model or "qwen2.5:7b",
                      ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    return _parse_verdict(raw)


def calibrate(judge_scores: list[int], human_scores: list[int]) -> dict:
    """Agreement stats between judge and practitioner labels on the same rows."""
    pairs = [(j, h) for j, h in zip(judge_scores, human_scores, strict=False) if j > 0]
    if not pairs:
        return {"n": 0, "usable": False}
    n = len(pairs)
    exact = sum(1 for j, h in pairs if j == h) / n
    within_one = sum(1 for j, h in pairs if abs(j - h) <= 1) / n
    mae = sum(abs(j - h) for j, h in pairs) / n
    return {
        "n": n,
        "exact_agreement": round(exact, 3),
        "within_one_agreement": round(within_one, 3),
        "mean_abs_error": round(mae, 3),
        "usable": within_one >= 0.8,  # else: human-in-the-loop for this metric
    }
