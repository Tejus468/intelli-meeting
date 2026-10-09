import Link from "next/link";
import { decisionExplorerHref } from "../lib/decisionLinks";

interface DecisionLinksProps {
  decisionIds: string[];
  /** Show the inline "Decision" label before each ID (the success card supplies its own heading). */
  showLabel?: boolean;
}

export default function DecisionLinks({ decisionIds, showLabel = true }: DecisionLinksProps) {
  if (decisionIds.length === 0) {
    return (
      <div className="decision-links">
        <span className="decision-none">
          {showLabel && <strong>Decisions:</strong>} None extracted
        </span>
      </div>
    );
  }

  return (
    <div className="decision-links">
      {decisionIds.map((decisionId) => (
        <div key={decisionId} className="decision-link-row">
          <span className="id-tag">
            {showLabel && <strong>Decision</strong>}
            <code>{decisionId}</code>
          </span>
          <Link
            href={decisionExplorerHref(decisionId)}
            className="btn-explore-decision"
            aria-label={`Explore decision ${decisionId}`}
          >
            Explore Decision
          </Link>
        </div>
      ))}
    </div>
  );
}
