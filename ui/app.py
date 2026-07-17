"""Minimal Streamlit chat client — demo front-end for the platform API.

Run in compose (--profile ui) or locally:  streamlit run ui/app.py
"""

import os

import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Agentic RAG Platform", page_icon="📚", layout="centered")
st.title("📚 Agentic RAG Platform")

# ── Auth ─────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Login")
    email = st.text_input("Email", value="admin@example.com")
    password = st.text_input("Password", type="password", value="")
    if st.button("Sign in", use_container_width=True):
        try:
            r = requests.post(
                f"{API}/api/v1/auth/token",
                data={"username": email, "password": password},
                timeout=30,
            )
            if r.ok:
                st.session_state.token = r.json()["access_token"]
                st.success("Signed in")
            else:
                st.error(r.json().get("detail", "Login failed"))
        except requests.RequestException as exc:
            st.error(f"API unreachable: {exc}")

    st.divider()
    provider = st.selectbox("LLM provider", ["default", "ollama", "openai", "anthropic"])
    top_k = st.slider("Top-k retrieval", 1, 10, 4)

if "token" not in st.session_state:
    st.info("Sign in from the sidebar (default admin credentials are in your .env).")
    st.stop()

# ── Chat ─────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None  # set from the first API response

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("Ask about your documents…"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    payload = {"question": question, "top_k": top_k}
    if provider != "default":
        payload["provider"] = provider
    if st.session_state.conversation_id:
        payload["conversation_id"] = st.session_state.conversation_id

    with st.chat_message("assistant"), st.spinner("Retrieving → grading → generating…"):
        try:
            r = requests.post(
                f"{API}/api/v1/chat",
                json=payload,
                headers={"Authorization": f"Bearer {st.session_state.token}"},
                timeout=300,
            )
            if r.ok:
                data = r.json()
                st.session_state.conversation_id = data.get("conversation_id")
                st.markdown(data["answer"])
                if data["sources"]:
                    with st.expander(f"Sources ({len(data['sources'])})"):
                        for src in data["sources"]:
                            score = f" · score {src['score']}" if src.get("score") else ""
                            badge = " · 🏷 phase-ranked" if src.get("retrieval") else ""
                            st.markdown(f"**[{src['index']}] {src['source']}**{score}{badge}")
                            st.caption(src["snippet"])
                analysis = data.get("analysis") or {}
                if analysis.get("was_corrected"):
                    st.caption(f"🔎 query corrected → “{analysis['corrected_query']}”")
                if data.get("rewrites"):
                    st.caption(f"🔄 rewrite flag: {data['rewrites']}")
                answer = data["answer"]
            else:
                answer = f"Error {r.status_code}: {r.json().get('detail', r.text)}"
                st.error(answer)
        except requests.RequestException as exc:
            answer = f"API unreachable: {exc}"
            st.error(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
