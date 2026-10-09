"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconOverview,
  IconDocuments,
  IconDecisions,
  IconAsk,
} from "@/components/icons";

interface NavItem {
  name: string;
  href: string;
  description: string;
  icon: (props: { size?: number }) => JSX.Element;
}

const NAV_ITEMS: NavItem[] = [
  {
    name: "Overview",
    href: "/",
    description: "System overview and capabilities",
    icon: IconOverview,
  },
  {
    name: "Documents",
    href: "/documents",
    description: "Upload & transcript ingestion",
    icon: IconDocuments,
  },
  {
    name: "Decisions",
    href: "/decisions",
    description: "Timeline & knowledge graph",
    icon: IconDecisions,
  },
  {
    name: "Ask",
    href: "/ask",
    description: "Evidence-backed Q&A assistant",
    icon: IconAsk,
  },
];

export default function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="nav-container" aria-label="Main Navigation">
      <ul className="nav-list" role="list">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          const Icon = item.icon;

          return (
            <li key={item.href} className="nav-item">
              <Link
                href={item.href}
                className={`nav-link ${isActive ? "active" : ""}`}
                aria-current={isActive ? "page" : undefined}
                title={item.description}
              >
                <span className="nav-indicator" aria-hidden="true"></span>
                <span className="nav-icon" aria-hidden="true">
                  <Icon size={16} />
                </span>
                <span className="nav-link-text">{item.name}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="nav-footer">
        <div className="system-indicator">
          <span className="system-indicator-dot" aria-hidden="true"></span>
          <span className="system-indicator-text">
            <span className="system-indicator-label">Intelligence Engine</span>
            <span className="system-indicator-version">v1.0</span>
          </span>
        </div>
      </div>
    </nav>
  );
}
