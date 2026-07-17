# RAG Frequently Asked Questions (sample document)

## What is chunk overlap and why does it matter?

Overlap repeats the tail of one chunk at the head of the next so that sentences
spanning a boundary remain retrievable as a unit. Too little overlap cuts ideas in
half; too much wastes storage and blurs retrieval scores. This platform defaults to
800-character chunks with 120 characters of overlap, tunable via environment variables.

## Why grade retrieved documents?

Vector similarity is not relevance. A chunk can be close in embedding space yet
useless for the question. Grading each retrieved chunk with a small LLM call filters
noise before generation, which reduces hallucinations. The trade-off is extra latency
and cost per chunk graded.

## When should a query be rewritten?

If grading discards every retrieved chunk, the query likely used vocabulary that does
not match the corpus. Rewriting expands abbreviations and adds synonyms, then retries
retrieval once. If the rewrite also fails, the agent answers honestly that it does
not know.

## Why do embeddings define the vector space?

Every embedding model maps text into its own coordinate system with a fixed dimension.
Vectors from different models are not comparable, so switching embedding models
requires re-ingesting all documents into a fresh collection.
