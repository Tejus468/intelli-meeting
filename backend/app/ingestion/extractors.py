"""Text and metadata extraction for PDF, DOCX, and TXT/transcripts."""
import io
import re
from typing import List, Tuple, Optional
from datetime import datetime, timezone
import pymupdf
import docx

from app.ingestion.models import ExtractedSegment, ExtractionResult, SourceType


# Regex patterns for common transcript speaker & timestamp formats:
# 1) [00:12:34] Rahul: text or [00:12] Rahul: text
PATTERN_TS_SPEAKER = re.compile(
    r"^\s*\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:\n]+?)\s*:\s*(.*)$"
)
# 2) Rahul [00:12:34]: text or Rahul [00:12]: text
PATTERN_SPEAKER_TS = re.compile(
    r"^\s*([^\[\n:]+?)\s*\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*:\s*(.*)$"
)
# 3) 00:12:34 Rahul: text or 00:12 Rahul: text
PATTERN_BARE_TS_SPEAKER = re.compile(
    r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+([^:\n]+?)\s*:\s*(.*)$"
)
# 4) Speaker Name: text (Clean name prefix)
PATTERN_SPEAKER_ONLY = re.compile(
    r"^\s*([A-Za-z0-9_\-\.\s]{2,40})\s*:\s+(.*)$"
)
# 5) Google Meet style: a name-only line, then a bare timestamp line, then the spoken text
#      Alice
#      00:18
#      Right now the backend is running on a single virtual machine.
PATTERN_NAME_ONLY = re.compile(r"^[^\W\d_][\w .'\-]{0,39}$")
PATTERN_BARE_TIMESTAMP = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)$")

# Meeting metadata labels ("Meeting: ...", "Date: ...") that must never be read as a speaker name.
NON_SPEAKER_LABELS = (
    "http", "https", "note", "warning", "tip", "summary", "agenda",
    "meeting", "date", "title", "time", "attendees", "participants", "topic", "subject", "location",
)

# A file is treated as Google Meet style once this many name+timestamp pairs are seen, so a single
# stray "Name / 09:30" pair in an ordinary document does not turn it into a transcript.
MIN_NAME_TIMESTAMP_TURNS = 2


def extract_pdf(file_bytes: bytes, filename: str) -> ExtractionResult:
    """Extract text page by page from PDF preserving page provenance."""
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Failed to parse PDF document: {e}")

    segments: List[ExtractedSegment] = []
    char_offset = 0
    full_text_parts: List[str] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        page_text = page.get_text("text").strip()
        if not page_text:
            continue

        c_start = char_offset
        c_end = char_offset + len(page_text)
        segments.append(
            ExtractedSegment(
                text=page_text,
                speaker=None,
                start_ts=None,
                end_ts=None,
                page=page_num,
                char_start=c_start,
                char_end=c_end,
            )
        )
        full_text_parts.append(page_text)
        char_offset = c_end + 1  # Accounting for newline separator

    if not segments:
        raise ValueError("PDF document contains no extractable text.")

    raw_text = "\n".join(full_text_parts)
    title = filename.rsplit(".", 1)[0] if filename else "PDF Document"

    return ExtractionResult(
        title=title,
        source_type="pdf",
        segments=segments,
        raw_text=raw_text,
        source_date=datetime.now(timezone.utc),
    )


def extract_docx(file_bytes: bytes, filename: str) -> ExtractionResult:
    """Extract paragraphs in document order from DOCX."""
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f"Failed to parse DOCX document: {e}")

    segments: List[ExtractedSegment] = []
    char_offset = 0
    full_text_parts: List[str] = []

    for para in doc.paragraphs:
        p_text = para.text.strip()
        if not p_text:
            continue

        c_start = char_offset
        c_end = char_offset + len(p_text)
        segments.append(
            ExtractedSegment(
                text=p_text,
                speaker=None,
                start_ts=None,
                end_ts=None,
                page=None,
                char_start=c_start,
                char_end=c_end,
            )
        )
        full_text_parts.append(p_text)
        char_offset = c_end + 1

    if not segments:
        raise ValueError("DOCX document contains no extractable text.")

    raw_text = "\n".join(full_text_parts)
    title = filename.rsplit(".", 1)[0] if filename else "DOCX Document"

    return ExtractionResult(
        title=title,
        source_type="docx",
        segments=segments,
        raw_text=raw_text,
        source_date=datetime.now(timezone.utc),
    )


def _match_transcript_line(line: str) -> Optional[Tuple[Optional[str], Optional[str], str]]:
    """Check if line matches any known transcript header format."""
    m1 = PATTERN_TS_SPEAKER.match(line)
    if m1:
        return m1.group(2).strip(), m1.group(1).strip(), m1.group(3).strip()

    m2 = PATTERN_SPEAKER_TS.match(line)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip(), m2.group(3).strip()

    m3 = PATTERN_BARE_TS_SPEAKER.match(line)
    if m3:
        return m3.group(2).strip(), m3.group(1).strip(), m3.group(3).strip()

    m4 = PATTERN_SPEAKER_ONLY.match(line)
    if m4:
        candidate_speaker = m4.group(1).strip()
        # Avoid false positive matching for URL schemes like http: or notes like Note:
        if candidate_speaker.lower() not in NON_SPEAKER_LABELS:
            return candidate_speaker, None, m4.group(2).strip()

    return None


def _is_name_timestamp_pair(lines: List[str], index: int) -> bool:
    """True if lines[index] is a bare speaker name directly followed by a bare timestamp line."""
    return (
        index + 1 < len(lines)
        and bool(PATTERN_NAME_ONLY.match(lines[index]))
        and bool(PATTERN_BARE_TIMESTAMP.match(lines[index + 1]))
    )


def _parse_name_timestamp_turns(
    lines: List[str],
) -> Optional[List[Tuple[Optional[str], Optional[str], str]]]:
    """Parse the Google Meet layout (name / timestamp / text lines) into (speaker, timestamp, text) turns.

    Returns None when the layout is not present, so the other transcript formats are handled as before.
    Lines before the first speaker (title, meeting name, date...) become one header turn with no speaker.
    """
    stripped = [line.strip() for line in lines if line.strip()]
    pair_count = sum(1 for i in range(len(stripped)) if _is_name_timestamp_pair(stripped, i))
    if pair_count < MIN_NAME_TIMESTAMP_TURNS:
        return None

    turns: List[Tuple[Optional[str], Optional[str], str]] = []
    speaker: Optional[str] = None
    timestamp: Optional[str] = None
    text_lines: List[str] = []

    i = 0
    while i < len(stripped):
        if _is_name_timestamp_pair(stripped, i):
            if text_lines:
                turns.append((speaker, timestamp, "\n".join(text_lines)))
            speaker = stripped[i]
            timestamp = PATTERN_BARE_TIMESTAMP.match(stripped[i + 1]).group(1)
            text_lines = []
            i += 2
        else:
            text_lines.append(stripped[i])
            i += 1

    if text_lines:
        turns.append((speaker, timestamp, "\n".join(text_lines)))
    return turns


def extract_txt(file_bytes: bytes, filename: str) -> ExtractionResult:
    """Extract text from plain text or transcript file."""
    try:
        raw_content = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw_content = file_bytes.decode("latin-1", errors="replace")

    raw_content = raw_content.strip()
    if not raw_content:
        raise ValueError("Text file is empty.")

    lines = raw_content.splitlines()

    # Determine if text represents a transcript with identifiable speaker turns
    detected_turns: List[Tuple[Optional[str], Optional[str], str]] = []
    has_transcript_format = False

    current_speaker: Optional[str] = None
    current_ts: Optional[str] = None
    current_text_lines: List[str] = []

    meet_turns = _parse_name_timestamp_turns(lines)
    if meet_turns is not None:
        detected_turns = meet_turns
        has_transcript_format = True
        lines = []  # the "Name: text" line scanner below does not apply to this layout

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        match = _match_transcript_line(stripped)
        if match:
            has_transcript_format = True
            # Save preceding turn
            if current_text_lines:
                detected_turns.append(
                    (current_speaker, current_ts, "\n".join(current_text_lines))
                )
            current_speaker, current_ts, turn_text = match
            current_text_lines = [turn_text] if turn_text else []
        else:
            if current_text_lines:
                current_text_lines.append(stripped)
            else:
                # Leading line before any speaker match
                current_text_lines.append(stripped)

    if current_text_lines:
        detected_turns.append(
            (current_speaker, current_ts, "\n".join(current_text_lines))
        )

    segments: List[ExtractedSegment] = []
    char_offset = 0
    full_text_parts: List[str] = []

    if has_transcript_format and detected_turns:
        source_type: SourceType = "transcript"
        for speaker, start_ts, turn_text in detected_turns:
            if not turn_text:
                continue
            c_start = char_offset
            c_end = char_offset + len(turn_text)
            segments.append(
                ExtractedSegment(
                    text=turn_text,
                    speaker=speaker,
                    start_ts=start_ts,
                    end_ts=None,
                    page=None,
                    char_start=c_start,
                    char_end=c_end,
                )
            )
            full_text_parts.append(turn_text)
            char_offset = c_end + 1
    else:
        # Standard plain text paragraphs
        source_type = "txt"
        paragraphs = [p.strip() for p in raw_content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [raw_content]

        for p_text in paragraphs:
            c_start = char_offset
            c_end = char_offset + len(p_text)
            segments.append(
                ExtractedSegment(
                    text=p_text,
                    speaker=None,
                    start_ts=None,
                    end_ts=None,
                    page=None,
                    char_start=c_start,
                    char_end=c_end,
                )
            )
            full_text_parts.append(p_text)
            char_offset = c_end + 1

    title = filename.rsplit(".", 1)[0] if filename else "Text Document"

    return ExtractionResult(
        title=title,
        source_type=source_type,
        segments=segments,
        raw_text="\n".join(full_text_parts),
        source_date=datetime.now(timezone.utc),
    )


def extract_document(file_bytes: bytes, filename: str) -> ExtractionResult:
    """Extract document content based on file extension."""
    lower_name = filename.lower().strip()
    if lower_name.endswith(".pdf"):
        return extract_pdf(file_bytes, filename)
    elif lower_name.endswith(".docx"):
        return extract_docx(file_bytes, filename)
    elif lower_name.endswith(".txt"):
        return extract_txt(file_bytes, filename)
    else:
        raise ValueError(
            f"Unsupported file format for '{filename}'. Supported formats: .txt, .pdf, .docx"
        )
