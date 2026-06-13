# CPC: A Cost-Per-Correct Methodology — Writer's Brief

> **This is SOURCE MATERIAL, not a finished post.** It is a writer's brief: the
> framing, the framework articulation, the verified facts/figures, suggested
> angles, and the honest caveats — clean and citable, organized for a human to
> draw from. It is deliberately *not* written in published prose voice. Do the
> prose pass yourself.
>
> **Canonical data:** `viz/data/runs/2026-06-12-r2.json` (the r2 run: 12 configs
> × 25 tasks, post-#22 dataset, parallel tasks re-scored under per-spec
> alternatives #25). Every figure in this brief traces to that file. If the live
> run is later refreshed, these numbers go stale — they are pinned to the
> 2026-06-12-r2 snapshot.
>
> **Companion docs (read alongside):** `viz/insights-2026-06-12-r2.md` (canonical
> insights), `CLAUDE.md` (North star, scoring, the closed adjudications in
> Design Decision 12, the four hardening axes in Decision 11),
> `viz/hardening-roadmap-2026-06-12.md` (the pre-r2 roadmap — see the figure-
> hygiene note before quoting its scoreboard).

---

## 0. Thesis spine (one line)

**The right way to rank a tool-selection model is neither accuracy alone nor
cost alone, but Cost Per Correct — total dollars spent to buy one correct
retrieval strategy — because that is the number a deployment budget actually
pays, and it double-penalizes the two failure modes (being wrong, and being
expensively right) that accuracy and cost each miss in isolation.**

Everything below supports, qualifies, or quantifies that sentence.

---

## 1. THE FRAMEWORK — why Cost-Per-Correct

### 1.1 Definition (state it exactly, once)

> **CPC (Cost Per Correct) = total run cost in USD / number of tasks with a
> correct retrieval strategy.**

Lower is better. It is dollars-per-useful-answer. It is *not* a per-token price
and *not* an accuracy percentage; it fuses both into the unit a buyer cares
about. A model that is cheap but often wrong and a model that is accurate but
expensive can land at the *same* CPC — which is exactly the point: it puts them
on one axis.

### 1.2 The argued case: why not accuracy alone?

- Accuracy answers "how often is it right?" but is silent on what right costs.
  In this run the accuracy ceiling is **flat and crowded** — gpt-5.5 tops out at
  21/25 (84%), and five configs sit one task below at 20/25 (80%): opus-4-6,
  opus-4-8, and all three Fable 5 efforts. An accuracy-only leaderboard would
  call those six "basically tied" and stop there.
- But those six "tied" configs span a **10×+ cost range**. Accuracy alone hides
  the entire economic story at the top of the board. CPC surfaces it: among the
  20/25 cluster, opus-4-6 costs $0.0195/correct while Fable 5 (high) costs
  $0.0441/correct — same quality, 2.3× the price.

### 1.3 The argued case: why not cost alone?

- A pure cost ranking rewards a model for being cheap *by being wrong*. The
  cheapest API config here, gpt-4o-mini, runs at $0.00039/correct — but only
  solves 14/25 (56%). The free local model (gemma4:12b) is "cheapest" of all at
  $0 and solves only 13/25 (52%).
- Cost-per-token says "use the nano model." CPC says "the nano model leaves a
  third of the work undone; price the work it *can't* do." CPC refuses to credit
  cheapness that doesn't buy correctness.

### 1.4 The load-bearing property: the double penalty

CPC = cost / correct. A bad model is punished **twice**:
- once in the **numerator** if it burns tokens (over-calls, long reasoning), and
- once in the **denominator** if those tokens don't convert to correct strategies.

A wrong-but-cheap model and a right-but-expensive model are both demoted, by the
same single number, without the analyst having to choose which axis to privilege.
This is the core argument for CPC as the north star of a *tool-selection* eval
specifically: the failure we most want to price is "spent a lot of model to pick
the wrong tool," and CPC is the metric that charges for exactly that.

### 1.5 The deployment-budget framing (the hook)

A team shipping a retrieval agent does not have an "accuracy budget" or a
"token budget" — it has a **dollar budget for answered questions**. CPC is
denominated in that unit. "What does one correct retrieval cost me on model X?"
is a question a finance-aware eng lead asks directly off this number.

### 1.6 The Pareto framing (how to read the board)

CPC is one scalar, but the honest read is a **frontier**, not a single winner.
Plot score (maximize) against CPC (minimize); the non-dominated configs are the
ones nothing beats on *both* axes:

> **Dollar Pareto frontier: gpt-4o-mini → gpt-5.4-nano → haiku-4-5 → gpt-5.5.**

Everything priced at sonnet's level or above is dominated: sonnet-4-6 is beaten
on both axes by gpt-5.5 (gpt-5.5 is cheaper *and* scores higher); the opus pair
and all three Fable efforts buy 20/25 at 1.6×–3.7× gpt-5.5's CPC while gpt-5.5
scores 21. gemma's $0 CPC sits *off* the dollar frontier — it's free because
it's local, not because it's a frontier win; keep it labeled "$0 (local)" so a
reader doesn't miscredit a weaker model as the cost champion. **Priority order
for the whole framework: Quality > Latency > Dollar cost.**

---

## 2. HOW THE HARNESS WORKS — the mechanics a skeptic will ask about

State these plainly; they are what make the CPC number trustworthy.

| Design choice | What it means | Why |
|---|---|---|
| **Single-turn tool selection** | Each task is one prompt → one expected tool call. It's "the exam, not the student" — we measure the model's *retrieval reasoning*, not a retrieval engine. | Isolates the brain of the agent from search infrastructure. |
| **Simulated corpus** | Tool responses are hardcoded JSON over a fake contract repository. The model never hits a real index. | Removes retrieval-quality noise; the only variable is the model's tool/argument choice. |
| **All-or-nothing scoring** | Score is 1 iff the tool name matches AND every required arg matches; else 0. No partial credit (backlogged for V2). | A retrieval call with the wrong filter is wrong, not 70%-right. Binary keeps CPC's denominator honest. |
| **Two arg-match types** | `exact` (doc_id, top_k, filters — case-insensitive, type-coerced, key/list-order insensitive) and `keywords` (free-text query — all keywords must appear). | Lets us score structured args strictly and free text leniently without NLP deps. |
| **Distractor tools** | 9 tools are offered, only 4 are ever correct. 3 are categorically wrong (web_search, tag_document, create_alert); 2 are semantic near-misses (summarize_document shadows get_document; search_history shadows search). | Tests tool *discrimination*, not just tool use — defends against saturation (the MCPAgentBench pattern). Distractor-pick rate is tracked as an unscored behavioral metric. |
| **Chains** | 3 multi-step scenarios (5, 4, 4 steps) sharing a `scenario_id`, built from real conversation history (not text summaries), with non-adjacent state dependencies. | Tests carrying a value from turn N to turn N+2 — the production failure mode. |
| **Parallel tasks** | 2 tasks expect 2+ calls in one batch; ALL specs must be matched (any-call-per-spec, all-specs-required). | Tests fan-out without serializing or dropping a leg. |
| **Adjudicated alternatives** | A task may list `expected_alternatives` (equally-correct whole strategies) or, per parallel spec, an `alternatives` list (e.g. scoping a counterparty via a metadata filter instead of a query token). A match on primary OR any alternative scores 1. | Added only after dataset red-teaming shows two strategies are genuinely equal — never to paper over a vague task. |
| **`tool_choice: "auto"`** | The model decides *whether* to call a tool at all. | A real agent isn't told "you must call something." |

One sentence the writer should land: **CPC is only as honest as the denominator,
and the denominator is honest because scoring is strict, binary, and the
"correct" set was adjudicated — so a correct count is a count of genuinely
correct strategies, not lucky partial matches.**

---

## 3. THE FOUR HARDENING AXES — and why saturation forced them

### 3.1 The saturation problem (the motivating fact)

The **first** benchmark run showed **10 of 15 tasks passed by everyone**.
Single-turn selection from a small tool set is saturated industry-wide: every
frontier model picks the obvious tool for the obvious task. A benchmark where
everyone scores ~90% can't rank anything — CPC computed on it just re-prices a
near-constant numerator. **Saturation is the disease; the four axes are the
cure.**

### 3.2 The four axes (Decision 11)

The dataset was deliberately hardened along four axes, with the easy tasks
*kept* as a baseline floor (they prove the harness isn't pure noise and they're
the only thing separating gemma from total collapse):

1. **Longer chains with non-adjacent state dependency** — a value surfaced at
   step N must be reused at step N+2, with nothing in between repeating it.
2. **Constraint-dense filters** — tasks requiring 2–3 simultaneous filter
   constraints (type + counterparty + date), where one wrong boundary fails.
3. **Semantic near-miss distractors** — summarize_document and search_history,
   plausible shadows of the right tool, testing discrimination.
4. **Parallel-invocation scoring** — `expected_parallel`: fan out N independent
   retrievals in one batch or score 0.

### 3.3 Did it work? (the payoff figure)

Yes. On the r2 run the per-config score spread is **13/25 → 21/25** across 12
configs — a real, rankable dispersion where the hard tasks are doing the
discriminating. The mid-band tasks (n_pass 3–9 of 12) are where CPC means
something:

- `halverson_dispute_02` (parallel): 7/12 pass
- `easton_amendment_03b` (content-hop, the dataset's strongest single
  discriminator): 3/12
- `vendor_autorenew_02`: 3/12 · `vendor_renewal_decompose_01`: 2/12
- `easton_amendment_02`: 5/12 · `halverson_dispute_05`: 6/12 ·
  `vendor_autorenew_04`: 6/12

The baseline floor still does its job: the saturated floor/near-floor tasks
(corvid_fetch_01, nda_inventory_01, q1_2025_inventory_01, nonsolicit_search_01,
termination_topk_01, h2_2024_relative_01, okafor_leases_01 — all 12/12) keep
even the weakest config off the floor.

> **FIGURE-HYGIENE WARNING (do not quote the wrong spread):** the *roadmap* doc
> reports a "9 → 19" spread — that is the **pre-r2, 23-task** scoreboard, before
> tasks #22/#25 landed. The canonical r2 figure is **13 → 21 over 25 tasks**.
> Never present the roadmap's 9→19 as r2.

---

## 4. HONEST THREATS TO VALIDITY — disclose these, don't bury them

### 4.1 Two adjudications, both closed (Design Decision 12)

These are *closed* (no dataset change), but the blog should disclose them as
threats-to-validity, exactly as decided:

- **`vendor_renewal_decompose_01` — KEPT STRICT.** Only sonnet-4-6 and opus-4-6
  pass it (2/12); the same two passers as the morning run. The strict rationale
  holds on the merits: decompose-first is the only first move that reaches all
  three clauses of the ask, and `list_documents(type=vendor_agreement)` provably
  cannot reach the Easton lease clause (which needs doc_19 / type=lease).
  **Frame it as a 4.6-generation behavioral fingerprint, NOT a decomposition-
  capability gradient** — the *newer* opus-4-8 fails it, so it's not "more
  capable models decompose more." It's a stylistic reflex the 4.6 generation
  has and later generations were tuned out of.

- **`easton_amendment_03b` — DEFENSIBLE AS-IS** (unanimous review-panel verdict;
  the dataset's strongest single discriminator, 3/12: opus-4-8, Fable medium,
  Fable high). Threats-to-validity disclosure: 8 of 9 failures jump to the
  user's *third* ask (listing the Pinehurst landlord's agreements, or a
  Pinehurst-scoped search) with the renewal question unanswered. The "wrong
  strategy" verdict rests on single-turn scoring semantics — but it holds because
  the failing route (`list_documents` on the landlord) is **metadata-only and
  never returns the renewal clause**; it does not even incidentally answer the
  open question. State this plainly; it's the strongest honesty move in the post.

### 4.2 Reasoning-token non-comparability across providers

This is a real cross-provider gotcha. **Do not chart reasoning_tokens across
providers.** Concretely, in r2:
- **OpenAI (gpt-5.5)** reports real reasoning tokens: **949**.
- **Anthropic** folds thinking into output_tokens, so reasoning_tokens reads
  **0** for every Anthropic config (haiku, sonnet, both opus, all Fable).
- **Ollama (gemma)** reports **2833**, but that value is a whitespace
  *word-count*, not a token count.

Rule for the post: chart reasoning tokens **within a provider only**, never
across. Crucially, **this does not touch dollar cost or CPC** — those are
computed from the providers' billed token accounting via `src/pricing.py`, so
the CPC frontier is unaffected by the reasoning-token apples-to-oranges issue.

### 4.3 r1-vs-r2 non-comparability

The r2 run is **not score-comparable task-for-task** to the June-10 grid or the
June-12 morning run — the dataset changed both times (different tasks, different
count: 15 → 23 → 25). The snapshot preserves `prior_run_june10` for *dispersion*
context, but never claim "model X improved from run to run" on a per-task basis.
Spread/shape comparisons are fine; task-level deltas are not.

### 4.4 Statistical power: single run, n=25, 12 configs

One run per config, 25 tasks, 12 configs. **Report structural findings**
(frontier shape, behavioral splits, axis postmortems) — **not 1-task gaps
between adjacent configs.** The gap between gpt-5.5 (21) and the 20/25 cluster is
a single task; treat it as "tied at the ceiling," not "gpt-5.5 is measurably
better." Adjacent CPC differences inside the cluster are likewise fragile.

### 4.5 Rescore provenance (be transparent about it)

The two parallel tasks were re-scored **offline** under per-spec alternatives
(PR #25) from recorded `actual_calls`; single-call tasks keep their runtime
scores (their rules didn't change). The snapshot preserves `score_at_runtime`
per config for auditability. The effect: **9 of 12 configs were rescued on at
least one parallel task; zero regressions; title-guess filters stay 0.**
Per-config deltas (runtime → final):

| Config | Runtime | Final | Δ | Rescored task(s) |
|---|---|---|---|---|
| gpt-4o-mini | 13 | 14 | +1 | halverson_dispute_02 |
| claude-haiku-4-5 | 16 | 18 | +2 | both parallel tasks |
| gpt-5.5 | 20 | 21 | +1 | halverson_dispute_02 |
| claude-sonnet-4-6 | 16 | 18 | +2 | both parallel tasks |
| claude-opus-4-6 | 18 | 20 | +2 | both parallel tasks |
| claude-opus-4-8 | 19 | 20 | +1 | tri_counterparty_parallel_01 |
| Fable 5 (low) | 19 | 20 | +1 | tri_counterparty_parallel_01 |
| Fable 5 (medium) | 19 | 20 | +1 | tri_counterparty_parallel_01 |
| Fable 5 (high) | 19 | 20 | +1 | tri_counterparty_parallel_01 |

(gpt-5.4-nano, gpt-5.4-mini, gemma had no rescored tasks — their runtime score
stood. gemma notably passed both parallel tasks *at runtime*, no rescue needed.)

### 4.6 Keyword-match leniency

Free-text `query` args are scored by keyword-contains (substring), with no NLP
(Design Decision 5). This has inherent leniency — a query containing the
expected keyword as a substring of a larger topic passes. Per-spec parallel
alternatives inherit the same leniency. We control both authoring sides, but it's
a real softness on the `query` arg; disclose it.

### 4.7 Latency is coarse

Mean over 25 sequential calls, one machine, one afternoon. Latency comparisons
are directional, not benchmarked. (gemma's 33.9s mean is local-hardware-bound,
not a model-quality signal.)

---

## 5. WHAT THE r2 RESULTS SHOW — quotable figures, verified

A tight set of claims, each with its supporting number. Every figure below
matches `viz/data/runs/2026-06-12-r2.json`.

### 5.1 The cost king vs the accuracy leader

- **Accuracy leader: gpt-5.5 — 21/25 (84%), CPC $0.0119.** The only config above
  20/25. Its single miss on `easton_amendment_03b` is the same landlord-listing
  jump everyone else takes.
- **CPC king at quality: claude-haiku-4-5 — 18/25 (72%), CPC $0.0042.** It is
  **2.85× cheaper per correct than gpt-5.5** while giving up 3 tasks — and it
  ties sonnet-4-6 (also 18/25) at **~1/3 of sonnet's CPC** ($0.0042 vs $0.0126).
  Haiku needed no decompose, no summarize_document, and produced textbook
  filter-scoped fan-outs on both parallel tasks.
- **The squeeze in one line:** the most accurate model and the most cost-
  efficient-at-quality model are different models, and the gap between them
  ($0.0042 → $0.0119, **2.85×**) is the whole reason CPC exists.

### 5.2 The free-but-weaker local baseline

- **gemma4:12b — 13/25 (52%), $0 cost, CPC $0 (local).** Free, but the weakest
  config. Its 13 is "floor + parallel": it clears the easy floor and passes both
  parallel tasks *at runtime* (the only config needing no rescue on either), but
  fails almost everything requiring multi-turn state tracking (1/5 on the
  Halverson chain, 1/4 on vendor_autorenew). Mean latency 33.9s (local hardware).
  **Keep it off the dollar Pareto frontier** — "$0 because local" is not a
  frontier win, and presenting it as the cost champion would mislead.

### 5.3 Distractor behavior (the discrimination axis paid off — narrowly)

- **8 distractor picks total, ALL `summarize_document`.** Concentrated on
  sonnet-4-6 (6 picks: 4× on `halverson_dispute_03`, 1× on `_04`, 1× on
  `stonebridge_term_01`); gpt-4o-mini and gemma take 1 each, both on
  `stonebridge_term_01`.
- **The three categorically-wrong distractors (web_search, tag_document,
  create_alert) drew ZERO picks. `search_history` drew ZERO picks.** Read: the
  semantic near-miss (summarize_document shadowing get_document) is the only
  distractor with teeth at this frontier; categorically-wrong tools are below
  the discrimination threshold for every config. search_history's zero is
  *expected* (Axis D held), not a bug.

### 5.4 The effort knob is a tax, not a strategy (interpretive — keep separate from facts)

- Fable 5 scores an **identical 20/25 at low, medium, and high effort**, while
  cost rises monotonically: **$0.8062 → $0.8451 → $0.8823** (CPC $0.0403 →
  $0.0423 → $0.0441). The knob buys tokens, not retrieval strategy, so **CPC
  strictly worsens with effort.** (Nuance, not a contradiction: the *path*
  differs — Fable low fails `easton_amendment_03b` but passes
  `vendor_autorenew_02`; medium/high invert it. Net score is identical.)

### 5.5 A generational personality split (interpretive — narrative reading, label it)

- The **4.6 generation** (sonnet-4-6, opus-4-6) are the *only* two configs that
  pass the decompose-on-cue task, and sonnet-4-6 is the heaviest
  summarize_document consumer (6 of 8 total picks). They read as tuned toward
  orchestration-style tool use.
- The **4.8 / 5.x generation** (opus-4-8, Fable, gpt-5.5) skip explicit
  decomposition and go straight to retrieval. Consistent with decompose-on-cue
  being RL'd out of newer assistants rather than a capability the ladder climbs.
- **Caveat for the writer:** §5.4 and §5.5 are *interpretive narrative*, not raw
  data. Keep them visibly distinct from the Facts Table; they're defensible
  readings, but they are readings.

---

## 6. Suggested hooks / angles (for the prose pass)

1. **"Accuracy is a leaderboard; CPC is an invoice."** Lead with the flat
   accuracy ceiling (six configs within one task) and reveal the 10× cost spread
   hiding underneath it.
2. **"The most accurate model and the cheapest-per-correct model are not the
   same model"** — and that 2.85× gap is the entire argument for the metric.
3. **"A benchmark everyone passes ranks nothing."** The 10/15-passed-by-everyone
   saturation story → the four hardening axes → a rankable 13→21 spread. This is
   the methodology spine.
4. **"The honest part."** A benchmark earns trust by disclosing its soft spots:
   two adjudicated tasks, a reasoning-token apples-to-oranges, an offline
   rescore with preserved provenance. Lead *into* the threats section as a
   feature, not an appendix.
5. **"The effort knob is a tax."** Fable's identical 20/25 across three efforts
   at monotonically rising cost — a concrete, counterintuitive, CPC-native
   finding.

---

## 7. FACTS TABLE — verified, quote directly (no re-derivation needed)

All values from `viz/data/runs/2026-06-12-r2.json`. Sorted by CPC.

| Config | Provider | Score /25 | Accuracy | Cost (USD) | **CPC (USD)** | Over-call rate | Mean latency (s) |
|---|---|---|---|---|---|---|---|
| gemma4:12b | ollama | 13 | 0.52 | 0.0 | **$0 (local)** | 0.00 | 33.94 |
| gpt-4o-mini | openai | 14 | 0.56 | 0.00541 | **0.000386** | 0.04 | 1.50 |
| gpt-5.4-nano | openai | 15 | 0.60 | 0.008299 | **0.000553** | 0.16 | 1.01 |
| gpt-5.4-mini | openai | 14 | 0.56 | 0.029989 | **0.002142** | 0.12 | 1.01 |
| **claude-haiku-4-5** | anthropic | **18** | 0.72 | 0.074899 | **0.004161** | 0.24 | 1.62 |
| **gpt-5.5** | openai | **21** | 0.84 | 0.249485 | **0.011880** | 0.44 | 2.77 |
| claude-sonnet-4-6 | anthropic | 18 | 0.72 | 0.227667 | **0.012648** | 0.16 | 3.64 |
| claude-opus-4-6 | anthropic | 20 | 0.80 | 0.389795 | **0.019490** | 0.28 | 3.83 |
| claude-opus-4-8 | anthropic | 20 | 0.80 | 0.429825 | **0.021491** | 0.24 | 2.43 |
| Fable 5 (low) | anthropic | 20 | 0.80 | 0.8062 | **0.040310** | 0.12 | 4.82 |
| Fable 5 (medium) | anthropic | 20 | 0.80 | 0.8451 | **0.042255** | 0.24 | 5.52 |
| Fable 5 (high) | anthropic | 20 | 0.80 | 0.8823 | **0.044115** | 0.24 | 6.13 |

**Derived ratios (verified):**
- gpt-5.5 CPC ÷ haiku CPC = **2.85×** (insights doc rounds this to "3×" — fine
  for prose, exact figure is 2.85).
- Fable 5 (low) CPC ÷ haiku CPC = **9.69×** (doc rounds to "10×").
- opus-4-6 CPC ÷ gpt-5.5 CPC = **1.64×**; Fable 5 (high) CPC ÷ gpt-5.5 CPC =
  **3.71×** → validates the "1.6–3.7× gpt-5.5's CPC" band for the dominated
  20/25 cluster.
- Score spread: **13 → 21 over 25 tasks** (gemma → gpt-5.5).
- Reasoning tokens (within-provider only): gpt-5.5 = 949 (real); all Anthropic =
  0 (folded into output); gemma = 2833 (whitespace word-count, not tokens).
- Distractor picks: **8 total, all summarize_document** (sonnet 6, gpt-4o-mini
  1, gemma 1). web_search / tag_document / create_alert / search_history = 0.
- Rescore: **9/12 configs rescued, 0 regressions** (see §4.5 table for per-config
  deltas).
- Meta: n_tasks = 25, n_configs = 12; chains = halverson_dispute (5),
  easton_amendment (4), vendor_autorenew (4); parallel tasks =
  halverson_dispute_02 (7/12), tri_counterparty_parallel_01 (9/12).

**Pareto frontier (dollar):** gpt-4o-mini → gpt-5.4-nano → haiku-4-5 → gpt-5.5.
Everything at/above sonnet's price is dominated. gemma's $0 is local, off-frontier.

---

## 8. Figure-hygiene corrections (what to NOT carry over)

For the writer's protection — small imprecisions in upstream prose that should
not propagate:

1. **"~3×" and "~10×"** in `insights-2026-06-12-r2.md` §1 are rounded; the exact
   ratios are **2.85×** and **9.69×**. Use the exact numbers if precision is
   wanted; the roundings are not errors, just rounding.
2. **The roadmap's "9 → 19" spread is the pre-r2, 23-task scoreboard** — NOT r2.
   r2 is **13 → 21 over 25 tasks**. Do not quote 9→19 as the canonical result.
3. **gemma CPC = "$0 (local)," not "$0 frontier win."** Always carry the "(local)"
   qualifier and keep gemma off the dollar Pareto frontier.
4. **reasoning_tokens are not cross-provider comparable** (§4.2). Never put
   gpt-5.5's 949, Anthropic's 0, and gemma's 2833 on the same chart axis.
5. **§5.4 / §5.5 are interpretive**, not facts-table material. Keep the
   "effort = tax" and "generational personality" readings visibly separated from
   the verified numbers.
