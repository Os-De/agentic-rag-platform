from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    provider: Literal["ollama", "openai", "anthropic"] | None = None  # default: env LLM_PROVIDER
    model: str | None = Field(default=None, max_length=100)  # e.g. "llama3.1:8b", "gpt-4o-mini"
    top_k: int | None = Field(default=None, ge=1, le=20)
    source: str | None = Field(default=None, max_length=512)  # restrict to one document
    conversation_id: str | None = Field(default=None, max_length=64)  # memory thread
    # Strategy knobs (eval program): vary agentic strategy per request, not just prompts
    grading: bool | None = None  # False = skip chunk grading (cheaper, maybe worse)
    max_rewrites: int | None = Field(default=None, ge=0, le=3)  # override rewrite budget


class UsageOut(BaseModel):
    """Token & cost accounting per request (eval program, Phase 1–2)."""

    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    model: str
    priced: bool  # False = model not in the pricing table (local models cost $0 API-side)


class QueryAnalysisOut(BaseModel):
    """What the analyze_query node decided — full transparency in every response."""

    original_question: str
    corrected_query: str
    was_corrected: bool = False
    wants_latest_phase: bool = False
    route: str = "retrieve"


class SourceChunk(BaseModel):
    index: int  # matches [n] citations in the answer
    source: str
    chunk_index: int | None = None
    phase_number: int | None = None
    score: float | None = None
    retrieval: str | None = None  # "phase_rank" when structural retrieval was used
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    rewrites: int  # includes analyzer corrections (flag=1) + retrieval-loop rewrites
    conversation_id: str  # send back to continue the conversation with memory
    analysis: QueryAnalysisOut | None = None
    usage: UsageOut | None = None
    sources: list[SourceChunk]
