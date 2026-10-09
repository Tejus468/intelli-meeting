"""Unit tests for document and transcript extraction and chunking."""
import io
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf
import pytest
import docx
from app.ingestion.extractors import (
    extract_txt,
    extract_pdf,
    extract_docx,
    extract_document,
)
from app.ingestion.chunker import (
    chunk_transcript,
    chunk_document,
    create_chunks,
    estimate_tokens,
)
from app.ingestion.models import ExtractedSegment, ExtractionResult


def test_txt_transcript_extraction():
    sample_transcript = """
[00:12:34] Rahul: We should use PostgreSQL for storage.
Rahul [00:13:00]: The pgvector extension makes vector search very fast.
00:14:15 Priya: I agree. What about the knowledge graph?
00:15:00 Rahul: We will use Neo4j for entities and relationships.
"""
    result = extract_txt(sample_transcript.encode("utf-8"), "meeting_notes.txt")
    assert result.source_type == "transcript"
    assert len(result.segments) == 4
    assert result.segments[0].speaker == "Rahul"
    assert result.segments[0].start_ts == "00:12:34"
    assert "PostgreSQL" in result.segments[0].text
    assert result.segments[2].speaker == "Priya"
    assert result.segments[2].start_ts == "00:14:15"


def test_txt_plain_document_extraction():
    plain_text = """This is the first paragraph of a system architecture specification.

This is the second paragraph discussing data models and storage requirements."""
    result = extract_txt(plain_text.encode("utf-8"), "architecture.txt")
    assert result.source_type == "txt"
    assert len(result.segments) == 2
    assert result.segments[0].speaker is None
    assert result.segments[0].page is None
    assert "architecture specification" in result.segments[0].text


def test_pdf_extraction_page_provenance():
    # Create in-memory multi-page PDF
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text((50, 72), "Page 1 Content: Project Kickoff and Requirements.")
    page2 = doc.new_page()
    page2.insert_text((50, 72), "Page 2 Content: Decision Matrix and Tradeoffs.")
    pdf_bytes = doc.tobytes()
    doc.close()

    result = extract_pdf(pdf_bytes, "project_doc.pdf")
    assert result.source_type == "pdf"
    assert len(result.segments) == 2
    assert result.segments[0].page == 1
    assert "Page 1" in result.segments[0].text
    assert result.segments[1].page == 2
    assert "Page 2" in result.segments[1].text


def test_docx_extraction_provenance():
    # Create in-memory DOCX
    doc = docx.Document()
    doc.add_paragraph("First paragraph in DOCX outlining goals.")
    doc.add_paragraph("Second paragraph in DOCX detailing action items.")
    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    result = extract_docx(docx_bytes, "meeting_summary.docx")
    assert result.source_type == "docx"
    assert len(result.segments) == 2
    assert result.segments[0].page is None
    assert "First paragraph" in result.segments[0].text
    assert "Second paragraph" in result.segments[1].text


def test_transcript_chunking_speaker_turn_preservation():
    segments = [
        ExtractedSegment(
            text="Let us discuss the vector database alternatives. Option A is pgvector.",
            speaker="Alex",
            start_ts="00:01:00",
            char_start=0,
            char_end=70,
        ),
        ExtractedSegment(
            text="Option B is Pinecone, but it is proprietary.",
            speaker="Sam",
            start_ts="00:02:00",
            char_start=71,
            char_end=115,
        ),
        ExtractedSegment(
            text="I strongly vote for pgvector because of relational co-location.",
            speaker="Alex",
            start_ts="00:03:00",
            char_start=116,
            char_end=180,
        ),
    ]

    chunks = chunk_transcript(segments, source_id="src_test_01", target_tokens=100, overlap_tokens=20)
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.source_id == "src_test_01"
        assert chunk.chunk_id.startswith("chk_")
        assert chunk.start_ts is not None


def test_document_chunking_sentence_boundaries():
    segments = [
        ExtractedSegment(
            text="Sentence one about the database schema. Sentence two about the vector embeddings.",
            page=1,
            char_start=0,
            char_end=81,
        )
    ]
    chunks = chunk_document(segments, source_id="src_doc_01", target_tokens=100, overlap_tokens=20)
    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert "Sentence one" in chunks[0].text
    assert "Sentence two" in chunks[0].text


def test_unsupported_file_format():
    try:
        extract_document(b"fake image data", "image.png")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported file format" in str(e)


def test_api_upload_unsupported_file_format():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    files = {"file": ("test.exe", b"binary content", "application/octet-stream")}
    response = client.post("/api/ingestion/upload", files=files)
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_api_upload_empty_file():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    files = {"file": ("empty.txt", b"", "text/plain")}
    response = client.post("/api/ingestion/upload", files=files)
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


# --- Google Meet style transcripts (name / timestamp / text) ---------------------------------------
MEET_TRANSCRIPT = """Google Meet Transcript

Meeting: E-commerce Platform Architecture & Deployment Planning

Date: October 6, 2026

Alice
00:00
Okay, let's get started. The main thing we need to decide today is the deployment.

Bob
00:18
Right now the backend is running on a single virtual machine.
It works, but we have had slowdowns.

Carol
00:34
I checked the monitoring data. We get sudden spikes during product launches.

Alice
01:02
That's one option. What's the downside?
"""


def test_google_meet_format_turns_get_speaker_timestamp_and_text():
    result = extract_txt(MEET_TRANSCRIPT.encode("utf-8"), "meet.txt")

    assert result.source_type == "transcript"
    turns = [s for s in result.segments if s.speaker]
    assert [(s.speaker, s.start_ts) for s in turns] == [
        ("Alice", "00:00"),
        ("Bob", "00:18"),
        ("Carol", "00:34"),
        ("Alice", "01:02"),
    ]
    assert turns[1].text == (
        "Right now the backend is running on a single virtual machine.\nIt works, but we have had slowdowns."
    )
    assert turns[3].text == "That's one option. What's the downside?"
    # the speaker name and the bare timestamp are not left behind inside the text
    assert all("00:18" not in s.text and s.text != "Bob" for s in turns)


def test_google_meet_metadata_header_is_not_read_as_speakers():
    result = extract_txt(MEET_TRANSCRIPT.encode("utf-8"), "meet.txt")

    speakers = {s.speaker for s in result.segments}
    assert speakers == {None, "Alice", "Bob", "Carol"}
    for label in ("Meeting", "Date", "Title", "Time", "Attendees", "Topic"):
        assert label not in speakers

    header = result.segments[0]
    assert header.speaker is None and header.start_ts is None
    assert "Google Meet Transcript" in header.text
    assert "Meeting: E-commerce Platform Architecture & Deployment Planning" in header.text
    assert "Date: October 6, 2026" in header.text


def test_google_meet_multiple_speakers_and_repeated_speaker():
    result = extract_txt(MEET_TRANSCRIPT.encode("utf-8"), "meet.txt")

    alice_turns = [s for s in result.segments if s.speaker == "Alice"]
    assert len(alice_turns) == 2  # one turn per appearance, not merged
    assert len([s for s in result.segments if s.speaker]) == 4
    # character offsets are strictly increasing, so provenance stays ordered
    starts = [s.char_start for s in result.segments]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)


def test_colons_inside_spoken_text_do_not_create_fake_speakers():
    text = "Alice\n00:00\nOne thing: we need to decide today.\nNote: this is urgent.\n\nBob\n00:10\nAgreed.\n"
    result = extract_txt(text.encode("utf-8"), "meet.txt")

    assert [s.speaker for s in result.segments] == ["Alice", "Bob"]
    assert "One thing: we need to decide today." in result.segments[0].text


@pytest.mark.parametrize("label", ["Meeting", "Date", "Title", "Time", "Attendees", "Topic"])
def test_metadata_labels_are_not_speakers_in_inline_transcripts_either(label):
    text = f"{label}: Weekly sync\n\nRahul: We should use PostgreSQL.\nPriya: Agreed.\n"
    result = extract_txt(text.encode("utf-8"), "notes.txt")

    assert result.source_type == "transcript"
    assert {s.speaker for s in result.segments if s.speaker} == {"Rahul", "Priya"}
    assert any(label in s.text for s in result.segments if s.speaker is None)


def test_existing_transcript_formats_still_parse_as_before():
    sample = """
[00:12:34] Rahul: We should use PostgreSQL for storage.
Rahul [00:13:00]: The pgvector extension makes vector search very fast.
00:14:15 Priya: I agree. What about the knowledge graph?
Anita: We will use Neo4j for entities and relationships.
"""
    result = extract_txt(sample.encode("utf-8"), "inline.txt")

    assert result.source_type == "transcript"
    assert [(s.speaker, s.start_ts) for s in result.segments] == [
        ("Rahul", "00:12:34"),
        ("Rahul", "00:13:00"),
        ("Priya", "00:14:15"),
        ("Anita", None),
    ]


def test_single_stray_name_and_time_pair_does_not_turn_a_document_into_a_transcript():
    text = "Project notes\n\nStandup\n09:30\nWe review the sprint board every morning.\n\nThe plan is simple."
    result = extract_txt(text.encode("utf-8"), "notes.txt")

    assert result.source_type == "txt"
    assert all(s.speaker is None for s in result.segments)


def test_plain_text_documents_are_unchanged():
    result = extract_txt(b"First paragraph about storage.\n\nSecond paragraph about models.", "doc.txt")

    assert result.source_type == "txt"
    assert len(result.segments) == 2


def test_google_meet_transcript_is_chunked_into_whole_turns_around_the_target_size():
    turns = []
    for n in range(60):
        speaker = ["Alice", "Bob", "Carol", "David"][n % 4]
        turns.append(
            f"{speaker}\n{n // 60:02d}:{n % 60:02d}\n"
            "We compared the managed container service with a single larger server for the checkout backend "
            "and noted the cost, the deployment effort and the expected traffic spikes."
        )
    text = "Google Meet Transcript\n\nMeeting: Planning\n\nDate: October 6, 2026\n\n" + "\n\n".join(turns)

    extraction = extract_txt(text.encode("utf-8"), "meet.txt")
    chunks = create_chunks(extraction, source_id="src_meet")

    assert len(extraction.segments) == 61  # header + 60 turns
    assert len(chunks) >= 3  # no longer one giant chunk
    turn_texts = {s.text for s in extraction.segments}
    for chunk in chunks:
        # each chunk is made of complete turns only (the chunker never cuts a turn)
        for part in chunk.text.split("\n\n"):
            body = part.split(": ", 1)[-1]
            assert body in turn_texts or part in turn_texts
        # target is ~400 tokens of turn text; allow the overlap and the speaker/timestamp prefixes on top
        assert estimate_tokens(chunk.text) < 600


if __name__ == "__main__":
    test_txt_transcript_extraction()
    test_txt_plain_document_extraction()
    test_pdf_extraction_page_provenance()
    test_docx_extraction_provenance()
    test_transcript_chunking_speaker_turn_preservation()
    test_document_chunking_sentence_boundaries()
    test_unsupported_file_format()
    test_api_upload_unsupported_file_format()
    test_api_upload_empty_file()
    print("All ingestion and API endpoint validation tests passed successfully!")

