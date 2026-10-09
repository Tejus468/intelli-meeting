"use client";

import React, { useState, useRef, useEffect, useCallback, ChangeEvent, DragEvent } from "react";
import {
  uploadDocument,
  listSources,
  deleteSource,
  IngestionResponse,
  SourceSummary,
  ApiError,
} from "@/lib/api";
import DecisionLinks from "@/components/DecisionLinks";
import {
  IconUpload,
  IconAlert,
  IconCheckCircle,
  IconDocuments,
  IconLayers,
  IconEntities,
  IconMerge,
} from "@/components/icons";

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"];

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function getFileExtension(filename: string): string {
  const parts = filename.split(".");
  return parts.length > 1 ? parts.pop()?.toUpperCase() || "UNKNOWN" : "FILE";
}

function formatIngestedDate(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

const FLOW_STEPS = [
  { title: "Document", desc: "Raw PDF, DOCX or TXT source", icon: IconDocuments },
  { title: "Chunks", desc: "Segmented with page & speaker provenance", icon: IconLayers },
  { title: "Entities", desc: "Problems, decisions, actions extracted", icon: IconEntities },
  { title: "Relationships", desc: "Persisted into the knowledge graph", icon: IconMerge },
];

export default function DocumentsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IngestionResponse | null>(null);
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [isLoadingSources, setIsLoadingSources] = useState(true);
  const [sourcesError, setSourcesError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshSources = useCallback(async () => {
    setSourcesError(null);
    try {
      setSources(await listSources());
    } catch (err: any) {
      setSourcesError(err?.message || "Failed to load documents.");
    } finally {
      setIsLoadingSources(false);
    }
  }, []);

  useEffect(() => {
    refreshSources();
  }, [refreshSources]);

  const validateAndSetFile = (file: File) => {
    setError(null);
    setResult(null);

    const lowerName = file.name.toLowerCase();
    const isValidExtension = ALLOWED_EXTENSIONS.some((ext) =>
      lowerName.endsWith(ext)
    );

    if (!isValidExtension) {
      setError(
        `Unsupported file type "${file.name}". Please select a PDF, DOCX, or TXT file.`
      );
      setSelectedFile(null);
      return;
    }

    if (file.size === 0) {
      setError(
        `File "${file.name}" is empty (0 bytes). Please select a valid document.`
      );
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isUploading) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: DragEvent<HTMLElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    if (isUploading) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("Please select a document to upload.");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const response = await uploadDocument(selectedFile);
      setResult(response);
      refreshSources();
    } catch (err: any) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to upload and ingest document.");
      } else if (err?.message) {
        setError(err.message);
      } else {
        setError("An unexpected network or server error occurred during upload.");
      }
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteSource = async (sourceId: string) => {
    setDeletingId(sourceId);
    setDeleteError(null);
    try {
      await deleteSource(sourceId);
      setConfirmDeleteId(null);
      if (result?.source_id === sourceId) {
        setResult(null);
      }
      await refreshSources();
    } catch (err: any) {
      setDeleteError(err?.message || "Failed to remove the document.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setError(null);
    setResult(null);
    setIsUploading(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <div className="view-enter">
      <div className="page-header-mini">
        <span className="eyebrow accent-cyan">
          <span className="eyebrow-dot" aria-hidden="true" />
          Document Intelligence
        </span>
        <h2 className="page-title-lg">Bring the source material into the decision graph.</h2>
        <p className="page-copy">
          Upload meeting transcripts and organizational documents to chunk, extract, and
          persist structured provenance in the decision knowledge base.
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

      {result ? (
        <div className="ingest-result" role="region" aria-label="Upload Result">
          <div className="ingest-result-header">
            <div className="ingest-result-icon" aria-hidden="true">
              <IconCheckCircle size={18} />
            </div>
            <div>
              <div className="ingest-result-title">Ingestion complete</div>
              <div className="ingest-result-subtitle">
                Document processed, chunked, and persisted into the knowledge base.
              </div>
            </div>
          </div>

          <div className="ingest-fields">
            <div className="ingest-field">
              <span className="ingest-field-label">Source</span>
              <span className="ingest-field-value">{result.title}</span>
            </div>
            <div className="ingest-field">
              <span className="ingest-field-label">Type</span>
              <span className="ingest-field-value">{result.source_type}</span>
            </div>
            <div className="ingest-field">
              <span className="ingest-field-label">Chunks</span>
              <span className="ingest-field-value accent">{result.number_of_chunks}</span>
            </div>
            <div className="ingest-field">
              <span className="ingest-field-label">Status</span>
              <span className="ingest-field-value" style={{ color: "var(--emerald)", textTransform: "capitalize" }}>
                {result.status}
              </span>
            </div>
            <div className="ingest-field">
              <span className="ingest-field-label">Source ID</span>
              <span className="ingest-field-value mono">{result.source_id}</span>
            </div>
          </div>

          <div className="ingest-decisions">
            <span className="ingest-field-label">
              {(result.decision_ids ?? []).length > 1 ? "Decision IDs" : "Decision ID"}
            </span>
            <DecisionLinks decisionIds={result.decision_ids ?? []} showLabel={false} />
          </div>

          <div className="actions-row">
            <button type="button" className="btn-secondary" onClick={handleReset}>
              Upload another document
            </button>
          </div>
        </div>
      ) : (
        <div className="doc-workspace">
          <div className="upload-container">
            <input
              ref={fileInputRef}
              type="file"
              id="document-file-input"
              className="sr-only"
              accept=".pdf,.docx,.txt"
              onChange={handleFileChange}
              disabled={isUploading}
              aria-label="Upload document file"
            />

            <label
              htmlFor="document-file-input"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className={`upload-surface ${isDragging ? "dragging" : ""}`}>
                <div className="upload-surface-icon" aria-hidden="true">
                  <IconUpload size={20} strokeWidth={1.8} />
                </div>
                <span className="upload-surface-title">
                  {selectedFile ? "Click or drop a different file to replace" : "Select or drag and drop a document"}
                </span>
                <span className="upload-surface-subtitle">
                  Supports meeting transcripts and technical documents
                </span>
                <div className="format-badges" aria-label="Supported file formats">
                  <span className="format-badge">PDF</span>
                  <span className="format-badge">DOCX</span>
                  <span className="format-badge">TXT</span>
                </div>
              </div>
            </label>

            {selectedFile && (
              <div className="selected-file-panel" role="status" aria-label="Selected file">
                <div className="file-details">
                  <div className="file-icon" aria-hidden="true">
                    {getFileExtension(selectedFile.name)}
                  </div>
                  <div className="file-meta">
                    <span className="file-name" title={selectedFile.name}>
                      {selectedFile.name}
                    </span>
                    <span className="file-size">{formatFileSize(selectedFile.size)}</span>
                  </div>
                </div>
                {!isUploading && (
                  <button
                    type="button"
                    className="btn-clear-file"
                    onClick={handleClearFile}
                    aria-label="Remove selected file"
                  >
                    Remove
                  </button>
                )}
              </div>
            )}

            {isUploading && (
              <div className="loading-panel" role="status" aria-live="polite">
                <div className="spinner" aria-hidden="true"></div>
                <span>Uploading document and extracting chunks with provenance...</span>
              </div>
            )}

            <div className="actions-row" style={{ marginTop: "0.25rem" }}>
              <button
                type="button"
                className="btn-primary"
                onClick={handleUpload}
                disabled={!selectedFile || isUploading}
                aria-busy={isUploading}
              >
                {isUploading ? (
                  <>
                    <div className="spinner" aria-hidden="true"></div>
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <IconUpload size={15} />
                    <span>Upload Document</span>
                  </>
                )}
              </button>

              {selectedFile && !isUploading && (
                <button type="button" className="btn-secondary" onClick={handleClearFile}>
                  Cancel
                </button>
              )}
            </div>
          </div>

          <div className="doc-flow-rail" aria-hidden="true">
            {FLOW_STEPS.map((step) => {
              const Icon = step.icon;
              return (
                <div className="doc-flow-node" key={step.title}>
                  <div className="doc-flow-marker">
                    <Icon size={14} />
                  </div>
                  <div className="doc-flow-body">
                    <div className="doc-flow-title">{step.title}</div>
                    <div className="doc-flow-desc">{step.desc}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <section className="doc-library" aria-label="Ingested documents">
        <div className="answer-block-header">
          <span className="eyebrow">Ingested Documents</span>
          {!isLoadingSources && !sourcesError && (
            <span className="evidence-count-tag">
              {sources.length} document{sources.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {deleteError && (
          <div className="alert-error" role="alert" aria-live="assertive">
            <span className="alert-icon" aria-hidden="true">
              <IconAlert size={16} />
            </span>
            <div className="alert-message">{deleteError}</div>
          </div>
        )}

        {isLoadingSources ? (
          <div className="loading-panel" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true"></div>
            <span>Loading documents...</span>
          </div>
        ) : sourcesError ? (
          <div className="alert-error" role="alert">
            <span className="alert-icon" aria-hidden="true">
              <IconAlert size={16} />
            </span>
            <div className="alert-message">{sourcesError}</div>
          </div>
        ) : sources.length === 0 ? (
          <p className="doc-library-empty">
            No documents have been ingested yet. Upload a transcript or document to get started.
          </p>
        ) : (
          <div className="sources-list">
            {sources.map((src) => {
              const ingested = formatIngestedDate(src.created_at);
              const isConfirming = confirmDeleteId === src.source_id;
              const isDeleting = deletingId === src.source_id;
              return (
                <div key={src.source_id} className="source-row">
                  <div className="source-row-header">
                    <span className="source-row-title">{src.title}</span>
                    <div className="source-row-side">
                      <span className="source-row-relevance">
                        {src.number_of_chunks} chunk{src.number_of_chunks !== 1 ? "s" : ""}
                      </span>
                      {isConfirming ? (
                        <div className="source-row-confirm" role="group" aria-label={`Confirm removing ${src.title}`}>
                          <span className="source-row-confirm-text">
                            Remove document, embeddings and graph data?
                          </span>
                          <button
                            type="button"
                            className="btn-confirm-remove"
                            onClick={() => handleDeleteSource(src.source_id)}
                            disabled={isDeleting}
                            aria-busy={isDeleting}
                          >
                            {isDeleting ? "Removing..." : "Confirm"}
                          </button>
                          <button
                            type="button"
                            className="btn-clear-file"
                            onClick={() => setConfirmDeleteId(null)}
                            disabled={isDeleting}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="btn-clear-file"
                          onClick={() => {
                            setDeleteError(null);
                            setConfirmDeleteId(src.source_id);
                          }}
                          disabled={deletingId !== null}
                          aria-label={`Remove document ${src.title}`}
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="source-row-meta">
                    <span className="source-row-meta-item">
                      <strong>Type:</strong> {src.source_type}
                    </span>
                    {ingested && (
                      <span className="source-row-meta-item">
                        <strong>Ingested:</strong> {ingested}
                      </span>
                    )}
                    <span className="source-row-meta-item">
                      <span className="id-tag">
                        <strong>Source</strong>
                        <code>{src.source_id}</code>
                      </span>
                    </span>
                  </div>
                  <DecisionLinks decisionIds={src.decision_ids ?? []} />
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
