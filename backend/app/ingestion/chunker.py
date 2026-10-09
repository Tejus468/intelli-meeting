"""Chunking strategies for transcripts and general documents."""
import re
import uuid
from typing import List, Optional
from app.ingestion.models import ExtractedSegment, ExtractionResult, ChunkRecord

DEFAULT_TARGET_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 80


def estimate_tokens(text: str) -> int:
    """Lightweight deterministic token estimation based on whitespace words."""
    if not text:
        return 0
    words = text.split()
    return max(1, int(len(words) * 1.25))


def _split_into_sentences(text: str) -> List[str]:
    """Split text into sentences cleanly without cutting in the middle."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _format_segment_text(seg: ExtractedSegment) -> str:
    """Format segment with speaker/timestamp prefix if available."""
    prefix_parts = []
    if seg.start_ts:
        prefix_parts.append(f"[{seg.start_ts}]")
    if seg.speaker:
        prefix_parts.append(f"{seg.speaker}:")

    if prefix_parts:
        return f"{' '.join(prefix_parts)} {seg.text}"
    return seg.text


def chunk_transcript(
    segments: List[ExtractedSegment],
    source_id: str,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[ChunkRecord]:
    """Speaker/turn-aware chunking for transcripts.

    Rule: Never split an individual speaker turn across chunks.
    If a turn is longer than target_tokens, keep that turn intact.
    """
    if not segments:
        return []

    chunks: List[ChunkRecord] = []
    current_turn_batch: List[ExtractedSegment] = []
    current_tokens = 0

    idx = 0
    while idx < len(segments):
        seg = segments[idx]
        seg_tokens = estimate_tokens(seg.text)

        # If a single turn is >= target_tokens and we already have accumulated turns,
        # flush the accumulated turns first
        if current_turn_batch and (current_tokens + seg_tokens > target_tokens):
            # Create chunk from current batch
            chunk_text = "\n\n".join(_format_segment_text(s) for s in current_turn_batch)
            speaker = (
                current_turn_batch[0].speaker
                if all(s.speaker == current_turn_batch[0].speaker for s in current_turn_batch)
                else None
            )
            chunks.append(
                ChunkRecord(
                    chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
                    source_id=source_id,
                    text=chunk_text,
                    speaker=speaker,
                    start_ts=current_turn_batch[0].start_ts,
                    end_ts=current_turn_batch[-1].start_ts or current_turn_batch[-1].end_ts,
                    page=current_turn_batch[0].page,
                    char_start=current_turn_batch[0].char_start,
                    char_end=current_turn_batch[-1].char_end,
                )
            )

            # Calculate overlap turns
            overlap_batch: List[ExtractedSegment] = []
            overlap_tok_count = 0
            for prev_s in reversed(current_turn_batch):
                p_tok = estimate_tokens(prev_s.text)
                if overlap_tok_count + p_tok <= overlap_tokens:
                    overlap_batch.insert(0, prev_s)
                    overlap_tok_count += p_tok
                else:
                    break

            current_turn_batch = overlap_batch
            current_tokens = overlap_tok_count

        current_turn_batch.append(seg)
        current_tokens += seg_tokens
        idx += 1

    if current_turn_batch:
        chunk_text = "\n\n".join(_format_segment_text(s) for s in current_turn_batch)
        speaker = (
            current_turn_batch[0].speaker
            if all(s.speaker == current_turn_batch[0].speaker for s in current_turn_batch)
            else None
        )
        chunks.append(
            ChunkRecord(
                chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
                source_id=source_id,
                text=chunk_text,
                speaker=speaker,
                start_ts=current_turn_batch[0].start_ts,
                end_ts=current_turn_batch[-1].start_ts or current_turn_batch[-1].end_ts,
                page=current_turn_batch[0].page,
                char_start=current_turn_batch[0].char_start,
                char_end=current_turn_batch[-1].char_end,
            )
        )

    return chunks


def chunk_document(
    segments: List[ExtractedSegment],
    source_id: str,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[ChunkRecord]:
    """Paragraph/sentence-aware chunking for standard documents (PDF, DOCX, TXT)."""
    if not segments:
        return []

    # Flatten segments into sentence units while keeping page & character offsets
    sentence_units = []
    for seg in segments:
        sentences = _split_into_sentences(seg.text)
        if not sentences:
            sentences = [seg.text]

        # Distribute char offset estimates across sentences
        offset = seg.char_start
        for s in sentences:
            s_len = len(s)
            sentence_units.append(
                {
                    "text": s,
                    "tokens": estimate_tokens(s),
                    "page": seg.page,
                    "char_start": offset,
                    "char_end": offset + s_len,
                }
            )
            offset += s_len + 1

    chunks: List[ChunkRecord] = []
    current_sentences = []
    current_tokens = 0

    idx = 0
    while idx < len(sentence_units):
        unit = sentence_units[idx]

        if current_sentences and (current_tokens + unit["tokens"] > target_tokens):
            chunk_text = " ".join(u["text"] for u in current_sentences)
            pages = [u["page"] for u in current_sentences if u["page"] is not None]
            page_val = pages[0] if pages else None

            chunks.append(
                ChunkRecord(
                    chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
                    source_id=source_id,
                    text=chunk_text,
                    speaker=None,
                    start_ts=None,
                    end_ts=None,
                    page=page_val,
                    char_start=current_sentences[0]["char_start"],
                    char_end=current_sentences[-1]["char_end"],
                )
            )

            # Calculate overlap sentences
            overlap_units = []
            overlap_tok_count = 0
            for prev_u in reversed(current_sentences):
                if overlap_tok_count + prev_u["tokens"] <= overlap_tokens:
                    overlap_units.insert(0, prev_u)
                    overlap_tok_count += prev_u["tokens"]
                else:
                    break

            current_sentences = overlap_units
            current_tokens = overlap_tok_count

        current_sentences.append(unit)
        current_tokens += unit["tokens"]
        idx += 1

    if current_sentences:
        chunk_text = " ".join(u["text"] for u in current_sentences)
        pages = [u["page"] for u in current_sentences if u["page"] is not None]
        page_val = pages[0] if pages else None

        chunks.append(
            ChunkRecord(
                chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
                source_id=source_id,
                text=chunk_text,
                speaker=None,
                start_ts=None,
                end_ts=None,
                page=page_val,
                char_start=current_sentences[0]["char_start"],
                char_end=current_sentences[-1]["char_end"],
            )
        )

    return chunks


def create_chunks(
    extraction: ExtractionResult,
    source_id: str,
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[ChunkRecord]:
    """Route extraction result to appropriate chunking strategy."""
    if extraction.source_type == "transcript":
        return chunk_transcript(
            extraction.segments,
            source_id=source_id,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
    else:
        return chunk_document(
            extraction.segments,
            source_id=source_id,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )
