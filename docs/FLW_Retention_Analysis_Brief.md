# FLW Retention & Engagement — Executive Brief

*Connect Interviews · per-FLW, cross-cohort analysis · as of 2026-08-06 · N = 1,424 FLWs who started ≥1 interview · 100% have demographics*

This looks at the program **through the front-line worker**, not the cohort — one row per unique FLW, with their interview timeline unioned across **every** cohort/arm they were part of. It answers: who engages, who drops, when, and what predicts staying.

---

## TL;DR (the five things that matter)

1. **Engagement is healthy.** 73% of FLWs are Champions or Steady finishers; only ~13% are genuine drop-offs (One-and-done / Early dropper / Lapsed).
2. **⭐ Re-use builds engagement — it doesn't fatigue it.** 64% of FLWs are in ≥2 cohorts, and those multi-cohort FLWs engage **deeper** (221 vs 165 words/session) at the same completion rate as single-cohort FLWs. Re-inviting the same workers is working *for* us.
3. **Early engagement depth is the single best predictor of finishing.** FLWs with above-median answer depth finish at **84%**; below-median finish at **61%**. How well the *first* interviews go decides retention.
4. **Geography drives a 32-point gap.** Finish rates: **Borno 85% · Kebbi 79% · Bauchi 68% · Sokoto 53%.** Sokoto is the clear place to intervene.
5. **COWACDI out-retains EHA at the worker level too** — 82% vs 62% finish — consistent with the cohort-level signal.

---

## 1. The engagement picture

| Behavioral persona | Share | Read |
|---|---|---|
| **Champion** (finishes, steady, deep) | 42% | the backbone |
| **Steady finisher** | 31% | reliable completers |
| **Slow-but-finishing** | 13% | get there, but with gaps |
| **One-and-done** (started once, stopped) | 12% | the real early-loss group |
| Early dropper / Lapsed / Re-engager | ~3% | small tails |

RFM engagement tiers (recency + completion + answer depth): **40% Champion/Solid, 48% Slipping, 12% At-risk/Lost.** "Slipping" is large but mostly reflects FLWs in finished short cohorts who are simply inactive now — not attrition.

## 2. ⭐ Cross-cohort: the standout, program-level finding

Our multi-arm design means most workers are re-used across studies — **64% are in ≥2 cohorts** (54% in 2, 10% in 3, 1% in 4).

| | Multi-cohort (n=918) | Single-cohort (n=506) |
|---|---|---|
| Completion rate | 0.87 | 0.90 |
| **Avg words / session (depth)** | **221** | **165** |

**Takeaway:** re-invited workers stay just as complete and engage *more deeply*. Re-use is an asset, not a fatigue risk — lean into a stable, repeatedly-engaged FLW panel.
*(Caveat: the raw "finished" share is higher for multi-cohort FLWs partly by construction — more cohorts = more chances to finish at least one — so we lead with depth and completion, which are bias-free.)*

## 3. Early engagement depth predicts retention (the lever)

Splitting FLWs at the median answer-depth:

| | Finish rate | Avg depth |
|---|---|---|
| Above-median depth (n=712) | **84%** | 285 words/session |
| Below-median depth (n=712) | **61%** | 116 words/session |

This matches the longitudinal-survey literature: a strong early experience predicts continuation. **The highest-leverage intervention is making the first interviews engaging** (prompt design, length, support at onboarding).

## 4. Where drop-off happens

Share of FLWs reaching each interview: **Int≥1 100% → Int≥2 85% → Int≥3 37%**. The Int2→Int3 step is steep, but note **most FLWs are in 2-interview cohorts**, so that step largely reflects *who was enrolled in a longer-schedule cohort*, not pure attrition. For true per-stage survival within a schedule, use the retention chart's "Reached previous interview" denominator (which holds ~90%). The clean FLW-level attrition signal is the **12% One-and-done**.

## 5. Who to leverage / where to support

- **By state:** Borno 85%, Kebbi 79% (strong); **Sokoto 53%** (needs support — 32 points below Borno).
- **By FLW type:** chv 83%, "others" 82%, eht 81% lead; the largest group **chew (556 FLWs) sits at 67%** — the single biggest opportunity to lift the average.
- **By LLO:** COWACDI 82% vs EHA 62%; FLWs spanning both partners finish ~100% (the most-engaged core).

## Recommendations
1. **Invest in the first-interview experience** — it's the strongest retention lever (84% vs 61%).
2. **Keep re-using engaged workers** — cross-cohort re-use deepens engagement; build a stable returning panel.
3. **Target Sokoto and the large "chew" segment** for support — the clearest below-average pockets.
4. **Lean on COWACDI / dual-LLO workers** as the reliable core; investigate what's dragging EHA finish rates.

## Method & data
- **Grain:** one row per unique FLW (deduped across cohorts); all metrics union the FLW's sessions across every arm. Ties out to the canonical count (1,424 started FLWs).
- **Tier (RFM):** Recency (days since last interview) + completion rate + answer depth (words/session), each 1–5.
- **Persona:** rule-based behavioral segment.
- **Finished:** completed all scheduled interviews in ≥1 of their cohorts.
- **Sources:** CommCare trigger/session data + OCS sessions (depth) + Connect funnel + `flw_registration` demographics (100% coverage). Full per-FLW detail: `flw_analysis.csv`. Live view: dashboard → **FLW Retention** tab (refreshes daily).
- **Caveats:** "finished" is upward-biased for multi-cohort FLWs (noted above); the progression-depth curve conflates cohort schedule lengths; `experience_years` in registration is unreliable (many default values) and is excluded.
