# FLW Retention & Engagement — Executive Analysis

*Connect Interviews program · per-FLW, cross-cohort · data as of 2026-08-07 (matches live dashboard v140)*
*Universe: **1,441 unique front-line workers (FLWs)** who started ≥1 interview · 100% demographic coverage · every metric dedups the worker across all cohorts/arms they were part of.*

> The Word version (`FLW_Retention_Analysis_Brief.docx`) and this file are both generated from the same payload the dashboard embeds, so all figures match the live **FLW Retention** tab.

---

> ## ⚠️ Correction notice — 2026-08-07 (read before citing §2 or §4)
>
> A statistical audit of this analysis found that two of its headline claims are artifacts of how "finished" was
> measured. **Do not circulate §2 or §4 in their current form.** Both the dashboard tab and the brief generator have
> been corrected; this document regenerates with the corrected figures on the next data refresh.
>
> 1. **§2 / exec-summary #2 — "re-use compounds engagement, finish rate 44% → 88%" is not supported.**
>    "Finished" here means *finished at least one* of a worker's cohort schedules. That is a maximum over cohorts, so
>    a worker in three cohorts gets three independent chances to clear the bar and the rate rises even if nothing
>    about them changed. On the like-for-like measure — the share of *their own* schedules a worker completes —
>    the live figures are **44% (single) vs 61% (multi)**: a real 17-point difference, but roughly 60% of the
>    44-point headline gap was arithmetic rather than behaviour. Completion rate (0.88 vs 0.89) is flat. And
>    "was re-invited" is itself an outcome of how a worker performed the first time, so even the residual gap
>    is not evidence that re-use *causes* finishing.
> 2. **§4 / exec-summary #4 — "first-interview depth predicts finishing, 88% vs 68%" overstates a real but modest
>    effect.** The split was computed on each worker's *lifetime* average answer depth across every interview, not
>    their first interview, so the predictor partly contained the outcome. Re-run on the first session only and
>    against the per-cohort finish rate, the gap is roughly **5 points**, not 20. Worth testing as a lever; not
>    established as one.
>
> Two further wording corrections: the persona previously called **"Slow-but-finishing"** has finished *nothing* by
> construction (it is reachable only after both "finished" branches fail) and is now **"Partial progress"**; and
> **"Slipping is largely benign"** is not accurate — that tier also holds a large share of the one-and-done group.
>
> Method note: engagement recency is now measured against the freshest session in the dataset rather than the wall
> clock, so these figures no longer drift when a data pull runs late.

---

## Why this analysis exists

Every other view of this program is **cohort-level** — how a study arm performed. This one looks at the program **through the worker**: one row per unique FLW, their interview history stitched across every cohort and arm they touched. That matters because **most workers are re-used across studies** — so the worker's cumulative experience, not any single cohort, drives whether they stay engaged. This lens tells us who the program retains, when it loses people, and what to do about it.

---

## Executive summary

1. **Engagement is fundamentally healthy.** **78%** of workers are reliable engagers (19% Champions, 59% Steady finishers). Genuine early loss is small — **9%** one-and-done.
2. **Re-using workers is our biggest engagement asset — and it compounds.** Finish rate climbs sharply from single- to multi-cohort workers (**44% → 88%**), and answer depth rises with it (168 → 246 words/session).
3. **The drop-off has a clear face.** One-and-done workers are disproportionately **Sokoto (49%), single-cohort (96%), and "chew" cadre (44%)** — first-time, single-exposure workers in one geography.
4. **The retention lever is the first interview.** Workers with above-median answer depth finish at **88%** vs **68%** below.
5. **The recoverable at-risk pool is small and targetable — 51 workers** (started, not finished, silent 14–60 days).

---

## 1. The engagement landscape

Behavioral personas (segments over the worker's whole history):

| Persona | Count | Share | What it means |
|---|--:|--:|---|
| **Champion** | 275 | 19% | Finishes, steady cadence, high depth — the backbone |
| **Steady finisher** | 850 | 59% | Completes their schedule reliably |
| **Slow-but-finishing** | 129 | 9% | Gets there, but with long gaps |
| **One-and-done** | 131 | 9% | Started once and stopped — the real early-loss group |
| Re-engager / Early dropper / Lapsed | 56 | ~4% | Small tails |

Engagement tiers (RFM blend of recency + completion + answer depth): **63% Champion/Solid** (26% + 37%), 29% Slipping, 8% At-risk/Lost. "Slipping" is largely benign — workers in finished short cohorts who are simply inactive now, not people who quit mid-schedule.

---

## 2. ⭐ The cross-cohort story (the standout finding)

The multi-arm design re-uses the same workers across studies — **77% are in ≥2 cohorts** (23% in 1, 42% in 2, 25% in 3, 9% in 4, 1% in 5+):

| Cohorts per worker | Workers | Share |
|---|--:|--:|
| 1 | 332 | 23% |
| 2 | 599 | 42% |
| 3 | 359 | 25% |
| 4 | 136 | 9% |
| 5+ | 15 | 1% |

Comparing **single- vs multi-cohort** workers: completion is flat (0.88 vs 0.89), while **finishing rises 44% → 88%** and **answer depth rises 168 → 246 words/session**. Repeat exposure builds commitment and richer engagement, with no sign of fatigue.

**Structurally, TRS is the gateway.** Almost every multi-arm worker started in the Training (TRS) cohort and was re-used into study arms — the top combination is `PANEL|TRS` (322), followed by TRS+2WT+ABT combinations. TRS is the program's on-ramp; workers who flow from it into further arms become the most engaged core.

> **Implication:** a stable, repeatedly-engaged worker panel is a competitive asset — deliberately re-invite proven workers rather than defaulting to fresh single-exposure recruitment.
> *(Caveat: the raw "finished" share is partly mechanical for multi-cohort workers — more cohorts = more chances to finish one — so completion and depth, which aren't subject to that bias, carry the cleaner signal; they agree.)*

---

## 3. Where the program loses people — and who they are

Genuine early loss is the **One-and-done** segment (131 workers, 9%). Not a random slice:

| Cut | One-and-done | Program overall |
|---|--:|--:|
| **Sokoto** (top state) | **49%** | 20% |
| **Single-cohort** | **96%** | 23% |
| **"chew" cadre** (top) | 44% | 39% |
| Median answer depth | **112 words** | Champions: 181 |

**The drop-off profile is a first-time, single-exposure worker in Sokoto, disproportionately "chew" cadre, who engaged shallowly on their one interview and didn't return.** This points at who to support (single-exposure Sokoto workers) and when (at/just after the first interview).

The depth curve (share reaching each interview: Int≥1 100% → Int≥2 88% → Int≥3 62%) partly reflects cohort schedule length — most workers are in shorter cohorts, so deeper steps largely mean "was this worker in a longer-schedule cohort," not attrition. The clean FLW-level attrition number is the **9% one-and-done**.

---

## 4. The retention lever: early engagement depth

Splitting the population at the median answer-depth:

| Group | Workers | Finish rate | Avg depth |
|---|--:|--:|--:|
| Above-median depth | 721 | **88%** | 323 words/session |
| Below-median depth | 720 | **68%** | 133 words/session |

A **20-point finish gap** tracks with how deeply a worker engages early — consistent with the longitudinal-survey literature, where a strong early experience is the dominant predictor of continuation. **The highest-leverage intervention is making the first interview(s) genuinely engaging** (prompt design, appropriate length, onboarding support).

---

## 5. Cross-cuts: geography, partner, cadre

**By state** — a 31-point spread:

| State | Workers | Finish rate |
|---|--:|--:|
| Borno | 367 | **89%** |
| Kebbi | 399 | 84% |
| Bauchi | 384 | 77% |
| **Sokoto** | 291 | **58%** |

Sokoto is the clear laggard and, per §3, where one-and-done concentrates — the priority geography for support.

**By implementing partner (LLO):** COWACDI **86%** vs EHA **69%** finish — the cohort-level partner gap, confirmed at the worker level.

**By FLW cadre:** chv 87%, "others" 86%, eht 85% lead; **the largest cadre, "chew" (558 workers), sits at 75%** — mid-pack but, by size, the single biggest opportunity to lift the program average.

---

## 6. The recoverable at-risk list

**51 workers** started, haven't finished, and have been silent **14–60 days** — recent enough to re-engage. Concentrated in **Sokoto (20), Bauchi (18)**, Kebbi (7), Borno (6). A small, concrete outreach list; a targeted nudge here is high-yield.

---

## 7. Recommendations

1. **Make the first interview the priority** — the strongest retention lever (88% vs 68%). Invest in prompt quality, length, and first-touch support, especially for first-time workers.
2. **Lean into worker re-use** — re-inviting proven workers compounds engagement (44% → 88% finish, single → multi-cohort). Build a returning-worker panel rather than defaulting to fresh single-exposure recruitment.
3. **Target Sokoto and the "chew" cadre** — where one-and-done concentrates. Pair them with the onboarding support that works elsewhere.
4. **Run the 51-worker recovery list now** — the fastest available win (heavily Sokoto + Bauchi).
5. **Investigate the EHA gap** — COWACDI retains ~17 points better; understanding why could lift EHA materially.

---

## Method & data

- **Grain:** one row per unique worker (`connect_id`), deduped across cohorts; metrics union the worker's sessions across every arm. Ties out to the canonical 1,441 started workers.
- **Engagement tier (RFM):** Recency + completion rate + answer depth, each 1–5. **Persona:** rule-based behavioral segment. **Finished:** completed all scheduled interviews in ≥1 cohort.
- **Sources:** CommCare trigger + session data · OCS sessions (depth) · Connect funnel · `flw_registration` demographics (100% coverage). Full per-worker detail: `flw_analysis.csv`. Live view: dashboard → **FLW Retention** tab (refreshes daily). This document and the `.docx` are generated from the same payload, so they always match the dashboard.
- **Caveats:** the multi-cohort "finished" share is upward-biased (§2 — completion & depth agree and are unbiased); the progression-depth curve conflates cohort schedule lengths (§3); `experience_years` in registration is unreliable (default values) and excluded.
