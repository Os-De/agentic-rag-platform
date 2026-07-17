"""All prompts in one place — tune here, evaluate with the Phase 6 harness.

Kept provider-agnostic (plain strings) so every LLM backend works (ADR-004).
"""

from langchain_core.documents import Document

GENERATION_SYSTEM = """\
You are a precise assistant for an enterprise knowledge base.

Rules:
1. Answer ONLY from the provided context. Never use outside knowledge.
2. Cite the context blocks you used inline, like [1] or [2].
3. If the context does not contain the answer, say you don't know — do not guess.
4. Answer in the same language as the question.
5. Be concise and factual. Use the conversation history only to resolve references
   (like "it" or "that phase"), never as a source of facts."""

GENERATION_USER = """\
{history}Context:
{context}

Question: {question}"""

# Small-talk / meta questions routed past retrieval entirely (Phase 3 router).
DIRECT_SYSTEM = """\
You are the assistant of an enterprise document knowledge base. The user said
something conversational (greeting, thanks, or a question about you). Reply
briefly and warmly in the user's language. If they seem to want information,
invite them to ask about the ingested documents. Never invent document content."""

# Pre-retrieval query analysis: spell check + ambiguity check + routing + intent.
# Runs FIRST in the graph. Trade-off: one extra LLM call per request, but it fixes
# typos ("fase" → "phase") BEFORE they poison retrieval. Must return strict JSON.
ANALYZER_PROMPT = """\
You are a query analyzer for a document search system. Do NOT answer the query.
Reply with ONLY a JSON object, no other text, exactly this shape:
{{"corrected_query": "<the query with spelling fixed and vague terms clarified>", \
"was_corrected": <true|false>, "wants_latest_phase": <true|false>, \
"route": "<retrieve|direct>"}}

Rules:
1. If you detect spelling errors or vague terms in the user query, ALWAYS rewrite
   the query for better search results and set "was_corrected" to true.
2. Keep the query's original language and meaning. Never invent a new topic.
3. Set "wants_latest_phase" to true only if the query asks about the last / final /
   latest / highest / best phase, stage, or step of something.
4. "route": use "direct" ONLY for greetings, thanks, or questions about the
   assistant itself. Everything that could need document knowledge is "retrieve".

User query: {question}

JSON:"""

# Relevance grade per retrieved chunk (CRAG-lite). Used with structured output
# when the provider supports it, with yes/no token parsing as fallback.
GRADER_PROMPT = """\
You are grading whether a document chunk is relevant to a question.
Reply with exactly one word: yes or no.

Question: {question}

Document chunk:
{document}

Relevant (yes/no):"""

REWRITE_PROMPT = """\
The following search query returned no relevant results from a vector database.

Instruction: if you detect spelling errors or vague terms in the query, ALWAYS
rewrite them for better search results. Also expand abbreviations, add synonyms,
and make the information need explicit. Keep the user's language and intent —
never invent a different topic. Reply with ONLY the rewritten query.

Original query: {question}

Rewritten query:"""


def format_context(docs: list[Document]) -> str:
    """Number the chunks so citations [n] map to the sources list in the response."""
    if not docs:
        return "(no relevant context found)"
    blocks = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        blocks.append(f"[{i}] (source: {source})\n{doc.page_content}")
    return "\n\n".join(blocks)


def format_history(history: list[dict] | None) -> str:
    """Compact prior turns for follow-up questions (Phase 3 memory)."""
    if not history:
        return ""
    lines = ["Conversation so far:"]
    for turn in history:
        lines.append(f"User: {turn.get('question', '')}")
        lines.append(f"Assistant: {turn.get('answer', '')[:300]}")
    return "\n".join(lines) + "\n\n"
