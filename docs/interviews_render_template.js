// Connect Interviews — MASTER dataset dashboard (v3). DISPLAY-ONLY build.
// Data is embedded (DATA below) from dashboard_data.json — the validated master (build_master_4src.py)
// aggregated by build_dashboard_data.py and reconciled 18/18 by build_dashboard_data_audit.py
// (which sits on top of audit_e2e 26/26). All 62 cohorts.
// WHY embedded, not live: a live multi-opp pipeline pull of 64 opportunities exceeds the platform's
// 600s SSE timeout (serial per-opp CCHQ/Connect fetches) and returns nothing. Embedding the audited
// snapshot gives a 100%-accurate all-cohort dashboard now. To refresh data: re-run the offline build
// (build_master_4src -> build_dashboard_data -> audit -> re-embed) — see docs.
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
  var dimp = React.useState(false);
  var deImpact = dimp[0], setDeImpact = dimp[1];   // item 8: raw vs de-impacted (penult/last artifact)
  var lvm = React.useState("pct");
  var lineMode = lvm[0], setLineMode = lvm[1];   // funnels retention chart x-axis: pct (by interview #) | time (by real calendar days since first interview); y is % Started in both
  var lsg = React.useState({}); var hidSg = lsg[0], setHidSg = lsg[1];   // funnels line chart: hidden subgroups (custom legend toggle)
  var lineRef = React.useRef(null), lineInst = React.useRef(null);
  var barRef = React.useRef(null), barInst = React.useRef(null);
  var fvw = React.useState("retention"); var funView = fvw[0], setFunView = fvw[1];   // funnels tab: retention lines | cohort engagement (3-panel)
  var esg = React.useState("PANEL"); var engSg = esg[0], setEngSg = esg[1];            // cohort-engagement: selected subgroup
  var eng1Ref = React.useRef(null), eng1Inst = React.useRef(null);
  var eng2Ref = React.useRef(null), eng2Inst = React.useRef(null);
  var eng3Ref = React.useRef(null), eng3Inst = React.useRef(null);

  // Design + topic names come from the build (DATA.subgroupDesign / topicNames), derived from the
  // CommCare HQ interview_schedule lookup — single source of truth. Fallbacks for older data only.
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
      "EXT": ["11", "C", "99"]
    };
  }
  var TOPIC_NAMES = DATA.topicNames || { A: "Community Demographics", B: "Malaria", C: "Nutrition Prevalance and Programs",
    D: "Water & Diarrhea", E: "Community & FLW Profile", "1": "Seasonal Malaria Chemoprevention",
    "2": "Seasonal Malaria Chemoprevention 2", "3": "Bed Net Usage", "4": "Health Worker Experience",
    "5": "Family Planning", "6": "Vitamin A Supplementation", "7": "Vaccines",
    "8": "Antibiotics and ACT Use", "9": "Medicine Quality & Counterfeiting",
    "10": "Malaria 2", "11": "Water & Diarrhea 2", "12": "Community & FLW Profile 2", "13": "Medicine Quality & Counterfeiting 2", "14": "Malaria 5",
    "8S": "Antibiotics and ACT Use 2", "8L": "Antibiotics and ACT Use 3", "10S": "Malaria 3", "10L": "Malaria 4", "11S": "Water & Diarrhea 3", "11L": "Water & Diarrhea 4", "13L": "Medicine Quality & Counterfeiting 3" };
  var SG_ORDER = ["TRS", "TRE", "ABT1-A", "ABT1-B", "ABT2-A", "ABT2-B", "PANEL", "ABT3-A", "ABT3-B", "2WT", "EXT"];
  // Subgroups whose Connect funnel (Invited/Accepted/Claimed) hasn't been pulled yet (cohorts present
  // in the interview data but missing from the Connect snapshot). Their Invited=0 means "not pulled",
  // not "nobody invited" — flagged in the UI so the 0s aren't misread.
  var CONNECT_PENDING = DATA.connectPendingSubgroups || [];
  function connPending(sg) { return CONNECT_PENDING.indexOf(sg) >= 0; }
  // 6 states in the spec order (Notes doc): not-applicable -> completed
  var STATES = ["not-applicable", "not-available-yet", "available-not-started", "available-missed-overdue", "started-not-completed", "completed"];
  var STATES5 = ["not-available-yet", "available-not-started", "available-missed-overdue", "started-not-completed", "completed"];
  // Topic-completion display order: completed (left/first) → not-available-yet; not-applicable parked last.
  // Used by the stacked bar, its legend, the detail table + drilldown, and the heatmap so they all read the same way.
  var BAR_ORDER = ["completed", "started-not-completed", "available-not-started", "available-missed-overdue", "not-available-yet", "not-applicable"];
  var BAR_ORDER5 = ["completed", "started-not-completed", "available-not-started", "available-missed-overdue", "not-available-yet"];
  var STATE_LABEL = { "not-applicable": "Not applicable", "not-available-yet": "Not available yet",
    "available-not-started": "Available, not started", "available-missed-overdue": "Available, missed/overdue",
    "started-not-completed": "Started, not completed", "completed": "Completed" };
  var STATE_COLOR = { "not-applicable": "#e5e7eb", "not-available-yet": "#6366f1",
    "available-not-started": "#f59e0b", "available-missed-overdue": "#b91c1c",
    "started-not-completed": "#06b6d4", "completed": "#16a34a" };
  var STATE_DEF = {
    "not-applicable": "topic isn't part of this cohort's design",
    "not-available-yet": "in the cohort, but not yet released per today's date, the topic's place in the schedule, and the cohort's training date",
    "available-not-started": "available for the FLW to trigger from the app, but not yet started",
    "available-missed-overdue": "the FLW missed this topic's window — the next topic is already available",
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
  var SG_COLOR = { "TRS": "#1f77b4", "TRE": "#17becf", "ABT1-A": "#2ca02c", "ABT1-B": "#d62728", "ABT2-A": "#9467bd", "ABT2-B": "#8c564b", "PANEL": "#e377c2", "ABT3-A": "#f58231", "ABT3-B": "#bcbd22", "2WT": "#334155", "EXT": "#c51b8a" };
  // FLW × Topic matrix cell glyphs, indexed by STATES order (0 not-applicable … 5 completed)
  var CELL_GLYPH = ["", "·", "○", "!", "◐", "✓"];
  var MATRIX_TOPIC_ORDER = ["A", "B", "C", "D", "E", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "8S", "8L", "10S", "10L", "11S", "11L", "13L", "99"];
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
    var STATE6 = ["not-applicable", "not-available-yet", "available-not-started", "available-missed-overdue", "started-not-completed", "completed"];
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
  function pctTxt(v) { return v == null ? "—" : v + "%"; }
  function pctOf(a, b) { return b > 0 ? Math.round((a / b) * 100) + "%" : "—"; }

  // ---- line chart (Interview Completion Funnels) ----
  React.useEffect(function () {
    if (activeTab !== "funnels") return;
    if (!lineRef.current || !window.Chart) return;
    if (lineInst.current) lineInst.current.destroy();
    // Both modes show retention (% Started) on Y. "pct" = x is the interview ordinal (evenly spaced);
    // "time" = x is real calendar days since the FLW's first interview (each dot at the day it landed).
    var byDay = lineMode === "time";
    var maxLen = 0; DATA.lineSeries.forEach(function (s) { maxLen = Math.max(maxLen, s.pts.length); });
    var labels = []; for (var i = 1; i <= maxLen; i++) labels.push("Int " + i);
    lineInst.current = new window.Chart(lineRef.current.getContext("2d"), {
      type: "line",
      data: { labels: byDay ? undefined : labels, datasets: DATA.lineSeries.map(function (s) {
        var raw = (deImpact && s.pts_di && s.pts_di.length) ? s.pts_di : s.pts;
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
        plugins: { title: { display: true, text: byDay ? "% FLWs still starting each interview, plotted against real days since their first interview — each dot is an interview at the day it landed; two dots on ~the same day = the last two triggered back-to-back (penultimate artifact)" : "% FLWs who started each interview round (denominator = # FLWs initiated, constant per subgroup) — solid = subgroup fully settled, dotted = subgroup still in progress, line ends where interviews aren't offered yet" }, legend: { display: false } },
        scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "% Started" } },
          x: byDay ? { type: "linear", beginAtZero: true, title: { display: true, text: "Days since first interview" } } : { title: { display: true, text: "Interview #" } } } }
    });
    return function () { if (lineInst.current) { lineInst.current.destroy(); lineInst.current = null; } };
  }, [activeTab, deImpact, hidSg, lineMode]);

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
    var maxApp = Math.max.apply(null, tsRows.map(function (t) { return t.applicable || 0; })) || 1;
    barInst.current = new window.Chart(barRef.current.getContext("2d"), {
      type: "bar",
      data: { labels: tsRows.map(function (t) { return t.label || (t.code + " · " + (TOPIC_NAMES[t.code] || t.code)); }),
        datasets: barStates.map(function (st) {
          return { label: STATE_LABEL[st],
            data: tsRows.map(function (t) { if (isCount) return t[st] || 0; var denom = excl ? (t.applicable || 0) : (t.total || 0); return denom ? Math.round(1000 * t[st] / denom) / 10 : 0; }),
            backgroundColor: STATE_COLOR[st] }; }) },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: "y",
        plugins: { title: { display: true, text: (topicGroupMode === "theme" ? "FLW status distribution by THEME (related topics pooled)" : "FLW status distribution by topic") + (isCount ? " — # of applicable FLWs" : (excl ? " — % of applicable FLWs (stacks to 100%)" : " — % of claimed FLWs (stacks to 100%)")) }, legend: { position: "bottom", title: { display: true, text: "⇄ Toggle: click any status in the legend below to show / hide it in the chart", color: "#4f46e5", font: { weight: "bold", size: 11 } } },
          tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ": " + ctx.parsed.x + (isCount ? "" : "%"); } } } },
        scales: { x: { stacked: true, max: isCount ? maxApp : 100, title: { display: true, text: isCount ? "# of FLWs the topic applies to" : "% of claimed FLWs" } }, y: { stacked: true, ticks: { autoSkip: false, font: { size: 10 } } } } }
    });
    return function () { if (barInst.current) { barInst.current.destroy(); barInst.current = null; } };
  }, [activeTab, tableSub, topicChart, tcMode, topicGroupMode, naMode]);

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
    ctx.fillStyle = "#111827"; ctx.font = "bold 16px sans-serif";
    ctx.fillText("Cohort Engagement — " + engSg + "  (as of " + (DATA.today || "") + ")", pad, 24);
    var y = title + pad;
    cs.forEach(function (c) { ctx.drawImage(c, pad, y); y += c.height + gap; });
    var a = document.createElement("a"); a.download = "cohort_engagement_" + engSg + ".png"; a.href = out.toDataURL("image/png"); a.click();
  }

  React.useEffect(function () {
    if (activeTab !== "funnels" || funView !== "engagement" || !window.Chart) return;
    [eng1Inst, eng2Inst, eng3Inst].forEach(function (r) { if (r.current) { r.current.destroy(); r.current = null; } });
    var ce = (DATA.cohortEngagement || {})[engSg];
    if (!ce) return;
    var labels = ce.weeks.map(fmtWk), gt = ce.gap_thresh;
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
        plugins: [barTopLabels("#1565C0"), whiteBg]
      });
    }
    if (eng2Ref.current) {
      eng2Inst.current = new window.Chart(eng2Ref.current.getContext("2d"), {
        type: "line",
        data: { labels: labels, datasets: [
          { label: "Finished: completed all interviews", data: ce.finished_pct, borderColor: "#00695C", backgroundColor: "#00695C" },
          { label: "Steady: never a gap > " + gt + " days", data: ce.steady_pct, borderColor: "#2E7D32", backgroundColor: "#2E7D32" },
          { label: "Inconsistent: at least one " + (gt + 1) + "+ day gap", data: ce.incons_pct, borderColor: "#F9A825", backgroundColor: "#F9A825" },
          { label: "Dropped off: silent 14+ days (not finished)", data: ce.drop_pct, borderColor: "#C62828", backgroundColor: "#C62828" }
        ].map(function (d) { return Object.assign({ fill: false, tension: 0.2, borderWidth: 3, pointRadius: 3, pointHoverRadius: 6 }, d); }) },
        options: { responsive: true, maintainAspectRatio: false, layout: { padding: { top: 16 } },
          plugins: { legend: { position: "bottom", labels: { boxWidth: 14, font: { size: 11 } } },
            title: { display: true, text: "Engagement quality among FLWs who started" },
            tooltip: { callbacks: { label: function (c) { return c.dataset.label.split(":")[0] + ": " + c.parsed.y + "%"; } } } },
          scales: { y: { beginAtZero: true, max: 100, title: { display: true, text: "% of started FLWs" }, ticks: { callback: function (v) { return v + "%"; } } } } },
        plugins: [linePointLabels(), whiteBg]
      });
    }
    if (eng3Ref.current) {
      eng3Inst.current = new window.Chart(eng3Ref.current.getContext("2d"), {
        type: "bar",
        data: { labels: labels, datasets: [
          { label: "Finished: completed all interviews", data: ce.finished, backgroundColor: "#00695C" },
          { label: "Active: interview within last 7 days (started earlier)", data: ce.active, backgroundColor: "#2E7D32" },
          { label: "Started this week (first-ever interview)", data: ce.new, backgroundColor: "#42A5F5" },
          { label: "Slow: last interview 8-14 days ago", data: ce.slow, backgroundColor: "#F9A825" },
          { label: "Quiet: 14+ days since last interview (not finished)", data: ce.quiet, backgroundColor: "#C62828" }
        ] },
        options: { responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { boxWidth: 14, font: { size: 11 } } },
            title: { display: true, text: "Status of started FLWs at each week's end" },
            tooltip: { callbacks: { label: function (c) { return c.dataset.label.split(":")[0] + ": " + c.parsed.y; } } } },
          scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true, title: { display: true, text: "FLWs" } } } },
        plugins: [stackedSegLabels(), whiteBg]
      });
    }
    return function () { [eng1Inst, eng2Inst, eng3Inst].forEach(function (r) { if (r.current) { r.current.destroy(); r.current = null; } }); };
  }, [activeTab, funView, engSg]);

  function renderEngagement() {
    var CE = DATA.cohortEngagement || {};
    var sgs = (CE["ALL"] ? ["ALL"] : []).concat(SG_ORDER.filter(function (sg) { return CE[sg]; }));
    var ce = CE[engSg];
    var scope = engSg === "ALL" ? "all cohorts" : engSg;
    return (
      <React.Fragment>
        <div className="flex flex-wrap items-center gap-2 px-1">
          <span className="text-xs font-medium text-gray-600">Cohort:</span>
          {sgs.map(function (sg) { return <span key={sg}>{subBtn(engSg, sg, setEngSg, sg === "ALL" ? "All cohorts" : sg)}</span>; })}
          {ce ? <button onClick={downloadEngPng} title="Download all 3 panels as one PNG" className="ml-auto px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-100">↓ PNG</button> : null}
        </div>
        {!ce ? (
          <div className="text-sm text-gray-500 px-2 py-6">No engagement data for {engSg} yet.</div>
        ) : (function () {
          var n = ce.weeks.length - 1;
          var started = ce.total_started, finished = ce.finished_pct[n], drop = ce.drop_pct[n];
          var activeNow = ce.active[n];
          var endTxt = ce.end_date ? (function () { var p = ce.end_date.split("-"); return MON[parseInt(p[1], 10) - 1] + " " + parseInt(p[2], 10); })() : null;
          var kpi = [
            { label: "Started interviewing", val: started, sub: "unique FLWs", color: "#1565C0" },
            { label: "Finished", val: finished + "%", sub: "completed all interviews", color: "#00695C" },
            { label: "Active now", val: activeNow, sub: "interviewed in last 7d", color: "#2E7D32" },
            { label: "Dropped off", val: drop + "%", sub: "silent 14+, not finished", color: "#C62828" }
          ];
          return (
            <React.Fragment>
              <div className="text-xs bg-indigo-50 border border-indigo-100 rounded px-3 py-2 text-gray-700">
                {engSg === "ALL" ? (
                  <span><b>Program-wide roll-up.</b> <b>{started}</b> FLWs have started interviewing across all cohorts; <b>{finished}%</b> have <b>finished</b> their whole schedule and only <b>{drop}%</b> dropped off (silent 14+ without finishing). Cohorts run different-length schedules, so read this as the recruitment + completion picture; for one cohort's engagement detail, pick it above.</span>
                ) : (
                  <span><b>Read this as recruitment + engagement, not attrition.</b> Of <b>{started}</b> FLWs who started interviewing in {scope}, <b>{finished}%</b> <b>finished</b> all their interviews and <b>{activeNow}</b> are active right now; only <b>{drop}%</b> truly dropped off (silent 14+ days without finishing). A dip in the retention curve is mostly <i>finishers</i>, <i>later starts</i> and <i>slower cadence</i> — not people quitting.{ce.ended && endTxt ? <span> This cohort's schedule ended ~<b>{endTxt}</b>.</span> : null}</span>
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
                <div><b>Panel 1 — recruitment:</b> cumulative FLWs who have started interviewing (appeared in the interview data). Not invited counts.</div>
                <div><b>Panel 2 — engagement quality:</b> each starter is <b>Finished</b> (completed all their interviews), Steady (never a gap &gt; {ce.gap_thresh} days), Inconsistent (≥1 gap of {ce.gap_thresh + 1}+ days), or Dropped off (silent 14+ days without finishing). Finished outranks the rest — a completer's silence is <i>done</i>, not dropout. <b>Steady is a one-way ratchet</b> — a single long gap moves an FLW to Inconsistent permanently.</div>
                <div><b>Panel 3 — status now:</b> where every starter stands at each week's end — Finished, Active (≤7d), Started-this-week, Slow (8–14d), Quiet (14+d). Totals equal Panel 1 by construction.</div>
                <div className="text-gray-400">x-axis is the week-ending date; the grid ends at the last interview date (so an ended cohort freezes there). {engSg === "ALL" ? ce.gap_thresh + "-day gap threshold (program-wide default — cohorts here have mixed cadences)" : ce.gap_thresh + " = 2× the " + engSg + " interview cadence"}; the 14-day dropout window is cadence-independent.{ce.ended && endTxt ? " Cohort schedule ended ~" + endTxt + "." : ""}</div>
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

  // Full OCS session link (same URL the "view ↗" links use) — for the table and CSV export.
  function sessionUrl(sid) { return sid ? "https://www.openchatstudio.com/a/Vaccine_Coach/chatbots/e/cc01d032-5931-4bdd-a4b2-6f05f4f72f88/s/" + sid + "/view/" : ""; }

  // Reusable multi-select checkbox dropdown (mirrors the mbw_monitoring column picker). Called as a
  // plain function returning JSX (like subBtn) so it holds no component state of its own — open state
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
        <td className={td + " text-right text-green-700 font-semibold"}>{iv.pct_completed == null ? "—" : iv.pct_completed + "%"}</td>
      </tr>
    );
  }

  var c = DATA.counts;
  var maxIv = Math.max.apply(null, (DATA.dropoff.subgroups || []).map(function (s) { return s.interviews.length; }));
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
      rows.push([r.connect_id, sessionCohort(r) || "", r.interview || "", r.completed ? "Completed" : (r.started ? "Started" : "—"), r.created_at || "", sessionUrl(r.session_id)]);
    });
    return rows;
  }
  function matCsvRows(list) {
    var rows = [["connect_id", "cohort", "subgroup"].concat(MTOPICS)];
    list.forEach(function (r) {
      var topics = SUBGROUP_DESIGN[r.g] || [], cb = {};
      topics.forEach(function (t, i) { cb[t] = r.s[i]; });
      var row = [r.f, r.c, r.g];
      MTOPICS.forEach(function (t) { row.push(t in cb ? STATE_LABEL[STATES[cb[t]]] : ""); });
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
  var FM = DATA.flwMatrix || [];
  var flwInfo = {};   // connect_id -> { g: subgroup, cohorts: {cohort:1}, u: untrained }
  var cohortSG = {};  // cohort id -> subgroup (global, for session-level subgroup filtering)
  FM.forEach(function (r) {
    var fi = flwInfo[r.f] || (flwInfo[r.f] = { g: r.g, cohorts: {}, cg: {}, u: 0 });
    fi.cohorts[r.c] = 1; fi.cg[r.c] = r.g; if (r.u) fi.u = 1;   // cg: cohort -> subgroup (topic disambiguation)
    cohortSG[r.c] = r.g;
  });
  // The FLW's cohort id(s). A live OCS session carries no cohort and an FLW can be claimed in several
  // cohorts, so this lists all (comma-joined); "" if the FLW isn't claimed.
  function cohortsFor(cid) { var fi = flwInfo[cid]; return fi ? Object.keys(fi.cohorts).sort().join(", ") : ""; }
  // Exact cohort for ONE session. Best source is the OCS session's own state (r.cohort_id — the cohort the
  // bot recorded on that session); every session from ~early May onward has it. Sessions before that predate
  // the field, so the exact cohort is simply not in the source data — for those we ONLY infer a cohort when
  // it is UNAMBIGUOUS (a single-cohort FLW, or exactly one of the FLW's cohorts runs the session's topic, or
  // a single trigger match). If it can't be pinned to exactly one, show "—" rather than a misleading list.
  var trigCohort = {};
  liveRows("triggers").forEach(function (r) {
    var cid = r.connect_id || r.username || "";
    var iv = (r.next_interview == null || r.next_interview === "") ? "" : String(r.next_interview);
    var ch = r.cohort_id || "";
    if (cid && iv && ch) { var k = cid + "|" + iv; (trigCohort[k] || (trigCohort[k] = {}))[ch] = 1; }
  });
  function sessionCohort(r) {
    if (r.cohort_id) return r.cohort_id;   // exact — from the OCS session state
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
    return "";   // multi-cohort FLW on a pre-cohort-tag session → not recoverable → "—"
  }
  var fSubgroups = SG_ORDER.filter(function (sg) { return FM.some(function (r) { return r.g === sg; }); });
  var fCohorts = Object.keys(FM.reduce(function (a, r) { a[r.c] = 1; return a; }, {})).sort();
  var MTOPICS = MATRIX_TOPIC_ORDER.filter(function (t) {
    return fSubgroups.some(function (sg) { return (SUBGROUP_DESIGN[sg] || []).indexOf(t) >= 0; });
  });
  var anyFilter = !!(fSg.length || fCo.length || fSt.length || fTr.length || fTopic.length || gq);
  function clearFilters() { setGSearch(""); setFSg([]); setFCo([]); setFSt([]); setFTr([]); setFTopic([]); setGPage(0); }
  // Sessions table: the cohort/subgroup filters match the SESSION'S OWN resolved cohort (sessionCohort),
  // so the filter and the COHORT_ID column always agree — filtering "1PE1" shows only the sessions that
  // are 1PE1, not every session of an FLW who happens to also be in 1PE1. Sessions whose exact cohort
  // isn't recoverable ("—") therefore don't match a specific cohort/subgroup filter. Trained/untrained
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
            <p className="text-xs text-gray-400 mt-1">Data as of {DATA.built_at || DATA.today || "—"} · auto-refreshes daily ~06:00 UTC</p>
          </div>
          <button onClick={function () { window.location.reload(); }}
            title="Data is rebuilt by the daily job; this just reloads the page — it does not pull new data on click."
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
            to a known program design (new program type?) — data is collected but hidden until a design is added:{" "}
            <span className="font-mono">{DATA.unmappedCohorts.join(", ")}</span>
          </div>
        ) : null}
      </div>

      <div className="bg-white rounded-lg shadow-sm">
        <div className="border-b border-gray-200 px-5">
          <nav className="-mb-px flex space-x-6">
            {[["overview", "Overview"], ["table", "Table View"], ["funnels", "Interview Completion Funnels"], ["fullretention", "Full Retention Table"], ["breakdowns", "Breakdowns"]].map(function (t) {
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
              {[["Cohorts", c.cohorts], ["Unique FLWs", c.flws], ["Interviews started", c.started],
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
              <p className="text-xs text-gray-400 mb-2"># FLWs who completed each interview number — completion beyond the 1st interview, not just the first.</p>
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
                                {iv ? iv.completed : "—"}
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
                      {sessFiltered.length} sessions{ocsLive.length ? " (live OCS)" : " (embedded sample — live pipeline not loaded)"}{anyFilter ? " matching" : ""}
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
                            var label = r.completed ? "Completed" : (r.started ? "Started" : "—");
                            var cls = r.completed ? "text-green-700 font-medium" : (r.started ? "text-lime-700" : "text-gray-400");
                            return (
                              <tr key={idx} className="hover:bg-gray-50">
                                <td className={td + " font-mono text-xs"}>{r.connect_id}</td>
                                <td className={td + " font-mono text-xs text-gray-600"} title={sessionCohort(r)}>{sessionCohort(r) || "—"}</td>
                                <td className={td}>{r.interview || "—"}</td>
                                <td className={td + " " + cls}>{label}</td>
                                <td className={td + " text-gray-500"}>{r.created_at || "—"}</td>
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
                      {matFiltered.length} FLW×cohort rows{anyFilter ? " matching" : ""} · one row per claimed FLW, one column per topic — hover a cell for its status.
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
                                  if (!(t in cb)) return <td key={t} className="px-2 py-1 text-center text-gray-200">·</td>;
                                  var code = cb[t];
                                  var _sid = sessByKey[r.f + "|" + t];
                                  var _cell = _sid
                                    ? <a href={sessionUrl(_sid)} target="_blank" rel="noopener noreferrer" style={{ color: "#fff", fontWeight: 700, textDecoration: "none" }}>{CELL_GLYPH[code]}<span style={{ fontSize: "10px", verticalAlign: "super", color: "#38bdf8", fontWeight: 700 }}>↗</span></a>
                                    : CELL_GLYPH[code];
                                  return <td key={t} className={"px-2 py-1 text-center text-xs" + (_sid ? " cursor-pointer" : "")} title={(TOPIC_NAMES[t] || t) + " — " + STATE_LABEL[STATES[code]] + (_sid ? " · click ↗ to open the OCS session" : "")}
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
                <p className="text-xs text-gray-400 px-1">Per-FLW status by topic, across all claimed FLWs (each topic stacks to 100%). Click a topic to break it down by cohort.</p>
                <p className="text-xs text-gray-400 px-1">Each bar counts <span className="font-medium text-gray-500">enrollment slots</span> for that topic (claimed FLW × cohort — the completion-rate base), not unique FLWs. It includes people enrolled but not yet started, and counts anyone in two cohorts twice, so a bar can exceed the Overview unique-FLW total.</p>
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
                  <p className="text-xs text-gray-400 px-1">Excludes “not applicable”: the 5 real statuses rescale to <span className="font-medium text-gray-500">100% of the interviews that apply</span>.</p>
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
                        var has = (DATA.topicStatusCohort[t.code] || []).length > 0;
                        function p(s, tot) { return tcMode === "count" ? s : (tot ? Math.round(1000 * s / tot) / 10 + "%" : "—"); }
                        var rows = [];
                        rows.push(
                          <tr key={t.code} className={"hover:bg-gray-50 " + (has ? "cursor-pointer" : "")}
                            onClick={has ? function () { var n = Object.assign({}, topicExp); n[t.code] = !open; setTopicExp(n); } : null}>
                            <td className={td + " font-medium"}>{has ? (open ? "▾ " : "▸ ") : ""}{t.code} · {TOPIC_NAMES[t.code] || t.code}</td>
                            {BAR_ORDER.map(function (s) {
                              return <td key={s} className={td + " text-right" + (s === "completed" ? " text-green-700 font-medium" : " text-gray-600")}>{p(t[s], t.total)}</td>;
                            })}
                          </tr>
                        );
                        if (open) {
                          var cohRows = DATA.topicStatusCohort[t.code] || [];
                          rows.push(
                            <tr key={t.code + "-exp"} className="bg-gray-50">
                              <td className={td} colSpan={STATES.length + 1} style={{ padding: 0 }}>
                                <div className="my-2 ml-8 mr-3 border-l-2 border-gray-300 pl-3">
                                  <div className="text-xs font-medium text-gray-500 mb-1">
                                    By cohort — {t.code} · {TOPIC_NAMES[t.code] || t.code} ({cohRows.length} cohort{cohRows.length === 1 ? "" : "s"})
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
            </div>
            {funView === "engagement" && renderEngagement()}
            {funView === "retention" && (
            <React.Fragment>
            <div className="flex flex-wrap items-center gap-2 px-1">
              <span className="text-xs font-medium text-gray-600">X-axis:</span>
              {subBtn(lineMode, "pct", setLineMode, "By interview #")}
              {subBtn(lineMode, "time", setLineMode, "By calendar day")}
              <span className="mx-1 text-gray-300">|</span>
              <span className="text-xs font-medium text-gray-600">Penult/last artifact:</span>
              {subBtn(deImpact ? "di" : "raw", "raw", function () { setDeImpact(false); }, "Raw")}
              {subBtn(deImpact ? "di" : "raw", "di", function () { setDeImpact(true); }, "De-impacted")}
              {deImpact ? (
                <span className="inline-flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                  <span title={"FLWs removed from the last interview's Started (started last but not penultimate, triggered back-to-back):\n" + Object.keys(DATA.deimpact || {}).sort().map(function (sg) { return "  " + sg + ": " + DATA.deimpact[sg].count; }).join("\n") + "\n  Total: " + Object.keys(DATA.deimpact || {}).reduce(function (a, sg) { return a + DATA.deimpact[sg].count; }, 0)}
                    className="cursor-help font-bold border border-amber-400 rounded-full w-4 h-4 inline-flex items-center justify-center shrink-0">ℹ</span>
                  Removes FLWs who started only the LAST interview (skipped the penultimate — triggered back-to-back) from the last interview's Started, revealing the true decline. Hover ℹ for per-subgroup counts. Affects the line chart &amp; drop-off %Started below.
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
                    title={off ? "Hidden — click to show" : "Click to hide" + (dashed ? " · dashed = still in progress" : "")}
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
              <div><b>Eligible</b> = # FLWs initiated (constant per group — the retention base). <b>Triggered</b> = the bot prompted that interview. <b>Started</b> = an OCS session exists. <b>Completed</b> = session reached interview_complete.</div>
              <div><b>% Started</b> = Started ÷ Eligible · <b>% Triggered</b> = Triggered ÷ Eligible · <b>% Completed</b> = Completed ÷ Started.</div>
            </Legend>

            {CONNECT_PENDING.length ? (
              <div className="text-xs bg-amber-50 border border-amber-200 rounded px-3 py-2 text-amber-800">
                ⏳ <b>Connect funnel pending for: {CONNECT_PENDING.join(", ")}.</b> These cohorts are live in the interview data (Triggered/Started/Completed are correct), but their Connect leg (Invited/Accepted/Started&amp;Completed Learn/Claimed) hasn&#39;t been pulled yet — it shows 0 until the next successful Connect pull. Cohort counts and interview funnels are complete.
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
                        <td className={td + " font-medium"}>{s.sg} <span className="text-gray-400">({s.cohorts_n})</span>{connPending(s.sg) ? <span title="Connect funnel not pulled yet — Invited/Accepted/Claimed pending" className="ml-1 text-amber-600">⏳</span> : null}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? <span className="text-amber-600" title="pending Connect pull">⏳</span> : c.invited}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "—" : c.accepted}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "—" : c.learn_started}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "—" : c.learn_completed}</td>
                        <td className={td + " text-right"}>{connPending(s.sg) ? "—" : c.claimed}</td>
                        <td className={td + " text-right"}>{c.flw_reg}</td>
                        <td className={td + " text-right font-medium"}>{c.initiated}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="overflow-x-auto">
              <h3 className="text-sm font-semibold text-gray-700 px-1 py-1">Interview drop-off — by interview, all topics</h3>
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
                        <td className={td + " font-bold text-indigo-800"} colSpan={9}>{open ? "▾" : "▸"} {s.sg} — {(DATA.dropoff.cohorts[s.sg] || []).length} cohorts</td>
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
                                    <div className="text-xs font-medium text-gray-500 mb-1">{co.cohort} — {co.interviews.length} interview{co.interviews.length === 1 ? "" : "s"}</div>
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
                                              <td className={td}>{iv.name}</td>
                                              <td className={td + " text-right"}>{iv.eligible}</td>
                                              <td className={td + " text-right"}>{iv.triggered}</td>
                                              <td className={td + " text-right text-gray-500"}>{iv.pct_trig}%</td>
                                              <td className={td + " text-right"}>{iv.started}</td>
                                              <td className={td + " text-right text-green-700 font-semibold"}>{iv.pct_started}%</td>
                                              <td className={td + " text-right"}>{iv.completed}</td>
                                              <td className={td + " text-right text-green-700 font-semibold"}>{iv.pct_completed == null ? "—" : iv.pct_completed + "%"}</td>
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
              <h3 className="text-sm font-semibold text-gray-700 mr-2">Full retention table — Connect funnel → every interview (one row per subgroup)</h3>
              <button onClick={copyRetention} className="px-3 py-1.5 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-700">⧉ Copy</button>
              <button onClick={downloadRetention} className="px-3 py-1.5 text-sm rounded-md border border-gray-300 hover:bg-gray-100">↓ CSV</button>
              <span className="text-xs text-gray-400">Copy pastes tab-separated into Sheets/Excel.</span>
            </div>
            <Legend title="Column definitions">
              <div><b>Connect funnel</b> (unique FLWs per subgroup): <b>Invited</b> → <b>Accepted</b> → <b>Started Learn</b> → <b>Completed Learn</b> → <b>Claimed</b> (downloaded the opportunity) → <b>FLW Reg</b> (also registered in CommCare HQ) → <b># Initiated</b> (submitted any Welcome/start form — the retention base).</div>
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
                    <th className={th + " text-right border-r-2 border-gray-300 border-b"} rowSpan={2} title="Unique FLWs with any Welcome/start form — the retention base (denominator for the % columns)"># Initiated</th>
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
                            <td key={i + "t"} className={td + " text-gray-200 border-l-2 border-gray-300"}>—</td>,
                            <td key={i + "e"} className={td}></td>, <td key={i + "tr"} className={td}></td>,
                            <td key={i + "s"} className={td}></td>, <td key={i + "c"} className={td}></td>,
                            <td key={i + "ci"} className={td}></td>,
                          ];
                          return [
                            <td key={i + "t"} className={td + " border-l-2 border-gray-300 font-medium text-gray-600"} title={iv.name}>{iv.topic}</td>,
                            <td key={i + "e"} className={td + " text-right text-gray-400"}>{iv.eligible}</td>,
                            <td key={i + "tr"} className={td + " text-right"}>{iv.triggered} <span className="text-gray-400">{iv.pct_trig}%</span></td>,
                            <td key={i + "s"} className={td + " text-right"}>{iv.started} <span className="text-gray-400">{iv.pct_started}%</span></td>,
                            <td key={i + "c"} className={td + " text-right text-green-700"}>{iv.completed} <span className="text-gray-400">{iv.pct_completed == null ? "—" : iv.pct_completed + "%"}</span></td>,
                            <td key={i + "ci"} className={td + " text-right font-semibold " + (iv.pct_completed_base == null ? "text-gray-400" : "text-green-800")}>{iv.pct_completed_base == null ? "—" : iv.pct_completed_base + "%"}</td>,
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
                          <td className={td + " text-right text-gray-500"}>{r.avg_words == null ? "—" : r.avg_words}</td>
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
                          <td className={td + " text-right text-gray-600"}>{_q == null ? "—" : _q}</td>
                          <td className={td + " text-right"}>{none ? "—" : r.flws}</td><td className={td + " text-right"}>{none ? "—" : r.ist}</td>
                          <td className={td + " text-right text-green-700 font-medium"}>{none ? "—" : r.icmp}</td>
                          <td className={td + " text-right text-gray-500"}>{pctTxt(r.pct)}</td>
                          <td className={td + " text-right text-gray-500"}>{r.avg_words == null ? "—" : r.avg_words}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {bdSub === "ab" && (
              <div className="overflow-x-auto">
                <p className="text-xs text-gray-400 px-1 py-1">A/B experimental arms (ABT1 &amp; ABT2 only). % Completed = completed ÷ started.</p>
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
                          <td className={td + " text-right text-gray-500"}>{r.avg_words == null ? "—" : r.avg_words}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
