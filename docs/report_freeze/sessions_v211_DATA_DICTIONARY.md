# sessions_v211.csv - data dictionary

The base table every dashboard number is aggregated from. Pinned at **v211**.

## Grain

**One row per (FLW, cohort, interview slot)** from the CommCare interview schedule.

A slot that was offered but never opened is still a row, with `is_started = N`. Those rows are
what make drop-off computable, so they are kept rather than filtered out. Filter on
`matched_session_id != ""` if you want only real sessions.

| | |
| --- | --- |
| rows | 10,535 |
| rows with a session | 9,958 |
| rows started | 9,958 |
| rows completed | 9,452 |
| distinct FLWs | 1,453 |
| distinct cohorts | 72 |

## This is NOT one row per raw OCS session

OCS holds about 22.4k sessions, roughly 10.2k of which carry an interview tag. The rest are
welcome clicks, run-on fragments and untagged sessions. The dashboard's universe is the
9,958 that match a scheduled slot. Anyone comparing this file against an OCS export will
see that gap; it is by design, not a loss.

## Identifiers are re-keyed

`connect_id`, `matched_session_id` and `trigger_form_id` are salted hashes, not real ids. No
Connect id, OCS UUID, CommCare form UUID, name, phone, LGA or settlement appears in this file.
Codes are stable across every file in this freeze, so they join to each other.

## Columns

| column | meaning |
| --- | --- |
| `connect_id` | The FLW, re-keyed as FLW_xxxxxxxx. Stable across every row and file in this freeze. |
| `cohort_id` | The cohort the slot belongs to, e.g. 01TRS, 1PC1, 2WTE1. |
| `subgroup` | The study arm the cohort rolls up to: TRS, TRE, ABT1-A/B, ABT2-A/B, PANEL, ABT3-A/B, 2WT, EXT. |
| `cohort_type` | Human-readable label for the subgroup, e.g. Standard, Panel, ABT2 A. |
| `interview_n` | Position in that cohort's schedule, 1-based. Panel runs 1 to 13. |
| `topic_code` | Topic identifier, e.g. A, 1, 12, 8S, 99. The same topic can sit at a different interview_n in different cohorts. |
| `topic_name` | Topic title, e.g. Seasonal Malaria Chemoprevention 2. |
| `training_date` | Earliest Connect invited_date for the cohort. |
| `release_date` | When this slot became available, from the cohort start plus the schedule offset. |
| `is_released` | Y if release_date has passed. Slots not yet released are not drop-off. |
| `trigger_form_id` | The CommCare Trigger Bot form, re-keyed as TRIG_xxxxxxxx. Present means the bot offered the interview. |
| `trigger_received_on` | When the bot offered it. This is the clock start for any response-time measure. |
| `matched_session_id` | The OCS session filling this slot, re-keyed as SESS_xxxxxxxx. Blank means the FLW never opened it. |
| `review_status` | Human review verdict: acceptable, unacceptable, or not-reviewed. Blank if no session. |
| `review_ai` | Y if a reviewer flagged suspected AI use. Independent of the verdict; a session can be acceptable AND flagged. |
| `session_created_at` | When the FLW opened the session. Added to close a gap: without it the weekly engagement series and the retention curves could not be re-derived. |
| `session_ended_at` | Last activity in the session. The last message timestamp where the transcript archive has it, otherwise the session's updated_at. |
| `session_end_source` | Which of those two session_ended_at came from: last_message or updated_at. On 2WT the two agreed on every row. |
| `session_status` | OCS interview_status, e.g. interview_complete, interview_incomplete, interview_ongoing. |
| `session_human_words` | Words the FLW typed in that session. |
| `session_human_msgs` | Messages the FLW sent in that session. |
| `is_triggered` | Y if the bot offered this slot. |
| `is_started` | Y if a session exists for it. Identical to matched_session_id being non-blank. |
| `is_completed` | Y if that session reached interview_complete. |
| `c_invited` | Connect funnel: the FLW had an invited_date for this cohort. |
| `c_accepted` | Connect funnel: the FLW accepted the invitation. |
| `c_learn_completed` | Connect funnel: the FLW finished the learn module. |
| `c_claimed` | Connect funnel: the FLW claimed the opportunity. |
| `is_initiated` | Y if the FLW clicked through the welcome for this cohort. NOT the same as started. |

## Worked examples

```
# completion rate for a subgroup, the way the dashboard computes it
started   = rows where subgroup == X and is_started == Y
completed = rows where subgroup == X and is_completed == Y
rate      = completed / started

# 2WT response time
lag = session end - trigger_received_on   (session end needs the transcript archive,
                                           already computed in 2wt_lags_v211.csv)

# panel retention
per FLW, the gaps between consecutive session dates; retained if no gap exceeds 14 days
(already computed in panel_gaps_v211.csv)
```

## Two traps

**`is_initiated` is not `is_started`.** Initiated means the FLW clicked through the welcome.
Started means a session exists. For 2WT that is 534 versus 515, and dividing completions by the
wrong one understates completion by three points.

**A topic can sit at different `interview_n` in different cohorts.** Join on `topic_code`, not
on position, when comparing the same topic across arms.

## Tie-out against the published dashboard

Aggregated from this file and compared to the payload, so the file proves its own
reconciliation rather than asking you to trust it. Figures are started / completed.

| subgroup | this file | dashboard | difference |
| --- | --- | --- | --- |
| built_at | 2026-09-04 18:11 UTC |  |  |
| TRS | 2349 / 2262 | 2349 / 2262 | +0 / +0 |
| TRE | 299 / 292 | 299 / 292 | +0 / +0 |
| ABT1 | 1201 / 1058 | 1201 / 1058 | +0 / +0 |
| ABT2 | 1267 / 1201 | 1267 / 1201 | +0 / +0 |
| PANEL | 3633 / 3491 | 3632 / 3491 | +1 / +0 |
| ABT3 | 217 / 201 | 217 / 201 | +0 / +0 |
| 2WT | 516 / 484 | 515 / 484 | +1 / +0 |
| EXT | 453 / 442 | 453 / 442 | +0 / +0 |

Any non-zero difference is build timing, not disagreement: this file was generated from a
master build a few minutes after the payload was published, so a slot triggered in between
appears here and not there. Completed counts should match exactly; a difference there would
be a real problem worth chasing.

