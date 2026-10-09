"use client";

import React, { useState, useRef, useMemo, MouseEvent, WheelEvent } from "react";
import { DecisionGraph, GraphNode, GraphEdge } from "@/lib/api";
import { IconGraph, IconWorkspace } from "@/components/icons";

interface GraphCanvasProps {
  graph: DecisionGraph;
}

interface PositionedNode {
  node: GraphNode;
  x: number;
  y: number;
  width: number;
  height: number;
}

const NODE_WIDTH = 190;
const NODE_HEIGHT = 56;
const CENTER_X = 650;

const NODE_COLOR_MAP: Record<
  string,
  { bg: string; border: string; text: string; tagBg: string; tagText: string }
> = {
  Decision: {
    bg: "rgba(53, 212, 255, 0.12)",
    border: "#35d4ff",
    text: "#f4f7fb",
    tagBg: "#0e3a4a",
    tagText: "#c7f0ff",
  },
  Problem: {
    bg: "rgba(242, 114, 114, 0.12)",
    border: "#f27272",
    text: "#f4f7fb",
    tagBg: "#4a1f1f",
    tagText: "#fbd7d7",
  },
  Alternative: {
    bg: "rgba(139, 124, 249, 0.12)",
    border: "#8b7cf9",
    text: "#f4f7fb",
    tagBg: "#2c2456",
    tagText: "#e2dcff",
  },
  Rationale: {
    bg: "rgba(245, 158, 11, 0.15)",
    border: "#fbbf24",
    text: "#f8fafc",
    tagBg: "#b45309",
    tagText: "#fffbeb",
  },
  Action: {
    bg: "rgba(53, 211, 153, 0.12)",
    border: "#35d399",
    text: "#f4f7fb",
    tagBg: "#0f3d2c",
    tagText: "#c8f5e2",
  },
  Person: {
    bg: "rgba(53, 211, 153, 0.08)",
    border: "#2dd4bf",
    text: "#f4f7fb",
    tagBg: "#0f3d3a",
    tagText: "#c8f5ee",
  },
  Outcome: {
    bg: "rgba(139, 124, 249, 0.1)",
    border: "#a996fa",
    text: "#f4f7fb",
    tagBg: "#332a5c",
    tagText: "#e6e0ff",
  },
  Source: {
    bg: "rgba(255, 255, 255, 0.03)",
    border: "#3a4356",
    text: "#dde3ec",
    tagBg: "#1a2030",
    tagText: "#9aa4b8",
  },
  Chunk: {
    bg: "rgba(255, 255, 255, 0.02)",
    border: "#2a3242",
    text: "#9aa4b8",
    tagBg: "#141822",
    tagText: "#7c8698",
  },
};

const DEFAULT_STYLE = {
  bg: "rgba(255, 255, 255, 0.03)",
  border: "#3a4356",
  text: "#f4f7fb",
  tagBg: "#1a2030",
  tagText: "#dde3ec",
};

const PROVENANCE_RELATIONSHIPS = new Set([
  "MADE_IN",
  "EVIDENCED_BY",
  "HAS_CHUNK",
  "SPOKEN_BY",
  "DISCUSSED",
]);

function truncateLabel(text: string, maxLen = 22): string {
  if (!text) return "";
  return text.length > maxLen ? text.slice(0, maxLen - 1) + "…" : text;
}

export default function GraphCanvas({ graph }: GraphCanvasProps) {
  const [scale, setScale] = useState(1.0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  // Deterministic Layered Layout Calculation
  const { positionedNodes, nodeMap, canvasWidth, canvasHeight } = useMemo(() => {
    const nodes = graph.nodes;

    const problems = nodes.filter((n) => n.node_type === "Problem");
    const alternatives = nodes.filter((n) => n.node_type === "Alternative");
    const rationales = nodes.filter((n) => n.node_type === "Rationale");
    const decisions = nodes.filter((n) => n.node_type === "Decision");
    const actions = nodes.filter((n) => n.node_type === "Action");
    const people = nodes.filter((n) => n.node_type === "Person");
    const outcomes = nodes.filter((n) => n.node_type === "Outcome");
    const sources = nodes.filter((n) => n.node_type === "Source");
    const chunks = nodes.filter((n) => n.node_type === "Chunk");
    const others = nodes.filter(
      (n) =>
        ![
          "Problem",
          "Alternative",
          "Rationale",
          "Decision",
          "Action",
          "Person",
          "Outcome",
          "Source",
          "Chunk",
        ].includes(n.node_type)
    );

    const posNodes: PositionedNode[] = [];

    const distributeRow = (
      items: GraphNode[],
      centerY: number,
      centerX = CENTER_X,
      spacing = 220
    ) => {
      if (items.length === 0) return;
      const totalWidth = (items.length - 1) * spacing;
      const startX = centerX - totalWidth / 2;
      items.forEach((node, i) => {
        posNodes.push({
          node,
          x: startX + i * spacing - NODE_WIDTH / 2,
          y: centerY - NODE_HEIGHT / 2,
          width: NODE_WIDTH,
          height: NODE_HEIGHT,
        });
      });
    };

    // Semantic hierarchy: Top to Bottom
    distributeRow(problems, 90);
    distributeRow(alternatives, 230);
    distributeRow(rationales, 370);
    distributeRow(decisions, 510);
    distributeRow(actions, 650);

    // Row 6: People (left side) and Outcomes (right side)
    distributeRow(people, 790, CENTER_X - 180, 220);
    distributeRow(outcomes, 790, CENTER_X + 180, 220);

    // Provenance: Sources on the Left column
    sources.forEach((node, i) => {
      posNodes.push({
        node,
        x: 80,
        y: 120 + i * 140 - NODE_HEIGHT / 2,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      });
    });

    // Provenance: Chunks on the Right column
    chunks.forEach((node, i) => {
      posNodes.push({
        node,
        x: 1180,
        y: 100 + i * 95 - NODE_HEIGHT / 2,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      });
    });

    // Any remaining nodes
    distributeRow(others, 930);

    // Compute bounding canvas dimensions
    let minX = 0;
    let maxX = 1450;
    let minY = 0;
    let maxY = 950;

    posNodes.forEach((p) => {
      if (p.x < minX) minX = p.x;
      if (p.x + p.width > maxX) maxX = p.x + p.width;
      if (p.y < minY) minY = p.y;
      if (p.y + p.height > maxY) maxY = p.y + p.height;
    });

    const cWidth = Math.max(1450, maxX + 100);
    const cHeight = Math.max(950, maxY + 100);

    const map = new Map<string, PositionedNode>();
    posNodes.forEach((p) => map.set(p.node.id, p));

    return {
      positionedNodes: posNodes,
      nodeMap: map,
      canvasWidth: cWidth,
      canvasHeight: cHeight,
    };
  }, [graph]);

  // Connected nodes and edges for selection highlight
  const { connectedNodeIds, connectedEdgeIds, selectedNode } = useMemo(() => {
    if (!selectedNodeId) {
      return {
        connectedNodeIds: new Set<string>(),
        connectedEdgeIds: new Set<string>(),
        selectedNode: null,
      };
    }

    const cNodes = new Set<string>([selectedNodeId]);
    const cEdges = new Set<string>();

    graph.edges.forEach((edge) => {
      if (edge.source === selectedNodeId) {
        cEdges.add(edge.id);
        cNodes.add(edge.target);
      } else if (edge.target === selectedNodeId) {
        cEdges.add(edge.id);
        cNodes.add(edge.source);
      }
    });

    const selNode = graph.nodes.find((n) => n.id === selectedNodeId) || null;

    return {
      connectedNodeIds: cNodes,
      connectedEdgeIds: cEdges,
      selectedNode: selNode,
    };
  }, [graph, selectedNodeId]);

  // Pan handlers
  const handleMouseDown = (e: MouseEvent<SVGSVGElement>) => {
    // Only pan when clicking on SVG background (not on interactive node)
    if ((e.target as HTMLElement).closest(".graph-node-interactive")) {
      return;
    }
    setIsPanning(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: MouseEvent<SVGSVGElement>) => {
    if (!isPanning) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  const handleWheel = (e: WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const zoomFactor = 1.1;
    const delta = e.deltaY < 0 ? zoomFactor : 1 / zoomFactor;
    setScale((prev) => Math.min(Math.max(prev * delta, 0.35), 2.5));
  };

  const handleZoomIn = () => setScale((s) => Math.min(s * 1.2, 2.5));
  const handleZoomOut = () => setScale((s) => Math.max(s / 1.2, 0.35));
  const handleResetView = () => {
    setScale(1.0);
    setPan({ x: 0, y: 0 });
    setSelectedNodeId(null);
  };

  const handleNodeClick = (e: MouseEvent, nodeId: string) => {
    e.stopPropagation();
    setSelectedNodeId((prev) => (prev === nodeId ? null : nodeId));
  };

  const handleBackgroundClick = () => {
    setSelectedNodeId(null);
  };

  if (graph.nodes.length === 0) {
    return (
      <div className="graph-empty-state">
        <div className="graph-empty-icon" aria-hidden="true">
          <IconGraph size={22} />
        </div>
        <p>No knowledge graph nodes found for this decision.</p>
      </div>
    );
  }

  return (
    <div className="graph-workspace">
      <div className="graph-toolbar">
        <div className="graph-toolbar-left">
          <span className="graph-toolbar-icon" aria-hidden="true">
            <IconWorkspace size={16} />
          </span>
          <div>
            <div className="graph-toolbar-title">Knowledge Graph Workspace</div>
            <div className="graph-toolbar-subtitle">
              Click a node to inspect it &middot; drag to pan &middot; scroll to zoom
            </div>
          </div>
        </div>
        <div className="graph-toolbar-stats">
          <span className="graph-stat-chip">{graph.nodes.length} nodes</span>
          <span className="graph-stat-chip">{graph.edges.length} relationships</span>
        </div>
      </div>

      <div className="graph-view-wrapper">
        <div
          className="graph-canvas-container"
          ref={containerRef}
          onWheel={handleWheel}
        >
        {/* Floating Zoom & Pan Controls */}
        <div className="graph-controls-floating" aria-label="Graph Controls">
          <button
            type="button"
            className="graph-control-btn"
            onClick={handleZoomIn}
            title="Zoom In"
            aria-label="Zoom In"
          >
            +
          </button>
          <button
            type="button"
            className="graph-control-btn"
            onClick={handleZoomOut}
            title="Zoom Out"
            aria-label="Zoom Out"
          >
            −
          </button>
          <button
            type="button"
            className="graph-control-btn"
            onClick={handleResetView}
            title="Reset View"
            aria-label="Reset View"
          >
            ⟲
          </button>
          <span className="graph-scale-indicator">
            {Math.round(scale * 100)}%
          </span>
        </div>

        {/* SVG Graph Viewport */}
        <div className={`graph-svg-wrapper ${isPanning ? "panning" : ""}`}>
          <svg
            className="graph-svg"
            width="100%"
            height="100%"
            viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onClick={handleBackgroundClick}
          >
            <defs>
              {/* Semantic Arrowhead */}
              <marker
                id="arrow-semantic"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1.5 L 10 5 L 0 8.5 z" fill="#64748b" />
              </marker>

              {/* Provenance Arrowhead */}
              <marker
                id="arrow-provenance"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1.5 L 10 5 L 0 8.5 z" fill="#475569" />
              </marker>

              {/* Highlighted Arrowhead */}
              <marker
                id="arrow-highlighted"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 1.5 L 10 5 L 0 8.5 z" fill="#38bdf8" />
              </marker>
            </defs>

            <g transform={`translate(${pan.x}, ${pan.y}) scale(${scale})`}>
              {/* 1. Render Edges */}
              <g className="graph-edges-layer">
                {graph.edges.map((edge) => {
                  const src = nodeMap.get(edge.source);
                  const tgt = nodeMap.get(edge.target);
                  if (!src || !tgt) return null;

                  const srcCenter = {
                    x: src.x + src.width / 2,
                    y: src.y + src.height / 2,
                  };
                  const tgtCenter = {
                    x: tgt.x + tgt.width / 2,
                    y: tgt.y + tgt.height / 2,
                  };

                  const isProvenance = PROVENANCE_RELATIONSHIPS.has(
                    edge.relationship
                  );
                  const isHighlighted =
                    selectedNodeId !== null && connectedEdgeIds.has(edge.id);
                  const isDimmed =
                    selectedNodeId !== null && !connectedEdgeIds.has(edge.id);

                  // Calculate label midpoint
                  const midX = (srcCenter.x + tgtCenter.x) / 2;
                  const midY = (srcCenter.y + tgtCenter.y) / 2;

                  const markerId = isHighlighted
                    ? "url(#arrow-highlighted)"
                    : isProvenance
                    ? "url(#arrow-provenance)"
                    : "url(#arrow-semantic)";

                  return (
                    <g
                      key={edge.id}
                      className={`graph-edge-group ${
                        isHighlighted ? "highlighted" : ""
                      } ${isDimmed ? "dimmed" : ""}`}
                    >
                      {/* Edge Line */}
                      <line
                        x1={srcCenter.x}
                        y1={srcCenter.y}
                        x2={tgtCenter.x}
                        y2={tgtCenter.y}
                        className={`graph-edge-line ${
                          isProvenance ? "provenance-line" : "semantic-line"
                        } ${isHighlighted ? "highlighted-line" : ""}`}
                        markerEnd={markerId}
                      />

                      {/* Edge Label Pill */}
                      {edge.relationship && (
                        <g transform={`translate(${midX}, ${midY})`}>
                          <rect
                            x={-(edge.relationship.length * 3.4 + 6)}
                            y="-9"
                            width={edge.relationship.length * 6.8 + 12}
                            height="18"
                            rx="4"
                            className="graph-edge-label-bg"
                          />
                          <text
                            className="graph-edge-label-text"
                            textAnchor="middle"
                            dy="3.5"
                          >
                            {edge.relationship}
                          </text>
                        </g>
                      )}
                    </g>
                  );
                })}
              </g>

              {/* 2. Render Nodes */}
              <g className="graph-nodes-layer">
                {positionedNodes.map((p) => {
                  const node = p.node;
                  const isSelected = selectedNodeId === node.id;
                  const isNeighbor =
                    selectedNodeId !== null && connectedNodeIds.has(node.id);
                  const isDimmed =
                    selectedNodeId !== null &&
                    !connectedNodeIds.has(node.id) &&
                    !isSelected;

                  const style = NODE_COLOR_MAP[node.node_type] || DEFAULT_STYLE;

                  return (
                    <g
                      key={node.id}
                      transform={`translate(${p.x}, ${p.y})`}
                      className={`graph-node-group graph-node-interactive ${
                        isSelected ? "selected" : ""
                      } ${isNeighbor ? "neighbor" : ""} ${
                        isDimmed ? "dimmed" : ""
                      }`}
                      onClick={(e) => handleNodeClick(e, node.id)}
                    >
                      {/* Node Box */}
                      <rect
                        width={p.width}
                        height={p.height}
                        rx="8"
                        fill={style.bg}
                        stroke={isSelected ? "#38bdf8" : style.border}
                        strokeWidth={isSelected ? "2.5" : "1.5"}
                        className="graph-node-rect"
                      />

                      {/* Type Badge */}
                      <rect
                        x="10"
                        y="8"
                        width={node.node_type.length * 6.2 + 10}
                        height="14"
                        rx="3"
                        fill={style.tagBg}
                      />
                      <text
                        x={15 + (node.node_type.length * 6.2) / 2}
                        y="18"
                        textAnchor="middle"
                        fill={style.tagText}
                        className="graph-node-type-text"
                      >
                        {node.node_type}
                      </text>

                      {/* Node Label */}
                      <text
                        x="12"
                        y="38"
                        fill={style.text}
                        className="graph-node-label-text"
                      >
                        <title>{node.label}</title>
                        {truncateLabel(node.label || node.id)}
                      </text>
                    </g>
                  );
                })}
              </g>
            </g>
          </svg>
        </div>

        {/* Selected Node Details Overlay Panel */}
        {selectedNode && (
          <div
            className="graph-details-overlay"
            role="region"
            aria-label="Node Details"
          >
            <div className="details-header">
              <div className="details-title-group">
                <span
                  className="details-type-tag"
                  style={{
                    backgroundColor:
                      NODE_COLOR_MAP[selectedNode.node_type]?.tagBg ||
                      DEFAULT_STYLE.tagBg,
                    color:
                      NODE_COLOR_MAP[selectedNode.node_type]?.tagText ||
                      DEFAULT_STYLE.tagText,
                  }}
                >
                  {selectedNode.node_type}
                </span>
                <h4 className="details-heading">
                  {selectedNode.label || selectedNode.id}
                </h4>
              </div>

              <button
                type="button"
                className="details-close-btn"
                onClick={() => setSelectedNodeId(null)}
                aria-label="Close details panel"
              >
                ✕
              </button>
            </div>

            <div className="details-body">
              <div className="details-id-row">
                <span className="details-prop-label">ID:</span>
                <code className="details-prop-code">{selectedNode.id}</code>
              </div>

              {/* Node Properties */}
              {Object.keys(selectedNode.properties || {}).length > 0 && (
                <div className="details-props-table">
                  {Object.entries(selectedNode.properties).map(([k, v]) => {
                    if (v === null || v === undefined || v === "") return null;
                    return (
                      <div key={k} className="details-prop-row">
                        <span className="details-prop-label">{k}:</span>
                        <span className="details-prop-val">
                          {typeof v === "object"
                            ? JSON.stringify(v)
                            : String(v)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Connected Relationships List */}
              <div className="details-relationships-section">
                <span className="details-rel-heading">
                  Connections ({connectedEdgeIds.size}):
                </span>
                <ul className="details-rel-list">
                  {graph.edges
                    .filter(
                      (e) =>
                        e.source === selectedNode.id ||
                        e.target === selectedNode.id
                    )
                    .map((edge) => {
                      const isOutgoing = edge.source === selectedNode.id;
                      const otherId = isOutgoing ? edge.target : edge.source;
                      const otherNode = graph.nodes.find(
                        (n) => n.id === otherId
                      );

                      return (
                        <li key={edge.id} className="details-rel-item">
                          <span className="rel-direction">
                            {isOutgoing ? "→" : "←"}
                          </span>
                          <span className="rel-name">{edge.relationship}</span>
                          <span className="rel-target">
                            {otherNode?.label
                              ? truncateLabel(otherNode.label, 18)
                              : otherId}
                          </span>
                        </li>
                      );
                    })}
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Node Type Legend */}
      <div className="graph-legend-bar" aria-label="Node Type Legend">
        <span className="legend-title">Legend:</span>
        <div className="legend-items">
          {Object.entries(NODE_COLOR_MAP).map(([type, colors]) => (
            <div key={type} className="legend-item">
              <span
                className="legend-dot"
                style={{ backgroundColor: colors.border }}
              ></span>
              <span className="legend-label">{type}</span>
            </div>
          ))}
          <div className="legend-item">
            <span className="legend-line-semantic"></span>
            <span className="legend-label">Semantic Link</span>
          </div>
          <div className="legend-item">
            <span className="legend-line-provenance"></span>
            <span className="legend-label">Provenance Link</span>
          </div>
        </div>
      </div>
      </div>
    </div>
  );
}
