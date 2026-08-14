# Does the chatbot's probing improve the data?

**Bottom line.** The chatbot notices a weak answer and asks again. That single behaviour turned **20,651 unusable answers into usable ones** — **21.3% of every usable answer we hold**. A static form cannot do this, because in a form the first answer is the final answer.

*Data as of 2026-08-13: 9,852 interview sessions, 514,296 messages, 1,461 FLWs, 27 topics — pulled from the live chat transcripts. Every number here is computed from those transcripts at the moment this document was generated.*

## 1. What 'probing' means

When an FLW gives a thin answer, the AI interviewer does not accept it and move on — it asks again, rephrasing or pressing for a specific example, and the FLW cannot progress until the answer is good enough. **That follow-up is a probe, and it is the one thing a paper or online form cannot do.**

*One measurement point, because it changes the numbers: most topics give the bot a single question containing several sub-questions, so it has to walk the FLW through them. Moving to the next sub-question is the interview proceeding, not a probe. Only turns that go back over a question already asked are counted here.*

## 2. How often the bot pushed back, and what set it off

Across **112,864 questions** actually put to an FLW, the bot probed on **70,655 of them (62.6%)** — 123,798 probing turns in all. Where it probed, it probed 1.75 times on average.

**What set it off.** Judged from the FLW's answer immediately before each probe:

| Reason the bot probed | Questions | Share |
|---|---|---|
| answer was thin — on topic, too shallow to use | 37,603 | 53.2% |
| answer was too short to carry any content | 22,947 | 32.5% |
| a number was asked for and not given | 9,096 | 12.9% |
| nothing was said at all | 419 | 0.6% |
| said "don't know" | 401 | 0.6% |
| FLW said they did not understand | 189 | 0.3% |

Most probes are chasing **depth**, not fixing a refusal — genuine non-answers ("don't know", nothing said, confusion) are under 1.5% combined. Separately, **12.9% of probes** were the bot chasing a number it had asked for and not received — a gap a form cannot even detect, let alone fix.

**What kind of probe.** Coded using the DICE scheme from the qualitative-interviewing literature (Robinson, 2023 — see References), not labels invented for this analysis:

| Probe type | Probes | Share |
|---|---|---|
| asking for detail or an example | 52,517 | 42.4% |
| other / not classified | 34,988 | 28.3% |
| checking it understood correctly | 22,415 | 18.1% |
| asking for a specific remembered case | 6,988 | 5.6% |
| asking why / how they know | 4,236 | 3.4% |
| asking for anything further | 2,654 | 2.1% |

## 3. What a Google Form would have captured instead

### How we worked this out

In a form, the first answer is the final answer — there is no one to notice it is thin. So for every question we already hold both halves of the comparison:

- **The "form" answer** — everything the FLW typed before the bot first pushed back.
- **The actual answer** — everything they had said by the time the bot moved on.

Both are then judged by the same simple test: an answer counts as **usable** if it is not blank, is longer than three words, and is not an explicit "I don't know" or "I don't understand". Same question, same FLW, same moment — the only difference is whether the probe happened. Nothing is compared across different people or different questions.

**21.3% of the usable answers we hold began as unusable ones.** Of 97,013 questions that ended usable, 20,651 were blank, too short, or a "don't know" at first attempt. In a form, that first attempt is what we would have filed.

|  | A static form would have got | What we actually got |
|---|---|---|
| Questions with a usable answer | 67.8% | 🟢 86.0% |
| Words per answer (average) | 10.7 | 22.1 |
| Words per answer (typical) | 6.0 | 14.0 |

That is **18.2 percentage points** more usable data from the same interviews with the same people. Question by question, 20,651 answers moved from unusable to usable and only 107 moved the other way.

### Does the result depend on where we set the bar?

"Usable" is a word-count test, so an answer can cross the line without really improving — reading cases by hand found one FLW going from "9" to "9 0 not available", which the test scores as a save and a reader would not. **15.0% of saves** are that marginal. Here is the headline again with every one of them thrown away:

|  | As measured | Throwing away every marginal save |
|---|---|---|
| Questions with a usable answer | 🟢 86.0% | 🟡 83.2% |
| Answers rescued by probing | 20,651 | 17,553 |
| Share of usable answers rescued | 21.3% | 18.7% |

The finding moves 2.6 points under the harshest test we can apply, so it does not rest on where the bar sits.

**By language.** Shown because the usable test counts words, and Hausa may carry the same meaning in fewer of them — publishing the split is what makes any measurement bias visible:

| Language | Questions | A form would have got | We actually got | Rescued |
|---|---|---|---|---|
| english | 65,500 | 64.2% | 🟡 84.5% | 13,340 |
| hausa | 46,415 | 72.7% | 🟢 88.1% | 7,132 |
| unknown | 656 | 62.2% | 🟡 83.7% | 141 |
| mixed | 293 | 75.1% | 🟢 88.1% | 38 |

**By topic**, largest first:

| Topic | Questions | A form would have got | We actually got | Rescued |
|---|---|---|---|---|
| Community Demographics | 15,751 | 54.5% | 🟡 75.8% | 3,345 |
| Malaria | 13,632 | 67.6% | 🟡 84.2% | 2,261 |
| Bed Net Usage | 12,088 | 75.2% | 🟢 86.9% | 1,426 |
| Seasonal Malaria Chemoprevention 2 | 9,837 | 68.1% | 🟢 89.0% | 2,079 |
| Malaria 5 | 9,815 | 63.1% | 🟢 87.1% | 2,385 |
| Seasonal Malaria Chemoprevention | 9,613 | 73.3% | 🟢 91.3% | 1,737 |
| Health Worker Experience | 8,879 | 66.5% | 🟡 79.8% | 1,181 |
| Vitamin A Supplementation | 5,560 | 70.7% | 🟢 89.5% | 1,056 |
| Community & FLW Profile 2 | 4,114 | 74.4% | 🟢 87.0% | 521 |
| Nutrition Prevalance and Programs | 3,719 | 63.7% | 🟢 90.0% | 981 |
| Water & Diarrhea 2 | 3,690 | 70.6% | 🟢 92.5% | 815 |
| Vaccines | 3,304 | 67.6% | 🟢 91.3% | 786 |

## 4. Where probing stops helping — and what it costs

Probing is not free. The closest published study of this approach (1,800 participants — see References) found it produced richer answers **but cost respondents some patience**. So we measured that here rather than leaving it for someone else to ask.

**Does the third probe still earn its keep?**

| Probing turns | Questions | Ended usable | Started unusable | Turned around |
|---|---|---|---|---|
| 0 | 42,209 | 🔴 70.3% | 12,540 | n/a |
| 1 | 44,419 | 🟢 94.0% | 13,425 | 🟢 80.2% |
| 2 | 15,701 | 🟢 97.3% | 5,942 | 🟢 93.5% |
| 3+ | 10,535 | 🟢 97.9% | 4,488 | 🟢 96.5% |

*The top row is a definition, not a result: with no probe there is no before and after, so nothing can be turned around. The meaningful comparison is between one, two and three-or-more probes.*

| Which probe | Probes | FLW answered it | Words they gave back |
|---|---|---|---|
| 1 | 70,655 | 🟢 97.9% | 11.3 |
| 2 | 26,236 | 🟢 96.0% | 9.6 |
| 3 | 10,535 | 🟢 95.7% | 8.9 |
| 4+ | 16,372 | 🟢 96.2% | 8.7 |

FLWs almost always answer a probe — 97.9% after the first, 96.2% by probe 4+. But **what they say gets shorter**: 11.3 words after the first probe against 8.7 by probe 4+, 23% less. Later probes still get a reply but extract steadily less, which is the argument for capping probes per question rather than letting them run.

**Does pushing harder drive people away?**

| Probes per question | Sessions | Finished the interview | Questions reached |
|---|---|---|---|
| 0 | 1,263 | 🟡 94.4% | 12.9 |
| 0.5-1 | 3,362 | 🟢 97.6% | 12.4 |
| 1-2 | 4,070 | 🟡 94.8% | 11.0 |
| 2+ | 1,122 | 🔴 86.5% | 9.2 |

*This is a correlation, not proof of cause — heavy probing and early exit can both simply follow from an FLW who is struggling. Completion falls from 94.4% to 86.5% as probing intensity rises, which is worth watching.*

## 5. Does needing a probe mean the FLW did badly?

### Where these numbers come from

These are **not** our numbers. As part of the daily review, the team reads sessions in OpenChatStudio and tags them `acceptable` or `unacceptable` by hand. Those tags travel with the session and come back through the API, so they are an independent human judgement we can test our automated measures against. There are 9,330 tagged sessions (8,761 acceptable, 569 unacceptable).

This matters because the team's own review notes record a genuine disagreement: one reviewer treats bot prompting as the chatbot doing its job, while others mark the need for probing against the FLW. That inconsistency distorts anything built on these tags — so here it is as numbers.

| Human verdict | Sessions | Probes per question | Ended usable | Turned around when unusable |
|---|---|---|---|---|
| acceptable | 8,761 | 1.07 | 🟢 86.9% | 57.9% |
| unacceptable | 569 | 1.32 | 🟡 76.0% | 50.2% |

**Sessions the team judged poor were probed more and recovered less** (1.32 vs 1.07 probes per question; 50.2% vs 57.9% turned around). So heavy probing is a **symptom** of a struggling session, not the cause of one — and the reviewer who reads a probe as the bot working correctly has the evidence on their side: the probe is what rescues the recoverable cases.

*Suggested change to the annotation guidance: record bot prompting as its own flag, and do not let it lower an FLW's rating on its own.*

## 6. Did prompt iteration change the bot's behaviour?

Every bot message is stamped with the prompt version that produced it, so we get a free record of how the bot behaved across releases:

| Prompt version | Questions | Probed | Probes per question | A form would have got | We actually got |
|---|---|---|---|---|---|
| v32 | 1,937 | 44.5% | 0.62 | 62.5% | 🟡 78.0% |
| v33 | 470 | 47.7% | 0.68 | 52.3% | 🔴 70.0% |
| v34 | 8,549 | 48.2% | 0.7 | 56.6% | 🔴 74.0% |
| v35 | 9,114 | 49.0% | 0.72 | 63.5% | 🟡 78.9% |
| v37 | 10,694 | 65.5% | 0.92 | 66.4% | 🟢 87.3% |
| v38 | 9,525 | 55.9% | 0.8 | 70.8% | 🟢 86.1% |
| v39 | 7,663 | 55.7% | 0.84 | 71.6% | 🟢 86.2% |
| v41 | 5,144 | 54.8% | 0.83 | 74.2% | 🟢 87.1% |
| v43 | 1,096 | 43.2% | 0.61 | 75.3% | 🟢 85.3% |
| v46 | 4,556 | 74.5% | 1.4 | 67.9% | 🟢 89.9% |
| v48 | 429 | 73.7% | 1.48 | 64.3% | 🟢 86.7% |
| v49 | 3,144 | 71.3% | 1.46 | 70.7% | 🟢 90.1% |
| v50 | 1,468 | 65.4% | 1.24 | 72.5% | 🟢 89.6% |
| v51 | 12,820 | 69.4% | 1.51 | 66.4% | 🟢 87.5% |
| v52 | 16,776 | 69.3% | 1.44 | 68.2% | 🟢 88.3% |
| v54 | 14,673 | 69.8% | 1.25 | 70.6% | 🟢 89.6% |
| v55 | 4,777 | 71.4% | 1.18 | 71.7% | 🟢 89.5% |

From v32 to v55, the share of questions probed moved up 26.9 points and usable answers moved up 11.5 points (78.0% to 89.5%). The bot became more willing to push back, and the data improved alongside it.

*Directional only. Versions run in calendar order and the topic mix changed with them, so a difference between versions is not evidence the prompt change caused it. Read this as what the bot was doing then, not as an experiment.*

## 7. In short

The whole document on one page.

- **What probing is.** The bot spots a weak answer and asks again; the FLW cannot move on until it is good enough. A form cannot do this.
- **How often.** It pushed back on 62.6% of 112,864 questions, 1.75 times on average where it did. Mostly chasing depth, not fixing refusals.
- **What it bought us.** Usable answers went from 67.8% to 86.0% — 20,651 answers rescued against 107 made worse. That is 21.3% of all our usable data, or 18.7% on the strictest reading.
- **Where it stops.** One probe turns around 80.2% of failed answers. FLWs keep replying to later probes but say less each time — the case for capping probes per question.
- **Needing a probe is not the FLW's failure.** Sessions the team judged poor were probed more and recovered less, so probing is a symptom, not a cause. The annotation guidance should say so.
- **Over time.** The bot probes more than it used to and the data is better than it was, though the two cannot be causally linked from this evidence alone.

### What this does not claim, and how far to trust it

- **We did not run a Google Form.** No form dataset exists for these FLWs. The comparison rests on the fact that a form cannot re-ask, so the pre-probe answer is what one would have captured. That is a property of the instrument, not an experiment.
- **"Usable" is a crude test** — not blank, over three words, not an explicit "don't know". It says nothing about whether an answer is true, relevant or deep. Scoring those five quality dimensions properly needs an AI judge marking each answer before and after probing; that is the next stage.
- **We never compare probed answers against unprobed ones.** The bot probes *because* an answer was weak, so that comparison would make probing look harmful. Every comparison here is the same answer before and after.
- **Nothing here proves a prompt version caused anything.**
- **This check was done by AI, not by a person.** 67 bot turns were picked at random, labelled without seeing what the classifier had said, then compared. The classifier agreed 89.6% of the time (91.7% on new questions, 80.0% on probes). But the labelling was done by the same AI that built the classifier, so it catches obvious mistakes rather than proving accuracy. Someone on the team can label the same turns to get a proper human figure.
- **The question list is imperfect.** Most topics bundle several questions into one block, which we split automatically. On 95,019 questions the bot announced its own part number: 78.4% matched our split. The rest are counted correctly using the bot's own wording, but the question list should not be treated as definitive.
- **Coverage.** Questions were reconstructed for 99.6% of the 9,852 sessions analysed. A further 11,848 were set aside — almost all of them sessions where no interview was ever assigned, because the FLW opened the chat and stopped at the welcome step. Those are not failed interviews; they never started one.

### How we measured this

Every session was pulled from OpenChatStudio with its full message list — 21,700 sessions and 542,328 messages, checked against an independent export to confirm nothing was missing. The question list was rebuilt from the sessions themselves, since each one carries the exact questions it was given. Within each session, every bot turn was classified as either opening a new question or going back over the open one, using four independent signals led by the position the bot states itself. The FLW's replies were then attached to whichever question was open, which is what gives us the answer before the probe and the answer after it.

*Colour on the numbers is a reading aid: **green** = strong, **amber** = watch, **red** = weak. It is applied only where better and worse are genuinely defined — never to counts, to the probe rate, or to probes per question, because a high or low value there is not good or bad in itself.*

### References

External sources used for method and comparison. The first two are the closest published work to what we are doing and are the right citations if this is challenged.

- **Xiao, Zhou, Fu et al., "Tell Me About Yourself: Using an AI-Powered Chatbot to Conduct Conversational Surveys with Open-ended Questions."** ACM Transactions on Computer-Human Interaction 27(3), 2020. https://dl.acm.org/doi/10.1145/3381804 — ~600 participants and 5,200 free-text answers comparing a chatbot against a standard online survey. The chatbot produced significantly better quality on informativeness, relevance, specificity and clarity. This is the benchmark our result points the same way as, and it is also independent evidence that the quality dimensions we use are an established framework rather than an in-house invention.
- **"AI-Assisted Conversational Interviewing: Effects on Data Quality and Respondent Experience."** arXiv:2504.13908, 2025. https://arxiv.org/abs/2504.13908 — 1,800 participants with LLM chatbots probing for elaboration. Answers were more detailed and informative, but at a slight cost to respondent experience. This is why Section 4 measures the cost of probing rather than reporting only the benefit.
- **Robinson, "Probing in qualitative research interviews: Theory and practice."** Qualitative Research in Psychology, 2023. https://www.tandfonline.com/doi/full/10.1080/14780887.2023.2238625 — the DICE taxonomy (descriptive-detail, idiographic-memory, clarifying, explanatory probes) used to classify probe types in Section 2, so those labels come from the literature rather than from us.
