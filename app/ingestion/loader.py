"""PDF document loader with pdfplumber and pypdf fallback."""

from __future__ import annotations

import hashlib
import io
from typing import NamedTuple

import pdfplumber
import pypdf

from app.config import settings


class ExtractedPage(NamedTuple):
    page_number: int  # 1-based
    text: str


class PDFLoadResult(NamedTuple):
    file_sha256: str
    size_bytes: int
    page_count: int
    pages: list[ExtractedPage]


class PDFLoaderError(Exception):
    """Base exception for PDF loading failures."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UnsupportedFileTypeError(PDFLoaderError):
    def __init__(self, message: str = "Only PDF documents are supported.") -> None:
        super().__init__("unsupported_file_type", message)


class FileTooLargeError(PDFLoaderError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(
            "file_too_large",
            f"File size {size_bytes / (1024*1024):.1f}MB exceeds limit of {max_bytes / (1024*1024):.1f}MB.",
        )


class PageLimitExceededError(PDFLoaderError):
    def __init__(self, page_count: int, max_pages: int) -> None:
        super().__init__(
            "page_limit_exceeded",
            f"Document has {page_count} pages, which exceeds the {max_pages} page ceiling.",
        )


class CorruptPDFError(PDFLoaderError):
    def __init__(self, details: str = "") -> None:
        super().__init__(
            "corrupt_pdf", f"Unable to read PDF file. File may be corrupted or encrypted: {details}"
        )


class NoExtractableTextError(PDFLoaderError):
    def __init__(self) -> None:
        super().__init__(
            "no_extractable_text",
            "No extractable text found in PDF — likely a scanned image without OCR text layer.",
        )


def load_pdf_bytes(file_bytes: bytes, filename: str) -> PDFLoadResult:
    """Parses raw PDF bytes into extracted pages with strict validation."""
    size_bytes = len(file_bytes)

    # 1. Size ceiling check
    if size_bytes > settings.max_file_size_bytes:
        raise FileTooLargeError(size_bytes, settings.max_file_size_bytes)

    # 2. Magic bytes validation (%PDF-)
    if not file_bytes.startswith(b"%PDF-"):
        raise UnsupportedFileTypeError(f"File '{filename}' does not contain valid PDF magic bytes.")

    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    pages: list[ExtractedPage] = []

    # 3. Primary extraction via pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_count = len(pdf.pages)
            if page_count > settings.max_pages_per_doc:
                raise PageLimitExceededError(page_count, settings.max_pages_per_doc)

            for i, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                pages.append(ExtractedPage(page_number=i, text=page_text.strip()))
    except (PageLimitExceededError, UnsupportedFileTypeError):
        raise
    except Exception as exc:
        # Fallback extraction via pypdf
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            page_count = len(reader.pages)
            if page_count > settings.max_pages_per_doc:
                raise PageLimitExceededError(page_count, settings.max_pages_per_doc)

            pages = []
            for i, pypdf_page in enumerate(reader.pages, start=1):
                page_text = pypdf_page.extract_text() or ""
                pages.append(ExtractedPage(page_number=i, text=page_text.strip()))
        except Exception as inner_exc:
            raise CorruptPDFError(f"{exc} / {inner_exc}") from exc

    # 4. Check for extractable text across all pages
    total_text_length = sum(len(p.text) for p in pages)
    if total_text_length < 20:  # Threshold for scanned/blank PDFs
        raise NoExtractableTextError()

    return PDFLoadResult(
        file_sha256=file_sha256,
        size_bytes=size_bytes,
        page_count=len(pages),
        pages=pages,
    )
