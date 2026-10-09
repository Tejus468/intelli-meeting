import Link from "next/link";
import {
  IconDocuments,
  IconSparkles,
  IconDatabase,
  IconMerge,
  IconEvidence,
  IconDecisions,
  IconAsk,
  IconGraph,
  IconArrowRight,
  IconUpload,
} from "@/components/icons";

interface FlowNode {
  id: string;
  x: number;
  y: number;
  label: string;
  sublabel: string;
  icon: (props: { size?: number }) => JSX.Element;
  merge?: boolean;
}

const FLOW_NODES: FlowNode[] = [
  { id: "docs", x: 60, y: 75, label: "Documents", sublabel: "PDF · DOCX · TXT", icon: IconDocuments },
  { id: "extract", x: 250, y: 75, label: "Extraction", sublabel: "Problems · actions · rationale", icon: IconSparkles },
  { id: "kg", x: 460, y: 35, label: "Knowledge Graph", sublabel: "Neo4j", icon: IconGraph },
  { id: "vec", x: 460, y: 115, label: "Vector Search", sublabel: "pgvector", icon: IconDatabase },
  { id: "hybrid", x: 660, y: 75, label: "Hybrid Retrieval", sublabel: "Fused ranking", icon: IconMerge, merge: true },
  { id: "evidence", x: 850, y: 75, label: "Evidence", sublabel: "Cited sources", icon: IconEvidence },
  { id: "decision", x: 1030, y: 75, label: "Decision Intelligence", sublabel: "Traceable answers", icon: IconDecisions },
];

const FLOW_LINKS: Array<{ from: string; to: string; active?: boolean }> = [
  { from: "docs", to: "extract", active: true },
  { from: "extract", to: "kg" },
  { from: "extract", to: "vec" },
  { from: "kg", to: "hybrid", active: true },
  { from: "vec", to: "hybrid", active: true },
  { from: "hybrid", to: "evidence", active: true },
  { from: "evidence", to: "decision", active: true },
];

function findNode(id: string) {
  return FLOW_NODES.find((n) => n.id === id)!;
}

interface Capability {
  index: string;
  kicker: string;
  subtitle: string;
  description: string;
  href: string;
  actionLabel: string;
  visual: JSX.Element;
}

const CAPABILITIES: Capability[] = [
  {
    index: "01",
    kicker: "Ask",
    subtitle: "Evidence-backed Q&A",
    description:
      "Ask why a decision was made and inspect the evidence behind the answer — grounded in hybrid vector and graph retrieval.",
    href: "/ask",
    actionLabel: "Ask a question",
    visual: (
      <div className="viz-qa">
        <div className="viz-qa-line" style={{ width: "82%" }} />
        <div className="viz-qa-line short" />
        <div className="viz-qa-line accent" />
      </div>
    ),
  },
  {
    index: "02",
    kicker: "Explore",
    subtitle: "Decision Explorer",
    description:
      "Trace problems, alternatives, rationale, actions and outcomes as one continuous decision journey.",
    href: "/decisions",
    actionLabel: "Explore decisions",
    visual: (
      <div className="viz-explorer">
        <span className="viz-explorer-dot on" />
        <span className="viz-explorer-seg" />
        <span className="viz-explorer-dot on" />
        <span className="viz-explorer-seg" />
        <span className="viz-explorer-dot" />
        <span className="viz-explorer-seg" />
        <span className="viz-explorer-dot on" />
      </div>
    ),
  },
  {
    index: "03",
    kicker: "Visualize",
    subtitle: "Knowledge Graph",
    description:
      "Navigate the relationships behind a decision with an interactive, pannable graph. Select any node to inspect its provenance.",
    href: "/decisions",
    actionLabel: "View the graph",
    visual: (
      <svg className="viz-graph" viewBox="0 0 220 130">
        <line className="viz-graph-line" x1="50" y1="35" x2="110" y2="65" />
        <line className="viz-graph-line" x1="170" y1="35" x2="110" y2="65" />
        <line className="viz-graph-line" x1="110" y1="65" x2="90" y2="100" />
        <line className="viz-graph-line" x1="110" y1="65" x2="150" y2="100" />
        <circle className="viz-graph-dot" cx="50" cy="35" r="6" />
        <circle className="viz-graph-dot" cx="170" cy="35" r="6" />
        <circle className="viz-graph-dot on" cx="110" cy="65" r="7" />
        <circle className="viz-graph-dot" cx="90" cy="100" r="6" />
        <circle className="viz-graph-dot on" cx="150" cy="100" r="6" />
      </svg>
    ),
  },
];

export default function OverviewPage() {
  return (
    <div className="view-enter">
      {/* Hero */}
      <section className="hero">
        <span className="eyebrow accent-cyan">
          <span className="eyebrow-dot" aria-hidden="true" />
          Decision Intelligence Platform
        </span>
        <h1 className="hero-heading">
          Turn conversations into
          <br />
          <span className="accent">decision intelligence.</span>
        </h1>
        <p className="hero-copy">
          A knowledge graph and hybrid retrieval system that turns unstructured meeting
          discussions into structured, evidence-backed intelligence — every answer
          traceable back to its source.
        </p>
        <div className="hero-actions">
          <Link href="/ask" className="btn-primary">
            <IconAsk size={15} />
            <span>Ask a Question</span>
          </Link>
          <Link href="/documents" className="btn-secondary">
            <IconUpload size={15} />
            <span>Upload Documents</span>
          </Link>
        </div>
      </section>

      {/* Pipeline flow */}
      <section className="flow-section">
        <div className="flow-heading-row">
          <span className="flow-heading">How information becomes intelligence</span>
          <span className="flow-note">Documents → Extraction → Graph + Vector → Retrieval → Evidence</span>
        </div>

        <svg className="flow-diagram" viewBox="0 0 1090 160" role="img" aria-label="Decision intelligence pipeline">
          <defs>
            <filter id="flow-node-blur" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="5" />
            </filter>
          </defs>
          <g className="flow-links">
            {FLOW_LINKS.map((link, i) => {
              const a = findNode(link.from);
              const b = findNode(link.to);
              const midX = (a.x + b.x) / 2;
              const path = `M ${a.x + 21} ${a.y} C ${midX} ${a.y}, ${midX} ${b.y}, ${b.x - 21} ${b.y}`;
              return (
                <path
                  key={i}
                  d={path}
                  className={link.active ? "flow-line-active" : "flow-line"}
                />
              );
            })}
          </g>

          {/* Merge indicator — Knowledge Graph + Vector Search combine into Hybrid Retrieval */}
          <g className="flow-merge-indicator">
            <line x1="460" y1="56" x2="460" y2="94" className="flow-merge-connector" />
            <circle cx="460" cy="75" r="9" className="flow-merge-badge" filter="url(#flow-node-blur)" opacity="0.5" />
            <circle cx="460" cy="75" r="9" className="flow-merge-badge" />
            <text x="460" y="79" textAnchor="middle" className="flow-merge-plus">+</text>
          </g>

          <g className="flow-nodes">
            {FLOW_NODES.map((node) => {
              const Icon = node.icon;
              return (
                <g
                  key={node.id}
                  className={`flow-node ${node.merge ? "is-merge" : ""}`}
                  transform={`translate(${node.x}, ${node.y})`}
                >
                  {node.merge && (
                    <circle className="flow-node-pulse" r="26" filter="url(#flow-node-blur)" />
                  )}
                  <circle className="flow-node-glow" r="26" />
                  <circle className="flow-node-circle" r="21" />
                  <g transform="translate(-9, -9)" className="flow-node-icon">
                    <Icon size={18} />
                  </g>
                  <text className="flow-node-label" textAnchor="middle" y="42">
                    {node.label}
                  </text>
                  <text className="flow-node-sublabel" textAnchor="middle" y="56">
                    {node.sublabel}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </section>

      {/* Capabilities — editorial split rows */}
      <section className="capabilities-section">
        {CAPABILITIES.map((cap) => (
          <Link key={cap.kicker} href={cap.href} className="capability-row">
            <span className="capability-index">{cap.index}</span>
            <div className="capability-copy">
              <div className="capability-kicker-row">
                <h3 className="capability-title">{cap.kicker}</h3>
                <span className="capability-subtitle">{cap.subtitle}</span>
              </div>
              <p className="capability-desc">{cap.description}</p>
              <span className="capability-link">
                <span>{cap.actionLabel}</span>
                <IconArrowRight size={13} />
              </span>
            </div>
            <div className="capability-visual" aria-hidden="true">
              {cap.visual}
            </div>
          </Link>
        ))}
      </section>
    </div>
  );
}
