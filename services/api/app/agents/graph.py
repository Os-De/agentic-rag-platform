"""Agentic RAG graph (LangGraph) — CRAG-lite self-correction with query analysis,
routing, conversation memory, and full eval instrumentation. See architecture §4.

    START → analyze_query ──(route: direct)──→ generate_direct → END
                 │ (route: retrieve)
                 ▼
             retrieve → grade_documents ──(relevant)──→ generate → END
                 ↑           │ (none relevant, rewrites left)
                 └── rewrite_query

Eval program hooks (docs/04-eval-program.md):
- every node reports latency to rag_node_seconds{node} (p50/p95 per component)
- every LLM call's usage_metadata accumulates into state["tokens"] → cost in the API
- strategy knobs per request: grading on/off, max_rewrites override, top_k, provider/model
"""

import time
import uuid
from typing import TypedDict

import structlog
from langchain_core.documents import Document
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agents.analyzer import parse_analysis
from app.core.config import get_settings
from app.core.metrics import RAG_NODE_SECONDS
from app.llm.providers import get_chat_model
from app.rag.prompts import (
    ANALYZER_PROMPT,
    DIRECT_SYSTEM,
    GENERATION_SYSTEM,
    GENERATION_USER,
    GRADER_PROMPT,
    REWRITE_PROMPT,
    format_context,
    format_history,
)
from app.rag.retriever import retrieve, retrieve_by_phase_rank

log = structlog.get_logger()


class RAGState(TypedDict, total=False):
    question: str            # current retrieval query (analyzer/rewriter may mutate)
    original_question: str   # what the user actually asked, verbatim
    effective_question: str  # user's question after spell/ambiguity correction
    analysis: dict           # QueryAnalysis.to_dict() — exposed in the API response
    provider: str | None     # per-request LLM override (ADR-004)
    model: str | None
    top_k: int | None
    source: str | None       # Phase 2: restrict retrieval to one document
    grading: bool | None     # strategy knob: skip chunk grading when False
    max_rewrites: int | None  # strategy knob: override MAX_QUERY_REWRITES
    documents: list[Document]
    generation: str
    rewrites: int
    history: list[dict]      # Phase 3 memory: [{"question": ..., "answer": ...}]
    tokens: dict             # accumulated {"input": int, "output": int} across LLM calls


def _llm(state: RAGState):
    return get_chat_model(provider=state.get("provider"), model=state.get("model"))


def _question_for_llm(state: RAGState) -> str:
    """Grade/generate against the corrected question (typos fixed), never the
    search-optimized rewrite — the user still gets an answer to what they meant."""
    return state.get("effective_question") or state["original_question"]


def _observe(node: str, started: float) -> None:
    RAG_NODE_SECONDS.labels(node=node).observe(time.perf_counter() - started)


def _add_usage(state: RAGState, *messages) -> dict:
    """Accumulate usage_metadata (standardized across LangChain providers)."""
    tokens = dict(state.get("tokens") or {"input": 0, "output": 0})
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None) or {}
        tokens["input"] += int(usage.get("input_tokens") or 0)
        tokens["output"] += int(usage.get("output_tokens") or 0)
    return tokens


# ── Nodes ────────────────────────────────────────────────────────────────────


def analyze_query_node(state: RAGState) -> dict:
    """Spell check + ambiguity check + route + intent detection (runs first)."""
    started = time.perf_counter()
    llm = _llm(state)
    msg = llm.invoke(ANALYZER_PROMPT.format(question=state["question"]))
    analysis = parse_analysis(str(msg.content), original_question=state["question"])
    if analysis.was_corrected:
        log.info("query corrected", old=state["question"][:80],
                 new=analysis.corrected_query[:80])
    _observe("analyze_query", started)
    return {
        "question": analysis.corrected_query,
        "effective_question": analysis.corrected_query,
        "analysis": analysis.to_dict(),
        "tokens": _add_usage(state, msg),
    }


def route_after_analysis(state: RAGState) -> str:
    return (state.get("analysis") or {}).get("route", "retrieve")


def retrieve_node(state: RAGState) -> dict:
    started = time.perf_counter()
    docs = retrieve(state["question"], k=state.get("top_k"), source=state.get("source"))

    # Structural intent beats text similarity: "last/final/best phase" questions
    # pull the highest phase_number chunks first (see retriever + chunking).
    analysis = state.get("analysis") or {}
    if analysis.get("wants_latest_phase"):
        k = state.get("top_k") or get_settings().retrieval_top_k
        phase_docs = retrieve_by_phase_rank(k=k)
        seen = {(d.metadata.get("source"), d.metadata.get("chunk_index")) for d in phase_docs}
        docs = phase_docs + [
            d for d in docs
            if (d.metadata.get("source"), d.metadata.get("chunk_index")) not in seen
        ]

    log.info("retrieved", n=len(docs), query=state["question"][:80],
             phase_ranked=bool(analysis.get("wants_latest_phase")))
    _observe("retrieve", started)
    return {"documents": docs}


class _Grade(BaseModel):
    """Structured grading schema (Phase 3 upgrade over token parsing)."""

    relevant: bool = Field(description="true if the chunk helps answer the question")


def _chunk_is_relevant(llm, question: str, text: str) -> tuple[bool, object | None]:
    """Returns (relevant, raw_message_or_None). Structured-output path loses
    usage_metadata (known limitation — upgrade via include_raw in Phase 6)."""
    prompt = GRADER_PROMPT.format(question=question, document=text[:1500])
    try:
        return bool(llm.with_structured_output(_Grade).invoke(prompt).relevant), None
    except Exception:  # provider/model without structured output → token fallback
        msg = llm.invoke(prompt)
        verdict = str(msg.content).strip().lower()
        return verdict.startswith("yes") or "yes" in verdict[:10], msg


def grade_documents_node(state: RAGState) -> dict:
    """Keep only chunks the LLM judges relevant. Strategy knob: grading=False skips
    entirely (measure the quality/cost trade-off in the eval matrix)."""
    started = time.perf_counter()
    if state.get("grading") is False:
        _observe("grade_documents", started)
        log.info("grading skipped (strategy knob)")
        return {"documents": state["documents"]}

    llm = _llm(state)
    question = _question_for_llm(state)
    kept: list[Document] = []
    raw_msgs = []
    for doc in state["documents"]:
        relevant, msg = _chunk_is_relevant(llm, question, doc.page_content)
        if msg is not None:
            raw_msgs.append(msg)
        if relevant:
            kept.append(doc)
    log.info("graded", kept=len(kept), dropped=len(state["documents"]) - len(kept))
    _observe("grade_documents", started)
    return {"documents": kept, "tokens": _add_usage(state, *raw_msgs)}


def decide_after_grading(state: RAGState) -> str:
    if state["documents"]:
        return "generate"
    cap = state.get("max_rewrites")
    if cap is None:
        cap = get_settings().max_query_rewrites
    if state.get("rewrites", 0) < cap:
        return "rewrite"
    return "generate"  # nothing relevant + no rewrites left → honest "don't know"


def rewrite_query_node(state: RAGState) -> dict:
    started = time.perf_counter()
    llm = _llm(state)
    msg = llm.invoke(REWRITE_PROMPT.format(question=state["question"]))
    rewritten = str(msg.content).strip().strip('"')
    log.info("rewrote query", old=state["question"][:80], new=rewritten[:80])
    _observe("rewrite_query", started)
    return {
        "question": rewritten,
        "rewrites": state.get("rewrites", 0) + 1,
        "tokens": _add_usage(state, msg),
    }


def _append_history(state: RAGState, answer: str) -> list[dict]:
    max_turns = get_settings().history_max_turns
    history = list(state.get("history") or [])
    history.append({"question": _question_for_llm(state), "answer": answer})
    return history[-max_turns:]


def generate_node(state: RAGState) -> dict:
    started = time.perf_counter()
    llm = _llm(state)
    messages = [
        ("system", GENERATION_SYSTEM),
        (
            "human",
            GENERATION_USER.format(
                history=format_history(state.get("history")),
                context=format_context(state["documents"]),
                question=_question_for_llm(state),
            ),
        ),
    ]
    msg = llm.invoke(messages)
    answer = str(msg.content)
    _observe("generate", started)
    return {
        "generation": answer,
        "history": _append_history(state, answer),
        "tokens": _add_usage(state, msg),
    }


def generate_direct_node(state: RAGState) -> dict:
    """Small talk / meta questions: no retrieval, no citations (Phase 3 router)."""
    started = time.perf_counter()
    llm = _llm(state)
    history = format_history(state.get("history"))
    messages = [
        ("system", DIRECT_SYSTEM),
        ("human", f"{history}{_question_for_llm(state)}"),
    ]
    msg = llm.invoke(messages)
    answer = str(msg.content)
    _observe("generate_direct", started)
    return {
        "generation": answer,
        "documents": [],
        "history": _append_history(state, answer),
        "tokens": _add_usage(state, msg),
    }


# ── Graph ────────────────────────────────────────────────────────────────────


def build_graph():
    g = StateGraph(RAGState)
    g.add_node("analyze_query", analyze_query_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("grade_documents", grade_documents_node)
    g.add_node("rewrite_query", rewrite_query_node)
    g.add_node("generate", generate_node)
    g.add_node("generate_direct", generate_direct_node)

    g.add_edge(START, "analyze_query")
    g.add_conditional_edges(
        "analyze_query",
        route_after_analysis,
        {"retrieve": "retrieve", "direct": "generate_direct"},
    )
    g.add_edge("retrieve", "grade_documents")
    g.add_conditional_edges(
        "grade_documents",
        decide_after_grading,
        {"generate": "generate", "rewrite": "rewrite_query"},
    )
    g.add_edge("rewrite_query", "retrieve")
    g.add_edge("generate", END)
    g.add_edge("generate_direct", END)

    # MemorySaver = in-process memory (lost on restart, per-worker). Production
    # upgrade path: langgraph-checkpoint-postgres for durable, shared threads.
    return g.compile(checkpointer=MemorySaver())


agent = build_graph()


def run_agent(
    question: str,
    provider: str | None = None,
    model: str | None = None,
    top_k: int | None = None,
    source: str | None = None,
    conversation_id: str | None = None,
    grading: bool | None = None,
    max_rewrites: int | None = None,
) -> tuple[RAGState, str]:
    """Invoke the graph. Returns (final_state, conversation_id) — pass the same
    conversation_id back to continue the thread with memory."""
    thread_id = conversation_id or str(uuid.uuid4())
    initial: RAGState = {
        "question": question,
        "original_question": question,
        "provider": provider,
        "model": model,
        "top_k": top_k,
        "source": source,
        "grading": grading,
        "max_rewrites": max_rewrites,
        "rewrites": 0,
        "tokens": {"input": 0, "output": 0},
    }
    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(initial, config=config)
    return result, thread_id
