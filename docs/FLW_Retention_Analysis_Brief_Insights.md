# FLW Retention & Engagement — Executive Analysis

*Connect Interviews programme · per-FLW, cross-cohort · data as of 2026-08-11 · build 2026-08-11 21:51 UTC · dashboard render v151*

*Universe: **1,441 unique front-line workers (FLWs)** who started ≥1 interview · 100% have demographics · every metric dedups the worker across all cohorts/arms they were part of. Generated from the same payload the dashboard's **FLW Retention** tab embeds, so every figure here matches what is on screen.*

## Why this analysis exists

Every other view of this programme is cohort-level — how a study arm performed. This one looks at the programme through the worker: one row per unique FLW, their interview history stitched across every cohort and arm they touched. Most workers are re-used across studies, so the worker's cumulative experience — not any single cohort — is what tells us who the programme retains and where it loses people.

## How to read the numbers (please read this first)

**Two ways of saying a worker “finished”.** They are different questions and are never interchangeable:

- **Finished at least one schedule** — "have they ever completed a full cohort schedule?" Beware: a worker in three cohorts has three chances to clear this bar, so this number rises with how many cohorts someone was put in, even if nothing about the worker changed. Useful for describing, misleading for comparing.
- **Per-cohort finish rate** — “of the schedules they were actually given, what share did they complete?” Worked out per person (schedules completed ÷ schedules enrolled in) and then averaged across the group. This is the fair one, and it is the number to quote when comparing groups.
**Two ways of grouping workers.** Both appear below and they are not comparable with each other:

- **Personas** — what a worker has done over their **whole history** (Champion, Steady finisher, One-and-done…). Fixed: a persona does not change as time passes.
- **Engagement tiers** — where a worker sits **right now** (Highly engaged, Engaged, Slipping, Gone quiet, Lost). A worker moves between tiers over time. Different words are used deliberately so the two are never mixed up.
*And one limitation that applies to everything here: this is observational data. It can show what goes together with finishing; it cannot show what causes finishing. Where a number is tempting to read causally, the text says so explicitly.*

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

**78% of workers have completed at least one full schedule** — Champions 19% + Steady finishers 59%, the two personas defined by having finished. Genuine early loss is **9%** (131 workers), the One-and-done segment that §3 profiles. **Important:** that 78% is the generous measure — the one §2 shows is inflated by how many cohorts a worker was put in. On the like-for-like per-cohort measure, workers complete **58%** of the schedules they were actually given. Quote 58% as the programme's headline finish figure, not 78%. *(Both are whole-history views. The tier table below describes the same people's CURRENT activity and is not comparable with either.)*

*Engagement tiers answer a **different question** from the personas above. A tier is where a worker sits **right now** — a band blending how recently they interviewed with their completion rate and answer depth — so a worker moves between tiers over time. A persona describes their **whole history** and does not move. The two use deliberately different words so they are never read as the same grouping.*

| Engagement tier (activity right now) | Workers | % of all |
|---|---|---|
| Highly engaged | 297 | 21% |
| Engaged | 576 | 40% |
| Slipping | 446 | 31% |
| Gone quiet | 101 | 7% |
| Lost | 21 | 1% |

**61% of workers sit in the top two tiers** (Highly engaged + Engaged). This answers a different question from the 78% above: that counted who has ever finished a schedule, this describes how active they are right now. "Slipping" is mixed - of its 446 workers, 295 have actually finished a schedule and are simply inactive now, while 89 are one-and-done workers - so it should not be read as uniformly benign.

*Tier recency is measured against the freshest session in the dataset rather than the wall clock, so these shares do not drift when a data pull runs late.*

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

The first row is the trap. "Finished ≥1 schedule" is a **maximum over a worker's cohorts** - a worker in three cohorts gets three independent chances to clear the bar — so it rises with cohort count even if nothing about the worker changed.

Compare the two rows directly. The headline measure gives a **44-point** gap (88% − 44%). The fair measure gives **18 points** (62% − 44%). So 44 − 18 = **26 points** of the original gap vanish once you stop rewarding a worker for having been put in more cohorts. That is 26 ÷ 44 = **59% of the headline gap**, which is arithmetic rather than behaviour. To be explicit: 59% is that share of the gap — it is NOT an average of the two rates.

*Where the 62% itself comes from: for each multi-cohort worker, take the schedules they completed divided by the schedules they were enrolled in, then average that across all 1,110 of them. Single-cohort workers have exactly one schedule, so their fraction can only be 0 or 1 and the average collapses to "what share finished their one schedule" — which is why both of their measures read 44%.*

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

**Read each row separately, not stacked.** Each line above is measured on its own, so they cannot be added up into one profile. Only **35 of the 131 one-and-done workers (27%)** are Sokoto *and* chew *and* single-cohort at the same time. The single strongest signal is Sokoto.

On how far workers get: of those whose schedule even *contains* interview 3, **86%** reach it (893 of 1,039). Quoting it against the whole population instead gives 62%, which understates retention because most workers are in short cohorts that stop before interview 3 — that is schedule length, not attrition.

On attrition, two numbers that are often confused: **9% (131 workers) is the clean early-loss figure** — they did one interview and vanished. Separately, **316 workers (22% of all) have not finished any schedule** — most of them engaged repeatedly first. So 9% is who we lost immediately; 22% is who has not got there yet. The recovery list is drawn from the second group.

## 4. Is early answer depth associated with finishing?

Splitting workers at the median depth of their **first session only** (123 words) — first session, so the predictor does not contain the outcome:

| Group | Workers | Per-cohort finish rate | Finished ≥1 schedule | First-session depth |
|---|---|---|---|---|
| Above-median depth | 725 | 61% | 82% | 222 words |
| Below-median depth | 716 | 55% | 74% | 80 words |

Read those percentages carefully: **61% means that group completed, on average, 61% of the schedules they were enrolled in** — it does NOT mean they finished everything. Workers in both halves finish some of their schedules and not others.

The difference between the halves is **6 points** on the like-for-like measure (61% vs 55%). On the looser "finished ≥1" reading it is 82% vs 74% — a gap of 8 points. It is a real association and the strongest early signal available, but it is modest — and the deeper group also happens to be in more cohorts, so the two effects are tangled together. Treat first-interview support as the leading hypothesis to **test**, not an established lever.

## 5. Geography and partner — one finding, not two

| State | Workers | Per-cohort finish rate | Finished ≥1 schedule | Answer depth |
|---|---|---|---|---|
| Borno | 367 | 65% | 89% | 237 words |
| Kebbi | 399 | 64% | 84% | 257 words |
| Bauchi | 384 | 56% | 77% | 230 words |
| Sokoto | 291 | 42% | 58% | 172 words |

| Implementing partner | Workers | Per-cohort finish rate | Finished ≥1 schedule | Answer depth |
|---|---|---|---|---|
| COWACDI | 765 | 65% | 86% | 247 words |
| EHA | 675 | 50% | 69% | 205 words |

These two tables are **the same finding cut two ways**. In this data the partners and the states are nested (**COWACDI** serves Borno and Kebbi; **EHA** serves Bauchi and Sokoto), so a state's result and its partner's result are the same observation — the data cannot tell you whether the difference is geography, the partner's ways of working, or something the two share. Treat "the EHA gap" and "the Sokoto gap" as one issue, and do not count them as two independent findings or give them two separate workstreams.

The spread is wide: Borno 65% vs Sokoto 42% per-cohort — 23 points.

By cadre, results are much tighter: 52–65% per-cohort across 8 cadres. The largest is **chew (558 workers) at 56%**. Because the cadre spread is narrow while the geography spread is wide, cadre looks like the weaker lever of the two.

## 6. The variation is LOCAL, not state-level — and that changes what to do

§5 compared states and partners because those are the units we manage by. But splitting the same workers by **LGA** (local government area, 24 of them with enough workers to measure) shows the state framing is the wrong altitude:

| State | Per-cohort finish | Spread between its own LGAs | LGAs measured |
|---|---|---|---|
| Borno | 65% | 26 points | 6 |
| Kebbi | 64% | 36 points | 6 |
| Bauchi | 56% | 34 points | 6 |
| Sokoto | 42% | 24 points | 6 |

**The gap between the best and worst state is 23 points. The gap between the best and worst LGA is 47 points.** Internal spreads run 24–36 points, so in 4 of the 4 states the variation inside the state is at least as large as the entire gap between states. The best-performing LGA in Sokoto (our weakest state, 55%) beats several LGAs in our strongest one.

*Why this matters for the decision: §5 correctly says we cannot separate partner from state, because they are perfectly nested — and that looked like a dead end. This resolves it from the other direction: whatever is driving performance is mostly operating BELOW the state, so a partner-wide or state-wide explanation is the wrong shape regardless of which one you blame. The unit of action is the LGA, and the question to ask is what the strong LGAs do differently from the weak ones in the SAME state under the SAME partner.*

## 7. Two things about how workers work that track with finishing

**Working alone is a disadvantage.** Grouping workers by how many colleagues share their settlement — the finest geography we hold — gives a clean gradient in the expected direction. This is the one factor here that the community-health-worker literature consistently flags (informal peer support), so it is a hypothesis we had reason to test rather than one found by trawling:

| Co-workers in the same settlement | Workers | Per-cohort finish | Finished ≥1 |
|---|---|---|---|
| Only worker in settlement | 553 | 52% | 72% |
| 2-4 in settlement | 558 | 59% | 79% |
| 5+ in settlement | 330 | 64% | 87% |

**Falling behind the schedule shows up early and gets worse.** Each worker's typical gap between interviews is measured against what their own schedule asks for, so subgroups with 3-day and 14-day cadences are compared fairly:

| Pace vs their own schedule | Workers | Per-cohort finish | Finished ≥1 |
|---|---|---|---|
| On/ahead of schedule | 1,041 | 68% | 91% |
| Somewhat slow | 112 | 49% | 74% |
| Very slow | 153 | 41% | 59% |
| Single interview (no pace) | 135 | 3% | 3% |

*Note the last row is workers with a single interview, who have no pace to measure — they are 0% by definition, not by behaviour. Among workers with a rhythm to measure, the gradient is monotonic.*

*Why these two and not others: both are measurable before a worker is lost, which makes them usable as early warnings rather than post-mortems: peer density is known at assignment, and pace is visible after two interviews. We also tested response *consistency* (longest silence versus a worker's own typical gap) and onboarding delay (training date to first interview) and are not reporting either: consistency does not separate cleanly in this data, and onboarding delay has no variation to analyse — all but 20 workers start within a week. Education and first language showed no relationship to finishing either.*

*This is the findings-only cut of a longer analysis. It deliberately omits the recovery list, the recommendations with their confidence levels, and the method and limitations appendix — ask for the full brief before acting on anything here.*
