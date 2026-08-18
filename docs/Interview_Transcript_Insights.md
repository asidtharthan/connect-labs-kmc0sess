# What the interviews actually contain

A complete read of every interview transcript on record, from the individual message up to the programme as a whole, with 384 verbatim extracts. Generated 2026-08-18.

*Every session in the archive was scanned: 21,916 sessions containing 547,445 messages. Nothing was sampled for the counts, and every figure in this document is read from that scan rather than typed in.*

## What this is, and what it is not

This is the open question - what is actually in these conversations - rather than a test of any single hypothesis. It is meant to be useful in three ways: as an orientation for anyone new to the project, as a source of real quotes for reports and presentations, and as a starting point for further analysis, since the full extract dump ships alongside it as a spreadsheet.

- **The counts cover everything.** No sampling, no shortcuts. The coverage figures are reported below and were checked by a separate audit script that recomputes them from the archive.
- **The quotes are real and unedited.** Spelling, grammar and code-switching are exactly as written. Every quote was verified to appear word for word in the session it is attributed to.
- **Both languages are represented.** Roughly 40% of interviews run in Hausa, so the detection rules were built from the corpus's own vocabulary in both languages. An English-only approach would have quietly concluded that Hausa-speaking FLWs had less to say.
- **No identities.** No worker identifier appears anywhere. Session references are truncated, and anything resembling a phone number or email was removed before quoting.

## Coverage: what was read, and what was set aside

|  | Sessions | Note |
|---|---|---|
| In the archive | 21,916 | everything OCS holds for this programme |
| Analysed here | 9,952 | carried an interview and had a conversation |
| No interview assigned | 11,891 | opened the chat and stopped before an interview began |
| Test topics | 52 | internal test scripts |
| Marked as test | 21 | flagged Test upstream |

The 11,891 sessions with no interview assigned are the largest exclusion and are worth understanding: these are people who opened the chat and stopped at the welcome or language step, before any question was put to them. They are not failed interviews. They never started one.

*Every session is therefore accounted for: 9,952 analysed plus 11,964 excluded for a stated reason equals the 21,916 in the archive. That reconciliation is checked automatically, so a session cannot be dropped quietly.*

## Level 1: the messages

The analysed sessions contain 519,180 messages: 252,114 from FLWs, 262,422 from the interviewer, and 4,644 system messages.

*The system messages are not conversation. They are the bot compressing its own context in long sessions, averaging 298 words each. Anyone analysing this corpus should exclude them: counted as FLW text they would add roughly 1,384,006 machine-written words to the totals.*

| Message length (words) | FLW | Interviewer |
|---|---|---|
| Typical (median) | 6 | 49 |
| Average | 10.1 | 52.4 |
| Shorter end (10th percentile) | 1 | 26 |
| Longer end (90th percentile) | 23 | 86 |
| Longest single message | 1,063 | 291 |

The interviewer writes roughly 8.2 times as much per message as the FLW does. That is expected for this format - the bot restates the question, acknowledges the answer and asks the next thing - but it means message counts are a poor proxy for how much a worker actually contributed. Use words.

80 messages were platform errors, where the bot failed to process what the FLW sent. That is 0.03% of interviewer messages - rare, but each one interrupts a live conversation.

## Level 2: the answers

Across 113,093 answers, the typical answer is 15 words and the average is 22.3. The distribution is heavily skewed: a tenth are 3 words or fewer, a tenth are 47 or more, and the longest is 1,675 words.

| What the answer contains | Answers | Share |
|---|---|---|
| A number | 36,628 | 32.4% |
| Concrete subject matter (clinic, medicine, children, nets...) | 33,062 | 29.2% |
| A reason (because / saboda / domin) | 16,018 | 14.2% |
| Something absent (babu / rashin / no / not available) | 21,704 | 19.2% |
| A qualification (but / amma) | 9,514 | 8.4% |
| A candour marker (gaskiya / honestly) | 7,945 | 7.0% |
| An example (misali / for example) | 1,768 | 1.6% |

Roughly 14.2% of answers contain an explicit reason. That is the single most useful property of this dataset: it is not just what FLWs report, it is why they think it, which is what makes an estimate interrogable rather than a bare figure.

## Level 3: the questions

113,804 questions were put to FLWs, drawing 125,084 follow-up turns from the interviewer - 1.1 per question on average. The follow-up is the behaviour a paper or online form cannot reproduce: when an answer is too thin, the interviewer asks again rather than filing it.

In 20,861 cases the follow-up changed the outcome outright - the first attempt was blank, too short or an explicit do-not-know, and the final answer was usable. Section 'Answers the follow-up rescued' below shows what that looks like in practice.

## Level 4: the sessions

9,952 sessions. The typical one runs 62.2 minutes and 47 messages, and 94.7% reached completion.

But the spread is the finding here. A tenth of sessions finish within 25.6 minutes, while a tenth run beyond 455 minutes - and the longest spans 1,439 minutes. An interview is plainly not one sitting for many workers: they answer, leave, and come back. Any analysis that assumes a single continuous session, or that treats elapsed time as effort, will be wrong for a large minority of cases.

Sessions the team has reviewed by hand carry these tags:

| Tag | Sessions |
|---|---|
| acceptable | 8,853 |
| unacceptable | 581 |
| n/a | 501 |
| suspected_ai | 185 |
| run-on session | 3 |
| user_ai_response | 1 |
| potential_improvement | 1 |
| session_end_bug | 1 |

121 sessions are flagged upstream as suspected AI use - 1.2% of sessions. They are listed in the dump so the team can review them directly.

*Sessions start throughout the day, peaking at 14:00 UTC. Since work happens in Nigeria (UTC+1), read that as roughly 15:00 local.*

## Level 5 to 7: workers, topics and cohorts

1,461 individual FLWs took part. The typical worker completed 6 sessions and wrote 1,269 words in total; the most prolific wrote 20,955.

By topic, largest first. 'Words per answer' is the clearest signal of which subjects draw people out, and which do not:

| Topic | Sessions | Answers | Words per answer | Follow-ups per question | Do-not-know |
|---|---|---|---|---|---|
| code A | 1,437 | 15,685 | 13.2 | 0.76 | 1.4% |
| code B | 1,166 | 13,547 | 20.2 | 0.86 | 1.2% |
| Seasonal Malaria Chemoprevention | 979 | 9,510 | 25.6 | 1.21 | 1.4% |
| Seasonal Malaria Chemoprevention 2 | 920 | 9,772 | 22.8 | 1.12 | 2.4% |
| Bed Net Usage | 677 | 12,084 | 18.9 | 0.77 | 2.3% |
| Health Worker Experience | 599 | 8,887 | 19.8 | 0.77 | 1.0% |
| Malaria 5 | 525 | 9,774 | 29.4 | 2.02 | 2.6% |
| Nutrition Prevalance and Programs | 476 | 3,794 | 24.8 | 1.18 | 2.2% |
| Vaccines | 467 | 3,294 | 23.4 | 1.23 | 1.2% |
| Family Planning | 432 | 2,242 | 27.9 | 1.12 | 1.8% |
| Vitamin A Supplementation | 416 | 5,573 | 23.9 | 1.29 | 3.6% |
| Water & Diarrhea 2 | 376 | 3,869 | 27.4 | 1.49 | 2.8% |
| Community & FLW Profile 2 | 326 | 4,102 | 29.1 | 1.14 | 3.2% |
| Antibiotics and ACT Use | 264 | 2,893 | 25.9 | 1.18 | 3.5% |
| Malaria 2 | 239 | 1,951 | 38.7 | 1.67 | 3.9% |
| Medicine Quality and Counterfeiting 2 | 197 | 1,623 | 24.1 | 1.02 | 4.7% |

Among topics with enough volume to compare, **Malaria 2** draws the fullest answers at 38.7 words, and **code A** the shortest at 13.2. A 2.9-fold difference in how much people write is worth understanding before comparing findings across topics.

The topic where knowledge most often runs out is **Water & Diarrhea 4** (5.1% of answers contain an explicit do-not-know). That is a finding about the question set as much as about the workers.

## What FLWs say is missing

Built from the workers' own phrasing rather than a prepared checklist: every time an answer said 'no X', 'without X', 'rashin X' or 'babu X', the thing named was counted. The list below is the raw result, so it reads like speech rather than like categories.

| Named as missing | Times | Meaning |
|---|---|---|
| awareness | 216 |  |
| tsaro | 142 | security |
| kudi | 113 | money |
| sanin | 111 | awareness / knowing |
| samun | 110 | access to |
| money | 104 |  |
| knowledge | 84 |  |
| smc | 83 |  |
| nomadic | 76 |  |
| kudin | 71 | money for |
| abinci | 67 | food |
| abinda | 62 | (that which) |
| longer | 57 |  |
| nafdac | 54 |  |
| challenge | 53 |  |
| challenges | 53 |  |
| idps | 53 |  |
| kayan | 52 | supplies |

*Grouping the obvious synonyms across the two languages, the shortages FLWs name most often are **awareness and knowledge** (about 411 mentions), **money** (288), **security** (142), **access** (110) and **food** (67). Read this as what is top of mind for the people doing the work, not as a measured prevalence - the questions asked shape what gets mentioned.*

## The extracts

Twelve categories. For each: how it was detected, how many exist in the whole corpus, and a sample spread across topics and both languages. The full set of extracts is in the accompanying spreadsheet - what follows is a readable selection, not the whole dump.

### How these quotes are handled

- **Verbatim, not tidied.** Every quote is exactly what the worker typed - spelling, grammar, abbreviations and code-switching untouched. Nothing is paraphrased, corrected or summarised. Each one was checked automatically against the session it came from.
- **Two edits only, both mechanical.** Line breaks are collapsed to single spaces so a quote reads as one block, and anything shaped like a phone number or email is removed. Long answers are cut at a few hundred characters and end with an ellipsis; the spreadsheet carries the same text.
- **An answer can span several messages.** Workers often send a short line, get a reply, then continue. Where that happened the answer is their turns for that one question joined in order, which is still their words and nobody else's.
- **Illustration, not proof.** Quotes show what the data feels like; the counts beside them are the evidence. A handful of vivid extracts cannot demonstrate a pattern, which is why every category states how many cases exist in the full corpus.
- **Punctuation inside quotes is theirs, not ours.** The rest of this document uses plain hyphens, but quoted text keeps whatever the worker or the interviewer actually typed. Where a quote contains a long dash it is because it was written that way.
- **Chosen mechanically, not hand-picked.** Selection is by fixed rule and fixed random seed, stratified across topics, so nobody chose the flattering ones. Re-running reproduces the same set.

### Both languages

Interviews run in English and Hausa, and both are represented here rather than defaulting to the ones that happen to be readable in English. Hausa quotes are shown in the original with a line of key terms underneath, and every extract is labelled with its language.

What is deliberately NOT here is a translation. Guidance on multilingual qualitative research is to publish the original alongside a proper translation so bilingual readers can check it - but an unverified translation of a participant's words is worse than none, so none has been invented. The spreadsheet flags every Hausa extract and leaves an empty column for a Hausa speaker to fill in. That should happen before any of these quotes are used outside the team.

*One category is language-skewed by construction and should not be read as a difference between speakers: gaskiya is an everyday Hausa word appearing in roughly 4% of Hausa messages, whereas the English honestly is much rarer, so the candour category is mostly Hausa because of how the two languages work, not because Hausa speakers are franker.*

| Category | Found in corpus | Topics | In the dump |
|---|---|---|---|
| Unusually full answers | 9,148 | 27 | 162 |
| Answers that explain WHY | 13,587 | 28 | 163 |
| Problems and shortages reported | 5,410 | 26 | 151 |
| Numbers with reasoning attached | 5,379 | 28 | 157 |
| Candid and hedged answers (mostly Hausa) | 5,693 | 27 | 162 |
| Concrete examples given | 1,682 | 27 | 135 |
| Answers the probe rescued | 20,861 | 28 | 164 |
| Recovered from not understanding | 206 | 17 | 87 |
| Explicit 'I do not know' | 1,650 | 25 | 138 |
| Low-quality or junk answers | 6,059 | 28 | 159 |
| Platform errors mid-interview | 80 | 14 | 54 |
| Sessions flagged as suspected AI use | 121 | 19 | 86 |

### Unusually full answers

*Top-decile length with at least two specificity markers - the answers that actually carry content. Found 9,148 times across 27 topics (5478 english, 3583 hausa, 47 unknown).*

*Antibiotics and ACT Use 3 - hausa* - asked: When people are prescribed antibiotics or buy them, do most people finish the whole course, or do they stop early once they start feeling better? Why do you think people don't finish the whole course? Out of 10 sick peop...

> Eh toh, gaskiya kasan mutane ba son shan magani ake so ba, Amma da Zara wani ya samu sauki zai daina shan maganin wasu kuma suna Sha duka kwas din. Sai dai muna basu shawara su dinga shanye wa dukka kwas din. Cikin mutanen 10 muna tsammani Kashi bakwai (7) suna shanye wa.

*Key terms: gaskiya = honestly / truly; amma = but; magani = medicine; maganin = medicine for; mutane = people*

*Medicine Quality and Counterfeiting 2 - hausa* - asked: Have you ever heard of fake medicines or counterfeit drugs (in other words, medicines that don't work or are not what they claim to be)? Have you experienced this issue with Artemisinin-based Combination Therapies (ACTs)...

> aa bamutaba aa agaskiya babu eh matsala ne babba sabida zai iya cutar alumman yankin bamuda masaniya akan daga ina yake zuwa Babu dashi Babu sabida ba,ataba kamasuba Kuma muntaba ganiba daga shedan cewa maganin in gancecen ne dakuma Duba kwanakin bacin launin maganin Yana cenzawa yanagari kuma Aa bamutaba ganiba gaskiya sabida munada tabbacin ba,akawo maganinda bashiba keu basutaba gayamanace wa maganin nakaryabane e...

*Key terms: babu = there is none; gaskiya = honestly / truly; maganin = medicine for*

*Internal Topic - english* - asked: How does the pay for these interviews compare to what you earn from your other work - better, worse, or about the same? And what would make you want to keep doing interviews like this in the future?

> yes about desame yes is about the same because it's not always if to say it's every day or every two days if you calculate the money in a month will be much but it's less that is why the money wil not be difference it's good and helpful by gaining experience and the reward of money

*Family Planning - hausa* - asked: Are implants in stock when women want them?

> idan mutum nasoyi dole saiyaje asibiti saboda malamin lafiya ne zasu sashin kan haiyan yin wanan abun lowani lokacin akwe shin asibiti gwamnatin dakuma asibiti zasu zaman kansu gaskiya basa qarewa saboda gwamnatin nakawosu ne dayawa saboda al'ummar sunsamu sauki saboda yin tazanrar haihuwa kowani lokaci idan suna son yin wanan abun

*Key terms: gaskiya = honestly / truly; saboda = because; asibiti = hospital; lafiya = health*

*Antibiotics and ACT Use - english* - asked: Thank you for that specific example! So you've counseled patients about side effects of certain antibiotics like Septrin (Sulphamethoxazole) causing rashes and body weakness, and Flagyl causing stomach upset. That's very...

> yes i tall them don't want to continue used antibiotics at any time. good appear from him and see him was appreciated yes no I allowed him to finished or completed the antibiotics not stop him once, if there is improvement. yes if there is is not tell them what is the must important of competed the antibiotics drugs best on prescription okay at least from 10 of my community peoples , from 10, 8-9 are completed, 1-2 a...

*Family Planning - english* - asked: Have you heard of Marie Stopes Nigeria (MSI)? If so, does MSI engage with you or your colleagues directly? What do you think of the quality of the services they provide?

> Yes I know about the organization but I have never engaged with them or hear of their service engagement with my colleagues, I don't think their services get here Yes I come across there page on social media and what they do and it's impressive as I see on their handle but no direct experience from them yet

*Water & Diarrhea - hausa* - asked: What water source do people typically use in your catchment area (e.g. open well water, piped water, etc)?

> gaskiya bazan iyaganewaba Amma nasan wasu suna bada maganin chemist kamar antidariya da flagyl kamar Kashi 50 suna amfani da shawara likita kashi 30 kuma sundogarane da chemist sai Kashi ashirin 20 kuma sune basa iya komai sakamakon talauci ko rashin ilimi kawai wanna kiyasi nane

*Key terms: rashin = lack of; gaskiya = honestly / truly; amma = but; maganin = medicine for; likita = doctor; ilimi = education*

*Malaria - english* - asked: Thank you for explaining that you used Rapid Diagnostic Tests (RDTs) to estimate the number of malaria cases. Now, the final part of Question 1: Of these children who got malaria (approximately 76), how many passed away ...

> by using microscope result by orientation mobilization to the community to go health facilities for Malaria case management I'm surely about , because Malaria injection is around Conner for the treatment Best of my experience Malaria a dangerous disease it can kill 234 for the last year I said 76 are confirm positive while 158 are not yes amount of 76, five dead 71 survive

*Vaccines - hausa* - asked: Do people receive cash incentives for vaccines in your community? If so, how does that affect their behavior? What would happen if the incentives were taken away?

> eh suna karba sosai a yankin mu Kashi 90% suna karban rigakafi sannan mu sake karfafa musu cewa wannan kudi da ake basu bawai ana basu bane don suna kawo yaran su rigakafi,ana basu ne saboda rage dogon tafi da uwar zatayi don kawo danta Riga Kafi ,to wannan kudi da ake basu Yana temakawa ne wajen samun saukin abin Hawa don kawo Yara rigakafi sasai ma kuwa Saka makon yanzu yadda iyayen Yara suka Saba da wannan kudi da...

*Key terms: saboda = because; yara = children; kudi = money; samun = getting / access; rigakafi = vaccination*

*Medicine Quality & Counterfeiting 3 - english* - asked: That's helpful — so community members are picking up on both packaging issues and when drugs don't seem to work. Next part: **If people think medicines are fake, what do they do? For example, do they stop using the medic...

> they reported to the pharmacy and sometimes changes pharmacy I was 1 month ago he discarded it it was fake paracetamol he take it 2 times but nothing works after contacting me I looked at it it was fake no Nafdac and I gave him original one

*Malaria 5 - english* - asked: How common is it for people to keep leftover anti-malarials or antibiotics to use later, or to share them with family members?

> Yes, for a child under 5 showing signs of severe malaria, administering pre-referral treatment like rectal artesunate (RAS) is a vital step to stabilize them before they begin the journey to a referral facility. However, maintaining a consistent stock can sometimes be a challenge due to supply chain delays, though we make every effort to keep it available yes we have it at all times

*Malaria 3 - english* - asked: That makes sense — you prioritize the patient's wellbeing by directing them to where they can get care rather than keeping them waiting. Now, let me move to the next part. **Have you heard of rectal artesunate?** If yes,...

> Yes and to me the caregiver should accept and it for children with severe malaria because artesunate is a powerful malaria vain injection that can be used for both children and adults they accept it and use it The caregiver accepted it and use it for my junior brother and to me as adults too Not often because almost all adults knows what Malaria is all about, so prevention is very high and hardly to hear an adult die...

### Answers that explain WHY

*Contains a causal marker (because / saboda / domin). These are the ones that tell you a mechanism, not just a number. Found 13,587 times across 28 topics (7082 english, 6403 hausa, 55 unknown).*

*Water & Diarrhea 3 - english* - asked: How common is it for families in your catchment area to consult a traditional healer or patent medicine vendor before coming to you when a child has diarrhea? If a traditional healer is consulted, what advice is offered ...

> it happens sometimes roughly 30-40% go to a pmv or traditional healer first most of them do this because pmv is closer and cheaper when persisting he would advice them to go to nearest health facility yes and in the process when persist he advice them to go to nearest health facility

*Community & FLW Profile 2 - english* - asked: Are there times of year when you can't do your work (e.g. due to farming season, rains, security concerns)? If so, describe the times of year and the reasons you aren't able to do your work.

> I work in every times in a year We because there is no time person to fall sick

*Internal Topic - english* - asked: What's been the main reason, if any, that's made you stop or take a break from doing these interviews?

> Late payment because up till this month I haven't received any payment aside the transport allowance so far Yes. I haven't receive any payment for the interview

*Malaria 3 - english* - asked: When you identify a child under 5 with danger signs of severe malaria and refer them to a hospital, what proportion of the caregivers actually end up reaching the hospital? For those who don't go, what reasons do caregiv...

> They mostly go to the hospital,those that don't go to the hospital usually go to pharmacies or clinics for treatment i can say 6 goes to the hospital and 4 go to pharmacies or clinics they are majorly because of cost

*Vitamin A Supplementation - hausa* - asked: When Maternal, Neonatal, and Child Health Weeks (MNCHWs) occur, how does this affect your workload? Are you still able to complete your main responsibilities?

> UNISAF, All Babies, Kuma suna dallafawa ta hanyoyi daban daban kaman Bayar da tallafin kudi na transport domin kai Yara Asibiti, bayar da tallafin magani, etc

*Key terms: domin = because; yara = children; kudi = money*

*Community & FLW Profile - hausa* - asked: What is the most common complaint you hear about health care from the people that you serve?

> karancin ma aikata da kuma rashin bada tallafi garesu saboda rashin kudi mutane suns zuwa neman taimako akai akai

*Key terms: rashin = lack of; saboda = because; kudi = money; mutane = people*

*Malaria - hausa* - asked: Nagode da amsar ka mai bayani. Zan ci gaba zuwa tambaya ta gaba. Tambaya ta 2 daga 9: Yaya adadin yaran kasa da shekara biyar da suka rasu sakamakon malaria a yankinka a shekarar da ta gabata ya bambanta da lokacin da ka...

> kimanin shida neh Adadin ragu neh gaskiya saboda Mafi yawanci Lokacin da malaria yake kamasu a ( Raining season) yafi yawa sosai

*Key terms: gaskiya = honestly / truly; saboda = because*

*Water & Diarrhea - hausa* - asked: For every 10 households in your catchment area, how many chlorinate their water? How do they do the chlorination? Is there a chlorine dispenser? Is there a device that adds chlorine? Are there tablets?

> Babu kodaya saboda basusan yadda ake hadawaba ruwa rijiya da bouhol to nidai bansan nawa ake shewaba Amma sunabiya gurin masu saidai ruwa ko kuma msu fampo don sudiba Babu kodaya saboda basuma San miye sanadarin chlorine ba

*Key terms: babu = there is none; saboda = because; amma = but; ruwa = water*

*Bed Net Usage - hausa* - asked: For every 10 households that own bed nets, how many use them for sleeping under?

> to gaskiya kuma wannan sai dai mu kiman ta bisa lura da aladar jima'an saboda akwai masu ilimi da dama zan iya cewa gaskiya fiye da 8 daga cikin 10 na amfani da shiya eh dai gaskiya sai dai naji kawai me da bakin su suna yawan Labarin yadda abin yake masu aiki

*Key terms: gaskiya = honestly / truly; saboda = because; aiki = work; ilimi = education*

*Vaccines - hausa* - asked: How often do you experience vaccine stockouts? Which vaccines are most commonly stocked-out?

> Allura koyanzu in anyi haihuwa munazuwa asibiti anayi kuma alluran dayafi Karanci banida masaniya akanshi saboda ba bangarena bane Amma tabbas suna kokari

*Key terms: saboda = because; amma = but; asibiti = hospital; allura = injection / vaccine*

*Antibiotics and ACT Use 3 - hausa* - asked: Do you think there is a difference in how people in your area use antibiotics compared to how they use malaria treatment drugs? If so, what do you think explains that difference?

> gaskiya bansaniba Eh suna daukar maganin zazzabi fiye da antibiotics saboda su kowane ciwo inba sunga yawuce wuriba matsayin zazzabi suke daukarshi

*Key terms: gaskiya = honestly / truly; saboda = because; maganin = medicine for; zazzabi = fever*

*Antibiotics and ACT Use 2 - english* - asked: Think about households you visited in the past month. Out of every 10 people, how many do you think took Artemisinin-based Combination Therapy (ACT)?

> 8 people out of 10 because more complain is about body hot,so I try to get it

### Problems and shortages reported

*Contains an absence marker (babu / rashin / no / not available). What the FLW says is missing or broken. Found 5,410 times across 26 topics (2906 english, 2465 hausa, 21 unknown).*

*Water & Diarrhea 3 - english* - asked: Out of all the water a typical family in your catchment area drinks in a day, how much of it would you say is purchased such as sachet or pouch water, versus water they collect for free? For the water they do buy, roughl...

> no was dig by government and community pipe wayer adult children use pipe water but boiled one after cool down before use

*Medicine Quality & Counterfeiting - hausa* - asked: Have you ever heard of fake medicines or counterfeit drugs (in other words, medicines that don't work or are not what they claim to be)? Have you experienced this issue with Artemisinin-based Combination Therapies (ACTs)...

> bantajin maganin QARYA ballet ma rudu Babu IRIN wannan matsalar Hakan nake NUFIN ,a cikin al umma ta musamman dai Ina Gani ko dai don sun ga Ina kula da harkar lapia ne,Basa bari insamu wani sirrin Hakan don tunanin Ina Kai bayani

*Key terms: babu = there is none; maganin = medicine for*

*Antibiotics and ACT Use 2 - hausa* - asked: I see, so symptoms like headache, fever, and hot body (high temperature) are what lead people to seek ACT treatment. Now the second part: **Do people in your community take Rapid Diagnostic Tests (RDTs) before they recei...

> yes no there's waiting for Rdt results I mean they can wait for Rdt results before they take the medicine no we can't give ACT until we do RDTs

*Community & FLW Profile - hausa* - asked: What does a normal working day look like for you? Please describe in detail.

> yadda aikin yake kasance kaman jiya nafita nasamu marasa lafiya suna jirana ga baki sunzo suna jirana gashi kuma ranan masu juna biyu suke zuwa awun ciki da safe idan nafita aiki watan nakanje nasamu me aihuwa ko marasa lafiya idan kuma babu ko daya aciki wadanan mukan zauna mu jirasu wani lokaci masu tazara zasuzo da rana Kuma idan lokacin tashi yayi zamu tafi gida

*Key terms: babu = there is none; lafiya = health; gida = house; aiki = work; aikin = work*

*Seasonal Malaria Chemoprevention 2 - hausa* - asked: Do most households in your catchment area receive Seasonal Malaria Chemoprevention (SMC) every year?

> Eey suna yawancin mutane suna karbar maganin Hello Yawancin gidaje suna karbar magungunan SMC a yankin da nake , saidai akwai wasu gidajin da basa karba saboda jahilci da rashin fahimta Akwai wani gida da suka ce bazasu karbaba saboda an raba gidan sauro ba'a basu ba

*Key terms: rashin = lack of; saboda = because; maganin = medicine for; sauro = mosquito; gida = house; gidaje = houses*

*Nutrition Prevalance and Programs - english* - asked: Have you observed cases where the same child under the age of 5 or family returns to nutrition programs multiple times? If so, describe in detail what you thinks contribute to their return to the program.

> English eh suna dawo waane saboda rashin vi gaba da ba wa yaro abnci mai gina jiki bayan an sallamesu daga asibiti ina jira they came back to the hospital due poor nutritonal status after has been discharge they are is lack of food ,lack of knowledge to prefare the food at home and some parent doesnt give their children RUFT they divart it to some ware

*Malaria 4 - english* - asked: When you identify a child under 5 with danger signs of severe malaria and refer them to a hospital, what proportion of the caregivers actually end up reaching the hospital? For those who don't go, what reasons do caregiv...

> reaching out hospital may provide good health care delivery but failure to do may risk more 6 of 10 goes while others don't due to financial ensure no mostly is financial constraints

*Community Demographics - hausa* - asked: How many internally displaced persons (IDPs) do you estimate are in your catchment area?

> ae ada lokacin daga [number removed] zan iya cewa kusan kaso 50% na mutanen yankin sun yi gudun hijira har da ni ciki sabida rikicin rashin zaman lafiya amma yanzu da sauki babu kowa yadawo se yan kadan wanda suka samu mafaka a waje basu dawo ba ko Zasu dawo se ziyara

*Key terms: babu = there is none; rashin = lack of; amma = but; lafiya = health*

*Malaria - english* - asked: How do people in your catchment area find out whether their children under 5 have malaria?

> when the children have fever they normally take them to hospital no they also come for RI

*Malaria 5 - hausa* - asked: Nagode! Fahimce - ba hakan ba zai yiwu ba a yanzu. Yanzu mu ci gaba da ɓangare na gaba na tambayarmu. **Shin kun taɓa karɓar magunguna ko RDTs da suka ƙare (expired), ko kusa da ƙarewa, ko waɗanda aka lalata (misali ta z...

> bamu taba karba ba Muna masa wani gwajin ne kamar na typot 6 saboda wasu suna Shan magani kafin suzoso asibiti Kuma hakan yana boye koyar cutar bamu taba samuba bama bada magani ba gwaji Muna ganinsu ashan farko sannan Muna gayamusu mahimmancin Shan sauran idan sunje gida Muna cewa sudawo bayan kwana uku ai Sai mun tabbatar malaria ne muke Basu magani tunda munyi gwadi eh Muna samu Sai musake masa gwajin typhoid Kuma...

*Key terms: saboda = because; asibiti = hospital; magani = medicine; gida = house; kwana = days*

*Community & FLW Profile - english* - asked: What does a normal working day look like for you? Please describe in detail.

> my first step was I visited the house's worked as chips agents in the morning make sure they have full time with me second step I went to the PHC for proper documentation I stayed until It was time to leave I don't have specific time living in the hospital because I spend the whole day at the PHC

*Water & Diarrhea 4 - english* - asked: Are there certain times or scenarios where families in your catchment area consider diarrhea normal or not serious enough to act on? Out of every 10 caregivers, how many do you think would wait and see rather than seek h...

> bamuda matsala da ruwa saboda Mai su kwaune Au babu wannan koma ga Allah ne gaskiya sai rashe na abinci Mai Gina jiki 2 ne kwai sabuda saura duk basuda kudi wani lokaci anasamu idan ankawo magani kyauta 5 babu Munayin koh yanzu dai muje zuwa tambaya na 8

### Numbers with reasoning attached

*A figure AND an explanation in the same answer - an estimate you can interrogate rather than a bare digit. Found 5,379 times across 28 topics (3197 english, 2126 hausa, 32 unknown).*

*Vitamin A Supplementation - english* - asked: When parents visit the clinic or Maternal, Neonatal, and Child Health Weeks (MNCHWs), what is usually the main reason (e.g. immunization, weighing, Vitamin A Supplementation (VAS), or something else)?

> 75 75 total across the service Based on personal observation because in my Area they goes to generally hospital

*Antibiotics and ACT Use 3 - english* - asked: In your experience, are there times when people treat themselves or a family member for an infection at home without visiting a health facility? What do they typically use, and what usually prompts them to do that?

> yeah there are people that do like 1-2 out of 15 people do mostly because of no money to buy antibiotics for treatment because our community are very poor people here they often try traditional medicine, herbal like some powder, watery etc yeah sometimes poverty drives u to everything in this life but after all lifes matter than everything when traditional doesn't work they go to health facility and even by borrowing...

*Malaria 2 - hausa* - asked: In your community, how common is it for pregnant women to attend antenatal care coverage (ANC) during their first trimester of pregnancy? For women who don't come in during that early period, what are the main reasons yo...

> ey muna samun Mata masu juna biyu suna zuwa awo ayankinmu acikin watanin uku nafarko sosai akalla Nuna samun kashi 9 cikin 10 mafi yawancin Wayanda basa zuwa Kai raayinsune wasukuma saboda wai abasu tunanin wai sunyi daurin zuwa awo dawuri bamutaba Jin wani da liliba abakainsu kawaidai basa zuwa

*Key terms: saboda = because; samun = getting / access*

*Vitamin A Supplementation - english* - asked: What changes would make your work distributing Vitamin A Supplementation (VAS) easier or more efficient?

> The payment increase will contribute a lot The distribution during MNCHW is a bit high because some mothers that not even knows they due will come for other services and their child records reveal it Apart from increase payment adding number of staffs to support the exercise Per facility only 2 staffs are selected e participated in the exercise so adding extra staffs will help

*Antibiotics and ACT Use 2 - hausa* - asked: Think about households you visited in the past month. Out of every 10 people, how many do you think took Artemisinin-based Combination Therapy (ACT)?

> ba,afara rabawaba ko 4 daga 10 saboda watan da yagabata malaria batayi yawaba kamar yanxu

*Key terms: saboda = because*

*Community & FLW Profile - english* - asked: How many days a week do you usually work?

> yeah my workload is difficult because in our facility we've shortage of manpower. we the parmanent staff are small so there's no task shifting and task sharing. yeah there's a day in our working days that we used to share RUTF to the large number of clients so when we're doing that work many of the people whom we used to do the work together are volunteers and the work is not easy so as we're working we can be up to ...

*Bed Net Usage - english* - asked: For every 10 households that use bednets, do they use them all year or only certain times of year? If only certain times of year, when is it used?

> 60% is during the raining season, 40% is yearly yes, the reason here is mostly they only believe that it is only during the raining season that they have mosquitoes around them, because they practice the measures to prevent themselves from being at stagnant area and bushes

*Malaria - hausa* - asked: What are the reasons that households are missed by Community Drug Distributors (CDDs) when distributing Seasonal Malaria Chemoprevention (SMC)? For every 100 households, how many do you think are missed?

> saboda wasu mutanen basu son ana ba yaran su maganin riga kafi 20%

*Key terms: saboda = because; maganin = medicine for*

*Malaria 3 - english* - asked: When you identify a child under 5 with danger signs of severe malaria and refer them to a hospital, what proportion of the caregivers actually end up reaching the hospital? For those who don't go, what reasons do caregiv...

> can you please expatiate the question Not all the 10 children went to the hospital for treatment because of the hospital bill. 8 out 10 children went to the hospital and there's no other besides the hospital bill

*Malaria 4 - hausa* - asked: Think about the malaria-related work you did last month - things like checking on sick children, distributing medication, or following up on cases. How much time did you spend conducting visits? How much time did you spe...

> a cikin sati muna Kai ziyara ga maras lafiya sau ukku muna shafe awa guda muna tafiya don Kai ziyarar sannan zamu iya daukar awa 6 domin duba su

*Key terms: domin = because; lafiya = health*

*Seasonal Malaria Chemoprevention 2 - hausa* - asked: Do distributors ever give SMC to children over 5 years old because they make a mistake, because the caregiver gives the wrong age, or for another reason? Out of every 10 children 6 to 10 years old in your community, how ...

> a'a a bisa namu horo da muka musu yara sama da shekaru biyar baswa karba, kuma idan iyaye suka ce yaran basu kai ba suna amfani da qiyasi, idan har alamu ya nuna yaron ya wuce shekaru biyar basu bashi, wasu lokutan ma har takardan shaida suna nema don kiyaye bawa yara da suka wuce shekarun karban maganin gaskiya da kamar wahala a samu, amma bari nace 1 na bada 1 saboda ba lallai ne a iya dakatar da iyaye wajen boye s...

*Key terms: gaskiya = honestly / truly; saboda = because; amma = but; maganin = medicine for; yara = children; iyaye = parents*

*Bed Net Usage - english* - asked: Thank you for sharing your experience as a recorder during the campaign and mentioning that your team performed well. Next part of the question: How did the most recent mass bed net campaign go? What percentage of total ...

> just on last month they distribute and almost 100 received is control and date, because card are giving with different date But as camping start people coming with date that not supposed to address them it difficult

### Candid and hedged answers (mostly Hausa)

*Marked with gaskiya / honestly. NOT comparable across languages: gaskiya is an everyday Hausa discourse particle appearing in about 4% of Hausa messages, while English honestly is rarer, so this category is overwhelmingly Hausa by construction rather than because Hausa speakers are more candid. Found 5,693 times across 27 topics (5411 hausa, 236 english, 23 mixed).*

*Malaria 4 - hausa* - asked: Think about the malaria-related work you did last month - things like checking on sick children, distributing medication, or following up on cases. How much time did you spend conducting visits? How much time did you spe...

> gaskiya ban iya misalita lokacin saboda munayi iya gwar gwado asati muna iya sau uku ko fiye da haka a a

*Key terms: gaskiya = honestly / truly; saboda = because*

*Bed Net Usage - hausa* - asked: What are the most common complaints you hear about the bed nets people have received?

> gaskiya banajin wani koke koke a yanki na domin kowa yanama kowa anfani kuma duk sunjidadin anfani da garkuwar kwari

*Key terms: gaskiya = honestly / truly; domin = because*

*Vitamin A Supplementation - hausa* - asked: Na gode da zaɓin Hausa. Zan fara da tambaya ta farko. Wannan tambayar tana da sassa da dama, don haka zan raba su ɗaya bayan ɗaya. Sashe na farko: Shin kuna rubuta adadin kwayoyin Vitamin A da kuka bayar a yankin aikinku...

> na shirya eh Muna rubutawa ta hanyar ta kadda eh akwai from din Muna bawa, forcul person na mu ne sai ya Kai health office namu sukuma sai subawa m and e namu saiyasa a saver eh to gaskiya daganan bansan ya akeyi da shi ba gaskiya Muna mu in anbamu mura ba shi ne

*Key terms: gaskiya = honestly / truly*

*Malaria - hausa* - asked: When a child under 5 in your catchment area gets malaria, where do they typically go for treatment (e.g: health facility, pharmacy, traditional healer, Patent and Proprietary Medicine Vendors (PPMVs))? What treatment do ...

> gaskiya wani time ba'a gwaji muke bada magani kuma ana samun sauki duk yaranda za'akai chemist 70% insu ba'a gwaji gaskiya

*Key terms: gaskiya = honestly / truly; magani = medicine; samun = getting / access*

*Community & FLW Profile - hausa* - asked: Are there times of year when you can't do your work (e.g. due to farming season, rains, security concerns)? If so, describe the times of year and the reasons you aren't able to do your work.

> gaskiya ko yaushe muna zuwa aiki idan an samu matsalar tsaro ne gaskiya kowa yana tsoron fita

*Key terms: gaskiya = honestly / truly; tsaro = security; aiki = work*

*Vaccines - hausa* - asked: Do people receive cash incentives for vaccines in your community? If so, how does that affect their behavior? What would happen if the incentives were taken away?

> gaskiya ban saniba bamuta jimkomaiba saidai wasu iyayen basa bada yaransu ana basu Indomi dakuma abuntabahwa hakadai chamdama ba'a.basuwa dabara yanxunedabayannan...suke adawa amma

*Key terms: gaskiya = honestly / truly; amma = but*

*Vaccines - hausa* - asked: What are the primary reasons children under 5 don't receive vaccines?

> Wasu iyayene ke sawa karsu karba Saboda karanci ilimi ga iyayen yaran Gaskiya babu shine iyaka

*Key terms: babu = there is none; gaskiya = honestly / truly; saboda = because; ilimi = education*

*Medicine Quality & Counterfeiting 3 - hausa* - asked: Have you ever personally seen a medicine that you thought might be fake or of poor quality?

> ta kamfani da nafdak number gaskiya inadibawa amma bantaba haduwa dawnda bashida kyuba

*Key terms: gaskiya = honestly / truly; amma = but*

### Concrete examples given

*Contains an example marker (misali / for example) - a specific case rather than a generality. Found 1,682 times across 27 topics (892 hausa, 785 english, 4 unknown).*

*Malaria - english* - asked: Thank you for providing a clear comparison and sharing specific examples from your experience. Question 3 of 9: How do people in your catchment area find out whether their children under 5 have malaria?

> firstly they usually observe the sign and symptoms e.g fever, headache, nausea and vomiting etc secondly they will go to the nearest hospital for blood test e.g rapid diagnostic test (RDTs) or microscopic test thirdly they get prompt treated

*Antibiotics and ACT Use - hausa* - asked: Describe the health conditions for which antibiotics are most commonly used in your catchment area? Do people get these antibiotics from health facilities or community pharmacies?

> saboda su tabbabata sun kula da lafiyar su kaman yadda yadaci shiyasa suke karba maganin antibiotics kuma shanshi yada yadaci misali Muna da yawan cicituka kaman cizun sauro daku makogwaro da kuma gudanawa misali kaman ciwon mangwaro suna zuwa karba maganin da kuma ZAZZABIN CIZON SAURO shima suna zuwa karba maganin da kuma gudanawa shima suna zuwa karba maganin rigakafin

*Key terms: saboda = because; misali = for example; maganin = medicine for; sauro = mosquito*

*Internal Topic - hausa* - asked: When you're doing interviews, how do you keep track of how many you can still do that day?

> yawan hira yayi daidai,kuma tsari na bangare bangare mun amfanidashi,misali kamar tsarin bed net starin bed net na rabiya da kulawa da bed net dasauransu

*Family Planning - english* - asked: Have you heard of Marie Stopes Nigeria (MSI)? If so, does MSI engage with you or your colleagues directly? What do you think of the quality of the services they provide?

> no people do not get pressured to use implants no organization or provider is pressuring women to use implants for example it's by choice some are advised by their husbands

*Health Worker Experience - english* - asked: Have you ever had a sick child in front of you and not had what you needed to help them? What do you do? How often does that happen?

> Yes access quickly: check danger signs first such as can the breathing first, drink, fever, convulsions and vomiting everything use what at home first such check if there is ORS, check sugar salt solution and send the caregiver to the nearest PHC comfort and explain, like letting the caregiver know you see how serious it is,that you are not ignoring it , and what the next step is . that matters a lot to families stoc...

*Nutrition Prevalance and Programs - english* - asked: How do people in the catchment area identify children with severe malnutrition (SAM)?

> In my community, caregivers usually identify severe malnutrition by visible signs like thinness, visible ribs, weakness, and swelling of the feet, loss of appetite and frequent illness. For example, I have seen a mother become concerned when her child became very thin and weak, which led her to seek help.

*Antibiotics and ACT Use 2 - hausa* - asked: Na gode! Hakan ya bayyana — Ciprofloxacin, Flagyl, Amoxicillin, da Ampiclox su ne antibiotics da ake samunsu da sauƙi. Yanzu game da ɓangare na biyu: **A ra'ayinka, shin mutane suna amfani da waɗannan maganin rigakafi (a...

> gsky aa anawa raayi basa amfani dasu yadda ya kamata na lura idan basuda lafiya suka siyo antibiotic basa shanshi yadda ya kamata misali ciproflacine idan ankace susha 500mg bd x1/52 suna iya shanshi 500mg tds x1/52

*Key terms: misali = for example; lafiya = health*

*Water & Diarrhea 3 - hausa* - asked: How common is it for families in your catchment area to consult a traditional healer or patent medicine vendor before coming to you when a child has diarrhea? If a traditional healer is consulted, what advice is offered ...

> idan matsala tasamesu sukan iya zuwa 3 yana basu magani kuma yana basu shawara yana basu maganin matsalar da suka jemusu maganin gargajiya yabasu aa babu wani misali

*Key terms: babu = there is none; misali = for example; magani = medicine; maganin = medicine for*

### Answers the probe rescued

*Started unusable, ended usable. The clearest evidence of what the conversational format buys. Found 20,861 times across 28 topics (13433 english, 7249 hausa, 141 unknown).*

*Medicine Quality and Counterfeiting 2 - english*

First answer: "no"

Interviewer: "Thank you for your response. Just to make sure I understand correctly — are you saying you have **never heard of** fake medicines or counterfeit drugs at all, or that you have heard of them but just haven't personally ex..."

> Then: no yes I haven't heard of it before

*Vaccines - english*

First answer: "yes"

Interviewer: "Thank you! Could you tell me a little more about that training? For example, what kind of training was it, and where did you receive it?"

> Then: yes is a polio vaccine training last year it was organized by UNICEF

*Malaria - english*

First answer: "95%"

Interviewer: "Thank you for your response. To understand better, could you explain how you arrived at the estimate that 95% of children who got SMC were over 5 years of age? Was this based on your records, observations during distribu..."

> Then: 95% sorry that was an error!. i can't actually give a percentage to that. but it's possible children over 5 years are given smc.because some of the parents don't remember data of birth

*Medicine Quality and Counterfeiting 2 - english*

First answer: "from pharmaceuticals company"

Interviewer: "Interesting. Could you say a bit more about that — do you mean local pharmaceutical companies, or imported products from outside the country? And what makes you think that's where they originate?"

> Then: from pharmaceuticals company local pharmaceuticals, because most of the fake drugs are country made

*Malaria 2 - english*

First answer: "yes"

Interviewer: "Thank you for confirming. Could you tell me more about what you've actually observed in your catchment area? For example: - Which types of households seem to be more affected? - What do you think makes them different fro..."

> Then: yes the type of household seem to be affect is located at anguwa ,and they located near the bush ,they only use to lead some dirty water in their pot and some discarded waste it is mainly environment,like bush and stagnat water near by

*Antibiotics and ACT Use 3 - english*

First answer: "malari"

Interviewer: "Thank you for that. Just to make sure I understand — you mentioned malaria as a common condition. Are antibiotics being used to treat malaria in your area, or is that more of a general illness people are experiencing? An..."

> Then: malari yes from pharmacies

*Health Worker Experience - english*

First answer: "Hello"

Interviewer: "Hello! We were just in the middle of the interview. Let me continue from where we left off. **Are the health challenges in your community worse than a year ago, about the same, or better?**"

> Then: Hello Is becoming less

*Medicine Quality & Counterfeiting 3 - english*

First answer: "4 people"

Interviewer: "Thank you. Could you walk me through how you arrived at that number — **what makes you think about 4 out of 10 sellers might be selling fake medicines? Is this based on something you've seen or heard in your area?**"

> Then: 4 people I have seen it no nafdac number and expiring date

*Medicine Quality & Counterfeiting - english*

First answer: "Yes,"

Interviewer: ""

> Then: Yes, Hello Really I don't know

*Nutrition Prevalance and Programs - english*

First answer: "No at all"

Interviewer: "Thank you for that response. Just to make sure I understand — in your catchment area, you have not observed any cases where the same child or family has returned to a nutrition program more than once?"

> Then: No at all yes

*Vitamin A Supplementation - english*

First answer: "explain more"

Interviewer: "Sure! This question is asking about **who oversees or monitors the work you do related to VAS distribution during MNCHWs**. For example: - Is there a supervisor, LGA officer, or any other person who comes to check how VA..."

> Then: explain more is the LGA officer

*Antibiotics and ACT Use - english*

First answer: "Act,cough syrup"

Interviewer: "Thank you for your response. Just to clarify, ACT is used for malaria, and cough syrup is for coughs. My question is specifically about antibiotics: For which health conditions do people in your area most commonly use an..."

> Then: Act,cough syrup cold especially in rainy season Health facility

### Recovered from not understanding

*FLW said they did not understand, then produced a usable answer after the bot rephrased. Found 206 times across 17 topics (127 english, 79 hausa).*

*Malaria 5 - hausa*

First answer: "ban gane tanbayarba"

Interviewer: "Yi hakuri! Bari in bayyana da sauƙi: Wani lokaci mutum yana da zazzaɓi, sai a gwada shi da kayan gwajin malaria (RDT), amma sakamakon ya nuna **NEGATIVE** — ma'ana gwajin ya ce **ba malaria ba**. Tambayata ita ce: **A wannan yanayi, menene ..."

> Then: gaskiya yadanganta da yanayinda mukaganshi nan kuma inmukaga haka muna amfani da alamumin da muka gani sai mubashi magani 3 mun ga alamun fever da vomit da duk wasu alamu nanuna malaria

*Key terms: gaskiya = honestly / truly; magani = medicine*

*Community Demographics - english*

First answer: "don't understand this question"

Interviewer: "Thank you for letting me know. Let me explain: Internally Displaced Persons (IDPs) are people who have been forced to leave their homes due to conflict, violence, or disasters, but who remain within their own country. In your catchment area..."

> Then: ihave them in my area but their not many their about 40 people livin in one primary school

*Malaria 2 - english*

First answer: "I don't understand the question very much"

Interviewer: "No problem, let me rephrase it! Since ITNs (bednets) are not given out at your facility, do you know of **any other way** pregnant women in your area can get a bednet — for example, through campaigns, markets, or other health programs? And ..."

> Then: some buy while some received during campaigns

*Nutrition Prevalance and Programs - english*

First answer: "I don't understand"

Interviewer: "No problem! Let me rephrase: When families in your catchment area need to bring their child to the CMAM/nutrition program — **is it easy or difficult for them to get there and participate?** And what things make it hard for some families to..."

> Then: it's for those that is near bye that get fear before coming to the center no

*Water & Diarrhea 2 - english*

First answer: "what do you mean by pouch water??"

Interviewer: "Sorry for the confusion! By "pouch water" I mean water that is sold in small sealed plastic bags or sachets — sometimes called "pure water" in some parts of Nigeria. It's water that is commercially packaged and sold for drinking. So, **do f..."

> Then: not really, due to how clean out water is, people mostly drink water they fetch from the tap or nearby borehall.

*Family Planning - hausa*

First answer: "ban Gane Wana Tanbaya Ba!"

Interviewer: "Yi hakuri! Bari in bayyana da sauki. Kun ce kuna jin daɗin implants, amma kun faɗi "mudda mun yarda da shi." Ina son fahimtar wannan sosai. **Wanene ya kamata ya yarda ko ya ba da izini kafin a saka implant? Misali, matar kanta, mijinta, ko..."

> Then: Mijin Matane ke bada dama kan Mace ta saka implant

*Community & FLW Profile 2 - hausa*

First answer: "ban gane ba"

Interviewer: ""

> Then: ban fahimci tambayar ba eh sukan ce gwamnati bata basu komai sai magani su sunfi bukatar abinci Eh duk lokacin da ake wani campaign na allura ne ko kuma na magani ne zakaji suna cewa an damesu da magunguna ai yunwa ce ke kawo ciwo

*Key terms: magani = medicine; abinci = food; allura = injection / vaccine*

*Health Worker Experience - hausa*

First answer: "ban gane tambayar ba"

Interviewer: "Yi haƙuri! Bari in sake faɗi da sauƙi: Idan kuna da ikon canza abubuwa a aikinku don ya zama mafi sauƙi ko mafi inganci — mene ne abubuwa 2 ko 3 da kuke son a canza?"

> Then: na farko dai za'a dinga bamu kuddin hawa machine,na biyu kuma dinga fahimtarda uwayen yara

*Key terms: yara = children*

### Explicit 'I do not know'

*Where knowledge genuinely stops - useful in itself, and distinct from a refusal. Found 1,650 times across 25 topics (1349 english, 287 hausa, 10 unknown).*

*Malaria 5 - english* - asked: To the best of your knowledge, which NGOs and Institutions were involved in supporting this campaign?

> I don't know but I think is malaria consortium artersunate suspension general hospital toro

*Water & Diarrhea 2 - hausa* - asked: Are there particular times of year such as after rains or during harvest season, when you see a spike in diarrhea cases among children under 5?

> ruwan magani gaskiya bansani ba gaskiya yanzu mutane sun waye ba a fiye damuwa da gargajiya ba baya faruwa

*Key terms: gaskiya = honestly / truly; magani = medicine; mutane = people*

*Vitamin A Supplementation - english* - asked: Who supervises or checks your Vitamin A Supplementation (VAS) work during the Maternal, Neonatal, and Child Health Week (MNCHW)?

> I don't really know someone used to come but I don't know his title our supervisor records and work

*Antibiotics and ACT Use - english* - asked: That's okay! Let's move to the next part. **What antibiotics are most commonly available to buy in your community?** From your experience, which specific antibiotics have you seen people purchasing or using?

> don't know it's not

*Community & FLW Profile 2 - english* - asked: What is the most common way that households get fertilizer in your catchment area? Around how much does it cost to buy one kilogram of fertilizer locally?

> I don't know

*Medicine Quality & Counterfeiting - english* - asked: When you recommend a medicine to someone, how confident are you that they are getting the real medication?

> no idea

*Health Worker Experience - english* - asked: What medicines most often run out of stock in your local health facility?

> honestly I don't know I do visit

*Malaria 4 - english* - asked: Do caregivers in your community know the difference between malaria and other causes of fever in a young child — for example, pneumonia or a common cold? How do you explain the difference to them?

> I don't know in a general sense, they have to be tested before

### Low-quality or junk answers

*Gibberish, single characters or repeats. Counted honestly so the corpus is not oversold. Found 6,059 times across 28 topics (4334 english, 1679 hausa, 35 unknown).*

*Medicine Quality and Counterfeiting 2 - english* - asked: Those are very practical identification methods — overlapping labels, missing NAFDAC numbers, and absent batch/manufacturing/expiry dates. Great observations! Next part: **Have you ever personally seen a medicine that yo...

> yes

*Malaria 3 - hausa* - asked: Have you heard of rectal artesunate? If yes, what is your sense of whether caregivers in your catchment area would be willing to accept and use it for a child with suspected severe malaria?

> bansaniba

*Vitamin A Supplementation - english* - asked: Outside the Maternal, Neonatal, and Child Health Week (MNCHW), how often can parents obtain Vitamin A Supplementation (VAS) in your catchment area? What are the other ways to get VAS?

> no

*Community & FLW Profile 2 - hausa* - asked: When nets or SMC campaigns occur, how does this affect your workload? Are you still able to complete your main responsibilities?

> english

*Community & FLW Profile 2 - english* - asked: Thank you! So farmers can access the subsidized fertilizers and equipment at the local government secretariat, and it is open to all farmers in the community. That's very clear! Now, the final part: **Are there any NGO p...

> No

*Water & Diarrhea 3 - hausa* - asked: Out of all the water a typical family in your catchment area drinks in a day, how much of it would you say is purchased such as sachet or pouch water, versus water they collect for free? For the water they do buy, roughl...

> 20%

### Platform errors mid-interview

*The bot failed to process a message. Rare, but it interrupts a real conversation. Found 80 times across 14 topics (52 english, 28 hausa).*

*Medicine Quality and Counterfeiting 2 - english*

> That's a very telling pattern — patients returning with the same symptoms is often the first sign that something went wrong with the medicine they received. **When they come back with those complaints...

*Vitamin A Supplementation - english*

> I'm sorry, something went wrong while processing your message. Please try again later.

*Internal Topic - english*

> I'm sorry, something went wrong while processing your message. Please try again later.

## What this adds up to

- **There is real content here, at scale.** 113,093 answers from 1,461 workers, 16,018 of which explain a reason rather than just stating a fact.
- **The follow-up earns its place.** 20,861 answers were unusable at first attempt and usable by the end. On a form, the first attempt is what would have been filed.
- **Workers are candid.** 5,693 answers carry an explicit candour marker, and 1,650 say plainly that they do not know - which is a more trustworthy corpus than one where every question gets a confident answer.
- **It is not uniformly clean.** 6,059 answers are junk, gibberish or a single character - about 5.4% of the total. That is a normal rate for open text at this scale, and it is stated here so nobody discovers it later.
- **Length varies enormously by topic**, so comparing raw answer depth across subjects will mislead unless the topic is held constant.
- **Interviews are not single sittings** for a large minority, which matters for any timing or effort measure.

## How this was produced

Every session was pulled from OpenChatStudio and stored locally, then read start to finish. Within each session the interviewer's turns were classified as either opening a new question or following up on the one already open, and the FLW's turns were attached to whichever question was open. That gives, for each question, the answer before any follow-up and the answer it ended with.

Detection rules were built from the corpus's own vocabulary rather than assumed. The Hausa markers were chosen after counting actual usage - for instance 'rashin' is used to mean a shortage roughly nine times out of ten, but 'rashin lafiya' simply means illness, so that phrase is excluded. Getting that wrong in either direction would have distorted the barrier counts.

Extracts are selected deterministically: a fixed random seed, stratified by topic so that one large cohort cannot dominate the examples. Re-running the analysis reproduces the same selection.

### Checks that were run

- Every session in the archive is accounted for - 9,952 analysed plus 11,964 excluded for a stated reason equals 21,916.
- Every quote was verified to appear word for word in the session it is attributed to. An answer is the worker's own turns for one question joined in order, so it is verbatim without necessarily being one uninterrupted message.
- No worker identifier appears anywhere in this document or the spreadsheet; session references are truncated and phone-shaped numbers were removed.
- The extracts were checked for spread, so no category is drawn from only one topic or one language.

### Limitations, stated plainly

- **These are self-reports.** An FLW saying something is missing is evidence about their experience and their perception, not an audited measurement of stock or coverage.
- **The questions shape the answers.** The shortages named most often are partly a function of what was asked. This is not a prevalence survey.
- **Keyword detection is approximate.** It finds the marker, not the meaning. A category count is a reliable order of magnitude and a good way to find examples, not a precise measurement.
- **Quality was not judged.** Nothing here scores whether an answer is accurate, relevant or deep. Length and markers are proxies for effort, not for truth. Scoring quality properly needs a separate pass with a judge model, validated against human raters.
- **Hausa detection is thinner than English.** The marker set is grounded in observed usage, but it is smaller. Where a category matters, check the Hausa share in the table above before drawing conclusions about differences between languages.

### Using the extract dump

The spreadsheet alongside this document carries every selected extract, one row each, with columns for the category, the topic, the language, the question as asked, the answer, and - where the follow-up mattered - the first attempt and the interviewer's reply. It is meant to be filtered and read, and it is a reasonable starting point for any deeper analysis on this project, including work with a language model, since it carries the context alongside each quote.
