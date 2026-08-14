"""Classify every AI turn in an interview as ASK / RE-ASK / PROBE / ADMIN, and rebuild sub-part windows.

This is the measurement instrument the whole probing analysis rests on, so every rule in it was
derived from the corpus rather than guessed, and every classification records WHICH channel fired
(`channel`) so precision can be audited per channel instead of as one opaque number.

WHY NOT the obvious approaches:

  * Bold text. The current bot wraps the catalogue question in `**...**`, which looks like a perfect
    signal — but it is a RECENT convention. Measured across the 2026-05-25 export: v32-v39 (~100k AI
    messages) use bold in only 2-4% of messages, versus 68% at v55. Bold alone would silently work on
    new sessions and fail on the bulk of the study.
  * Catalogue word-overlap alone. Works for English (asks land at 0.6-1.0 overlap) but COLLAPSES for
    Hausa sessions, where the bot translates the question and overlap against the English catalogue is
    noise (measured 0.03-0.47 on a Hausa session whose asks were unambiguous to a reader).
  * A single "probe" regex (what `interviews_step1.r` does). Its pattern list mixes "could you
    explain" (a real quality probe) with "for the second part" (the bot simply advancing through
    sub-parts). Those are different events; see below.

THE DISTINCTION THAT MATTERS. Most topics hand the bot ONE question containing 3-19 sub-questions
concatenated with no separator (see build_question_catalogue.py), so the bot must walk the FLW
through them. Therefore:

  ASK    - opens a sub-part that has not been opened yet. The interview proceeding. NOT a probe.
  RE-ASK - restates/rephrases the sub-part already open (bot judged the answer unusable).
  PROBE  - any other bot turn on an already-open sub-part: the quality follow-up.
  ADMIN  - welcome, language choice, closing, "are you there" — outside the question flow.

Only RE-ASK and PROBE are probing. Counting advances as probes is what would inflate the apparent
quality problem and understate the measured lift.

DETECTION CHANNELS, in priority order:
  1. `declared`  - the bot states its position explicitly. Hausa is the richest here:
                   "**tambaya ta 1 (sashi na 3):**" = "Question 1 (part 3)". English: "Question 1",
                   "the final part of the question". A declared index that INCREASES is an advance;
                   one that repeats is a re-ask.
  2. `advance`   - transition phrase without an index: EN "moving to the next part", "now the next
                   part:"; HA "sashi na gaba", "tambaya ta gaba", "mu ci gaba".
  3. `overlap`   - word overlap with a not-yet-opened catalogue sub-part (English fallback).
  4. `admin`     - welcome / language / closing patterns.
Anything unclaimed on an open sub-part is a PROBE.
"""
import re
import unicodedata

# ---------------------------------------------------------------- tokenising / overlap
_WORD = re.compile(r"[a-z0-9]+")
BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)


def _fold(s):
    """Lowercase and strip Hausa hooked letters to ASCII so 'ɓangare'/'bangare' and 'huɗu'/'hudu' match."""
    s = (s or "").lower().replace("ɓ", "b").replace("ɗ", "d").replace("ƙ", "k").replace("ʼ", "'")
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def toks(t):
    return set(_WORD.findall(_fold(t)))


def overlap(msg, question):
    """Share of the QUESTION's words present in the message. Asymmetric on purpose: the bot adds
    acknowledgement text around the question, which should not dilute the score."""
    tq = toks(question)
    return len(toks(msg) & tq) / max(len(tq), 1)


def overlap_toks(msg_toks, q_toks):
    """overlap() on pre-tokenised sets. Hot path: a 19-sub-part topic in a 70-message session is
    ~1,300 comparisons, so re-running the tokeniser each time dominated runtime."""
    return len(msg_toks & q_toks) / max(len(q_toks), 1)


# ---------------------------------------------------------------- ordinals
EN_ORD = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
}
_HA_UNIT = {
    "daya": 1,
    "biyu": 2,
    "uku": 3,
    "hudu": 4,
    "biyar": 5,
    "shida": 6,
    "bakwai": 7,
    "takwas": 8,
    "tara": 9,
    "goma": 10,
}
# Hausa builds teens as "goma sha <unit>" (ten-and-x): "goma sha biyar" = 15. A single-word capture
# read that as "goma" = 10, so declared part 15 collided with part 10 and the ask was scored a probe.
HA_ORD = {
    "farko": 1,
    **_HA_UNIT,
    **{f"goma sha {w}": 10 + v for w, v in _HA_UNIT.items() if v <= 9},
    **{f"sha {w}": 10 + v for w, v in _HA_UNIT.items() if v <= 9},
}
NEXT_WORDS = {"next", "gaba"}
LAST_WORDS = {"final", "last", "karshe"}

# ---------------------------------------------------------------- declared position (channel 1)
# Hausa carries an explicit part index: "**tambaya ta 1 (sashi na 3):**"
# capture up to three words so "goma sha biyar" (15) survives, not just "goma" (10)
HA_PART = re.compile(r"(?:sashi|sashe|bangare|kashi)\s*na\s*((?:goma\s+sha\s+\w+|sha\s+\w+|[\w]+))")
HA_QNUM = re.compile(r"tambaya(?:r)?\s*(?:ta\s*)?(\d+)")
# English: "Question 1 of 2", "the third part", "part 2"
EN_QNUM = re.compile(r"question\s*(\d+)(?:\s*of\s*\d+)?")
EN_PART = re.compile(r"(?:^|\W)(?:the\s+)?([a-z]+|\d+)\s+part(?:\W|$)|part\s*(\d+)")

# ---------------------------------------------------------------- advance phrases (channel 2)
ADVANCE = re.compile(
    r"moving\s+(?:on\s+)?to\s+the\s+next|now\s+(?:the\s+)?next\s+part|next\s+part\s*[:\-]"
    r"|moving\s+on\s*[:.\-]|let'?s\s+move\s+(?:on\s+)?to|let'?s\s+(?:now\s+)?(?:go|turn)\s+to"
    r"|now\s+for\s+the\s+next|let'?s\s+start\s+with\s+the\s+first|final\s+part\s+of\s+the\s+question"
    r"|now\s+let'?s\s+move|let'?s\s+continue\s+(?:to|with)"
    # Hausa: "next part", "next question", "let us continue / go / look at"
    r"|sashi\s*na\s*gaba|bangare\s*na\s*gaba|tambaya(?:r)?\s*ta\s*gaba"
    # "ci gaba" = continue. Was written as "mu ci gaba" (we continue) and so missed the bot's much
    # commoner "ZAN ci gaba" (I will continue) — 3 of 7 missed asks in the hand-validation sample.
    r"|ci\s+gaba|mu\s+tafi|mu\s+duba|yanzu\s+zuwa",
    re.I,
)

# The bot announces the multi-part structure when it opens a mega-question. Useful as an ask marker.
MULTIPART = re.compile(
    r"this\s+question\s+has\s+multiple\s+parts|take\s+them\s+one\s+at\s+a\s+time"
    r"|go\s+through\s+them\s+one\s+at\s+a\s+time|tana\s+da\s+sassa\s+da\s+yawa",
    re.I,
)

# ---------------------------------------------------------------- admin (channel 4)
ADMIN = re.compile(
    r"i\s+am\s+an\s+ai\s+interviewer|conduct\s+a\s+qualitative\s+interview"
    r"|before\s+we\s+(?:begin|start|dive)|english\s+or\s+hausa|hausa\s+or\s+english"
    r"|this\s+concludes\s+our\s+interview|you\s+can\s+exit\s+the\s+interview"
    r"|do\s+not\s+respond\s+further|thank\s+you\s+for\s+participating"
    r"|thank\s+you\s+for\s+joining|we'?ll\s+(?:proceed|continue|conduct)\s+in\s+(?:english|hausa)"
    r"|interview\s+is\s+now\s+complete|may\s+exit\s+the\s+chat|no\s+more\s+questions"
    r"|ni\s+ne\s+mai\s+(?:hira|gudanar|tambayoyi)|ina\s+nan\s+don|turanci\s+ko\s+hausa"
    r"|hausa\s+ko\s+turanci|wannan\s+ya\s+kammala|za\s+ku\s+iya\s+fita|na\s+gode\s+da\s+shiga"
    # OCS platform error replies. Only 80 of 260,649 bot turns (0.03%), so immaterial to the totals,
    # but they are not probes and were being counted as such — found by hand-reading the validation
    # sample, where they are over-represented because an error reply carries no prompt-version tag.
    r"|something\s+went\s+wrong|please\s+try\s+again\s+later|experiencing\s+some\s+technical",
    re.I,
)

# "are you there" style connective — bot answering a meta-question, not probing content
META = re.compile(r"^(?:yes,?\s*i'?m\s+here|i'?m\s+here|sorry\s+for\s+(?:any\s+)?delay)", re.I)

# ---------------------------------------------------------------- FLW-side trigger patterns
DONT_KNOW = re.compile(
    r"^\s*(?:i\s+)?(?:don'?t|do\s+not|dont)\s+know|^\s*no\s+idea|^\s*not\s+sure|^\s*can'?t\s+say"
    r"|^\s*ban\s+sani|^\s*bansani|^\s*ban\s+san|^\s*sanni\s+ba",
    re.I,
)
CONFUSED = re.compile(
    r"don'?t\s+understand|do\s+not\s+understand|didn'?t\s+understand|what\s+do\s+you\s+mean"
    r"|repeat\s+the\s+question|come\s+again|ban\s+gane|ba\s+na\s+gane",
    re.I,
)
NUMERIC_ASK = re.compile(
    r"how\s+many|how\s+much|what\s+percentage|out\s+of\s+every|roughly\s+how|approximately\s+how"
    r"|what\s+proportion|how\s+often|estimate",
    re.I,
)
HAS_DIGIT = re.compile(r"\d")
NUM_WORD = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|sixty|seventy"
    r"|eighty|ninety|hundred|half|none|all|most|few|many|daya|biyu|uku|hudu|biyar|shida|goma|dari)\b",
    re.I,
)

SHORT_TURN_WORDS = 3  # same threshold interviews_step1.r uses for "a substantive turn"


def _ord_val(word):
    """'third'/'uku'/'3' -> 3; 'next'/'gaba' -> 'next'; 'final'/'karshe' -> 'last'."""
    w = _fold(word).strip()
    if not w:
        return None
    if w.isdigit():
        return int(w)
    if w in NEXT_WORDS:
        return "next"
    if w in LAST_WORDS:
        return "last"
    return EN_ORD.get(w) or HA_ORD.get(w)


def declared_position(text):
    """(question_no, part_no) as declared by the bot; either may be None / 'next' / 'last'."""
    f = _fold(text)
    q = p = None
    m = HA_QNUM.search(f) or EN_QNUM.search(f)
    if m:
        try:
            q = int(m.group(1))
        except (TypeError, ValueError):
            q = None
    m = HA_PART.search(f)
    if m:
        p = _ord_val(m.group(1))
    else:
        m = EN_PART.search(f)
        if m:
            p = _ord_val(m.group(1) or m.group(2) or "")
    return q, p


def resolve_declared(q_no, p_no, qp, open_idx, opened):
    """Map the position the bot DECLARED onto a sub-part index.

    The bot states its position two ways and both matter:
      "Question 2 of 9:"                  -> question number only  (topics A/B have discrete Q1..Q9)
      "**Tambaya ta 1 (Sashi na 3):**"    -> question AND part
      "**Sashi na gaba:**"                -> part only, within the current question

    Tracking only the part number — the original implementation — silently dropped every
    question-number-only advance. In hand validation that was the single largest error source: 5 of 7
    missed asks, all of them scored as probes, which inflates the probe count.

    `qp` is [(question_no, part_no), ...] parallel to the sub-part list, so a declared position maps
    to a real index instead of being assumed to be a flat offset.
    """
    if not qp:
        return None
    cur_q = qp[open_idx][0] if (isinstance(open_idx, int) and 0 <= open_idx < len(qp)) else None

    # part word may be relative rather than absolute
    if p_no == "next":
        return (open_idx + 1) if isinstance(open_idx, int) else 0
    if p_no == "last":
        if q_no or cur_q:
            want = q_no or cur_q
            idxs = [i for i, (q, _p) in enumerate(qp) if q == want]
            if idxs:
                return idxs[-1]
        return len(qp) - 1

    if isinstance(q_no, int) and isinstance(p_no, int):
        for i, (q, p) in enumerate(qp):
            if q == q_no and p == p_no:
                return i
        # question exists but that part number is beyond what the split derived: clamp to its last
        idxs = [i for i, (q, _p) in enumerate(qp) if q == q_no]
        return idxs[-1] if idxs else None
    if isinstance(p_no, int):
        want_q = cur_q or 1
        for i, (q, p) in enumerate(qp):
            if q == want_q and p == p_no:
                return i
        return None
    if isinstance(q_no, int):
        # question number alone: open its first part not yet visited, else its first
        idxs = [i for i, (q, _p) in enumerate(qp) if q == q_no]
        if not idxs:
            return None
        fresh = [i for i in idxs if i not in opened]
        return fresh[0] if fresh else idxs[0]
    return None


def classify_turns(messages, subparts, ask_overlap=0.55, subpart_toks=None, subpart_qp=None):
    """Label each AI turn and bind FLW turns to the sub-part that was open.

    Returns (turns, windows):
      turns   - one dict per message, in order, with role/kind/channel/subpart/words
      windows - one dict per (opened sub-part) with the ask, its probes, and the FLW answers
    """
    turns, windows = [], []
    open_idx = None  # sub-part currently being answered (bot's index where it declares one)
    opened = set()
    cur = None  # the window dict being filled
    last_declared = None  # the (question, part) the bot last stated — see the reask rule below
    synth = 0  # counter for parts the bot declares beyond what the split derived
    # caller may pass these in cached per question-block variant; they are identical for every
    # session sharing a variant and rebuilding them per session dominated runtime
    sub_toks = subpart_toks if subpart_toks is not None else [toks(s) for s in subparts]
    # (question_no, part_no) per sub-part; without it a declared position cannot be resolved.
    # Default assumes one question with sequential parts, which is true for all but topics A and B.
    qp = subpart_qp if subpart_qp is not None else [(1, i + 1) for i in range(len(subparts))]

    def start_window(idx, msg_i, channel, content, declared):
        """Open a sub-part window. `idx` may exceed the derived catalogue length: for 4 of 12 codes the
        bot declares MORE parts than the no-space split derives (it also splits some space-separated
        asks). The bot's own numbering is authoritative, so the window is still opened and
        `subpart_text` is simply None where we have no catalogue text to attach."""
        nonlocal cur, open_idx
        cur = {
            "subpart_idx": idx,
            "declared_part": declared if isinstance(declared, int) else None,
            "subpart_text": subparts[idx] if 0 <= idx < len(subparts) else None,
            "ask_msg_i": msg_i,
            "ask_channel": channel,
            "ask_text": content,
            "probes": [],
            "answers": [],
            "n_probes": 0,
            "n_reasks": 0,
        }
        windows.append(cur)
        open_idx = idx
        opened.add(idx)

    for i, m in enumerate(messages):
        content = (m.get("content") or "").strip()
        role = m.get("role")
        words = len(content.split())
        ver = next((t for t in (m.get("tags") or []) if re.match(r"^v\d+", str(t))), None)

        # OCS injects role=="system" messages into long sessions: "Here is a summary of the
        # conversation to date: ## SESSION INTENT ...". There are 4,648 of them averaging 298 words.
        # They are the bot's own context compression — NOT anything the FLW said. Treating any
        # non-assistant role as an FLW answer put 1.39M machine-written words into the "final answer"
        # totals and could make a question look answered on the strength of a summary. Excluded from
        # both sides of the conversation, but recorded so the count stays visible.
        if role == "system":
            turns.append(
                {
                    "i": i,
                    "role": "system",
                    "kind": "system",
                    "channel": None,
                    "subpart_idx": open_idx,
                    "words": words,
                    "text": content,
                    "created_at": m.get("created_at"),
                    "version": ver,
                }
            )
            continue

        if role != "assistant":
            rec = {
                "i": i,
                "role": "user",
                "kind": "answer",
                "channel": None,
                "subpart_idx": open_idx,
                "words": words,
                "text": content,
                "created_at": m.get("created_at"),
                "version": ver,
            }
            turns.append(rec)
            if cur is not None:
                cur["answers"].append(rec)
            continue

        f = _fold(content)
        q_no, p_no = declared_position(content)
        is_admin = bool(ADMIN.search(f)) or bool(META.search(content))
        mt = toks(content)
        best_idx, best_ov = None, 0.0
        for k, st in enumerate(sub_toks):
            o = overlap_toks(mt, st)
            if o > best_ov:
                best_idx, best_ov = k, o

        kind = channel = None
        target = None

        # NOTE on ordering: `is_admin` must NOT veto the ask channels. The bot routinely packs the
        # first question into the same message as the language confirmation ("Great, we'll proceed in
        # English! **Question 1** ... **Have you ever had a sick child...**"), and answers a meta
        # question in the same breath as the next ask ("Yes, I'm here! **Do you fill out reports?**").
        # Treating those as admin loses the ask and promotes the following probe to ask — measured on
        # session 5095a8b5. Admin is therefore a FALLBACK, checked only after every ask channel.

        # ---- channel 1: the position the bot declared (strongest signal; question and/or part)
        if p_no is not None or q_no is not None:
            target = resolve_declared(q_no, p_no, qp, open_idx, opened)
            if target is not None and target >= 0:
                # A RE-ASK is the bot restating the position it just stated. Deciding that from the
                # RESOLVED INDEX instead was wrong: for 4 of 27 codes the bot declares more parts than
                # the no-space split derives, so a genuine advance resolves onto an already-open index
                # and was scored a re-ask. In hand validation that was 4 of the 5 remaining missed
                # asks. Compare what the bot SAID to what it said last time instead, and when it has
                # moved but the index collides, open a fresh synthetic slot.
                # A RELATIVE declaration ("next part", "sashi na gaba", "final part") is by definition
                # a move, so it is always an ask — comparing those tuples for equality scored every
                # repeated "next part" as a re-ask and cost 4.5 points of agreement.
                # Only an ABSOLUTE position restated identically is a re-ask.
                declared_now = (
                    (q_no, p_no) if isinstance(p_no, int) or (p_no is None and isinstance(q_no, int)) else None
                )
                if declared_now is not None and declared_now == last_declared:
                    kind = "reask"
                elif target in opened:
                    synth += 1
                    target = len(qp) + synth
                    kind = "ask"
                else:
                    kind = "ask"
                channel = "declared"
                if declared_now is not None:
                    last_declared = declared_now

        # ---- channel 2: a bolded span that matches a catalogue sub-part (v50+ convention only, so
        # additive — never relied on, because v32-v39 bold only 2-4% of messages)
        if kind is None:
            bb_idx, bb_ov = None, 0.0
            for b in BOLD.findall(content):
                bt = toks(b)
                for k, st in enumerate(sub_toks):
                    o = overlap_toks(bt, st)
                    if o > bb_ov:
                        bb_idx, bb_ov = k, o
            if bb_idx is not None and bb_ov >= 0.50:
                if bb_idx not in opened:
                    target, kind, channel = bb_idx, "ask", "bold"
                elif bb_idx == open_idx:
                    kind, channel = "reask", "bold"

        # ---- channel 3: transition phrase with no index
        if kind is None and (ADVANCE.search(f) or MULTIPART.search(f)):
            nxt = (open_idx + 1) if open_idx is not None else 0
            if nxt < max(len(subparts), 1):
                target, kind, channel = nxt, "ask", "advance"

        # ---- channel 4: overlap with a sub-part not yet opened (English fallback)
        if kind is None and best_ov >= ask_overlap and best_idx is not None:
            if best_idx not in opened:
                target, kind, channel = best_idx, "ask", "overlap"
            elif best_idx == open_idx and best_ov >= 0.75:
                kind, channel = "reask", "overlap"

        # ---- channel 5: admin, only if nothing above claimed the turn
        if kind is None and is_admin:
            kind, channel = "admin", "admin"

        # ---- default: a probe on whatever is open (or admin if nothing is open yet)
        if kind is None:
            if open_idx is None:
                kind, channel = "admin", "preamble"
            else:
                kind, channel = "probe", "default"

        if kind == "ask" and target is not None:
            start_window(target, i, channel, content, p_no)
        rec = {
            "i": i,
            "role": "assistant",
            "kind": kind,
            "channel": channel,
            "subpart_idx": (target if kind == "ask" else open_idx),
            "words": words,
            "text": content,
            "created_at": m.get("created_at"),
            "version": ver,
            "best_overlap": round(best_ov, 3),
            "declared_q": q_no,
            "declared_part": p_no if isinstance(p_no, int) else None,
        }
        turns.append(rec)
        if kind in ("probe", "reask") and cur is not None:
            cur["probes"].append(rec)
            cur["n_probes" if kind == "probe" else "n_reasks"] += 1

    return turns, windows


def trigger_of(prev_answer_text, question_text):
    """Why did the bot probe? Classified from the FLW turn that preceded the probe.

    Deliberately NO topicality / "off-topic" category. Topicality would have to be judged by word
    overlap against the question, but ~40% of sessions run in Hausa against an ENGLISH question
    catalogue, so that overlap is near zero by construction. With the test in, "off_topic" came out as
    the single largest trigger (32.7%) and 92% of Hausa answers were marked unusable versus 55% of
    English ones — an artefact of the measure, not a finding. Judging relevance across languages needs
    the LLM pass, so it is left to that stage instead of being faked here.
    """
    t = (prev_answer_text or "").strip()
    if not t:
        return "no_answer"
    if CONFUSED.search(t):
        return "confused"
    if DONT_KNOW.search(t):
        return "dont_know"
    if len(t.split()) <= SHORT_TURN_WORDS:
        return "too_short"
    if NUMERIC_ASK.search(question_text or "") and not HAS_DIGIT.search(t) and not NUM_WORD.search(t):
        return "no_number_given"
    return "needs_depth"


# ---------------------------------------------------------------- probe typology (Robinson 2023, DICE)
# Descriptive-detail / Idiographic-memory / Clarifying / Explanatory, plus the elaboration probe.
# Published taxonomy rather than invented labels, and both languages, since ~60% of sessions are Hausa.
_PROBE_TYPES = (
    (
        "clarifying",
        re.compile(
            r"just\s+to\s+clarify|to\s+clarify|do\s+you\s+mean|did\s+you\s+mean|am\s+i\s+right"
            r"|to\s+confirm|make\s+sure\s+i\s+understand|correctly\s+understood|i\s+want\s+to\s+be\s+sure"
            r"|kuna\s+nufin|tabbatar|na\s+fahimci|fahimta\s+daidai",
            re.I,
        ),
    ),
    (
        "idiographic_memory",
        re.compile(
            r"a\s+time\s+when|a\s+specific\s+(?:case|time|instance|situation)|last\s+time|remember\s+a"
            r"|can\s+you\s+recall|think\s+of\s+a|walk\s+me\s+through\s+a|lokacin\s+da|ka\s+tuna|kun\s+tuna",
            re.I,
        ),
    ),
    (
        "descriptive_detail",
        re.compile(
            r"could\s+you\s+describe|can\s+you\s+describe|describe\s+(?:a|the|what)|more\s+detail"
            r"|for\s+example|such\s+as|specific\s+example|walk\s+me\s+through|what\s+exactly"
            r"|how\s+many|roughly\s+how|out\s+of\s+every|what\s+percentage"
            r"|misali|bayani\s+dalla|karin\s+bayani|adadi",
            re.I,
        ),
    ),
    (
        "explanatory",
        re.compile(
            r"\bwhy\b|what\s+makes|what\s+are\s+the\s+reasons|how\s+do\s+you\s+know|how\s+did\s+you"
            r"|what\s+causes|reason\s+for|dalili|me\s+ya\s+sa|yaya\s+kuka",
            re.I,
        ),
    ),
    (
        "elaboration",
        re.compile(
            r"tell\s+me\s+more|anything\s+else|could\s+you\s+share|can\s+you\s+share|more\s+about"
            r"|say\s+more|expand\s+on|kara\s+bayani|wani\s+abu\s+kuma",
            re.I,
        ),
    ),
)


def probe_type(text):
    """DICE-style label for one probe. First match wins, most specific patterns first."""
    f = _fold(text)
    for name, rx in _PROBE_TYPES:
        if rx.search(f):
            return name
    return "other"


def is_nonanswer(text, question_text=""):
    """Language-neutral 'a static form would have captured nothing usable here' test — no LLM.

    Only signals that hold in BOTH English and Hausa: nothing said, a turn too short to carry content
    (the same >3-word threshold interviews_step1.r uses), an explicit don't-know, or explicit
    confusion. `question_text` is kept in the signature for call-site stability but is intentionally
    unused — see trigger_of for why a topicality test cannot go here.
    """
    del question_text
    t = (text or "").strip()
    if not t or len(t.split()) <= SHORT_TURN_WORDS:
        return True
    return bool(DONT_KNOW.search(t) or CONFUSED.search(t))


# ---------------------------------------------------------------- language normalisation
# `preferred_language` is free text: "english", "hausa", "both", "english and hausa",
# "bilingual (english and hausa)", "hausa_english_mix", ... Collapse to 4 buckets so breakdowns are
# readable and the long tail cannot masquerade as separate populations.
def norm_lang(raw):
    f = _fold(raw or "")
    if not f.strip():
        return "unknown"
    en, ha = "english" in f or "turanci" in f, "hausa" in f
    if en and ha:
        return "mixed"
    if ha:
        return "hausa"
    if en:
        return "english"
    return "unknown"
