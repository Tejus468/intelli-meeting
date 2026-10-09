/** Link to the existing Decision Explorer for a real, persisted decision ID. */
export function decisionExplorerHref(decisionId: string): string {
  return `/decisions?id=${encodeURIComponent(decisionId)}`;
}

/** Read the decision ID from a query string such as "?id=dec_abc123"; null if absent or blank. */
export function decisionIdFromSearch(search: string): string | null {
  const id = new URLSearchParams(search).get("id");
  return id && id.trim() ? id.trim() : null;
}
