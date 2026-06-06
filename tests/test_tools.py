from __future__ import annotations

from src.tools import ALL_TOOLS, get_tool_names


def test_all_tools_count() -> None:
    assert len(ALL_TOOLS) == 5


def test_get_tool_names() -> None:
    expected = [
        "search",
        "get_document",
        "list_documents",
        "query_decompose",
        "compare",
    ]
    assert get_tool_names() == expected


def test_all_tools_have_valid_schema() -> None:
    for tool in ALL_TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_search_tool_has_query_required() -> None:
    fn = ALL_TOOLS[0]["function"]
    assert fn["name"] == "search"
    assert "query" in fn["parameters"]["required"]
    assert "filters" not in fn["parameters"]["required"]
    assert "top_k" not in fn["parameters"]["required"]


def test_search_tool_top_k_default() -> None:
    top_k = ALL_TOOLS[0]["function"]["parameters"]["properties"]["top_k"]
    assert top_k["default"] == 5


def test_compare_tool_requires_min_two_docs() -> None:
    doc_ids = ALL_TOOLS[4]["function"]["parameters"]["properties"]["doc_ids"]
    assert doc_ids["minItems"] == 2
