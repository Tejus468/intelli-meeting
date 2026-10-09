"""System prompts and prompt formatting templates for evidence-backed Q&A."""
from typing import List, Optional
from app.retrieval.models import DecisionContext, EvidenceItem

QA_SYSTEM_PROMPT = """You are an accurate, factual AI assistant specializing in meeting intelligence and decision intelligence.
Your task is to answer the user's question STRICTLY and ONLY based on the retrieved evidence provided below.

CRITICAL INSTRUCTIONS:
1. Grounding & Strict Truthfulness: Answer ONLY using facts explicitly stated in the provided evidence. Do NOT invent, extrapolate, speculate, or hallucinate.
2. Insufficient Evidence: If the provided evidence does not contain enough information to answer the question with certainty, state clearly: "The available meeting and document evidence is insufficient to answer this question."
3. Distinguish Statuses:
   - Distinguish agreed DECISIONS from tentative proposals, exploratory brainstorming, or general discussions.
   - Distinguish PLANNED actions from COMPLETED actions.
   - Do NOT claim an alternative was rejected unless explicit evidence confirms rejection.
   - The structured decision context labels each alternative SELECTED, REJECTED, or CONSIDERED. CONSIDERED means it was discussed but is not recorded as selected or rejected: never call a CONSIDERED alternative "rejected".
   - Do NOT claim an action was completed unless explicit evidence confirms completion.
4. Explanations & Rationales: When explaining why a decision was made, cite the specific reasons, trade-offs, or alternatives mentioned in the evidence.
5. Exact Attribution: Preserve explicit names of people, deadlines, dates, and status values as stated in the evidence. Do not infer causality or connections not directly asserted in the text.
6. Conciseness: Provide a direct, well-structured, and factual response. Do not include unnecessary conversational filler.
7. Options that were not chosen: If asked why an alternative was not selected, answer from the rationales: first the reason(s) given in favor of that alternative (why it was considered), then the reason(s) given for the option that was selected (why it was preferred), each as stated in the evidence. Say "not selected" rather than "rejected" unless the evidence explicitly says it was rejected. If the evidence gives no reason, use the insufficient-evidence statement from instruction 2.
8. Structured decision context: When present, use it to match each rationale to the alternative it supports or opposes. Use it only when it is relevant to the question; it never makes an unrelated question answerable.
"""


def format_evidence_block(evidence: List[EvidenceItem]) -> str:
    """Format a list of retrieved evidence items into a clean, compact context block."""
    if not evidence:
        return "No evidence retrieved."

    lines: List[str] = []
    for idx, item in enumerate(evidence, start=1):
        header_parts = [
            f"[Evidence #{idx}] Type: {item.evidence_type.upper()}",
            f"Method: {item.retrieval_method}",
            f"Score: {item.score:.2f}",
        ]
        lines.append(" | ".join(header_parts))

        prov_parts = []
        if item.source_id:
            prov_parts.append(f"Source ID: {item.source_id}")
        if item.chunk_id:
            prov_parts.append(f"Chunk ID: {item.chunk_id}")
        if item.node_id:
            prov_parts.append(f"Entity ID: {item.node_id}")

        meta = item.metadata or {}
        if meta.get("speaker"):
            prov_parts.append(f"Speaker: {meta['speaker']}")
        if meta.get("start_ts"):
            prov_parts.append(f"Time: {meta['start_ts']}")
        if meta.get("page") is not None:
            prov_parts.append(f"Page: {meta['page']}")
        if meta.get("status"):
            prov_parts.append(f"Status: {meta['status']}")
        if meta.get("assignee"):
            prov_parts.append(f"Assignee: {meta['assignee']}")
        if meta.get("deadline"):
            prov_parts.append(f"Deadline: {meta['deadline']}")
        if meta.get("stance"):
            prov_parts.append(f"Stance: {meta['stance']}")

        if prov_parts:
            lines.append("Provenance: " + " | ".join(prov_parts))

        lines.append(f"Content: {item.text.strip()}")
        lines.append("")  # Blank line separator

    return "\n".join(lines).strip()


def _alternative_label(name: str, ctx: DecisionContext) -> str:
    if name in ctx.selected_alternatives:
        return "SELECTED"
    if name in ctx.rejected_alternatives:
        return "REJECTED"
    if ctx.selected_alternatives:
        return "CONSIDERED (discussed, but a different option was selected; no explicit rejection recorded)"
    return "CONSIDERED (discussed; no selection recorded)"


def format_decision_context(contexts: List[DecisionContext]) -> str:
    """Render decisions with their alternatives and rationale-to-alternative links as plain text."""
    lines: List[str] = []
    for ctx in contexts:
        header = f'[Decision {ctx.decision_id}] "{ctx.statement}"'
        if ctx.status:
            header += f" (status: {ctx.status})"
        lines.append(header)
        for problem in ctx.problems:
            lines.append(f"  Problem: {problem}")
        if ctx.considered_alternatives:
            lines.append("  Alternatives:")
            for name in ctx.considered_alternatives:
                lines.append(f"    - {name} -- {_alternative_label(name, ctx)}")
        if ctx.rationales:
            lines.append("  Rationales (each is about the alternative named):")
            for rationale in ctx.rationales:
                targets = ", ".join(f'"{t}"' for t in rationale.target_alternatives) or "no specific alternative"
                lines.append(f"    - {rationale.stance.upper()} {targets}: {rationale.reason}")
        lines.append("")
    return chr(10).join(lines).strip()


def build_qa_user_prompt(
    question: str,
    evidence: List[EvidenceItem],
    decision_context: Optional[List[DecisionContext]] = None,
) -> str:
    """Construct user prompt combining retrieved evidence context and the user query."""
    context_str = format_evidence_block(evidence)
    structured_section = ""
    if decision_context:
        structured_section = f"""

Structured decision context (from the knowledge graph):
==================================================
{format_decision_context(decision_context)}
=================================================="""
    return f"""Retrieved Evidence:
==================================================
{context_str}
=================================================={structured_section}

User Question:
{question}

Answer:"""
