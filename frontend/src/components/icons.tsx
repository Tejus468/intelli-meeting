"use client";

import React from "react";

export type IconProps = {
  size?: number;
  className?: string;
  strokeWidth?: number;
};

function base(paths: React.ReactNode) {
  return function Icon({ size = 18, className, strokeWidth = 1.8 }: IconProps) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-hidden="true"
      >
        {paths}
      </svg>
    );
  };
}

export const IconOverview = base(
  <>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </>
);

export const IconDocuments = base(
  <>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="13" y2="17" />
  </>
);

export const IconDecisions = base(
  <>
    <circle cx="6" cy="6" r="2.5" />
    <circle cx="18" cy="6" r="2.5" />
    <circle cx="12" cy="18" r="2.5" />
    <path d="M6 8.5V13a3 3 0 0 0 3 3h0.3" />
    <path d="M18 8.5V13a3 3 0 0 1-3 3h-0.3" />
  </>
);

export const IconAsk = base(
  <>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    <line x1="8" y1="9" x2="16" y2="9" />
    <line x1="8" y1="13" x2="13" y2="13" />
  </>
);

export const IconGraph = base(
  <>
    <circle cx="5" cy="6" r="2.2" />
    <circle cx="19" cy="6" r="2.2" />
    <circle cx="12" cy="12" r="2.2" />
    <circle cx="6" cy="19" r="2.2" />
    <circle cx="18" cy="18" r="2.2" />
    <line x1="6.9" y1="7.2" x2="10.3" y2="10.5" />
    <line x1="17.1" y1="7.2" x2="13.7" y2="10.5" />
    <line x1="10.4" y1="13.7" x2="7.4" y2="17.5" />
    <line x1="13.6" y1="13.7" x2="16.6" y2="16.5" />
  </>
);

export const IconTimeline = base(
  <>
    <circle cx="12" cy="12" r="9" />
    <polyline points="12 7 12 12 15.5 14" />
  </>
);

export const IconPeople = base(
  <>
    <circle cx="9" cy="8" r="3" />
    <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
    <circle cx="18" cy="8.5" r="2.3" />
    <path d="M15.8 14.2c2.6.3 4.7 2.4 4.9 5.1" />
  </>
);

export const IconAction = base(
  <>
    <path d="M9 11l2.5 2.5L20 5" />
    <path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" />
  </>
);

export const IconEvidence = base(
  <>
    <path d="M12 2l8 3.5v6c0 5-3.4 8.4-8 10.5-4.6-2.1-8-5.5-8-10.5v-6z" />
    <polyline points="9 12 11 14 15.5 9.5" />
  </>
);

export const IconUpload = base(
  <>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </>
);

export const IconStatus = base(
  <>
    <path d="M3 12h4l2-7 4 14 2-7h6" />
  </>
);

export const IconArrowRight = base(<path d="M5 12h13M13 6l6 6-6 6" />);

export const IconArrowDown = base(<path d="M12 5v13M6 13l6 6 6-6" />);

export const IconSearch = base(
  <>
    <circle cx="11" cy="11" r="7" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </>
);

export const IconSparkles = base(
  <>
    <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3z" />
    <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z" />
  </>
);

export const IconDatabase = base(
  <>
    <ellipse cx="12" cy="5.5" rx="8" ry="3" />
    <path d="M4 5.5V12c0 1.7 3.6 3 8 3s8-1.3 8-3V5.5" />
    <path d="M4 12v6.5c0 1.7 3.6 3 8 3s8-1.3 8-3V12" />
  </>
);

export const IconMerge = base(
  <>
    <circle cx="6" cy="6" r="2.3" />
    <circle cx="6" cy="18" r="2.3" />
    <circle cx="18" cy="12" r="2.3" />
    <path d="M8 6.5C11 7 13.5 9 15.8 10.7" />
    <path d="M8 17.5C11 17 13.5 15 15.8 13.3" />
  </>
);

export const IconLayers = base(
  <>
    <polygon points="12 2 21 7 12 12 3 7 12 2" />
    <polyline points="3 12 12 17 21 12" />
    <polyline points="3 17 12 22 21 17" />
  </>
);

export const IconCheckCircle = base(
  <>
    <circle cx="12" cy="12" r="9" />
    <polyline points="8 12.5 11 15.5 16 9" />
  </>
);

export const IconAlert = base(
  <>
    <path d="M12 9v4" />
    <path d="M10.3 3.9L1.8 18a1.5 1.5 0 0 0 1.3 2.3h17.8a1.5 1.5 0 0 0 1.3-2.3L13.7 3.9a1.5 1.5 0 0 0-2.6 0z" />
    <circle cx="12" cy="16.5" r="0.5" fill="currentColor" />
  </>
);

export const IconClose = base(
  <>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </>
);

export const IconCopy = base(
  <>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </>
);

export const IconWorkspace = base(
  <>
    <rect x="3" y="4" width="18" height="14" rx="2" />
    <line x1="3" y1="9" x2="21" y2="9" />
    <line x1="8" y1="4" x2="8" y2="9" />
  </>
);

export const IconChevronRight = base(<polyline points="9 6 15 12 9 18" />);

export const IconSend = base(
  <>
    <line x1="12" y1="19" x2="12" y2="5" />
    <polyline points="6 11 12 5 18 11" />
  </>
);

export const IconEntities = base(
  <>
    <circle cx="6" cy="6" r="2" />
    <circle cx="18" cy="6" r="2" />
    <circle cx="12" cy="18" r="2" />
    <circle cx="12" cy="10" r="2" />
    <line x1="7.5" y1="7" x2="10.7" y2="9.1" />
    <line x1="16.5" y1="7" x2="13.3" y2="9.1" />
    <line x1="12" y1="12" x2="12" y2="16" />
  </>
);
