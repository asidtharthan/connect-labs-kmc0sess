# FLW Retention & Engagement — Executive Analysis

*Connect Interviews programme · per-FLW, cross-cohort · data as of 2026-08-11 · build 2026-08-11 18:18 UTC · dashboard render v147*

*Universe: **1,441 unique front-line workers (FLWs)** who started ≥1 interview · 100% have demographics · every metric dedups the worker across all cohorts/arms they were part of. Generated from the same payload the dashboard's **FLW Retention** tab embeds, so every figure here matches what is on screen.*

## Why this analysis exists

Every other view of this programme is cohort-level — how a study arm performed. This one looks at the programme through the worker: one row per unique FLW, their interview history stitched across every cohort and arm they touched. Most workers are re-used across studies, so the worker's cumulative experience — not any single cohort — is what tells us who the programme retains and where it loses people.

*Two things to hold on to before the numbers. First, there are **two different ways to say a worker "finished"**, and they answer different questions (§2). Second, this is observational data: it shows what is associated with finishing, not what causes it.*

## 1. The engagement landscape

Behavioural personas — rule-based segments over each worker's whole history:

| Persona | Workers | Share | What it means |
|---|---|---|---|
| Champion | 276 | 19% | Finishes, steady cadence, high answer depth — the backbone |
| Steady finisher | 849 | 59% | Completes at least one full schedule reliably |
| Partial progress | 130 | 9% | Over half their triggered interviews done, but no schedule finished yet |
| Re-engager | 34 | 2% | Went silent, then came back |
| Early dropper | 16 | 1% | Shallow start, left early |
| One-and-done | 131 | 9% | Started once and stopped — the genuine early-loss group |
| Lapsed | 5 | 0% | Inactive, nothing finished |

**78% have completed at least one full schedule** (Champions 19% + Steady finishers 59%). Genuine early loss is **9%** (131 workers) — the One-and-done segment, which §3 profiles.

*Engagement tiers answer a **different question** from the personas above. A tier is where a worker sits **right now** — a band blending how recently they interviewed with their completion rate and answer depth — so a worker moves between tiers over time. A persona describes their **whole history** and does not move. The two use deliberately different words so they are never read as the same grouping.*

On that basis: 61% sit in the top two tiers. Full spread — 21% Highly engaged, 40% Engaged, 31% Slipping, 7% Gone quiet, 1% Lost. "Slipping" is mixed: it holds both finishers who are simply inactive now and a large share of the one-and-done group, so it should not be read as uniformly benign. Tier recency is measured against the freshest session in the dataset rather than the wall clock, so these shares do not drift when a data pull runs late.

## 2. Re-use across cohorts — and the measurement trap

The multi-arm design re-uses the same workers across studies: **77%** are in ≥2 cohorts.

| Cohorts per worker | Workers | Share |
|---|---|---|
| 1 | 331 | 23% |
| 2 | 600 | 42% |
| 3 | 358 | 25% |
| 4 | 137 | 10% |
| 5 | 13 | 1% |
| 6 | 2 | 0% |

| Measure | Single-cohort workers | Multi-cohort workers | What it asks |
|---|---|---|---|
| Finished ≥1 schedule | 44% | 88% | Have they ever completed anything? |
| Per-cohort finish rate | 44% | 62% | Of the schedules they were given, how many did they complete? |
| Completion rate | 0.88 | 0.89 | Of interviews they were sent, how many did they finish? |
| Answer depth | 168 words/session | 245 words/session | How much do they actually say? |
| Workers | 331 | 1,110 |  |

The first row is the trap. "Finished ≥1 schedule" is a **maximum over a worker's cohorts** — a worker in three cohorts gets three independent chances to clear the bar — so it rises with cohort count even if nothing about the worker changed. It shows a 44-point gap. On the like-for-like measure, the gap is **18 points** (44% vs 62%), so roughly **59% of the headline gap is arithmetic rather than behaviour**.

What re-used workers clearly do differ on is **depth: 168 → 245 words/session**, while completion rate is essentially unchanged (0.88 vs 0.89).

*Causal caution: being re-invited is itself an outcome of how a worker performed the first time, so even the residual difference is not evidence that re-using a worker causes them to finish more. Re-use is operationally valuable — these are known, trained, available workers who answer at greater length — but do not budget for a finish-rate gain from re-use itself.*

Most common arm combinations: PANEL|TRS (322), 2WT|ABT1-B|TRS (87), 2WT|ABT2-B|EXT|TRS (70), 2WT|ABT2-B|TRS (70). (The arm set is unordered in this data, so we can say which arms co-occur, not which came first.)

## 3. Where the programme loses people — and who they are

Genuine early loss is the One-and-done segment: **131 workers (9%)** who started exactly one interview and never returned. They are not a random slice. Each row below compares the segment against that group's share of the whole population, so a share is only notable if it exceeds the base rate:

| Cut | One-and-done | Programme base rate | Over-represented |
|---|---|---|---|
| Sokoto (top state) | 49% | 20% | ×2.5 |
| Single-cohort | 96% | 23% | ×4.2 |
| chew (top cadre) | 44% | 39% | ×1.1 |
| Median first-session depth | 112 words | 123 words (all workers) |  |

Read together, the drop-off profile is a first-time, single-exposure worker in one geography, engaging shallowly on their single interview and not returning.

On how far workers get: of those whose schedule even *contains* interview 3, **86%** reach it (893 of 1,039). Quoting it against the whole population instead gives 62%, which understates retention because most workers are in short cohorts that stop before interview 3 — that is schedule length, not attrition. The clean worker-level attrition figure is the 9% one-and-done.

## 4. Does early answer depth predict finishing?

Splitting workers at the median depth of their **first session only** (123 words) — first session, so the predictor does not contain the outcome:

| Group | Workers | Per-cohort finish rate | Finished ≥1 schedule | First-session depth |
|---|---|---|---|---|
| Above-median depth | 725 | 61% | 82% | 222 words |
| Below-median depth | 716 | 55% | 74% | 80 words |

That is a **6-point** difference on the like-for-like measure (74% vs 82% on the looser "finished ≥1" reading). It is a real association and the strongest early signal available, but it is modest, and the deeper group is also in more cohorts — so treat first-interview support as the leading hypothesis to **test**, not an established lever.

## 5. Geography and partner — one finding, not two

| State | Workers | Per-cohort finish rate | Finished ≥1 schedule | Answer depth |
|---|---|---|---|---|
| Borno | 367 | 65% | 89% | 237 words |
| Kebbi | 399 | 64% | 84% | 256 words |
| Bauchi | 384 | 56% | 77% | 230 words |
| Sokoto | 291 | 42% | 58% | 172 words |

| Implementing partner | Workers | Per-cohort finish rate | Finished ≥1 schedule | Answer depth |
|---|---|---|---|---|
| COWACDI | 765 | 65% | 86% | 247 words |
| EHA | 675 | 50% | 69% | 205 words |

These two tables are **the same finding cut two ways**. In this data the partners and the states are nested (**COWACDI** serves Borno and Kebbi; **EHA** serves Bauchi and Sokoto), so a state's result and its partner's result are the same observation — the data cannot tell you whether the difference is geography, the partner's ways of working, or something the two share. Treat "the EHA gap" and "the Sokoto gap" as one issue, and do not count them as two independent findings or give them two separate workstreams.

The spread is wide: Borno 65% vs Sokoto 42% per-cohort — 23 points.

By cadre, results are much tighter: 52–65% per-cohort across 8 cadres. The largest is **chew (558 workers) at 56%**. Because the cadre spread is narrow while the geography spread is wide, cadre looks like the weaker lever of the two.

## 6. The recoverable at-risk list

**27 workers** started, have not finished any schedule, **were** offered a complete schedule, and have been silent 14–60 days — recent enough that a nudge is plausible. Concentrated in Sokoto (12), Bauchi (9), Kebbi (4), Borno (2). They are the recent slice of **316** unfinished workers, not the whole unfinished population — the rest have been silent longer than 60 days.

*Two caveats: the list is defined off the newest session in the dataset, so it moves as data refreshes; and it deliberately excludes workers the programme never finished triggering, who are unfinished through no choice of their own.*

## 7. What to do — and how confident we are

1. **Run the 27-worker recovery list now.** Small, named, and time-bounded — the only directly actionable item here. Confidence: high, it is a list, not an inference.
1. **Trial first-interview support, with a control group.** Above-median first-session depth is associated with a 6-point higher per-cohort finish rate. Confidence: moderate — real association, modest size, confounded with cohort count, so measure it rather than rolling it out.
1. **Treat the Sokoto / EHA gap as one investigation.** It is the largest effect in the data (23 points) and it is where one-and-done concentrates. Confidence: high that the gap is real, none at all on the cause — geography and partner cannot be separated here, so the next step is qualitative, not another cut of this data.
1. **Keep re-using proven workers for operational reasons** — known, trained, available, and they answer at greater length. Confidence: high on the operational value; do not forecast a finish-rate gain from re-use itself, because the headline gap is mostly arithmetic and re-invitation is itself an outcome of past performance.

## Method & data

- **Grain:** one row per unique worker (connect_id), deduped across cohorts; metrics union the worker's sessions across every arm. Ties out to the dashboard's canonical started-worker count (1,441).
- **Per-cohort finish rate** — the measure to quote. Of all the cohort schedules a worker was enrolled in, the share they completed. Unlike "finished ≥1 schedule", it does not rise just because a worker was in more cohorts.
- **Depth curve** is quoted against the workers whose schedule contains that interview, not the whole population, so a 2-interview worker is not counted as dropping out at interview 3.
- **Engagement tier (RFM):** recency + completion rate + answer depth, each scored 1–5, with recency measured against the freshest session in the dataset rather than today's date.
- **Personas** are rule-based. "Partial progress" means over half of triggered interviews completed but **no** schedule finished — it is not a slow finisher.
- **Limits.** Observational, so associations only. Small groups are pooled into an "Other / not recorded" row rather than dropped or published as their own rate. Figures move with each daily refresh; this document is generated from dashboard render v147.
- **Full per-worker detail** is in the flw_analysis.csv export; the dashboard's FLW Retention tab is interactive.
