"""Search agent tool definitions in OpenAI function-calling format.

4 tools modeling a realistic search API:
  QU:        query_decompose
  Strategy:  search, get_document, list_documents

Plus 5 distractor tools: 3 categorically wrong (web_search,
tag_document, create_alert) and 2 semantic near-misses
(summarize_document, search_history). All are plausible schemas offered
to models but never the correct answer for any task. They test tool
discrimination (MCPAgentBench pattern).
"""

from __future__ import annotations

from typing import Any

SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Semantic search across the document corpus. Returns ranked"
            " passages matching the query. Use filters to narrow by"
            " metadata (author, type, date range). Defaults to top 5"
            " results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional metadata filters. Flat key-value pairs"
                        ' for exact match (e.g. {"type": "NDA"}).'
                        " For date ranges, use start_date and end_date"
                        ' (e.g. {"start_date": "2024-01-01",'
                        ' "end_date": "2024-12-31"}).'
                    ),
                    "additionalProperties": True,
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return.",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}

GET_DOCUMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_document",
        "description": (
            "Fetch the full content of a specific document by its ID."
            " Use when you already know which document you need, rather"
            " than searching for it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The document identifier.",
                },
            },
            "required": ["doc_id"],
        },
    },
}

LIST_DOCUMENTS_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "list_documents",
        "description": (
            "List available documents with their metadata. Use to"
            " explore what documents exist before committing to a"
            " search query. Optionally filter by metadata fields."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional metadata filters. Same format as"
                        " search filters: flat key-value for exact"
                        " match, start_date/end_date for date ranges."
                    ),
                    "additionalProperties": True,
                },
            },
            "required": [],
        },
    },
}

QUERY_DECOMPOSE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_decompose",
        "description": (
            "Break a complex query into simpler sub-queries that can"
            " be answered independently. Use when the user's question"
            " involves multiple distinct information needs, comparisons"
            " across time periods, or multi-entity lookups."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The complex query to decompose.",
                },
            },
            "required": ["query"],
        },
    },
}

# --- Distractor tools ---
# Never the expected tool for any task. Offered alongside the real tools
# to test whether models can discriminate; descriptions are intentionally
# realistic bait.

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the public web for information that is not contained"
            " in the company's contract repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The web search query.",
                },
            },
            "required": ["query"],
        },
    },
}

TAG_DOCUMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "tag_document",
        "description": (
            "Add or update metadata tags on a document in the contract repository."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The document identifier.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to apply to the document.",
                },
            },
            "required": ["doc_id", "tags"],
        },
    },
}

CREATE_ALERT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_alert",
        "description": (
            "Save a standing search query against the contract"
            " repository; the legal team is notified when new or amended"
            " documents match it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The standing search query to save.",
                },
                "frequency": {
                    "type": "string",
                    "enum": ["daily", "weekly"],
                    "description": "How often matches are checked.",
                },
            },
            "required": ["query"],
        },
    },
}

# --- Semantic near-miss distractors ---
# Closer bait than the categorical distractors above: schemas that mirror
# the real tools but are still never correct. summarize_document returns
# generated text instead of retrieving source text (this harness scores
# retrieval strategy; in a contracts corpus the authoritative language
# comes from get_document). search_history searches prior interactions
# instead of the corpus (in chain tasks the prior context is already in
# the conversation).

SUMMARIZE_DOCUMENT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "summarize_document",
        "description": (
            "Produce a concise summary of a document's contents,"
            " optionally focused on a particular topic or clause type."
            " Returns a generated summary rather than the document's"
            " actual text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doc_id": {
                    "type": "string",
                    "description": "The document identifier.",
                },
                "focus": {
                    "type": "string",
                    "description": (
                        "Optional topic or clause type to focus the summary on."
                    ),
                },
            },
            "required": ["doc_id"],
        },
    },
}

SEARCH_HISTORY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_history",
        "description": (
            "Search your previous searches and document views in this"
            " workspace, rather than the document corpus. Use to recall"
            " what was searched for or retrieved in earlier sessions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The history search query.",
                },
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional metadata filters. Same format as"
                        " search filters: flat key-value for exact"
                        " match, start_date/end_date for date ranges."
                    ),
                    "additionalProperties": True,
                },
            },
            "required": [],
        },
    },
}

SEARCH_TOOLS: list[dict[str, Any]] = [
    SEARCH_TOOL,
    GET_DOCUMENT_TOOL,
    LIST_DOCUMENTS_TOOL,
    QUERY_DECOMPOSE_TOOL,
]

DISTRACTOR_TOOLS: list[dict[str, Any]] = [
    WEB_SEARCH_TOOL,
    TAG_DOCUMENT_TOOL,
    CREATE_ALERT_TOOL,
    SUMMARIZE_DOCUMENT_TOOL,
    SEARCH_HISTORY_TOOL,
]

# What the runner passes to models: real tools plus distractors.
ALL_TOOLS: list[dict[str, Any]] = SEARCH_TOOLS + DISTRACTOR_TOOLS


def get_tool_names() -> list[str]:
    return [t["function"]["name"] for t in ALL_TOOLS]


def get_search_tool_names() -> list[str]:
    return [t["function"]["name"] for t in SEARCH_TOOLS]
