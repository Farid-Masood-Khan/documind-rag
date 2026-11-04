"""End-to-end API integration tests for DocuMind."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_test_pdf_bytes(text_lines: list[str]) -> bytes:
    """Builds valid PDF bytes containing extractable text streams."""
    # Build standard raw PDF with text stream
    stream_content = "\n".join(
        [f"BT /F1 12 Tf 50 {700 - i*20} Td ({line}) Tj ET" for i, line in enumerate(text_lines)]
    )
    stream_bytes = stream_content.encode("latin1")
    stream_len = len(stream_bytes)

    xref_entries = [
        "0000000000 65535 f",
        "0000000009 00000 n",
        "0000000058 00000 n",
        "0000000115 00000 n",
        "0000000244 00000 n",
        "0000000300 00000 n",
    ]
    xref_block = "\n".join(xref_entries)

    pdf_template = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {stream_len} >>
stream
{stream_content}
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
{xref_block}
trailer
<< /Size 6 /Root 1 0 R >>
startxref
370
%%EOF
"""
    return pdf_template.encode("latin1")


def test_end_to_end_rag_api(client: TestClient) -> None:
    headers = {"X-Client-Token": "test-e2e-client"}

    # 1. Create Session
    s_resp = client.post("/api/v1/sessions", json={"name": "End-to-End RAG Test"}, headers=headers)
    assert s_resp.status_code == 201
    session_id = s_resp.json()["id"]

    # 2. Ask before uploading any documents -> 400 empty_index
    ask_empty = client.post(
        f"/api/v1/sessions/{session_id}/ask",
        json={"question": "What is backpropagation?"},
        headers=headers,
    )
    assert ask_empty.status_code == 400
    assert "empty_index" in ask_empty.text

    # 3. Upload valid PDF document
    doc_lines = [
        "Convolutional neural networks extract hierarchical spatial representations from image matrices.",
        "Residual connections allow deep networks to train without vanishing gradients.",
        "Adam optimizer computes adaptive learning rates for each parameter.",
    ]
    pdf_bytes = make_test_pdf_bytes(doc_lines)

    files = [("files", ("deep_learning.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    upload_resp = client.post(
        f"/api/v1/sessions/{session_id}/documents",
        files=files,
        headers=headers,
    )
    assert upload_resp.status_code == 201
    results = upload_resp.json()["results"]
    assert len(results) == 1
    assert results[0]["status"] == "indexed"
    assert results[0]["chunk_count"] >= 1

    # 4. In-corpus question -> Answered with citations
    ask_valid = client.post(
        f"/api/v1/sessions/{session_id}/ask",
        json={"question": "What do convolutional neural networks extract?"},
        headers=headers,
    )
    assert ask_valid.status_code == 200
    valid_data = ask_valid.json()
    assert valid_data["refused"] is False
    assert valid_data["answer"] is not None
    assert len(valid_data["citations"]) >= 1
    assert valid_data["citations"][0]["filename"] == "deep_learning.pdf"

    # 5. Out-of-corpus question -> Refusal without hallucinations
    ask_refusal = client.post(
        f"/api/v1/sessions/{session_id}/ask",
        json={
            "question": "How do you prepare authentic Neapolitan pizza dough with high hydration?"
        },
        headers=headers,
    )
    assert ask_refusal.status_code == 200
    refusal_data = ask_refusal.json()
    assert refusal_data["refused"] is True
    assert refusal_data["answer"] is None
    assert refusal_data["citations"] == []
    assert refusal_data["reason"] == "no_evidence"

    # 6. Verify message history
    history_resp = client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert history_resp.status_code == 200
    history = history_resp.json()["messages"]
    assert len(history) == 4  # 2 user questions + 2 assistant answers
