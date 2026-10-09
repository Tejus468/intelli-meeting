"use client";

import React, { useState, useRef, useEffect, FormEvent, ChangeEvent } from "react";
import {
  getDecisionTimeline,
  getDecisionGraph,
  DecisionTimeline,
  DecisionGraph,
  TimelineEvent,
  ApiError,
} from "@/lib/api";
import GraphCanvas from "@/components/GraphCanvas";
import { decisionIdFromSearch } from "@/lib/decisionLinks";
import {
  IconAlert,
  IconSearch,
  IconCopy,
  IconCheckCircle,
  IconGraph,
  IconTimeline,
  IconLayers,
  IconAction,
  IconPeople,
  IconSend,
} from "@/components/icons";

function formatTimestamp(
  start?: string | number | null,
  end?: string | number | null
): string | null {
  if (start !== null && start !== undefined && end !== null && end !== undefined) {
    return `${start}s → ${end}s`;
  }
  if (start !== null && start !== undefined) return `${start}s`;
  if (end !== null && end !== undefined) return `${end}s`;
  return null;
}

interface EnrichedEvent extends TimelineEvent {
  alternativeStance?: "selected" | "rejected" | string;
  rationaleTarget?: string;
  rationaleStance?: string;
  actionOwnerName?: string;
  actionOwnerRole?: string;
  actionDeadline?: string;
  outcomeProducedBy?: string;
}

type ViewMode = "timeline" | "categorized" | "graph";

export default function DecisionsPage() {
  const [decisionIdInput, setDecisionIdInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<DecisionTimeline | null>(null);
  const [graph, setGraph] = useState<DecisionGraph | null>(null);
  const [activeTab, setActiveTab] = useState<ViewMode>("timeline");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isTyping = ["INPUT", "TEXTAREA"].includes(target?.tagName || "");
      if (e.key === "/" && !isTyping && !timeline) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [timeline]);

  useEffect(() => {
    const linkedId = decisionIdFromSearch(window.location.search);
    if (linkedId) {
      setDecisionIdInput(linkedId);
      loadDecision(linkedId);
    }
    // run once on mount: the id comes from the URL the user navigated with
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCopy = (id: string) => {
    if (!navigator?.clipboard) return;
    navigator.clipboard.writeText(id).then(() => {
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    });
  };

  const handleFetchDecision = async (e?: FormEvent) => {
    if (e) e.preventDefault();

    const cleanId = decisionIdInput.trim();
    if (!cleanId) {
      setError("Please enter a valid Decision ID.");
      return;
    }

    await loadDecision(cleanId);
  };

  const loadDecision = async (cleanId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const [timelineData, graphData] = await Promise.all([
        getDecisionTimeline(cleanId),
        getDecisionGraph(cleanId),
      ]);

      setTimeline(timelineData);
      setGraph(graphData);
    } catch (err: any) {
      setTimeline(null);
      setGraph(null);
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setError(`Decision "${cleanId}" not found. Check the Decision ID and try again.`);
        } else {
          setError(err.message || "Failed to retrieve decision context from knowledge graph.");
        }
      } else if (err?.message) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred while fetching the decision.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setTimeline(null);
    setGraph(null);
    setError(null);
    setDecisionIdInput("");
    setIsLoading(false);
    setActiveTab("timeline");
  };

  const enrichEvent = (ev: TimelineEvent): EnrichedEvent => {
    const enriched: EnrichedEvent = { ...ev };
    if (!graph) return enriched;

    if (ev.event_type === "alternative") {
      const relEdge = graph.edges.find(
        (e) =>
          e.target === ev.event_id &&
          (e.relationship === "SELECTED" || e.relationship === "REJECTED")
      );
      if (relEdge) {
        enriched.alternativeStance = relEdge.relationship.toLowerCase();
      } else if (ev.status) {
        enriched.alternativeStance = ev.status.toLowerCase();
      }
    }

    if (ev.event_type === "rationale") {
      const ratEdge = graph.edges.find(
        (e) =>
          e.source === ev.event_id &&
          (e.relationship === "SUPPORTS" || e.relationship === "OPPOSES")
      );
      if (ratEdge) {
        enriched.rationaleStance = ratEdge.relationship.toLowerCase();
        const targetNode = graph.nodes.find((n) => n.id === ratEdge.target);
        enriched.rationaleTarget =
          targetNode?.label || targetNode?.properties?.name || ratEdge.target;
      } else if (ev.status) {
        enriched.rationaleStance = ev.status.toLowerCase();
      }
    }

    if (ev.event_type === "action") {
      const ownerEdge = graph.edges.find(
        (e) => e.source === ev.event_id && e.relationship === "OWNED_BY"
      );
      if (ownerEdge) {
        const personNode = graph.nodes.find((n) => n.id === ownerEdge.target);
        if (personNode) {
          enriched.actionOwnerName = personNode.properties?.name || personNode.label;
          enriched.actionOwnerRole = personNode.properties?.role;
        }
      }
      const actionNode = graph.nodes.find((n) => n.id === ev.event_id);
      const deadline = actionNode?.properties?.deadline || actionNode?.properties?.due_date;
      if (deadline) {
        enriched.actionDeadline = String(deadline);
      }
    }

    if (ev.event_type === "outcome") {
      const prodEdge = graph.edges.find(
        (e) => e.target === ev.event_id && e.relationship === "PRODUCED"
      );
      if (prodEdge) {
        const actionNode = graph.nodes.find((n) => n.id === prodEdge.source);
        if (actionNode) {
          enriched.outcomeProducedBy = actionNode.properties?.task || actionNode.label;
        }
      }
    }

    return enriched;
  };

  const enrichedEvents = timeline?.events.map(enrichEvent) || [];
  const problems = enrichedEvents.filter((e) => e.event_type === "problem");
  const alternatives = enrichedEvents.filter((e) => e.event_type === "alternative");
  const rationales = enrichedEvents.filter((e) => e.event_type === "rationale");
  const decisionEvents = enrichedEvents.filter((e) => e.event_type === "decision");
  const actions = enrichedEvents.filter((e) => e.event_type === "action");
  const outcomes = enrichedEvents.filter((e) => e.event_type === "outcome");

  // Real provenance for the decision itself, sourced from its own timeline event (never invented)
  const decisionEvent = decisionEvents[0];
  const decisionTimeStr = decisionEvent
    ? formatTimestamp(decisionEvent.start_ts, decisionEvent.end_ts)
    : null;

  const renderProvenance = (ev: TimelineEvent) => {
    const hasEvidence =
      ev.source_title ||
      ev.source_date ||
      ev.speaker ||
      (ev.page !== null && ev.page !== undefined) ||
      (ev.start_ts !== null && ev.start_ts !== undefined) ||
      ev.chunk_id ||
      ev.source_id;

    if (!hasEvidence) return null;
    const timeStr = formatTimestamp(ev.start_ts, ev.end_ts);

    const parts: React.ReactNode[] = [];
    if (ev.source_title) parts.push(<span key="doc">{ev.source_title}</span>);
    if (ev.source_date) parts.push(<span key="date">{ev.source_date}</span>);
    if (ev.speaker) parts.push(<span key="spk">{ev.speaker}</span>);
    if (ev.page !== null && ev.page !== undefined) parts.push(<span key="pg">p.{ev.page}</span>);
    if (timeStr) parts.push(<span key="ts">{timeStr}</span>);

    return (
      <div className="timeline-provenance">
        {parts.map((p, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="sep">·</span>}
            {p}
          </React.Fragment>
        ))}
        {ev.chunk_id && (
          <>
            <span className="sep">·</span>
            <span className="id-tag">
              <code>{ev.chunk_id}</code>
              <button
                type="button"
                className="copy-id-btn"
                onClick={() => handleCopy(ev.chunk_id!)}
                title="Copy Chunk ID"
                aria-label="Copy Chunk ID"
              >
                {copiedId === ev.chunk_id ? <IconCheckCircle size={11} /> : <IconCopy size={11} />}
              </button>
            </span>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="view-enter">
      <div className="page-header-mini">
        <span className="eyebrow accent-cyan">
          <span className="eyebrow-dot" aria-hidden="true" />
          Decision Explorer
        </span>
        <h2 className="page-title-lg">Trace the reasoning behind a decision.</h2>
        <p className="page-copy">
          Follow the context, evidence, actions and outcomes connected to a decision
          through its timeline, categorized context, and knowledge graph.
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

      {!timeline && (
        <div className="decision-search-workspace">
          <span className="eyebrow">Search Decisions</span>
          <form onSubmit={handleFetchDecision}>
            <div className="decision-search-input-row">
              <span className="decision-search-icon" aria-hidden="true">
                <IconSearch size={18} />
              </span>
              <input
                ref={searchInputRef}
                id="decision-id-input"
                type="text"
                className="decision-search-input"
                placeholder="Enter a decision identifier…"
                value={decisionIdInput}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setDecisionIdInput(e.target.value)}
                disabled={isLoading}
                aria-label="Decision ID"
              />
              {!decisionIdInput && <span className="kbd" aria-hidden="true">/</span>}
              <button
                type="submit"
                className="btn-icon decision-search-submit"
                disabled={!decisionIdInput.trim() || isLoading}
                aria-busy={isLoading}
                aria-label="View decision"
              >
                {isLoading ? <div className="spinner" aria-hidden="true"></div> : <IconSend size={14} />}
              </button>
            </div>
          </form>
          <p className="page-copy" style={{ fontSize: "0.85rem" }}>
            Trace the reasoning, evidence, actions and outcomes behind a decision — e.g. try{" "}
            <code style={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}>dec_1</code>.
          </p>
          <div className="decision-modes-inline">
            <span className="decision-mode-chip">
              <IconTimeline size={14} />
              Timeline
            </span>
            <span className="decision-mode-chip">
              <IconLayers size={14} />
              Context
            </span>
            <span className="decision-mode-chip">
              <IconGraph size={14} />
              Knowledge Graph
            </span>
          </div>
        </div>
      )}

      {isLoading && !timeline && (
        <div className="loading-panel" role="status" aria-live="polite">
          <div className="spinner" aria-hidden="true"></div>
          <span>Loading decision context and knowledge graph relationships...</span>
        </div>
      )}

      {timeline && (
        <>
          <div className="decision-report" role="region" aria-label="Decision Details">
            <div className="decision-report-top">
              <div>
                <span className="eyebrow accent-cyan" style={{ marginBottom: "0.6rem" }}>
                  Decision
                </span>
                <h3 className="decision-report-statement">{timeline.decision_statement}</h3>
              </div>
              {timeline.decision_status && (
                <span className="decision-status-pill">{timeline.decision_status}</span>
              )}
            </div>

            <div className="decision-provenance-line">
              <span className="id-tag">
                <strong style={{ color: "var(--text-dim)" }}>ID</strong>
                <code>{timeline.decision_id}</code>
                <button
                  type="button"
                  className="copy-id-btn"
                  onClick={() => handleCopy(timeline.decision_id)}
                  title="Copy Decision ID"
                  aria-label="Copy Decision ID"
                >
                  {copiedId === timeline.decision_id ? <IconCheckCircle size={12} /> : <IconCopy size={12} />}
                </button>
              </span>
              {decisionEvent?.source_title && (
                <>
                  <span className="sep">·</span>
                  <span>
                    <strong style={{ color: "var(--text-dim)" }}>Source</strong> {decisionEvent.source_title}
                  </span>
                </>
              )}
              {decisionEvent?.source_date && (
                <>
                  <span className="sep">·</span>
                  <span>
                    <strong style={{ color: "var(--text-dim)" }}>Date</strong> {decisionEvent.source_date}
                  </span>
                </>
              )}
              {decisionTimeStr && (
                <>
                  <span className="sep">·</span>
                  <span>
                    <strong style={{ color: "var(--text-dim)" }}>Timestamp</strong> {decisionTimeStr}
                  </span>
                </>
              )}
            </div>

            <div className="decision-report-footer">
              <div />
              <button type="button" className="btn-ghost" onClick={handleReset}>
                Explore another decision
              </button>
            </div>
          </div>

          <div className="workspace-modes" role="tablist" aria-label="View options">
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "timeline"}
              className={`workspace-mode-btn ${activeTab === "timeline" ? "active" : ""}`}
              onClick={() => setActiveTab("timeline")}
            >
              <IconTimeline size={14} />
              Timeline
              <span className="mode-count">{enrichedEvents.length}</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "categorized"}
              className={`workspace-mode-btn ${activeTab === "categorized" ? "active" : ""}`}
              onClick={() => setActiveTab("categorized")}
            >
              <IconLayers size={14} />
              Context
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === "graph"}
              className={`workspace-mode-btn ${activeTab === "graph" ? "active" : ""}`}
              onClick={() => setActiveTab("graph")}
            >
              <IconGraph size={14} />
              Graph
              <span className="mode-count">{graph?.nodes.length || 0}</span>
            </button>
          </div>

          {activeTab === "graph" && graph && <GraphCanvas graph={graph} />}

          {activeTab === "timeline" && (
            <div className="timeline-rail" role="region" aria-label="Decision Timeline">
              {enrichedEvents.map((ev, index) => (
                <div
                  key={`${ev.event_id}-${index}`}
                  className="timeline-entry"
                  style={{ animationDelay: `${Math.min(index * 40, 400)}ms` }}
                >
                  <div className={`timeline-entry-marker type-${ev.event_type}`}></div>

                  <div className="timeline-entry-header">
                    <span className={`timeline-type-label type-${ev.event_type}`}>{ev.event_type}</span>

                    {ev.event_type === "alternative" && ev.alternativeStance && (
                      <span className={ev.alternativeStance === "selected" ? "badge-selected" : "badge-rejected"}>
                        {ev.alternativeStance === "selected" ? "Selected" : "Rejected"}
                      </span>
                    )}
                    {ev.event_type === "rationale" && ev.rationaleStance && (
                      <span className={ev.rationaleStance === "opposes" ? "badge-opposes" : "badge-supports"}>
                        {ev.rationaleStance}
                      </span>
                    )}
                    {ev.event_type === "action" && ev.status && (
                      <span className="badge-selected">{ev.status}</span>
                    )}
                    {ev.event_type === "outcome" && ev.status && (
                      <span className="badge-selected">{ev.status}</span>
                    )}
                  </div>

                  <div className="timeline-entry-title">{ev.label}</div>
                  {ev.description && <p className="timeline-entry-desc">{ev.description}</p>}

                  {(ev.rationaleTarget || ev.actionOwnerName || ev.outcomeProducedBy) && (
                    <div className="timeline-entry-meta">
                      {ev.rationaleTarget && (
                        <span className="timeline-entry-meta-item">
                          <strong>Target</strong> {ev.rationaleTarget}
                        </span>
                      )}
                      {ev.actionOwnerName && (
                        <span className="timeline-entry-meta-item">
                          <IconPeople size={12} />
                          <strong>Owner</strong> {ev.actionOwnerName}
                          {ev.actionOwnerRole ? ` (${ev.actionOwnerRole})` : ""}
                        </span>
                      )}
                      {ev.outcomeProducedBy && (
                        <span className="timeline-entry-meta-item">
                          <strong>From action</strong> {ev.outcomeProducedBy}
                        </span>
                      )}
                    </div>
                  )}

                  {renderProvenance(ev)}
                </div>
              ))}
            </div>
          )}

          {activeTab === "categorized" && (
            <div className="context-flow" role="region" aria-label="Categorized Context">
              {problems.length > 0 && (
                <div className="context-block">
                  <div className="context-block-label">
                    <span className="eyebrow" style={{ color: "var(--rose)" }}>Problem</span>
                  </div>
                  <div className="context-block-body">
                    {problems.map((pr, idx) => (
                      <div key={`${pr.event_id}-${idx}`} className="context-item">
                        <span className="context-item-title">{pr.label}</span>
                        {pr.description && <p className="context-item-desc">{pr.description}</p>}
                        {renderProvenance(pr)}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {alternatives.length > 0 && (
                <div className="context-block">
                  <div className="context-block-label">
                    <span className="eyebrow" style={{ color: "var(--violet)" }}>Considered</span>
                  </div>
                  <div className="context-block-body">
                    {alternatives.map((alt, idx) => (
                      <div key={`${alt.event_id}-${idx}`} className="context-item">
                        <div className="context-item-row">
                          <span
                            className={`context-item-title ${
                              alt.alternativeStance === "selected"
                                ? "is-selected"
                                : alt.alternativeStance === "rejected"
                                ? "is-rejected"
                                : ""
                            }`}
                          >
                            {alt.label}
                          </span>
                          {alt.alternativeStance && (
                            <span className={alt.alternativeStance === "selected" ? "badge-selected" : "badge-rejected"}>
                              {alt.alternativeStance === "selected" ? "Selected" : "Rejected"}
                            </span>
                          )}
                        </div>
                        {alt.description && <p className="context-item-desc">{alt.description}</p>}
                        {renderProvenance(alt)}
                        {idx < alternatives.length - 1 && <div className="context-divider-thin" />}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {rationales.length > 0 && (
                <div className="context-block">
                  <div className="context-block-label">
                    <span className="eyebrow" style={{ color: "var(--amber)" }}>Rationale</span>
                  </div>
                  <div className="context-block-body">
                    {rationales.map((rat, idx) => (
                      <div key={`${rat.event_id}-${idx}`} className="context-item">
                        <div className="context-item-row">
                          <span className="context-item-title">{rat.label}</span>
                          {rat.rationaleStance && (
                            <span className={rat.rationaleStance === "opposes" ? "badge-opposes" : "badge-supports"}>
                              {rat.rationaleStance}
                            </span>
                          )}
                        </div>
                        {rat.description && <p className="context-item-desc">{rat.description}</p>}
                        {rat.rationaleTarget && (
                          <div className="context-item-footer">
                            <span className="context-item-footer-item">
                              <strong>Alternative</strong> {rat.rationaleTarget}
                            </span>
                          </div>
                        )}
                        {renderProvenance(rat)}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {decisionEvents.length > 0 && (
                <div className="context-block">
                  <div className="context-block-label">
                    <span className="eyebrow accent-cyan">Decision</span>
                  </div>
                  <div className="context-block-body">
                    {decisionEvents.map((dec, idx) => (
                      <div key={`${dec.event_id}-${idx}`} className="context-item">
                        <span className="context-item-title is-selected">{dec.label}</span>
                        {dec.description && <p className="context-item-desc">{dec.description}</p>}
                        {renderProvenance(dec)}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {actions.length > 0 && (
                <div className="context-block">
                  <div className="context-block-label">
                    <span className="eyebrow" style={{ color: "var(--emerald)" }}>Action</span>
                  </div>
                  <div className="context-block-body">
                    {actions.map((act, idx) => (
                      <div key={`${act.event_id}-${idx}`} className="context-item">
                        <div className="context-item-row">
                          <span className="context-item-title">{act.label}</span>
                          {act.status && <span className="badge-selected">{act.status}</span>}
                        </div>
                        {act.description && <p className="context-item-desc">{act.description}</p>}
                        {(act.actionOwnerName || act.actionDeadline) && (
                          <div className="context-item-footer">
                            {act.actionOwnerName && (
                              <span className="context-item-footer-item">
                                <IconAction size={12} />
                                <strong>Owner</strong> {act.actionOwnerName}
                                {act.actionOwnerRole ? ` (${act.actionOwnerRole})` : ""}
                              </span>
                            )}
                            {act.actionDeadline && (
                              <span className="context-item-footer-item">
                                <strong>Deadline</strong> {act.actionDeadline}
                              </span>
                            )}
                          </div>
                        )}
                        {renderProvenance(act)}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {outcomes.length > 0 && (
                <div className="context-block">
                  <div className="context-block-label">
                    <span className="eyebrow" style={{ color: "var(--violet)" }}>Outcome</span>
                  </div>
                  <div className="context-block-body">
                    {outcomes.map((out, idx) => (
                      <div key={`${out.event_id}-${idx}`} className="context-item">
                        <div className="context-item-row">
                          <span className="context-item-title">{out.label}</span>
                          {out.status && <span className="badge-selected">{out.status}</span>}
                        </div>
                        {out.description && <p className="context-item-desc">{out.description}</p>}
                        {out.outcomeProducedBy && (
                          <div className="context-item-footer">
                            <span className="context-item-footer-item">
                              <strong>Produced by</strong> {out.outcomeProducedBy}
                            </span>
                          </div>
                        )}
                        {renderProvenance(out)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
