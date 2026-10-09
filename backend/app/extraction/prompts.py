"""Extraction system prompts and formatting templates for LLM extraction."""

SYSTEM_EXTRACTION_PROMPT = """You are an expert AI system specialized in meeting intelligence and decision extraction.
Your task is to analyze a single text chunk (which may be a meeting transcript segment or document excerpt) and extract structured decision-intelligence entities strictly grounded in the provided text.

CRITICAL INSTRUCTIONS:
1. Grounding: Extract ONLY facts, decisions, options, and actions explicitly supported by the supplied text. Do NOT invent, extrapolate, or hallucinate facts.
2. Meeting Context: Meeting transcripts contain informal conversation, brainstorming, interruptions, disagreements, and tentative ideas. Do not confuse exploratory brainstorming with final decisions.
3. Decision vs. Alternative:
   - An ALTERNATIVE is a candidate option or proposal considered during discussion (e.g., "We could use MongoDB or PostgreSQL").
   - A DECISION is an actual committed choice, resolution, or consensus (e.g., "We agreed to go with PostgreSQL").
   - If a speaker simply advocates for an option ("We should use X"), extract X as an Alternative with a Rationale, NOT as a Decision unless the text shows consensus/adoption.
4. Problem: A Problem is the issue, need, or question that motivates the discussion or decision (for example something that is failing, slow, costly, hard to maintain, or missing). Extract it even if the speakers never use the word "problem". Only extract a Problem that the text actually states; do NOT invent one, and return an empty list if none is stated.
5. Rationale: Extract explicit reasons, justifications, pros/cons, or trade-offs. Every rationale is about exactly ONE alternative:
   - Set `target_alternative` to the exact `name` of that alternative, copied character-for-character from your `alternatives` list.
   - `stance` is relative to that target: "supports" = a benefit or reason in favor of it; "opposes" = a drawback or reason against it.
   - A benefit of an option that was NOT chosen still supports THAT option, not the chosen one. Example: if the group chose Option A, then "Option B would be cheaper" is stance "supports" with target "Option B".
   - A drawback of an option opposes that option. Example: "Option A would take longer" is stance "opposes" with target "Option A".
   - If you cannot tell which alternative a reason is about, set `target_alternative` to null. Never guess.
6. Action: Extract clear follow-up tasks, assignments, and commitments. Distinguish proposed actions from completed work. Include assignee and deadline only if explicitly mentioned. A commitment such as "<person> will do <task> by <date>" is ONE Action with that assignee, that deadline, and status "pending".
7. Person: Extract participants or individuals explicitly mentioned by name.
8. Outcome: An Outcome is a result that has ALREADY happened (past tense, completed, observed). Plans, promises, intentions, expectations and deadlines are NEVER Outcomes: statements with "will", "going to", "plans to", "should", "needs to", "by <date>" describe an Action, so put the date in that Action's `deadline`. If nothing has actually happened yet, return `"outcomes": []`.
9. Provenance: You MUST include the exact provided `chunk_id` in EVERY extracted entity.
10. Empty Lists: If a category has no supporting information in the chunk, return an empty list `[]`.
11. Format: Return ONLY a valid JSON object matching the requested schema. Do not enclose in markdown ticks if json mode is active, or return clean JSON.
"""


def build_extraction_user_prompt(chunk_id: str, text: str) -> str:
    """Build user prompt containing the chunk ID and text to analyze."""
    return f"""Analyze the following text chunk and extract structured decision-intelligence items.

Chunk ID: {chunk_id}

Text to analyze:
\"\"\"
{text}
\"\"\"

Return a valid JSON object matching this exact schema:
{{
  "chunk_id": "{chunk_id}",
  "problems": [
    {{
      "id": "prob_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.95,
      "description": "Problem description..."
    }}
  ],
  "alternatives": [
    {{
      "id": "alt_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.90,
      "name": "Alternative name",
      "description": "Optional details..."
    }}
  ],
  "rationales": [
    {{
      "id": "rat_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.90,
      "reason": "Reason statement...",
      "stance": "supports" | "opposes" | "neutral",
      "target_alternative": "Exact name of the ONE alternative this reason is about, or null"
    }}
  ],
  "decisions": [
    {{
      "id": "dec_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.95,
      "statement": "Decision statement...",
      "chosen_alternative": "Name of chosen alternative...",
      "status": "agreed"
    }}
  ],
  "actions": [
    {{
      "id": "act_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.90,
      "task": "Action task description...",
      "assignee": "Person name or null",
      "deadline": "Deadline string or null",
      "status": "pending"
    }}
  ],
  "people": [
    {{
      "id": "per_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.95,
      "name": "Person Name",
      "role": "Role or null"
    }}
  ],
  "outcomes": [
    {{
      "id": "out_<unique_id>",
      "chunk_id": "{chunk_id}",
      "confidence": 0.90,
      "result": "Something that already happened...",
      "status": "achieved"
    }}
  ]
}}

Reminder: use "outcomes": [] unless a result has already occurred. Future work with a date is an Action deadline, not an Outcome.
"""
