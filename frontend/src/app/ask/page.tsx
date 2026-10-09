"use client";

import React, { useState, KeyboardEvent, ChangeEvent, FormEvent } from "react";
import { askQuestion, QuestionRequest, AnswerResponse, SourceReference, ApiError } from "@/lib/api";
import {
  IconSend,
  IconAlert,
  IconEvidence,
  IconCheckCircle,
  IconCopy,
} from "@/components/icons";

const EXAMPLE_QUESTIONS = [
  "Why was this decision made?",
  "What alternatives were considered?",
  "Why was this option rejected?",
  "Who owns the resulting action?",
  "What happened after the decision?",
];

const TOP_K_OPTIONS = [3, 5, 8, 10];

function formatRelevance(score: number): string {
  if (typeof score !== "number" || isNaN(score)) return "—";
  return `${Math.round(score * 100)}%`;
}

function formatTimestamp(start?: string | null, end?: string | null): string | null {
  if (start && end) return `${start} → ${end}`;
  if (start) return start;
  if (end) return end;
  return null;
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleSubmit = async (e?: FormEvent) => {
    if (e) e.preventDefault();

    const cleanQuestion = question.trim();
    if (!cleanQuestion) {
      setError("Please enter a question.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const payload: QuestionRequest = {
        question: cleanQuestion,
        top_k: topK,
      };
      const response = await askQuestion(payload);
      setResult(response);
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to retrieve evidence and generate answer.");
      } else if (err?.message) {
        setError(err.message);
      } else {
        setError("An unexpected network or server error occurred.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSelectExample = (example: string) => {
    setQuestion(example);
    setError(null);
  };

  const handleCopyId = (id: string) => {
    if (!navigator?.clipboard) return;
    navigator.clipboard.writeText(id).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const sortedSources = result?.sources
    ? [...result.sources].sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))
    : [];

  return (
    <div className="view-enter">
      <div className="page-header-mini">
        <span className="eyebrow accent-cyan">
          <span className="eyebrow-dot" aria-hidden="true" />
          Evidence-backed Intelligence
        </span>
        <h2 className="page-title-lg">Ask the knowledge base.</h2>
        <p className="page-copy">
          Ask anything about your organization's decisions — every answer is grounded in
          hybrid vector and knowledge graph retrieval, with sources you can inspect.
        </p>
      </div>

      {error && (
        <div className="alert-error" role="alert" aria-live="assertive" style={{ marginBottom: "1.25rem" }}>
          <span className="alert-icon" aria-hidden="true">
            <IconAlert size={16} />
          </span>
          <div className="alert-message">{error}</div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="composer">
          <label htmlFor="qa-question-input" className="sr-only">
            Ask a question about your meetings and decisions
          </label>
          <textarea
            id="qa-question-input"
            className="composer-textarea"
            placeholder="What would you like to know? e.g. Why was the database architecture changed?"
            value={question}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <div className="composer-footer">
            <div className="composer-footer-left">
              <div className="evidence-select-group">
                <span className="evidence-select-label">EVIDENCE</span>
                <div className="evidence-toggle-row" role="group" aria-label="Evidence items">
                  {TOP_K_OPTIONS.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      className={`evidence-toggle-btn ${topK === opt ? "active" : ""}`}
                      onClick={() => setTopK(opt)}
                      disabled={isLoading}
                      aria-pressed={topK === opt}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
              <span className="composer-hint">
                <span className="kbd">Ctrl</span>+<span className="kbd">Enter</span>
              </span>
            </div>

            <button
              type="submit"
              className="btn-icon"
              disabled={!question.trim() || isLoading}
              aria-busy={isLoading}
              aria-label="Ask question"
              title="Ask question"
            >
              {isLoading ? <div className="spinner" aria-hidden="true"></div> : <IconSend size={15} />}
            </button>
          </div>
        </div>
      </form>

      {!result && (
        <div className="suggestions-row">
          <span className="suggestions-label">SUGGESTED</span>
          <div className="suggestions-grid">
            {EXAMPLE_QUESTIONS.map((ex, idx) => (
              <button
                key={idx}
                type="button"
                className="suggestion-chip"
                onClick={() => handleSelectExample(ex)}
                disabled={isLoading}
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      {isLoading && (
        <div className="intelligence-loading" role="status" aria-live="polite">
          <span className="eyebrow accent-cyan">
            <span className="eyebrow-dot" aria-hidden="true" />
            Retrieving Evidence
          </span>
          <div className="loading-steps">
            <span className="loading-step" style={{ animationDelay: "0ms" }}>
              <span className="loading-step-dot" style={{ animationDelay: "0ms" }} />
              Graph context
            </span>
            <span className="loading-step" style={{ animationDelay: "120ms" }}>
              <span className="loading-step-dot" style={{ animationDelay: "220ms" }} />
              Semantic matches
            </span>
            <span className="loading-step" style={{ animationDelay: "240ms" }}>
              <span className="loading-step-dot" style={{ animationDelay: "440ms" }} />
              Source verification
            </span>
          </div>
        </div>
      )}

      {result && (
        <div className="answer-report" role="region" aria-label="Generated Answer">
          {/* QUESTION */}
          <div className="answer-block">
            <span className="eyebrow">Question</span>
            <div className="question-recap">&ldquo;{result.question}&rdquo;</div>
          </div>

          <hr className="hairline" />

          {/* ANSWER */}
          <div className="answer-block">
            <div className="answer-block-header">
              <span className="eyebrow accent-cyan">
                <span className="eyebrow-dot" aria-hidden="true" />
                Answer
              </span>
              <span className="grounded-tag">
                <IconCheckCircle size={12} />
                Grounded in retrieved evidence
              </span>
            </div>
            <div className="answer-body">{result.answer}</div>
          </div>

          {/* EVIDENCE TRAIL */}
          {sortedSources.length > 0 && (
            <div className="answer-block">
              <div className="answer-block-header">
                <span className="eyebrow">Evidence Trail</span>
                <span className="evidence-count-tag">
                  {result.evidence_count} item{result.evidence_count !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="evidence-trail-list">
                {sortedSources.map((src, index) => {
                  const pct = Math.max(0, Math.min(1, src.relevance_score || 0));
                  const timeStr = formatTimestamp(src.start_ts, src.end_ts);
                  const metaParts = [
                    src.speaker,
                    src.page !== null && src.page !== undefined ? `p.${src.page}` : null,
                    timeStr,
                  ].filter(Boolean);
                  return (
                    <div className="evidence-trail-row" key={`trail-${src.chunk_id || index}`}>
                      <span className="evidence-trail-index">{String(index + 1).padStart(2, "0")}</span>
                      <div className="evidence-trail-main">
                        <span className="evidence-trail-title">
                          {src.title || "Meeting / Source Document"}
                        </span>
                        {metaParts.length > 0 && (
                          <span className="evidence-trail-meta">{metaParts.join(" · ")}</span>
                        )}
                      </div>
                      <span className="evidence-trail-bar" aria-hidden="true">
                        <span className="evidence-trail-bar-fill" style={{ width: `${pct * 100}%` }} />
                      </span>
                      <span className="evidence-trail-relevance">{formatRelevance(src.relevance_score)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SOURCES */}
          {sortedSources.length > 0 && (
            <div className="answer-block">
              <div className="answer-block-header">
                <span className="eyebrow">
                  <IconEvidence size={13} />
                  Sources &amp; Provenance
                </span>
              </div>
              <div className="sources-list">
                {sortedSources.map((src: SourceReference, index: number) => {
                  const timeStr = formatTimestamp(src.start_ts, src.end_ts);
                  return (
                    <div key={`${src.source_id || "src"}-${src.chunk_id || index}`} className="source-row">
                      <div className="source-row-header">
                        <span className="source-row-title">
                          {src.title || "Meeting / Source Document"}
                        </span>
                        <span className="source-row-relevance">{formatRelevance(src.relevance_score)} match</span>
                      </div>
                      <div className="source-row-meta">
                        {src.speaker && (
                          <span className="source-row-meta-item">
                            <strong>Speaker:</strong> {src.speaker}
                          </span>
                        )}
                        {src.page !== null && src.page !== undefined && (
                          <span className="source-row-meta-item">
                            <strong>Page:</strong> {src.page}
                          </span>
                        )}
                        {timeStr && (
                          <span className="source-row-meta-item">
                            <strong>Time:</strong> {timeStr}
                          </span>
                        )}
                        {src.chunk_id && (
                          <span className="source-row-meta-item">
                            <span className="id-tag">
                              <strong>Chunk</strong>
                              <code>{src.chunk_id}</code>
                              <button
                                type="button"
                                className="copy-id-btn"
                                onClick={() => handleCopyId(src.chunk_id!)}
                                title="Copy Chunk ID"
                                aria-label="Copy Chunk ID"
                              >
                                {copiedId === src.chunk_id ? <IconCheckCircle size={12} /> : <IconCopy size={12} />}
                              </button>
                            </span>
                          </span>
                        )}
                        {src.source_id && (
                          <span className="source-row-meta-item">
                            <span className="id-tag">
                              <strong>Source</strong>
                              <code>{src.source_id}</code>
                              <button
                                type="button"
                                className="copy-id-btn"
                                onClick={() => handleCopyId(src.source_id!)}
                                title="Copy Source ID"
                                aria-label="Copy Source ID"
                              >
                                {copiedId === src.source_id ? <IconCheckCircle size={12} /> : <IconCopy size={12} />}
                              </button>
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
