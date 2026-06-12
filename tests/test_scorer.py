from __future__ import annotations

from src.adapters.base import ToolCall
from src.scorer import score_task
from src.tasks import ArgMatchType, ExpectedArg, ExpectedCall, Task


def _make_task(
    tool: str = "search",
    args: list[ExpectedArg] | None = None,
    alternatives: list[ExpectedCall] | None = None,
) -> Task:
    return Task(
        task_id="test_01",
        scenario_id="test",
        step=1,
        description="Test task",
        messages=[{"role": "user", "content": "test"}],
        expected_tool=tool,
        expected_args=args or [],
        expected_alternatives=alternatives or [],
    )


class TestScoreTask:
    def test_no_tool_calls(self) -> None:
        task = _make_task()
        result = score_task(task, [])
        assert result.score == 0
        assert result.actual_tool == ""
        assert result.actual_tools == []

    def test_wrong_tool(self) -> None:
        task = _make_task(tool="search")
        result = score_task(task, [ToolCall(name="get_document")])
        assert result.score == 0
        assert result.actual_tool == "get_document"

    def test_right_tool_no_args(self) -> None:
        task = _make_task(tool="search")
        result = score_task(task, [ToolCall(name="search")])
        assert result.score == 1

    def test_exact_match_string(self) -> None:
        task = _make_task(
            tool="get_document",
            args=[
                ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
            ],
        )
        result = score_task(
            task,
            [ToolCall(name="get_document", arguments={"doc_id": "doc_3"})],
        )
        assert result.score == 1
        assert result.matched_args == ["doc_id"]

    def test_exact_match_case_insensitive(self) -> None:
        task = _make_task(
            tool="get_document",
            args=[
                ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
            ],
        )
        result = score_task(
            task,
            [ToolCall(name="get_document", arguments={"doc_id": "DOC_3"})],
        )
        assert result.score == 1

    def test_exact_match_int(self) -> None:
        task = _make_task(
            tool="search",
            args=[ExpectedArg(name="top_k", match_type=ArgMatchType.EXACT, value=10)],
        )
        result = score_task(
            task,
            [ToolCall(name="search", arguments={"top_k": 10})],
        )
        assert result.score == 1

    def test_exact_match_wrong_value(self) -> None:
        task = _make_task(
            tool="get_document",
            args=[
                ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
            ],
        )
        result = score_task(
            task,
            [ToolCall(name="get_document", arguments={"doc_id": "doc_7"})],
        )
        assert result.score == 0
        assert result.failed_args == ["doc_id"]

    def test_keyword_match(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="query",
                    match_type=ArgMatchType.KEYWORDS,
                    value=["indemnification"],
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"query": "indemnification clauses in contracts"},
                )
            ],
        )
        assert result.score == 1

    def test_keyword_match_case_insensitive(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="query", match_type=ArgMatchType.KEYWORDS, value=["NDA"]
                ),
            ],
        )
        result = score_task(
            task,
            [ToolCall(name="search", arguments={"query": "nda agreements"})],
        )
        assert result.score == 1

    def test_keyword_match_multiple_keywords(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="query",
                    match_type=ArgMatchType.KEYWORDS,
                    value=["indemnification", "2024"],
                ),
            ],
        )
        good = ToolCall(
            name="search",
            arguments={"query": "indemnification clauses from 2024"},
        )
        bad = ToolCall(
            name="search",
            arguments={"query": "indemnification clauses"},
        )
        assert score_task(task, [good]).score == 1
        assert score_task(task, [bad]).score == 0

    def test_keyword_match_missing_keyword(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="query",
                    match_type=ArgMatchType.KEYWORDS,
                    value=["indemnification"],
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"query": "contract liability terms"},
                )
            ],
        )
        assert result.score == 0

    def test_missing_arg(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="query", match_type=ArgMatchType.KEYWORDS, value=["NDA"]
                ),
                ExpectedArg(name="top_k", match_type=ArgMatchType.EXACT, value=10),
            ],
        )
        result = score_task(
            task,
            [ToolCall(name="search", arguments={"query": "NDA docs"})],
        )
        assert result.score == 0
        assert "query" in result.matched_args
        assert "top_k" in result.failed_args

    def test_all_or_nothing(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="query", match_type=ArgMatchType.KEYWORDS, value=["NDA"]
                ),
                ExpectedArg(name="top_k", match_type=ArgMatchType.EXACT, value=10),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"query": "NDA docs", "top_k": 5},
                )
            ],
        )
        assert result.score == 0
        assert result.matched_args == ["query"]
        assert result.failed_args == ["top_k"]

    def test_batch_any_match_first_call(self) -> None:
        task = _make_task(tool="search")
        result = score_task(
            task,
            [ToolCall(name="search"), ToolCall(name="get_document")],
        )
        assert result.score == 1
        assert result.actual_tool == "search"
        assert result.actual_tools == ["search", "get_document"]

    def test_batch_any_match_second_call(self) -> None:
        task = _make_task(
            tool="get_document",
            args=[
                ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(name="search", arguments={"query": "doc_3 contents"}),
                ToolCall(name="get_document", arguments={"doc_id": "doc_3"}),
            ],
        )
        assert result.score == 1
        assert result.actual_tool == "get_document"
        assert result.actual_tools == ["search", "get_document"]
        assert result.matched_args == ["doc_id"]

    def test_batch_right_name_wrong_args_then_full_match(self) -> None:
        task = _make_task(
            tool="get_document",
            args=[
                ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(name="get_document", arguments={"doc_id": "doc_7"}),
                ToolCall(name="get_document", arguments={"doc_id": "doc_3"}),
            ],
        )
        assert result.score == 1
        assert result.actual_tool == "get_document"
        assert result.actual_tools == ["get_document", "get_document"]
        assert result.matched_args == ["doc_id"]
        assert result.failed_args == []

    def test_batch_right_name_bad_args_everywhere(self) -> None:
        task = _make_task(
            tool="get_document",
            args=[
                ExpectedArg(name="doc_id", match_type=ArgMatchType.EXACT, value="doc_3")
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(name="get_document", arguments={"doc_id": "doc_7"}),
                ToolCall(name="get_document", arguments={"doc_id": "doc_12"}),
            ],
        )
        assert result.score == 0
        assert result.actual_tool == "get_document"
        assert result.actual_tools == ["get_document", "get_document"]
        assert result.failed_args == ["doc_id"]

    def test_exact_match_dict_key_order_insensitive(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="filters",
                    match_type=ArgMatchType.EXACT,
                    value={"start_date": "2024-01-01", "end_date": "2024-12-31"},
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={
                        "filters": {
                            "end_date": "2024-12-31",
                            "start_date": "2024-01-01",
                        }
                    },
                )
            ],
        )
        assert result.score == 1

    def test_exact_match_dict_wrong_value(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="filters",
                    match_type=ArgMatchType.EXACT,
                    value={"type": "NDA"},
                ),
            ],
        )
        result = score_task(
            task,
            [ToolCall(name="search", arguments={"filters": {"type": "MSA"}})],
        )
        assert result.score == 0

    def test_exact_match_dict_extra_key(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="filters",
                    match_type=ArgMatchType.EXACT,
                    value={"type": "NDA"},
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"filters": {"type": "NDA", "author": "Smith"}},
                )
            ],
        )
        assert result.score == 0

    def test_exact_match_nested_dict_values(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="filters",
                    match_type=ArgMatchType.EXACT,
                    value={"type": "NDA", "year": 2024},
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"filters": {"year": 2024, "type": "nda"}},
                )
            ],
        )
        assert result.score == 1

    def test_exact_match_list_order_insensitive(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="doc_ids",
                    match_type=ArgMatchType.EXACT,
                    value=["doc_3", "doc_7"],
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"doc_ids": ["DOC_7", "doc_3"]},
                )
            ],
        )
        assert result.score == 1

    def test_exact_match_list_wrong_element(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="doc_ids",
                    match_type=ArgMatchType.EXACT,
                    value=["doc_3", "doc_7"],
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"doc_ids": ["doc_3", "doc_12"]},
                )
            ],
        )
        assert result.score == 0

    def test_exact_match_list_length_mismatch(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="doc_ids",
                    match_type=ArgMatchType.EXACT,
                    value=["doc_3", "doc_7"],
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"doc_ids": ["doc_3", "doc_7", "doc_12"]},
                )
            ],
        )
        assert result.score == 0

    def test_exact_match_list_multiset_semantics(self) -> None:
        task = _make_task(
            tool="search",
            args=[
                ExpectedArg(
                    name="doc_ids",
                    match_type=ArgMatchType.EXACT,
                    value=["doc_3", "doc_3"],
                ),
            ],
        )
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"doc_ids": ["doc_3", "doc_7"]},
                )
            ],
        )
        assert result.score == 0


class TestExpectedAlternatives:
    _ALTERNATIVE = ExpectedCall(
        tool="search",
        args=[
            ExpectedArg(
                name="query", match_type=ArgMatchType.KEYWORDS, value=["auto-renew"]
            ),
            ExpectedArg(
                name="filters",
                match_type=ArgMatchType.EXACT,
                value={"type": "vendor_agreement"},
            ),
        ],
    )

    def _make_task_with_alternative(self) -> Task:
        return _make_task(
            tool="list_documents",
            args=[
                ExpectedArg(
                    name="filters",
                    match_type=ArgMatchType.EXACT,
                    value={"type": "vendor_agreement"},
                ),
            ],
            alternatives=[self._ALTERNATIVE],
        )

    def test_no_alternatives_scores_as_before(self) -> None:
        task = _make_task(
            tool="list_documents",
            args=[
                ExpectedArg(
                    name="filters",
                    match_type=ArgMatchType.EXACT,
                    value={"type": "vendor_agreement"},
                ),
            ],
        )
        good = ToolCall(
            name="list_documents", arguments={"filters": {"type": "vendor_agreement"}}
        )
        bad = ToolCall(
            name="search",
            arguments={
                "query": "auto-renew",
                "filters": {"type": "vendor_agreement"},
            },
        )
        assert score_task(task, [good]).score == 1
        assert score_task(task, [bad]).score == 0

    def test_primary_match_still_scores(self) -> None:
        task = self._make_task_with_alternative()
        result = score_task(
            task,
            [
                ToolCall(
                    name="list_documents",
                    arguments={"filters": {"type": "vendor_agreement"}},
                )
            ],
        )
        assert result.score == 1
        assert result.actual_tool == "list_documents"

    def test_primary_fails_alternative_matches(self) -> None:
        task = self._make_task_with_alternative()
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={
                        "query": "vendor agreements with auto-renewal",
                        "filters": {"type": "vendor_agreement"},
                    },
                )
            ],
        )
        assert result.score == 1
        assert result.actual_tool == "search"
        assert result.matched_args == ["query", "filters"]
        assert result.failed_args == []

    def test_primary_and_alternatives_all_fail(self) -> None:
        task = self._make_task_with_alternative()
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={"query": "vendor agreements with auto-renewal"},
                )
            ],
        )
        assert result.score == 0
        # Failure reporting stays anchored to the primary expectation.
        assert result.expected_tool == "list_documents"
        assert result.failed_args == ["filters"]

    def test_partial_alternative_match_no_credit(self) -> None:
        task = self._make_task_with_alternative()
        result = score_task(
            task,
            [
                ToolCall(
                    name="search",
                    arguments={
                        "query": "renewal terms",
                        "filters": {"type": "vendor_agreement"},
                    },
                )
            ],
        )
        assert result.score == 0


def _make_parallel_task(specs: list[ExpectedCall]) -> Task:
    return Task(
        task_id="parallel_01",
        scenario_id="parallel",
        step=1,
        description="Parallel test task",
        messages=[{"role": "user", "content": "test"}],
        expected_tool="",
        expected_args=[],
        expected_parallel=specs,
    )


class TestExpectedParallel:
    _SPECS = [
        ExpectedCall(
            tool="search",
            args=[
                ExpectedArg(
                    name="query",
                    match_type=ArgMatchType.KEYWORDS,
                    value=["halverson"],
                ),
            ],
        ),
        ExpectedCall(
            tool="search",
            args=[
                ExpectedArg(
                    name="query",
                    match_type=ArgMatchType.KEYWORDS,
                    value=["apex"],
                ),
            ],
        ),
    ]
    _HALVERSON = ToolCall(
        name="search", arguments={"query": "halverson indemnification"}
    )
    _APEX = ToolCall(name="search", arguments={"query": "apex liability caps"})

    def test_all_specs_matched(self) -> None:
        task = _make_parallel_task(self._SPECS)
        result = score_task(task, [self._HALVERSON, self._APEX])
        assert result.score == 1
        assert result.parallel_expected == 2
        assert result.parallel_matched == 2
        assert result.parallel_failed_specs == []
        assert result.expected_tool == "search + search"
        assert result.actual_tools == ["search", "search"]

    def test_call_order_does_not_matter(self) -> None:
        task = _make_parallel_task(self._SPECS)
        assert score_task(task, [self._APEX, self._HALVERSON]).score == 1

    def test_partial_batch_no_credit(self) -> None:
        task = _make_parallel_task(self._SPECS)
        result = score_task(task, [self._HALVERSON])
        assert result.score == 0
        assert result.parallel_expected == 2
        assert result.parallel_matched == 1
        assert result.parallel_failed_specs == ["1:search"]

    def test_no_tool_calls(self) -> None:
        task = _make_parallel_task(self._SPECS)
        result = score_task(task, [])
        assert result.score == 0
        assert result.parallel_matched == 0
        assert result.actual_tool == ""
        assert result.parallel_failed_specs == ["0:search", "1:search"]

    def test_right_tools_wrong_args_no_credit(self) -> None:
        task = _make_parallel_task(self._SPECS)
        result = score_task(
            task,
            [
                self._HALVERSON,
                ToolCall(name="search", arguments={"query": "stonebridge nda"}),
            ],
        )
        assert result.score == 0
        assert result.parallel_matched == 1

    def test_extra_calls_do_not_hurt(self) -> None:
        task = _make_parallel_task(self._SPECS)
        result = score_task(
            task,
            [
                ToolCall(name="list_documents"),
                self._HALVERSON,
                self._APEX,
            ],
        )
        assert result.score == 1

    def test_mixed_tool_specs(self) -> None:
        task = _make_parallel_task(
            [
                self._SPECS[0],
                ExpectedCall(
                    tool="get_document",
                    args=[
                        ExpectedArg(
                            name="doc_id",
                            match_type=ArgMatchType.EXACT,
                            value="doc_3",
                        ),
                    ],
                ),
            ]
        )
        good = [
            self._HALVERSON,
            ToolCall(name="get_document", arguments={"doc_id": "doc_3"}),
        ]
        result = score_task(task, good)
        assert result.score == 1
        assert result.expected_tool == "search + get_document"
        bad = [self._HALVERSON, self._APEX]
        assert score_task(task, bad).score == 0

    def test_one_call_cannot_satisfy_two_specs(self) -> None:
        # A single combined search containing both specs' keywords is
        # NOT parallel invocation — matching is injective.
        task = _make_parallel_task(self._SPECS)
        combined = ToolCall(
            name="search", arguments={"query": "halverson apex indemnification"}
        )
        result = score_task(task, [combined])
        assert result.score == 0
        assert result.parallel_matched == 1
        assert result.parallel_failed_specs == ["1:search"]

    def test_matching_reroutes_around_greedy_collision(self) -> None:
        # Spec 0 (halverson) matches both calls and is assigned first;
        # spec 1 (apex) matches ONLY the combined call. The matcher
        # must reroute spec 0 onto the halverson-only call so spec 1
        # can take the combined one — first-fit greedy would score 0.
        task = _make_parallel_task(self._SPECS)
        combined = ToolCall(
            name="search", arguments={"query": "halverson apex indemnification"}
        )
        halverson_only = ToolCall(
            name="search", arguments={"query": "halverson contract terms"}
        )
        result = score_task(task, [combined, halverson_only])
        assert result.score == 1
        assert result.parallel_matched == 2

    def test_single_call_tasks_have_no_parallel_fields(self) -> None:
        task = _make_task(tool="search")
        result = score_task(task, [ToolCall(name="search")])
        assert result.parallel_expected is None
        assert result.parallel_matched is None
        assert result.parallel_failed_specs is None
