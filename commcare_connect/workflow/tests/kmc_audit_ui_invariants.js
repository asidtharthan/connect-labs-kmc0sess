/* UI-invariant gate for the KMC Audit Dashboard FLW Detail tab.
 *
 * Why this exists: parity.js proves the flag ENGINE is right. It says nothing about whether the
 * UI's summary counts agree with the rows the UI actually shows. A shipped build had the chip
 * tally reading an unfiltered cohort while the table applied the quick filter too, so "15 Green"
 * could return 8 rows. Numbers on screen that disagree with each other are a reporting defect
 * whether or not the engine is correct, so they get a gate of their own.
 *
 * The predicates are EXTRACTED from kmc_audit_dashboard.py, never re-typed here — a hand-written
 * second copy is the exact failure mode this is meant to catch.
 *
 *   node ui_invariants.js
 */
'use strict';
var fs = require('fs'),
  path = require('path');

// KMC_UI_TPL lets mutation-testing point the gate at a deliberately broken copy, to prove the gate
// still fails when the invariant is violated. A gate nobody has watched fail is not a gate.
var TPL =
  process.env.KMC_UI_TPL ||
  path.join(__dirname, '..', 'templates', 'kmc_audit_dashboard.py');
var src = fs.readFileSync(TPL, 'utf8');
var m = /RENDER_CODE = r"""([\s\S]*?)"""/.exec(src);
if (!m) {
  console.error('could not locate RENDER_CODE');
  process.exit(1);
}
var render = m[1];

/* Pull `var NAME = React.useMemo(function(){ ... }` out of the render source by brace matching,
 * and return the body. Brace matching (not regex) because the bodies contain nested braces. */
function memoBody(name) {
  var head = 'var ' + name + ' = React.useMemo(function(){';
  var i = render.indexOf(head);
  if (i < 0) throw new Error('memo not found: ' + name);
  var j = i + head.length,
    depth = 1;
  while (j < render.length && depth > 0) {
    var c = render[j];
    if (c === '{') depth++;
    else if (c === '}') depth--;
    j++;
  }
  return render.slice(i + head.length, j - 1);
}
function fnSource(sig) {
  var i = render.indexOf(sig);
  if (i < 0) throw new Error('function not found: ' + sig);
  var j = render.indexOf('{', i) + 1,
    depth = 1;
  while (j < render.length && depth > 0) {
    var c = render[j];
    if (c === '{') depth++;
    else if (c === '}') depth--;
    j++;
  }
  return render.slice(i, j);
}

var METRIC_KEYS = [
  'low_avg_visits',
  'mortality',
  'enroll_ontime',
  'zero_danger',
  'implausible_danger',
  'no_referral',
  'rounded_weights',
  'weight_loss',
  'low_weight_gain',
  'implausible_weight',
  'flat_weight',
  'gps_far',
  'hr_copycat',
  'temp_copycat',
  'spo2_copycat',
  'equipment_image_missing',
  'flw_early_discharge',
  'kmc_wrap_missing',
];
var BANDS = ['GREEN', 'YELLOW', 'RED', 'N/A'];

/* Build a deterministic synthetic cohort. Values are irrelevant here — only the band matters, and
 * bands are what both the table filter and the chip tally key on. A fixed LCG keeps runs identical. */
var seed = 20260811;
function rnd() {
  seed = (seed * 1103515245 + 12345) % 2147483648;
  return seed / 2147483648;
}
var LLOS = ['PIPN', 'NAMA', 'GHI', 'Kikapu', 'EHA', 'BERI'],
  VERS = ['V1', 'V2', 'V3'];
var rows = [];
for (var i = 0; i < 400; i++) {
  var r = {
    username: 'u' + i,
    flw_name: 'FLW ' + i,
    llo: LLOS[i % LLOS.length],
    versions: [VERS[i % VERS.length]],
    total_cases: 1 + (i % 60),
    win: null,
    in_window: true,
  };
  var red = 0,
    yel = 0;
  for (var k = 0; k < METRIC_KEYS.length; k++) {
    var p = rnd(),
      rag = p < 0.15 ? 'N/A' : p < 0.45 ? 'GREEN' : p < 0.7 ? 'YELLOW' : 'RED';
    r[METRIC_KEYS[k]] = { rag: rag, value: p * 100, num: 1, den: 2 };
    if (rag === 'RED') red++;
    else if (rag === 'YELLOW') yel++;
  }
  r.red_count = red;
  r.yellow_count = yel;
  rows.push(r);
}

var failures = [],
  checks = 0;

var bodies = {
  effM: fnSource('function effM(r,k){'),
  effRag: fnSource('function effRag(r,k){'),
  condMatch: fnSource('function condMatch(d,c){'),
  condsPass: fnSource('function condsPass(d,cs){'),
  bandTally: fnSource('function bandTally(pool, kk){'),
  baseFiltered: memoBody('baseFiltered'),
  filtered: memoBody('filtered'),
  metricTallyView: memoBody('metricTallyView'),
  metricTally: memoBody('metricTally'),
};

/* Evaluate the extracted bodies with the component's free variables supplied as parameters. */
var harness = new Function(
  'METRIC_KEYS',
  'analyzed',
  'state',
  'bodies',
  [
    'var lloFilter=state.lloFilter, verFilter=state.verFilter, search=state.search, filter=state.filter;',
    'var metricConds=state.metricConds, condMode=state.condMode, winActive=state.winActive;',
    'var sortKey=state.sortKey, sortAsc=state.sortAsc;',
    'var WINDOWED_METRICS={};',
    bodies.effM,
    bodies.effRag,
    bodies.condMatch,
    bodies.condsPass,
    bodies.bandTally,
    'var baseFiltered=(function(){' + bodies.baseFiltered + '})();',
    'var filtered=(function(){' + bodies.filtered + '})();',
    'var metricTallyView=(function(){' + bodies.metricTallyView + '})();',
    'var metricTally=(function(){' + bodies.metricTally + '})();',
    'return {baseFiltered:baseFiltered, filtered:filtered, tallyView:metricTallyView, tally:metricTally};',
  ].join('\n'),
);

function run(state) {
  return harness(METRIC_KEYS, rows, state, bodies);
}
function base(over) {
  var s = {
    lloFilter: 'all',
    verFilter: 'all',
    search: '',
    filter: 'all',
    metricConds: [],
    condMode: 'all',
    winActive: false,
    sortKey: 'red',
    sortAsc: false,
  };
  for (var k in over) s[k] = over[k];
  return s;
}
function check(label, cond) {
  checks++;
  if (!cond) failures.push(label);
}

/* ---- INVARIANT 1 ---------------------------------------------------------------------------
 * With one indicator condition active, the chip for that band must equal the number of rows the
 * table shows. Swept across every metric, every band, and every quick filter / LLO scope, because
 * the bug that shipped only appeared when a quick filter was combined with the indicator. */
var QUICK = ['all', 'any_red', 'two_red', 'any_yellow'];
var SCOPE = [
  {},
  { lloFilter: 'NAMA' },
  { verFilter: 'V3' },
  { search: 'FLW 1' },
];
for (var qi = 0; qi < QUICK.length; qi++) {
  for (var si = 0; si < SCOPE.length; si++) {
    for (var mi = 0; mi < METRIC_KEYS.length; mi++) {
      for (var bi = 0; bi < BANDS.length; bi++) {
        var k = METRIC_KEYS[mi],
          b = BANDS[bi];
        var st = base(SCOPE[si]);
        st.filter = QUICK[qi];
        st.metricConds = [{ k: k, b: b }];
        var out = run(st);
        var chip = out.tallyView[k][b];
        check(
          'chip!=rows  quick=' +
            QUICK[qi] +
            ' scope=' +
            JSON.stringify(SCOPE[si]) +
            ' ' +
            k +
            '/' +
            b +
            '  chip=' +
            chip +
            ' rows=' +
            out.filtered.length,
          chip === out.filtered.length,
        );
      }
    }
  }
}

/* ---- INVARIANT 2 ---------------------------------------------------------------------------
 * The four band chips for a metric must partition the base cohort — no row uncounted, none twice. */
for (var mi2 = 0; mi2 < METRIC_KEYS.length; mi2++) {
  var st2 = base({});
  st2.metricConds = [{ k: METRIC_KEYS[mi2], b: 'RED' }];
  var o2 = run(st2),
    t2 = o2.tallyView[METRIC_KEYS[mi2]];
  check(
    'bands do not partition base for ' + METRIC_KEYS[mi2],
    t2.GREEN + t2.YELLOW + t2.RED + t2['N/A'] === o2.baseFiltered.length,
  );
}

/* ---- INVARIANT 3 ---------------------------------------------------------------------------
 * "Red or Yellow" must equal Red + Yellow, and "Any band" must equal the whole base. */
for (var mi3 = 0; mi3 < METRIC_KEYS.length; mi3++) {
  var kk3 = METRIC_KEYS[mi3];
  var flagOut = run(base({ metricConds: [{ k: kk3, b: 'flag' }] }));
  var t3 = flagOut.tallyView[kk3];
  check(
    'flag != red+yellow for ' + kk3,
    flagOut.filtered.length === t3.RED + t3.YELLOW,
  );
  var anyOut = run(base({ metricConds: [{ k: kk3, b: 'any' }] }));
  check(
    'any band != base for ' + kk3,
    anyOut.filtered.length === anyOut.baseFiltered.length,
  );
}

/* ---- INVARIANT 4 ---------------------------------------------------------------------------
 * ALL mode is an intersection and ANY mode a union, so for the same pair of conditions
 * |ALL| <= min(|A|,|B|) <= max(|A|,|B|) <= |ANY| <= |A|+|B|, and ALL+ANY == |A|+|B| exactly. */
for (var p = 0; p + 1 < METRIC_KEYS.length; p += 3) {
  var ka = METRIC_KEYS[p],
    kb = METRIC_KEYS[p + 1];
  var nA = run(base({ metricConds: [{ k: ka, b: 'RED' }] })).filtered.length;
  var nB = run(base({ metricConds: [{ k: kb, b: 'RED' }] })).filtered.length;
  var pair = [
    { k: ka, b: 'RED' },
    { k: kb, b: 'RED' },
  ];
  var nAll = run(base({ metricConds: pair, condMode: 'all' })).filtered.length;
  var nAny = run(base({ metricConds: pair, condMode: 'any' })).filtered.length;
  check('ALL not <= min for ' + ka + '+' + kb, nAll <= Math.min(nA, nB));
  check('ANY not >= max for ' + ka + '+' + kb, nAny >= Math.max(nA, nB));
  check(
    'inclusion-exclusion broken for ' +
      ka +
      '+' +
      kb +
      ' (' +
      nAll +
      '+' +
      nAny +
      ' vs ' +
      (nA + nB) +
      ')',
    nAll + nAny === nA + nB,
  );
}

/* ---- INVARIANT 5 ---------------------------------------------------------------------------
 * The Overview scoreboard is deliberately blind to the detail tab's quick filter and search, but
 * it must still track the LLO/version scope, and its rows must sum to the scoped cohort. */
var sb = run(base({}));
for (var mi5 = 0; mi5 < METRIC_KEYS.length; mi5++) {
  var t5 = sb.tally[METRIC_KEYS[mi5]];
  check(
    'scoreboard row does not sum to cohort for ' + METRIC_KEYS[mi5],
    t5.GREEN + t5.YELLOW + t5.RED + t5['N/A'] === rows.length,
  );
}
var sbNama = run(base({ lloFilter: 'NAMA' }));
var namaN = rows.filter(function (r) {
  return r.llo === 'NAMA';
}).length;
for (var mi6 = 0; mi6 < METRIC_KEYS.length; mi6++) {
  var t6 = sbNama.tally[METRIC_KEYS[mi6]];
  check(
    'scoreboard ignores LLO scope for ' + METRIC_KEYS[mi6],
    t6.GREEN + t6.YELLOW + t6.RED + t6['N/A'] === namaN,
  );
}

/* ---- INVARIANT 6 ---------------------------------------------------------------------------
 * Clicking a scoreboard cell must land on exactly that many rows: scoreboard count (no detail-tab
 * filters) == rows once focusMetric has set the condition and cleared nothing else. */
var clean = base({});
for (var mi7 = 0; mi7 < METRIC_KEYS.length; mi7++) {
  for (var bi7 = 0; bi7 < BANDS.length; bi7++) {
    var k7 = METRIC_KEYS[mi7],
      b7 = BANDS[bi7];
    var o7 = run(base({ metricConds: [{ k: k7, b: b7 }] }));
    check(
      'scoreboard cell != landed rows for ' + k7 + '/' + b7,
      sb.tally[k7][b7] === o7.filtered.length,
    );
  }
}

console.log(
  'cohort=' +
    rows.length +
    ' metrics=' +
    METRIC_KEYS.length +
    ' checks=' +
    checks,
);
if (failures.length) {
  console.error('UI INVARIANTS FAIL — ' + failures.length + ' of ' + checks);
  failures.slice(0, 20).forEach(function (f) {
    console.error('  ' + f);
  });
  process.exit(1);
}
console.log(
  'UI INVARIANTS PASS — every on-screen count equals the rows it filters to.',
);
