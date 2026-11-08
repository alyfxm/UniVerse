"""PDF extraction, text normalization, and page-aware semantic chunker."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import re

import pymupdf as fitz

from app.core.exceptions import AppError
from app.models.documents import (
    DocumentCategory,
    DocumentChunk,
    DocumentLanguage,
    HighlightRect,
    PagePreviewResponse,
)

PDF_MAGIC_BYTES = b"%PDF-"


@dataclass(frozen=True)
class ExtractedPage:
    """Represents cleaned text extracted from a single 1-indexed PDF page."""

    page_number: int
    text: str


class PdfProcessorService:
    """Validates PDF files, extracts page-level text, and builds page-cited chunks."""

    def __init__(
        self,
        chunk_size_chars: int = 1200,
        chunk_overlap_chars: int = 200,
    ) -> None:
        if chunk_overlap_chars >= chunk_size_chars:
            raise ValueError("chunk_overlap_chars must be smaller than chunk_size_chars")
        self.chunk_size_chars = chunk_size_chars
        self.chunk_overlap_chars = chunk_overlap_chars

    @staticmethod
    def compute_sha256(file_bytes: bytes) -> str:
        """Compute deterministic SHA-256 hex hash for PDF deduplication."""
        return hashlib.sha256(file_bytes).hexdigest()

    @staticmethod
    def validate_pdf_bytes(file_bytes: bytes, max_size_bytes: int) -> None:
        """Validate PDF non-empty, size limit, and %PDF- magic header."""
        if not file_bytes:
            raise AppError(
                code="DOCUMENT_EMPTY",
                message="Uploaded PDF file is empty.",
            )
        if len(file_bytes) > max_size_bytes:
            raise AppError(
                code="DOCUMENT_TOO_LARGE",
                message=f"PDF file exceeds maximum size limit of {max_size_bytes // (1024 * 1024)} MB.",
                details={"file_size_bytes": len(file_bytes), "max_size_bytes": max_size_bytes},
            )
        if not file_bytes.lstrip().startswith(PDF_MAGIC_BYTES):
            raise AppError(
                code="DOCUMENT_INVALID_FORMAT",
                message="Uploaded file is not a valid PDF document.",
            )

    @staticmethod
    def normalize_page_text(raw_text: str) -> str:
        """Clean control characters, normalize hyphenation and whitespace."""
        cleaned = raw_text.replace("\x00", "")
        cleaned = re.sub(r"\r\n?", "\n", cleaned)
        # Collapse 3+ consecutive newlines into double newline (paragraph break)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        # Collapse horizontal whitespace runs into a single space
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    def extract_pages(self, file_bytes: bytes) -> tuple[int, list[ExtractedPage]]:
        """Extract normalized text per page (1-indexed) from PDF bytes."""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise AppError(
                code="DOCUMENT_CORRUPTED",
                message="Unable to parse PDF file structure.",
            ) from exc

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            raise AppError(
                code="DOCUMENT_EMPTY_PAGES",
                message="The uploaded PDF contains zero pages.",
            )

        extracted_pages: list[ExtractedPage] = []
        for idx in range(total_pages):
            page = doc.load_page(idx)
            raw_text = page.get_text("text") or ""
            table_markdown = self._extract_tables_as_markdown(page)
            combined_text = (
                f"{raw_text}\n\n{table_markdown}".strip()
                if table_markdown
                else raw_text
            )
            normalized = self.normalize_page_text(combined_text)
            if normalized:
                extracted_pages.append(
                    ExtractedPage(page_number=idx + 1, text=normalized)
                )

        doc.close()

        if not extracted_pages:
            raise AppError(
                code="DOCUMENT_NO_EXTRACTABLE_TEXT",
                message="No extractable text found in PDF. Scanned image-only PDFs require OCR.",
            )

        return total_pages, extracted_pages

    def chunk_pages(
        self,
        document_id: str,
        document_title: str,
        category: DocumentCategory,
        language: DocumentLanguage,
        pages: list[ExtractedPage],
        is_active: bool = True,
    ) -> list[DocumentChunk]:
        """Split extracted pages into overlapping semantic chunks with exact page numbers."""
        chunks: list[DocumentChunk] = []

        for page in pages:
            text = page.text
            text_len = len(text)
            start = 0
            chunk_idx = 0

            while start < text_len:
                end = min(start + self.chunk_size_chars, text_len)

                # Prefer breaking at a paragraph, sentence, or space boundary if not at end
                if end < text_len:
                    boundary = self._find_natural_boundary(text, start, end)
                    if boundary > start + (self.chunk_size_chars // 3):
                        end = boundary

                snippet = text[start:end].strip()
                if snippet:
                    chunk_id = f"{document_id}_p{page.page_number}_c{chunk_idx}"
                    contextual_text = (
                        f"[Document: {document_title} | Category: {category} | Page: {page.page_number}]\n"
                        f"{snippet}"
                    )
                    chunks.append(
                        DocumentChunk(
                            chunk_id=chunk_id,
                            document_id=document_id,
                            document_title=document_title,
                            category=category,
                            language=language,
                            page_number=page.page_number,
                            chunk_index=chunk_idx,
                            text=snippet,
                            contextual_text=contextual_text,
                            char_start=start,
                            char_end=end,
                            is_active=is_active,
                        )
                    )
                    chunk_idx += 1

                if end >= text_len:
                    break
                start = max(end - self.chunk_overlap_chars, start + 1)

        return chunks

    @staticmethod
    def _extract_tables_as_markdown(page: fitz.Page) -> str:
        """Detect structured tables on a PDF page and convert them to Markdown tables."""
        try:
            finder = page.find_tables()
            tables = getattr(finder, "tables", None) or []
            md_tables: list[str] = []
            for table in tables:
                rows = table.extract()
                if not rows or len(rows) < 2:
                    continue
                cleaned_rows = [
                    [str(cell or "").replace("\n", " ").strip() for cell in row]
                    for row in rows
                ]
                header = cleaned_rows[0]
                if not any(header):
                    continue
                sep = ["---" for _ in header]
                lines = [
                    "| " + " | ".join(header) + " |",
                    "| " + " | ".join(sep) + " |",
                ]
                for data_row in cleaned_rows[1:]:
                    if any(data_row):
                        lines.append("| " + " | ".join(data_row) + " |")
                if len(lines) > 2:
                    md_tables.append("\n".join(lines))
            return "\n\n".join(md_tables)
        except Exception:
            return ""

    @staticmethod
    def render_page_with_highlight(
        file_bytes: bytes,
        document_id: str,
        document_title: str,
        page_number: int,
        highlight_snippet: str | None = None,
    ) -> PagePreviewResponse:
        """Render a 1-indexed PDF page to PNG with translucent yellow bounding-box highlight over the cited snippet."""
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as exc:
            raise AppError(
                code="DOCUMENT_CORRUPTED",
                message="Unable to open PDF for page preview.",
            ) from exc

        total_pages = len(doc)
        if page_number < 1 or page_number > total_pages:
            doc.close()
            raise AppError(
                code="PAGE_OUT_OF_RANGE",
                message=f"Requested page {page_number} is out of bounds (1..{total_pages}).",
            )

        page = doc.load_page(page_number - 1)
        page_text = (page.get_text("text") or "").strip()
        rect_width = max(1.0, float(page.rect.width))
        rect_height = max(1.0, float(page.rect.height))

        highlight_boxes: list[HighlightRect] = []
        if highlight_snippet and highlight_snippet.strip():
            # Search for progressively shorter phrases from the snippet to locate exact quads on the page
            clean_snip = re.sub(r"\s+", " ", highlight_snippet.strip())
            candidates = [
                clean_snip[:90],
                clean_snip[:55],
                " ".join(clean_snip.split()[:6]),
            ]
            matched_rects = []
            for phrase in candidates:
                if len(phrase) >= 4:
                    matched_rects = page.search_for(phrase)
                    if matched_rects:
                        break

            for r in matched_rects:
                annot = page.add_highlight_annot(r)
                annot.set_colors(stroke=(1.0, 0.92, 0.23))
                annot.update()
                highlight_boxes.append(
                    HighlightRect(
                        x0=round(float(r.x0) / rect_width, 4),
                        y0=round(float(r.y0) / rect_height, 4),
                        x1=round(float(r.x1) / rect_width, 4),
                        y1=round(float(r.y1) / rect_height, 4),
                    )
                )

        pix = page.get_pixmap(dpi=130)
        png_bytes = pix.tobytes("png")
        doc.close()

        b64_png = base64.b64encode(png_bytes).decode("ascii")
        return PagePreviewResponse(
            document_id=document_id,
            document_title=document_title,
            page_number=page_number,
            total_pages=total_pages,
            page_text=page_text,
            image_data_url=f"data:image/png;base64,{b64_png}",
            highlight_boxes=highlight_boxes,
        )

    @staticmethod
    def _find_natural_boundary(text: str, start: int, tentative_end: int) -> int:
        """Find nearest paragraph, sentence, or word boundary before tentative_end."""
        window = text[start:tentative_end]
        for sep in ("\n\n", ". ", "\n", " "):
            pos = window.rfind(sep)
            if pos != -1 and pos > len(window) // 2:
                return start + pos + len(sep)
        return tentative_end
