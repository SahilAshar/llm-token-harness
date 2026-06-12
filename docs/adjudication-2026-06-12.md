# Adjudication memo — 2026-06-12

Two tasks from the hardened 23-task run (12 configs) were flagged by both
the run insights (`insights.md` §6) and the hardening roadmap
(`hardening.md` §2) as possible **grading artifacts**: cases where the
dataset penalizes a defensible model move rather than a real capability
gap. This memo adjudicates each against the actual task definitions, the
scorer, and the per-config behavior in `bench_data.json`.

**Frozen context (not relitigated here):** all-or-nothing scoring
(Decision 4), single-turn design (Decision 2), `tool_choice: auto`
(Decision 7), and the rule that `expected_alternatives` are added only
after adjudication and never to paper over a vague task (Decision 10).

**Data limitation, stated up front.** `bench_data.json` records each
config's *tool-call names per task* (`parallel_task.per_config[*].calls`)
and the scorer's per-spec pass/fail (`failed_specs`), but **not the
argument strings** the models actually passed. So claims about *which
query keywords* a failing model used are inferred from (a) the scorer's
binary spec outcomes and (b) the in-context decompose response that
steers phrasing — not read directly from raw call arguments. Where this
matters, it is called out.

---

## Task 1 — `halverson_dispute_02` (parallel, `expected_parallel`)

### The claim
The expected keyword on each parallel `search` spec is over-tuned: it
requires the literal token `indemnification`, but the in-context
decompose response (the step-2 tool message) reads *"indemnification
**and limitation of liability**"*. A model that correctly fans out two
parallel searches but phrases one or both legs around
`liability` / `limitation of liability` scores 0 despite making the exact
parallel retrieval move the task is testing.

### What the task actually specifies
`expected_parallel` has two specs, each a single `keywords` arg on
`query`:

- spec 0: `search`, `query` keywords `["halverson", "indemnification"]`
- spec 1: `search`, `query` keywords `["apex", "indemnification"]`

`_match_keywords` (scorer.py:73) requires **all** keywords present as
substrings. So a search leg must contain *both* the counterparty token
**and** the literal `indemnification` to bind its spec.

The in-context decompose response the model is reacting to:

> sub_queries: [1] "indemnification **and limitation of liability**
> provisions in agreements with Halverson Logistics", [2]
> "indemnification **and limitation of liability** provisions in the
> Apex Components master services agreement"

The corpus framing therefore actively presents *two* equally-valid topic
tokens (`indemnification`, `limitation of liability`). Keying the spec on
only one of them penalizes the synonym the model was just handed.

### What the data shows
From `parallel_task.per_config` (call-name sequences) cross-referenced
with `per_config_task_scores`:

| Config | calls | matched/2 | passed |
|---|---|---|---|
| gpt-5.4-nano | search ×4 | 2 | ✅ |
| gpt-4o-mini | search, search | 0 | ❌ |
| claude-haiku-4-5 | search, search, list_documents, list_documents | 0 | ❌ |
| gpt-5.5 | list_documents, list_documents, search, search | 0 | ❌ |
| claude-sonnet-4-6 | list_documents, list_documents, search, search | 0 | ❌ |
| claude-opus-4-6 | search, search, list_documents, list_documents | 0 | ❌ |
| gpt-5.4-mini | list_documents, list_documents | 0 | ❌ |
| claude-opus-4-8 | list_documents, list_documents | 0 | ❌ |
| Fable 5 (low/med/high) | list_documents, list_documents | 0 | ❌ |
| gemma4:12b | (none) | 0 | ❌ |

Two distinct failure populations:

1. **Issued two distinct `search` calls but scored 0**
   (gpt-4o-mini; and gpt-5.5 / sonnet / opus-4-6 / haiku, which issued
   `search ×2` alongside two `list_documents` probes). These configs
   **did parallelize two searches.** With two distinct search calls
   present, the injective matcher can bind each spec to its own call —
   so the only way both specs fail (`failed_specs: ["0:search",
   "1:search"]`) is a **keyword mismatch**: their search queries did not
   both contain the literal `indemnification`. Given the decompose
   message foregrounds "limitation of liability," the most likely
   phrasing split indemnification onto one leg and liability onto the
   other (or used "liability caps," matching the user's own wording).
   *This is argument formulation on a synonym, not a failure to fan out.*

2. **Issued only `list_documents` calls** (opus-4-8, gpt-5.4-mini, all
   three Fable efforts). These configs explored metadata instead of
   retrieving passages — a **genuine strategy error**: they did not
   parallelize searches at all. The fix below must not rescue them.

### Verdict: **artifact (partial), on the keyword spec only**
The parallel *axis* is a good discriminator — only nano fanned out into
two passage searches that survived. But the single task is over-tuned on
keyword choice. Population (1) made the correct parallel move and was
rejected on a synonym the corpus itself surfaced; population (2) is a
real miss. The grader currently cannot tell them apart.

Corroborating signal already in the repo: the scorer unit test
`TestExpectedParallel` (test_scorer.py:594) was authored with
counterparty-only specs (`["halverson"]`, `["apex"]`) and an `_APEX`
fixture query of `"apex liability caps"` — which *passes the looser test
spec but would fail the live task's `["apex","indemnification"]` spec.*
The test and the task already disagree; the test encodes the more
defensible expectation.

### Recommended action (implemented)
Relax each parallel spec's `query` keywords to the **counterparty token
only**:

- spec 0: `["halverson", "indemnification"]` → `["halverson"]`
- spec 1: `["apex", "indemnification"]` → `["apex"]`

Rationale and guardrails:

- **It does not let a non-parallelizer pass.** The score still requires
  two *distinct* `search` calls (injective matching, scorer.py:102–133).
  Every `list_documents`-only config (opus-4-8, gpt-5.4-mini, Fable ×3)
  still scores 0. Population (2) is unaffected.
- **It stops rejecting correct synonyms.** Any model that issues a
  Halverson-scoped search and an Apex-scoped search — regardless of
  whether it says "indemnification," "liability caps," or "limitation of
  liability" — now binds both specs, which is the behavior the task name
  ("parallel invocation") is actually measuring.
- **`expected_parallel` cannot carry alternatives.** The loader forbids
  `expected_alternatives` on parallel tasks (tasks.py:91–95), so a
  per-spec adjudicated alternative is not schema-expressible. Keyword
  relaxation to the robust counterparty token is the conventional fix
  (it is exactly what `hardening.md` §2 and §4-note-1 recommend, and what
  the existing unit test already assumes).
- **Counterparty token is robust.** "halverson" / "apex" each appear in
  the user turn, the decompose response, and the corpus titles; there is
  no synonym ambiguity on the entity, unlike on the topic.

### Expected grading impact
- `halverson_dispute_02` passers: **1/12 → likely 4–6/12.** The configs
  that issued two distinct searches (gpt-4o-mini, gpt-5.5, sonnet-4-6,
  opus-4-6, haiku-4-5) should now bind both specs *if* their two searches
  were counterparty-scoped (one Halverson, one Apex). nano stays passing.
  The `list_documents`-only configs stay failing. **This must be
  confirmed on a re-run** — we cannot prove the exact pass set from
  call-name data alone (see data limitation). The change can only ever
  *help* a config that already issued ≥2 distinct searches; it can never
  flip a non-parallelizer.
- North-star CPC denominators shift only for the configs that flip.

---

## Task 2 — `vendor_renewal_decompose_01` (single-call, forces `query_decompose`)

> **Prior decision in play.** The project status doc recorded a
> deliberate decision to *"keep `vendor_renewal_decompose_01` strict —
> decompose-vs-parallel is the blog's behavioral story."* Loosening this
> task **reverses a prior human decision** and is therefore Sahil's call,
> not something to flip silently.

### The claim
A single `list_documents(type=vendor_agreement)` (or a `search`)
defensibly answers the query, so forcing `query_decompose` penalizes the
10 configs that made the cheaper, equally-valid first move. Only
sonnet-4-6 and opus-4-6 passed (2/12).

### What the task actually specifies
- `expected`: `query_decompose`, `query` keywords `["vendor", "renew"]`
- User turn: *"Which of our vendor agreements auto-renew, how much notice
  do we have to give to terminate each one, and do any of those notice
  deadlines land before the renewal-decision date on the Easton warehouse
  lease?"*

### What the data shows
- Passers: **claude-sonnet-4-6, claude-opus-4-6** (the adjacent-gen
  Anthropic pair). All 10 others scored 0, including nano, gpt-5.5, all
  Fable efforts, and opus-4-8.
- The bench data records only the score for this task, not the tool the
  failing configs reached for. From the harness design and the insight
  notes, the failing configs "almost certainly went straight to
  `list_documents`/`search`" — but this is **inference, not logged
  fact.** No distractor picks are recorded on this task.

### Evidence the query is genuinely decompose-worthy (keep-strict)
- The query spans **two document families**: vendor agreements *and* the
  Easton warehouse **lease**. The third clause is an explicit
  **cross-family temporal comparison** ("do any of those notice deadlines
  land before the renewal-decision date on the Easton lease"). That is
  precisely the trigger `query_decompose`'s own description names:
  *"comparisons across time periods, or multi-entity lookups."*
- It is **structurally identical to `halverson_dispute_01`**, which the
  dataset already accepts as a legitimate forced-decompose entry
  (two counterparties + a comparison → `query_decompose` with
  `["halverson","apex"]`). If halverson_dispute_01 is fair, so is this.
- A single `list_documents(type=vendor_agreement)` answers **at most the
  first two clauses** (which agreements auto-renew, and — via a follow-up
  filtered search — the notice terms; cf. `vendor_autorenew_01`/`02`).
  It **cannot** answer the third clause, which needs the Easton lease's
  renewal-decision date from a *different* doc family. So the "single
  cheap call" does not actually satisfy the request; it satisfies a
  sub-question.

### Evidence it is a defensible artifact (the other side)
- The first two clauses *are* answerable by the `vendor_autorenew` chain's
  real opening move — `list_documents(type=vendor_agreement)` then
  `search(notice, filters=vendor_agreement)` (steps 01–02 of that chain,
  which every config passes). So a model that opens with
  `list_documents` and defers the Easton comparison to a later turn is
  not making a *wrong* first move — it is making a valid first move on a
  multi-turn plan, which `tool_choice: auto` permits.
- The passer set is inverted from capability expectation: only the
  *older* Anthropic 4.6 pair decomposes; newer/stronger models
  (opus-4-8, gpt-5.5, Fable) skip it. That pattern is at least
  *consistent* with "decompose is a stylistic Anthropic-4.6 reflex" rather
  than "the strong models failed a hard task."

### Verdict: **mixed — lean KEEP STRICT; do not flip without Sahil**
On balance the task is defensible as written: the cross-family temporal
comparison genuinely warrants decomposition, and it mirrors the accepted
`halverson_dispute_01`. The "single cheap call" objection answers only
two of three clauses, so it is not a strictly-equivalent alternative the
way a true adjudicated tie (Decision 10) requires. Adding
`expected_alternatives: list_documents(type=vendor_agreement)` would
assert that metadata listing is *equally correct* — but it demonstrably
answers a *subset* of the question, so it fails the "equally sound
strategy" bar in Decision 10.

Combined with the explicit prior "keep strict" decision, the
recommendation is to **leave the task unchanged** and surface the
evidence for Sahil. **No change is implemented for this task.**

### If Sahil decides to loosen anyway
The least-invasive change consistent with the schema is to add a single
`expected_alternatives` entry:

```json
"expected_alternatives": [
  { "tool": "list_documents",
    "args": { "filters": { "type": "exact", "value": { "type": "vendor_agreement" } } } }
]
```

This would flip the (inferred) `list_documents`-first configs to passing.
It should land **only** with an explicit acknowledgment that it reverses
the prior keep-strict decision and weakens the decompose-vs-parallel
behavioral story the blog leans on. It is **not** implemented here.

---

## Summary

| Task | Verdict | Action | Reverses prior decision? |
|---|---|---|---|
| `halverson_dispute_02` | Artifact (keyword over-tuned) | Relax parallel keywords to counterparty-only (`indemnification` dropped from both specs) | No |
| `vendor_renewal_decompose_01` | Mixed, lean keep-strict | **No change.** Evidence surfaced for Sahil. | n/a (unchanged) |

The `halverson_dispute_02` fix corrects a grader that conflates "didn't
parallelize" with "phrased the synonym differently"; it cannot make a
non-parallelizer pass. The decompose task is left to Sahil because
changing it reverses an explicit decision and the cheaper alternative
answers only part of the question.
