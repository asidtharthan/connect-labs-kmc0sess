# Connect Interviews: project learnings

**Read this before starting any work on this project.** It is the running record of rules, traps and
settled facts. Update it whenever something is learned, corrected or decided. Last updated 2026-08-24.

---

## 0. Before you push: the checklist

**Read this section every time. It is short on purpose.**

| #   | Ask                                         | Command                                                            | If it fails                                                    |
| --- | ------------------------------------------- | ------------------------------------------------------------------ | -------------------------------------------------------------- |
| 1   | Did I write down a risk and not measure it? | re-read my own notes for "this could break" / "I should check"     | go measure it NOW, before the next step                        |
| 2   | Does this change REMOVE or RESHAPE data?    | `python impact_diff.py` (needs a `--snapshot before` taken first)  | paste the printed list into `allow_regression`; never guess it |
| 3   | Will CI pass?                               | `python preflight.py`                                              | fix locally; do not push to find out                           |
| 4   | Am I quoting a number to a human?           | it must come from `_pull_full_live.py`, never a local build        | the local build is ~40% short                                  |
| 5   | Did I add a gate?                           | mutate the payload and prove the gate fails                        | a gate that cannot fail is decoration                          |
| 6   | Is the cohort mapping edited in EVERY copy? | `build_payload_agg.py`, `audit_e2e.py`, `brutal_verify.py`, render | `brutal_verify` keeps its own copy and will fail alone         |

**The rule behind the checklist:** a predicted failure that is not measured is worse than an
unpredicted one. If naming the risk was possible, enumerating its instances was possible too.
Reasoning about a CLASS is not the same act as producing the LIST, and only the list prevents the
failure. When one attempt fails, stop retrying and go enumerate all of them at once.

## 1. Hard rules

| Rule                                                                                                                                                       | Why                                                                                                                                                                 |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Plain hyphens only.** Never em or en dashes, anywhere - chat, code, commits, briefs, dashboard copy, Word documents.                                     | The user calls the em dash an obvious AI tell, and this work goes to partners and funders. Swept from the codebase 2026-08-17 and from all memory files 2026-08-24. |
| **Never call an AI check "human", "manual", "independent" or "hand" validation.** Name the actor, state the sample honestly, offer the human upgrade path. | Caught by a reviewer on the probing brief. Overclaiming provenance is the fastest way to lose a reader's trust.                                                     |
| **Every number needs a denominator and a source.** Computed, retrieved, reported or estimated - say which.                                                 | A figure without a denominator cannot be checked, and a reviewer will assume the worst.                                                                             |
| **Never publish without an explicit go-ahead.** Publishing is outward-facing.                                                                              | Applies to the dashboard render, to funder documents, and to anything leaving the team.                                                                             |
| **No participant data or credentials in git.** The repo is a PUBLIC fork.                                                                                  | 4.58 GB of untracked participant data sits in the working tree. One `git add -A` from exposure.                                                                     |

## 2. Verification standards that have already caught real errors

- **A predicted risk is a TASK, not a remark.** The moment "this will probably break X" is written
  down, stop and measure it. On 2026-08-26 a one-cohort removal failed CI three times running, and
  the outcome had been written down in advance both times. Stating a risk and then walking into it
  is worse than not stating it: it proves the information was available.
- **Never substitute the CLASS for the LIST.** "Removing a cohort will lower some counters" is not
  knowledge. `{counts.cohorts, counts.flws, flwMatrix.rows, sources.*, table1.Overall.*,
connectFunnel.NPS.*}` is. Reasoning about a category and enumerating its members are different
  acts and only the second prevents the failure. `python impact_diff.py` produces the list in
  seconds; preflight step 2c now refuses to pass without it.
- **One failed attempt means STOP and enumerate.** Three retries each surfacing one more instance of
  the same root cause is the tell that CI is doing the thinking. Go find all of them at once.
- **Try to break your own claim before publishing it.** The "4-5x the largest corpus" claim failed
  under adversarial search - a 300,000-interview preprint exists. Narrow true beats broad impressive.
- **Verify every citation by retrieving it.** Six defects were found in one research document,
  including a paper attributed to a journal whose name appears nowhere in it, and a quotation that
  does not exist in its cited source.
- **Recompute rather than relay.** Agent-relayed figures have differed from source (9,945 vs 9,952
  sessions) because exclusion rules differed by a hair. Read the payload, not the summary.
- **Check the denominator before comparing two of our own numbers.** 21.3% and 18.5% describe the
  same effect on different bases. Two documents stating both will look like a contradiction.
- **A gate that imports the code under test proves nothing.** The audit re-derives from the raw
  archive for exactly this reason.
- **Controlling one confound while leaving another produces a number that looks clean and is not.**
  The within-topic save-rate slope looked like an experience effect, but later interview positions
  happen later in the calendar, so it had inherited the calendar effect. Ask what else moves with
  the variable you just controlled for.
- **Check the reviewer's premise, not just their conclusion.** A comment can be right about the
  limitation and wrong about the mechanism. Agree with what the data and logic support, and say
  plainly where they do not.
- **Always name the unit when reporting a rate: sessions, answers, or probe windows.** Mixing them
  in one sentence caused a real misreading in the reply to Ali. "66.6% of their triggers" reads as
  sessions but means answers. Write "66.6% of the 1,905 probed answers inside those sessions".
- **Distinguish the eligible subset from the whole set.** 242 sessions are flagged for suspected AI
  use; only 228 were probed at least once, and only those 228 can say anything about probe reasons.
  Quoting 242 in a probe-reason analysis would be wrong.

## 3. Data gotchas - the ones that have actually bitten

- **`role == "system"` is not conversation.** 4,644 bot self-summaries averaging 298 words. Under 2%
  of non-bot messages but roughly 35% of non-bot words. Counting them as FLW text inflates worker
  output by more than half.
- **Local artifacts lie.** `payload_agg.json` and `dashboard_data.json` have been stamped with a
  recent date while built off a two-month-old cache. Local `hq_pull_full/` has been 39% short of live.
  **Never calibrate against a local build.**
- **`.hq_creds.json` pins `domains` to only the original four.** A local pull without `HQ_DOMAINS` set
  silently produces a badly undercounted build. CI is unaffected.
- **Untagged sessions are not failures.** Roughly 11,900 sessions were opened and abandoned at the
  welcome step. They never started an interview. Never report them as drop-off.
- **Adding a topic to a subgroup design requires adding it to `_CANON_TOPICS` in BOTH
  `build_payload_agg.py` and `audit_e2e.py`**, plus `TOPIC_NAMES` (which is read as a bare subscript
  and will KeyError), `TOPIC_QUESTIONS`, and `MATRIX_TOPIC_ORDER` in the render.
- **Word locks files.** If a `.docx` is open, a regeneration either fails or silently writes an
  `_UPDATED` copy that then sits stale in the repo. Check for `~$` lock files first.
- **Heredocs mangle apostrophes.** For any content with quotes, use the Write tool, not a bash heredoc.

## 4. Settled facts that were once wrong

| Claim                                      | Status                                                                                                                                                                        |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PANEL opportunity ids                      | **1958 = 1PE1, 1959 = 1PC1.** An early memory had them reversed.                                                                                                              |
| `acceptable` / `unacceptable` session tags | **LLM-applied, not human.** Confirmed by Leah Ng'aari 2026-08-21 and independently by Andrea King in review. Incomplete interviews get `n/a`. Never cite as human validation. |
| "An LLM judge was planned but not built"   | **False.** The OCS session evaluator runs on every session, and Neal's `interviews_step2.r` is a complete per-answer judge that ran at scale.                                 |
| "Live interviews EHA is doing"             | **EHA does desk-based annotation.** But a separate EHA Clinics study of 50 FLWs given both AI and human interviews DOES exist - findings not yet available.                   |
| Topic 99 question count                    | **9, not 1.** `TOPIC_QUESTIONS["99"] = 1` is wrong in code. Confirmed against the tracker and raw question blocks.                                                            |
| The Hausa/English usability gap            | **A measurement artefact.** See section 5.                                                                                                                                    |

## 5. Analysis findings worth not re-deriving

- **The Hausa/English first-attempt gap (64.2% vs 72.7%) is an artefact of a word-count rule.** Mean
  words are near-identical. The one-word bucket alone is 119% of the gap. Moving the threshold by one
  word closes it to 0.39pp. 9.1% of English replies are a bare "yes" or "no". The same 234 FLWs who
  answered in both languages score +14.5pp higher in Hausa. **Do not report it as a quality finding.**
- **There is no FLW learning effect over the interview sequence.** 97.2% of interview-1 windows are
  topic A, the hardest topic in the study, so position and difficulty are inseparable. Within-topic
  slope is zero. What improved across the study was the bot: topic-standardised save rate climbed from
  45.1% to 63.2% while FLW first-attempt quality stayed flat.
  **This was challenged and re-tested 2026-08-24** by crossing each FLW's own interview ordinal with
  calendar month so experience and bot generation vary independently. Holding experience constant the
  save rate rises in every bracket (pos 2-3: 42.4% April to 67.9% June, +23.7pp); holding the month
  constant it does NOT rise with experience and in June and July it falls (74.0 to 64.8 to 49.3).
  Same inside single topics (topic B early-position 38.0% April to 63.5% May). The bot attribution
  survives. **Lesson: the original claim rested on the raw calendar trend, which cannot separate bot
  improvement from FLW familiarity. It was correct but under-evidenced when first made - a two-way
  decomposition is the minimum for any "X improved, not Y" claim.** Caveats: August pos 4-6 dips to
  49.6% on n=282, and topics A and B are April-May only.
- **The bot helps rather than pushes.** In 561 of 590 don't-know and didn't-understand cases (95.1%)
  it explained, rephrased, offered options, narrowed or lowered the bar. It pressed with no help in 6
  (1.0%). Explaining a term recovers 77.3% of answers; merely re-narrowing recovers 48.2%.
- **Generic and AI-pasted answers can only land in `needs_depth`.** `trigger_of` has no genericness
  test and `needs_depth` is the fall-through. `too_short` is capped at 3 words so cannot contain them.
  AI-flagged sessions show 66.6% needs_depth against 52.7% for everyone else.
- **The probe-rescue count is an upper bound.** 98.7% fire on the three-word rule and roughly a third
  already contained a number. Genuine rescues are 7 to 13% of answers, not 18.5%.
- **Quote grounding is provable; category labels are not.** All published quotes trace word for word.
  Category labelling runs at about two thirds correct, with three categories at or below 60%.
- **`recovered` in `probing_windows.csv` is structurally False for all don't-know and confused rows.**
  It cannot answer "did it work" for those triggers. Do not quote it that way.
- **What 67.8% means, since it is easy to misread.** It is the form baseline: the share of the 112,864
  questions whose FIRST answer already passed the usability test, 76,469 of them, before any probe.
  86.0% (97,013) is the share whose FINAL answer passed. Usable means only three things - not blank,
  more than three words, not an explicit don't-know. It is a word count, not a quality judgement.
- **Prompt version and calendar time are the same axis.** Versions changed over time, so the
  decomposition can support "the bot improved, not the FLWs" but CANNOT attribute a gain to any
  specific version. Do not let "great data for the report" become a per-version claim.
- **Progress visibility is a form design choice, not a property of forms.** A Google Form with one
  question per section, no progress bar and conditional branching tells a respondent as little as a
  chat does. Any form-versus-chat comparison depends on which form gets built, so phase 2 must choose
  deliberately.
- **The probe trigger has no genericness or AI test.** `trigger_of` runs five checks (empty,
  confused, dont_know, `<=3 words`, no-number-where-asked) and everything else falls into
  `needs_depth`. So pasted or generic answers are labelled "thin" alongside genuinely thin ones.
  **This is a labelling gap, not a detection failure** - say it that way. `too_short` is impossible
  (capped at 3 words; longest of all 23,469 is 3 words). Evidence they sit in `needs_depth`: inside
  the 228 flagged-and-probed sessions, 66.6% of their 1,905 probed answers fired `needs_depth`
  against 52.7% of everyone else's 70,232; 223 of 228 had at least one.
- **Do not build a category on a low-recall detector.** A stylistic AI detector flagged 46 answers
  across 31 sessions at 89% precision (41 of 46 sat in already-flagged sessions) but only ~3% recall.
  Publishing 46 as a count would understate by roughly 30x while looking authoritative. **A wrong
  number in a table is worse than an honest gap.**
- **The evaluator cannot be plugged into the probe logic.** It judges a whole session after the fact;
  a probe trigger needs to label one answer, live. Knowing a session contained pasted content does
  not say which answer was pasted. Connecting them is a build, not a relabel.

## 5b. Finding 1 claims that CANNOT ship as written (audited 2026-08-25)

| Claim in the draft                                    | Status                                                                                                                                                                                                                                       |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **"$2.76 per interview"**                             | **NO SOURCE ANYWHERE.** The draft contradicts itself at para 369 with $3.05 and $3.42. Nearest sheet gives $3.35 planned or $2.67 realised. Do not publish without the author's workings.                                                    |
| **"17 out of 117 responses, 15%"** (March UAT AI use) | The **117 is traceable**, the **17 is recorded nowhere**.                                                                                                                                                                                    |
| **"1 out of 75 sessions, 1.3%"** (April review)       | **The source says 2 of 75 = 2.7%, and it is dated May, and the set was 73 sessions.** The 1.3% was lifted from a different line (the evaluator's full-run output).                                                                           |
| **"15% fell to 1.3%"** narrative                      | **Not supportable.** The archive's own `suspected_ai_use` shows no decline: 1.9% Apr, 0.6% May, 4.1% Jun, 2.5% Jul, 2.7% Aug - and scoring coverage is 7% in Apr-May against 82% in Jul-Aug, so the two rows compare non-comparable samples. |
| **"Across 766 FLWs, 70% scored 1 or 2 out of 5"**     | **No source in the repo.** `interviews_catchment_analysis.r` is absent; the data path is Neal's local Dropbox. 766 is not reproducible from the largest answers extract.                                                                     |
| **"85% to 94% completion"**                           | **Not reproducible and it understates.** True figure is 95.0% overall, 87.6% to 100% by arm.                                                                                                                                                 |
| **"Panel retention 88% over 10 weeks"**               | Number exists but under a different definition (drop-off reading C) than the draft's own stated 14-day rule (reading A = 73.4%), and the window is 7.4 weeks, not 10.                                                                        |

**"9129 completed interviews" IS real** - `counts.completed` from CI run 31568449830, 2026-08-12. Just stale. Current equivalent is 9,446 of 9,944 started.

**Confirmed and safe:** the $2 to $6 pay range (Cohort Design sheet); 4 states and 2 LLOs (Kebbi 404, Bauchi 385, Borno 368, Sokoto 297 of 1,454; COWACDI and EHA); and "completion did not fall at 20+ questions" - but cite the **randomised ABT3 contrast** (7 questions 91.4% vs 20 questions 93.3%, p=0.62), NOT the pooled observational comparison, which runs the other way (95.7% vs 93.8%, p=0.0005) and is confounded by cohort and topic.

## 5b-i. THE completion number - verified by hand 2026-08-25, use this

Three different "completion" figures are all live in our own files. **They are all correct and they
answer different questions.** Never quote one without its denominator.

| Figure                                                                          | Denominator                   | Value             |
| ------------------------------------------------------------------------------- | ----------------------------- | ----------------- |
| FLW-cohort level (`dashboard_data.json` `counts`)                               | 5,683 started FLW-cohort rows | **5,335 = 93.9%** |
| Session level, all analysed (`insights_payload.json` `L4_session.complete_pct`) | 10,115 analysed sessions      | **94.7%**         |
| Session level, terminal states only                                             | 10,605                        | 90.7%             |

The 90.7% looks alarming next to the others until you decompose it, and the decomposition is the
finding worth publishing:

- **548 sessions never got underway** - no `interview_topic` was ever set, and 523 of those also have
  no `preferred_language`. They completed at **2.9%**. These opened and died at the door.
- **10,057 sessions did get underway** and completed at **95.4%**.

So the honest two-stage framing is: **5.2% of sessions never started an interview; of the interviews
that did start, 95.4% ran to the end.** Quoting 95.4% alone hides the door-step loss; quoting 90.7%
alone blames the instrument for it.

⭐ **Language parity is real and it is the strongest single number in Finding 1.** Among sessions that
got underway: **English 95.71% (5,405/5,647), Hausa 95.63% (4,116/4,304). A 0.08pp difference**, Wilson
95% CIs [95.01, 96.08] and [94.98, 96.20] - almost perfectly superimposed. Verified by hand from
`_ocs_tag_census.json` (22,259 records, 2026-08-25 refresh), not taken from an agent.

⚠️ `_ocs_sessions_cache.json` is a **June** cache with no `state` - do not use it. The live session
store is `_ocs_tag_census.json`. `ocs_transcript_dump/session_index.csv` (21,700) is the Aug 13 dump.

## 5b-ii. ⚠ RETRACTED: there was NO PANEL undercount. Check the LIVE payload, not a local build

I claimed on 2026-08-25 that the dashboard undercounted PANEL by 8x. **That was wrong and is
withdrawn.** The live dashboard is correct and agrees with the archive.

|                   | Archive | **Live (`_live_full.json`, 01:42 UTC)** | My local `dashboard_data.json` (01:43 UTC) |
| ----------------- | ------- | --------------------------------------- | ------------------------------------------ |
| PANEL completed   | 3,472   | **3,433**                               | 415                                        |
| 2WT               | 501     | **483**                                 | 29                                         |
| EXT               | 447     | **441**                                 | 55                                         |
| Overall completed | 9,598   | **9,458**                               | 5,335                                      |
| Cohorts           |         | **73**                                  | 72 (NPS missing)                           |
| master_rows       |         | **10,526**                              | 6,221                                      |

Live reports **9,458 of 9,953 = 95.0%**, within 1.5% of the archive. **The broken file was my local
one** - a degraded build running on partial inputs while the pipeline was refreshing.

⭐ **THE LESSON: self-consistency is not correctness.** My local file's rows summed cleanly to its own
totals, so every internal check passed. That is exactly why it did not look wrong. **Before calling
anything a defect, diff the local artifact against `_live_full.json` (or the published render).** A
locally rebuilt file during an active refresh is the classic trap.

**What does survive:** the Cohort Tracker's PANEL row is genuinely self-contradictory - **I1 started
199 but I1 completed 302**, and from I6 onward zero triggered and zero started while recording 134,
104, 51 completed. A hand-maintained sheet drifting from the system, not a pipeline fault. It is the
reason tracker PANEL earnings of $5,652 cannot reconcile against 3,433 interviews at $4, which is the
sole basis for scoping the cost figure to the six settled subgroups.

## 5b-iii. `cohort_id` in OCS state CANNOT carry attribution

**67.3% of sessions in the Aug-13 dump have a blank `cohort_id`** (14,598 of 21,700), and the
population is skewed by era: late cohorts (PANEL, EXT, 2WT) mostly have it, early ones mostly do not.
Attributing by `cohort_id` therefore gives TRS **342** when the true figure is ~2,257, while inflating
nothing for PANEL. Any per-subgroup split built on OCS `cohort_id` alone is wrong in both directions.

**Consequence for Finding 1: use archive totals, which need no attribution** (95.4% completion,
language parity). Do not build subgroup splits from OCS `cohort_id`.

## 5b-iv. Cost per interview - what the tracker actually supports

From `Connect Interviews _ Cohort Tracker.xlsx`, sheet **`Estimated FLW payment`** (the authoritative
pricing). Pay is set **by design per subgroup**, $2 to $6:

| $2 | TRS, TRE, ABT1-A |
| $3 | ABT2-A, ABT2-B |
| $4 | ABT1-B, PANEL, ABT3-A, ABT3-B |
| $6 | GW Test |

The sheet is a **budget with actuals patched in**, not a ledger. The `Assumptions` column marks which:
six rows are ACTUAL ("Interviews complete" / "No significant volume added"), four are PROJECTED
(PANEL, ABT3-A, ABT3-B, GW Test).

- **ACTUAL-basis six subgroups: $11,984 / 4,758 interviews = $2.52 per interview.** These tie to the
  live dashboard within **0.4%** (TRS 2,257 vs 2,256; TRE 289 vs 289; ABT2-B 969 vs 968), so this
  figure is defensible.
- Blended including projections: $20,732 / 6,743 = $3.07. **Weaker** - the PANEL denominator is wrong.
- ⚠️ **`GW Test` is priced at $2,424 for 404 interviews but does not exist in the live data at all.**
- ⚠️ If PANEL truly delivered 3,472 interviews at $4, that is $13,888 against the $5,652 the sheet
  records as earned. **Either PANEL was not paid per interview at $4, or recorded earnings are stale.**

**PUBLISH: the $2 to $6 design range, and $2.52 for the six settled subgroups, scoped explicitly.**
**DO NOT publish a single programme-wide cost per interview** until the PANEL denominator is resolved.
`$2.76` remains underivable from any basis.

## 5b-iv-bis. COSTING, corrected 2026-08-25 post-refresh (supersedes 5b-iv's $2.52)

Two errors in my earlier costing, both now fixed:

1. **`GW Test` IS `2WT`.** It is the "GiveWell 2-Week Test" ($6/interview, topic 14). I wrongly said it
   "does not exist in the live data at all". It is simply labelled differently in the payment sheet
   than in the dashboard. Only **EXT and NPS** are genuinely absent from the payment sheet.
2. **$2.52 covered only six subgroups and excluded PANEL**, which is the single biggest cost line.

**Pay rates by subgroup, from the tracker's `Cohort Design` sheet (authoritative):**
$2 TRS, TRE, ABT1-A · $3 ABT2-A, ABT2-B, EXT, NPS · $4 ABT1-B, PANEL, ABT3-A, ABT3-B · $6 2WT

**Design rate x live completed interviews, 100% coverage of all 9,460:**

|                 | completed | $/iv | earned      |
| --------------- | --------- | ---- | ----------- |
| PANEL           | 3,433     | 4    | 13,732      |
| TRS             | 2,262     | 2    | 4,524       |
| ABT2-B          | 978       | 3    | 2,934       |
| ABT1-B          | 653       | 4    | 2,612       |
| 2WT             | 483       | 6    | 2,898       |
| EXT             | 441       | 3    | 1,323       |
| ABT1-A          | 405       | 2    | 810         |
| TRE             | 292       | 2    | 584         |
| ABT2-A          | 228       | 3    | 684         |
| ABT3-A / ABT3-B | 117 / 84  | 4    | 468 / 336   |
| NPS             | 84        | 3    | 252         |
| **TOTAL**       | **9,460** |      | **$31,157** |

**= $3.29 per completed interview.**

⚠️ **UNRESOLVED CONFLICT.** The tracker records **$20,732** actually earned - **50% below** the
design-rate computation. Driver: the tracker's PANEL row records 1,413 interviews against 3,433
actually completed, and omits EXT and NPS. Either the tracker's earnings column is as stale as its
interview count, or PANEL was not paid per interview at $4. **Cannot be resolved from anything in the
repo** - needs Connect payment records or the sheet's maintainer.

**Safe to publish either way: the $2 to $6 design range.** A single total-spend or cost-per-interview
figure is blocked until that conflict is settled.

## 5b-iv-ter. Post-refresh re-derivation: nothing material moved

Re-derived every figure against live render **v182** (built 2026-08-25 09:33 UTC, 211/211 gates pass)
and a re-pulled archive (22,263 records, was 22,259):

| Figure               | Before                        | After                                          |
| -------------------- | ----------------------------- | ---------------------------------------------- |
| Completion, underway | 9,598/10,057 = 95.4%          | **9,601/10,060 = 95.4%**                       |
| Doorstep loss        | 548, 5.2%, 2.9% compl         | **unchanged**                                  |
| English              | 5,405/5,647 = 95.71%          | **5,407/5,649 = 95.72%**                       |
| Hausa                | 4,116/4,304 = 95.63%          | **unchanged**                                  |
| Language gap         | 0.08pp                        | **unchanged**                                  |
| ABT3 7Q vs 20Q       | 92.1% vs 94.4%, p=0.52        | **byte-identical**                             |
| Observational length | 96.0 / 95.4 / 93.9            | **unchanged**                                  |
| PANEL                | 364 FLWs, 3,472 iv, median 11 | **3,474 iv**, rest unchanged; >=8 75.0%->75.3% |
| EHA (all)            | 83.3% / 0.812 / 92.6% / 11.8% | **identical** (fixed files)                    |

⭐ **Lesson: a daily refresh moves these figures by ~0.03%.** Re-deriving after every refresh is not
required for precision; it is required only when a _source_ changes or a defect is suspected. The
live-vs-archive reconciliation (95.0% live vs 95.4% archive, 0.4pp) is the check that matters.

## 5b-v. Numeric questions are NOT worse - the draft has this backwards

Source: `chatbot analysis- support data/Numeric question analysis.docx` (Stage 5, parent-question
level, 64 parent questions across 7 topics, n>=100 filter, Welch t-test, dated 2026-06-17).

The draft says _"Numeric questions do not appear to work well."_ The analysis found the **opposite**:

| Outcome            | Avoids numeric (n=24) | Has numeric ask (n=26) |                                |
| ------------------ | --------------------- | ---------------------- | ------------------------------ |
| % specific         | 49.0%                 | **61.9%**              | **+12.9pp, p=0.016**           |
| % complete         | 27.5%                 | **37.7%**              | **+10.2pp, p=0.033**           |
| Mean turns         | 2.04                  | **2.65**               | **+0.61, p=0.010**             |
| Mean quality score | 2.73                  | 2.81                   | n.s.                           |
| % not answered     | 17.8%                 | **15.8%**              | n.s. (numeric slightly better) |

**Two distinct claims are being conflated and must be separated:**

1. _"Numeric questions produce worse answers"_ - **FALSE.** They produce more specific, more complete
   answers with more back-and-forth. The numeric ask anchors the response and gives the bot a concrete
   target to probe toward.
2. _"The numbers FLWs give are not internally coherent"_ - this is the 766-FLW catchment claim, which
   is **unsourced** and is about arithmetic consistency, not answer quality.

These are compatible: FLWs **engage well** with numeric questions while the **numbers themselves** may
still not reconcile. 1.4 must be written on that distinction, not on "numeric does not work".

## 5b-vi. Instrument length - use the randomised contrast, and only it

**ABT3 is a matched randomised design**: arm A got the 7-question version of four subjects, arm B got
the 20-question version of the same four.

| Subject               | short 7Q            | long 20Q          |
| --------------------- | ------------------- | ----------------- |
| Antibiotics & ACT Use | 30/36 83.3%         | 23/27 85.2%       |
| Malaria               | 23/25 92.0%         | 15/15 100%        |
| Medicine Quality      | 32/34 94.1%         | 26/26 100%        |
| Water & Diarrhea      | 32/32 100%          | 20/21 95.2%       |
| **POOLED**            | **117/127 = 92.1%** | **84/89 = 94.4%** |

**+2.3pp, z=0.64, p=0.52, long arm higher in 3 of 4 pairs.** Tripling the questions did not reduce
completion. ⚠️ n=216, CIs [86.1, 95.7] and [87.5, 97.6] - this **rules out a large fall, not a small
one**. Say so.

⚠️ **The observational comparison across all topics runs the OTHER way**: <=9 questions 96.0%
(5,391/5,618) vs 16-20 questions 93.9% (1,764/1,879), **-2.1pp, p=1.8e-4**. It is confounded by cohort
and topic (long topics sit mostly in PANEL). **Cite the randomised contrast and disclose this.**

⚠️ `state.total_questions` is a **placeholder** - 7,461 sessions claim "1" question. Never use it for
instrument length. Join `interview_topic` to the tracker's **`Topics_Master`** sheet instead
(normalise "&" to "and": the archive writes "Medicine Quality and Counterfeiting 2", the tracker
writes "&").

## 5c. Finding 1 literature - the three attacks to pre-empt

1. **"95% completion is unremarkable."** Mavletova and Couper's meta-analysis puts ordinary mobile web breakoff at **0.4% to 30.9%**. Do not argue from the level. Argue from the conjunction: long conversational instrument, mobile-only, probing on - and **Barari et al. (NORC, n=1,200) found probing raises attrition, worst among mobile users**. Completion holding under those conditions is the notable result.
2. **"Completion parity is not quality parity."** Uhura (arXiv:2412.00948) benchmarks six African languages including Hausa: GPT-4o scores **94.9% English vs 75.5% Hausa** on ARC-Easy. Scope our claim to interview conduct and completion, not model comprehension.
3. **"Rich answers prove nothing."** Traylor (2025) found MTurk answers **looked better but were more likely AI-generated**. Authenticity cannot rest on richness. The detectable signature is paste and keystroke behaviour, which we do not log - say so.

**The citation that defends our word-count artefact finding:** Petrov et al. (NeurIPS 2023) - the same text tokenises **up to 15x longer** across languages, so a length threshold is a different threshold per language. Counter-pressure to state: Hada et al. (EACL 2024) found LLM evaluators are **biased toward higher scores in low-resource languages**.

**Support for 1.4:** Silva et al. (PLOS ONE 2016) - CHWs reported for 95-100% of catchment but captured only 30-90% of births and 22-91% of under-five deaths. Holbrook et al. (POQ 2014) - heaping marks estimation not counting, and is not merely satisficing, but is _expected_ on percentage questions so our count-based heaping is the stronger evidence. Ghiselli (2019) and Salisbury (2024) - in Sokoto specifically, "the problem is the denominator", so an implausible catchment figure may reflect a broken system rather than a broken respondent.

**Disclose:** Sobolewski et al. (JMIR 2024) - payment lifts completion 43.6% to 89.8% at $5, but imports 4.5-4.7% fraud. Our completion is partly bought.

**Two genuine novelty claims:** no published AI-interview study reports completion in Hausa or any African language, and none studies chatbot interviews with health workers as respondents.

## 5d. transcript_gems.csv is NOT quotable as-is

**All six gems pulled for Finding 1 turned out to be multi-turn concatenations**, and one was truncated with a trailing ellipsis. The `text` column joins several consecutive FLW turns. Quoting it directly publishes a single utterance that was never said. **Always recover the contiguous turn from `_ocs_messages.jsonl` before quoting.** Affects Finding 1, Finding 3 and the insights document.

## 5e. AI-use detection vs humans - the decisive head-to-head (computed 2026-08-25)

Matched **all 245** EHA-annotated sessions by `session_id` against the archive's automated flag
(`suspected_ai_use` field OR a `suspected_ai`/`user_ai_response` session tag):

|                 | auto = YES | auto = NO |
| --------------- | ---------- | --------- |
| **human = YES** | 25         | 4         |
| **human = NO**  | 9          | 207       |

- **Raw agreement 94.7%, Cohen's kappa 0.763**
- **Recall 86.2%** (25 of 29 human-flagged caught), 95% CI [69, 95] - ⚠ n=29, state the width
- **Precision 73.5%** (25 of 34 auto-flags confirmed)
- Human rate 11.8% vs auto rate 13.9% on the same sessions

⭐ **THE FINDING: the detector agrees with humans (94.7%, kappa 0.763) at essentially the same rate
humans agree with each other (94.7%, kappa 0.812).** That is the human-human-ceiling argument made
concrete on the dimension that matters most, and it is a much stronger claim than any overall
acceptability number.

⚠️ **I initially got this WRONG and must not repeat it.** I compared the corpus-wide flag rate
(**234 of 10,135 analysed interviews = 2.31%**) against the EHA sample's 11.8% and inferred a "5x
under-detection gap". **False.** The EHA sample is deliberately harder-weighted; on matched sessions
the detector is at the human ceiling. **This is the same apples-to-oranges trap as the AI-trend
coverage error (7% vs 82%).** Always match on session id before comparing two raters.

## 5f. Real-time AI detection does not exist - confirmed, it is purely post hoc

Ali Flaming's review comment ("AI detection in real time - the bot is not that good at this, only post
hoc") is **correct, and stronger than stated: it never happens at all.**

Scanned all 22,075 sessions in `_ocs_messages.jsonl` for assistant turns that confront possible AI use.
**Zero genuine instances.** Two false-positive classes to avoid:

- **282 sessions** matched on "someone else" - ordinary interview talk about who records data, nothing
  to do with AI.
- **4,218 sessions** matched strict AI language - all the bot's own self-introduction, _"I am an AI
  interviewer, here to conduct a qualitative interview with you."_

The bot says **"your own words"** as boilerplate in **4,285 sessions (19.4%)** but never challenges an
answer as AI-generated mid-interview. Detection is entirely post-hoc, by the evaluator, after the
session closes.

## 5g. Neal's own `Updates from Dimagi.docx` - two admissions worth quoting

From the outputs pack root:

1. **"Hausa responses are under-represented - am working through a few bugs there"** (19 July). A known
   pipeline bug under-representing Hausa in the _analysis_, separate from Ali's separate concern about
   Hausa-to-English translation quality during human review.
2. **"The auditing we're doing may well lead to some changes. Guessing it will mostly be that we have
   more data than the current reports have been indicating."** An acknowledgement that the reports were
   undercounting.
3. Navigation friction in his own words on the numeric pack: _"My guess is that looking at the PDF
   first would be the easiest way to understand this."_ Three artifacts for one analysis, with a verbal
   hint about which to open first.

Also: Malaria 5 analysis ran on **~430 interviews** with ~30 more unanalysed at the time.

## 5h. Our own deliverable footprint (the other half of the mega-reports problem)

**64,433 words across 34 markdown deliverables** in this repo, largest being
`docs/Interview_Transcript_Insights.md` at 11,649 words. And the dashboard render is at **496.2 KB
against a hard 512 KB ceiling - 15.8 KB headroom, 97% full**. The size ceiling is now a real
engineering constraint on adding anything further, which is itself evidence for the
"finding the right level of detail" challenge.

## 5i. The Dimagi Outputs pack, measured (the "mega reports" evidence)

`Dimagi Outputs-20260825T132546Z-1-001.zip`. This is the folder Andrea King cited as _"an example file
that has several different types of outputs - for the same topic area"_, evidencing her point that
_"we have also been building out massive reports that can be hard for humans to get a lot out of"_.

**Scale:** 834 files, **2.59 GiB**, 5 date folders, 22 report sets, 45 PDFs / **2,239 pages**,
529,646 words of Markdown reports, 505 CSVs (88% of all bytes), 44 XLSX.

**One topic's full cost to read** (Aug 10 / Bed Net Usage, the _cleanest and smallest_ modern set,
13 files): **29,569 report words, 71 PDF pages, 54,505 tabular rows, ~2.0M words total.** The largest
(Malaria/malaria5): 45,696 report words, 109 pages, 115,364 rows, ~4.0M words.

**Verified redundancy - I checked these myself, not just the agent's word:**

- ⭐ **`answers_scored.csv` carries no column its sibling lacks. Confirmed in 32 of 32 upload folders**:
  its 28 columns are a strict subset of `typology_classifications.csv`'s 32. The 4 extra are
  `typology_id`, `typology_name`, `classification_basis`, `classification_reasoning`. ~122 MB of files
  that add nothing.
- **151 duplicate groups, 317 MB (11.7% of the pack) byte-identical**, mostly `upload/` re-shipping the
  topic-root file verbatim.
- **The .md report is a verbatim superset of four CSVs**: 75/75 key_findings topic_sentences, 15/15
  synthesis rows, 64/64 exemplar snippets, 45/45 gem explanations found as exact substrings. The PDF is
  a render of the .md (0.97 word ratio).
- **One finding appears in 4 artifacts; one typology statistic in 6.**

**⚠ Two artifacts in the same folder give different numbers for the same quantity - VERIFIED:**
Aug 10 / Bed Net Usage, question 3.1, typology T1 "Bare Percentage or Count Statement":

| Artifact                                       | Figure                                |
| ---------------------------------------------- | ------------------------------------- |
| `report_bednets...md`                          | **257 responses, 48%**                |
| `interview_analysis...xlsx` `Typology_Summary` | **n_total 435, 40%** of 1,080 offered |

Each is right under its own denominator (per-FLW vs per-sub-answer) but they ship side by side with no
cross-reference.

**⭐ The `upload/` folder is addressed to an LLM, not a person.** `system_prompt.txt` - **18
byte-identical copies, 3,896 bytes each, verified** - opens _"You have been given 6 files"_ in a folder
whose `manifest.csv` lists **12**. It names the audience: _"used to provide qualitative evidence to
GiveWell... decision-relevant for funders"_.

**Structure per report:** Bed Net Usage = 101 headings, 75 numbered findings, 18 tables, 214 example
blocks. malaria5 = 154 headings, 116 findings, 26 tables, 333 example blocks.

**Direction of travel is mixed, and this matters for the write-up:** per-set page count FELL
(June 15 Bed Nets 165pp -> Aug 10 71pp) and files per set fell (20 -> 13), but sets per drop ROSE
(2 -> 8) and total pages per drop rose (380 -> 524). **The team was already simplifying each report
while the overall pack grew.** Do not write this as "reports keep getting bigger".

**`Probes [New]` (Aug 10) is the counter-example worth highlighting**: 6 PDFs, 79 pages, organised by
**funder decision question rather than by topic**, each opening with the question and naming GiveWell,
e.g. _"GiveWell adjusts SMC effectiveness assuming 93-94% of children complete doses 2 and 3 at home,
based on caregiver self-report it distrusts. What do FLWs - the independent observers - say?"_ A probe
crosses topic folders. Two of the six are 6 pages / ~3,000 words. **This is the format that answers
Andrea's "right level of detail" problem, and it already exists in the pack.**

**Pipeline internals ship inside deliverables:** `July 19/malaria5` holds 263 files / 660 MB including
`align/`, `audit_packets/` (46 per-session HTML renders), `_prerun_backup_2026-07-17/`, 16 `.csv.bak`,
files named `*_OLD_20260724` / `*_prerecovery_*` / `*_pretx_*`, a **596 MB `messages_cache.csv`**, and
the same malaria5 analysis three times over (reports dated 07-16, 07-19, 07-26).

⚠️ `interview_analysis_*.xlsx` files have a **broken drawing reference and wrong declared sheet
dimensions** - openpyxl returns 1 row in both normal and read_only mode. Parse the sheet XML directly
via `zipfile` + `ElementTree` or you will silently read nothing.

## 5j. ⭐ Per-dimension human-human agreement COLLAPSES - the real "interesting finding"

Computed by me from the 245 EHA annotations, parsing the per-dimension grades out of the free-text
`fields.Comment` for both raters (238 of 245 records parsable):

| Dimension                 | n   | agreement | Cohen's kappa |
| ------------------------- | --- | --------- | ------------- |
| Clarity                   | 234 | 60.3%     | **0.276**     |
| Completeness              | 231 | 61.0%     | **0.207**     |
| Relevance                 | 237 | 64.1%     | **0.377**     |
| Depth                     | 229 | 66.8%     | **0.383**     |
| **Authenticity**          | 228 | **91.2%** | **0.645**     |
| _(Overall acceptability)_ | 245 | _94.7%_   | _0.812_       |

⭐ **THE FINDING: two experts agree on the verdict (94.7%, kappa 0.812) but barely agree on WHY.**
Four of the five dimensions land at kappa 0.21 to 0.38 - only "fair" on Landis & Koch. Only
**Authenticity**, the AI-detection dimension, holds up. This is far more interesting than the
"88 to 96%" line and it is fully quantified.

It also explains why Claim 2 could never have worked: the draft makes five per-dimension model-agreement
claims, but the humans themselves cannot agree on four of those five dimensions, so the ceiling for any
per-dimension model-vs-human comparison is very low by construction.

## 5k. ⚠ "88% to 96%" is WRONG - it is 88% to 97%

Per-round human-human agreement, computed: **R1 96.0%, R2 88.0%, R3 95.7%, R4 97.3%.** The draft's
upper bound of 96% omits R4. Correct range: **88% to 97%**. Pooled 94.7%, kappa 0.812.

## 5l. ⚠⚠ The "OpenAI vs Anthropic" comparison IS UNSUPPORTED - the comparison was never run

The draft's five per-dimension statements about Anthropic vs OpenAI evaluators **cannot be sourced.**
I grepped the whole repo and the whole outputs pack for `openai` / `gpt-4` / `gpt4`: **every hit is
Python library code under `.venv`. Zero data artifacts. Zero hits in the outputs pack.** Output files
are slugged `claude-multiple-models`, and no model name appears inside any report or system prompt, so
"multiple models" cannot be shown to mean two vendors.

**Where the draft's "stricter / lenient" language actually came from** - and it is garbled in two ways.
`chatbot analysis- support data/Connect Interviews _ OCS Evaluations - Overall tabs.docx` para 1985+
holds a **"Concordance Report (Dimagi team vs Evaluator)", n=23**, all figures verified from its tables:

| Metric                      | Value             |
| --------------------------- | ----------------- |
| Overall concordance         | **16/23 = 69.6%** |
| Sensitivity on Unacceptable | **37.5% (3/8)**   |
| Specificity                 | **86.7% (13/15)** |
| PPV                         | 60.0% (3/5)       |
| NPV                         | 72.2% (13/18)     |
| Discordant                  | 7/23 = 30.4%      |

Its own headline: _"the evaluator is rating individual dimensions ACCEPTABLE in cases where humans see
LOW"_ - i.e. **too LENIENT**, the **opposite** of the draft's "Anthropic ran stricter than OpenAI on
flagging it LOW". And it is **one model versus humans, not vendor versus vendor**.

Two genuine strengths it does record: _"Evaluator is stricter on Rule C (data integrity)... catching
numerical contradictions humans missed"_, and AI-use detection listed under "What's working".

⚠️ **Do not pool the n=23 Dimagi-internal exercise with the n=245 EHA set.** Different reviewers,
different rounds.

## 5m. Reviewer strictness varies enormously - 44% to 85%

From the same docx, the Dimagi-internal review of **75 sessions (55 acceptable = 73.3%)**:

| Reviewer  | Sessions | Acceptable   |
| --------- | -------- | ------------ |
| Andrea    | 20       | 17 (**85%**) |
| Ali       | 6        | 5 (83%)      |
| Aathithya | 21       | 16 (76%)     |
| Zohaib    | 19       | 13 (68%)     |
| Mansi     | 9        | 4 (**44%**)  |

**A 41-point spread in how strict reviewers are.** Small per-reviewer n, so treat as indicative, but it
is direct evidence for "even expert reviewers don't agree".

**The four named disagreement axes** (their own conflict table): is LOW Depth alone disqualifying; does
bot prompting count against the FLW; where is the Clarity threshold; what is the AI-suspicion
threshold. The first was settled by fiat: _"Decision: If low depth AND low clarity, then
unacceptable."_

**Also on record:** the evaluator DID emit all five dimensions on every session, but only into a
free-text reasoning blob that was **never exported**, so only **10 hand-curated gold-label sessions**
carry per-dimension evaluator tags as data. That is why no per-dimension model file exists.

## 5n. Section 3 comment round (2026-08-25) - the restructure ALREADY happened

⭐ **HOW TO READ COMMENTS: always use the `.docx`, never a comments export or screenshots.**
`word/comments.xml` + `word/document.xml` gives author, timestamp AND the exact anchored text range,
extractable programmatically. The Google-Docs `comments.md` export carried only **21 of 125** comments
and **no anchor text at all**, so it cannot tell you which sentence a comment is on. An **empty anchor
range means the anchored text was DELETED** - i.e. the comment is already actioned or moot.

**State of Finding 3 in `Copy of Interviews Final Report Outline - AS.docx` (2026-08-25 20:02):**
125 comments total (Mansi 49, Andrea 45, Ali 24, Neal 7); **28 in Finding 3** (#80-#107).

Andrea deleted most of my draft. **Only 4 paragraphs of 3.1 survive (p710-p713).** Gone: "What only
becomes visible at this size", **all of 3.2**, "How this kind of tooling is known to fail", "How ours
performs on those two measures". Her comment #81: _"I took out the last section 'how our system
performs' which I think keeps to the intent of 3.1 and 3.2."_ **20 of the 28 comments now have empty
anchors** - already actioned.

⚠️ **THE KEY LESSON: my draft read as self-criticism.** Andrea said so twice, independently:
#80 _"my takeaway from this first section is that we don't think the AI analysis worked well - is that
what we're trying to say?"_ and #98 _"my takeaway is that we don't think the analysis went well? (which
I don't think is true)... we're just trying to lay the base information in this section... we actually
don't need to get into the conclusions of how we performed - the later sections in 3 get into this."_
Ali agreed (#100), Andrea confirmed (#101). **Agreed flow for 3.1: base information ONLY - scale, and
what has/hasn't been done before at smaller scale. No failure modes, no self-assessment.**
The 3.2 substance was **moved, not lost**, into "Platform and Pipeline Evolution" (p1031) and
"What's still open" (p1047, which now carries the Hausa quality gap and the post-hoc AI-detection point).

**5 ORPHANED REFERENCES** - citing text deleted but entries remain: **Fehring, Lu, Mehta, Wuttke,
Xiao**. The surviving 3.1 cites only Jack, Barari, micro1, Qiao, Marston. Cut the 5.
No dangling forward/backward references in the surviving text - checked.

⚠️ **VISIBLE FLOW DEFECT: the heading numbering has a hole.** Headings run
"(3.1)" -> "(3.3)" -> "(3.4 - 3.6)" with **no 3.2**, and then "Interesting Findings" and "Challenges"
carry no number at all. Either renumber or restore a short 3.2.

## 5o. THE FIGURES PROBLEM - six different interview counts in one document

| Para        | Figure                                                               | Section                |
| ----------- | -------------------------------------------------------------------- | ---------------------- |
| p228        | **9460** completed, 95%                                              | Finding 1 opener       |
| p287        | **9,852** sessions / 514,296 msgs / 1,461 FLWs / **27** topics       | vs static forms        |
| p377        | **72** cohorts, **1449** FLWs, **9833** started / **9341** completed | Finding 2              |
| p442        | **8,328** interviews (89%), $3.05, $3.42, $6.82                      | Finding 2 costs        |
| p710/713    | **10,115** interviews, **28** topics, **1,461** FLWs                 | Finding 3.1            |
| p768 / p777 | 8,313 / 8,619                                                        | LLM Evaluations        |
| p858        | **1,454** FLWs, "**seven** cohorts"                                  | Project Implementation |
| p1044       | ~1,449 FLWs, ~**72** cohorts                                         | Uncertainties          |

**They are not all wrong - they are different UNITS and different CUT DATES:**

- **9,464 completed / 9,960 started** = Connect interview SLOTS, live render v182+, 2026-08-25 19:18 UTC
- **10,115** = sessions in the ANALYSIS corpus (`insights_payload`, 24 Aug), incl. sessions that never
  began an interview
- **10,060 began / 9,601 completed** = archive, hand-computed 25 Aug
- **1,449** = FLWs who started interviewing (live) vs **1,461** = FLWs in the analysis corpus vs
  **1,454** = FLWs trained
- **72 vs 73** cohorts = before/after NPS onboarding
- **27 vs 28** topics = before/after a topic was added

⭐⭐ **THE NUMBERS MOVE DAILY, WHICH IS WHY A REGISTER IS NEEDED.** Live went from
**9,957 started / 9,460 completed at 09:33 UTC** to **9,960 / 9,464 at 19:18 UTC on the same day** -
two more refresh runs landed (18:54 and 19:09; two earlier ones at 18:22 and 18:35 FAILED).
**Every headline figure must carry its source and cut date, and the report should freeze ONE cut.**

## 5p. WARNING: `state.external_id` IS NOT THE FLW IDENTITY - use `participant.identifier`

I nearly published a corpus-wide FLW count of **2,952**. It is wrong by roughly 2x.

| Key                      | Distinct values (interviews that began, non-test) |
| ------------------------ | ------------------------------------------------- |
| `state.external_id`      | **2,952**                                         |
| `participant.identifier` | **1,460**                                         |

**976 participants hold more than one `external_id`** - it is issued per cohort/opportunity, not per
person, so anyone in two cohorts is counted twice. Example: participant `f875545b28e1b2bda1d4` holds
both `861130f0f04745fd8c2d0a261f62a70b` and `c9b2105406254f91be2b13bb5f8c0b6a`.

**`participant.identifier` gives 1,460, which ties to `insights_payload` L0_corpus.flws = 1,461.**
Some identifiers are staff emails (e.g. `kmehrotra@dimagi.com`) - exclude any containing "@".

PANEL retention is NOT affected - checked: 363 by participant vs 364 by external_id, because PANEL
FLWs sit in one cohort each. Median 11, >=8 interviews 75.5%, full 13 = 92 FLWs all stand.
**But any CORPUS-WIDE per-FLW figure must be re-keyed.**

## 5q. THE FOUR LEGITIMATE FLW COUNTS - all different, all correct

| Value     | Means                                                | Source                                                                                       |
| --------- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **1,454** | FLWs invited/trained in the phase-1 Training cohorts | `connectFunnel` TRS 1,335 + TRE 119; ties to Kebbi 404 + Bauchi 385 + Borno 368 + Sokoto 297 |
| **1,449** | unique FLWs _reached_ across all 73 cohorts          | `_live_full.json` `counts.flws`                                                              |
| **1,441** | unique FLWs who _started_ at least one interview     | `_live_full.json` `table1` Overall `flws`                                                    |
| **1,461** | FLWs in the _analysis corpus_                        | `insights_payload.json` `L0_corpus.flws`                                                     |

They are 20 apart and will read as drift unless all four are defined. **A sentence saying "started
interviewing" must use 1,441, not 1,449.**

## 5r. Finding 2 figures - verified 2026-08-25, four are UNSOURCED or WRONG

| Para        | Claim                                      | Verdict                                                                                                           | Correct value                                                                       |
| ----------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| p377        | 72 cohorts, 9,833 started, 9,341 completed | **STALE** (~2026-08-20 cut)                                                                                       | 73, **9,960**, **9,464**                                                            |
| p377        | 1,449 FLWs; 95% completion                 | **CORRECT**                                                                                                       | keep (94.98%)                                                                       |
| p377 table  | Training "completed >=1" = 1,454           | **WRONG** - pasted from Invited                                                                                   | **1,392**                                                                           |
| p442        | **$3.05** per interview                    | **UNSOURCED** - implies a $28,490 total that exists nowhere                                                       | **$3.29** ($31,173 / 9,464)                                                         |
| p442        | **8,328** interviews (89%) acceptable      | **UNSOURCED**; denominator is the stale 9,341                                                                     | **8,239 of 8,546 reviewed = 96.4%**; 87.1% of all completed; **918 never reviewed** |
| p442        | $3.42 per quality interview                | arithmetic right, inputs bad                                                                                      | $3.42 by a sound route, or **$3.78** strict                                         |
| p442        | **$6.82** all-in                           | **UNSOURCED** - no operational cost data exists in the repo                                                       | cannot be computed; needs the author's workings                                     |
| p442        | "5 to 23 questions"                        | **WRONG** upper bound                                                                                             | **5 to 20** (`Topics_Master` max = 20)                                              |
| p649/659    | 78% finished                               | **CORRECT**                                                                                                       | keep                                                                                |
| p649/659    | 19% dropped                                | **WRONG** rounding (19.64%)                                                                                       | **20%**                                                                             |
| p649/659    | base 1,449 "started"                       | **WRONG** quantity                                                                                                | **1,441**                                                                           |
| p649/659    | "remaining were inconsistent"              | **WRONG** - conflates two unrelated 19%s                                                                          | they were _Waiting_: had done everything sent                                       |
| p649 + p659 | the paragraph itself                       | **DUPLICATED** - verified verbatim, p649 has one extra trailing sentence; both mis-anchored (Panel / 2-Week Test) | delete one, move the survivor                                                       |
| p858        | "seven cohorts"                            | **DIFFERENT-UNIT + STALE**                                                                                        | **eight cohort types / 73 cohorts**                                                 |
| p858        | 1,454 trained                              | **CORRECT**, distinct from 1,449                                                                                  | keep, define both                                                                   |
| p313        | all seven probing figures                  | **CORRECT** - recomputed from `probing_windows.csv`                                                               | keep the upper-bound caveat on 20,651                                               |

`reviewStatus.overall` ties exactly: 8,239 + 132 unacceptable + 175 suspected_ai + 918 not-reviewed
= **9,464** = `counts.completed`.

**Two open problems beyond the figures.** (1) The OCS review tags DISAGREE between
`_ocs_tag_census.json` / `_ocs_tags_cache.json` (8,441 acceptable) and `_ocs_messages.jsonl` (9,206) -
**765 apart**; any published quality rate depends on which is right. (2) The pay-weighted FLW payment
total **$31,173 exceeds the recorded $25,000 FLW payment budget by $6,173**; the tracker hides this
because its PANEL row still carries a 1,413 projection against 3,437 completed and omits EXT and NPS.

## 5s. Building a figures register - what actually works (researched 2026-08-25)

**There is NO established name for this artifact.** Do not invent one. Nearest real precedents to cite:
the M&E pair **PIRS** (definitions only - USAID: "PIRS are not the place to document actual data or
results") and **PITT / IPTT** (the values table, officially templated by State, FANTA, MCC); plus
**PCAOB AS 1215 .13**, the engagement completion document, which holds findings "or cross-references,
as appropriate, to other available supporting audit documentation". **"fact table" collides with
Kimball dimensional modelling - do not use it.** The established term for a cut date is **"vintage"**
or **"as-of date"** (St. Louis Fed ALFRED).

**Google Docs mechanics, verified:**

- **Variable chips are the best option IF the Workspace edition has them.** Real feature
  (`Insert > Smart chips > Variables`; `Tools > Variables` opens a panel listing all of them). Change
  the value once and every occurrence updates, which **removes the duplicate-figure problem entirely**
  rather than helping you navigate to duplicates. Editions: Business Standard/Plus, Enterprise
  Standard/Plus, Education Plus, Nonprofits. **NOT** Business Starter or personal accounts.
  **One-minute check needed for dimagi.com.** No API or Apps Script path exists (all 48
  `batchUpdate` request types checked) so the weekly update is manual. Export behaviour undocumented.
  Danger: deleting a chip in the panel **removes every instance in the document**.
- **Bookmarks: reject.** They **cannot be named**, so ~60 anchors become an unlabelled picker list. The
  Docs API **cannot create or enumerate them** (no `CreateBookmarkRequest`); only Apps Script can
  (`Document.addBookmark`). **Internal links BREAK on .docx round-trip** - Microsoft staff, Nov 2025:
  "Google Docs does not fully support Word bookmarks." The .docx is what reviewers read.
- **Heading links: the most robust anchor.** `ParagraphStyle.headingId` is read-only and Docs-generated
  (`h.<random>`), so **rewording a heading does not break the link**.
- **A typed `[F-07]` tag convention is legitimate practice**, not a hack: audit tick marks are
  explicitly non-standardised, firms use house conventions **with a legend**. But **Google Docs has no
  hidden-text feature** - white or 1pt text still exports and is still searchable in the PDF, so tags
  CAN ship to the funder. Mitigation: `Find and replace` has an official **"Match using regular
  expressions"** option, so the tag pattern clears in one pass as a fixed pre-export step.
- **Named ranges: wrong for humans, right for machines.** Zero user-facing surface, no UI, not
  linkable. But `ReplaceNamedRangeContentRequest` is the documented way for a script to overwrite a
  value in place.
- **Sheets-to-Docs linking is block-level and MANUAL.** Only charts, tables and slides can be linked;
  **there is no inline linked value**, so a number inside a sentence cannot auto-update. Tables over
  **400 cells** paste unlinked. No auto-refresh, and **the update click cannot be automated** (the
  Slides API has `RefreshSheetsChartRequest`; the Docs API has no equivalent).

**Recommendation: variable chips if the edition allows, otherwise heading links with the section named
in words PLUS regex-strippable tags. Never rely on internal links surviving export.**

## 5t. SETTLED by test 2026-08-25: Google Docs variable chips DO survive .docx export

Google documents this nowhere; the user tested it on dimagi.com's Workspace edition at my request.
Results of the three checkpoints:

| Check                                                                   | Result                                                          |
| ----------------------------------------------------------------------- | --------------------------------------------------------------- |
| Grey pill visible in the editor                                         | **NO**                                                          |
| Value auto-updates every occurrence when changed in `Tools > Variables` | **YES**                                                         |
| Survives `.docx` export as plain value                                  | **YES** - "Interviews completed: 9464" came through Word intact |

**The auto-update is the proof the chip is real.** Plain text cannot do that. So variable chips are the
confirmed register mechanism for this report (`Insert > Smart chips > Variables > Insert new
variable`), and the 5s fallback (heading links plus regex-strippable tags) is not needed.

⚠️ **BUT: chips are visually indistinguishable from ordinary typed numbers in this Workspace version.**
No pill, no shading. Consequences that matter:

- You cannot tell by eye which figures are chipped and which are still hard-typed. **`Tools >
Variables` is the only source of truth** - it lists every chip in the document.
- A half-finished conversion is invisible. Convert figure-by-figure and tick each off the register.
- Someone can retype over a chip and silently break the link, with nothing on screen to show it.
  Re-check the panel before each weekly update.

⚠️ **Deleting a chip in the `Tools > Variables` panel removes EVERY instance of it in the document.**
Delete occurrences in the text, never in the panel.
⚠️ No API or Apps Script path exists (all 48 `batchUpdate` request types checked), so the weekly value
update is a human editing the panel. For ~8 figures that is a few minutes.

**The naming trap that matters most:** `flws_reached` (1,449), `flws_started` (1,441) and
`flws_trained` (1,454) must be THREE separate chips. They are three different real quantities. One
chip for all three would silently make the report wrong, and with no visible pill the error would be
invisible.

## 5u. THE SCALE SUPERLATIVE IS DEAD - verified 2026-08-26. Do not claim it again.

I have now made a version of this claim THREE times and it has failed twice under adversarial search.
My own rule in section 1 already said "try to break your own claim before publishing it" and cited the
first failure. I wrote the rule and then drifted back into the claim. **Stop claiming it.**

### The decisive fact is internal, not in the literature

**Our LLM-driven analysis covers 6,712 sessions, not ~9,880.** Counted by unioning the distinct
`session_id` values across every `typology_classifications*.csv` and `answers_scored*.csv` in the
Dimagi Outputs pack (typology 6,494; answers_scored 6,712; union 6,712).

The corpus is ~10,000 interviews. **The interpretive LLM analysis covered 6,712 of them.** Those are
different numbers and only the second one supports an "LLM-analysed corpus" claim.

Separately, the LLM **evaluator** (rubric scoring) reviewed **8,464** of 9,382 completed interviews,
918 never reviewed. That is a different task class - and it is the SAME task class as micro1's, so it
buys no distinction.

### micro1 is 6,500, not 300,000 - and it IS LLM analysis

Verified from the full text of arXiv:2507.16835 myself:

- Analysed sample is **6,500** (5,000 for Google x GPT-4.1 x OpenAI, plus 500 each for three other
  stacks). **The 300,000 is the production pool sampled FROM**, not the analysed set.
- They used **Claude 3.5 Sonnet as an LLM judge** scoring transcripts on Question Quality,
  Conversational Flow and Answer Assessment, explicitly "to reduce human grading costs".
- Their interviews are adaptive audio, with follow-ups generated from prior turns. **Calling them
  "structured screening" is a stretch.**

**So: ours 6,712 vs micro1 6,500 = 1.03x.** Not orders of magnitude. Three percent.

⚠️ **Two supporting sentences I published are FALSE and must come out:**

- "one to two orders of magnitude smaller than this corpus" - there is no order-of-magnitude gap to
  anything.
- "the largest comparable corpora are 1,000 to 1,600 documents" - micro1 sits at 6,500.

### The comparator baseline, now verified (I had carried both unverified through three documents)

| Corpus                                                              | n                                       | What the LLM did                                                                 | Status                                                                                        |
| ------------------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Open-text survey answers, Mellon et al. 2024, _Research & Politics_ | **81,266**                              | assigned one of **50 fixed categories** to one short answer                      | **peer-reviewed**; excluded as closed-set classification of a survey question, not interviews |
| InterviewSim, arXiv:2602.20294                                      | 23,000 transcripts                      | personality simulation, not analysis of content                                  | preprint                                                                                      |
| Displaced Karelians, arXiv:2602.15436                               | 89,339 in archive                       | classified **71,874 extracted entity names**; **the LLM never saw an interview** | preprint; cleanest exclusion                                                                  |
| CallCenterEN, arXiv:2507.02958                                      | 91,706 call transcripts                 | **no LLM analysis in the paper**; dataset release only                           | preprint                                                                                      |
| **micro1**, arXiv:2507.16835                                        | **6,500**                               | Claude 3.5 Sonnet judge on 3 dimensions                                          | preprint; **the true peer**                                                                   |
| Holocaust testimonies, arXiv:2605.21623                             | **1,668** (1,000 Shoah + 668 Fortunoff) | ChatGPT labelled **every Q/A pair**, full corpus                                 | preprint; genuinely LLM-driven                                                                |
| JAIOH oral histories, arXiv:2508.06729                              | **1,002** (92,191 sentences)            | full-corpus LLM semantic + sentiment annotation                                  | preprint                                                                                      |

Both figures I had been carrying unverified turned out **real** - 1,600 is 1,668, and 1,002 is exact.
But I should have retrieved them before publishing them three times.

### Which distinctions hold

- **Open-ended multi-turn vs closed-set classification: HOLDS, and it is now load-bearing.** It is the
  only thing standing between us and Mellon's 81,266. State it up front rather than burying it.
- **Collection vs analysis: DOES NOT HOLD. Abandon it.** micro1 did analyse content with an LLM. We
  no longer need the technicality because 6,500 < 6,712 on the plain numbers.
- ⚠️ **New exposure:** if our own LLM work is mostly rubric-style classification rather than
  interpretive thematic analysis, micro1 is a true peer and the distinction collapses to "3% more".

### The only claim worth making

Not a size record. **Design novelty:** no published study analyses _repeated_ interviews with the
_same workforce_ in a _low-resource language_. That is harder to refute and more interesting.

And if a scale sentence is wanted, name the bigger non-interview corpora ourselves - that reads as
diligence. "That we are aware of" with no stated search reads as weasel wording, because one Scholar
query surfaces Mellon.

⚠️ **Live counts moved again during this check: completed 9,464 (19:18 UTC 25 Aug) -> 9,382.**

## 6. Known defects not yet fixed

- `TOPIC_QUESTIONS["99"] = 1` should be 9.
- The `barrier` gem detector fires about half the time on a bare negation or a good outcome. The
  named-shortage list derived from it should not be quoted until tightened.
- The `data_quality` gem category is a mislabel - every member is a one-word answer, published as
  "junk". Rename it.
- Two topics carry the placeholder name `te001_topic`.
- `pull_hq_user_cases.py` covers 8 of 12 domains, so 2WT and ABT3 default to "trained".
- `ai-review.yml` posts empty reviews on every PR and costs tokens.
- Nothing validates the JSX before the dashboard publishes. Gate F is a substring and size check only.
- `CONNECT_SNAP_1/2/3` are from 2026-06-24 and the reassembly step ends in `|| true`, so a failure is
  silent.

## 7. People, and what they care about

| Person           | Role                            | Watch for                                                                                          |
| ---------------- | ------------------------------- | -------------------------------------------------------------------------------------------------- |
| **Neal Lesh**    | Analytic design, reviews drafts | Particular about writing and about analysis. Owns the typology work. Going offline.                |
| **Ali Flaming**  | Reviews Finding 3               | Asks precise, structural questions. Chief strategy officer - be brief.                             |
| **Andrea King**  | Reviewer                        | Catches methodological confounds and provenance errors. Her intuitions are worth testing properly. |
| **Mansi Narang** | Coordinates the report          | Checks whether two numbers on different screens agree.                                             |
| **Leah Ng'aari** | OCS and evals                   | Source of truth on the evaluator and the annotation rounds.                                        |
| **Simon Kelly**  | OCS owner                       | Flagged rate limits. Keep the daily pull incremental.                                              |

---

_Keep this file current. When something is learned, corrected or decided, add it here rather than
leaving it in a chat log._
