from __future__ import annotations

import re
from dataclasses import dataclass

# -----------------------------
# Regex patterns (strong + safe)
# -----------------------------

# StandSpecs signals:
#   "SECTION 701 – GENERAL ITEMS"
SECTION_RE = re.compile(r"(?mi)^\s*SECTION\s+(\d{3})\b")

# Strong subsection header like:
#   "701.03.02  Rigid Metallic Conduit (Earth)"
#   "701.01  DESCRIPTION"
#
# Requirements:
# - start-of-line
# - subsection id
# - 2+ spaces
# - heading-like text starting with a capital letter
#
# This avoids cross references like:
#   "... as specified in 701.03.01 ..."
SUBSECTION_HEADER_RE = re.compile(
    r"(?m)^\s*(\d{3}\.\d{2}(?:\.\d{2})?)\s{2,}([A-Z][^\n]{2,})\s*$"
)


@dataclass
class Chunk:
    section_id: str | None
    heading: str | None
    page_start: int
    page_end: int
    text: str


@dataclass
class PageSegment:
    section_id: str | None
    heading: str | None
    text: str


def _section_heading_line(text: str, marker: str) -> str | None:
    """
    For SECTION headings only (e.g., "SECTION 701 – GENERAL ITEMS"),
    return the matching line if present.
    """
    if not text:
        return None
    for ln in text.splitlines():
        if re.search(rf"(?i)\bSECTION\s+{re.escape(marker)}\b", ln):
            return ln.strip()[:200]
    return f"SECTION {marker}"[:200]


def split_page_into_segments(text: str) -> list[PageSegment]:
    """
    Split a page into segments. Priority:
    1) Strong subsection headers (701.03.02  Title)
    2) SECTION headers (SECTION 701 – ...)
    3) Otherwise, one segment with no section_id
    """
    if not text:
        return [PageSegment(None, None, "")]

    preamble_min_chars = 40

    # -----------------------------
    # 1) Strong subsection headers
    # -----------------------------
    sub_matches = list(SUBSECTION_HEADER_RE.finditer(text))
    if sub_matches:
        segments: list[PageSegment] = []
        starts = [m.start() for m in sub_matches]
        preamble = text[:starts[0]].strip()

        for idx, m in enumerate(sub_matches):
            start = starts[idx]
            end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
            seg_text = text[start:end].strip()

            # Keep preamble only if it's meaningful and attaches to first segment
            if idx == 0 and len(preamble) >= preamble_min_chars:
                seg_text = f"{preamble}\n{seg_text}"

            sec_id = m.group(1)
            # Use the exact header line as heading; it’s stable and avoids false matches
            header_line = m.group(0).strip()
            heading = header_line[:200]

            segments.append(PageSegment(sec_id, heading, seg_text))

        return segments

    # -----------------------------
    # 2) SECTION headers (fallback)
    # -----------------------------
    sec_matches = list(SECTION_RE.finditer(text))
    if sec_matches:
        segments: list[PageSegment] = []
        starts = [m.start() for m in sec_matches]
        preamble = text[:starts[0]].strip()

        for idx, m in enumerate(sec_matches):
            start = starts[idx]
            end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
            seg_text = text[start:end].strip()

            if idx == 0 and len(preamble) >= preamble_min_chars:
                seg_text = f"{preamble}\n{seg_text}"

            sec_id = m.group(1)  # "701"
            heading = _section_heading_line(seg_text, sec_id)

            segments.append(PageSegment(sec_id, heading, seg_text))

        return segments

    # -----------------------------
    # 3) No detectable markers
    # -----------------------------
    return [PageSegment(None, None, text.strip())]


def chunk_document_pages(pages: list[tuple[int, str]]) -> list[Chunk]:
    """
    Input: list of (page_number, page_text) sorted.
    Output: chunks split when we detect a new SECTION or subsection header.
    """
    chunks: list[Chunk] = []

    cur_section: str | None = None
    cur_heading: str | None = None
    cur_start: int | None = None
    cur_buf: list[str] = []
    cur_end: int | None = None

    def flush():
        nonlocal cur_section, cur_heading, cur_start, cur_end, cur_buf
        if cur_start is None or cur_end is None or not cur_buf:
            return
        text = "\n".join(cur_buf).strip()
        if text:
            chunks.append(Chunk(cur_section, cur_heading, cur_start, cur_end, text))
        cur_section, cur_heading, cur_start, cur_end, cur_buf = None, None, None, None, []

    for page_no, text in pages:
        segments = split_page_into_segments(text)

        for seg in segments:
            is_new_marker = seg.section_id is not None and seg.section_id != cur_section

            if cur_start is None:
                cur_start = page_no
                cur_section = seg.section_id
                cur_heading = seg.heading

            elif is_new_marker:
                # IMPORTANT: flush BEFORE switching section_id/heading
                flush()
                cur_start = page_no
                cur_section = seg.section_id
                cur_heading = seg.heading

            elif cur_section is None and seg.section_id is not None:
                cur_section = seg.section_id
                cur_heading = seg.heading

            cur_end = page_no
            cur_buf.append(seg.text or "")

    flush()
    return chunks
