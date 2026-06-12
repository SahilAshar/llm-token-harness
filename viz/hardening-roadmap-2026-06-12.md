# Dataset Hardening Roadmap — Round 2

Grounded in the 2026-06-12 run (23 tasks × 12 configs). Source: `/tmp/llm-harness-viz/bench_data.json`, `data/tasks/search_agent_v1.json`, `src/scorer.py`, `src/tools.py`.

Scoreboard for reference (score / 23): Fable 5 low+med **19**, gpt-5.5 / opus-4-6 / gpt-5.4-mini / sonnet-4-6 / Fable-high **17–18**, gpt-5.4-nano / opus-4-8 **16**, haiku-4-5 **15**, gpt-4o-mini **13**, gemma4:12b **9**. Spread 9→19 (was 10→14 on the June-10 15-task grid). Hardening worked; now we trim dead weight and add new discriminating axes.

---

## 1. Diagnosis from this run

### Saturated — passed by all 12 (`n_pass == 12`): dead weight as discriminators
- `easton_amendment_01` (12) — fetch by explicit doc_id
- `easton_amendment_03` (12) — fetch amendment by doc_id from history
- `corvid_fetch_01` (12) — fetch by explicit doc_id **[floor]**
- `nda_inventory_01` (12) — list_documents type filter **[floor]**
- `q1_2025_inventory_01` (12) — list_documents date range **[floor]**
- `nonsolicit_search_01` (12) — plain search **[floor]**
- `termination_topk_01` (12) — search + top_k=10 **[floor]**

Near-saturated (11/12, single straggler = gemma or nano): `vendor_autorenew_01`, `vendor_autorenew_03`, `vendor_indemnification_2024_01`, `okafor_leases_01`.

**Recommendation.**
- **Keep the 5 floor tasks** (`corvid_fetch_01`, `nda_inventory_01`, `q1_2025_inventory_01`, `nonsolicit_search_01`, `termination_topk_01`). They are the deliberate baseline floor (CLAUDE.md design decision 11) and the *only* thing separating gemma (9) from total collapse — they prove the harness isn't just noise. Floor tasks are features, not bugs. Do **not** retire them.
- **Retire/replace the two saturated *chain* tasks that aren't floor**: `easton_amendment_01` and `easton_amendment_03` add length to the easton chain but contribute zero discrimination (both 12/12) and zero state-dependency challenge (01 = doc_id handed in prompt; 03 = doc_id sitting in the immediately-prior search result). The easton chain's discrimination lives entirely in steps 02 (4/12) and 04 (10/12). Replacing 01/03 with harder intermediate steps (see Axis B and Axis E) raises the chain's discriminating density without lengthening it.
- The near-saturated 11/12 tasks are fine — they discriminate gemma/nano and cost nothing to keep.

### Discriminating well (mid-band `n_pass` 4–9, splits the frontier models)
- `halverson_dispute_03` (9), `halverson_dispute_04` (8), `halverson_dispute_05` (5) — non-adjacent state dependency is doing real work
- `halverson_sow_sla_01` (8) — 3-constraint filter (type+counterparty+date)
- `stonebridge_term_01` (8) — fetch-vs-search subtlety **[floor, but actually discriminating]**
- `vendor_autorenew_04` (5) — search for a never-surfaced doc by name from content
- `easton_amendment_02` (4), `easton_amendment_04` (10) — filter inference + non-adjacent entity resolution

These are the gold. The mid-band is where CPC means something. Note `stonebridge_term_01` is tagged `is_floor` but behaves like a mid-band discriminator (8/12) — the fetch-vs-search trap is harder than its "floor" label suggests. It also drew `summarize_document` picks from 4o-mini, sonnet, gemma. Keep it; arguably re-label it as discriminating, not floor.

### At the floor — passed by ≤2 (too hard, or mis-graded?)
- `halverson_dispute_02` (**1/12**, parallel) — only gpt-5.4-nano passed. **Investigated below (§2); this is partly a grading artifact.**
- `vendor_renewal_decompose_01` (**2/12**) — only sonnet-4-6 and opus-4-6 passed. Expects `query_decompose` with keywords `["vendor","renew"]`. The other 10 configs almost certainly went straight to `list_documents`/`search` — a *defensible* move, because unlike `halverson_dispute_01` (which forces decompose by spanning two counterparties + a comparison), this query is answerable by a single `list_documents(type=vendor_agreement)` followed by reads. The task asserts decompose is the only right answer but the corpus doesn't force it. **This is a candidate mis-grade: add `expected_alternatives` (list_documents with vendor filter) OR make the query genuinely require decomposition.** Right now it's penalizing the 10 models that made the cheaper, equally-valid first move.

**Bottom line:** 7 saturated (keep 5 floor, retire 2 chain-padding), ~10 discriminating, 2 at floor (1 grading artifact in parallel, 1 likely mis-grade in decompose). Net: the dataset is healthier than the raw spread suggests, but `vendor_renewal_decompose_01` should be adjudicated before the next run.

---

## 2. Where the current axes have headroom

### Parallel invocation (`halverson_dispute_02`): 1/12 — discriminator or artifact?
Both. Look at the actual call sequences in `parallel_task.per_config`:
- **Defensible "near-miss" moves the scorer counts as 0:** gpt-5.5, sonnet-4-6, opus-4-6, haiku all issued `list_documents ×2 + search ×2` or `search ×2 + list_documents ×2` — i.e. they *did* parallelize two searches, but also fired two `list_documents` probes in the same batch. The scorer requires each spec to bind to a distinct call (injective match), and the two correct searches are present — but their **query keywords didn't match** (`failed_specs: ["0:search","1:search"]` even when calls include `search,search`). So the failure is **argument formulation**, not failure to parallelize. The models split indemnification/liability differently than the expected `["halverson","indemnification"]` / `["apex","indemnification"]` keyword pair.
- **Genuinely wrong:** opus-4-8, all three Fable configs, gpt-5.4-mini issued only `list_documents ×2` — they explored metadata instead of retrieving passages. That's a real strategy error worth catching.
- **Passed:** gpt-5.4-nano fired `search ×4` (the two correct ones plus two extra) and matched.

**Verdict:** the parallel axis is a *good* discriminator but the single task is over-tuned on keyword choice. The keyword `"indemnification"` is too narrow — the decompose output (step 2's tool response) says "indemnification **and limitation of liability**", so a model that queries `["halverson","liability"]` is equally correct and scores 0. **Fix: loosen step-02 expected keywords to the counterparty only (`["halverson"]` / `["apex"]`), or add `expected_alternatives`-style per-spec tolerance.** (Note: `expected_parallel` does **not** support alternatives today — see §4 code note.) A second, cleaner parallel task (Axis A) will tell us whether 1/12 is the task or the axis.

### Chains: discriminating well
`halverson_dispute` (5 steps) is the best axis in the set — `correct/total` ranges from 0/5 (gpt-4o-mini, gemma) to 3/5 (frontier). Nobody clears it; the non-adjacent state dependency (step 4 needs `doc_07` surfaced two turns back, step 5 needs a never-surfaced rider) is exactly the intended difficulty. `vendor_autorenew` also splits well (0/4 gemma → 4/4 Fable). `easton` is the weakest chain because half its steps are saturated (§1). **Keep all three; tighten easton.**

### Near-miss distractors: half-working
- `summarize_document` **did its job** — it drew picks from gpt-4o-mini, sonnet-4-6, gemma, concentrated on `halverson_dispute_03/04/05`, `vendor_autorenew_02`, `stonebridge_term_01` — exactly the get_document/content steps where "just summarize it" is tempting. Sonnet picked it 11 times across 5 tasks. This is a working trap.
- `search_history` **drew zero picks**. It is currently a wasted distractor — no task creates a situation where searching prior interactions looks right, so no model is tempted. **It's not harmful (it adds tool-set noise) but it's not earning its place.** Two options: (a) retire it to reduce prompt bloat, or (b) **author a task that baits it** (Axis D) — a query that explicitly references "what did we look at earlier" so that `search_history` becomes the tempting-but-wrong move while the correct move is to read the conversation already in context. Option (b) is higher value: it converts dead bait into a live discriminator.

---

## 3. Proposed NEW hardening axes

Five axes, prioritized in §5. Every example is authorable in the current schema unless a code note says otherwise.

### Axis A — Longer parallel batches (3–4 distinct calls)
**Capability:** issuing 3+ genuinely independent retrievals in one turn without serializing or over-calling. Real search agents (LangChain `RunnableParallel`, LlamaIndex `SubQuestionQueryEngine`, Anthropic parallel tool-use) fan out N independent sub-queries in a single turn; 2-way is the easy case, 3–4-way is where models start serializing or dropping a leg.
**Why it discriminates:** the existing 2-way task already split the field; widening to 3 specs raises the injective-match bar and punishes "issued 2 of 3" — which `parallel_matched`/`parallel_failed_specs` already records for free.
**Difficulty/spread:** expect 0–3 / 12 passing. Likely only nano + one or two frontier configs. Strong top-end discriminator.
**Code changes:** none for scoring (`_score_parallel` already does N-way bipartite matching). **But** see §4: `expected_parallel` can't carry per-spec alternatives, so keep keywords to the counterparty token only to avoid the §2 over-tuning trap.

Example task (new standalone, not a chain — keeps it simple to author):
```json
{
  "task_id": "tri_counterparty_parallel_01",
  "scenario_id": "tri_counterparty_parallel",
  "step": 1,
  "description": "Three independent counterparty lookups; correct move is three parallel searches in one batch. Issuing fewer, or serializing, scores 0.",
  "messages": [
    {"role": "system", "content": "<<standard contract-intelligence system prompt>>"},
    {"role": "user", "content": "Board prep: I need the termination-for-convenience clause from three separate agreements at once — the Halverson MSA, the Apex Components MSA, and the Corvid MSA. Pull them in parallel; don't make me wait on three round-trips."}
  ],
  "expected_parallel": [
    {"tool": "search", "args": {"query": {"type": "keywords", "value": ["halverson", "termination"]}}},
    {"tool": "search", "args": {"query": {"type": "keywords", "value": ["apex", "termination"]}}},
    {"tool": "search", "args": {"query": {"type": "keywords", "value": ["corvid", "termination"]}}}
  ],
  "scoring_weights": {}
}
```
Keywords are counterparty + one robust topic token only — avoids the `indemnification`-vs-`liability` artifact from §2.

### Axis B — Content-dependent multi-hop (step N keyed on *content returned* at step N-2)
**Capability:** carrying a concrete value (a doc title, a section number, a counterparty name) out of a document's *body text* — not its metadata — and using it as the anchor for a later retrieval. `vendor_autorenew_04` already does a one-hop version (Kestrel's body names the "Master Vendor Program Agreement"). This axis makes it a *two-hop* non-adjacent dependency: the value needed at step N was buried in the body of a doc fetched at step N-2, and nothing in steps N-1 or the user turn repeats it.
**Why it's a real skill:** agentic RAG (self-RAG, ReAct-style retrieval loops) routinely chases cross-references — "see Schedule C", "governed by Section 9.4 of the MSA", "as defined in the Master Agreement". The model must read, extract the pointer, and re-retrieve. This is the single most common failure mode in production contract agents.
**Difficulty/spread:** expect 3–6 / 12. This is the mid-band sweet spot — frontier models hop, weaker models re-search the wrong anchor or summarize.
**Code changes:** none. Standard single-call `expected` with `keywords`.

Example (replaces saturated `easton_amendment_03`, slots into the easton chain as a content-hop step). Suppose the amendment body (`doc_20`) references "the Pinehurst Master Lease Framework" governing all the landlord's leases:
```json
{
  "task_id": "easton_amendment_03b",
  "scenario_id": "easton_amendment",
  "step": 3,
  "description": "The amendment body cross-references the 'Pinehurst Master Lease Framework' as governing the renewal mechanics. That framework has never been surfaced and its doc_id is unknown; the only anchor is the name appearing in doc_20's body two steps back. Correct move: search anchored on that framework name.",
  "messages": ["<<history through fetching doc_20, whose content names the 'Pinehurst Master Lease Framework'>>"],
  "expected": {
    "tool": "search",
    "args": {"query": {"type": "keywords", "value": ["master lease framework"]}}
  },
  "scoring_weights": {}
}
```
Distractor pull here: `summarize_document(doc_20)` (re-summarize instead of chasing the reference) and re-fetching `doc_19`/`doc_20` (re-reading what you've already got).

### Axis C — Cost-trap / over-calling tasks (a cheap single move suffices)
**Capability:** restraint. The correct answer is one cheap, targeted call; the trap is to fan out, decompose, or list-then-search when the user already pinned the answer down. CLAUDE.md's north star is **CPC** — a model that gets the right answer via 4 calls when 1 was right is wasting the denominator's worth of tokens. We currently reward correctness but never *penalize over-calling*, even though it's the core cost story.
**Why it's a real skill:** "minimal tool use" is an explicit objective in agent frameworks (OpenAI's tool-use guidance, Anthropic's "don't over-tool" guidance). Over-calling is the dominant cost driver in production.
**Difficulty/spread:** with all-or-nothing scoring as-is, a cost-trap only discriminates if the over-call produces a *wrong tool* (then it already fails) — so to make it bite under V1 scoring, design it so the tempting expansion is a *distractor* or a *different tool*. Expect 5–9 / 12.
**Code changes:** none for V1 (lean on tool-name mismatch). **For V2**, a real cost-trap wants a "calls ≤ N" graded signal — see §4. For now, `actual_tools` already records batch length, so over-call *rate* falls out as an unscored behavioral metric (like distractor-pick rate) even without changing the score.

Example (single call should win; decompose is the trap):
```json
{
  "task_id": "single_clause_costtrap_01",
  "scenario_id": "single_clause_costtrap",
  "step": 1,
  "description": "Looks multi-part ('and') but is one narrow content lookup in one named doc family. The cheap move is a single filtered search. query_decompose is the over-engineering trap; it's not wrong-tool but it burns a turn — scored via expected=search, and decompose scores 0.",
  "messages": [
    {"role": "system", "content": "<<standard system prompt>>"},
    {"role": "user", "content": "Real quick — across our NDAs, what's the standard confidentiality survival period after termination? Just the survival clause language, nothing fancy."}
  ],
  "expected": {
    "tool": "search",
    "args": {
      "query": {"type": "keywords", "value": ["survival"]},
      "filters": {"type": "exact", "value": {"type": "nda"}}
    }
  },
  "expected_alternatives": [
    {"tool": "search", "args": {"query": {"type": "keywords", "value": ["confidentiality", "survive"]}, "filters": [{"name": "filters", "match_type": "exact", "value": {"type": "nda"}}]}}
  ],
  "scoring_weights": {}
}
```
(Author the alternative with the same `expected` arg shape as the primary; shown loosely above.) Track batch-length of the passing configs from `actual_tools` to report over-call behavior even though the score is binary.

### Axis D — Convert the dead `search_history` distractor into a live trap
**Capability:** distinguishing "search my prior interactions" from "read the conversation already in front of me." `search_history` drew **zero** picks — it's wasted. A task that explicitly says "what we looked at earlier" makes `search_history` the tempting move, while the correct move is either to answer from in-context history or to re-issue a corpus `search`/`get_document`.
**Why it's a real skill:** in stateful agents, conversation context and a "session history" tool are genuinely confusable; picking the tool when the answer is already in the message window is a real and costly error.
**Difficulty/spread:** expect 6–10 / 12 — weaker/cheaper models more likely to grab the shiny history tool. Resurrects a dead distractor into a discriminator.
**Code changes:** none.

Example (mid-chain, where the prior result is already in context):
```json
{
  "task_id": "halverson_recall_01",
  "scenario_id": "halverson_dispute",
  "step": 6,
  "description": "User asks to re-confirm a figure from a document already fetched earlier in THIS conversation (doc_07, Section 9.2). The answer is in context; the correct retrieval move if a re-read is wanted is get_document(doc_07). search_history is the trap (it searches prior sessions, not this corpus and not this in-context history).",
  "messages": ["<<halverson history through step 5; user now asks 'remind me exactly what the 9.2 cap said in the Halverson MSA we pulled earlier'>>"],
  "expected": {
    "tool": "get_document",
    "args": {"doc_id": {"type": "exact", "value": "doc_07"}}
  },
  "scoring_weights": {}
}
```
Watch `distractor_picks` for `search_history` to confirm the bait now fires.

### Axis E — Adversarial / ambiguous filter language (filter precision under linguistic noise)
**Capability:** mapping fuzzy human date/scope language onto exact filter boundaries. The current constraint-dense tasks use clean phrasing ("in 2024", "first quarter of 2025"). Real users say "since last spring", "the back half of last year", "before we renewed Easton", "everything newer than the Apex deal." The model must resolve these to `start_date`/`end_date` boundaries — and a one-day boundary error fails under `exact` matching.
**Why it's a real skill:** date-range resolution is the #1 filter bug in production search agents; Azure AI Search / Elastic range queries are unforgiving about boundaries.
**Difficulty/spread:** expect 3–7 / 12 — boundary-off-by-one and "did they mean inclusive?" splits the field hard. **Caveat:** relative dates need a fixed "today" anchor. The system prompt already implies a present; pin it explicitly in the task's system message (`"Today's date is 2026-06-12."`) so the expected boundary is deterministic. Avoid genuinely ambiguous phrasings where two boundaries are both defensible — that becomes a mis-grade, not a discriminator. Prefer phrasings with one correct resolution.
**Code changes:** none (uses existing `exact` filter matching). Authoring discipline only.

Example:
```json
{
  "task_id": "h2_2024_relative_01",
  "scenario_id": "h2_2024_relative",
  "step": 1,
  "description": "Relative date phrasing ('the back half of 2024') must resolve to start_date 2024-07-01 / end_date 2024-12-31. Date anchor pinned in system prompt. Exact-match on the boundary; an off-by-quarter or inclusive/exclusive slip fails.",
  "messages": [
    {"role": "system", "content": "<<standard system prompt>> Today's date is 2026-06-12."},
    {"role": "user", "content": "Give me every agreement we executed in the back half of 2024 — titles and dates only."}
  ],
  "expected": {
    "tool": "list_documents",
    "args": {"filters": {"type": "exact", "value": {"start_date": "2024-07-01", "end_date": "2024-12-31"}}}
  },
  "scoring_weights": {}
}
```

### Axes considered and rejected (pressure-test)
- **Abstention / "don't call a tool" tasks** — the most-requested idea, but **structurally unauthorable in V1**: `_parse_task` requires exactly one of `expected`/`expected_parallel`, and `expected.tool` is a non-empty string; `score_task` hard-codes score 0 for an empty `tool_calls` batch (lines 173–183). There is no "no-call is correct" target. Authoring one needs a new sentinel mode (e.g. `expected_no_call: true`) plus a scorer branch. It's a legitimate axis (refusing to search the public web, asking for clarification on an ambiguous ID) but it is **net-new code + new task type = V2**, not a June-21 add. Do not attempt for this round.
- **Clarification-question tasks** — same blocker, plus they collide with `tool_choice: "auto"` semantics and would need the model's *text* response graded, which the harness doesn't score. V2.
- **A distractor that is *almost* right** — interesting, but our near-miss distractors (`summarize_document`) already occupy this space and it's working. A new "almost-right real tool" risks becoming an adjudication swamp (is it actually wrong?). Lower priority than A–E.

---

## 4. Scoring evolution

**All-or-nothing is still right for V1** and for every axis A–E above — each is authorable as a clean binary pass/fail. Specific notes:

1. **`expected_parallel` needs per-spec alternatives (small V1-eligible fix).** §2 showed the 2-way parallel task over-fits on `indemnification` vs `liability`. Today a parallel spec's args are matched strictly; there's no `expected_alternatives` for parallel (and `_parse_task` actively forbids it). The cheap fix is **authoring discipline** — keep parallel keywords to a single robust token (counterparty + topic) so there's only one reasonable phrasing. A code fix (allow each `ExpectedCall` in `expected_parallel` to carry alternative keyword sets) is a ~20-line scorer change but is **optional** and can wait. Recommend authoring-discipline for June-21.

2. **Cost-trap (Axis C) and over-call behavior want a graded signal — but that's V2.** Partial credit is explicitly backlogged (design decision 4). For now, `TaskResult.actual_tools` already records batch length and call order, so over-call rate and decompose-invocation rate fall out as **unscored behavioral metrics** exactly like distractor-pick rate. Report them in the viz; don't change the score. *If/when V2 adds partial credit*, the natural shape is a calls-budget penalty (`score = correct ? max(0, 1 - λ·(n_calls - min_calls)) : 0`) — frame for V2, don't build now.

3. **`vendor_renewal_decompose_01` is a scoring fix, not a new axis** — add an `expected_alternatives` entry for the `list_documents(type=vendor_agreement)` first move, or rewrite the query to genuinely require decomposition (span two doc families with a cross-family comparison, like `halverson_dispute_01` does). This is adjudication per design decision 10, and it should land before the next run regardless of which axes ship.

---

## 5. Prioritized next steps (toward ~June-21 post)

Ordered by discrimination-per-effort. Effort in rough half-day units; all are authoring-only unless noted.

| # | Action | Effort | Why first |
|---|--------|--------|-----------|
| 1 | **Adjudicate `vendor_renewal_decompose_01`** (add list_documents alternative or rewrite). Loosen `halverson_dispute_02` parallel keywords to counterparty-only. | 0.5d | Fixes two grading artifacts currently *understating* the dataset's fairness. Zero new code. Must-do before re-run. |
| 2 | **Axis B — content-dependent multi-hop**, replacing saturated `easton_amendment_03` with `03b` (and optionally retiring `easton_amendment_01`). | 0.5d | Highest discrimination-per-effort: mid-band, reuses an existing chain, kills dead weight while adding signal. Pure authoring. |
| 3 | **Axis A — one 3-way parallel task** (`tri_counterparty_parallel_01`). | 0.5d | Tests whether parallel 1/12 was the task or the axis; `_score_parallel` already handles N-way, so zero code. Strong top-end split. |
| 4 | **Axis D — `search_history` bait task** (`halverson_recall_01`). | 0.5d | Converts a dead distractor into a live one; cheap; gives the viz a new distractor-pick story. |
| 5 | **Axis E — 1–2 relative-date filter tasks** with pinned date anchor. | 0.5d | Good mid-band discriminator; only risk is authoring an ambiguous boundary — keep phrasings single-resolution. |
| 6 | **Axis C — one cost-trap task** + report over-call rate from `actual_tools` in the viz. | 0.5d | Ties directly to the CPC north star; binary-scoreable in V1 via tool-name mismatch; behavioral metric is free. |
| 7 | *(V2, not June-21)* Abstention/clarification mode: new `expected_no_call` task type + scorer branch. | 1.5d+ | Real axis, but net-new code AND new task type. Backlog. |

**June-21 scope:** items 1–4 are the floor (2 days, all authoring, zero code) and already meaningfully sharpen the run. Items 5–6 if time allows. Item 7 is explicitly V2.

**Re-run note:** after items 1–4, re-run the full 12-config grid. Watch for (a) `vendor_renewal_decompose` no longer at floor, (b) the 3-way parallel landing 0–3/12 (validates the axis), (c) `search_history` finally drawing picks (validates Axis D), (d) easton chain `correct/total` spread widening now that 01/03 are gone or replaced.
