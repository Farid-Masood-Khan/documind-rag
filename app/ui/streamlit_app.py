"""DocuMind Streamlit User Interface.

Two-region layout with session workspace, drag-and-drop document upload,
citation chips, source expanders, and explicit refusal cards.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="DocuMind — Grounded Document Q&A",
    page_icon="📖",
    layout="wide",
)

# Initialize persistent client token in session_state for multi-client isolation
if "client_token" not in st.session_state:
    st.session_state["client_token"] = str(uuid.uuid4())

HEADERS = {"X-Client-Token": st.session_state["client_token"]}

# ==============================================================================
# SIDEBAR: Sessions, Documents & Backend Status
# ==============================================================================
with st.sidebar:
    st.header("📖 DocuMind")
    st.caption("Verifiable, grounded PDF research assistant")

    # Backend Status Indicator
    try:
        h_resp = requests.get(f"{API_BASE_URL}/api/v1/health", timeout=2)
        if h_resp.status_code == 200:
            h_data = h_resp.json()
            st.success(f"🟢 Backend Online | Model: `{h_data['embed_model']}`")
        else:
            st.error("🔴 Backend Unhealthy")
    except Exception:
        st.warning(f"🟡 Backend Offline ({API_BASE_URL}). Run `.\\run.ps1 serve`.")

    st.divider()

    # Session Management
    st.subheader("Workspaces")
    sessions: list[dict[str, Any]] = []
    try:
        s_resp = requests.get(f"{API_BASE_URL}/api/v1/sessions", headers=HEADERS, timeout=3)
        if s_resp.status_code == 200:
            sessions = s_resp.json().get("sessions", [])
    except Exception:
        pass

    session_names = {s["id"]: s["name"] for s in sessions}

    # Session Selector
    if sessions:
        selected_session_id = st.selectbox(
            "Active Session",
            options=list(session_names.keys()),
            format_func=lambda x: session_names.get(x, x),
            key="current_session_id",
        )
    else:
        selected_session_id = None
        st.info("No active session. Create one below.")

    # Create New Session
    with st.expander("➕ Create New Session"):
        new_name = st.text_input("Session Name", value="Research Session")
        if st.button("Create Session"):
            try:
                c_resp = requests.post(
                    f"{API_BASE_URL}/api/v1/sessions",
                    json={"name": new_name},
                    headers=HEADERS,
                )
                if c_resp.status_code == 201:
                    st.rerun()
            except Exception as e:
                st.error(f"Error creating session: {e}")

    st.divider()

    # Document Upload to Active Session
    if selected_session_id:
        st.subheader("Documents")
        uploaded_files = st.file_uploader(
            "Upload PDFs (Max 25MB each)",
            type=["pdf"],
            accept_multiple_files=True,
        )

        if uploaded_files and st.button("Process & Index Documents", type="primary"):
            files_payload = [
                ("files", (f.name, f.getvalue(), "application/pdf")) for f in uploaded_files
            ]
            with st.spinner("Extracting text, chunking, and embedding with FAISS..."):
                try:
                    up_resp = requests.post(
                        f"{API_BASE_URL}/api/v1/sessions/{selected_session_id}/documents",
                        files=files_payload,
                        headers=HEADERS,
                        timeout=60,
                    )
                    if up_resp.status_code == 201:
                        st.success("Indexing complete!")
                        st.rerun()
                    else:
                        st.error(f"Upload error: {up_resp.text}")
                except Exception as exc:
                    st.error(f"Upload connection error: {exc}")

        # List Existing Documents in Active Session
        try:
            d_resp = requests.get(
                f"{API_BASE_URL}/api/v1/sessions/{selected_session_id}/documents",
                headers=HEADERS,
                timeout=3,
            )
            if d_resp.status_code == 200:
                docs = d_resp.json().get("documents", [])
                if docs:
                    st.markdown("**Indexed Files:**")
                    for d in docs:
                        st.markdown(
                            f"📄 `{d['original_filename']}`\n"
                            f"- {d['page_count']} pages · {d['chunk_count']} chunks"
                        )
                else:
                    st.caption("No documents in this session yet.")
        except Exception:
            pass

# ==============================================================================
# MAIN CHAT REGION
# ==============================================================================
st.title("📚 DocuMind Document Q&A")

if not selected_session_id:
    st.info("👈 Please create or select a session from the sidebar to begin.")
else:
    st.caption(f"Active Session: **{session_names.get(selected_session_id, selected_session_id)}**")

    # Load Message History
    messages: list[dict[str, Any]] = []
    try:
        m_resp = requests.get(
            f"{API_BASE_URL}/api/v1/sessions/{selected_session_id}/messages",
            headers=HEADERS,
            timeout=3,
        )
        if m_resp.status_code == 200:
            messages = m_resp.json().get("messages", [])
    except Exception:
        pass

    # Render Transcript
    for msg in messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                if msg["refused"]:
                    st.warning("⚠️ **Evidence Not Found in Uploaded Documents**")
                    st.write(
                        "The uploaded documents do not contain evidence to answer this question. "
                        "Try rephrasing or uploading documents that cover this topic."
                    )
                else:
                    st.markdown(msg["content"])
                    citations = msg.get("citations", [])
                    if citations:
                        with st.expander(f"🔍 Cited Sources ({len(citations)})"):
                            for cit in citations:
                                st.markdown(
                                    f"**[{cit['source_tag']}] {cit['filename']} (Page {cit['page_number']})** — *Similarity: {cit['similarity']:.2f}*"
                                )
                                st.info(f"\"{cit['snippet']}\"")

    # Question Input Box
    query = st.chat_input("Ask a question about your uploaded documents...")
    if query:
        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("Searching document index and synthesizing answer..."):
                try:
                    resp = requests.post(
                        f"{API_BASE_URL}/api/v1/sessions/{selected_session_id}/ask",
                        json={"question": query, "top_k": 5},
                        headers=HEADERS,
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        ans_data = resp.json()
                        st.rerun()
                    elif resp.status_code == 400 and "empty_index" in resp.text:
                        st.error(
                            "Please upload and index at least one PDF before asking questions."
                        )
                    else:
                        st.error(f"API Error ({resp.status_code}): {resp.text}")
                except Exception as exc:
                    st.error(f"Failed to communicate with API: {exc}")
