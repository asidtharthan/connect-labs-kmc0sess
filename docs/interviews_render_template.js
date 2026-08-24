// Connect Interviews - MASTER dataset dashboard (v3). DISPLAY-ONLY build.
// Data is embedded (DATA below) from dashboard_data.json - the validated master (build_master_4src.py)
// aggregated by build_dashboard_data.py and reconciled 18/18 by build_dashboard_data_audit.py
// (which sits on top of audit_e2e 26/26). All 62 cohorts.
// WHY embedded, not live: a live multi-opp pipeline pull of 64 opportunities exceeds the platform's
// 600s SSE timeout (serial per-opp CCHQ/Connect fetches) and returns nothing. Embedding the audited
// snapshot gives a 100%-accurate all-cohort dashboard now. To refresh data: re-run the offline build
// (build_master_4src -> build_dashboard_data -> audit -> re-embed) - see docs.
// Charts via window.Chart (Chart.js, preloaded in the Labs render env, same as the KMC dashboards).
function WorkflowUI(props) {
  var DATA = /*__DATA__*/;

  var tab = React.useState("overview");
  var activeTab = tab[0], setTab = tab[1];
  var tsub = React.useState("granular");
  var tableSub = tsub[0], setTableSub = tsub[1];
  var bsub = React.useState("subgroup");
  var bdSub = bsub[0], setBdSub = bsub[1];
  var fex = React.useState({});
  var funExp = fex[0], setFunExp = fex[1];   // expanded subgroups in the drop-off matrix
  var tex = React.useState({});
  var topicExp = tex[0], setTopicExp = tex[1];   // expanded topics in topic-completion drilldown
  var tcc = React.useState("stacked");
  var topicChart = tcc[0], setTopicChart = tcc[1];   // topic-completion chart type: stacked | scoreboard | heatmap
  var tgm = React.useState("topic");
  var topicGroupMode = tgm[0], setTopicGroupMode = tgm[1];   // topic-completion grouping: topic | theme (GW consolidated bars)
  var tcm = React.useState("pct");
  var tcMode = tcm[0], setTcMode = tcm[1];   // topic-completion value mode: pct | count (raw interview counts)
  var nam = React.useState("include");
  var naMode = nam[0], setNaMode = nam[1];   // stacked %-bar: include | exclude "not applicable" (exclude -> rescale to 100% of applicable)
  var gss = React.useState("");
  var gSearch = gss[0], setGSearch = gss[1];   // granular session search box
  var gpp = React.useState(0);
  var gPage = gpp[0], setGPage = gpp[1];   // granular page
  var gvw = React.useState("sessions");
  var gView = gvw[0], setGView = gvw[1];   // granular sub-view: sessions | matrix (FLW × Topic)
  // Granular-view filters are MULTI-select: each holds an array of selected values ([] = "All", no filter).
  var gf1 = React.useState([]); var fSg = gf1[0], setFSg = gf1[1];   // filter: subgroup(s)
  var gf2 = React.useState([]); var fCo = gf2[0], setFCo = gf2[1];   // filter: cohort(s)
  var gf3 = React.useState([]); var fSt = gf3[0], setFSt = gf3[1];   // filter: status(es)
  var gf4 = React.useState([]); var fTr = gf4[0], setFTr = gf4[1];   // filter: trained | untrained
  var gf5 = React.useState([]); var fTopic = gf5[0], setFTopic = gf5[1];   // filter: topic(s) (interview code)
  var odd = React.useState(null); var openDD = odd[0], setOpenDD = odd[1];   // which filter dropdown is open (one at a time)
  var ddq = React.useState({}); var ddQuery = ddq[0], setDdQuery = ddq[1];   // per-dropdown in-list search text
  var gso = React.useState({ key: "", dir: "asc" }); var gSort = gso[0], setGSort = gso[1];   // sessions table sort
  // FLW Retention tab: cross-filter selection {dim: [values]} + which outcome the panels rank by.
  var flwf = React.useState({}); var flwSel = flwf[0], setFlwSel = flwf[1];
  var flwm = React.useState("pc");
  var flwMetric = flwm[0], setFlwMetric = flwm[1];   // pc = per-cohort finish rate | any = finished >=1 schedule
  var dimp = React.useState(false);
  var deImpact = dimp[0], setDeImpact = dimp[1];   // item 8: raw vs de-impacted (penult/last artifact)
  var lvm = React.useState("pct");
  var lineMode = lvm[0], setLineMode = lvm[1];   // funnels retention chart x-axis: pct (by interview #) | time (by real calendar days since first interview); y is % Started in both
  var ldm = React.useState("init");
  var denomMode = ldm[0], setDenomMode = ldm[1];   // retention denominator: init (# initiated, constant) | prev (FLWs who started the previous interview)
  var lsg = React.useState({}); var hidSg = lsg[0], setHidSg = lsg[1];   // funnels line chart: hidden subgroups (custom legend toggle)
  var lineRef = React.useRef(null), lineInst = React.useRef(null);
  var barRef = React.useRef(null), barInst = React.useRef(null);
  var fvw = React.useState("retention"); var funView = fvw[0], setFunView = fvw[1];   // funnels tab: retention lines | cohort engagement (3-panel) | drop-off by cohort
  var cdl = React.useState("design"); var cdLevel = cdl[0], setCdLevel = cdl[1];       // drop-off view: by design | every cohort
  var cds = React.useState("drop"); var cdSort = cds[0], setCdSort = cds[1];           // drop-off view: sort by drop-off % | cohort id
  var cdw = React.useState(false); var cdWhy = cdw[0], setCdWhy = cdw[1];               // drop-off view: the fixed-days explainer, collapsed by default
  var esg = React.useState("ALL"); var engSg = esg[0], setEngSg = esg[1];              // cohort-engagement: selected cohort (default ALL - meaningful first view)
  var ell = React.useState("all"); var engLlo = ell[0], setEngLlo = ell[1];            // cohort-engagement: LLO filter (all | COWACDI | EHA)
  var ewin = React.useState("active"); var engWin = ewin[0], setEngWin = ewin[1];      // cohort-engagement: active window | full timeline
  var emk = React.useState(false); var engMark = emk[0], setEngMark = emk[1];
  var dsc = React.useState("flow"); var docSec = dsc[0], setDocSec = dsc[1];          // Documentation tab: which section
  var dnd = React.useState(null); var docNode = dnd[0], setDocNode = dnd[1];          // Documentation tab: selected lineage node
  var dcp = React.useState(false); var docCopied = dcp[0], setDocCopied = dcp[1];     // Documentation tab: clipboard feedback          // full timeline: opt-in active-window boundary annotation (off = clean)
  var ethr = React.useState(2); var engThr = ethr[0], setEngThr = ethr[1];             // active-window threshold: % of started FLWs newly active/week (1 tight | 2 std | 5 loose)
  var eng1Ref = React.useRef(null), eng1Inst = React.useRef(null);
  var eng2Ref = React.useRef(null), eng2Inst = React.useRef(null);
  var eng3Ref = React.useRef(null), eng3Inst = React.useRef(null);

  // Design + topic names come from the build (DATA.subgroupDesign / topicNames), derived from the
  // CommCare HQ interview_schedule lookup - single source of truth. Fallbacks for older data only.
  var SUBGROUP_DESIGN = {};
  if (DATA.subgroupDesign) {
    Object.keys(DATA.subgroupDesign).forEach(function (sg) { SUBGROUP_DESIGN[sg] = DATA.subgroupDesign[sg].topics; });
  } else {
    SUBGROUP_DESIGN = {
      "TRS": ["A", "B"], "TRE": ["A", "B", "C", "D", "E"],
      "ABT1-A": ["1", "2", "3", "4"], "ABT1-B": ["1", "2", "3", "4"],
      "ABT2-A": ["1", "2"], "ABT2-B": ["1", "2", "5", "6", "7", "8", "9", "3"],
      "PANEL": ["7", "1", "2", "12", "3", "4", "5", "6", "C", "10", "11", "8", "13"],
      "ABT3-A": ["8", "9", "10", "11"], "ABT3-B": ["8", "9", "10", "11"],
      "EXT": ["11", "C", "99"],
      "NPS": ["101"]
    };
  }
  var TOPIC_NAMES = DATA.topicNames || { A: "Community Demographics", B: "Malaria", C: "Nutrition Prevalance and Programs",
    D: "Water & Diarrhea", E: "Community & FLW Profile", "1": "Seasonal Malaria Chemoprevention",
    "2": "Seasonal Malaria Chemoprevention 2", "3": "Bed Net Usage", "4": "Health Worker Experience",
    "5": "Family Planning", "6": "Vitamin A Supplementation", "7": "Vaccines",
    "8": "Antibiotics and ACT Use", "9": "Medicine Quality & Counterfeiting",
    "10": "Malaria 2", "11": "Water & Diarrhea 2", "12": "Community & FLW Profile 2", "13": "Medicine Quality & Counterfeiting 2", "14": "Malaria 5",
    "8S": "Antibiotics and ACT Use 2", "8L": "Antibiotics and ACT Use 3", "10S": "Malaria 3", "10L": "Malaria 4", "11S": "Water & Diarrhea 3", "11L": "Water & Diarrhea 4", "13L": "Medicine Quality & Counterfeiting 3", "101": "NPS" };
  var SG_ORDER = ["TRS", "TRE", "ABT1-A", "ABT1-B", "ABT2-A", "ABT2-B", "PANEL", "ABT3-A", "ABT3-B", "2WT", "EXT", "NPS"];
  // Subgroups whose Connect funnel (Invited/Accepted/Claimed) hasn't been pulled yet (cohorts present
  // in the interview data but missing from the Connect snapshot). Their Invited=0 means "not pulled",
  // not "nobody invited" - flagged in the UI so the 0s aren't misread.
  var CONNECT_PENDING = DATA.connectPendingSubgroups || [];
  function connPending(sg) { return CONNECT_PENDING.indexOf(sg) >= 0; }
  // Wire format for flwMatrix cells - INDEX ORDER IS APPEND-ONLY (completed must stay 5). See
  // topic_status_lib.py. "not-triggered" (6) was added 2026-08-07: it separates "the bot never sent
  // this interview" from "we sent it and the FLW didn't respond", which the old model conflated.
  var STATES = ["not-applicable", "not-available-yet", "available-not-started", "available-missed-overdue", "started-not-completed", "completed", "not-triggered"];
  var STATES5 = ["not-available-yet", "available-not-started", "available-missed-overdue", "started-not-completed", "completed", "not-triggered"];
  // Topic-completion display order: completed (left/first) → not-available-yet; not-applicable parked last.
  // Used by the stacked bar, its legend, the detail table + drilldown, and the heatmap so they all read the same way.
  var BAR_ORDER = ["completed", "started-not-completed", "available-not-started", "available-missed-overdue", "not-triggered", "not-available-yet", "not-applicable"];
  var BAR_ORDER5 = ["completed", "started-not-completed", "available-not-started", "available-missed-overdue", "not-triggered", "not-available-yet"];
  var STATE_LABEL = { "not-applicable": "Not applicable", "not-available-yet": "Not available yet",
    "available-not-started": "Available, not started", "available-missed-overdue": "Window passed, not started",
    "started-not-completed": "Started, not completed", "completed": "Completed",
    "not-triggered": "Never sent (no trigger)" };
  var STATE_COLOR = { "not-applicable": "#e5e7eb", "not-available-yet": "#6366f1",
    "available-not-started": "#f59e0b", "available-missed-overdue": "#b91c1c",
    "started-not-completed": "#06b6d4", "completed": "#16a34a",
    "not-triggered": "#94a3b8" };   // slate: a pipeline gap, deliberately not alarm-red like a real miss
  var STATE_DEF = {
    "not-applicable": "topic isn't part of this cohort's design",
    "not-available-yet": "in the cohort, but not yet released per today's date, the topic's place in the schedule, and the cohort's training date",
    "available-not-started": "due per the schedule, not yet started (the next topic isn't due yet)",
    "available-missed-overdue": "the bot DID send this interview, the scheduled window has since passed, and no session exists - a genuine non-response",
    "not-triggered": "the schedule says this interview was due but NO trigger form was ever sent - a pipeline gap, not an FLW choice. Until 2026-08-07 these slots were counted as 'missed/overdue', which blamed the FLW",
    "started-not-completed": "FLW responded with ≥1 message but did not complete the session",
    "completed": "FLW completed the interview",
  };
  function Legend(props2) {
    return (
      <details className="text-xs text-gray-600 bg-gray-50 rounded border border-gray-200 px-3 py-2">
        <summary className="cursor-pointer font-medium text-gray-700">{props2.title}</summary>
        <div className="mt-2 space-y-1">{props2.children}</div>
      </details>
    );
  }
  // Maximally-distinct categorical palette (D3 category10) so every subgroup line is unambiguous.
  var SG_COLOR = { "TRS": "#1f77b4", "TRE": "#17becf", "ABT1-A": "#2ca02c", "ABT1-B": "#d62728", "ABT2-A": "#9467bd", "ABT2-B": "#8c564b", "PANEL": "#e377c2", "ABT3-A": "#f58231", "ABT3-B": "#bcbd22", "2WT": "#334155", "EXT": "#c51b8a", "NPS": "#0f766e" };
  // FLW × Topic matrix cell glyphs, indexed by STATES order (0 not-applicable … 5 completed)
  var CELL_GLYPH = ["", "·", "○", "!", "◐", "✓", "-"];   // index 6 = not-triggered (never sent)
  var MATRIX_TOPIC_ORDER = ["A", "B", "C", "D", "E", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "8S", "8L", "10S", "10L", "11S", "11L", "13L", "99", "101"];
  // GiveWell thematic grouping: pool related topics into one bar. Static + forward-looking
  // (already includes topics that get data later, e.g. ABT3 8S/8L/10S/10L/11S/11L/13L, 2WT 14).
  // A topic not listed here renders as its own bar. THEME_ORDER = display order of theme bars.
  var THEME_ORDER = ["Malaria", "Water & Diarrhea", "Community & FLW Profile", "Antibiotics and ACT Use", "Medicine Quality & Counterfeiting"];
  var TOPIC_GROUP = {
    "B": "Malaria", "1": "Malaria", "2": "Malaria", "10": "Malaria", "10S": "Malaria", "10L": "Malaria", "14": "Malaria",
    "D": "Water & Diarrhea", "11": "Water & Diarrhea", "11S": "Water & Diarrhea", "11L": "Water & Diarrhea",
    "E": "Community & FLW Profile", "12": "Community & FLW Profile",
    "8": "Antibiotics and ACT Use", "8S": "Antibiotics and ACT Use", "8L": "Antibiotics and ACT Use",
    "9": "Medicine Quality & Counterfeiting", "13": "Medicine Quality & Counterfeiting", "13L": "Medicine Quality & Counterfeiting"
  };
  // Pool DATA.topicStatus rows into theme bars (interview-level sum). Topics not in a theme stay
  // individual. Returns the SAME row shape (+ a `label`) so the charts reuse their existing code.
  function groupedTopicStatus(rows) {
    // derive from STATES, not a second hardcoded list: when "not-triggered" was added, a literal list
    // here left that key undefined on every pooled row and the theme bars charted NaN
    var STATE6 = STATES;
    var byKey = {}, order = [];
    rows.forEach(function (t) {
      var theme = TOPIC_GROUP[t.code];
      var key = theme || ("#" + t.code);   // "#code" keeps ungrouped topics distinct from theme labels
      if (!byKey[key]) {
        byKey[key] = { code: theme || t.code, name: theme || t.name, isTheme: !!theme,
          label: theme || (t.code + " · " + (TOPIC_NAMES[t.code] || t.code)), total: 0, applicable: 0 };
        STATE6.forEach(function (s) { byKey[key][s] = 0; });
        order.push(key);
      }
      var g = byKey[key];
      g.total += t.total || 0; g.applicable += t.applicable || 0;
      STATE6.forEach(function (s) { g[s] += t[s] || 0; });
    });
    return order.map(function (k) { return byKey[k]; }).sort(function (a, b) {
      var ai = a.isTheme ? THEME_ORDER.indexOf(a.name) : 100 + MATRIX_TOPIC_ORDER.indexOf(a.code);
      var bi = b.isTheme ? THEME_ORDER.indexOf(b.name) : 100 + MATRIX_TOPIC_ORDER.indexOf(b.code);
      return ai - bi;
    });
  }
  // The row set the topic-completion charts render: grouped-by-theme or raw per-topic.
  function topicRowsFor(rows, mode) { return mode === "theme" ? groupedTopicStatus(rows) : rows; }

  var th = "px-3 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider";
  var td = "px-3 py-2 whitespace-nowrap text-sm text-gray-800";
  function pctTxt(v) { return v == null ? "-" : v + "%"; }
  function pctOf(a, b) { return b > 0 ? Math.round((a / b) * 100) + "%" : "-"; }

  // ---- line chart (Interview Completion Funnels) ----
  React.useEffect(function () {
    if (activeTab !== "funnels") return;
    if (!lineRef.current || !window.Chart) return;
    if (lineInst.current) lineInst.current.destroy();
    // Both modes show retention (% Started) on Y. "pct" = x is the interview ordinal (evenly spaced);
    // "time" = x is real calendar days since the FLW's first interview (each dot at the day it landed).
    // The prev-denominator view is interview-# only (a "reached previous interview" denominator has no
    // meaning on a calendar-day axis), so force byDay off when denomMode === "prev".
    var prevDenom = denomMode === "prev";
    var byDay = lineMode === "time" && !prevDenom;
    var maxLen = 0; DATA.lineSeries.forEach(function (s) { maxLen = Math.max(maxLen, s.pts.length); });
    var labels = []; for (var i = 1; i <= maxLen; i++) labels.push("Int " + i);
    lineInst.current = new window.Chart(lineRef.current.getContext("2d"), {
      type: "line",
      data: { labels: byDay ? undefined : labels, datasets: DATA.lineSeries.map(function (s) {
        // denominator: prev = %started vs previous-interview starters; else initiated base (raw / de-impacted)
        var raw = prevDenom ? (s.pts_prev || []) : ((deImpact && s.pts_di && s.pts_di.length) ? s.pts_di : s.pts);
        var st = s.status || [];
        var dd = s.days || [];
        // not-available interviews (not yet offered) → null so the line ends instead of a false 0%
        var data;
        if (byDay) {
          // x = real days since first interview, y = % started; skip points with no day value
          data = raw.map(function (v, i) {
            if (dd[i] == null) return null;
            return { x: dd[i], y: st[i] === "not-available" ? null : v };
          }).filter(function (p) { return p !== null; });
        } else {
          data = raw.map(function (v, i) { return st[i] === "not-available" ? null : v; });
        }
        var col = SG_COLOR[s.sg] || "#9ca3af";
        // Dot the whole line while the subgroup is still being triggered (bot actively handing out
        // interviews); solid once triggering has stopped. Uses the build's activity flag (real trigger
        // within 2x cadence); falls back to the release-window status for older builds without the flag.
        var inProgress = (s.active != null) ? !!s.active : st.some(function (x) { return x === "in-progress"; });
        return { label: s.sg + " (n=" + s.base + ")", data: data, borderColor: col,
          backgroundColor: col, fill: false, tension: 0.2, spanGaps: false, borderWidth: 3,
          pointRadius: byDay ? 4 : 3, pointHoverRadius: 6,
          hidden: !!hidSg[s.sg], borderDash: inProgress ? [8, 5] : undefined }; }) },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { title: { display: true, text: prevDenom ? "% who started each interview OF THOSE WHO REACHED THE PREVIOUS ONE (denominator = FLWs who started interview N-1, not the full initiated base) - later interviews no longer collapse just because many FLWs haven't reached that stage yet; interview 1 = vs # initiated" : (byDay ? "% FLWs still starting each interview, plotted against real days since their first interview - each dot is an interview at the day it landed; two dots on ~the same day = the last two triggered back-to-back (penultimate artifact)" : "% FLWs who started each interview round (denominator = # FLWs initiated, constant per subgroup) - solid = subgroup fully settled, dotted = subgroup still in progress, line ends where interviews aren't offered yet") }, legend: { display: false } },
        scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: prevDenom ? "% Started (of prev-interview starters)" : "% Started" } },
          x: byDay ? { type: "linear", beginAtZero: true, title: { display: true, text: "Days since first interview" } } : { title: { display: true, text: "Interview #" } } } }
    });
    return function () { if (lineInst.current) { lineInst.current.destroy(); lineInst.current = null; } };
    // funView MUST be a dep: the canvas only exists while funView==="retention", so switching to
    // "engagement" and back remounts a fresh canvas while lineInst still points at the destroyed one -
    // without this the flagship retention chart came back as a blank 380px hole until some other
    // toggle happened to re-run the effect.
  }, [activeTab, funView, deImpact, hidSg, lineMode, denomMode]);

  // ---- stacked bar chart (Table View > Topic completion) ----
  React.useEffect(function () {
    if (activeTab !== "table" || tableSub !== "topiccomplete" || topicChart !== "stacked") return;
    if (!barRef.current || !window.Chart) return;
    if (barInst.current) barInst.current.destroy();
    var isCount = tcMode === "count";
    // counts mode: drop "not applicable" (it isn't an interview count) and fit the axis to the largest
    // applicable bar. % mode: by default keeps all 6 (stacks to 100% of total incl. N/A); when the user
    // excludes N/A, drop it and rescale the 5 real states to 100% of applicable.
    var excl = tcMode === "pct" && naMode === "exclude";
    var barStates = (isCount || excl) ? BAR_ORDER5 : BAR_ORDER;
    var tsRows = topicRowsFor(DATA.topicStatus, topicGroupMode);
    // length-guarded: Math.max.apply(null, []) === -Infinity, which is truthy, so `|| 1` never fires
    var maxApp = tsRows.length ? Math.max.apply(null, tsRows.map(function (t) { return t.applicable || 0; })) || 1 : 1;
    barInst.current = new window.Chart(barRef.current.getContext("2d"), {
      type: "bar",
      data: { labels: tsRows.map(function (t) { return t.label || (t.code + " · " + (TOPIC_NAMES[t.code] || t.code)); }),
        datasets: barStates.map(function (st) {
          return { label: STATE_LABEL[st],
            data: tsRows.map(function (t) { if (isCount) return t[st] || 0; var denom = excl ? (t.applicable || 0) : (t.total || 0); return denom ? Math.round(1000 * t[st] / denom) / 10 : 0; }),
            backgroundColor: STATE_COLOR[st] }; }) },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: "y",
        plugins: { title: { display: true, text: (topicGroupMode === "theme" ? "FLW status distribution by THEME (related topics pooled)" : "FLW status distribution by topic") + (isCount ? " - # of applicable slots" : (excl ? " - % of applicable slots (stacks to 100%)" : " - % of all slots (incl. cohorts the topic isn't in)")) }, legend: { position: "bottom", title: { display: true, text: "⇄ Toggle: click any status in the legend below to show / hide it in the chart", color: "#4f46e5", font: { weight: "bold", size: 11 } } },
          tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ": " + ctx.parsed.x + (isCount ? "" : "%"); } } } },
        scales: { x: { stacked: true, max: isCount ? maxApp : 100, title: { display: true, text: isCount ? "# of slots the topic applies to" : (excl ? "% of applicable slots" : "% of all slots") } }, y: { stacked: true, ticks: { autoSkip: false, font: { size: 10 } } } } }
    });
    return function () { if (barInst.current) { barInst.current.destroy(); barInst.current = null; } };
  }, [activeTab, tableSub, topicChart, tcMode, topicGroupMode, naMode]);

  // The tab list lives here, not inline in the JSX, so the Documentation tab can compare what it
  // documents against what actually exists (see docsCoverage) instead of silently going stale.
  var TABS = [["overview", "Overview"], ["table", "Table View"], ["funnels", "Interview Completion Funnels"],
              ["fullretention", "Full Retention Table"], ["breakdowns", "Breakdowns"],
              ["flw", "FLW Retention"], ["docs", "Documentation"]];

  // ============================================================ DOCUMENTATION TAB
  // ONE structured constant, TWO outputs: the interactive UI below and the Markdown/JSON export.
  // Same rule as the written briefs - this holds STRUCTURE AND EXPLANATION ONLY. Every quantity is
  // interpolated from the LIVE DATA object at render time (see liveFacts), so the documentation can
  // never quote a stale snapshot and cannot drift from the dashboard it describes.
  var DOCS = {
    layers: [
      { id: "src", label: "1 · Upstream systems", color: "#1565C0", note: "Where the raw facts are created. Labs only reads these; it never writes to them." },
      { id: "pull", layer: "pull", label: "2 · Pull scripts", color: "#00897B", note: "Fetch to local files, so a build is reproducible and can re-run without re-hitting the APIs." },
      { id: "build", label: "3 · Build", color: "#7B1FA2", note: "Join first, then aggregate. The join is the single source of truth." },
      { id: "gate", label: "4 · Gates", color: "#D84315", note: "Independent re-checks. Any failure ABORTS the run, so a bad number cannot reach the dashboard." },
      { id: "pub", label: "5 · Publish", color: "#2E7D32", note: "Embed the data into the React file and upload it to Labs." }
    ],
    nodes: [
      { id: "connect", layer: "src", label: "CommCare Connect", owns: "Invitations · Learn · claims",
        what: "The platform FLWs are recruited through. It knows who was invited to an opportunity, who accepted, who finished Learn, and who claimed the job.",
        why: "Gives us the TOP of the funnel. Without it we could only see people who already started interviewing, never the ones we failed to convert." },
      { id: "hqtrig", layer: "src", label: "CommCare HQ · Trigger Bot forms", owns: "What was offered, to whom, when",
        what: "Every time the bot offers an FLW their next interview, a form is submitted in the CommCare app.",
        why: "The ONLY record of what was OFFERED. Comparing offered against done is what separates “we never asked them” from “they did not do it”." },
      { id: "hqwel", layer: "src", label: "CommCare HQ · Welcome / Learn forms", owns: "Registration + demographics",
        what: "Registration fields: name, state, LGA, settlement, cadre, education, language.",
        why: "Every geography and cadre breakdown comes from here. No demographic is invented downstream." },
      { id: "hqsch", layer: "src", label: "CommCare HQ · interview_schedule lookup", owns: "The DESIGN: topic order + cadence",
        what: "An app lookup table saying which topics a cohort should get, in what order, and how many days apart.",
        why: "Defines what “finished” MEANS for each cohort. A 2-interview cohort that did 2 is complete; a 13-interview cohort that did 2 is not." },
      { id: "ocs", layer: "src", label: "OpenChatStudio (OCS)", owns: "The interviews themselves",
        what: "The AI interviewer. One session per FLW per interview, with status, timestamps and message counts.",
        why: "The only place an interview is actually STARTED or COMPLETED. Everything about answer depth originates here." },

      { id: "p_connect", layer: "pull", label: "fetch_connect_user_data.py", owns: "connect_user_data_snapshot.csv",
        what: "Headless pull of per-opportunity user data, consolidated to one row per FLW per cohort.",
        why: "Connect has no simple API key, so this uses a self-rotating refresh token. It also filters by cohort pattern - a new cohort missing from that map silently gets NO funnel data." },
      { id: "p_hq", layer: "pull", label: "pull_hq_full_payloads.py", owns: "hq_pull_full/{domain}__*.jsonl",
        what: "Downloads every Trigger-Bot and Welcome form submission, per CommCare domain.",
        why: "Full payloads rather than summaries, so any field can be re-derived later without another pull." },
      { id: "p_sch", layer: "pull", label: "pull_hq_interview_schedule.py", owns: "_interview_schedule.json",
        what: "Reads the schedule lookup and walks each topic chain into an ordered design.",
        why: "The design is read from the app rather than hardcoded, so a schedule change appears without a code edit." },
      { id: "p_ocs", layer: "pull", label: "pull_ocs_state.py · pull_ocs_words.py", owns: "_ocs_state_cache.json · _ocs_words_cache.json",
        what: "Session list with state, plus per-session FLW word and message counts.",
        why: "Incremental on purpose: OCS has no usable updated-at filter, so it re-scans a recent window and merges by session id. Re-pulling everything daily would hit rate limits." },

      { id: "master", layer: "build", label: "build_master_4src.py", owns: "ONE ROW PER FLW × INTERVIEW",
        what: "The join. For every FLW and every interview slot in their cohort’s design, it interlocks Connect, both HQ form sets and the OCS session, then marks that slot triggered / started / completed.",
        why: "THE source of truth. Every tab, chart and export is an aggregate of these rows - which is why two numbers on the dashboard cannot disagree by construction." },
      { id: "agg", layer: "build", label: "build_payload_agg.py", owns: "payload_agg.json",
        what: "Rolls the master rows into subgroup funnels, per-interview drop-off, weekly engagement series and the de-impact adjustment.",
        why: "Aggregating once, outside the browser, keeps the payload small and stops two charts computing the same thing two different ways." },
      { id: "dash", layer: "build", label: "build_dashboard_data.py", owns: "dashboard_data.json + render_data.json",
        what: "Assembles the final payload, then writes a PRUNED copy for the render.",
        why: "Labs caps the render file at 512 KB. The full payload stays complete for the gates; the pruned copy drops keys the interface never reads." },

      { id: "g6a", layer: "gate", label: "audit_e2e.py", owns: "Gate 6a",
        what: "End-to-end reconciliation of the master rows back against each source.",
        why: "Catches a join that silently dropped or duplicated rows." },
      { id: "g6b", layer: "gate", label: "build_dashboard_data_audit.py", owns: "Gate 6b",
        what: "Checks the payload the dashboard will actually read: every headline count must tie to the rows behind it.",
        why: "Catches an aggregation that no longer matches its own detail." },
      { id: "g7b", layer: "gate", label: "brutal_verify.py", owns: "Gate 7b + regression guard",
        what: "Re-derives the headline numbers from the RAW sources using its own separate code, cross-checks every place a number appears, and compares against run history.",
        why: "The duplication is deliberate. If the builder and this disagree, one is wrong and the run stops. It also blocks a silent collapse: counts cannot fall below a floor derived from the best-ever run." },

      { id: "inject", layer: "pub", label: "inject into the render template", owns: "docs/interviews_master_v3_render.js",
        what: "Substitutes the pruned payload into the placeholder inside docs/interviews_render_template.js.",
        why: "The data is EMBEDDED, not fetched live: a live multi-cohort pull exceeds the platform request timeout and would return nothing at all." },
      { id: "push", layer: "pub", label: "publish via MCP", owns: "Labs workflow 3962 render_code",
        what: "Uploads the finished file as a new render version, guarded by the expected current version.",
        why: "Version-guarded so two runs cannot overwrite each other unnoticed. A timed-out upload is re-checked rather than assumed to have failed." }
    ],
    edges: [
      ["connect", "p_connect", "invited · accepted · learn · claimed"],
      ["hqtrig", "p_hq", "offer events"], ["hqwel", "p_hq", "registration fields"],
      ["hqsch", "p_sch", "topic chain + cadence"], ["ocs", "p_ocs", "sessions + word counts"],
      ["p_connect", "master", "funnel columns"], ["p_hq", "master", "triggered + demographics"],
      ["p_sch", "master", "the design"], ["p_ocs", "master", "started + completed"],
      ["master", "agg", "rows"], ["agg", "dash", "rollups + series"],
      ["dash", "g6a", ""], ["dash", "g6b", ""], ["dash", "g7b", "raw re-derivation"],
      ["g7b", "inject", "all gates pass"], ["inject", "push", "one .js file"]
    ],

    // ---- what each tab answers, and which payload keys it reads
    tabs: [
      { id: "overview", name: "Overview", question: "How big is this and is it healthy?",
        reads: ["counts", "table1", "topicStatus"],
        charts: [
          ["Headline counts", "Unique FLWs, cohorts, interviews started and completed - counted as DISTINCT things, so the same FLW in three cohorts is one FLW."],
          ["FLW status by topic", "For each topic, how many claimed slots ended completed / started-not-completed / offered-but-missed / never offered."]
        ] },
      { id: "table", name: "Table View", question: "What do the numbers look like per subgroup and per cohort?",
        reads: ["table1", "table2", "table3", "cohortSG"],
        charts: [["Subgroup and cohort tables", "The same counts as Overview, split by subgroup, arm and individual cohort, with average FLW words per interview."]] },
      { id: "funnels", name: "Interview Completion Funnels", question: "Where do people fall out, and are they still engaged?",
        reads: ["connectFunnel", "dropoff", "lineSeries", "deimpact", "cohortEngagement", "cohortEngagementLLO", "cohortDropoff"],
        charts: [
          ["Connect funnel", "Invited → accepted → Learn completed → claimed → initiated. Everything before an interview exists."],
          ["Interview drop-off table", "Per interview slot: eligible, triggered, started, completed, with three percentage bases (see Indicators)."],
          ["Retention lines", "Completion by interview number, with a Denominator toggle and a de-impact toggle."],
          ["Cohort Engagement (3 panels)", "Weekly recruitment, outcome (Completed / Dropped off / Schedule not completed / In progress) plus rhythm (Steady / Inconsistent), and status-now (New / Active / Slow / Quiet / Finished)."],
          ["Drop-off by cohort", "One row per cohort design or per individual cohort, each scored at ITS OWN end date rather than today or a date shared across the design. Five mutually exclusive states, defined on the page itself, plus a table showing what a fixed number of days would have meant in each design. Sortable by drop-off or by name at either level."]
        ] },
      { id: "fullretention", name: "Full Retention Table", question: "Give me every cohort × interview number in one grid.",
        reads: ["dropoff", "cohortSG"],
        charts: [["Full grid + CSV export", "One row per cohort, one column per interview slot, exportable."]] },
      { id: "breakdowns", name: "Breakdowns", question: "How does completion differ by who and where?",
        reads: ["granular", "topicStatusCohort", "flwMatrixV2"],
        charts: [
          ["Granular filters", "Multi-select filters over the per-slot rows, with CSV export of the filtered set or everything."],
          ["FLW × topic matrix", "One row per FLW, one cell per topic, coloured by the 7-state slot model."]
        ] },
      { id: "flw", name: "FLW Retention", question: "Treating each PERSON as the unit, who keeps going and who stops?",
        reads: ["flwEngagement"],
        charts: [
          ["Headline cards", "Per-cohort finish on both bases, finished ≥ 1 schedule, answer depth."],
          ["Nine drill-down panels", "State, partner, cadre, tier, persona, cohort count, finished, peer density, pace - all click-to-filter and cross-filtering."],
          ["Survival ladder", "Share reaching each interview number, each row against its OWN eligible pool."],
          ["Geography", "LGA-level spread, which is wider than the between-state spread."]
        ] },
      { id: "docs", name: "Documentation", question: "How does all of this work, and how do I add a cohort?",
        reads: ["everything (read-only)"],
        charts: [["This tab", "Lineage diagram, indicator definitions, the cohort-onboarding checklist, glossary, and the export bundle."]] }
    ],

    // ---- every indicator: where it appears, how it is computed, and what NOT to conclude
    metrics: [
      { g: "Funnel", name: "Invited / Accepted / Learn completed / Claimed", where: "Funnels → Connect funnel",
        how: "Counted from the Connect snapshot, one row per FLW per cohort.",
        base: "Everyone invited to that opportunity.",
        gotcha: "This is the ONE leg that does not auto-refresh from a live API in every mode - if a new cohort is missing from the Connect pull’s cohort map, its funnel shows zeros while its interview numbers look fine." },
      { g: "Funnel", name: "Eligible", where: "Funnels → drop-off table",
        how: "FLWs whose cohort design CONTAINS that interview slot and who reached the point of being in the study.",
        base: "-", gotcha: "Eligible is a TRIGGERED-side basis. It can exceed the number who ever started an interview, so a percentage of eligible is not a percentage of active people." },
      { g: "Funnel", name: "Triggered", where: "Funnels → drop-off table",
        how: "A Trigger-Bot form exists for that FLW and slot: the bot offered it.",
        base: "Eligible", gotcha: "Offered is not the same as received. A low triggered share is a programme/rollout issue, not an FLW behaviour issue." },
      { g: "Funnel", name: "Started / Completed", where: "Funnels, Overview, Tables",
        how: "An OCS session for that FLW and topic exists (started) and reached completion (completed).",
        base: "Eligible, triggered, or the interview-1 base - the table shows all three",
        gotcha: "Always check WHICH base a percentage uses. “% of base” compares against interview 1, so it falls as the schedule progresses even when each individual step is healthy." },
      { g: "Retention", name: "Retention line - # Initiated", where: "Funnels → Retention lines",
        how: "Completed at interview N divided by everyone who initiated the study.",
        base: "Fixed base = initiated", gotcha: "Falls steeply for long schedules simply because later interviews have not been offered yet." },
      { g: "Retention", name: "Retention line - Reached previous interview", where: "Funnels → Retention lines (Denominator toggle)",
        how: "Started at N divided by started at N−1, any status.",
        base: "Moving base = the previous step", gotcha: "Answers “of those who got here, how many continued”. Same numerator as the other view - only the denominator changes." },
      { g: "Retention", name: "De-impact", where: "Funnels → de-impact toggle",
        how: "Removes FLWs affected by a known upstream scheduling artefact where a final interview could fire back-to-back with the one before it.",
        base: "-", gotcha: "A correction for a bug in the interview app, not a data cleanup. Root cause is upstream; the toggle only shows what the number would be without it." },
      { g: "Engagement", name: "Finished", where: "Funnels → Cohort Engagement; FLW Retention",
        how: "Completed EVERY interview in their cohort’s design. The finish date is the date the last one was completed.",
        base: "FLWs who started ≥ 1 interview in that subgroup",
        gotcha: "Depends on the design length, so it is not comparable across subgroups without saying how many interviews each has. Finished OUTRANKS every other status - a finisher is never counted as dropped." },
      { g: "Engagement", name: "Dropped off", where: "Funnels → Cohort Engagement; Funnels → Drop-off by cohort",
        how: "Has NOT finished the schedule AND an interview they were actually sent went past its deadline unfinished. The deadline is one interview gap after it was released - so 3 days in a 3-day design and 14 in a 14-day one. This is the same rule the FLW × Topic matrix uses to call a slot missed/overdue, so the two halves of the dashboard now agree.",
        base: "FLWs who started ≥ 1 interview",
        gotcha: "Only interviews the bot ACTUALLY SENT can be missed. An FLW who completed everything sent to them but whose design never finished is counted as SCHEDULE NOT COMPLETED, not Dropped - blaming them for a schedule that stopped would be wrong. Recoverable on purpose: complete a late interview and the FLW leaves this bucket." },
      { g: "Engagement", name: "Schedule not completed", where: "Funnels → Cohort Engagement; Funnels → Drop-off by cohort",
        how: "Completed every interview that was ever SENT to them, but their design is not complete because nothing further was sent, and their cohort has since closed.",
        base: "FLWs who started ≥ 1 interview",
        gotcha: "Every FLW here sits in a CLOSED cohort with no interview merely “not due yet”, so nothing is still coming. NOT drop-outs (blaming them for a schedule that stopped would be wrong) and NOT finishers (some did 1 of 2 interviews, some 11 of 13). Never add this to a drop-off figure." },
      { g: "Engagement", name: "Completed late", where: "Funnels → Drop-off by cohort",
        how: "Completed every interview in their design, but the last one landed AFTER their cohort’s window had closed.",
        base: "FLWs who started ≥ 1 interview",
        gotcha: "Scoring strictly at the window end filed these as “dropped off”, which is wrong - they finished. Completed on time + Completed late is the total who finished." },
      { g: "Engagement", name: "Steady vs Inconsistent", where: "Funnels → Cohort Engagement",
        how: "Steady = never a gap longer than the cohort’s gap threshold. Inconsistent = at least one longer gap. The threshold is twice that cohort’s interview cadence. This is a SEPARATE reading from the outcome (Completed / Dropped off / Schedule not completed / In progress), not one of its buckets - a finisher has a rhythm just as much as a dropout does, and the two pairs each sum to 100% on their own base. Measured on the largest gap BETWEEN interviews, not time since the last one.",
        base: "Starters with 2+ interviews (rhythm_base). One interview gives no gap to judge, so a single-interview design reads “not measurable” rather than 0%",
        gotcha: "Cadence-relative on purpose, so a 3-day and a 14-day cohort are judged fairly. It is therefore NOT a fixed number of days across subgroups. On the ALL COHORTS view each FLW is judged against their OWN design’s cadence, and the figure is pooled from the per-design results so it cannot contradict them." },
      { g: "Engagement", name: "New / Active / Slow / Quiet", where: "Funnels → Cohort Engagement panel 3",
        how: "Status right now, in priority order: first-ever interview this week (New), last interview within ONE interview gap (Active), one to two gaps (Slow), more than two gaps (Quiet). Finished takes precedence over all four.",
        base: "FLWs who started ≥ 1 interview",
        gotcha: "The bands are gap multiples, not fixed days, so “Active” means the same thing (on pace) in a 3-day design and a 14-day one. Until 2026-08-21 they were a flat 7 and 14 days for every design. Quiet and Dropped no longer count the same people: Quiet is about silence, Dropped is about a missed deadline." },
      { g: "Engagement", name: "Active window vs Full timeline", where: "Funnels → Cohort Engagement",
        how: "Active window trims trailing weeks once fewer than the cutoff share of a cohort is newly starting or finishing, so a completed cohort does not read as a long flat drop-off. Full timeline shows every week.",
        base: "-",
        gotcha: "For ALL COHORTS the window runs as long as ANY cohort is still active, because a percentage of the whole population is a bar a small late cohort could never reach. Where there is nothing to trim the toggle is hidden. The KPI tiles are always CURRENT; a trimmed chart can legitimately end earlier, and the page states both numbers when they differ." },
      { g: "Slots", name: "The 7 slot states", where: "Overview, Breakdowns matrix",
        how: "Each FLW × topic cell is exactly one of: completed, started-not-completed, available-not-started, available-missed-overdue, not-available-yet, not-triggered, not-applicable. A slot is missed/overdue one interview gap after it was sent.",
        base: "Claimed slots",
        gotcha: "“Not applicable” means the topic is not in that cohort’s design at all - it is not a failure and must not be added to a denominator. The FINAL interview has a deadline like every other; it used to be exempt, so nobody could be recorded as skipping their last one." },
      { g: "FLW", name: "Per-cohort finish - so far", where: "FLW Retention",
        how: "For each FLW, schedules finished divided by every schedule they were enrolled in, then averaged across FLWs.",
        base: "All their enrolments",
        gotcha: "Counts schedules the programme has NOT finished rolling out as unfinished, so it understates finishing - and understates it slightly more for multi-cohort FLWs, who are likelier to be carrying one still in flight." },
      { g: "FLW", name: "Per-cohort finish - of schedules actually offered", where: "FLW Retention",
        how: "Same numerator, but divided only by schedules whose whole design was actually put to them.",
        base: "Fully-offered enrolments only",
        gotcha: "The fair like-for-like rate, but silent about work still in progress. FLWs with no fully-offered schedule are EXCLUDED rather than counted as zero." },
      { g: "FLW", name: "Recently active / came back / needs following up", where: "FLW Retention",
        how: "Recently active = last session within two interview gaps. Came back = a break of three or more gaps, then a return. Needs following up = last session between two and eight gaps ago, unfinished, and the programme did finish offering them a schedule.",
        base: "All FLWs (the follow-up pool also requires a fully-offered schedule)",
        gotcha: "Gap multiples, not fixed days, so they mean the same thing at any pace. A single-interview design falls back to 7 days." },
      { g: "FLW", name: "Finished ≥ 1 schedule", where: "FLW Retention",
        how: "Finished at least one of their cohorts.",
        base: "All FLWs",
        gotcha: "Mechanically rises with the number of cohorts someone is in - three cohorts is three chances. Do not read a multi-vs-single gap on this measure as evidence that re-use improves engagement." },
      { g: "FLW", name: "Engagement tier", where: "FLW Retention",
        how: "A score band blending recency, completion rate and answer depth.",
        base: "All FLWs",
        gotcha: "Describes where someone is TODAY, not their history. Because it rewards recency and depth, the top tier is NOT necessarily the best finishers. Recency is measured against the freshest session in the data, not the wall clock, so a lagging pull cannot push everyone into a worse tier." },
      { g: "FLW", name: "Persona", where: "FLW Retention",
        how: "A rule-based segment over the FLW’s whole history.",
        base: "All FLWs",
        gotcha: "Several personas are DEFINED by whether the person finished, so the finish rate shown beside them is a definition, not a result - One-and-done is 0% by construction." },
      { g: "FLW", name: "Survival ladder", where: "FLW Retention",
        how: "Share reaching each interview number, each row against the FLWs whose own design CONTAINS that interview.",
        base: "Per-row eligible pool",
        gotcha: "Each row has a DIFFERENT denominator, so a later interview can legitimately show a HIGHER share than an earlier one when short-schedule cohorts leave the pool. Compare a row to its own count, never to the row above." },
      { g: "Quality", name: "Average FLW words", where: "Overview, Tables, FLW Retention",
        how: "Whitespace-separated words in FLW messages only, from OCS.",
        base: "FLW messages",
        gotcha: "Bot messages and OCS system messages are excluded. A word count is a proxy for effort, not for correctness or relevance." },
      { g: "Display", name: "Dotted vs solid funnel line", where: "Funnels → Retention lines",
        how: "Dotted while a subgroup is still inside its expected rollout window; solid once every cohort has passed it.",
        base: "-",
        gotcha: "Dotted means “still arriving, do not read the fall as attrition”. Two subgroups whose real schedule cannot be derived have a pinned end date, taken from the Cohort Tracker." }
    ],

    // ---- adding a cohort: the checklist, verified against current code
    onboarding: [
      { n: 1, title: "Get the facts first", file: "-",
        what: "You need four things: the CommCare domain name, the cohort id as it appears in the data, which subgroup it belongs to (existing or new), and its interview design - the topic order and the cadence in days.",
        gotcha: "Do not guess the design. It comes from the app’s interview_schedule lookup and is pulled automatically; the fallback in code is only a safety net." },
      { n: 2, title: "Add the domain to the three HQ pull scripts", file: "pull_hq_full_payloads.py · pull_hq_interview_schedule.py · pull_hq_user_cases.py",
        what: "Each has a default domain list. Add the new domain to all three.",
        gotcha: "Miss one and you get partial data with no error - forms but no schedule, or a schedule with no forms." },
      { n: 3, title: "Add the domain to the list the BUILD actually reads", file: "build_master_4src.py → ALL_DOMAINS",
        what: "This is the list that opens the downloaded files.",
        gotcha: "THE #1 GOTCHA. Miss this and the data sits on disk and is silently ignored: no error, no new cohort, the counts simply do not move." },
      { n: 4, title: "Map the cohort id to its subgroup", file: "build_master_4src.py → cohort_to_sg",
        what: "A pattern turning a cohort id into a subgroup name.",
        gotcha: "Unmapped cohorts are collected and surfaced on the dashboard as a warning rather than dropped - so if you see that notice, this step is what is missing." },
      { n: 5, title: "Label the subgroup and give it a fallback design", file: "build_master_4src.py → COHORT_TYPE_MAP, _FALLBACK_DESIGN",
        what: "A human-readable label, plus topics and cadence used if the live schedule is unavailable.",
        gotcha: "-" },
      { n: 6, title: "Add the same pattern to the Connect pull", file: "fetch_connect_user_data.py → _cohort_to_sg",
        what: "The Connect pull filters opportunities by the same mapping.",
        gotcha: "Miss this and the interview numbers appear but the whole Connect funnel reads zero for the new cohort." },
      { n: 7, title: "Add the subgroup to every gate script", file: "build_payload_agg.py · audit_e2e.py · brutal_verify.py · build_dashboard_data_audit.py",
        what: "Each holds its own subgroup ordering and arm-rollup map. brutal_verify.py deliberately keeps its OWN copy of the cohort mapping.",
        gotcha: "Miss one and the build ABORTS with a key error. That is the gates working as intended - it is louder and safer than shipping a half-loaded cohort." },
      { n: 8, title: "Add it to the render", file: "docs/interviews_render_template.js",
        what: "Subgroup display order, a distinct colour, and the fallback design. Add topic names only if the cohort introduces a NEW topic.",
        gotcha: "Pick a colour that is genuinely distinct from the existing ones - several near-identical colours have had to be fixed here before." },
      { n: 9, title: "Build locally and read the gate output", file: "python refresh_interviews_dashboard.py",
        what: "With no flags it skips all the network pulls and just builds, audits and injects, so you can check the new cohort appears with sensible numbers.",
        gotcha: "A brand-new cohort legitimately looks odd at first - release status not-available, a nonsense average from a single interview. Those settle as data accrues." },
      { n: 10, title: "Publish with a FULL refresh, not the render-only shortcut", file: "GitHub Actions → Refresh Interviews Dashboard",
        what: "A new cohort is a DATA change, so the Connect pull has to run. Trigger the workflow rather than pushing a render.",
        gotcha: "Never run two refreshes at once: the Connect credential rotates itself during a run, so a second overlapping run fails authentication." }
    ],

    shortcuts: [
      { name: "Render-only publish", when: "You changed only presentation - wording, colours, layout, a chart option.",
        how: "Read the CURRENTLY PUBLISHED render, lift its embedded data out, inject that same data into the edited template, and upload. Live numbers are preserved exactly and no rebuild runs.",
        risk: "Valid ONLY when no number changes. If you touched anything that computes a value, this quietly ships old data under new code." },
      { name: "Build with no credentials", when: "Local development.",
        how: "Run the refresh script with no flags: it uses the local source files already on disk and does build → audit → inject.",
        risk: "Whatever is on disk may be stale. Never quote a number from a local build - read it from the published dashboard." },
      { name: "Test render changes without publishing", when: "You edited the React file.",
        how: "Inject the live data into the edited template and run it through the offline browser harness, which drives real clicks and asserts on what is displayed.",
        risk: "None. This is the cheapest way to catch a blank chart or a mislabelled figure before anyone sees it." },
      { name: "Re-run after a failed publish", when: "The gates passed but the upload failed.",
        how: "Just re-trigger. The upload is version-guarded and re-checks whether the write actually landed, so a retry cannot double-publish.",
        risk: "Read the actual error first. A timeout is transient; an authentication error means the token needs re-minting." }
    ],

    // ---- CREATING THE OPPORTUNITY (CommCare HQ + Connect). This happens BEFORE Labs is touched at all:
    // no opportunity means no cohort, no forms and nothing for the pipeline to read. Transcribed from the
    // team's "Interviews: Opportunity Creation Checklist", which is the operational source of truth.
    // Two variants exist; they differ only at step 3.
    opportunity: {
      note: "Do this first. Steps 1-2 happen in CommCare HQ, steps 3-6 in the Connect dashboard. Cohort-specific values (payment, total interviews, max users, cadence) all come from the Cohort Tracker - do not invent them.",
      variants: [
        ["Standard experimental", "The opportunity is created directly from the opportunities list."],
        ["Program-based (generic)", "The opportunity is created inside a Program, so it inherits that program's settings. Only step 3 differs."]
      ],
      steps: [
        { n: 1, title: "Prepare the apps", where: "CommCare HQ",
          items: [
            "Copy the existing app from the master connect-interviews project space - once per cohort, for BOTH the Learn app and the Deliver app - into the delivering partner's project space (EHA or COWACDI).",
            "Rename each copy by changing the bracketed value to the new Cohort ID (e.g. 09TRE).",
            "Publish a new version of both apps and mark it released."
          ],
          why: "The Deliver app is what submits the Trigger-Bot forms Labs reads. An unreleased app submits nothing, so the cohort would silently never appear.",
          gotcha: "Both apps, not just one. Learn gates payment eligibility; Deliver produces the interview records." },
        { n: 2, title: "Update the user field and the lookup table", where: "CommCare HQ",
          items: [
            "User field: in the MAIN project space add the new Cohort ID as a choice, then push it down to the downstream projects.",
            "Lookup table: add one row per interview topic for the new cohort, each with its frequency in days (from the Cohort Tracker).",
            "Set the FIRST topic's frequency to empty (a double dash) and the LAST topic's frequency to 9999.",
            "Push the lookup table down to the two downstream projects - excluding the test project domain."
          ],
          why: "THIS TABLE IS THE DESIGN. Labs reads it to learn which topics a cohort should receive, in what order and how far apart - which is what defines “finished” for that cohort and therefore every completion and drop-off percentage on the dashboard.",
          gotcha: "The first-empty / last-9999 convention is how the chain start and end are detected. Get it wrong and the derived schedule is wrong: a missing 9999 can leave the chain open, and a real topic mistaken for an end-marker drops a whole interview from the design. That exact mistake has happened - a genuine third interview was read as a terminal marker and disappeared from the dashboard until it was corrected." },
        { n: "2b", title: "If the workers are re-used from an existing cohort", where: "CommCare HQ",
          items: [
            "FIRST - case update via Excel import on commcare-user, keeping ONLY case-id, name and cohort-id (remove every other property).",
            "SECOND - update the mobile worker user field via bulk upload with the new cohort_id."
          ],
          why: "The same person can appear in several cohorts. Both the case and the user field must carry the new cohort_id or their interviews attach to the wrong cohort.",
          gotcha: "Order matters: case update first, then the user field. This is also why the dashboard counts a person once but their enrolments separately." },
        { n: 3, title: "Create the opportunity", where: "Connect dashboard",
          items: [
            "STANDARD: go to the opportunities section and click Add Opportunity.",
            "PROGRAM-BASED: open the Dimagi program-manager profile, go to Programs, click View Status on the relevant program, then Create Opportunity - and confirm the info panel reads “This opportunity will be created under the … program”.",
            "Name it with the Cohort ID (e.g. 09TRE). Currency NGN, country Nigeria.",
            "HQ server: CommCare HQ. Select the API query, and make sure that API is configured for ALL projects.",
            "Copy the long description from an existing opportunity and change the cohort reference to the new Cohort ID. Add a short description (e.g. “Connect Interviews : EHA Cohort 08TRS”).",
            "Select the newly created Learn and Deliver apps. Learn app passing score is 4."
          ],
          why: "The opportunity is what FLWs are invited to, and its name is the cohort id that flows through every downstream join.",
          gotcha: "If the API query is not configured for all projects the opportunity cannot see its own app data. Check the program info panel before submitting - an opportunity created outside its program is awkward to move." },
        { n: 4, title: "Configure payment and budget", where: "Connect dashboard",
          items: [
            "Add a payment unit, named for the cohort (e.g. “08TRS interview completed successfully”).",
            "Payment amount: from the Cohort Tracker.",
            "Maximum visits per user = the cohort's TOTAL INTERVIEWS.",
            "Maximum visits per day = 1.",
            "Start date: today is fine - but it CANNOT be changed afterwards.",
            "Worker budget: from the Cohort Tracker's max users, rounded up (e.g. 33 or 35 → 40).",
            "End date: optional. Leaving it blank avoids problems later if the end date moves."
          ],
          why: "Maximum visits per user caps how many interviews a worker can be paid for, so it must equal the design length or the last interviews cannot be completed.",
          gotcha: "The start date is immutable - set it deliberately. One visit per day is what keeps interviews spaced rather than done back to back." },
        { n: 5, title: "Create the conditional alert", where: "CommCare HQ",
          items: [
            "One alert per opportunity, on commcare-user.",
            "Conditions: cohort_id = the new Cohort ID, and session_completion = session completed."
          ],
          why: "This is what triggers payment on a completed interview session.",
          gotcha: "The cohort_id in the alert must match the new cohort exactly - copying an alert and forgetting to change it pays the wrong cohort." },
        { n: 6, title: "Verify the configuration", where: "Connect dashboard → hamburger menu",
          items: [
            "Delivery Type: change to “Interviews”.",
            "Verification flags: REMOVE the GPS verification check.",
            "“Is Test”: make sure it is switched OFF.",
            "Active status: set active when it is ready to launch."
          ],
          why: "These four are easy to miss and each one breaks something quietly.",
          gotcha: "GPS verification left on stops workers being auto-approved for payment. “Is Test” left on marks the cohort as test data, and Labs deliberately EXCLUDES test-flagged data - so the cohort would be invisible on the dashboard while looking fine in Connect." }
      ]
    },

    // ---- what to do when a figure looks wrong. Every entry here is a failure that has actually occurred.
    troubleshooting: [
      { symptom: "A new cohort does not appear at all, and there is no error anywhere.",
        cause: "Its domain is missing from the list the BUILD reads, so the downloaded files are never opened.",
        fix: "Add the domain to ALL_DOMAINS in the master build, not just to the pull scripts. This is the single most common onboarding mistake." },
      { symptom: "Interview counts look right but the Connect funnel reads zero for one cohort.",
        cause: "The Connect pull filters opportunities by a cohort pattern and the new cohort does not match it.",
        fix: "Add the pattern to the Connect pull as well as the master build - they keep separate copies." },
      { symptom: "The build aborts with a key error naming a subgroup.",
        cause: "A gate script does not know that subgroup yet.",
        fix: "Add it to all four gate scripts. This is the gates working correctly: stopping is safer than publishing a half-loaded cohort." },
      { symptom: "A cohort appears but its schedule length is wrong, so completion looks impossible or too easy.",
        cause: "The lookup table's frequency convention was not followed, so the topic chain was derived incorrectly.",
        fix: "Check the first topic is an empty/double-dash frequency and the last is 9999, then confirm the derived design on this dashboard matches the Cohort Tracker." },
      { symptom: "Two figures on the same screen disagree about the same thing.",
        cause: "Almost always different denominators, or one figure is current while the other is windowed.",
        fix: "Check the Indicators section for both - every one states its base. Chart tiles are current-state; a trimmed chart can legitimately end earlier, and the page says so where they differ." },
      { symptom: "The dashboard did not refresh today.",
        cause: "The daily job failed. Data problems abort at a gate; publishing problems abort at the upload.",
        fix: "Read the run log. If the gates passed and the upload failed, the data was fine and a re-run usually fixes it - the upload is version-guarded and re-checks whether the write actually landed." },
      { symptom: "A brand-new cohort shows odd values - a negative average, or nothing on the line charts.",
        cause: "Too little data yet. Release status is not-available until the window opens, and an average over one interview is meaningless.",
        fix: "Nothing. These settle as interviews accrue over the following daily runs." },
      { symptom: "A number here disagrees with a number someone calculated locally.",
        cause: "A local build reads whatever files are on that machine, which may be weeks stale.",
        fix: "Always quote the published dashboard. Local builds are for development only." }
    ],

    // ---- honest limitations. Stated in the product so nobody discovers them by being wrong in a meeting.
    limits: [
      ["The Connect funnel is the least live part.", "Interview data refreshes from HQ and OCS every day. The Connect leg depends on a credential that has broken before, and when it does the funnel silently falls back to the last good snapshot - invitation and claim numbers can be older than the interview numbers beside them."],
      ["“Per-cohort finish - so far” understates finishing.", "It counts schedules the programme has not finished rolling out as unfinished, and does so slightly more often for multi-cohort workers. The offered-only figure beside it is the fair like-for-like rate. Read both."],
      ["The survival ladder is not a single funnel.", "Each row has its own eligible pool, so a later interview can show a higher share than an earlier one when short-schedule cohorts leave the pool. Compare each row to its own count."],
      ["The dotted-line rule is a heuristic.", "A subgroup's line is dotted while it is inside its expected rollout window, computed from the design. A late-firing interview can make a line look settled while it is still rolling out. Two subgroups whose real schedule cannot be derived have their end date pinned from the Cohort Tracker."],
      ["Word counts measure effort, not quality.", "Average FLW words counts words in the worker's own messages. It says nothing about whether an answer was accurate, relevant or deep."],
      ["Cross-arm totals are not the sum of the arms.", "A worker can appear in more than one arm, so per-arm counts add up to more than the number of people. Quote the subgroup or overall total, not a sum of arms."],
      ["The render has a hard size limit.", "The platform caps the dashboard file at 512 KB, so the payload is pruned to the keys the interface reads. A new chart may require pruning something else first."]
    ],
    glossary: [
      ["FLW", "Front-line worker - the community health worker being interviewed. One person, even if they appear in several cohorts."],
      ["Cohort", "One recruited group in one place, with its own id. The smallest unit the programme runs."],
      ["Subgroup", "A family of cohorts sharing an interview design, e.g. the panel group or an A/B arm."],
      ["Arm", "The A or B side of an experiment. Arms roll up to one experiment for reporting."],
      ["Topic", "The subject of a single interview, e.g. bed net usage. Identified by a short code."],
      ["Interview slot", "One position in a cohort’s schedule: interview 3 of 13. A slot exists whether or not it happened."],
      ["Design", "The ordered list of topics a cohort should receive, plus the cadence between them."],
      ["Cadence", "Intended days between interviews. Varies by subgroup, which is why time-based rules are cadence-relative."],
      ["Triggered", "The bot OFFERED the interview. Recorded as a form in CommCare."],
      ["Initiated", "The FLW started participating in the study at all."],
      ["Claimed", "The FLW took up the opportunity in Connect - the last step before interviewing."],
      ["Session", "One conversation in OCS: one FLW, one interview, start to finish."],
      ["LLO", "Local learning organisation - the partner running delivery on the ground."],
      ["Gate", "An automated check that stops the build. Nothing publishes with a failing gate."]
    ]
  };

  // Numbers quoted anywhere in the documentation come from HERE - read out of the live DATA object at
  // render time. Nothing about scale is written as a literal, so the docs cannot describe a dashboard
  // that no longer exists.
  function liveFacts() {
    var c = DATA.counts || {}, SD = DATA.subgroupDesign || {}, sgs = Object.keys(SD);
    var lens = sgs.map(function (s) { return (SD[s].topics || []).length; });
    var cads = sgs.map(function (s) { return SD[s].cadence; }).filter(function (x) { return x; });
    return {
      today: DATA.today || "", built: DATA.built_at || "",
      flws: c.flws, cohorts: c.cohorts, rows: c.master_rows, started: c.started, completed: c.completed,
      subgroups: sgs.length, sgList: sgs,
      topics: Object.keys(DATA.topicNames || {}).length,
      minLen: lens.length ? Math.min.apply(null, lens) : 0,
      maxLen: lens.length ? Math.max.apply(null, lens) : 0,
      minCad: cads.length ? Math.min.apply(null, cads) : 0,
      maxCad: cads.length ? Math.max.apply(null, cads) : 0,
      unmapped: (DATA.unmappedCohorts || []).length,
      designs: sgs.map(function (s) { return s + ": " + (SD[s].topics || []).length + " interviews every " + SD[s].cadence + "d"; })
    };
  }

  // ---- Markdown export. llms.txt-style (llmstxt.org): plain Markdown, one H1, stable H2 sections and a
  // trailing Optional block a model can drop, so the whole context pastes into an LLM in one go.
  function docsMarkdown(section) {
    var F = liveFacts(), L = [], all = section === "all";
    function h(n, t) { L.push("\n" + Array(n + 1).join("#") + " " + t + "\n"); }
    L.push("# Connect Interviews Dashboard - how it works");
    L.push("\n> Generated from the live dashboard on " + F.today + " (build " + F.built + ").");
    L.push("> Every figure is read from the published payload at generation time, not copied by hand.");
    L.push("\n**Scale right now:** " + F.flws + " unique FLWs · " + F.cohorts + " cohorts · " + F.subgroups +
      " subgroups · " + F.topics + " topics · " + F.rows + " FLW×interview rows · " +
      F.started + " interviews started · " + F.completed + " completed.");
    L.push("\n**Interview designs vary**, which is why nearly every rule is relative rather than absolute: " +
      "schedules run from " + F.minLen + " to " + F.maxLen + " interviews at " + F.minCad + "-" + F.maxCad + " day cadences.\n");
    L.push("- " + F.designs.join("\n- "));
    L.push("\n**Reading order:** what a cohort is and how one is created → how the data flows → what each " +
      "tab shows → what each indicator means → what to do when something looks wrong.\n");

    if (all || section === "opportunity") {
      h(2, "Creating a cohort (the opportunity)");
      L.push(DOCS.opportunity.note + "\n");
      L.push("Variants:");
      DOCS.opportunity.variants.forEach(function (v) { L.push("- **" + v[0] + "** - " + v[1]); });
      DOCS.opportunity.steps.forEach(function (s) {
        h(3, "Step " + s.n + " - " + s.title + "  (" + s.where + ")");
        s.items.forEach(function (i) { L.push("- " + i); });
        L.push("\n_Why:_ " + s.why);
        if (s.gotcha) L.push("_Watch out:_ " + s.gotcha);
      });
    }
    if (all || section === "onboarding") {
      h(2, "Adding that cohort to Labs");
      L.push("Ten places, in order. They are separate on purpose: the pull scripts decide what is " +
        "downloaded, the build decides what is read, and the gates refuse to run on a half-configured subgroup.\n");
      DOCS.onboarding.forEach(function (s) {
        L.push("**Step " + s.n + " - " + s.title + "**  \n_File:_ `" + s.file + "`  \n" + s.what +
          (s.gotcha && s.gotcha !== "-" ? "  \n⚠ " + s.gotcha : "") + "\n");
      });
      h(3, "Shortcuts, and when they are safe");
      DOCS.shortcuts.forEach(function (s) {
        L.push("**" + s.name + "**  \n_Use when:_ " + s.when + "  \n_How:_ " + s.how + "  \n_Risk:_ " + s.risk + "\n");
      });
    }
    if (all || section === "flow") {
      h(2, "Where the data comes from");
      L.push("Five upstream systems, pulled to local files, joined into one row per FLW per interview, " +
        "aggregated, checked by three independent gates, then embedded in the dashboard file.\n");
      DOCS.layers.forEach(function (ly) {
        h(3, ly.label);
        L.push("_" + ly.note + "_\n");
        DOCS.nodes.filter(function (n) { return n.layer === ly.id; }).forEach(function (n) {
          L.push("**" + n.label + "** - produces: " + n.owns);
          L.push("- What: " + n.what);
          L.push("- Why it matters: " + n.why + "\n");
        });
      });
      h(3, "Connections");
      DOCS.edges.forEach(function (e) {
        var a = DOCS.nodes.filter(function (n) { return n.id === e[0]; })[0];
        var b = DOCS.nodes.filter(function (n) { return n.id === e[1]; })[0];
        if (a && b) L.push("- " + a.label + " → " + b.label + (e[2] ? " (" + e[2] + ")" : ""));
      });
    }
    if (all || section === "tabs") {
      h(2, "What each tab shows");
      DOCS.tabs.forEach(function (t) {
        h(3, t.name);
        L.push("**Answers:** " + t.question + "  \n**Reads payload keys:** " + t.reads.join(", ") + "\n");
        t.charts.forEach(function (c) { L.push("- **" + c[0] + "** - " + c[1]); });
      });
    }
    if (all || section === "metrics") {
      h(2, "Every indicator, and how it is calculated");
      L.push("`Base` is the denominator. The single most common reason two figures look contradictory is " +
        "that they use different bases, so it is stated for every one.\n");
      var groups = [];
      DOCS.metrics.forEach(function (m) { if (groups.indexOf(m.g) < 0) groups.push(m.g); });
      groups.forEach(function (g) {
        h(3, g);
        DOCS.metrics.filter(function (m) { return m.g === g; }).forEach(function (m) {
          L.push("**" + m.name + "**  \n_Where:_ " + m.where + "  \n_How:_ " + m.how +
            "  \n_Base:_ " + m.base + (m.gotcha && m.gotcha !== "-" ? "  \n_Read with care:_ " + m.gotcha : "") + "\n");
        });
      });
    }
    if (all || section === "trouble") {
      h(2, "When a number looks wrong");
      L.push("Each of these has actually happened.\n");
      DOCS.troubleshooting.forEach(function (t) {
        L.push("**Symptom:** " + t.symptom + "  \n_Cause:_ " + t.cause + "  \n_Fix:_ " + t.fix + "\n");
      });
      h(3, "Known limitations");
      DOCS.limits.forEach(function (l) { L.push("- **" + l[0] + "** " + l[1]); });
    }
    if (all || section === "glossary") {
      h(2, "Glossary");
      DOCS.glossary.forEach(function (g) { L.push("- **" + g[0] + "** - " + g[1]); });
    }
    if (all) {
      h(2, "Optional");
      L.push("Detail a reader can skip on a first pass, kept separate so an LLM can drop it to save context.\n");
      L.push("- **Payload keys in this build:** " + Object.keys(DATA).sort().join(", "));
      L.push("- **Subgroups present:** " + F.sgList.join(", "));
      L.push("- **Unmapped cohorts (should be 0):** " + F.unmapped);
      L.push("- The dashboard EMBEDS its data rather than querying live, because a live multi-cohort pull " +
        "exceeds the platform request timeout and returns nothing.");
      L.push("- The render file is capped at 512 KB by the platform, so the payload is pruned of keys the " +
        "interface never reads.");
      L.push("- Test-flagged cohorts and known test accounts are excluded from every figure.");
    }
    return L.join("\n") + "\n";
  }

  function dlText(text, name, mime) {
    var blob = new Blob([text], { type: mime || "text/markdown;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
  }

  // small presentational helpers, so every section looks the same
  function docCard(title, sub, children, accent) {
    return (
      <div className="rounded border border-gray-200 bg-white px-3 py-3" style={accent ? { borderLeft: "3px solid " + accent } : {}}>
        <div className="text-sm font-semibold text-gray-800">{title}</div>
        {sub ? <p className="text-xs text-gray-600 mt-0.5 mb-2">{sub}</p> : <div className="mb-2"></div>}
        {children}
      </div>
    );
  }
  function docStep(n, title, where, items, why, gotcha, accent) {
    return (
      <div key={String(n) + title} className="flex gap-2 mb-3">
        <div className="flex-shrink-0 rounded-md text-white font-bold flex items-center justify-center"
          style={{ width: "22px", height: "22px", fontSize: "10px", background: accent || "#1565C0" }}>{n}</div>
        <div style={{ minWidth: 0 }}>
          <div className="text-xs font-semibold text-gray-800">
            {title}{where ? <span className="ml-1 text-gray-400 font-normal">· {where}</span> : null}
          </div>
          {items.map(function (it, i) { return <div key={i} className="text-xs text-gray-700 mt-0.5">- {it}</div>; })}
          {why ? <div className="text-xs text-gray-600 mt-1"><b>Why:</b> {why}</div> : null}
          {gotcha ? <div className="text-xs mt-0.5" style={{ color: "#b45309" }}><b>Watch out:</b> {gotcha}</div> : null}
        </div>
      </div>
    );
  }


  // ---- DRIFT GUARD. Be honest about what is and is not automatic here:
  //   AUTOMATIC  - every number, the subgroup roster, the designs, the payload-key list. These are read
  //                from DATA on load, so a data refresh updates them with no human action.
  //   NOT AUTOMATIC - the prose. Adding a tab, renaming a chart or changing how a metric is computed does
  //                not update the words describing it.
  // So rather than claim the docs self-maintain, this compares what they DOCUMENT against what the
  // dashboard actually HAS and shows any gap in the tab. Silent staleness becomes visible staleness.
  function docsCoverage() {
    var present = TABS.map(function (t) { return t[0]; });
    var documented = DOCS.tabs.map(function (t) { return t.id; });
    var undocumentedTabs = present.filter(function (id) { return documented.indexOf(id) < 0; });
    var staleTabs = documented.filter(function (id) { return present.indexOf(id) < 0; });
    // payload keys the docs say a tab reads, vs what the payload actually carries
    var referenced = {};
    DOCS.tabs.forEach(function (t) { (t.reads || []).forEach(function (k) { referenced[k] = 1; }); });
    var META = { today: 1, built_at: 1, counts: 1, subgroupDesign: 1, topicNames: 1, topicQuestions: 1,
                 unmappedCohorts: 1, connectPendingSubgroups: 1, flwMatrixCohorts: 1, flwMatrixOrder: 1,
                 flwMatrixOrderW: 1, cohortSG: 1 };
    var unreferenced = Object.keys(DATA).filter(function (k) { return !referenced[k] && !META[k]; });
    var ghosts = Object.keys(referenced).filter(function (k) {
      return k !== "everything (read-only)" && Object.keys(DATA).indexOf(k) < 0;
    });
    return { undocumentedTabs: undocumentedTabs, staleTabs: staleTabs,
             unreferenced: unreferenced, ghosts: ghosts,
             ok: !undocumentedTabs.length && !staleTabs.length && !unreferenced.length && !ghosts.length };
  }

  // ---- KPI cross-check. The headline figures with their UNITS spelled out, plus the arithmetic that
  // reconciles the per-subgroup roster to the unique-person total. Two different units (people vs
  // interviews) and one genuine double-count are the three things people trip over.
  function kpiCrossCheck() {
    var c = DATA.counts || {}, cf = DATA.connectFunnel || [], ce = (DATA.cohortEngagement || {}).ALL || {};
    var rows = cf.map(function (r) { return { sg: r.sg, flws: r.started, done: r.completed }; });
    var sumFlws = rows.reduce(function (a, r) { return a + (r.flws || 0); }, 0);
    var unique = ce.total_started || 0;
    return { rows: rows, n: rows.length, sumFlws: sumFlws, unique: unique,
             dup: sumFlws - unique, triggered: c.flws, notStarted: (c.flws || 0) - unique,
             ivStarted: c.started, ivCompleted: c.completed, rows_master: c.master_rows, cohorts: c.cohorts };
  }

  function renderDocs() {
    var F = liveFacts();
    var SEC = [["kpi", "0 · Numbers & cross-check"], ["opportunity", "1 · Create a cohort"],
               ["onboarding", "2 · Add it to Labs"], ["flow", "3 · Data flow"],
               ["tabs", "4 · Tabs & charts"], ["metrics", "5 · Indicators"],
               ["trouble", "6 · Troubleshooting"], ["glossary", "7 · Glossary"]];
    var K = kpiCrossCheck(), COV = docsCoverage();
    // ---- diagram geometry. One ROW per layer; nodes are laid out from the node list, so adding a node
    // cannot break the picture. Connectors are ORTHOGONAL (down, across, down) with arrowheads rather
    // than long bezier swoops - with 16 edges the curves crossed each other and were unreadable.
    var W = 1180, ROW = 132, PAD = 40, NH = 62, TOP = 34;
    var pos = {};
    DOCS.layers.forEach(function (ly, li) {
      var ns = DOCS.nodes.filter(function (n) { return n.layer === ly.id; });
      var nw = Math.min(212, (W - 2 * PAD - (ns.length - 1) * 16) / ns.length);
      var gap = ns.length > 1 ? (W - 2 * PAD - ns.length * nw) / (ns.length - 1) : 0;
      ns.forEach(function (n, i) {
        pos[n.id] = { x: PAD + i * (nw + gap), y: TOP + li * ROW, w: nw, h: NH, color: ly.color, row: li };
      });
    });
    var H = TOP + DOCS.layers.length * ROW - 30;
    var sel = docNode ? DOCS.nodes.filter(function (n) { return n.id === docNode; })[0] : null;
    var lit = {};
    if (sel) DOCS.edges.forEach(function (e) { if (e[0] === sel.id || e[1] === sel.id) { lit[e[0]] = 1; lit[e[1]] = 1; } });

    function wrap(txt, per) {
      var out = [], line = "";
      String(txt).split(" ").forEach(function (w) {
        if ((line + " " + w).trim().length > per) { out.push(line.trim()); line = w; } else { line += " " + w; }
      });
      if (line.trim()) out.push(line.trim());
      return out;
    }

    return (
      <div className="space-y-3">
        {/* ---------- header */}
        <div className="rounded border border-indigo-200 bg-indigo-50 px-3 py-2">
          <div className="text-sm font-semibold text-gray-800 mb-1">How this dashboard works, end to end</div>
          <p className="text-xs text-gray-700">
            Written for someone who has never seen the pipeline. Sections are in the order things actually
            happen: create a cohort, wire it into Labs, then how the data reaches each chart. Every number
            on this page is read from the live data when the page loads, so it cannot describe a version
            that no longer exists.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-gray-800">
            <span><b>{Number(F.flws).toLocaleString()}</b> unique FLWs</span>
            <span><b>{F.cohorts}</b> cohorts</span>
            <span><b>{F.subgroups}</b> subgroups</span>
            <span><b>{F.topics}</b> topics</span>
            <span><b>{Number(F.rows).toLocaleString()}</b> FLW×interview rows</span>
            <span><b>{Number(F.started).toLocaleString()}</b> started</span>
            <span><b>{Number(F.completed).toLocaleString()}</b> completed</span>
            <span className="text-gray-500">data as of <b>{F.today}</b></span>
          </div>
          <p className="text-xs text-gray-600 mt-1">
            Schedules run from <b>{F.minLen}</b> to <b>{F.maxLen}</b> interviews at <b>{F.minCad}</b>-<b>{F.maxCad}</b> day
            cadences, which is why nearly every rule here is <i>relative to the cohort</i> rather than a fixed number.
          </p>
        </div>

        {/* ---------- export */}
        <div className="rounded border border-gray-200 bg-white px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-gray-700">Export:</span>
            <button className="px-2.5 py-1 text-xs rounded-md border border-indigo-300 bg-indigo-50 hover:bg-indigo-100 text-indigo-800 font-medium"
              onClick={function () { dlText(docsMarkdown("all"), "interviews-dashboard-documentation.md"); }}>
              ↓ Everything (Markdown)
            </button>
            <button className="px-2.5 py-1 text-xs rounded-md border border-gray-300 hover:bg-gray-100"
              onClick={function () { dlText(docsMarkdown(docSec), "interviews-docs-" + docSec + ".md"); }}>
              ↓ This section only
            </button>
            <button className="px-2.5 py-1 text-xs rounded-md border border-gray-300 hover:bg-gray-100"
              onClick={function () { dlText(JSON.stringify({ generated: F.today, built_at: F.built, scale: F, docs: DOCS }, null, 1), "interviews-dashboard-documentation.json", "application/json"); }}>
              ↓ Structured JSON
            </button>
            <button className="px-2.5 py-1 text-xs rounded-md border border-gray-300 hover:bg-gray-100"
              onClick={function () {
                var t = docsMarkdown("all");
                if (navigator.clipboard) { navigator.clipboard.writeText(t); setDocCopied(true); setTimeout(function () { setDocCopied(false); }, 2200); }
              }}>
              {docCopied ? "✓ copied" : "⧉ Copy all"}
            </button>
          </div>
          <p className="text-gray-500 mt-1" style={{ fontSize: "10px" }}>
            Plain Markdown with stable headings, so it can be pasted straight into a model as project
            context - it carries the lineage, every indicator with its denominator, both onboarding
            checklists and the troubleshooting guide. The full file ends with an <i>Optional</i> section an
            LLM can drop to save context. JSON is the same content for programmatic use.
          </p>
        </div>

        {/* ---------- section nav */}
        <div className="flex flex-wrap items-center gap-2 px-1">
          {SEC.map(function (s) { return <span key={s[0]}>{subBtn(docSec, s[0], setDocSec, s[1])}</span>; })}
        </div>

        {/* ---------- 0. NUMBERS & CROSS-CHECK */}
        {docSec === "kpi" ? (
          <div className="space-y-3">
            {docCard("The headline numbers, with their units",
              "Two different units and one genuine double-count are what make these look contradictory. Everything below is read live, so the dashboard can be checked against it at any time.",
              <div>
                <table className="w-full" style={{ fontSize: "11px" }}>
                  <tbody>
                    <tr className="border-b border-gray-100"><td className="py-1 text-gray-700">Unique FLWs who started at least one interview</td>
                      <td className="py-1 text-right font-bold text-gray-900">{Number(K.unique).toLocaleString()}</td><td className="py-1 pl-2 text-gray-400">people</td></tr>
                    <tr className="border-b border-gray-100"><td className="py-1 text-gray-700">FLWs triggered (offered at least one interview)</td>
                      <td className="py-1 text-right font-bold text-gray-900">{Number(K.triggered).toLocaleString()}</td><td className="py-1 pl-2 text-gray-400">people</td></tr>
                    <tr className="border-b border-gray-100"><td className="py-1 text-gray-700">Interviews started</td>
                      <td className="py-1 text-right font-bold text-gray-900">{Number(K.ivStarted).toLocaleString()}</td><td className="py-1 pl-2 text-gray-400">interviews</td></tr>
                    <tr className="border-b border-gray-100"><td className="py-1 text-gray-700">Interviews completed</td>
                      <td className="py-1 text-right font-bold text-gray-900">{Number(K.ivCompleted).toLocaleString()}</td><td className="py-1 pl-2 text-gray-400">interviews</td></tr>
                    <tr className="border-b border-gray-100"><td className="py-1 text-gray-700">FLW x interview rows behind every figure</td>
                      <td className="py-1 text-right font-bold text-gray-900">{Number(K.rows_master).toLocaleString()}</td><td className="py-1 pl-2 text-gray-400">rows</td></tr>
                    <tr><td className="py-1 text-gray-700">Cohorts / subgroups</td>
                      <td className="py-1 text-right font-bold text-gray-900">{K.cohorts} / {K.n}</td><td className="py-1 pl-2 text-gray-400">groups</td></tr>
                  </tbody>
                </table>
                <div className="mt-2 rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-gray-800">
                  <b>People are not interviews.</b> {Number(K.unique).toLocaleString()} people did{" "}
                  {Number(K.ivStarted).toLocaleString()} interviews, because each person does several, so those
                  two figures must never be compared with each other. Separately, {K.notStarted} FLW{K.notStarted === 1 ? " was" : "s were"}{" "}
                  offered an interview but never started one, which is why the triggered count is slightly
                  higher than the started count.
                </div>
              </div>, "#1565C0")}

            {docCard("All " + K.n + " subgroups, and why they add to more than the total",
              "The full roster. Each row counts PEOPLE who started at least one interview in that subgroup.",
              <div>
                <table className="w-full" style={{ fontSize: "11px" }}>
                  <thead><tr className="text-gray-500" style={{ fontSize: "9.5px" }}>
                    <th className="text-left py-1">Subgroup</th><th className="text-right py-1">FLWs started</th>
                    <th className="text-right py-1">FLWs completed</th><th className="text-left py-1 pl-3">Its design</th></tr></thead>
                  <tbody>
                    {K.rows.map(function (r) {
                      var d = (DATA.subgroupDesign || {})[r.sg] || {};
                      return (
                        <tr key={r.sg} className="border-t border-gray-100">
                          <td className="py-0.5 font-semibold text-gray-800">{r.sg}</td>
                          <td className="py-0.5 text-right text-gray-800">{Number(r.flws).toLocaleString()}</td>
                          <td className="py-0.5 text-right text-gray-600">{Number(r.done).toLocaleString()}</td>
                          <td className="py-0.5 pl-3 text-gray-500">{(d.topics || []).length} interviews, every {d.cadence}d</td>
                        </tr>
                      );
                    })}
                    <tr className="border-t-2 border-gray-300 font-bold">
                      <td className="py-1 text-gray-900">Sum of all {K.n} subgroups</td>
                      <td className="py-1 text-right text-gray-900">{Number(K.sumFlws).toLocaleString()}</td>
                      <td className="py-1"></td><td className="py-1"></td>
                    </tr>
                    <tr>
                      <td className="py-0.5 text-gray-700">Unique people</td>
                      <td className="py-0.5 text-right font-bold text-gray-900">{Number(K.unique).toLocaleString()}</td>
                      <td className="py-0.5"></td><td className="py-0.5"></td>
                    </tr>
                    <tr>
                      <td className="py-0.5" style={{ color: "#b45309" }}>Counted in more than one subgroup</td>
                      <td className="py-0.5 text-right font-bold" style={{ color: "#b45309" }}>{Number(K.dup).toLocaleString()}</td>
                      <td className="py-0.5"></td><td className="py-0.5"></td>
                    </tr>
                  </tbody>
                </table>
                <div className="mt-2 rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-gray-800">
                  <b>Do not sum the subgroups.</b> The {K.n} rows add to {Number(K.sumFlws).toLocaleString()} but there
                  are only {Number(K.unique).toLocaleString()} people, a difference of {Number(K.dup).toLocaleString()},
                  because the same worker is often recruited into more than one subgroup and is counted in
                  each. Quote a subgroup figure, or the overall total, never a sum of arms.
                </div>
              </div>, "#7B1FA2")}

            {docCard("Is this page up to date?",
              "Being straight about what maintains itself and what does not.",
              <div>
                <div className="text-xs text-gray-700 mb-1">
                  <b>Updates itself:</b> every number, the subgroup roster, the designs and the payload-key
                  list are read from the live data each time this page loads, so a daily data refresh updates
                  them with nobody touching anything.
                </div>
                <div className="text-xs text-gray-700 mb-2">
                  <b>Does not update itself:</b> the written explanations. If a chart is renamed, or a metric
                  changes how it is calculated, the words here do not know. So this check compares what the
                  page documents against what the dashboard actually has:
                </div>
                {COV.ok ? (
                  <div className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1.5 text-xs text-gray-800">
                    <b>In sync.</b> All {TABS.length} tabs are documented, and every payload key the data
                    carries is claimed by a documented tab. No drift detected.
                  </div>
                ) : (
                  <div className="rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-gray-800">
                    <b>Drift detected, this page needs an edit:</b>
                    {COV.undocumentedTabs.length ? <div>- Tabs that exist but are not documented: {COV.undocumentedTabs.join(", ")}</div> : null}
                    {COV.staleTabs.length ? <div>- Documented tabs that no longer exist: {COV.staleTabs.join(", ")}</div> : null}
                    {COV.unreferenced.length ? <div>- Payload keys no documented tab claims to read: {COV.unreferenced.join(", ")}</div> : null}
                    {COV.ghosts.length ? <div>- Docs reference payload keys that are gone: {COV.ghosts.join(", ")}</div> : null}
                  </div>
                )}
                <div className="text-gray-500 mt-1" style={{ fontSize: "10px" }}>
                  What this cannot check: whether a written definition still matches the code that computes
                  it. That still needs a person to update the words when a calculation changes.
                </div>
              </div>, "#2E7D32")}
          </div>
        ) : null}


        {/* ---------- 1. CREATE A COHORT */}
        {docSec === "opportunity" ? docCard(
          "Creating a cohort - the opportunity",
          DOCS.opportunity.note,
          <div>
            <div className="flex flex-wrap gap-2 mb-2">
              {DOCS.opportunity.variants.map(function (v) {
                return (
                  <div key={v[0]} className="rounded border border-gray-200 bg-gray-50 px-2 py-1" style={{ maxWidth: "48%" }}>
                    <div className="text-xs font-semibold text-gray-800">{v[0]}</div>
                    <div className="text-xs text-gray-600">{v[1]}</div>
                  </div>
                );
              })}
            </div>
            {DOCS.opportunity.steps.map(function (s) {
              return docStep(s.n, s.title, s.where, s.items, s.why, s.gotcha, "#00695C");
            })}
            <div className="rounded border border-amber-300 bg-amber-50 px-2 py-1.5 text-xs text-gray-800">
              <b>The one step that changes the dashboard most:</b> the lookup table in step 2. That table IS the
              interview design - Labs reads it to learn a cohort’s topics, their order and their spacing, which
              is what defines “finished” and therefore every completion and drop-off percentage shown here.
              The dashboard currently reads these designs:
              <div className="mt-1">{F.designs.map(function (d) { return <div key={d}>• {d}</div>; })}</div>
              If a cohort’s row above does not match the Cohort Tracker, fix the lookup table - not the dashboard.
            </div>
          </div>, "#00695C") : null}

        {/* ---------- 2. ADD IT TO LABS */}
        {docSec === "onboarding" ? docCard(
          "Adding that cohort to Labs",
          "Ten places, in the order you should do them. They are separate on purpose: the pull scripts decide what gets downloaded, the build decides what gets read, and the gates refuse to run on a half-configured subgroup.",
          <div>
            {DOCS.onboarding.map(function (s) {
              return docStep(s.n, s.title, s.file !== "-" ? s.file : "", [s.what], "", s.gotcha !== "-" ? s.gotcha : "", "#7B1FA2");
            })}
            <div className="text-sm font-semibold text-gray-700 mt-3 mb-1">Shortcuts, and when each is safe</div>
            {DOCS.shortcuts.map(function (s) {
              return (
                <div key={s.name} className="mb-2 pl-2" style={{ borderLeft: "3px solid #2E7D32" }}>
                  <div className="text-xs font-semibold text-gray-800">{s.name}</div>
                  <div className="text-xs text-gray-700"><b>Use when:</b> {s.when}</div>
                  <div className="text-xs text-gray-700"><b>How:</b> {s.how}</div>
                  <div className="text-xs" style={{ color: "#b45309" }}><b>Risk:</b> {s.risk}</div>
                </div>
              );
            })}
            {F.unmapped
              ? <div className="mt-2 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-gray-800">
                  <b>{F.unmapped} cohort(s) are unmapped right now</b> - their data exists but no subgroup pattern
                  matches, so they are excluded from every rollup. That is step 4.
                </div>
              : <div className="mt-2 rounded border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs text-gray-700">
                  ✓ No unmapped cohorts right now - every cohort in the data resolves to a subgroup.
                </div>}
          </div>, "#7B1FA2") : null}

        {/* ---------- 3. DATA FLOW */}
        {docSec === "flow" ? (
          <div className="rounded border border-gray-200 bg-white px-3 py-3" style={{ borderLeft: "3px solid #1565C0" }}>
            <div className="text-sm font-semibold text-gray-800">The whole pipeline, end to end</div>
            <p className="text-xs text-gray-600 mt-0.5 mb-2">
              Read top to bottom. <b>Click any box</b> for what it produces and why it exists - every connection
              touching it is highlighted, so you can trace where a number came from or what a change would affect.
            </p>
            <div style={{ overflowX: "auto" }}>
              <svg viewBox={"0 0 " + W + " " + H} style={{ width: "100%", minWidth: "860px", height: "auto" }}>
                <defs>
                  <marker id="docarrow" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="5" markerHeight="5" orient="auto">
                    <path d="M0,1 L6,4 L0,7 z" fill="#94a3b8" />
                  </marker>
                  <marker id="docarrowOn" viewBox="0 0 8 8" refX="6" refY="4" markerWidth="5.5" markerHeight="5.5" orient="auto">
                    <path d="M0,1 L6,4 L0,7 z" fill="#1f2937" />
                  </marker>
                </defs>
                {DOCS.layers.map(function (ly, li) {
                  return (
                    <g key={ly.id}>
                      <rect x="0" y={TOP + li * ROW - 20} width={W} height={NH + 34} rx="4"
                        fill={li % 2 ? "#f8fafc" : "#ffffff"} stroke="#f1f5f9" />
                      <text x="4" y={TOP + li * ROW - 7} fill={ly.color} style={{ fontSize: "10.5px", fontWeight: 700 }}>{ly.label}</text>
                    </g>
                  );
                })}
                {DOCS.edges.map(function (e, i) {
                  var a = pos[e[0]], b = pos[e[1]];
                  if (!a || !b) return null;
                  var x1 = a.x + a.w / 2, y1 = a.y + a.h, x2 = b.x + b.w / 2, y2 = b.y - 6;
                  var on = sel && (e[0] === sel.id || e[1] === sel.id);
                  var midY = y1 + (y2 - y1) * 0.55;
                  // orthogonal: straight down, across on a shared lane, then down into the target
                  var d = Math.abs(x1 - x2) < 3
                    ? "M" + x1 + "," + y1 + " L" + x2 + "," + y2
                    : "M" + x1 + "," + y1 + " L" + x1 + "," + midY + " L" + x2 + "," + midY + " L" + x2 + "," + y2;
                  return (
                    <g key={"e" + i} opacity={sel && !on ? 0.22 : 1}>
                      <path d={d} fill="none" stroke={on ? "#1f2937" : "#94a3b8"} strokeWidth={on ? 2 : 1.1}
                        markerEnd={on ? "url(#docarrowOn)" : "url(#docarrow)"} />
                      {on && e[2]
                        ? <text x={(x1 + x2) / 2} y={midY - 4} textAnchor="middle" fill="#374151" style={{ fontSize: "9px" }}>{e[2]}</text>
                        : null}
                    </g>
                  );
                })}
                {DOCS.nodes.map(function (n) {
                  var p = pos[n.id], on = sel && n.id === sel.id, near = lit[n.id] && !on;
                  var nameLines = wrap(n.label, Math.floor(p.w / 6.4));
                  var ownLines = wrap(n.owns, Math.floor(p.w / 5.2)).slice(0, 2);
                  return (
                    <g key={n.id} onClick={function () { setDocNode(docNode === n.id ? null : n.id); }} style={{ cursor: "pointer" }}
                      opacity={sel && !on && !near ? 0.45 : 1}>
                      <rect x={p.x} y={p.y} width={p.w} height={p.h} rx="6"
                        fill={on ? p.color : "#ffffff"} stroke={on || near ? p.color : "#cbd5e1"} strokeWidth={on ? 2.2 : near ? 1.8 : 1} />
                      {nameLines.slice(0, 2).map(function (ln, k) {
                        return <text key={k} x={p.x + p.w / 2} y={p.y + 16 + k * 12} textAnchor="middle"
                          fill={on ? "#ffffff" : "#111827"} style={{ fontSize: "10.5px", fontWeight: 600 }}>{ln}</text>;
                      })}
                      {ownLines.map(function (ln, k) {
                        return <text key={"o" + k} x={p.x + p.w / 2} y={p.y + 16 + nameLines.slice(0, 2).length * 12 + 11 + k * 10}
                          textAnchor="middle" fill={on ? "#e0e7ff" : "#6b7280"} style={{ fontSize: "8.6px" }}>{ln}</text>;
                      })}
                    </g>
                  );
                })}
              </svg>
            </div>
            {sel ? (
              <div className="mt-2 rounded px-3 py-2 bg-gray-50" style={{ borderLeft: "4px solid " + pos[sel.id].color }}>
                <div className="text-sm font-semibold text-gray-800">{sel.label}</div>
                <div className="text-gray-500 mb-1" style={{ fontSize: "10px" }}>Produces: {sel.owns}</div>
                <p className="text-xs text-gray-700"><b>What it does.</b> {sel.what}</p>
                <p className="text-xs text-gray-700 mt-1"><b>Why it exists.</b> {sel.why}</p>
                <button className="text-indigo-600 hover:underline mt-1" style={{ fontSize: "10px" }}
                  onClick={function () { setDocNode(null); }}>clear selection</button>
              </div>
            ) : (
              <p className="text-gray-500 mt-1" style={{ fontSize: "10px" }}>
                Nothing selected - click a box. The small text inside each box is what that step produces.
              </p>
            )}
            <Legend title="Two design choices worth knowing">
              <div><b>The join comes first.</b> One row per FLW per interview slot is built before anything is
                summarised, and every tab is an aggregate of those rows. That is why two numbers here cannot
                disagree - they are different summaries of one table, not separate queries.</div>
              <div><b>Nothing publishes past a failing gate.</b> Three checks run after the build, one of which
                re-derives the headline numbers from the raw sources using entirely separate code. If the two
                disagree, the run stops rather than shipping.</div>
            </Legend>
          </div>
        ) : null}

        {/* ---------- 4. TABS */}
        {docSec === "tabs" ? docCard(
          "What each tab is for",
          "Each tab answers one question. If you are looking for a number, this tells you which tab owns it.",
          <div>
            {DOCS.tabs.map(function (t) {
              return (
                <div key={t.id} className="mb-2 rounded border border-gray-100 bg-gray-50 px-2 py-1.5">
                  <div className="text-xs font-semibold text-gray-800">{t.name}</div>
                  <div className="text-xs text-gray-600 mb-1">Answers: <i>{t.question}</i></div>
                  {t.charts.map(function (c, i) {
                    return <div key={i} className="text-xs text-gray-700">• <b>{c[0]}</b> - {c[1]}</div>;
                  })}
                  <div className="text-gray-400 mt-1" style={{ fontSize: "9px" }}>payload keys: {t.reads.join(", ")}</div>
                </div>
              );
            })}
          </div>, "#0277BD") : null}

        {/* ---------- 5. INDICATORS */}
        {docSec === "metrics" ? docCard(
          "Every indicator, and the logic behind it",
          "Base is the denominator. If two figures ever look contradictory, the cause is almost always that they use different bases - so it is stated for every single one.",
          <div>
            {(function () {
              var gs = [];
              DOCS.metrics.forEach(function (m) { if (gs.indexOf(m.g) < 0) gs.push(m.g); });
              return gs.map(function (g) {
                return (
                  <div key={g} className="mb-3">
                    <div className="text-xs font-bold text-white inline-block rounded px-1.5 py-0.5 mb-1" style={{ background: "#0277BD" }}>{g}</div>
                    {DOCS.metrics.filter(function (m) { return m.g === g; }).map(function (m) {
                      return (
                        <div key={m.name} className="mb-2 rounded border border-gray-100 px-2 py-1.5">
                          <div className="flex items-baseline justify-between gap-2">
                            <div className="text-xs font-semibold text-gray-800">{m.name}</div>
                            <div className="text-gray-400 text-right" style={{ fontSize: "9px" }}>{m.where}</div>
                          </div>
                          <div className="text-xs text-gray-700 mt-0.5"><b>How:</b> {m.how}</div>
                          <div className="text-xs text-gray-700"><b>Base (denominator):</b> {m.base}</div>
                          {m.gotcha && m.gotcha !== "-"
                            ? <div className="text-xs mt-0.5" style={{ color: "#b45309" }}><b>Read with care:</b> {m.gotcha}</div>
                            : null}
                        </div>
                      );
                    })}
                  </div>
                );
              });
            })()}
          </div>, "#0277BD") : null}

        {/* ---------- 6. TROUBLESHOOTING */}
        {docSec === "trouble" ? (
          <div className="space-y-3">
            {docCard("When a number looks wrong",
              "Every entry below is a failure that has actually happened on this dashboard.",
              <div>
                {DOCS.troubleshooting.map(function (t, i) {
                  return (
                    <div key={i} className="mb-2 rounded border border-gray-100 px-2 py-1.5">
                      <div className="text-xs font-semibold text-gray-800">{t.symptom}</div>
                      <div className="text-xs text-gray-700 mt-0.5"><b>Cause:</b> {t.cause}</div>
                      <div className="text-xs" style={{ color: "#1b7f3b" }}><b>Fix:</b> {t.fix}</div>
                    </div>
                  );
                })}
              </div>, "#D84315")}
            {docCard("Known limitations",
              "Stated here so nobody discovers them by being wrong in a meeting.",
              <div>
                {DOCS.limits.map(function (l, i) {
                  return (
                    <div key={i} className="mb-1.5 text-xs">
                      <span className="font-semibold text-gray-800">{l[0]}</span>{" "}
                      <span className="text-gray-700">{l[1]}</span>
                    </div>
                  );
                })}
              </div>, "#b45309")}
          </div>
        ) : null}

        {/* ---------- 7. GLOSSARY */}
        {docSec === "glossary" ? docCard(
          "Glossary",
          "Plain definitions for the words used throughout the dashboard.",
          <div>
            {DOCS.glossary.map(function (g) {
              return (
                <div key={g[0]} className="mb-1.5 text-xs">
                  <span className="font-semibold text-gray-800">{g[0]}</span>
                  <span className="text-gray-700"> - {g[1]}</span>
                </div>
              );
            })}
            <div className="text-xs font-semibold text-gray-800 mt-3 mb-1">Subgroups and their designs in this build</div>
            <div className="text-xs text-gray-700">{F.designs.map(function (d) { return <div key={d}>• {d}</div>; })}</div>
          </div>, "#546E7A") : null}
      </div>
    );
  }

  // ---- Cohort Engagement (3-panel) helpers + charts ----
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmtWk(iso) { var p = iso.split("-"); return MON[parseInt(p[1], 10) - 1] + " " + parseInt(p[2], 10); }
  // Manual value labels (no datalabels plugin is available in the Labs render env).
  function barTopLabels(color) {
    return { afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx, meta = chart.getDatasetMeta(0);
      ctx.save(); ctx.fillStyle = color; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      meta.data.forEach(function (el, i) { var v = chart.data.datasets[0].data[i]; if (v == null) return; ctx.fillText(v, el.x, el.y - 3); });
      ctx.restore();
    } };
  }
  function linePointLabels() {
    return { afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx; ctx.save(); ctx.font = "bold 10px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      chart.data.datasets.forEach(function (ds, di) {
        var meta = chart.getDatasetMeta(di); if (meta.hidden) return; ctx.fillStyle = ds.borderColor;
        meta.data.forEach(function (el, i) { var v = ds.data[i]; if (v == null) return; ctx.fillText(v + "%", el.x, el.y - 6); });
      });
      ctx.restore();
    } };
  }
  function stackedSegLabels() {
    return { afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx; ctx.save(); ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = "#fff";
      chart.data.datasets.forEach(function (ds, di) {
        var meta = chart.getDatasetMeta(di);
        meta.data.forEach(function (el, i) { var v = ds.data[i]; if (!v || v < 15) return; if (Math.abs(el.base - el.y) < 14) return; ctx.fillText(v, el.x, (el.y + el.base) / 2); });
      });
      ctx.restore();
    } };
  }
  // opaque white background so exported PNGs aren't transparent
  var whiteBg = { beforeDraw: function (chart) { var ctx = chart.ctx; ctx.save(); ctx.globalCompositeOperation = "destination-over"; ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, chart.width, chart.height); ctx.restore(); } };
  // the engagement series for the current cohort + LLO filter ("all" -> whole cohort; else the LLO split)
  function engData(sg, llo) {
    if (llo && llo !== "all") return ((DATA.cohortEngagementLLO || {})[sg] || {})[llo];
    return (DATA.cohortEngagement || {})[sg];
  }
  // The cohort's ACTIVE WINDOW = weeks up to the last one where >= thrPct% of its started FLWs were newly
  // active (new starts + new finishes). Trims the long trailing trickle so a completed cohort doesn't read
  // as a big inactive drop-off tail (Neal's external-sharing concern). Adapts per cohort; still-running
  // cohorts keep their full length.
  function activeEndIdx(ce, thrPct) {
    var st = ce.started, fin = ce.finished, N = st.length, tot = st[N - 1] || 1;
    var thr = Math.max(2, (thrPct / 100) * tot), last = 0;
    for (var n = 1; n < N; n++) { if ((st[n] - st[n - 1]) + (fin[n] - fin[n - 1]) >= thr) last = n; }
    // The final point is an "as of today" stub, not a full week - build_payload_agg appends the data's
    // last date, which is typically 1-6 days after the previous week-end. Measured against a FULL-WEEK
    // threshold it almost never qualifies, which silently froze the right-hand edge one period behind:
    // PANEL charted 83 FLWs finished while the true current figure was 85, so the chart and the KPI
    // tile above it disagreed on the same screen (Andrea, 2026-08-13).
    // Include that stub ONLY when it directly continues the active window (last === N-2). The slice is
    // contiguous, so pulling in the final point of a long-finished cohort would drag every dead week
    // between along with it - measured: a single late TRS finish would have re-expanded its window from
    // 7 weeks back to the full 19, which is precisely the inactive tail the trimming exists to remove.
    if (N >= 2 && last === N - 2 && (st[N - 1] - st[N - 2]) + (fin[N - 1] - fin[N - 2]) > 0) last = N - 1;
    // keep >= 2 points, but never index past the last week: a 1-week series (every newly onboarded
    // cohort passes through one, and per-LLO splits are shorter than the parent) would otherwise
    // return 1 for N===1 and blow up the whole render at full.weeks[aEnd].
    return Math.min(Math.max(last, 1), Math.max(N - 1, 0));
  }
  // ALL is a special case. Thresholding the AGGREGATE series is wrong for it: the cutoff is a % of the
  // WHOLE population (2% of ~1,400 FLWs ~= 28 newly active per week), which a small late-starting
  // cohort can never reach on its own. That cut the ALL active window at 2026-07-14 while PANEL was
  // active to 08-11 and EXT to 08-12, hiding 5 weeks of real activity (reported by Mansi 2026-08-13).
  // The programme is active for as long as ANY cohort is, so take the LATEST per-cohort active end and
  // map that date back onto the ALL week axis. Week labels are ISO dates, so string compare is safe.
  function activeEndIdxAll(CE, thrPct) {
    var all = CE["ALL"];
    if (!all || !all.weeks || !all.weeks.length) return 0;
    var latest = "";
    Object.keys(CE).forEach(function (k) {
      var c = CE[k];
      if (k === "ALL" || !c || !Array.isArray(c.weeks) || !c.weeks.length) return;
      var e = c.weeks[activeEndIdx(c, thrPct)];
      if (e && e > latest) latest = e;
    });
    if (!latest) return activeEndIdx(all, thrPct);
    for (var i = 0; i < all.weeks.length; i++) { if (all.weeks[i] >= latest) return i; }
    return all.weeks.length - 1;
  }
  // Active-window end for whatever is selected: per-cohort normally, any-cohort-active for ALL.
  function activeEndFor(sg, ce, thrPct) {
    return sg === "ALL" ? activeEndIdxAll(DATA.cohortEngagement || {}, thrPct) : activeEndIdx(ce, thrPct);
  }
  // Return a copy of an engagement series sliced to weeks [0..endIdx].
  function sliceCe(ce, endIdx) {
    var keys = ["weeks", "started", "finished_pct", "steady_pct", "incons_pct", "drop_pct",
      "waiting_pct", "inprog_pct", "rhythm_base", "finished", "new", "active", "slow", "quiet",
      "waiting"];
    var out = Object.assign({}, ce);
    keys.forEach(function (k) { if (Array.isArray(ce[k])) out[k] = ce[k].slice(0, endIdx + 1); });
    return out;
  }
  // In FULL-timeline mode, mark where the active window ended (dashed line + greyed tail) so the trailing
  // weeks read as "post-active", not drop-off. Not drawn in active-window mode (there is no tail).
  function activePeriodMarker(fullCe, endIdx) {
    return { afterDraw: function (chart) {
      if (endIdx == null || endIdx >= fullCe.weeks.length - 1) return;
      var x = chart.scales.x.getPixelForValue(endIdx), ca = chart.chartArea, ctx = chart.ctx;
      ctx.save();
      ctx.fillStyle = "rgba(107,114,128,0.10)"; ctx.fillRect(x, ca.top, ca.right - x, ca.bottom - ca.top);
      ctx.strokeStyle = "#6b7280"; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(x, ca.top); ctx.lineTo(x, ca.bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = "#6b7280"; ctx.font = "10px sans-serif"; ctx.textAlign = "left";
      ctx.fillText("◀ active window", x + 4, ca.top + 10);
      ctx.restore();
    } };
  }
  // Download the 3 engagement panels stacked into one white PNG (c-suite-ready).
  function downloadEngPng() {
    var cs = [eng1Ref.current, eng2Ref.current, eng3Ref.current].filter(Boolean);
    if (!cs.length) return;
    var pad = 18, gap = 22, title = 34;
    var w = Math.max.apply(null, cs.map(function (c) { return c.width; }));
    var h = cs.reduce(function (a, c) { return a + c.height; }, 0) + gap * (cs.length - 1) + pad * 2 + title;
    var out = document.createElement("canvas"); out.width = w + pad * 2; out.height = h;
    var ctx = out.getContext("2d");
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, out.width, out.height);
    var lloTag = engLlo !== "all" ? " · " + engLlo : "";
    ctx.fillStyle = "#111827"; ctx.font = "bold 16px sans-serif";
    ctx.fillText("Cohort Engagement - " + engSg + lloTag + "  (as of " + (DATA.today || "") + ")", pad, 24);
    var y = title + pad;
    cs.forEach(function (c) { ctx.drawImage(c, pad, y); y += c.height + gap; });
    var a = document.createElement("a"); a.download = "cohort_engagement_" + engSg + (engLlo !== "all" ? "_" + engLlo : "") + ".png"; a.href = out.toDataURL("image/png"); a.click();
  }

  React.useEffect(function () {
    if (activeTab !== "funnels" || funView !== "engagement" || !window.Chart) return;
    [eng1Inst, eng2Inst, eng3Inst].forEach(function (r) { if (r.current) { r.current.destroy(); r.current = null; } });
    var full = engData(engSg, engLlo);
    if (!full) return;
    var aEnd = activeEndFor(engSg, full, engThr);
    var ce = engWin === "active" ? sliceCe(full, aEnd) : full;
    var labels = ce.weeks.map(fmtWk), gt = ce.gap_thresh;
    // Full timeline is CLEAN by default. The dashed boundary + greyed tail is now opt-in (engMark),
    // because "Full timeline" reading as "the whole timeline, unannotated" is what people expect and
    // the marker was being read as part of the data (Mansi, 2026-08-13). The annotation still exists
    // for the case it was built for - explaining why a finished cohort has a long flat tail.
    var apm = activePeriodMarker(full, engWin === "full" && engMark ? aEnd : null);
    if (eng1Ref.current) {
      eng1Inst.current = new window.Chart(eng1Ref.current.getContext("2d"), {
        type: "bar",
        data: { labels: labels, datasets: [{ label: "FLWs started", data: ce.started, backgroundColor: "#1565C0", maxBarThickness: 70 }] },
        options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 18 } },
          plugins: { legend: { display: false },
            title: { display: true, text: engSg + ": cumulative FLWs who started interviewing, by week" },
            subtitle: { display: true, text: "FLWs appearing in the interview data; additional FLWs were invited but never started", color: "#6b7280", font: { style: "italic", size: 11 } },
            tooltip: { callbacks: { label: function (c) { return "Started: " + c.parsed.y; } } } },
          scales: { y: { beginAtZero: true, title: { display: true, text: "FLWs started" } } } },
        plugins: [barTopLabels("#1565C0"), whiteBg, apm]
      });
    }
    if (eng2Ref.current) {
      eng2Inst.current = new window.Chart(eng2Ref.current.getContext("2d"), {
        type: "line",
        data: { labels: labels, datasets: [
          // ---- OUTCOME: where each starter ended up. These four sum to 100.
          { label: "Finished: completed all interviews", data: ce.finished_pct, borderColor: "#5E35B1", backgroundColor: "#5E35B1" },
          // Dropped is no longer a flat 14-day silence rule. It asks whether an interview THIS FLW was
          // actually sent went past its deadline (released, plus one interview gap to do it) unfinished,
          // so it means the same thing in a 3-day-gap design and a 14-day-gap one.
          { label: "Dropped off: let a due interview pass", data: ce.drop_pct, borderColor: "#C62828", backgroundColor: "#C62828" },
          { label: "Schedule not completed: did all sent, nothing more sent", data: ce.waiting_pct, borderColor: "#0277BD", backgroundColor: "#0277BD" },
          { label: "Still in progress", data: ce.inprog_pct, borderColor: "#607D8B", backgroundColor: "#607D8B" },
          // ---- RHYTHM: a SEPARATE reading over starters with 2+ interviews. These two sum to 100 on
          // their own base, which is why they are dashed - they are not part of the stack above. They
          // used to be the leftover of it, so they emptied to 0% the moment every cohort closed.
          { label: "Rhythm - steady: never a gap > " + gt + " days", data: ce.steady_pct, borderColor: "#2E7D32", backgroundColor: "#2E7D32", borderDash: [6, 4] },
          { label: "Rhythm - inconsistent: one " + (gt + 1) + "+ day gap", data: ce.incons_pct, borderColor: "#F9A825", backgroundColor: "#F9A825", borderDash: [6, 4] }
        ].map(function (d) { return Object.assign({ fill: false, tension: 0.2, borderWidth: 3, pointRadius: 3, pointHoverRadius: 6 }, d); }) },
        options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 16 } },
          // Chart.js copies each dataset's borderDash into its legend swatch, which turned the two
          // dashed rhythm entries into a row of specks that read as noise next to the solid ones. The
          // LINES stay dashed - that distinction is the point - but every legend swatch is drawn solid
          // so the key stays legible.
          plugins: { legend: { position: "bottom", labels: { boxWidth: 14, font: { size: 11 },
                generateLabels: function (chart) {
                  var items = window.Chart.defaults.plugins.legend.labels.generateLabels(chart);
                  items.forEach(function (it) { it.lineDash = []; it.lineDashOffset = 0; });
                  return items;
                } } },
            title: { display: true, text: "Outcome (solid lines, of all starters) and rhythm (dashed lines, of those with 2+ interviews)" },
            tooltip: { callbacks: { label: function (c) { return c.dataset.label.split(":")[0] + ": " + c.parsed.y + "%"; } } } },
          scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "% of started FLWs" }, ticks: { callback: function (v) { return v + "%"; } } } } },
        plugins: [linePointLabels(), whiteBg, apm]
      });
    }
    if (eng3Ref.current) {
      eng3Inst.current = new window.Chart(eng3Ref.current.getContext("2d"), {
        type: "bar",
        data: { labels: labels, datasets: [
          { label: "Finished: completed all interviews", data: ce.finished, backgroundColor: "#5E35B1" },
          { label: "Active: interview within one gap (started earlier)", data: ce.active, backgroundColor: "#2E7D32" },
          { label: "Started this week (first-ever interview)", data: ce.new, backgroundColor: "#42A5F5" },
          { label: "Slow: last interview one to two gaps ago", data: ce.slow, backgroundColor: "#F9A825" },
          { label: "Quiet: more than two gaps since last interview", data: ce.quiet, backgroundColor: "#C62828" }
        ] },
        options: { responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { boxWidth: 14, font: { size: 11 } } },
            title: { display: true, text: "Status of started FLWs at each week's end" },
            tooltip: { callbacks: { label: function (c) { return c.dataset.label.split(":")[0] + ": " + c.parsed.y; } } } },
          scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, title: { display: true, text: "FLWs" } } } },
        plugins: [stackedSegLabels(), whiteBg, apm]
      });
    }
    return function () { [eng1Inst, eng2Inst, eng3Inst].forEach(function (r) { if (r.current) { r.current.destroy(); r.current = null; } }); };
  }, [activeTab, funView, engSg, engLlo, engWin, engThr, engMark]);

  // ---- Drop-off by cohort (cross-cohort comparison) ----------------------------------------------
  // Each cohort is scored at ITS OWN end date, not at today and not at a date shared across its whole
  // design. Two things made the old figure incomparable: a flat 14-day silence rule applied to designs
  // whose interviews are 3 to 14 days apart, and a single end date per design even though TRS cohorts
  // (for example) finished up to 37 days apart.
  //
  // No day-threshold control here on purpose. Every cohort has finished, and once a cohort is over the
  // question is simply "did they complete it?" - the deadline only decides who counts as dropped WHILE
  // a cohort is still running. Three presets would therefore have produced three identical charts,
  // which teaches people the controls do not work. The default is one interview gap; a cohort needing
  // something different gets an entry in GRACE_DAYS and is flagged in the table below.
  function cohortDropRows() {
    var CD = DATA.cohortDropoff || [], SD = DATA.subgroupDesign || {}, CSGm = DATA.cohortSG || {};
    return CD.map(function (r) {
      var sg = CSGm[r.c] || "?";
      var des = SD[sg] || {};
      var ivs = (des.topics || []).length;
      // f = completed by the window end, l = completed after it, d = dropped, w = schedule never
      // fully sent, z = nothing ever sent. In-progress is the residual.
      var late = r.l || 0, never = r.z || 0;
      var prog = r.n - r.f - late - r.d - r.w - never;
      var pc = function (v) { return r.n ? Math.round(1000 * v / r.n) / 10 : null; };
      return {
        cohort: r.c, sg: sg, ivs: ivs, gap: des.cadence || null,
        grace: r.g != null ? r.g : (des.cadence || null),
        graceOverridden: r.g != null, startEstimated: !!r.x,
        start: r.s, end: r.e, closed: r.e <= (DATA.today || ""),
        n: r.n, onTime: r.f, late: late, done: r.f + late,
        drop: r.d, notSent: r.w, never: never, prog: prog,
        sent: r.ts || 0, sentDone: r.tc || 0,
        sentDonePct: r.ts ? Math.round(1000 * r.tc / r.ts) / 10 : null,
        donePct: pc(r.f + late), onTimePct: pc(r.f),
        // "of which late" is a share of the FINISHERS, not of all workers - the header says "of which".
        latePct: (r.f + late) ? Math.round(1000 * late / (r.f + late)) / 10 : null,
        dropPct: pc(r.d), notSentPct: pc(r.w), neverPct: pc(never)
      };
    });
  }

  // Roll the cohorts up to one row per design, so a reader sees both levels.
  function cohortDropByDesign(rows) {
    var by = {};
    rows.forEach(function (r) {
      var a = by[r.sg] || (by[r.sg] = { sg: r.sg, ivs: r.ivs, gap: r.gap, cohorts: 0, n: 0,
        onTime: 0, late: 0, done: 0, drop: 0, notSent: 0, never: 0, prog: 0,
        sent: 0, sentDone: 0, ends: [] });
      a.cohorts++; a.n += r.n; a.onTime += r.onTime; a.late += r.late; a.done += r.done;
      a.drop += r.drop; a.notSent += r.notSent; a.never += r.never; a.prog += r.prog;
      a.sent += r.sent; a.sentDone += r.sentDone;
      a.ends.push(r.end);
    });
    return Object.keys(by).map(function (k) {
      var a = by[k], pc = function (v) { return a.n ? Math.round(1000 * v / a.n) / 10 : null; };
      a.ends.sort();
      a.endFirst = a.ends[0]; a.endLast = a.ends[a.ends.length - 1];
      a.spread = Math.round((new Date(a.endLast) - new Date(a.endFirst)) / 86400000);
      a.donePct = pc(a.done); a.onTimePct = pc(a.onTime);
      a.latePct = a.done ? Math.round(1000 * a.late / a.done) / 10 : null;
      a.dropPct = pc(a.drop); a.notSentPct = pc(a.notSent); a.neverPct = pc(a.never);
      a.sentDonePct = a.sent ? Math.round(1000 * a.sentDone / a.sent) / 10 : null;
      return a;
    });
  }

  function renderCohortDropoff() {
    var rows = cohortDropRows();
    if (!rows.length) {
      return <div className="text-sm text-gray-500 p-3">No per-cohort drop-off data in this payload.</div>;
    }
    var byDesign = cohortDropByDesign(rows);
    var tot = rows.reduce(function (a, r) {
      a.n += r.n; a.onTime += r.onTime; a.late += r.late; a.done += r.done;
      a.drop += r.drop; a.notSent += r.notSent; a.never += r.never; a.prog += r.prog;
      a.sent += r.sent; a.sentDone += r.sentDone; return a;
    }, { n: 0, onTime: 0, late: 0, done: 0, drop: 0, notSent: 0, never: 0, prog: 0,
         sent: 0, sentDone: 0 });
    // Sorting applies to BOTH levels. By id sorts designs alphabetically and cohorts by cohort id.
    function sortRows(list, isDesign) {
      var out = list.slice();
      if (cdSort === "cohort") {
        out.sort(function (x, y) {
          var a = isDesign ? x.sg : x.cohort, b = isDesign ? y.sg : y.cohort;
          return a < b ? -1 : a > b ? 1 : 0;
        });
      } else {
        out.sort(function (x, y) { return (y.dropPct || 0) - (x.dropPct || 0); });
      }
      return out;
    }
    var shown = cdLevel === "design" ? sortRows(byDesign, true) : sortRows(rows, false);
    var estimated = rows.filter(function (r) { return r.startEstimated; }).length;
    var openN = rows.filter(function (r) { return !r.closed; }).length;
    var overridden = rows.filter(function (r) { return r.graceOverridden; });

    function pctCell(v) { return v == null ? "-" : v + "%"; }
    function bar(r) {
      // Segment widths must all be shares of the SAME base (all workers), so they sum to 100. latePct
      // is deliberately a share of finishers for the column, so recompute the segment here.
      var lateOfAll = r.n ? Math.round(1000 * r.late / r.n) / 10 : 0;
      var progOfAll = r.n ? Math.round(1000 * r.prog / r.n) / 10 : 0;
      var seg = [["#5E35B1", r.onTimePct, "Finished on time"], ["#7E57C2", lateOfAll, "Finished late"],
                 ["#C62828", r.dropPct, "Dropped off"], ["#0277BD", r.notSentPct, "Schedule not completed"],
                 ["#607D8B", progOfAll, "Still in progress"], ["#9E9E9E", r.neverPct, "Never began"]];
      return (
        <div className="flex h-4 w-full overflow-hidden rounded" title={seg.map(function (t) { return t[2] + " " + pctCell(t[1]); }).join(" / ")}>
          {seg.map(function (t, i) {
            return t[1] ? <div key={i} style={{ width: t[1] + "%", background: t[0] }} /> : null;
          })}
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 px-1">
          <span className="text-xs font-semibold text-gray-700">Show:</span>
          {subBtn(cdLevel, "design", setCdLevel, "By cohort design (" + byDesign.length + ")")}
          {subBtn(cdLevel, "cohort", setCdLevel, "Every cohort (" + rows.length + ")")}
          <span className="ml-2 text-xs font-medium text-gray-600">Sort:</span>
          {subBtn(cdSort, "drop", setCdSort, "Highest drop-off")}
          {subBtn(cdSort, "cohort", setCdSort, cdLevel === "design" ? "Design name" : "Cohort id")}
        </div>

        <div className="rounded border border-gray-200 bg-gray-50 p-3 text-xs leading-relaxed text-gray-700">
          <b>What this shows.</b> Every cohort measured at <b>its own end date</b> - the day its last
          interview stopped being open - rather than today or a date shared across its whole design.
          A worker&apos;s <b>deadline for one interview is one interview gap after it was sent</b>, so it is
          3 days in a 3-day design and 14 in a 14-day one, and means the same thing in both.
          <div className="mt-2">
            <b>Why there is no day-count control.</b> {rows.length - openN} of {rows.length} cohorts have
            finished. Once a cohort is over, &quot;did they complete it?&quot; needs no waiting period, so
            changing the number would not move these figures. It only matters while a cohort is running.
            {overridden.length
              ? <span> {overridden.length} cohort(s) run a non-default deadline: {overridden.map(function (r) { return r.cohort + " (" + r.grace + "d)"; }).join(", ")}.</span>
              : <span> No cohort currently overrides the default.</span>}
            {estimated
              ? <span> {estimated} cohort(s) have no Connect invitation date, so their start comes from
                the first interview trigger recorded; marked * below.</span>
              : null}
          </div>
        </div>

        {/* Every state spelled out, in the view. Five states, mutually exclusive, and they sum to the
            worker count - so nobody has to guess what "dropped" or "not completed" means here. */}
        <div className="rounded border border-gray-200 p-3">
          <div className="mb-2 text-xs font-semibold text-gray-700">What each column means</div>
          <div className="grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {[["Finished the design", "#5E35B1", "Did every interview in their plan - the same measure the Cohort engagement panel calls Finished. Split into on time (by their cohort's end) and late (after it); both are finishes."],
              ["Dropped off", "#C62828", "An interview WAS sent to them, its deadline passed, and they never completed it. Note this includes sessions they STARTED and abandoned part-way, not only silence - roughly 40% of these are replies that never reached the end. Leaving ONE interview undone is enough, so read it beside the sent-and-done column."],
              ["Schedule not completed", "#0277BD", "They completed everything that was ever sent to them, but their plan was never fully sent, and the cohort has since closed. Nothing is still coming. Not their doing, so kept out of drop-off."],
              ["Never began", "#9E9E9E", "Claimed the opportunity but the bot never sent them a single interview."],
              ["Still in progress", "#607D8B", "Their cohort is still running and they have a live interview in hand. Outcome not decided yet."]]
              .map(function (t, i) {
                return (
                  <div key={i} className="flex gap-2">
                    <span className="mt-1 inline-block h-2 w-2 flex-none rounded-full" style={{ background: t[1] }} />
                    <span className="text-gray-700"><b>{t[0]}.</b> {t[2]}</span>
                  </div>
                );
              })}
          </div>
          <div className="mt-2 text-xs text-gray-500">
            One row per worker per cohort, so somebody enrolled in two cohorts appears twice - once for
            each. That is why these totals are larger than the unique-worker counts elsewhere.
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {[["Finished the design", tot.done, "#5E35B1", tot.late ? tot.onTime.toLocaleString() + " on time, " + tot.late.toLocaleString() + " late" : "all on time"],
            ["Dropped off", tot.drop, "#C62828", "let a sent interview go undone"],
            ["Schedule not completed", tot.notSent, "#0277BD", "did all that was sent"],
            ["Never began", tot.never, "#9E9E9E", "nothing ever sent"],
            ["Still in progress", tot.prog, "#607D8B", "cohort still running"]]
            .map(function (t, i) {
              return (
                <div key={i} className="rounded border border-gray-200 bg-white px-3 py-2"
                     style={{ minWidth: "150px", flex: "1 1 150px", maxWidth: "260px" }}>
                  <div className="text-xs font-medium text-gray-700">{t[0]}</div>
                  <div className="text-lg font-bold" style={{ color: t[2] }}>
                    {t[1].toLocaleString()}
                    <span className="ml-1 text-xs font-normal text-gray-500">
                      {tot.n ? Math.round(100 * t[1] / tot.n) + "%" : ""}
                    </span>
                  </div>
                  <div className="text-gray-400" style={{ fontSize: "10px" }}>{t[3]}</div>
                </div>
              );
            })}
        </div>

        {/* The worker-level headline on its own reads as a collapse. Of everything actually SENT, this
            is how much got done - both are true and they belong side by side. */}
        <div className="rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-gray-700">
          <b>Read this next to the drop-off figure.</b> Of the <b>{tot.sent.toLocaleString()}</b>{" "}
          interviews actually sent across these cohorts, <b>{tot.sentDone.toLocaleString()}</b> were
          completed - <b>{tot.sent ? Math.round(1000 * tot.sentDone / tot.sent) / 10 : 0}%</b>. A worker
          counts as dropped off for leaving <i>one</i> interview undone, so a high drop-off rate and a
          high completion rate are not a contradiction: long schedules give more chances to miss one.
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-100 text-gray-700">
              <tr>
                <th className="px-2 py-1 text-left">{cdLevel === "design" ? "Cohort design" : "Cohort"}</th>
                {cdLevel === "cohort" && <th className="px-2 py-1 text-left">Design</th>}
                <th className="px-2 py-1 text-right">Ivs</th>
                <th className="px-2 py-1 text-right">Gap</th>
                <th className="px-2 py-1 text-right">Deadline</th>
                <th className="px-2 py-1 text-left">{cdLevel === "design" ? "Own end dates" : "Started"}</th>
                <th className="px-2 py-1 text-left">{cdLevel === "design" ? "Spread" : "Its own end"}</th>
                <th className="px-2 py-1 text-right">Workers</th>
                <th className="px-2 py-1 text-right">Finished</th>
                <th className="px-2 py-1 text-right">of which late</th>
                <th className="px-2 py-1 text-right">Dropped off</th>
                <th className="px-2 py-1 text-right">Schedule not completed</th>
                <th className="px-2 py-1 text-right">Never began</th>
                <th className="px-2 py-1 text-right">Of interviews sent, done</th>
                <th className="px-2 py-1 text-left" style={{ minWidth: 140 }}>Split</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(function (r, i) {
                var isD = cdLevel === "design";
                return (
                  <tr key={i} className={i % 2 ? "bg-gray-50" : ""}>
                    <td className="px-2 py-1 font-medium">
                      {isD ? r.sg : r.cohort}{!isD && r.startEstimated ? " *" : ""}
                    </td>
                    {!isD && <td className="px-2 py-1 text-gray-600">{r.sg}</td>}
                    <td className="px-2 py-1 text-right">{r.ivs || "-"}</td>
                    <td className="px-2 py-1 text-right">{r.gap ? r.gap + "d" : "-"}</td>
                    <td className="px-2 py-1 text-right">
                      {isD ? (r.gap ? r.gap + "d" : "-")
                           : <span className={r.graceOverridden ? "font-semibold text-amber-700" : ""}>{r.grace ? r.grace + "d" : "-"}</span>}
                    </td>
                    <td className="px-2 py-1 text-gray-600">{isD ? r.endFirst : r.start}</td>
                    <td className="px-2 py-1 text-gray-600">
                      {isD ? (r.spread ? r.spread + " days" : "same day") : r.end}
                    </td>
                    <td className="px-2 py-1 text-right">{r.n.toLocaleString()}</td>
                    <td className="px-2 py-1 text-right">{pctCell(r.donePct)}</td>
                    <td className="px-2 py-1 text-right text-gray-500">{r.late ? pctCell(r.latePct) : "-"}</td>
                    <td className="px-2 py-1 text-right font-semibold" style={{ color: "#C62828" }}>{pctCell(r.dropPct)}</td>
                    <td className="px-2 py-1 text-right" style={{ color: "#0277BD" }}>{pctCell(r.notSentPct)}</td>
                    <td className="px-2 py-1 text-right text-gray-500">{r.never ? pctCell(r.neverPct) : "-"}</td>
                    <td className="px-2 py-1 text-right font-medium" style={{ color: "#2E7D32" }}
                        title={r.sentDone + " of " + r.sent + " interviews sent"}>{pctCell(r.sentDonePct)}</td>
                    <td className="px-2 py-1">{bar(r)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="rounded border border-gray-200 p-3">
          {/* Collapsed by default: it explains a rule that is no longer in force, so it is reference
              rather than a daily read. The heading and its one-line summary stay visible. */}
          <button type="button" onClick={function () { setCdWhy(!cdWhy); }}
                  className="flex w-full items-start gap-2 text-left">
            <span className="mt-0.5 text-xs text-gray-500" style={{ width: "10px" }}>
              {cdWhy ? "▾" : "▸"}
            </span>
            <span>
              <span className="block text-xs font-semibold text-gray-700">
                What a fixed number of days would have meant, per design
              </span>
              <span className="block text-xs text-gray-600">
                The old rule called a worker dropped after 14 days of silence, the same 14 days in every
                design - which was not one rule but {byDesign.length} different ones.
                <span className="ml-1 text-gray-400">{cdWhy ? "Click to hide." : "Click to see the per-design breakdown."}</span>
              </span>
            </span>
          </button>
          <div className="overflow-x-auto" style={{ display: cdWhy ? "block" : "none" }}>
            <table className="min-w-full text-xs">
              <thead className="bg-gray-100 text-gray-700">
                <tr>
                  <th className="px-2 py-1 text-left">Design</th>
                  <th className="px-2 py-1 text-right">Gap</th>
                  <th className="px-2 py-1 text-right">3 days =</th>
                  <th className="px-2 py-1 text-right">7 days =</th>
                  <th className="px-2 py-1 text-right">14 days =</th>
                  <th className="px-2 py-1 text-left">In this design, 14 days meant</th>
                </tr>
              </thead>
              <tbody>
                {byDesign.slice().sort(function (x, y) { return (x.gap || 99) - (y.gap || 99); }).map(function (r, i) {
                  var f = function (d) { return r.gap ? (Math.round(10 * d / r.gap) / 10) + "x" : "-"; };
                  var note = !r.gap
                    ? "single interview - there is no next one to miss"
                    : (r.gap >= 14 ? "exactly one interview: a worker on schedule looked like a drop-out"
                      : (14 / r.gap >= 4 ? "over four missed interviews before we noticed"
                        : "about " + (Math.round(10 * 14 / r.gap) / 10) + " missed interviews"));
                  return (
                    <tr key={i} className={i % 2 ? "bg-gray-50" : ""}>
                      <td className="px-2 py-1 font-medium">{r.sg}</td>
                      <td className="px-2 py-1 text-right">{r.gap ? r.gap + "d" : "one iv"}</td>
                      <td className="px-2 py-1 text-right">{f(3)}</td>
                      <td className="px-2 py-1 text-right">{f(7)}</td>
                      <td className="px-2 py-1 text-right font-semibold">{f(14)}</td>
                      <td className="px-2 py-1 text-gray-600">{note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  function renderEngagement() {
    var CE = DATA.cohortEngagement || {};
    var sgs = (CE["ALL"] ? ["ALL"] : []).concat(SG_ORDER.filter(function (sg) { return CE[sg]; }));
    var full = engData(engSg, engLlo);
    var aEnd = full ? activeEndFor(engSg, full, engThr) : 0;
    var hasTail = full && aEnd < full.weeks.length - 1;
    var ce = full ? (engWin === "active" ? sliceCe(full, aEnd) : full) : null;
    // Windowed vs current finished count. A trimmed cohort legitimately charts a lower final bar
    // than the KPI tile shows, and comparing the two was exactly the confusion reported on
    // 2026-08-13 (chart 83 vs actual 85). State both numbers rather than leaving it to be inferred.
    var finWin = ce && ce.finished ? ce.finished[ce.finished.length - 1] : 0;
    var finNow = full && full.finished ? full.finished[full.finished.length - 1] : 0;
    var scope = (engSg === "ALL" ? "all cohorts" : engSg) + (engLlo !== "all" ? " · " + engLlo : "");
    return (
      <React.Fragment>
        <div className="flex flex-wrap items-center gap-2 px-1">
          <span className="text-xs font-medium text-gray-600">Cohort:</span>
          {sgs.map(function (sg) { return <span key={sg}>{subBtn(engSg, sg, setEngSg, sg === "ALL" ? "All cohorts" : sg)}</span>; })}
          <span className="mx-1 text-gray-300">|</span>
          <span className="text-xs font-medium text-gray-600">LLO:</span>
          {[["all", "Both"], ["COWACDI", "COWACDI"], ["EHA", "EHA"]].map(function (o) { return <span key={o[0]}>{subBtn(engLlo, o[0], setEngLlo, o[1])}</span>; })}
          {ce ? <button onClick={downloadEngPng} title="Download all 3 panels as one PNG" className="ml-auto px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-100">↓ PNG</button> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 px-1">
          {/* Hide these controls when they cannot do anything, rather than leaving dead buttons that
              look broken when clicked.
              - No tail (active window already reaches the last week) => Active/Full render an identical
                chart and the marker has nothing to mark. True right now for All cohorts, PANEL, ABT3-A,
                2WT and EXT, i.e. anything still active in the latest week.
              - All cohorts => the window is derived from the LATEST per-cohort active end, so it is the
                last week at every cutoff (verified at Tight/Standard/Loose); the cutoff cannot move it
                either, so that control goes too. */}
          {hasTail ? (
            <React.Fragment>
              <span className="text-xs font-medium text-gray-600">Window:</span>
              {subBtn(engWin, "active", setEngWin, "Active window")}
              {subBtn(engWin, "full", setEngWin, "Full timeline")}
              {engWin === "full" ? (
                <label className="flex items-center gap-1 text-gray-600 cursor-pointer" style={{ fontSize: "11px" }}
                       title="Draw a dashed line and shade the weeks after the active window ended. Off by default: Full timeline shows the whole period unannotated.">
                  <input type="checkbox" checked={engMark} onChange={function (e) { setEngMark(e.target.checked); }} />
                  mark active-window end
                </label>
              ) : null}
              <span className="text-gray-400" style={{ fontSize: "10px" }} title="Active window = weeks where enough FLWs were still newly starting or finishing. Full timeline shows the trailing weeks too.">ℹ</span>
              <span className="mx-1 text-gray-300">|</span>
              <span className="text-xs font-medium text-gray-600">Cutoff:</span>
              {[[1, "Tight"], [2, "Standard"], [5, "Loose"]].map(function (o) { return <span key={o[0]}>{subBtn(engThr, o[0], setEngThr, o[1])}</span>; })}
              <span className="text-gray-400" style={{ fontSize: "10px" }}>min {engThr}%/wk newly active</span>
            </React.Fragment>
          ) : (
            <span className="text-gray-500" style={{ fontSize: "11px" }}
                  title="There is nothing to trim: this selection was still active in the most recent week, so the chart already covers the whole period. The Active window / Full timeline choice would produce an identical chart, so it is hidden.">
              Showing the full period - {engSg === "ALL" ? "at least one cohort" : engSg} was still active in the latest week, so there are no inactive weeks to trim.
            </span>
          )}
        </div>
        {!ce ? (
          <div className="text-sm text-gray-500 px-2 py-6">No engagement data for {scope} yet{engLlo !== "all" ? " (this cohort has no " + engLlo + " FLWs)" : ""}.</div>
        ) : (function () {
          // KPIs + banner numbers = current state (from the FULL series); the CHARTS use the windowed view.
          var nf = full.weeks.length - 1;
          var started = full.total_started, finished = full.finished_pct[nf], drop = full.drop_pct[nf];
          var activeNow = full.active[nf];
          var endTxt = full.weeks[aEnd] ? fmtWk(full.weeks[aEnd]) : "";   // guarded; was an inline copy of fmtWk
          // These four tiles are CURRENT STATE (full series). The charts below may be windowed to an
          // earlier week, so each tile states its own as-of date. Without that, the tile and the last
          // point of the chart read as two answers to one question: PANEL showed 12% here and 9% on
          // the chart, and on TRE the same pair is 92% vs 71% (Andrea, 2026-08-13).
          var asOf = DATA.today ? " · as of " + fmtWk(DATA.today) : "";
          // Waiting and rhythm read the same index as the other tiles. Rhythm sits on its own base
          // (starters with 2+ interviews), so the tile states that base rather than implying it is a
          // share of everyone - and says "not measurable" when a design gives nobody a second
          // interview to compare against, instead of showing a misleading 0%.
          var waitPctNow = full.waiting_pct ? full.waiting_pct[nf] : null;
          var rBase = full.rhythm_base ? full.rhythm_base[nf] : 0;
          var steadyNow = full.steady_pct ? full.steady_pct[nf] : null;
          var kpi = [
            { label: "Started interviewing", val: started, sub: "unique FLWs" + asOf, color: "#1565C0" },
            // For ALL this is person-level and means "finished AT LEAST ONE of their schedules" - a
            // materially more generous question than the per-design rows ask, so it says so. The
            // enrolment-level figure (the same question the drop-off view asks) sits beside it.
            { label: engSg === "ALL" ? "Finished ≥1 schedule" : "Finished",
              val: finished + "%",
              sub: (engSg === "ALL"
                ? "of " + started.toLocaleString() + " people - generous, rises with # cohorts"
                : "completed every interview in the design") + asOf, color: "#5E35B1" },
            { label: "Active now", val: activeNow, sub: "interviewed within one gap" + asOf, color: "#2E7D32" },
            { label: "Dropped off", val: drop + "%", sub: "let a due interview pass" + asOf, color: "#C62828" },
            { label: "Schedule not completed", val: (waitPctNow == null ? "-" : waitPctNow + "%"),
              sub: "did all sent, nothing more sent" + asOf, color: "#0277BD" },
            ...(full.enrol_base ? [{
              label: "Finished the design",
              val: (full.enrol_finished_pct ? full.enrol_finished_pct[nf] : "-") + "%",
              sub: "of " + (full.enrol_base[nf] || 0).toLocaleString()
                + " enrolments - the per-design question" + asOf, color: "#4527A0" }] : []),
            { label: "Steady rhythm", val: (rBase ? steadyNow + "%" : "not measurable"),
              sub: (rBase
                ? "of " + rBase.toLocaleString() + (full.rhythm_pooled ? " enrolments" : "") + " with 2+ interviews"
                : "needs 2+ interviews") + asOf, color: "#2E7D32" }
          ];
          // Windowed reading of the same two headline metrics, for the reconciliation note below.
          var dropWin = ce.drop_pct ? ce.drop_pct[ce.drop_pct.length - 1] : drop;
          var finPctWin = ce.finished_pct ? ce.finished_pct[ce.finished_pct.length - 1] : finished;
          var windowLags = engWin === "active" && hasTail && (dropWin !== drop || finPctWin !== finished);
          return (
            <React.Fragment>
              <div className="text-xs bg-indigo-50 border border-indigo-100 rounded px-3 py-2 text-gray-700">
                {engSg === "ALL" ? (
                  <span><b>Program-wide roll-up.</b> <b>{started}</b> FLWs have started interviewing across all cohorts; <b>{finished}%</b> have <b>finished</b> their whole schedule and <b>{drop}%</b> dropped off, meaning an interview they were sent went past its deadline unfinished. For a further <b>{waitPctNow}%</b> the <b>schedule was not completed</b>: they did everything sent to them, but their plan was never fully sent. Cohorts run different-length schedules, so read this as the recruitment + completion picture; for one cohort's engagement detail, pick it above.</span>
                ) : (
                  <span><b>Read this as recruitment + engagement, not attrition.</b> Of <b>{started}</b> FLWs who started interviewing in {scope}, <b>{finished}%</b> <b>finished</b> all their interviews and <b>{activeNow}</b> are active right now. <b>{drop}%</b> dropped off, meaning an interview they were sent went past its deadline (one interview gap after it was sent) unfinished, and for <b>{waitPctNow}%</b> the <b>schedule was not completed</b> - they did everything sent and nothing more was sent. A dip in the retention curve is mostly <i>finishers</i>, <i>later starts</i> and <i>slower cadence</i> - not people quitting.{engWin === "active" && hasTail ? <span> <b>The tiles above are as of {fmtWk(DATA.today)}; the charts below stop at ~{endTxt}</b> (the active window).{windowLags ? <span> So the charts end on <b>{finPctWin}% finished / {dropWin}% dropped</b> while the current figures are <b>{finished}% / {drop}%</b> - the gap is activity in the trimmed weeks, not two different measures.</span> : null} Switch to Full timeline for the complete series.</span> : null}</span>
                )}
              </div>
              <div className="flex flex-wrap gap-2 px-1">
                {kpi.map(function (k) {
                  return (
                    <div key={k.label} className="rounded border border-gray-200 bg-white px-3 py-2" style={{ minWidth: "130px" }}>
                      <div className="text-lg font-bold" style={{ color: k.color }}>{k.val}</div>
                      <div className="text-xs font-medium text-gray-700">{k.label}</div>
                      <div className="text-gray-400" style={{ fontSize: "10px" }}>{k.sub}</div>
                    </div>
                  );
                })}
              </div>
              <div style={{ height: "260px" }}><canvas ref={eng1Ref}></canvas></div>
              <div style={{ height: "300px" }}><canvas ref={eng2Ref}></canvas></div>
              <div style={{ height: "300px" }}><canvas ref={eng3Ref}></canvas></div>
              <Legend title="How to read these three panels">
                <div><b>Panel 1 - recruitment:</b> cumulative FLWs who have started interviewing (appeared in the interview data). Not invited counts.</div>
                <div><b>Panel 2 - two separate readings.</b> The <b>solid</b> lines are the <b>outcome</b> and cover every starter: <b>Finished</b> (completed all their interviews), <b>Dropped off</b> (an interview they were sent went past its deadline - one gap after it was sent - unfinished), <b>Schedule not completed</b> (they did everything sent to them, but their plan was never fully sent, so the schedule stopped rather than they did), and <b>Still in progress</b>. Those four sum to 100%. The <b>dashed</b> lines are <b>rhythm</b> and answer a different question - of the starters with two or more interviews, how many kept a steady pace (never a gap &gt; {ce.gap_thresh} days). Those two sum to 100% on their own base, so they are not part of the stack above. <b>Rhythm is a one-way ratchet</b> - a single long gap moves an FLW to Inconsistent permanently. Rhythm uses the largest gap between interviews, not time since the last one, so a finisher does not drift into Inconsistent as the calendar moves.{ce.rhythm_pooled ? <span> On <b>All cohorts</b> the rhythm figure is <b>pooled from the individual designs</b> rather than recomputed on a merged history, so it can never disagree with them; its base counts <b>enrolments</b> (an FLW in two cohorts has two rhythms), which is why it can exceed the unique-FLW count above.</span> : null}</div>
                <div><b>Panel 3 - status now:</b> where every starter stands at each week's end - Finished, Active (within one interview gap), New this week, Slow (one to two gaps), Quiet (more than two gaps). The bands are gap MULTIPLES, so they mean the same thing at any cadence. Totals equal Panel 1 by construction.</div>
                <div className="text-gray-400">x-axis is the week-ending date. <b>Active window</b> trims the trailing weeks once fewer than the cutoff ({engThr}%) of the cohort's FLWs are newly starting/finishing per week - so a completed cohort isn't shown as a long inactive tail; <b>Full timeline</b> shows the whole period, Apr through today, unannotated - tick “mark active-window end” if you want the boundary drawn. For <b>ALL cohorts</b> the active window runs as long as ANY cohort is still active, so it reaches close to today while individual finished cohorts trim earlier. {engSg === "ALL" ? ce.gap_thresh + "-day gap threshold (program-wide default - cohorts here have mixed cadences)" : ce.gap_thresh + " = 2× the " + engSg + " interview cadence"}. Dropped off no longer uses any silence window: it asks whether an interview the FLW was SENT went past its deadline unfinished, and that deadline is one interview gap - so it too scales with the cohort's pace.</div>
              </Legend>
            </React.Fragment>
          );
        })()}
      </React.Fragment>
    );
  }

  function subBtn(cur, val, set, label) {
    var on = cur === val;
    return (
      <button onClick={function () { set(val); }}
        className={"px-3 py-1.5 text-sm rounded-md font-medium " + (on ? "bg-indigo-100 text-indigo-700" : "text-gray-500 hover:bg-gray-100")}>
        {label}
      </button>
    );
  }

  function rgbaOf(hex, a) {
    var h = String(hex).replace("#", "");
    var r = parseInt(h.substring(0, 2), 16), g = parseInt(h.substring(2, 4), 16), b = parseInt(h.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + a + ")";
  }

  // Full OCS session link (same URL the "view ↗" links use) - for the table and CSV export.
  function sessionUrl(sid) { return sid ? "https://www.openchatstudio.com/a/Vaccine_Coach/chatbots/e/cc01d032-5931-4bdd-a4b2-6f05f4f72f88/s/" + sid + "/view/" : ""; }

  // Reusable multi-select checkbox dropdown (mirrors the mbw_monitoring column picker). Called as a
  // plain function returning JSX (like subBtn) so it holds no component state of its own - open state
  // and per-dropdown search live in the parent (openDD / ddQuery), which keeps input focus stable.
  // opts: array of strings OR {value,label}. selected: array of values ([] = All). One dropdown open at a time.
  function filterDropdown(id, label, opts, selected, setSelected) {
    var norm = opts.map(function (o) { return typeof o === "string" ? { value: o, label: o } : o; });
    var open = openDD === id;
    var q = (ddQuery[id] || "").toLowerCase();
    var shown = q ? norm.filter(function (o) { return (o.label + " " + o.value).toLowerCase().indexOf(q) >= 0; }) : norm;
    function toggle(v) { setSelected(selected.indexOf(v) >= 0 ? selected.filter(function (x) { return x !== v; }) : selected.concat([v])); setGPage(0); }
    return (
      <div key={id} className="inline-block" style={{ position: "relative" }}>
        <button onClick={function () { setOpenDD(open ? null : id); }}
          className={"inline-flex items-center gap-1.5 border rounded-md px-2 py-1.5 text-sm " + (selected.length ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-gray-300 text-gray-700 bg-white hover:bg-gray-50")}>
          {label}
          {selected.length
            ? <span className="bg-indigo-600 text-white text-xs px-1.5 py-0.5 rounded-full">{selected.length}</span>
            : <span className="text-gray-400 text-xs">All</span>}
          <span className="text-gray-400 text-xs">▾</span>
        </button>
        {open && <div style={{ position: "fixed", inset: 0, zIndex: 40 }} onClick={function () { setOpenDD(null); }}></div>}
        {open && (
          <div style={{ position: "absolute", left: 0, top: "100%", marginTop: 4, zIndex: 50, width: 250, background: "white", border: "1px solid #e5e7eb", borderRadius: 8, boxShadow: "0 10px 15px -3px rgba(0,0,0,0.1)" }}>
            {norm.length > 8 && (
              <div className="px-2 py-2 border-b border-gray-200">
                <input type="text" value={ddQuery[id] || ""} placeholder={"Search " + label.toLowerCase() + "…"}
                  onChange={function (e) { var v = e.target.value; setDdQuery(function (p) { var n = Object.assign({}, p); n[id] = v; return n; }); }}
                  className="w-full border border-gray-300 rounded px-2 py-1 text-sm" />
              </div>
            )}
            <div style={{ maxHeight: 260, overflowY: "auto" }} className="py-1">
              {shown.length ? shown.map(function (o) {
                return (
                  <label key={o.value} className="flex items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50">
                    <input type="checkbox" checked={selected.indexOf(o.value) >= 0} onChange={function () { toggle(o.value); }} className="mr-2" style={{ accentColor: "#4f46e5" }} />
                    {o.label}
                  </label>
                );
              }) : <div className="px-3 py-2 text-xs text-gray-400">No matches</div>}
            </div>
            <div className="px-3 py-2 border-t border-gray-200 flex items-center justify-between gap-2">
              <button onClick={function () { var add = shown.map(function (o) { return o.value; }).filter(function (v) { return selected.indexOf(v) < 0; }); if (add.length) { setSelected(selected.concat(add)); setGPage(0); } }} className="text-xs text-indigo-600 hover:underline font-medium">Select all</button>
              {selected.length ? <button onClick={function () { setSelected([]); setGPage(0); }} className="text-xs text-gray-500 hover:underline font-medium">Clear</button> : <span className="text-xs text-gray-400">All</span>}
            </div>
          </div>
        )}
      </div>
    );
  }

  function ivRow(key, label, iv, indent) {
    var di = deImpact && iv.started_di != null;
    var stVal = di ? iv.started_di : iv.started;
    var pstVal = di ? iv.pct_started_di : iv.pct_started;
    var changed = di && iv.started_di !== iv.started;
    return (
      <tr key={key} className="hover:bg-gray-50">
        <td className={td + " " + indent + " text-gray-500"}>{label}</td>
        <td className={td}>{iv.name}</td>
        <td className={td + " text-right"}>{iv.eligible}</td>
        <td className={td + " text-right"}>{iv.triggered}</td>
        <td className={td + " text-right text-gray-500"}>{iv.pct_trig}%</td>
        <td className={td + " text-right" + (changed ? " text-amber-700 font-medium" : "")} title={changed ? "de-impacted (raw " + iv.started + ")" : ""}>{stVal}</td>
        <td className={td + " text-right text-green-700 font-semibold"}>{pstVal}%</td>
        <td className={td + " text-right"}>{iv.completed}</td>
        <td className={td + " text-right text-green-700 font-semibold"}>{iv.pct_completed == null ? "-" : iv.pct_completed + "%"}</td>
      </tr>
    );
  }

  var c = DATA.counts;
  // Math.max.apply(null, []) is -Infinity, which is truthy - so a `|| 1` guard would NOT rescue it and
  // Array.apply(null, {length: -Infinity}) throws, blanking the whole dashboard. Check length first.
  var _ivLens = (DATA.dropoff.subgroups || []).map(function (s) { return s.interviews.length; });
  var maxIv = _ivLens.length ? Math.max.apply(null, _ivLens) : 1;
  // ---- Full Retention Table: build a flat matrix (for copy/CSV export) ----
  function retentionMatrix() {
    var cols = ["Subgroup", "Cohorts", "Invited", "Accepted", "Started Learn", "Completed Learn", "Claimed", "FLW Reg", "# Initiated"];
    for (var k = 1; k <= maxIv; k++) {
      ["Topic", "Eligible", "Triggered", "% Trig", "Started", "% Started", "Completed", "% Compl", "Overall completed %"].forEach(function (h) { cols.push("I" + k + " " + h); });
    }
    var rows = [cols];
    DATA.dropoff.subgroups.forEach(function (s) {
      var cn = s.connect, byN = {};
      s.interviews.forEach(function (iv) { byN[iv.n] = iv; });
      var r = [s.sg, s.cohorts_n, cn.invited, cn.accepted, cn.learn_started, cn.learn_completed, cn.claimed, cn.flw_reg, cn.initiated];
      for (var k = 1; k <= maxIv; k++) {
        var iv = byN[k];
        if (!iv) { r.push("", "", "", "", "", "", "", "", ""); }
        else { r.push(iv.topic, iv.eligible, iv.triggered, iv.pct_trig, iv.started, iv.pct_started, iv.completed, iv.pct_completed == null ? "" : iv.pct_completed, iv.pct_completed_base == null ? "" : iv.pct_completed_base); }
      }
      rows.push(r);
    });
    return rows;
  }
  function copyRetention() {
    var t = retentionMatrix().map(function (r) { return r.join("\t"); }).join("\n");
    if (navigator.clipboard) navigator.clipboard.writeText(t);
  }
  function downloadRetention() {
    var csv = retentionMatrix().map(function (r) {
      return r.map(function (c) { var s = String(c); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(",");
    }).join("\n");
    var blob = new Blob([csv], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "full_retention_table.csv"; a.click();
  }

  // ---- Granular CSV export (same Blob idiom as downloadRetention; opens directly in Excel) ----
  function csvCell(c) { var s = String(c == null ? "" : c); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function dlCsv(rows, name) {
    var csv = rows.map(function (r) { return r.map(csvCell).join(","); }).join("\n");
    var blob = new Blob([csv], { type: "text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
  }
  function sessCsvRows(list) {
    var rows = [["connect_id", "cohort_id", "interview", "status", "created", "session_link"]];
    list.forEach(function (r) {
      rows.push([r.connect_id, sessionCohort(r) || "", r.interview || "", r.completed ? "Completed" : (r.started ? "Started" : "-"), r.created_at || "", sessionUrl(r.session_id)]);
    });
    return rows;
  }
  function matCsvRows(list) {
    var rows = [["connect_id", "cohort", "subgroup"].concat(MTOPICS)];
    list.forEach(function (r) {
      var topics = SUBGROUP_DESIGN[r.g] || [], cb = {};
      topics.forEach(function (t, i) { cb[t] = r.s[i]; });
      var row = [r.f, r.c, r.g];
      // cb[t] == null (not `t in cb`): if a design gains a topic before the matrix builder catches up,
      // the key exists with an undefined value and `in` would let it through as the string "undefined".
      MTOPICS.forEach(function (t) { row.push(cb[t] == null ? "" : STATE_LABEL[STATES[cb[t]]]); });
      rows.push(row);
    });
    return rows;
  }
  // filtered=true -> exactly what's on screen (all active filters + search); false -> the full dataset.
  function exportGranular(filtered) {
    var d = new Date().toISOString().slice(0, 10);
    if (gView === "matrix") dlCsv(matCsvRows(filtered ? matFiltered : FM), "interviews_matrix_" + (filtered ? "filtered" : "all") + "_" + d + ".csv");
    else dlCsv(sessCsvRows(filtered ? sessSorted : sessSource), "interviews_sessions_" + (filtered ? "filtered" : "all") + "_" + d + ".csv");
  }

  // ---- Granular: ALL live OCS sessions (from the pipeline prop, not embedded) + client-side search/paging ----
  function liveRows(alias) { var p = props.pipelines; return (p && p[alias] && p[alias].rows) || []; }
  var ocsLive = liveRows("sessions");
  // (FLW × Topic links, item D) map "connect_id|interview" -> OCS session id, from the live pipeline.
  // Lets each matrix cell link to its session with zero embed-size cost; empty if pipeline not loaded.
  var sessByKey = {};
  ocsLive.forEach(function (r) {
    var cid = r.connect_id || r.username || "";
    var iv = (r.interview == null || r.interview === "") ? "" : String(r.interview);
    var sid = r.id || r.matched_session_id || "";
    if (cid && iv && sid && !sessByKey[cid + "|" + iv]) sessByKey[cid + "|" + iv] = sid;
  });
  var sessSource = ocsLive.length
    ? ocsLive.map(function (r) {
        var iv = r.interview, stt = r.interview_status || "";
        return {
          connect_id: r.connect_id || r.username || "", interview: (iv == null || iv === "") ? "" : String(iv),
          started: !!(iv != null && iv !== ""), completed: stt === "interview_complete",
          created_at: (r.created_at || "").slice(0, 10), session_id: r.id || r.matched_session_id || "",
          cohort_id: r.cohort_id || "",   // exact cohort the bot recorded in the OCS session state
        };
      })
    : DATA.granular.map(function (r) {
        return { connect_id: r.connect_id, interview: r.topic_code, started: r.is_started,
          completed: r.is_completed, created_at: "", session_id: r.session_id, cohort_id: r.cohort_id || "" };
      });
  var gq = gSearch.trim().toLowerCase();
  // ---- per-(FLW × cohort) × topic matrix + a connect_id lookup for filtering both tables ----
  // flwMatrix arrives compact (payload-size trim): flwMatrixV2 = one string per unique FLW,
  //   "<f>|<cohortIdx>:<stateDigits>[u]|<cohortIdx>:<stateDigits>[u]…"
  // cohortIdx indexes flwMatrixCohorts; stateDigits is one digit per topic; a trailing "u" is the
  // untrained flag. flwMatrixOrder[cohortIdx] is a run of fixed-width (flwMatrixOrderW) base36
  // indices into flwMatrixV2 that restores the ORIGINAL row order (the matrix table paginates and
  // exports in array order, so order is user-visible). Falls back to the old uncompressed
  // DATA.flwMatrix when flwMatrixV2 is absent, so this render works with old and new payloads.
  var FM = (function () {
    if (!DATA.flwMatrixV2) return DATA.flwMatrix || [];
    var CH = DATA.flwMatrixCohorts || [], V2 = DATA.flwMatrixV2;
    var ORD = DATA.flwMatrixOrder || [], W = DATA.flwMatrixOrderW || 3;
    var per = [];
    for (var i = 0; i < V2.length; i++) {
      var parts = V2[i].split("|"), cells = {};
      for (var j = 1; j < parts.length; j++) {
        var p = parts[j], k = p.indexOf(":");
        var body = p.slice(k + 1), u = 0;
        if (body.charAt(body.length - 1) === "u") { u = 1; body = body.slice(0, -1); }
        var st = [];
        for (var q = 0; q < body.length; q++) st.push(+body.charAt(q));
        cells[p.slice(0, k)] = { s: st, u: u };
      }
      per.push({ f: parts[0], cells: cells });
    }
    var rows = [];
    for (var ci = 0; ci < CH.length; ci++) {
      var seq = ORD[ci] || "";
      for (var off = 0; off + W <= seq.length; off += W) {
        var e = per[parseInt(seq.substr(off, W), 36)], cell = e.cells[ci];
        var row = { f: e.f, c: CH[ci], s: cell.s };
        if (cell.u) row.u = 1;
        rows.push(row);
      }
    }
    return rows;
  })();
  // topicStatusCohort arrives compressed (payload-size trim): each row is
  //   [cohort, completed, started-not-completed, available-missed-overdue, available-not-started,
  //    not-available-yet, not-triggered]
  // in a fixed APPEND-ONLY order, because seven long state names x 220 rows cost ~30 KB. Rehydrate to
  // the object shape the table expects. Falls back to the old object rows so this render works with
  // either payload vintage.
  var TSC_ORDER = ["completed", "started-not-completed", "available-missed-overdue",
    "available-not-started", "not-available-yet", "not-triggered"];
  function tscRows(code) {
    var raw = (DATA.topicStatusCohort || {})[code] || [];
    return raw.map(function (r) {
      if (!Array.isArray(r)) return r;
      var o = { cohort: r[0], total: 0 };
      TSC_ORDER.forEach(function (k, i) { o[k] = r[i + 1] || 0; o.total += o[k]; });
      return o;
    });
  }

  var CSG = DATA.cohortSG || {};   // cohort -> subgroup (flwMatrix rows drop their own g to save payload; re-derive here)
  var flwInfo = {};   // connect_id -> { g: subgroup, cohorts: {cohort:1}, u: untrained }
  var cohortSG = {};  // cohort id -> subgroup (global, for session-level subgroup filtering)
  FM.forEach(function (r) {
    if (r.g == null) r.g = CSG[r.c];   // restore subgroup on each row so all downstream r.g uses work unchanged
    var fi = flwInfo[r.f] || (flwInfo[r.f] = { g: r.g, cohorts: {}, cg: {}, u: 0 });
    fi.cohorts[r.c] = 1; fi.cg[r.c] = r.g; if (r.u) fi.u = 1;   // cg: cohort -> subgroup (topic disambiguation)
    cohortSG[r.c] = r.g;
  });
  // The FLW's cohort id(s). A live OCS session carries no cohort and an FLW can be claimed in several
  // cohorts, so this lists all (comma-joined); "" if the FLW isn't claimed.
  function cohortsFor(cid) { var fi = flwInfo[cid]; return fi ? Object.keys(fi.cohorts).sort().join(", ") : ""; }
  // Exact cohort for ONE session. Best source is the OCS session's own state (r.cohort_id - the cohort the
  // bot recorded on that session); every session from ~early May onward has it. Sessions before that predate
  // the field, so the exact cohort is simply not in the source data - for those we ONLY infer a cohort when
  // it is UNAMBIGUOUS (a single-cohort FLW, or exactly one of the FLW's cohorts runs the session's topic, or
  // a single trigger match). If it can't be pinned to exactly one, show "-" rather than a misleading list.
  var trigCohort = {};
  liveRows("triggers").forEach(function (r) {
    var cid = r.connect_id || r.username || "";
    var iv = (r.next_interview == null || r.next_interview === "") ? "" : String(r.next_interview);
    var ch = r.cohort_id || "";
    if (cid && iv && ch) { var k = cid + "|" + iv; (trigCohort[k] || (trigCohort[k] = {}))[ch] = 1; }
  });
  function sessionCohort(r) {
    if (r.cohort_id) return r.cohort_id;   // exact - from the OCS session state
    var cid = r.connect_id, iv = r.interview;
    if (iv) { var t = trigCohort[cid + "|" + iv]; var tk = t ? Object.keys(t) : []; if (tk.length === 1) return tk[0]; }
    var fi = flwInfo[cid];
    if (!fi) return "";
    var ck = Object.keys(fi.cohorts);
    if (ck.length === 1) return ck[0];   // single-cohort FLW → unambiguous for any of their sessions
    if (iv) {
      var bt = Object.keys(fi.cg).filter(function (c) { return (SUBGROUP_DESIGN[fi.cg[c]] || []).indexOf(iv) >= 0; });
      if (bt.length === 1) return bt[0];   // exactly one of the FLW's cohorts runs this topic
    }
    return "";   // multi-cohort FLW on a pre-cohort-tag session → not recoverable → "-"
  }
  var fSubgroups = SG_ORDER.filter(function (sg) { return FM.some(function (r) { return r.g === sg; }); });
  var fCohorts = Object.keys(FM.reduce(function (a, r) { a[r.c] = 1; return a; }, {})).sort();
  var MTOPICS = MATRIX_TOPIC_ORDER.filter(function (t) {
    return fSubgroups.some(function (sg) { return (SUBGROUP_DESIGN[sg] || []).indexOf(t) >= 0; });
  });
  var anyFilter = !!(fSg.length || fCo.length || fSt.length || fTr.length || fTopic.length || gq);
  function clearFilters() { setGSearch(""); setFSg([]); setFCo([]); setFSt([]); setFTr([]); setFTopic([]); setGPage(0); }
  // Sessions table: the cohort/subgroup filters match the SESSION'S OWN resolved cohort (sessionCohort),
  // so the filter and the COHORT_ID column always agree - filtering "1PE1" shows only the sessions that
  // are 1PE1, not every session of an FLW who happens to also be in 1PE1. Sessions whose exact cohort
  // isn't recoverable ("-") therefore don't match a specific cohort/subgroup filter. Trained/untrained
  // stays an FLW attribute; status/topic come from the row itself.
  var sessFiltered = sessSource.filter(function (r) {
    var sc = sessionCohort(r);
    if (gq && (r.connect_id + " " + sc + " " + r.session_id + " " + r.interview + " " + (r.completed ? "completed" : r.started ? "started" : "")).toLowerCase().indexOf(gq) < 0) return false;
    var fi = flwInfo[r.connect_id];
    if (fSg.length && fSg.indexOf(cohortSG[sc]) < 0) return false;
    if (fCo.length && fCo.indexOf(sc) < 0) return false;
    if (fTr.length && (!fi || fTr.indexOf(fi.u ? "untrained" : "trained") < 0)) return false;
    if (fTopic.length && fTopic.indexOf(String(r.interview)) < 0) return false;
    if (fSt.length) { var st = r.completed ? "completed" : (r.started ? "started-not-completed" : ""); if (fSt.indexOf(st) < 0) return false; }
    return true;
  });
  // FLW × Topic matrix rows: row-level filters; status filter = FLW has >=1 topic in that state.
  var fStIdxs = fSt.map(function (s) { return STATES.indexOf(s); }).filter(function (i) { return i >= 0; });
  var matFiltered = FM.filter(function (r) {
    if (gq && (r.f + " " + r.c).toLowerCase().indexOf(gq) < 0) return false;
    if (fSg.length && fSg.indexOf(r.g) < 0) return false;
    if (fCo.length && fCo.indexOf(r.c) < 0) return false;
    if (fTr.length && fTr.indexOf(r.u ? "untrained" : "trained") < 0) return false;
    if (fTopic.length) {
      var idxs = fTopic.map(function (t) { return (SUBGROUP_DESIGN[r.g] || []).indexOf(t); }).filter(function (i) { return i >= 0; });
      if (!idxs.length) return false;                        // subgroup runs none of the picked topics
      // any picked topic must be in any picked state (cell-level, mirrors the single-select "that topic in that state")
      if (fStIdxs.length && !idxs.some(function (i) { return fStIdxs.indexOf(r.s[i]) >= 0; })) return false;
    } else if (fStIdxs.length && !r.s.some(function (x) { return fStIdxs.indexOf(x) >= 0; })) return false;   // any topic in any picked state
    return true;
  });
  // ---- sessions sort (click a column header) ----
  function sortVal(r, key) {
    if (key === "cohort_id") return sessionCohort(r);
    if (key === "interview") { var n = Number(r.interview); return isNaN(n) ? r.interview || "" : n; }
    if (key === "status") return r.completed ? 2 : r.started ? 1 : 0;   // ordinal: completed > started > none
    if (key === "created") return r.created_at || "";
    return r.connect_id || "";
  }
  var sessSorted = gSort.key
    ? sessFiltered.slice().sort(function (a, b) {
        var va = sortVal(a, gSort.key), vb = sortVal(b, gSort.key);
        var c = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
        return gSort.dir === "asc" ? c : -c;
      })
    : sessFiltered;
  function sortTh(label, key) {
    var active = gSort.key === key;
    return (
      <th key={label} onClick={function () { setGSort(active ? { key: key, dir: gSort.dir === "asc" ? "desc" : "asc" } : { key: key, dir: key === "created" ? "desc" : "asc" }); setGPage(0); }}
        className={th + " text-left cursor-pointer select-none hover:text-indigo-600"} title="Click to sort">
        {label}<span className={"ml-1 " + (active ? "text-indigo-600" : "text-gray-300")}>{active ? (gSort.dir === "asc" ? "▲" : "▼") : "↕"}</span>
      </th>
    );
  }
  var GPAGE = 100;
  var activeLen = gView === "matrix" ? matFiltered.length : sessFiltered.length;
  var gPages = Math.max(1, Math.ceil(activeLen / GPAGE));
  var gPageC = Math.min(gPage, gPages - 1);
  var sessPageRows = sessSorted.slice(gPageC * GPAGE, gPageC * GPAGE + GPAGE);
  var matPageRows = matFiltered.slice(gPageC * GPAGE, gPageC * GPAGE + GPAGE);
  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg shadow-sm p-5">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Connect Interviews Labs Dashboard</h1>
            <p className="text-xs text-gray-400 mt-1">Data as of {DATA.built_at || DATA.today || "-"} · auto-refreshes daily ~04:40 UTC</p>
          </div>
          <button onClick={function () { window.location.reload(); }}
            title="Data is rebuilt by the daily job; this just reloads the page - it does not pull new data on click."
            className="shrink-0 inline-flex items-center gap-1 px-3 py-2 text-sm font-medium rounded-md bg-indigo-600 text-white hover:bg-indigo-700">
            ↻ Reload page
          </button>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-1 mt-3 text-sm">
          <span><b>{c.cohorts}</b> cohorts</span>
          <span><b>{c.master_rows}</b> master rows</span>
          <span><b>{c.flws}</b> unique FLWs</span>
          <span><b>{c.started}</b> interviews started</span>
          <span><b>{c.completed}</b> completed</span>
        </div>
        {(DATA.unmappedCohorts && DATA.unmappedCohorts.length) ? (
          <div className="mt-3 text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded-md px-3 py-2">
            ⚠ {DATA.unmappedCohorts.length} cohort{DATA.unmappedCohorts.length === 1 ? "" : "s"} not yet mapped
            to a known program design (new program type?) - data is collected but hidden until a design is added:{" "}
            <span className="font-mono">{DATA.unmappedCohorts.join(", ")}</span>
          </div>
        ) : null}
      </div>

      <div className="bg-white rounded-lg shadow-sm">
        <div className="border-b border-gray-200 px-5">
          <nav className="-mb-px flex space-x-6">
            {TABS.map(function (t) {
              var on = activeTab === t[0];
              return (
                <button key={t[0]} onClick={function () { setTab(t[0]); }}
                  className={"py-3 px-1 border-b-2 text-sm font-medium " + (on ? "border-indigo-500 text-indigo-600" : "border-transparent text-gray-500 hover:text-gray-700")}>
                  {t[1]}
                </button>
              );
            })}
          </nav>
        </div>

        {activeTab === "overview" && (
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {/* "FLWs reached" not "Unique FLWs": counts.flws is the TRIGGERED universe (1,449), which is
                  looser than the FLW Retention tab's 1,441 "started ≥1 interview". Naming the base stops the
                  two tabs reading as a contradiction. */}
              {[["Cohorts", c.cohorts], ["FLWs reached", c.flws], ["Interviews started", c.started],
                ["Interviews completed", c.completed], ["% completed", pctOf(c.completed, c.started)]].map(function (kv) {
                return (
                  <div key={kv[0]} className="bg-gray-50 rounded-lg p-3">
                    <div className="text-2xl font-bold text-gray-900">{kv[1]}</div>
                    <div className="text-xs text-gray-500 mt-1">{kv[0]}</div>
                  </div>
                );
              })}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Connect funnel by subgroup</h3>
              <p className="text-xs text-gray-400 mb-2">Invited → Accepted → Completed Learn → Claimed from Connect (user_data); Initiated = any Welcome form; Started/Completed from OCS sessions.</p>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50"><tr>
                    <th className={th + " text-left"}>Subgroup</th>
                    <th className={th + " text-right"}>Invited</th>
                    <th className={th + " text-right"}>Accepted</th>
                    <th className={th + " text-right"}>Completed Learn</th>
                    <th className={th + " text-right"}>Claimed</th>
                    <th className={th + " text-right"}>Initiated</th>
                    <th className={th + " text-right"}>FLWs Started ≥1</th>
                    <th className={th + " text-right"}>FLWs Completed ≥1</th>
                  </tr></thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {DATA.connectFunnel.map(function (r) {
                      return (
                        <tr key={r.sg} className="hover:bg-gray-50">
                          <td className={td + " font-medium"}>{r.sg}</td>
                          <td className={td + " text-right"}>{r.invited}</td>
                          <td className={td + " text-right"}>{r.accepted}</td>
                          <td className={td + " text-right"}>{r.learn_completed}</td>
                          <td className={td + " text-right"}>{r.claimed}</td>
                          <td className={td + " text-right"}>{r.initiated}</td>
                          <td className={td + " text-right"}>{r.started}</td>
                          <td className={td + " text-right text-green-700 font-medium"}>{r.completed}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Completed interviews by round (unique FLWs per subgroup)</h3>
              <p className="text-xs text-gray-400 mb-2"># FLWs who completed each interview number - completion beyond the 1st interview, not just the first.</p>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50"><tr>
                    <th className={th + " text-left"}>Subgroup</th>
                    {Array.apply(null, { length: maxIv }).map(function (_, i) {
                      return <th key={i} className={th + " text-right"}>Int {i + 1}</th>;
                    })}
                  </tr></thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {DATA.dropoff.subgroups.map(function (s) {
                      var byN = {};
                      s.interviews.forEach(function (iv) { byN[iv.n] = iv; });
                      return (
                        <tr key={s.sg} className="hover:bg-gray-50">
                          <td className={td + " font-medium"}>{s.sg}</td>
                          {Array.apply(null, { length: maxIv }).map(function (_, i) {
                            var iv = byN[i + 1];
                            return (
                              <td key={i} className={td + " text-right" + (iv && iv.completed ? " text-green-700 font-medium" : " text-gray-300")}>
                                {iv ? iv.completed : "-"}
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === "table" && (
          <div className="p-3 space-y-3">
            <div className="flex items-center gap-2">
              {subBtn(tableSub, "granular", setTableSub, "Granular view")}
              {subBtn(tableSub, "topiccomplete", setTableSub, "Topic completion view")}
            </div>

            {tableSub === "granular" && (
              <div>
                <div className="flex flex-wrap items-center gap-2 px-1 py-2">
                  {subBtn(gView, "sessions", function (v) { setGView(v); setGPage(0); }, "Sessions")}
                  {subBtn(gView, "matrix", function (v) { setGView(v); setGPage(0); }, "FLW × Topic")}
                  <span className="mx-1 text-gray-300">|</span>
                  <input type="text" value={gSearch} placeholder={gView === "matrix" ? "Search connect_id / cohort…" : "Search connect_id / session / interview / status…"}
                    onChange={function (e) { setGSearch(e.target.value); setGPage(0); }}
                    className="border border-gray-300 rounded-md px-3 py-1.5 text-sm" style={{ width: "18rem" }} />
                  {filterDropdown("sg", "Subgroup", fSubgroups, fSg, setFSg)}
                  {filterDropdown("co", "Cohort", fCohorts, fCo, setFCo)}
                  {filterDropdown("topic", "Topic", MTOPICS.map(function (t) { return { value: t, label: t + " · " + (TOPIC_NAMES[t] || t) }; }), fTopic, setFTopic)}
                  {filterDropdown("st", "Status", STATES5.map(function (s) { return { value: s, label: STATE_LABEL[s] }; }), fSt, setFSt)}
                  {filterDropdown("tr", "FLW", [{ value: "trained", label: "Trained" }, { value: "untrained", label: "Untrained" }], fTr, setFTr)}
                  {anyFilter ? <button onClick={clearFilters} className="px-2 py-1.5 text-xs text-indigo-600 hover:underline">Clear</button> : null}
                  <span className="mx-1 text-gray-300">|</span>
                  <button onClick={function () { exportGranular(true); }} title="Download exactly the rows shown (all active filters + search)"
                    className="px-2 py-1.5 text-xs rounded-md border border-gray-300 hover:bg-gray-100">⬇ Export (filtered)</button>
                  <button onClick={function () { exportGranular(false); }} title="Download the full dataset for this view, ignoring filters"
                    className="px-2 py-1.5 text-xs rounded-md border border-gray-300 hover:bg-gray-100">⬇ Export all</button>
                </div>

                {gView === "sessions" && (
                  <div>
                    <div className="px-1 pb-2 text-xs text-gray-500">
                      {sessFiltered.length} sessions{ocsLive.length ? " (live OCS)" : " (embedded sample - live pipeline not loaded)"}{anyFilter ? " matching" : ""}
                    </div>
                    <div className="overflow-x-auto" style={{ maxHeight: "65vh" }}>
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50 sticky top-0"><tr>
                          {sortTh("connect_id", "connect_id")}
                          {sortTh("cohort_id", "cohort_id")}
                          {sortTh("interview", "interview")}
                          {sortTh("status", "status")}
                          {sortTh("created", "created")}
                          <th className={th + " text-left"}>session</th>
                        </tr></thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {sessPageRows.map(function (r, idx) {
                            var label = r.completed ? "Completed" : (r.started ? "Started" : "-");
                            var cls = r.completed ? "text-green-700 font-medium" : (r.started ? "text-lime-700" : "text-gray-400");
                            return (
                              <tr key={idx} className="hover:bg-gray-50">
                                <td className={td + " font-mono text-xs"}>{r.connect_id}</td>
                                <td className={td + " font-mono text-xs text-gray-600"} title={sessionCohort(r)}>{sessionCohort(r) || "-"}</td>
                                <td className={td}>{r.interview || "-"}</td>
                                <td className={td + " " + cls}>{label}</td>
                                <td className={td + " text-gray-500"}>{r.created_at || "-"}</td>
                                <td className={td + " font-mono text-xs"}>{r.session_id ? <a href={sessionUrl(r.session_id)} target="_blank" rel="noopener noreferrer" title={r.session_id} className="text-indigo-600 hover:underline">view ↗</a> : ""}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {gView === "matrix" && (
                  <div>
                    <div className="px-1 pb-1 text-xs text-gray-500">
                      {matFiltered.length} FLW×cohort rows{anyFilter ? " matching" : ""} · one row per FLW × cohort in the matrix universe, one column per topic - hover a cell for its status.
                    </div>
                    <div className="flex flex-wrap gap-x-3 gap-y-1 px-1 pb-2 text-xs text-gray-500">
                      {STATES5.map(function (s) {
                        return <span key={s} className="inline-flex items-center gap-1"><span style={{ display: "inline-block", width: 11, height: 11, background: STATE_COLOR[s], borderRadius: 2 }}></span>{CELL_GLYPH[STATES.indexOf(s)]} {STATE_LABEL[s]}</span>;
                      })}
                    </div>
                    <div className="overflow-x-auto" style={{ maxHeight: "65vh" }}>
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50 sticky top-0"><tr>
                          <th className={th + " text-left"}>connect_id</th>
                          <th className={th + " text-left"}>cohort</th>
                          <th className={th + " text-left"}>subgroup</th>
                          {MTOPICS.map(function (t) { return <th key={t} className={th + " text-center"} title={TOPIC_NAMES[t] || t}>{t}</th>; })}
                        </tr></thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {matPageRows.map(function (r, idx) {
                            var topics = SUBGROUP_DESIGN[r.g] || [];
                            var cb = {}; topics.forEach(function (t, i) { cb[t] = r.s[i]; });
                            return (
                              <tr key={idx} className="hover:bg-gray-50">
                                <td className={td + " font-mono text-xs"}>{r.f}{r.u ? <span title="Untrained FLW" className="ml-1 text-amber-600">⚑</span> : null}</td>
                                <td className={td}>{r.c}</td>
                                <td className={td + " text-gray-500"}>{r.g}</td>
                                {MTOPICS.map(function (t) {
                                  if (cb[t] == null) return <td key={t} className="px-2 py-1 text-center text-gray-200">·</td>;
                                  var code = cb[t];
                                  var _sid = sessByKey[r.f + "|" + t];
                                  var _cell = _sid
                                    ? <a href={sessionUrl(_sid)} target="_blank" rel="noopener noreferrer" style={{ color: "#fff", fontWeight: 700, textDecoration: "none" }}>{CELL_GLYPH[code]}<span style={{ fontSize: "10px", verticalAlign: "super", color: "#38bdf8", fontWeight: 700 }}>↗</span></a>
                                    : CELL_GLYPH[code];
                                  return <td key={t} className={"px-2 py-1 text-center text-xs" + (_sid ? " cursor-pointer" : "")} title={(TOPIC_NAMES[t] || t) + " - " + STATE_LABEL[STATES[code]] + (_sid ? " · click ↗ to open the OCS session" : "")}
                                    style={{ backgroundColor: rgbaOf(STATE_COLOR[STATES[code]], 0.85), color: "#fff" }}>{_cell}</td>;
                                })}
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-3 px-1 py-2 text-sm">
                  <button onClick={function () { setGPage(Math.max(0, gPageC - 1)); }} disabled={gPageC <= 0}
                    className="px-2 py-1 rounded border border-gray-300 disabled:opacity-40">‹ Prev</button>
                  <span className="text-gray-500">Page {gPageC + 1} / {gPages}</span>
                  <button onClick={function () { setGPage(Math.min(gPages - 1, gPageC + 1)); }} disabled={gPageC >= gPages - 1}
                    className="px-2 py-1 rounded border border-gray-300 disabled:opacity-40">Next ›</button>
                </div>
              </div>
            )}

            {tableSub === "topiccomplete" && (
              <div className="space-y-4">
                <p className="text-xs text-gray-400 px-1">Per-FLW status by topic, across every FLW × cohort slot (each topic stacks to 100%). Click a topic to break it down by cohort.</p>
                <p className="text-xs text-gray-400 px-1">Each bar counts <span className="font-medium text-gray-500">enrollment slots</span> for that topic (FLW × cohort - the completion-rate base), not unique FLWs. It includes people enrolled but not yet started, and counts anyone in two cohorts twice, so a bar can exceed the Overview unique-FLW total.</p>
                <p className="text-xs px-1 text-gray-500">
                  <b>% base:</b> {naMode === "exclude"
                    ? <span>share of <b>applicable</b> slots - the topic row, its by-cohort rows and the chart all use the same base.</span>
                    : <span>the topic row shows share of <b>all</b> slots (including cohorts where the topic isn't in the design), while its by-cohort rows show share of <b>applicable</b> slots. Switch <i>Not applicable</i> to <i>Exclude</i> to put everything on one base.</span>}
                </p>
                <div className="flex flex-wrap items-center gap-2 px-1">
                  <span className="text-xs text-gray-400">Group:</span>
                  {subBtn(topicGroupMode, "topic", setTopicGroupMode, "By topic")}
                  {subBtn(topicGroupMode, "theme", setTopicGroupMode, "By theme")}
                  <span className="mx-1 text-gray-300">|</span>
                  <span className="text-xs text-gray-400">Show:</span>
                  {subBtn(tcMode, "pct", setTcMode, "%")}
                  {subBtn(tcMode, "count", setTcMode, "Raw counts")}
                  {topicChart === "stacked" && tcMode === "pct" && (
                    <React.Fragment>
                      <span className="mx-1 text-gray-300">|</span>
                      <span className="text-xs text-gray-400">Not applicable:</span>
                      {subBtn(naMode, "include", setNaMode, "Include")}
                      {subBtn(naMode, "exclude", setNaMode, "Exclude")}
                    </React.Fragment>
                  )}
                </div>
                {topicChart === "stacked" && tcMode === "pct" && naMode === "exclude" && (
                  <p className="text-xs text-gray-400 px-1">Excludes “not applicable”: the remaining statuses rescale to <span className="font-medium text-gray-500">100% of the interviews that apply</span>.</p>
                )}
                {topicGroupMode === "theme" && (
                  <p className="text-xs text-gray-400 px-1">Related topics pooled into themes (interview-level sum): <span className="font-medium text-gray-500">Malaria</span> = B,1,2,10,10S,10L,14 · <span className="font-medium text-gray-500">Water &amp; Diarrhea</span> = D,11,11S,11L · <span className="font-medium text-gray-500">Community &amp; FLW Profile</span> = E,12 · <span className="font-medium text-gray-500">Antibiotics &amp; ACT Use</span> = 8,8S,8L · <span className="font-medium text-gray-500">Medicine Quality</span> = 9,13,13L. Topics not in a theme stay individual.</p>
                )}
                <Legend title="Status definitions (in chart order)">
                  {BAR_ORDER.map(function (s) {
                    return (
                      <div key={s} className="flex items-start gap-2">
                        <span style={{ display: "inline-block", width: 11, height: 11, background: STATE_COLOR[s], borderRadius: 2, marginTop: 3, flexShrink: 0 }}></span>
                        <span><b>{STATE_LABEL[s]}:</b> {STATE_DEF[s]}</span>
                      </div>
                    );
                  })}
                </Legend>
                {topicChart === "stacked" && (
                  <div style={{ height: Math.max(440, (topicRowsFor(DATA.topicStatus, topicGroupMode).length || 12) * 30) + "px" }}><canvas ref={barRef}></canvas></div>
                )}
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50"><tr>
                      <th className={th + " text-left"}>Topic</th>
                      {BAR_ORDER.map(function (s) { return <th key={s} className={th + " text-right"}>{STATE_LABEL[s]}</th>; })}
                    </tr></thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {DATA.topicStatus.map(function (t) {
                        var open = !!topicExp[t.code];
                        var has = tscRows(t.code).length > 0;
                        function p(s, tot) { return tcMode === "count" ? s : (tot ? Math.round(1000 * s / tot) / 10 + "%" : "-"); }
                        // The parent row used to divide by t.total (EVERY slot, including cohorts where the
                        // topic isn't in the design) while the cohort rows below it divide by the applicable
                        // base - so one screen showed 41.0% and 94.5% for the same topic. The parent now
                        // follows the same Not-applicable mode as the chart, which makes all three agree in
                        // Exclude mode; in Include mode the base is stated in the header instead.
                        var pTot = naMode === "exclude" ? (t.applicable || 0) : t.total;
                        var rows = [];
                        rows.push(
                          <tr key={t.code} className={"hover:bg-gray-50 " + (has ? "cursor-pointer" : "")}
                            onClick={has ? function () { var n = Object.assign({}, topicExp); n[t.code] = !open; setTopicExp(n); } : null}>
                            <td className={td + " font-medium"}>{has ? (open ? "▾ " : "▸ ") : ""}{t.code} · {TOPIC_NAMES[t.code] || t.code}</td>
                            {BAR_ORDER.map(function (s) {
                              // in Exclude mode "not applicable" is outside the base, so a % of it is meaningless
                              var cell = (naMode === "exclude" && s === "not-applicable" && tcMode !== "count") ? "-" : p(t[s], pTot);
                              return <td key={s} className={td + " text-right" + (s === "completed" ? " text-green-700 font-medium" : " text-gray-600")}>{cell}</td>;
                            })}
                          </tr>
                        );
                        if (open) {
                          var cohRows = tscRows(t.code);
                          rows.push(
                            <tr key={t.code + "-exp"} className="bg-gray-50">
                              <td className={td} colSpan={STATES.length + 1} style={{ padding: 0 }}>
                                <div className="my-2 ml-8 mr-3 border-l-2 border-gray-300 pl-3">
                                  <div className="text-xs font-medium text-gray-500 mb-1">
                                    By cohort - {t.code} · {TOPIC_NAMES[t.code] || t.code} ({cohRows.length} cohort{cohRows.length === 1 ? "" : "s"})
                                  </div>
                                  <table className="min-w-full border border-gray-200 rounded-md overflow-hidden">
                                    <thead className="bg-white"><tr>
                                      <th className={th + " text-left"}>Cohort</th>
                                      <th className={th + " text-left"}>Distribution</th>
                                      {BAR_ORDER5.map(function (s) { return <th key={s} className={th + " text-right"}>{STATE_LABEL[s]}</th>; })}
                                    </tr></thead>
                                    <tbody className="divide-y divide-gray-100">
                                      {cohRows.map(function (rc) {
                                        return (
                                          <tr key={rc.cohort} className="bg-white hover:bg-gray-50">
                                            <td className={td + " text-gray-700"}>{rc.cohort} <span className="text-gray-400">(n={rc.total})</span></td>
                                            <td className={td}>
                                              <div style={{ display: "flex", width: 120, height: 10, borderRadius: 2, overflow: "hidden", border: "1px solid #e5e7eb" }}>
                                                {BAR_ORDER5.map(function (s) {
                                                  var w = rc.total ? (100 * rc[s] / rc.total) : 0;
                                                  return w > 0 ? <div key={s} title={STATE_LABEL[s] + ": " + (Math.round(10 * w) / 10) + "%"} style={{ width: w + "%", backgroundColor: STATE_COLOR[s] }}></div> : null;
                                                })}
                                              </div>
                                            </td>
                                            {BAR_ORDER5.map(function (s) {
                                              return <td key={s} className={td + " text-right" + (s === "completed" ? " text-green-700" : " text-gray-500")}>{p(rc[s], rc.total)}</td>;
                                            })}
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                </div>
                              </td>
                            </tr>
                          );
                        }
                        return rows;
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "funnels" && (
          <div className="p-3 space-y-4">
            <div className="flex flex-wrap items-center gap-2 px-1">
              <span className="text-xs font-semibold text-gray-700">View:</span>
              {subBtn(funView, "retention", setFunView, "Retention lines")}
              {subBtn(funView, "engagement", setFunView, "Cohort engagement")}
              {subBtn(funView, "dropoff", setFunView, "Drop-off by cohort")}
            </div>
            {funView === "engagement" && renderEngagement()}
            {funView === "dropoff" && renderCohortDropoff()}
            {funView === "retention" && (
            <React.Fragment>
            <div className="flex flex-wrap items-center gap-2 px-1">
              <span className="text-xs font-medium text-gray-600">Denominator:</span>
              {subBtn(denomMode, "init", setDenomMode, "# Initiated")}
              {subBtn(denomMode, "prev", setDenomMode, "Reached prev interview")}
              <span className="text-gray-400" style={{ fontSize: "10px" }} title={"# Initiated: % Started = started ÷ FLWs who initiated (constant base) - later interviews look low because many FLWs haven't reached them.\nReached prev interview: denominator = FLWs who STARTED the previous interview, so each point is 'of those who got here, how many started this one' - later interviews no longer collapse."}>ℹ</span>
              <span className="mx-1 text-gray-300">|</span>
              <span className="text-xs font-medium text-gray-600">X-axis:</span>
              {/* in prev-denominator mode the chart is forced onto the interview-# axis, so show that
                  option as active even though lineMode is preserved for when the user switches back -
                  otherwise neither option looks selected. */}
              {subBtn(denomMode === "prev" ? "pct" : lineMode, "pct", setLineMode, "By interview #")}
              {denomMode === "prev"
                ? <span className="text-gray-300 line-through" title="Calendar-day view isn't available with the reached-prev denominator">By calendar day</span>
                : subBtn(lineMode, "time", setLineMode, "By calendar day")}
              <span className="mx-1 text-gray-300">|</span>
              <span className="text-xs font-medium text-gray-600">Penult/last artifact:</span>
              {subBtn(deImpact ? "di" : "raw", "raw", function () { setDeImpact(false); }, "Raw")}
              {subBtn(deImpact ? "di" : "raw", "di", function () { setDeImpact(true); }, "De-impacted")}
              {deImpact ? (
                <span className="inline-flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                  <span title={"FLWs removed from the last interview's Started (started last but not penultimate, triggered back-to-back):\n" + Object.keys(DATA.deimpact || {}).sort().map(function (sg) { return "  " + sg + ": " + DATA.deimpact[sg].count; }).join("\n") + "\n  Total: " + Object.keys(DATA.deimpact || {}).reduce(function (a, sg) { return a + DATA.deimpact[sg].count; }, 0)}
                    className="cursor-help font-bold border border-amber-400 rounded-full w-4 h-4 inline-flex items-center justify-center shrink-0">ℹ</span>
                  Removes FLWs who started only the LAST interview (skipped the penultimate - triggered back-to-back) from the last interview's Started, revealing the true decline. Hover ℹ for per-subgroup counts. Affects {denomMode === "prev" ? "the drop-off %Started table below only - the reached-prev line chart has its own denominator and is not de-impacted" : "the line chart & drop-off %Started below"}.
                </span>
              ) : null}
            </div>
            <div style={{ height: "380px" }}><canvas ref={lineRef}></canvas></div>
            <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 px-2">
              <span className="text-xs font-semibold text-indigo-600 mr-1">⇄ Toggle: click a subgroup to show / hide its line</span>
              {DATA.lineSeries.map(function (s) {
                var col = SG_COLOR[s.sg] || "#9ca3af";
                var dashed = (s.active != null) ? !!s.active : (s.status || []).some(function (x) { return x === "in-progress"; });
                var off = !!hidSg[s.sg];
                return (
                  <button key={s.sg} type="button"
                    onClick={function () { var n = Object.assign({}, hidSg); n[s.sg] = !n[s.sg]; setHidSg(n); }}
                    title={off ? "Hidden - click to show" : "Click to hide" + (dashed ? " · dashed = still in progress" : "")}
                    className={"inline-flex items-center gap-1.5 text-xs " + (off ? "opacity-40 line-through" : "text-gray-700 hover:text-gray-900")}>
                    <svg width="32" height="12" style={{ flexShrink: 0 }}>
                      <line x1="1" y1="6" x2="31" y2="6" stroke={col} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={dashed ? "6,4" : "none"} />
                    </svg>
                    {s.sg} (n={s.base})
                  </button>
                );
              })}
            </div>

            <Legend title="What these columns mean">
              <div><b>Connect funnel:</b> Invited → Accepted → Started/Completed Learn → Claimed (downloaded the app) → FLW Reg (HQ) (registered in CommCare HQ) → # Initiated (clicked any Welcome/start form).</div>
              <div><b>Eligible</b> = # FLWs initiated (constant per group - the retention base). <b>Triggered</b> = the bot prompted that interview. <b>Started</b> = an OCS session exists. <b>Completed</b> = session reached interview_complete.</div>
              <div><b>% Started</b> = Started ÷ Eligible · <b>% Triggered</b> = Triggered ÷ Eligible · <b>% Completed</b> = Completed ÷ Started.</div>
            </Legend>

            {CONNECT_PENDING.length ? (
              <div className="text-xs bg-amber-50 border border-amber-200 rounded px-3 py-2 text-amber-800">
                ⏳ <b>Connect funnel pending for: {CONNECT_PENDING.join(", ")}.</b> These cohorts are live in the interview data (Triggered/Started/Completed are correct), but their Connect leg (Invited/Accepted/Started&amp;Completed Learn/Claimed) hasn&#39;t been pulled yet - it shows 0 until the next successful Connect pull. Cohort counts and interview funnels are complete.
              </div>
            ) : null}
            <div className="overflow-x-auto">
              <h3 className="text-sm font-semibold text-gray-700 px-1 py-1">Connect funnel by subgroup</h3>
              <p className="text-xs text-gray-400 px-1">Invited → Accepted → Started/Completed Learn → Claimed → FLW registered (HQ) → # Initiated (any Welcome form). From Connect user_data (static snapshot) + HQ.</p>
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50"><tr>
                  {["Subgroup", "Invited", "Accepted", "Started Learn", "Completed Learn", "Claimed", "FLW Reg (HQ)", "# Initiated"].map(function (h, i) {
                    return <th key={h} className={th + (i === 0 ? " text-left" : " text-right")}>{h}</th>;
                  })}
                </tr></thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {DATA.dropoff.subgroups.map(function (s) {
                    var c = s.connect;
                    return (
                      <tr key={s.sg} className="hover:bg-gray-50">
                        <td className={td + " font-medium"}>{s.sg} <span className="text-gray-400">({s.cohorts_n})</span>{connPending(s.sg) ? <span title="Connect funnel not pulled yet - Invited/Accepted/Claimed pending" className="ml-1 text-amber-600">⏳</span> : null}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? <span className="text-amber-600" title="pending Connect pull">⏳</span> : c.invited}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "-" : c.accepted}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "-" : c.learn_started}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "-" : c.learn_completed}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "-" : c.claimed}</td>
                        <td className={td + " text-right"}>{c.flw_reg}</td>
                        <td className={td + " text-right font-medium"}>{c.initiated}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="overflow-x-auto">
              <h3 className="text-sm font-semibold text-gray-700 px-1 py-1">Interview drop-off - by interview, all topics</h3>
              <p className="text-xs text-gray-400 px-1">Retention rates: Eligible = # FLWs initiated (constant per group); % Started = Started ÷ Eligible; % Completed = Completed ÷ Started. Click a subgroup to expand its cohorts.</p>
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50"><tr>
                  <th className={th + " text-left"}>Group / Int</th><th className={th + " text-left"}>Topic</th>
                  <th className={th + " text-right"}>Eligible</th><th className={th + " text-right"}>Triggered</th>
                  <th className={th + " text-right"}>% Trig</th><th className={th + " text-right"}>Started</th>
                  <th className={th + " text-right"}>% Started</th><th className={th + " text-right"}>Completed</th>
                  <th className={th + " text-right"}>% Completed</th>
                </tr></thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {DATA.dropoff.subgroups.map(function (s) {
                    var open = !!funExp[s.sg];
                    var rows = [];
                    rows.push(
                      <tr key={s.sg + "-h"} className="bg-indigo-50 cursor-pointer"
                        onClick={function () { var n = Object.assign({}, funExp); n[s.sg] = !open; setFunExp(n); }}>
                        <td className={td + " font-bold text-indigo-800"} colSpan={9}>{open ? "▾" : "▸"} {s.sg} - {(DATA.dropoff.cohorts[s.sg] || []).length} cohorts</td>
                      </tr>
                    );
                    s.interviews.forEach(function (iv) { rows.push(ivRow(s.sg + "-" + iv.n, "Int " + iv.n, iv, "")); });
                    if (open) {
                      var cos = DATA.dropoff.cohorts[s.sg] || [];
                      rows.push(
                        <tr key={s.sg + "-exp"} className="bg-gray-50">
                          <td className={td} colSpan={9} style={{ padding: 0 }}>
                            <div className="my-2 ml-6 mr-3 border-l-2 border-indigo-200 pl-3 space-y-3">
                              {cos.map(function (co) {
                                return (
                                  <div key={co.cohort}>
                                    <div className="text-xs font-medium text-gray-500 mb-1">
                                      {co.cohort} - {co.interviews.length} interview{co.interviews.length === 1 ? "" : "s"}
                                      {/* de-impact is only computed at subgroup level, so these rows stay RAW.
                                          Say so, otherwise the parent row's Started looks like it disagrees with
                                          the sum of its own children (e.g. ABT1-B Int 4: 131 vs 171). */}
                                      {deImpact ? <span className="ml-2 text-amber-700 font-normal">· raw (de-impact applies to the subgroup row above, not per-cohort)</span> : null}
                                    </div>
                                    <table className="min-w-full border border-gray-200 rounded-md overflow-hidden">
                                      <thead className="bg-white"><tr>
                                        <th className={th + " text-left"}>Int</th><th className={th + " text-left"}>Topic</th>
                                        <th className={th + " text-right"}>Eligible</th><th className={th + " text-right"}>Triggered</th>
                                        <th className={th + " text-right"}>% Trig</th><th className={th + " text-right"}>Started</th>
                                        <th className={th + " text-right"}>% Started</th><th className={th + " text-right"}>Completed</th>
                                        <th className={th + " text-right"}>% Completed</th>
                                      </tr></thead>
                                      <tbody className="divide-y divide-gray-100">
                                        {co.interviews.map(function (iv) {
                                          return (
                                            <tr key={co.cohort + "-" + iv.n} className="bg-white hover:bg-gray-50">
                                              <td className={td + " text-gray-500"}>Int {iv.n}</td>
                                              <td className={td}>{iv.name || TOPIC_NAMES[iv.topic] || iv.topic}</td>
                                              <td className={td + " text-right"}>{iv.eligible}</td>
                                              <td className={td + " text-right"}>{iv.triggered}</td>
                                              <td className={td + " text-right text-gray-500"}>{iv.pct_trig}%</td>
                                              <td className={td + " text-right"}>{iv.started}</td>
                                              <td className={td + " text-right text-green-700 font-semibold"}>{iv.pct_started}%</td>
                                              <td className={td + " text-right"}>{iv.completed}</td>
                                              <td className={td + " text-right text-green-700 font-semibold"}>{iv.pct_completed == null ? "-" : iv.pct_completed + "%"}</td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                );
                              })}
                            </div>
                          </td>
                        </tr>
                      );
                    }
                    return rows;
                  })}
                </tbody>
              </table>
            </div>
            </React.Fragment>
            )}

          </div>
        )}

        {activeTab === "fullretention" && (
          <div className="p-3 space-y-4">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-700 mr-2">Full retention table - Connect funnel → every interview (one row per subgroup)</h3>
              <button onClick={copyRetention} className="px-3 py-1.5 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-700">⧉ Copy</button>
              <button onClick={downloadRetention} className="px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-100">↓ CSV</button>
              <span className="text-xs text-gray-400">Copy pastes tab-separated into Sheets/Excel.</span>
            </div>
            <Legend title="Column definitions">
              <div><b>Connect funnel</b> (unique FLWs per subgroup): <b>Invited</b> → <b>Accepted</b> → <b>Started Learn</b> → <b>Completed Learn</b> → <b>Claimed</b> (downloaded the opportunity) → <b>FLW Reg</b> (also registered in CommCare HQ) → <b># Initiated</b> (submitted any Welcome/start form - the retention base).</div>
              <div><b>Per interview:</b> <b>Eligible</b> = # Initiated (constant base). <b>Triggered</b> = bot prompted that interview. <b>Started</b> = an OCS session exists. <b>Completed</b> = session reached interview_complete.</div>
              <div><b>% Trig</b> = Triggered ÷ Eligible · <b>% Started</b> = Started ÷ Eligible · <b>% Compl</b> = Completed ÷ Started (conversion of those who started) · <b>Overall completed</b> = Completed ÷ # Initiated (completion as a share of everyone who initiated).</div>
            </Legend>
            <Legend title="Which interviews each subgroup runs (topic sequence)">
              {SG_ORDER.filter(function (sg) { return (SUBGROUP_DESIGN[sg] || []).length; }).map(function (sg) {
                return (
                  <div key={sg}><b>{sg}</b> <span className="text-gray-400">({(SUBGROUP_DESIGN[sg] || []).length} interviews, every {(DATA.subgroupDesign && DATA.subgroupDesign[sg] ? DATA.subgroupDesign[sg].cadence : "?")}d)</span>: {(SUBGROUP_DESIGN[sg] || []).map(function (t, i) { return "Int" + (i + 1) + "=" + t + " (" + (TOPIC_NAMES[t] || t) + ")"; }).join(" · ")}</div>
                );
              })}
            </Legend>
            <div className="overflow-x-auto border border-gray-200 rounded-lg" style={{ maxHeight: "70vh", fontVariantNumeric: "tabular-nums" }}>
              <table className="min-w-full text-xs border-collapse">
                <thead className="sticky top-0 z-20">
                  <tr className="bg-gray-100">
                    <th className={th + " text-left sticky left-0 z-30 bg-gray-100 border-b border-gray-300"} rowSpan={2} title="Study arm / program type">Subgroup</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Number of cohorts in this subgroup">Cohorts</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Unique FLWs with an invited_date in Connect">Invited</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Unique FLWs with user_invite_status = accepted">Accepted</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Unique FLWs with a date_learn_started">Started Learn</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Unique FLWs with a completed_learn_date">Compl. Learn</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Unique FLWs with a date_claimed (downloaded the opportunity)">Claimed</th>
                    <th className={th + " text-right border-b border-gray-300"} rowSpan={2} title="Claimed FLWs also registered in CommCare HQ (claimed ∩ HQ flw_registration)">FLW Reg</th>
                    <th className={th + " text-right border-r-2 border-gray-300 border-b"} rowSpan={2} title="Unique FLWs with any Welcome/start form - the retention base (denominator for the % columns)"># Initiated</th>
                    {Array.apply(null, { length: maxIv }).map(function (_, i) {
                      return <th key={i} className={th + " text-center border-l-2 border-gray-300 " + (i % 2 ? "bg-gray-100" : "bg-indigo-50")} colSpan={6}>Interview {i + 1}</th>;
                    })}
                  </tr>
                  <tr className="bg-gray-100">
                    {Array.apply(null, { length: maxIv }).map(function (_, i) {
                      var gb = (i % 2 ? "bg-gray-100" : "bg-indigo-50");
                      return [
                        <th key={i + "t"} className={th + " text-left border-l-2 border-gray-300 border-b border-gray-300 " + gb} title="Topic code for this interview position (hover a cell for the topic name)">Topic</th>,
                        <th key={i + "e"} className={th + " text-right border-b border-gray-300 " + gb} title="Eligible = # Initiated (constant retention base)">Elig</th>,
                        <th key={i + "tr"} className={th + " text-right border-b border-gray-300 " + gb} title="Bot-triggered FLWs · % = Triggered ÷ Eligible">Trig/%</th>,
                        <th key={i + "s"} className={th + " text-right border-b border-gray-300 " + gb} title="FLWs with an OCS session · % = Started ÷ Eligible">Start/%</th>,
                        <th key={i + "c"} className={th + " text-right border-b border-gray-300 " + gb} title="Completed (session reached interview_complete) · % = Completed ÷ Started">Compl/%</th>,
                        <th key={i + "ci"} className={th + " text-right border-b border-gray-300 " + gb} title="Overall completed = Completed ÷ # Initiated (share of everyone who initiated)">Overall Compl%</th>,
                      ];
                    })}
                  </tr>
                </thead>
                <tbody>
                  {DATA.dropoff.subgroups.map(function (s, ridx) {
                    var cn = s.connect, byN = {};
                    s.interviews.forEach(function (iv) { byN[iv.n] = iv; });
                    var rbg = ridx % 2 ? "bg-gray-50" : "bg-white";
                    return (
                      <tr key={s.sg} className={rbg + " hover:bg-indigo-50/60 border-b border-gray-100"}>
                        <td className={td + " font-semibold sticky left-0 z-10 " + rbg}>{s.sg}</td>
                        <td className={td + " text-right text-gray-500"}>{s.cohorts_n}</td>
                        <td className={td + " text-right"}>{cn.invited}</td>
                        <td className={td + " text-right"}>{cn.accepted}</td>
                        <td className={td + " text-right"}>{cn.learn_started}</td>
                        <td className={td + " text-right"}>{cn.learn_completed}</td>
                        <td className={td + " text-right"}>{cn.claimed}</td>
                        <td className={td + " text-right"}>{cn.flw_reg}</td>
                        <td className={td + " text-right font-semibold border-r-2 border-gray-300"}>{cn.initiated}</td>
                        {Array.apply(null, { length: maxIv }).map(function (_, i) {
                          var iv = byN[i + 1];
                          if (!iv) return [
                            <td key={i + "t"} className={td + " text-gray-200 border-l-2 border-gray-300"}>-</td>,
                            <td key={i + "e"} className={td}></td>, <td key={i + "tr"} className={td}></td>,
                            <td key={i + "s"} className={td}></td>, <td key={i + "c"} className={td}></td>,
                            <td key={i + "ci"} className={td}></td>,
                          ];
                          return [
                            <td key={i + "t"} className={td + " border-l-2 border-gray-300 font-medium text-gray-600"} title={iv.name}>{iv.topic}</td>,
                            <td key={i + "e"} className={td + " text-right text-gray-400"}>{iv.eligible}</td>,
                            <td key={i + "tr"} className={td + " text-right"}>{iv.triggered} <span className="text-gray-400">{iv.pct_trig}%</span></td>,
                            <td key={i + "s"} className={td + " text-right"}>{iv.started} <span className="text-gray-400">{iv.pct_started}%</span></td>,
                            <td key={i + "c"} className={td + " text-right text-green-700"}>{iv.completed} <span className="text-gray-400">{iv.pct_completed == null ? "-" : iv.pct_completed + "%"}</span></td>,
                            <td key={i + "ci"} className={td + " text-right font-semibold " + (iv.pct_completed_base == null ? "text-gray-400" : "text-green-800")}>{iv.pct_completed_base == null ? "-" : iv.pct_completed_base + "%"}</td>,
                          ];
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === "breakdowns" && (
          <div className="p-3 space-y-3">
            <div className="flex items-center gap-2">
              {subBtn(bdSub, "subgroup", setBdSub, "By Subgroup")}
              {subBtn(bdSub, "topic", setBdSub, "By Topic")}
              {subBtn(bdSub, "ab", setBdSub, "A/B Arms")}
            </div>
            <Legend title="Metric definitions">
              <div><b>FLWs Started:</b> unique FLWs who started ≥1 interview in the group.</div>
              <div><b>Interviews Started / Completed:</b> count of started / completed interviews (an FLW can have several).</div>
              <div><b>% Completed:</b> Interviews Completed ÷ Interviews Started.</div>
              <div><b>Avg words / FLW msg:</b> total FLW-message words ÷ total FLW messages, over started sessions (whitespace word count).</div>
            </Legend>

            {bdSub === "subgroup" && (
              <div className="overflow-x-auto">
                <p className="text-xs text-gray-400 px-1 py-1">Unique FLWs &amp; interview counts per study arm. % Completed = completed ÷ started.</p>
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50"><tr>
                    <th className={th + " text-left"}>Subgroup</th><th className={th + " text-right"}>FLWs Started</th>
                    <th className={th + " text-right"}>Interviews Started</th><th className={th + " text-right"}>Interviews Completed</th>
                    <th className={th + " text-right"}>% Completed</th><th className={th + " text-right"}>Avg words / FLW msg</th>
                  </tr></thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {DATA.table1.map(function (r) {
                      var ov = r.key === "Overall";
                      return (
                        <tr key={r.key} className={ov ? "bg-gray-50" : "hover:bg-gray-50"}>
                          <td className={td + (ov ? " font-bold" : " font-medium")}>{r.key}</td>
                          <td className={td + " text-right"}>{r.flws}</td><td className={td + " text-right"}>{r.ist}</td>
                          <td className={td + " text-right text-green-700 font-medium"}>{r.icmp}</td>
                          <td className={td + " text-right text-gray-500"}>{pctTxt(r.pct)}</td>
                          <td className={td + " text-right text-gray-500"}>{r.avg_words == null ? "-" : r.avg_words}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {bdSub === "topic" && (
              <div className="overflow-x-auto">
                <p className="text-xs text-gray-400 px-1 py-1">Interview engagement by topic (pooled across subgroups). % Completed = completed ÷ started.</p>
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50"><tr>
                    <th className={th + " text-left"}>Topic</th><th className={th + " text-left"}>Name</th>
                    <th className={th + " text-right"} title="Number of questions in this topic's interview (per the design)"># Questions</th>
                    <th className={th + " text-right"}>FLWs Started</th><th className={th + " text-right"}>Interviews Started</th>
                    <th className={th + " text-right"}>Interviews Completed</th><th className={th + " text-right"}>% Completed</th>
                    <th className={th + " text-right"}>Avg words / FLW msg</th>
                  </tr></thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {DATA.table2.map(function (r) {
                      var _q = DATA.topicQuestions && DATA.topicQuestions[r.code] != null ? DATA.topicQuestions[r.code] : null;
                      var none = !r.ist;  // no started interviews yet (e.g. not-yet-reached PANEL topics)
                      return (
                        <tr key={r.code} className={none ? "text-gray-400" : "hover:bg-gray-50"}>
                          <td className={td + " font-medium"}>{r.code}</td><td className={td}>{r.name}</td>
                          <td className={td + " text-right text-gray-600"}>{_q == null ? "-" : _q}</td>
                          <td className={td + " text-right"}>{none ? "-" : r.flws}</td><td className={td + " text-right"}>{none ? "-" : r.ist}</td>
                          <td className={td + " text-right text-green-700 font-medium"}>{none ? "-" : r.icmp}</td>
                          <td className={td + " text-right text-gray-500"}>{pctTxt(r.pct)}</td>
                          <td className={td + " text-right text-gray-500"}>{r.avg_words == null ? "-" : r.avg_words}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {bdSub === "ab" && (
              <div className="overflow-x-auto">
                <p className="text-xs text-gray-400 px-1 py-1">A/B experimental arms ({(DATA.table3 || []).filter(function (r) { return r.key !== "Overall"; }).map(function (r) { return r.key; }).join(", ")}; Overall = their sum). % Completed = completed ÷ started.</p>
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50"><tr>
                    <th className={th + " text-left"}>Arm</th><th className={th + " text-right"}>FLWs Started</th>
                    <th className={th + " text-right"}>Interviews Started</th><th className={th + " text-right"}>Interviews Completed</th>
                    <th className={th + " text-right"}>% Completed</th><th className={th + " text-right"}>Avg words / FLW msg</th>
                  </tr></thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {DATA.table3.map(function (r) {
                      var ov = r.key === "Overall";
                      return (
                        <tr key={r.key} className={ov ? "bg-gray-50" : "hover:bg-gray-50"}>
                          <td className={td + (ov ? " font-bold" : " font-medium")}>{r.key}</td>
                          <td className={td + " text-right"}>{r.flws}</td><td className={td + " text-right"}>{r.ist}</td>
                          <td className={td + " text-right text-green-700 font-medium"}>{r.icmp}</td>
                          <td className={td + " text-right text-gray-500"}>{pctTxt(r.pct)}</td>
                          <td className={td + " text-right text-gray-500"}>{r.avg_words == null ? "-" : r.avg_words}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === "flw" && (function () {
          var FE = DATA.flwEngagement || {};
          if (!FE.n_flws) return <div className="p-6 text-sm text-gray-500">FLW-level analysis not available in this build.</div>;
          var N = FE.n_flws;
          // Tier labels were renamed 2026-08-11 to stop them colliding with the persona names
          // ("Champion" was in both lists, with different counts, as two clickable filters on one
          // screen). Old keys kept as aliases so a payload built before the rename still colours.
          var TIER_COLOR = { "Highly engaged": "#065f46", Engaged: "#2E7D32", Slipping: "#F9A825", "Gone quiet": "#EF6C00", Lost: "#C62828",
                             Champion: "#065f46", Solid: "#2E7D32", "At-risk": "#EF6C00" };
          var PERSONA_COLOR = { Champion: "#065f46", "Steady finisher": "#2E7D32", "Partial progress": "#F9A825", "Re-engager": "#1565C0", "Early dropper": "#EF6C00", "One-and-done": "#C62828", Lapsed: "#9ca3af" };
          // top two score bands, by published order - no hardcoded tier names to go stale
          var healthy = (FE.tiers || []).slice(0, 2).reduce(function (a, t) { return a + t.pct; }, 0);
          var cc = FE.crossCohort || { multi: {}, single: {}, dist: [] };
          // horizontal bar row
          var bar = function (label, pct, color, right, key) {
            return (
              <div key={key} className="flex items-center gap-2 text-xs py-0.5">
                <div className="text-gray-700 text-right" style={{ width: "150px", flexShrink: 0 }}>{label}</div>
                <div className="flex-1 bg-gray-100 rounded h-4 relative" style={{ minWidth: "80px" }}>
                  <div className="h-4 rounded" style={{ width: Math.min(100, pct) + "%", backgroundColor: color }}></div>
                </div>
                <div className="text-gray-600 font-medium text-right" style={{ width: "78px", flexShrink: 0 }}>{right}</div>
              </div>
            );
          };
          var card = function (val, label, sub, color, key) {
            return (
              <div key={key} className="rounded border border-gray-200 bg-white px-3 py-2" style={{ minWidth: "150px" }}>
                <div className="text-xl font-bold" style={{ color: color }}>{val}</div>
                <div className="text-xs font-medium text-gray-700">{label}</div>
                <div className="text-gray-400" style={{ fontSize: "10px" }}>{sub}</div>
              </div>
            );
          };
          // ---- interactive cross-filter over the per-FLW micro block ------------------------------
          // FE.micro carries one character per FLW per dimension (no identifier), so the whole tab can
          // re-slice client-side: click any bar and every other panel re-computes for that segment.
          var M = FE.micro;
          var DIMS = [["state", "State"], ["llo", "Partner (LLO)"], ["type", "Cadre"],
                      ["tier", "Engagement tier - right now"], ["persona", "Persona - whole history"],
                      ["nco", "Cohorts they were in"], ["fin", "Finished a schedule?"],
                      ["peers", "Co-workers in their settlement"], ["pace", "Pace vs their schedule"]];
          // Nine dimensions, nine clearly separated hues (~40 degrees apart). The previous palette had
          // four near-identical teal/greens (#00695C type, #0f766e tier, #0e7490 peers, #065f46 fin),
          // two near-identical violets (#6d28d9 llo, #7c3aed nco) and two near-identical ambers
          // (#b45309 persona, #a16207 pace) - so at a glance half the panels looked like the same
          // colour and the panels were hard to tell apart. Status red (#C62828, used for dropped/missed
          // across the dashboard) is deliberately NOT reused here: these bars are a share of the
          // selection, not a good/bad signal.
          var DIM_COLOR = { state: "#1565C0", peers: "#3949AB", llo: "#7B1FA2", nco: "#AD1457",
                            persona: "#D84315", pace: "#F9A825", tier: "#2E7D32", fin: "#00897B",
                            type: "#546E7A" };
          var DIM_HELP = {
            tier: "Where the worker is TODAY: a score band blending how recently they interviewed, their completion rate and their answer depth. A worker moves between tiers over time. Because it also rewards recency and answer depth, the top tier is NOT necessarily the highest finish rate.",
            peers: "How many other FLWs work in the same settlement. A proxy for informal peer support, which the community-health-worker literature repeatedly identifies as a retention factor.",
            pace: "Their typical gap between interviews measured against what their own schedule asks for - so it is comparable across subgroups whose cadences differ (3 to 14 days).",
            persona: "What the worker has DONE overall, across their whole history - a fixed behavioural segment, not a current-state reading. Deliberately worded differently from the tiers so the two are never confused. NOTE: several personas are DEFINED by whether the worker finished, so the right-hand % in this panel is a definition, not a result (One-and-done is 0% by construction).",
          };
          function unpackNum(spec) {
            var out = [], i, w = spec.w, s = spec.s;
            for (i = 0; i < s.length; i += w) out.push(parseInt(s.substr(i, w), 36));
            return out;
          }
          var NUM = {}, dimOK = !!(M && M.n && M.col && M.dict);
          if (dimOK) { Object.keys(M.num || {}).forEach(function (k) { NUM[k] = unpackNum(M.num[k]); }); }
          // "Other" is this build's catch-all for tail values; "others" is a REAL cadre in the source
          // data. They looked identical on screen, so the catch-all is renamed and marked everywhere.
          function isResidual(label) { return label === "Other" || label === "(not recorded)" || label === "Other / not recorded" || label === "traditional_birth_attendants"; }
          function residualLabel(label) { return isResidual(label) ? "Other / not recorded" : label; }
          var selKeys = Object.keys(flwSel).filter(function (k) { return (flwSel[k] || []).length; });
          var filtered = selKeys.length > 0;
          // mask, optionally ignoring one dimension's own filter (so you can still see/deselect its
          // other values - standard cross-filter behaviour)
          function maskFor(skipDim) {
            var m = [], i, j, ok, k;
            for (i = 0; i < (dimOK ? M.n : 0); i++) {
              ok = true;
              for (j = 0; j < selKeys.length; j++) {
                k = selKeys[j];
                if (k === skipDim) continue;
                if (flwSel[k].indexOf(+M.col[k].charAt(i)) < 0) { ok = false; break; }
              }
              m.push(ok);
            }
            return m;
          }
          var MASK = dimOK ? maskFor(null) : [];
          function median(a) { if (!a.length) return 0; var b = a.slice().sort(function (x, y) { return x - y; }); var h = b.length >> 1; return b.length % 2 ? b[h] : Math.round((b[h - 1] + b[h]) / 2); }
          var FIN_IDX = dimOK ? (M.dict.fin || []).indexOf("Finished ≥1 schedule") : -1;
          function stats(mask) {
            var n = 0, fin = 0, pcf = 0, pcfo = 0, nOff = 0, fd = [], dp = [], deep = [], i;
            for (i = 0; i < mask.length; i++) {
              if (!mask[i]) continue;
              n++;
              if (FIN_IDX >= 0 && +M.col.fin.charAt(i) === FIN_IDX) fin++;
              pcf += (NUM.pcf || [])[i] || 0;
              // pcfo == 101 means "no cohort of theirs has been fully offered yet", i.e. not measurable.
              // Those workers are EXCLUDED from this average - counting them as 0 would read as
              // "finished nothing" when the schedule was never put to them.
              var _o = (NUM.pcfo || [])[i];
              if (_o != null && _o <= 100) { pcfo += _o; nOff++; }
              fd.push((NUM.fdepth || [])[i] || 0);
              dp.push((NUM.depth || [])[i] || 0);
              deep.push((NUM.deep || [])[i] || 0);
            }
            return { n: n, any: n ? Math.round(100 * fin / n) : 0, pc: n ? Math.round(pcf / n) : 0,
                     pco: nOff ? Math.round(pcfo / nOff) : null, nOff: nOff,
                     fdepth: median(fd), depth: median(dp), deep: median(deep) };
          }
          var SEL = dimOK ? stats(MASK) : { n: N, any: 0, pc: 0, pco: null, nOff: 0, fdepth: 0, depth: 0, deep: 0 };
          var ALL = dimOK ? stats(MASK.map(function () { return true; })) : SEL;
          function toggle(dim, idx) {
            var cur = (flwSel[dim] || []).slice(), at = cur.indexOf(idx);
            if (at >= 0) cur.splice(at, 1); else cur.push(idx);
            var next = {}; Object.keys(flwSel).forEach(function (k) { next[k] = flwSel[k]; });
            next[dim] = cur; setFlwSel(next);
          }
          // one dimension panel: bar length = share of the current selection, right-hand chip = outcome
          function panel(dim, title) {
            var dictv = M.dict[dim] || [], col = M.col[dim];
            var sub = maskFor(dim), i, v;
            var cnt = dictv.map(function () { return 0; }), tot = 0;
            var finc = dictv.map(function () { return 0; }), pcs = dictv.map(function () { return 0; });
            for (i = 0; i < M.n; i++) {
              if (!sub[i]) continue;
              v = +col.charAt(i); cnt[v]++; tot++;
              if (FIN_IDX >= 0 && +M.col.fin.charAt(i) === FIN_IDX) finc[v]++;
              pcs[v] += (NUM.pcf || [])[i] || 0;
            }
            // baseline share of each value across ALL FLWs, for the lift badge
            var base = dictv.map(function () { return 0; });
            for (i = 0; i < M.n; i++) base[+col.charAt(i)]++;
            var rows = dictv.map(function (label, idx) {
              return { label: label, idx: idx, n: cnt[idx], share: tot ? 100 * cnt[idx] / tot : 0,
                       baseShare: 100 * base[idx] / M.n,
                       any: cnt[idx] ? Math.round(100 * finc[idx] / cnt[idx]) : 0,
                       pc: cnt[idx] ? Math.round(pcs[idx] / cnt[idx]) : 0 };
            }).filter(function (r) { return r.n > 0 || (flwSel[dim] || []).indexOf(r.idx) >= 0; });
            // Count-sorting an ORDERED scale makes the tab look broken: tiers rendered
            // "Engaged, Slipping, Highly engaged, Gone quiet, Lost" and cohort counts "2, 3, 1, 4, 5".
            // Nominal dimensions (state/partner/cadre) still sort by size; ordered ones keep their
            // natural order, and the pooled residual is always pinned last wherever it appears.
            // peers/pace carry a monotone gradient (peers 52->59->64%, pace 68->49->41%), so they must
            // render in their natural order. Unlisted dimensions fall through to a count sort, which
            // printed "Very slow" above "Somewhat slow" and made both panels read as noise.
            var ORDERED = { tier: 1, persona: 1, nco: 1, peers: 1, pace: 1 };
            if (ORDERED[dim]) rows.sort(function (a, b) { return a.idx - b.idx; });
            else rows.sort(function (a, b) { return b.n - a.n; });
            rows.sort(function (a, b) { return (isResidual(a.label) ? 1 : 0) - (isResidual(b.label) ? 1 : 0); });
            var maxShare = Math.max.apply(null, rows.map(function (r) { return r.share; }).concat([1]));
            return (
              <div key={dim} className="rounded border border-gray-200 bg-white px-3 py-2">
                <div className="flex items-baseline justify-between mb-1">
                  <div className={"text-xs font-semibold text-gray-700" + (DIM_HELP[dim] ? " cursor-help underline decoration-dotted decoration-gray-300" : "")}
                    title={DIM_HELP[dim] || ""}>{title}</div>
                  {(flwSel[dim] || []).length
                    ? <button className="text-indigo-600 hover:underline" style={{ fontSize: "10px" }}
                        onClick={function () { var nx = {}; Object.keys(flwSel).forEach(function (k) { nx[k] = flwSel[k]; }); nx[dim] = []; setFlwSel(nx); }}>clear</button>
                    : <span className="text-gray-300" style={{ fontSize: "10px" }}>click to filter</span>}
                </div>
                {/* P1: the row carries four quantities and used to label none of them. The bar is a
                    SHARE of the current selection; the right-hand % is an outcome RATE whose meaning is
                    set by the toggle above. Naming them here also makes the toggle's scope obvious. */}
                <div className="flex items-center gap-2 text-gray-400" style={{ fontSize: "9px" }}>
                  <div className="text-right" style={{ width: "118px", flexShrink: 0 }}></div>
                  <div className="flex-1" style={{ minWidth: "60px" }}>share of selection</div>
                  <span style={{ width: "34px" }}></span>
                  <div className="text-right" style={{ width: "62px", flexShrink: 0 }}>workers · share</div>
                  <div className="text-right" style={{ width: "34px", flexShrink: 0 }}>{flwMetric === "pc" ? "per-cohort finish" : "finished ≥1"}</div>
                </div>
                {rows.map(function (r) {
                  var on = (flwSel[dim] || []).indexOf(r.idx) >= 0;
                  var lift = r.baseShare > 0 ? r.share / r.baseShare : 1;
                  var showLift = filtered && r.n > 0 && (lift >= 1.3 || lift <= 0.77);
                  var out = flwMetric === "pc" ? r.pc : r.any;
                  return (
                    <div key={r.idx} onClick={function () { toggle(dim, r.idx); }}
                      title={r.label + " - " + r.n + " FLWs (" + Math.round(r.share) + "% of selection, " + Math.round(r.baseShare) + "% of all). Click to " + (on ? "remove" : "apply") + " this filter."}
                      className={"flex items-center gap-2 py-0.5 cursor-pointer rounded " + (on ? "bg-indigo-50" : "hover:bg-gray-50")}
                      style={{ fontSize: "11px" }}>
                      <div className={"text-right truncate " + (on ? "text-indigo-700 font-semibold" : isResidual(r.label) ? "text-gray-400 italic" : "text-gray-700")} style={{ width: "118px", flexShrink: 0 }}
                        title={isResidual(r.label) ? "Catch-all for values with too few workers to show separately, plus any not recorded. Not a group in its own right." : ""}>
                        {on ? "✓ " : ""}{residualLabel(r.label)}
                      </div>
                      <div className="flex-1 bg-gray-100 rounded h-3.5 relative" style={{ minWidth: "60px" }}>
                        <div className="h-3.5 rounded" style={{ width: Math.max(1, 100 * r.share / maxShare) + "%", backgroundColor: DIM_COLOR[dim] || "#1565C0", opacity: on ? 1 : 0.75 }}></div>
                      </div>
                      {/* P12: direction by glyph as well as colour, so it survives greyscale and
                          colour-blindness. Shown only outside 0.77-1.3x (reciprocals). */}
                      {showLift
                        ? <span className={"font-semibold " + (lift >= 1.3 ? "text-rose-600" : "text-gray-500")} style={{ width: "34px", fontSize: "10px" }}
                            title={"This group is " + (Math.round(lift * 10) / 10) + "x its programme-wide share - " + (lift >= 1.3 ? "over" : "under") + "-represented in your current selection."}>
                            {(lift >= 1.3 ? "▲×" : "▼×") + (Math.round(lift * 10) / 10)}
                          </span>
                        : <span style={{ width: "34px" }}></span>}
                      <div className="text-gray-600 text-right" style={{ width: "62px", flexShrink: 0 }}>{r.n} · {Math.round(r.share)}%</div>
                      {/* P11: a rate off 1-2 workers reads as a finding (an n=1 partner showed "100%").
                          P5: with an empty selection every row was a red 0%. Both now render "-". */}
                      <div className="text-right font-medium" style={{ width: "34px", flexShrink: 0, color: r.n < 20 ? "#9ca3af" : out >= 70 ? "#065f46" : out >= 50 ? "#F9A825" : "#C62828" }}
                        title={r.n < 20 ? "too few workers (" + r.n + ") to quote a rate" : ""}>{r.n < 20 ? "-" : out + "%"}</div>
                    </div>
                  );
                })}
              </div>
            );
          }
          var chips = [];
          selKeys.forEach(function (k) {
            (flwSel[k] || []).forEach(function (idx) {
              chips.push(
                <button key={k + idx} onClick={function () { toggle(k, idx); }}
                  className="px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700 hover:bg-indigo-200" style={{ fontSize: "10px" }}
                  title="remove this filter">
                  {(DIMS.filter(function (d) { return d[0] === k; })[0] || ["", k])[1].split(" -")[0]}: {residualLabel((M.dict[k] || [])[idx])} ✕
                </button>
              );
            });
          });
          var ds = FE.depthSplit || null;
          // P4: these three sections are precomputed programme-wide. Sitting under a KPI that says
          // "291 FLWs in selection", an unmarked n=1,110 reads as a contradiction (or worse, as Sokoto's).
          var globalTag = filtered
            ? <span className="ml-2 px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-normal" style={{ fontSize: "9px" }}
                title="This section is computed for the whole programme and does not change with your filter.">
                whole programme ({N.toLocaleString()}) - not filtered
              </span>
            : null;
          return (
            <div className="p-4 space-y-4">
              <div className="text-xs bg-indigo-50 border border-indigo-100 rounded px-3 py-2 text-gray-700">
                <b>Per-FLW, cross-cohort.</b> One row per unique FLW who started interviewing, with their timeline unioned across every cohort/arm they were part of ({FE.coverage_lga}% have demographics).
                {dimOK ? <span> <b>Click any bar to drill in</b> - every other panel re-computes for that segment, and <span className="text-rose-600 font-semibold">×N</span> marks a group that is over-represented in your selection versus the programme as a whole.</span> : null}
              </div>

              {dimOK ? (
                <div className="flex flex-wrap items-center gap-2 px-1">
                  <span className="text-xs font-medium text-gray-600">Showing:</span>
                  {chips.length ? chips : <span className="text-xs text-gray-400">all {N.toLocaleString()} FLWs</span>}
                  {filtered
                    ? <button onClick={function () { setFlwSel({}); }} className="px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-100" style={{ fontSize: "10px" }}>reset</button>
                    : null}
                  <span className="mx-1 text-gray-300">|</span>
                  <span className="text-xs font-medium text-gray-600">Right-hand % on every panel:</span>
                  {subBtn(flwMetric, "pc", setFlwMetric, "Per-cohort finish")}
                  {subBtn(flwMetric, "any", setFlwMetric, "Finished ≥1")}
                </div>
              ) : null}

              {dimOK && filtered && SEL.n === 0 ? (
                <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  <b>No FLWs match this combination of filters.</b> The figures below are not zero results - there is
                  nothing to compute. Remove a filter (click a ✓ row again, or use “reset”) to continue.
                </div>
              ) : null}
              <div className="flex flex-wrap gap-2 px-1">
                {card(SEL.n.toLocaleString(), filtered ? "FLWs in selection" : "FLWs analysed",
                      filtered ? Math.round(100 * SEL.n / (M.n || 1)) + "% of all " + N.toLocaleString() : "started ≥1 interview", "#1565C0", "k1")}
                {card(SEL.n ? SEL.pc + "%" : "-", "Per-cohort finish - so far", filtered ? "all FLWs: " + ALL.pc + "%" : "counts schedules still being rolled out as unfinished", "#065f46", "k2")}
                {SEL.pco == null ? null : card(SEL.pco + "%", "Per-cohort finish - of schedules actually offered", filtered ? "all FLWs: " + (ALL.pco == null ? "-" : ALL.pco + "%") : "the like-for-like rate: only cohorts whose whole schedule was put to them", "#0277BD", "k2b")}
                {card(SEL.n ? SEL.any + "%" : "-", "Finished ≥1 schedule", filtered ? "all FLWs: " + ALL.any + "%" : "generous - rises with # cohorts", "#2E7D32", "k3")}
                {card(SEL.n ? SEL.fdepth : "-", "Median words, first interview they did", filtered ? "all FLWs: " + ALL.fdepth : "their first session - not necessarily interview 1 of a schedule", "#6d28d9", "k4")}
                {card(SEL.n ? "Int " + SEL.deep : "-", "Median furthest interview", filtered ? "all FLWs: Int " + ALL.deep : "how far through a schedule they got", "#b45309", "k5")}
              </div>

              {/* Cross-cohort: the honest version */}
              <div className="rounded border border-purple-200 bg-purple-50 px-3 py-2 text-xs text-gray-700">
                <b>⭐ Most FLWs work across several cohorts - but re-use does not by itself raise finishing.</b>{globalTag}{" "}
                {cc.multi.n} FLWs ({100 - (cc.single.n ? Math.round(100 * cc.single.n / N) : 0)}%) span ≥2 cohorts. They finish ≥1 schedule far more often ({cc.multi.finished}% vs {cc.single.finished}%) - but that comparison is <b>mechanical</b>: "finished ≥1" is a max over cohorts, so being in three cohorts gives three chances. On the like-for-like measure - the share of <i>their own</i> schedules they complete - multi-cohort FLWs are <b>{cc.multi.finished_pc}%</b> vs <b>{cc.single.finished_pc}%</b> for single-cohort: {(function () {
                  var g = (cc.multi.finished_pc || 0) - (cc.single.finished_pc || 0), a = Math.abs(g);
                  var raw = (cc.multi.finished || 0) - (cc.single.finished || 0);
                  if (a <= 3) return <span>essentially flat, so the headline gap is almost entirely arithmetic</span>;
                  return <span>a real <b>{g > 0 ? "+" : "−"}{a} point</b> difference, but roughly {Math.max(0, Math.round(100 * (raw - g) / (raw || 1)))}% of the {raw}-point headline gap is arithmetic rather than behaviour</span>;
                })()}. They also answer at greater length ({cc.multi.depth} vs {cc.single.depth} words/session). Neither measure establishes that re-using a worker <i>causes</i> them to finish more - being re-invited is itself an outcome of how they performed the first time.
              </div>

              {dimOK ? (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  {DIMS.filter(function (d) { return (M.dict[d[0]] || []).length > 1; }).map(function (d) { return panel(d[0], d[1]); })}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <div className="text-sm font-semibold text-gray-700 mb-1">Finish rate by state</div>
                    {(FE.byState || []).map(function (s) { return bar(s.k + " (n=" + s.n + ")", s.finished, "#1565C0", s.finished + "%", "st" + s.k); })}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-700 mb-1">Finish rate by FLW type</div>
                    {(FE.byType || []).map(function (s) { return bar(s.k + " (n=" + s.n + ")", s.finished, "#5E35B1", s.finished + "%", "ty" + s.k); })}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-gray-700 mb-1">Finish rate by LLO</div>
                    {(FE.byLLO || []).map(function (s) { return bar(s.k + " (n=" + s.n + ")", s.finished, "#6d28d9", s.finished + "%", "llo" + s.k); })}
                  </div>
                </div>
              )}

              {/* Early depth */}
              {ds ? (
                <div className="rounded border border-gray-200 bg-white px-3 py-2">
                  <div className="text-sm font-semibold text-gray-700 mb-1">Is answer depth at the first interview associated with finishing?{globalTag}</div>
                  <p className="text-gray-500 text-xs mb-2">FLWs split at the median first-session answer depth ({ds.median} words). Read the per-cohort rate, not "finished ≥1": the deeper group is also in more cohorts, which inflates the ≥1 measure.</p>
                  <div className="flex flex-wrap gap-2">
                    {card(ds.hi.finished_pc + "%", "Above-median depth", "per-cohort finish · n=" + ds.hi.n + " · " + ds.hi.first_depth + " words", "#065f46", "fi1")}
                    {card(ds.lo.finished_pc + "%", "Below-median depth", "per-cohort finish · n=" + ds.lo.n + " · " + ds.lo.first_depth + " words", "#C62828", "fi2")}
                    {card(ds.hi.finished + "% / " + ds.lo.finished + "%", "Same split, \"finished ≥1\"", "the inflated version, for comparison", "#9ca3af", "fi3")}
                  </div>
                </div>
              ) : null}

              {/* How deep FLWs get */}
              <div>
                <div className="text-sm font-semibold text-gray-700 mb-1">How far through the schedule FLWs get{globalTag}</div>
                <p className="text-gray-400 mb-1" style={{ fontSize: "10px" }}>Share reaching each interview, as a % of the FLWs whose schedule even <i>contains</i> that interview (a 2-interview TRS worker is not a drop-out at interview 3). Each row has its own denominator, so a later interview can show a HIGHER share than an earlier one - the pool shrinks as short-schedule cohorts drop out of it (e.g. the 119 TRE workers leave after interview 5). Compare each row to its own count, not to the row above.</p>
                {(FE.survival || []).map(function (s) {
                  var p = (s.pct_elig == null ? s.pct : s.pct_elig);
                  return bar("reached Int≥" + s.d, p, "#1565C0",
                    s.reached + " / " + (s.elig == null ? N : s.elig) + " · " + p + "%", "sv" + s.d);
                })}
              </div>

              {/* The headline of this analysis: the spread WITHIN states is larger than the spread
                  between them, so the state/partner comparison above is at the wrong altitude. Global
                  (not filtered) because it is a property of the whole population. */}
              {(function () {
                var GV = FE.geoVariance || {}, LG = (FE.byLGA || []).slice();
                if (!GV.states || !LG.length) return null;
                LG.sort(function (a, b) { return (b.finished_pc || 0) - (a.finished_pc || 0); });
                var best = LG.slice(0, 3), worst = LG.slice(-3).reverse();
                var mx = Math.max.apply(null, LG.map(function (r) { return r.finished_pc || 0; }).concat([1]));
                var row = function (r, key) {
                  return (
                    <div key={key} className="flex items-center gap-2 py-0.5" style={{ fontSize: "11px" }}>
                      <div className="text-right text-gray-700 truncate" style={{ width: "150px", flexShrink: 0 }}>{r.k}</div>
                      <div className="flex-1 bg-gray-100 rounded h-3.5" style={{ minWidth: "60px" }}>
                        <div className="h-3.5 rounded" style={{ width: Math.max(2, 100 * (r.finished_pc || 0) / mx) + "%", backgroundColor: "#1565C0" }}></div>
                      </div>
                      <div className="text-gray-500 text-right" style={{ width: "44px", flexShrink: 0 }}>n={r.n}</div>
                      <div className="text-right font-medium" style={{ width: "34px", flexShrink: 0, color: (r.finished_pc || 0) >= 60 ? "#065f46" : (r.finished_pc || 0) >= 45 ? "#F9A825" : "#C62828" }}>{r.finished_pc}%</div>
                    </div>
                  );
                };
                return (
                  <div className="rounded border border-blue-200 bg-blue-50 px-3 py-2">
                    <div className="text-sm font-semibold text-gray-700 mb-1">
                      Look below the state: that is where the variation is{globalTag}
                    </div>
                    <p className="text-xs text-gray-700 mb-2">
                      Best-to-worst <b>between the {GV.states.length} states: {GV.state_spread} points</b>. Best-to-worst
                      <b> across the {GV.n_lgas} LGAs: {GV.lga_spread} points</b>. Each state's own internal spread runs{" "}
                      {Math.min.apply(null, GV.states.map(function (x) { return x.lga_spread; }))}-{Math.max.apply(null, GV.states.map(function (x) { return x.lga_spread; }))} points,
                      so comparing states (or partners, which are nested inside them) is the wrong altitude - the same
                      state and the same partner contain both the best and the worst performers.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <div className="text-gray-500 mb-0.5" style={{ fontSize: "10px" }}>STRONGEST LGAs (per-cohort finish)</div>
                        {best.map(function (r, i) { return row(r, "b" + i); })}
                      </div>
                      <div>
                        <div className="text-gray-500 mb-0.5" style={{ fontSize: "10px" }}>WEAKEST LGAs</div>
                        {worst.map(function (r, i) { return row(r, "w" + i); })}
                      </div>
                    </div>
                    <p className="text-gray-500 mt-1" style={{ fontSize: "10px" }}>
                      Only LGAs with 20+ FLWs are shown. The useful question is what the strong LGAs do differently from
                      the weak ones in the SAME state under the SAME partner.
                    </p>
                  </div>
                );
              })()}

              {/* The one directly actionable number in the analysis - the tab had no view of it. */}
              {FE.atRisk && FE.atRisk.n ? (
                <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-gray-700">
                  <b>Reachable now: {FE.atRisk.n} FLWs.</b> Started, finished no schedule, were offered a complete one,
                  and have been silent between two and eight interview gaps - recent enough that a nudge is plausible.
                  {(FE.atRisk.byState || []).length
                    ? <span> Concentrated in {(FE.atRisk.byState || []).map(function (x) { return x.k + " (" + x.n + ")"; }).join(", ")}.</span>
                    : null}
                  {FE.atRisk.ofUnfinished
                    ? <span className="text-gray-500"> They are the recent slice of {FE.atRisk.ofUnfinished.toLocaleString()} unfinished FLWs, not the whole group.</span>
                    : null}
                  {globalTag}
                </div>
              ) : null}

              <Legend title="How this is built">
                <div><b>Grain:</b> one row per unique FLW (deduped across cohorts); metrics union their sessions across every arm.</div>
                <div><b>Per-cohort finish rate:</b> of all the cohort schedules an FLW was enrolled in, the share they have completed <b>so far</b>. Unlike "finished 1+ schedule" it does not rise simply from being in more cohorts - but read the multi-vs-single comparison with care, because it does not fall neutrally either: <b>about 22% of enrolment slots have not yet had their full schedule triggered</b>, those count as unfinished, and multi-cohort workers are more likely to be carrying one. The measure therefore understates finishing for everyone, and slightly more for multi-cohort workers.</div>
                <div><b>Tier (RFM):</b> Recency + completion rate + answer depth, each scored 1-5. Recency is measured against the freshest session in the dataset, not the wall clock, so a lagging data pull cannot push everyone into a worse tier.</div>
                <div><b>Persona:</b> rule-based behavioural segment. "Partial progress" means ≥50% of triggered interviews done but <i>no</i> schedule finished (it was previously labelled "Slow-but-finishing", which described the opposite of what it selects).</div>
                <div><b>Drill-down:</b> the tab holds one character per FLW per dimension - attributes only, no identifier - so filtering happens in your browser. "×N" is the group's share of your selection divided by its share of all FLWs.</div>
                <div><b>Colour on the right-hand %:</b> green ≥70, amber 50-69, red below 50. It is a reading aid only - for the per-cohort measure the normal range is roughly 40-70%, so amber is common and does not signal a problem.</div>
                <div><b>Co-workers in settlement</b> proxies informal peer support (the factor most consistently identified in community-health-worker retention research). <b>Pace</b> is each FLW's typical gap between interviews divided by what their own schedule asks, so subgroups on 3-day and 14-day cadences compare fairly.</div>
                <div><b>Not shown here:</b> full per-FLW detail lives in the flw_analysis.csv export.</div>
              </Legend>
            </div>
          );
        })()}

        {activeTab === "docs" && renderDocs()}
      </div>
    </div>
  );
}
