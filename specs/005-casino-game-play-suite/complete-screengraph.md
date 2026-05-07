# Complete screen-graph of the entire app

Goal: a single DB object — nodes = screens, edges = actions — that the agent always improves and updates, and a human periodically reviews. This doc inventories what's already there and what's missing to get from "graph along goal paths" to "complete graph of the app."

## What you already have

The bones of the graph are there:
- `screen_signatures` (nodes), `screen_elements`, `screen_transitions` (edges with confidence + decay)
- `signature_proposals` staging + operator promotion
- Auto-recorder writes edges on every verified tap
- Path planner with read-time confidence decay (`shared/screen_graph._effective_confidence`)

That's enough to grow a graph **along goal paths**. It is not enough to grow a *complete* one. Below is the gap list, grouped into five pillars + smaller gaps + a phased plan.

## Five pillars missing

### 1. Coverage — exploration as a first-class mode

Goal-driven traversal only ever visits screens needed for the goal. A casino app has 200+ screens; "play slingo" touches ~20.

- New intent: **`intent_explore`** — picks the highest-information-gain `(screen, untried_action)` pair, attempts it, records, repeats until budget.
- New table: **`screen_action_frontier(screen_sig, element_id, attempted_count, succeeded_count, last_attempted_at)`**. Populated on every visit by enumerating interactive elements from the page-source.
- Exploration policy: priority queue — *unattempted > low-confidence > stale*. ε-greedy mix in normal runs (90% goal, 10% explore an adjacent unknown edge).
- Halt rules: max screens visited, max actions attempted, max balance loss, loop detector (same screen 5× in 20 steps).

### 2. Edge expressivity — what an "action" actually is

Today an edge is implicitly `tap`. Real apps need:

- **`edge_kind`** enum: `tap | back | system_back | swipe_{l,r,u,d} | longpress | type | scroll | deeplink`.
- **`side_effect`**: `idempotent | reversible | destructive`. Destructive edges (deposit_submit, withdrawal, KYC submit, account_close) are blacklisted from explore, allowed only inside an explicitly authorized intent.
- **`precondition`** JSON over RuntimeFacts: `{logged_in: true, jurisdiction: NJ, balance>0, flag.X: on}`. Same physical edge, different reachability.
- **Stochastic outcomes** — one `(start_sig, action)` can land on N different end_sigs (A/B tests, RNG, banner rotation). Replace the 1-to-1 row with `transition_outcomes(start_sig, action, end_sig, observed_count)`.

### 3. Logical identity — the graph that survives releases

Every UI tweak changes signature hashes. Without a layer above the physical fingerprint, the graph wipes itself every release.

- **`logical_screens(logical_id, canonical_name)`** — operator-named, stable. e.g., `lobby_home`, `slingo_base_grid`.
- `screen_signatures.logical_id` FK (nullable; set on promotion).
- Same for elements: `logical_elements(logical_id, canonical_label)` — "the spin button" is one thing across builds.
- Promotion script extended: `accept_signature_proposal.py <hash> --as <logical_name>` either creates a new logical node or attaches a new physical variant to an existing one.

This is what makes the "single DB object always improving" durable across releases.

### 4. Provenance — so review is meaningful

For periodic human review you need to see when/where/how each edge entered the graph.

- New table **`transition_observations(sig_pair, action, run_id, build_env, ts, outcome)`** — append-only log; the summarized row stays in `screen_transitions`.
- Add `last_observed_at`, `last_observed_build`, `observed_count`, `failed_count` to both `screen_signatures` and `screen_transitions`.
- Staleness scoring exposed in queries (green/yellow/red) so the reviewer's eye lands on what matters.

### 5. Reviewability — the surface a human actually uses

A graph that can't be rendered won't get reviewed.

- **`scripts/render_graph.py [--platform android --build cert]`** → static HTML (Mermaid for small subgraphs, d3 force-layout for full app). Filterable by confidence, age, intent. Click node → screenshot evidence; click edge → list of runs that observed it.
- **`scripts/graph_diff.py <build_a> <build_b>`** → markdown: added/removed/changed nodes & edges, coverage delta, regressions. Drives the per-release review.
- Coverage metrics: % of nodes ≥ 0.9 conf, % of edges visited in last 7d, dead-ends (no out-edges), unreachable nodes (no in-edges from main graph), staleness count.

## Smaller-but-load-bearing gaps

| Gap | Fix |
|---|---|
| Modals/drawers as overlays vs. screens | `screen_signatures.parent_sig` (nullable). Path planner treats overlays specially: dismiss → parent. |
| Deeplinks (`app://game/slingo_classic`) | `deeplinks(uri, target_logical_id)` — zero-cost edges from anywhere. Speeds exploration enormously. |
| Hub/back-stack confusion | `is_hub: bool` on signatures (bottom nav, lobby home). Path planner penalizes bouncing through hubs. |
| Tombstones for removed screens | `screen_signatures.deprecated_at` instead of delete; preserves history for diffs. |
| Read-only prod mode | `RuntimeFacts.constraints.write_allowed=false` → only verify existing edges; never propose new actions. |

## Phased plan (3 sprints)

**Sprint 1 — coverage & expressivity**
- Add `edge_kind`, `side_effect`, `precondition` to `screen_transitions`.
- Add `screen_action_frontier` table + auto-populate on every screen visit.
- Add `intent_explore` with budget guard (max_screens, max_loss_usd).
- Add destructive-edge blacklist + read-only-prod gate.

**Sprint 2 — identity & provenance**
- Add `logical_screens` + `logical_elements` tables; backfill from accepted proposals.
- Extend `accept_signature_proposal.py` to attach to an existing logical node or create a new one.
- Add `transition_observations` log; backfill last-observed fields on summary rows.

**Sprint 3 — review surface**
- `render_graph.py` → static HTML viewer.
- `graph_diff.py` → release-over-release diff in run-report JSON.
- Weekly cron: run `intent_explore` against cert with a fixed budget; emit graph diff vs last week to a Slack/PR channel.

After Sprint 1 the graph grows on its own beyond goals. After Sprint 2 it survives releases. After Sprint 3 a human can review it in 15 min/week and accept/reject the week's deltas.

## What you do **not** need to add

- A separate "skill" primitive — multi-step recipes are paths through the graph.
- A graph DB / Neo4j — SQLite + indexes is fine at this scale (low thousands of nodes per platform).
- ML on the graph — exploration policy is a priority queue; visualization is graphviz/d3. Nothing learned beyond what `effective_confidence` already does.
