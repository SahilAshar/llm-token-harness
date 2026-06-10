from __future__ import annotations

from src.tools import (
    ALL_TOOLS,
    DISTRACTOR_TOOLS,
    SEARCH_TOOLS,
    get_search_tool_names,
    get_tool_names,
)


def test_all_tools_count() -> None:
    assert len(SEARCH_TOOLS) == 4
    assert len(DISTRACTOR_TOOLS) == 3
    assert len(ALL_TOOLS) == 7


def test_all_tools_is_search_plus_distractors() -> None:
    assert ALL_TOOLS == SEARCH_TOOLS + DISTRACTOR_TOOLS


def test_no_name_collisions() -> None:
    names = get_tool_names()
    assert len(names) == len(set(names))


def test_get_tool_names() -> None:
    expected = [
        "search",
        "get_document",
        "list_documents",
        "query_decompose",
        "web_search",
        "tag_document",
        "create_alert",
    ]
    assert get_tool_names() == expected


def test_get_search_tool_names() -> None:
    expected = [
        "search",
        "get_document",
        "list_documents",
        "query_decompose",
    ]
    assert get_search_tool_names() == expected


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


def test_web_search_tool_params() -> None:
    fn = DISTRACTOR_TOOLS[0]["function"]
    assert fn["name"] == "web_search"
    assert "query" in fn["parameters"]["properties"]
    assert fn["parameters"]["required"] == ["query"]


def test_tag_document_tool_params() -> None:
    fn = DISTRACTOR_TOOLS[1]["function"]
    assert fn["name"] == "tag_document"
    props = fn["parameters"]["properties"]
    assert props["doc_id"]["type"] == "string"
    assert props["tags"]["type"] == "array"
    assert props["tags"]["items"] == {"type": "string"}
    assert fn["parameters"]["required"] == ["doc_id", "tags"]


def test_create_alert_tool_params() -> None:
    fn = DISTRACTOR_TOOLS[2]["function"]
    assert fn["name"] == "create_alert"
    props = fn["parameters"]["properties"]
    assert props["query"]["type"] == "string"
    assert props["frequency"]["enum"] == ["daily", "weekly"]
    assert fn["parameters"]["required"] == ["query"]
