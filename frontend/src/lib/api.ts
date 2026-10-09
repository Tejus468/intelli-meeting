/**
 * Typed API Client for the Intelligent Meeting & Decision Intelligence System.
 * Connects the Next.js frontend to the FastAPI backend services.
 */

// ---------------------------------------------------------------------------
// 1. Data Models (mirrors FastAPI / Pydantic schemas)
// ---------------------------------------------------------------------------

export interface IngestionResponse {
  source_id: string;
  source_type: string;
  title: string;
  number_of_chunks: number;
  status: string;
  decision_ids: string[];
}

export interface SourceSummary {
  source_id: string;
  title: string;
  source_type: string;
  source_date: string | null;
  created_at: string | null;
  number_of_chunks: number;
  decision_ids: string[];
}

export interface DeleteSourceResponse {
  source_id: string;
  status: string;
}

export interface QuestionRequest {
  question: string;
  top_k?: number;
}

export interface SourceReference {
  source_id?: string | null;
  chunk_id?: string | null;
  title?: string | null;
  page?: number | null;
  speaker?: string | null;
  start_ts?: string | null;
  end_ts?: string | null;
  relevance_score: number;
}

export interface AnswerResponse {
  question: string;
  answer: string;
  sources: SourceReference[];
  evidence_count: number;
}

export type TimelineEventType =
  | "problem"
  | "alternative"
  | "rationale"
  | "decision"
  | "action"
  | "outcome"
  | string;

export interface TimelineEvent {
  event_type: TimelineEventType;
  event_id: string;
  label: string;
  description: string;
  source_id?: string | null;
  chunk_id?: string | null;
  source_title?: string | null;
  source_date?: string | null;
  page?: number | null;
  speaker?: string | null;
  start_ts?: string | number | null;
  end_ts?: string | number | null;
  status?: string | null;
}

export interface DecisionTimeline {
  decision_id: string;
  decision_statement: string;
  decision_status?: string | null;
  events: TimelineEvent[];
}

export interface GraphNode {
  id: string;
  node_type: string;
  label: string;
  properties: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relationship: string;
  properties: Record<string, any>;
}

export interface DecisionGraph {
  decision_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// 2. Error Handling
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  status: number;
  statusText: string;
  data?: any;

  constructor(message: string, status: number, statusText: string, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.statusText = statusText;
    this.data = data;
  }
}

// ---------------------------------------------------------------------------
// 3. Request Helper
// ---------------------------------------------------------------------------

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000";

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  const defaultHeaders: Record<string, string> = {};
  if (!(options.body instanceof FormData)) {
    defaultHeaders["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    let responseData: any = null;

    try {
      responseData = await response.json();
      if (responseData?.detail) {
        errorDetail =
          typeof responseData.detail === "string"
            ? responseData.detail
            : JSON.stringify(responseData.detail);
      }
    } catch {
      // Body is not JSON
    }

    throw new ApiError(
      errorDetail || `API request failed with status ${response.status}`,
      response.status,
      response.statusText,
      responseData
    );
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// 4. Client Endpoints
// ---------------------------------------------------------------------------

/**
 * Upload a TXT, PDF, or DOCX document to extract, chunk, and persist provenance.
 * POST /api/ingestion/upload
 */
export async function uploadDocument(file: File): Promise<IngestionResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return request<IngestionResponse>("/api/ingestion/upload", {
    method: "POST",
    body: formData,
  });
}

/**
 * List persisted sources (newest first) with chunk counts from PostgreSQL.
 * GET /api/ingestion/sources
 */
export async function listSources(): Promise<SourceSummary[]> {
  return request<SourceSummary[]>("/api/ingestion/sources", {
    method: "GET",
  });
}

/**
 * Permanently remove a source and its chunks, embeddings and knowledge-graph data.
 * DELETE /api/ingestion/sources/{source_id}
 */
export async function deleteSource(sourceId: string): Promise<DeleteSourceResponse> {
  return request<DeleteSourceResponse>(
    `/api/ingestion/sources/${encodeURIComponent(sourceId)}`,
    { method: "DELETE" }
  );
}

/**
 * Ask a natural language question grounded in hybrid vector + graph evidence.
 * POST /api/qa/ask
 */
export async function askQuestion(
  req: QuestionRequest
): Promise<AnswerResponse> {
  return request<AnswerResponse>("/api/qa/ask", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/**
 * Retrieve the full chronological context and evolution of a specific decision from Neo4j.
 * GET /api/timeline/decisions/{decision_id}
 */
export async function getDecisionTimeline(
  decisionId: string
): Promise<DecisionTimeline> {
  const encodedId = encodeURIComponent(decisionId.trim());
  return request<DecisionTimeline>(`/api/timeline/decisions/${encodedId}`, {
    method: "GET",
  });
}

/**
 * Retrieve the connected context and provenance graph for a given decision.
 * GET /api/graph/decisions/{decision_id}
 */
export async function getDecisionGraph(
  decisionId: string
): Promise<DecisionGraph> {
  const encodedId = encodeURIComponent(decisionId.trim());
  return request<DecisionGraph>(`/api/graph/decisions/${encodedId}`, {
    method: "GET",
  });
}
