"""Search agent tool definitions in OpenAI function-calling format.

5 tools modeling a realistic search API:
  QU:        query_decompose
  Strategy:  search, get_document, list_documents
  Execution: compare
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

COMPARE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "compare",
        "description": (
            "Compare two or more documents on a specific aspect."
            " Use after retrieving documents when the user needs"
            " cross-document analysis, differences, or trends."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doc_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of document IDs to compare.",
                    "minItems": 2,
                },
                "aspect": {
                    "type": "string",
                    "description": (
                        "The dimension to compare on (e.g."
                        " 'indemnification terms', 'pricing',"
                        " 'effective dates')."
                    ),
                },
            },
            "required": ["doc_ids", "aspect"],
        },
    },
}

ALL_TOOLS: list[dict[str, Any]] = [
    SEARCH_TOOL,
    GET_DOCUMENT_TOOL,
    LIST_DOCUMENTS_TOOL,
    QUERY_DECOMPOSE_TOOL,
    COMPARE_TOOL,
]


def get_tool_names() -> list[str]:
    return [t["function"]["name"] for t in ALL_TOOLS]
