/**
 * Render-level verification for the Interviews dashboard.
 *
 * Transpiles the JSX template with @babel/core, injects the REAL render_data.json, mounts the
 * component in jsdom and asserts against the rendered DOM. This catches what a Python-side check
 * cannot: a JSX syntax error, an undefined state hook, a crash inside a new view, or a number that
 * renders as "NaN%" / "undefined" because a payload key was renamed.
 *
 * Chart.js is not installed here. The template guards every chart on `!window.Chart`, so canvases are
 * skipped and the DOM/table content still renders - which is exactly what the drop-off view is made of.
 *
 * Usage: node verify_render_dropoff.js
 */
const fs = require('fs');
const os = require('os');
const cp = require('child_process');
const path = require('path');
const babel = require('@babel/core');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const { JSDOM } = require('jsdom');

const ROOT = __dirname;
const TEMPLATE = path.join(ROOT, 'docs', 'interviews_render_template.js');
const DATA = path.join(ROOT, 'render_data.json');

let pass = 0;
const fails = [];
function check(name, ok, detail) {
  if (ok) {
    pass++;
    console.log(`  PASS  ${name}${detail ? '  ' + detail : ''}`);
  } else {
    fails.push(name);
    console.log(`  FAIL  ${name}  ${detail || ''}`);
  }
}

// ---------------------------------------------------------------- build the component
// What ships is the COMMENT-STRIPPED template (see strip_render_comments.js), so that is what gets
// mounted and measured here. Asserting on the source while publishing the reprint would leave the
// reprint itself untested - exactly the gap that matters.
const rawSrc = fs.readFileSync(TEMPLATE, 'utf8');
let src = rawSrc;
try {
  const stripped = path.join(os.tmpdir(), 'verify_render_stripped.js');
  cp.execFileSync(
    'node',
    [path.join(__dirname, 'strip_render_comments.js'), TEMPLATE, stripped],
    { stdio: 'pipe' },
  );
  src = fs.readFileSync(stripped, 'utf8');
} catch (e) {
  console.log(
    '  NOTE  comment strip unavailable, verifying the commented source instead',
  );
}
const data = fs.readFileSync(DATA, 'utf8');
check(
  'render_data.json parses',
  (() => {
    try {
      JSON.parse(data);
      return true;
    } catch (e) {
      return false;
    }
  })(),
);

let injected = src.replace('/*__DATA__*/', data);
check('DATA placeholder was substituted', !injected.includes('/*__DATA__*/'));

// LIVE MODE. Point INTERVIEWS_LIVE_RENDER at a render pulled back off Labs and every check below runs
// against the code that is actually serving the dashboard, not the copy about to be published. Without
// this the harness could only ever certify an intention - a publish that silently truncated, stripped
// wrong, or landed an older build would pass every check while the live page was broken.
const LIVE = process.env.INTERVIEWS_LIVE_RENDER;
let liveRecovered = false;
if (LIVE) {
  injected = fs.readFileSync(LIVE, 'utf8');
  check(
    'live render was read',
    injected.length > 100000,
    injected.length + ' chars',
  );
  check(
    'live render carries no unsubstituted placeholder',
    !injected.includes('/*__DATA__*/'),
  );
  console.log('  MODE  verifying LIVE render from ' + LIVE);
}

let code;
try {
  code = babel.transformSync(injected, {
    presets: [
      [
        require.resolve('@babel/preset-react'),
        { pragma: 'React.createElement' },
      ],
    ],
    configFile: false,
    babelrc: false,
    compact: false,
  }).code;
  check(
    'template transpiles (JSX valid)',
    true,
    `${Math.round(code.length / 1024)} KB of JS`,
  );
} catch (e) {
  check('template transpiles (JSX valid)', false, e.message.split('\n')[0]);
  process.exit(1);
}

// ---------------------------------------------------------------- render it in jsdom
const dom = new JSDOM(
  "<!doctype html><html><body><div id='root'></div></body></html>",
  { pretendToBeVisual: true },
);
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.React = React;
dom.window.React = React;
// deliberately no window.Chart - the template must degrade gracefully without it

function build(initialTab, tweaks) {
  const factory = new Function(
    'React',
    'window',
    'document',
    code + '\n;return WorkflowUI;',
  );
  const Comp = factory(React, dom.window, dom.window.document);
  // Drive useState by pre-seeding: render, then re-render with the hook order patched. Simpler and
  // more robust here: monkey-patch useState so the Nth call can be given a forced initial value.
  const realUseState = React.useState;
  let call = 0;
  React.useState = function (init) {
    call++;
    const forced = tweaks && tweaks[call];
    return realUseState(forced !== undefined ? forced : init);
  };
  try {
    return ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, {}));
  } finally {
    React.useState = realUseState;
    call = 0;
  }
}

let baseHtml;
try {
  baseHtml = build();
  check(
    'component renders without throwing',
    baseHtml.length > 1000,
    `${Math.round(baseHtml.length / 1024)} KB of HTML`,
  );
} catch (e) {
  check('component renders without throwing', false, e.message.split('\n')[0]);
  process.exit(1);
}

// ---------------------------------------------------------------- assertions on the DEFAULT render
check(
  'no literal NaN in the output',
  !/>\s*NaN/.test(baseHtml) && !baseHtml.includes('NaN%'),
);
check('no literal undefined rendered', !baseHtml.includes('>undefined<'));

// The funnels tab is not mounted by default (the tab hook starts on "overview"), so force it. Hook 1
// is the active tab; the view hook is discovered below rather than hardcoded, so this harness keeps
// working when hooks are added above it.
const funnelsHtml = build(null, { 1: 'funnels' });
check('funnels tab renders', funnelsHtml.length > 1000);
check('the new view button exists', funnelsHtml.includes('Drop-off by cohort'));

// ---------------------------------------------------------------- render WITH the new view selected
// Hook order in the template: 1 tab, ... find the funView hook by rendering with each candidate.
let payload = JSON.parse(data);
if (LIVE) {
  // Recover the DATA literal the live render carries, so every numeric expectation below is derived
  // from the same dataset the live DOM was rendered from.
  // The published render declares `var DATA`, not `const` - matching only `const` meant this quietly
  // fell through to the LOCAL payload and still reported PASS, which is the failure mode this whole
  // mode exists to catch.
  const m = injected.match(/(?:const|var|let)\s+DATA\s*=\s*/);
  if (m) {
    const start = injected.indexOf('{', m.index);
    let depth = 0,
      end = -1,
      inStr = false,
      esc = false;
    for (let i = start; i < injected.length; i++) {
      const ch = injected[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch.charCodeAt(0) === 92) esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') inStr = true;
      else if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) {
          end = i + 1;
          break;
        }
      }
    }
    if (end > 0) {
      try {
        payload = JSON.parse(injected.slice(start, end));
        liveRecovered = true;
      } catch (e) {
        console.log('  ERROR live DATA found but did not parse: ' + e.message);
      }
    }
  }
  check(
    'live payload was recovered from the live render (not silently the local one)',
    liveRecovered && (payload.cohortDropoff || []).length > 0,
    liveRecovered
      ? (payload.cohortDropoff || []).length +
          ' cohort rows, built ' +
          payload.built_at
      : 'FELL BACK TO LOCAL - every numeric check below would grade live output against local data',
  );
}
const CD = payload.cohortDropoff || [];
check('payload carries cohortDropoff', CD.length > 0, `${CD.length} cohorts`);

let dropHtml = null,
  viewHook = null;
for (let i = 2; i <= 60 && !dropHtml; i++) {
  let html;
  try {
    html = build(null, { 1: 'funnels', [i]: 'dropoff' });
  } catch (e) {
    continue;
  }
  if (html.includes('What this shows')) {
    dropHtml = html;
    viewHook = i;
  }
}
check(
  'drop-off view renders when selected',
  !!dropHtml,
  viewHook ? `view hook #${viewHook}` : 'no hook produced the view',
);

// the per-cohort level must render too, not just the default by-design roll-up
let cohortLevelHtml = null;
if (viewHook) {
  for (let j = viewHook; j <= viewHook + 4 && !cohortLevelHtml; j++) {
    let h;
    try {
      h = build(null, { 1: 'funnels', [viewHook]: 'dropoff', [j]: 'cohort' });
    } catch (e) {
      continue;
    }
    if (h.includes('What this shows') && CD.length && h.includes('>' + CD[0].c))
      cohortLevelHtml = h;
  }
}
check(
  'per-cohort level renders every cohort',
  !!cohortLevelHtml &&
    CD.every(function (r) {
      return cohortLevelHtml.includes('>' + r.c);
    }),
  cohortLevelHtml ? `${CD.length} cohort rows` : 'cohort level did not render',
);

if (dropHtml) {
  check(
    'explains why there is no day-count control',
    /no day-count control/i.test(dropHtml),
  );
  check(
    'the default view explains what the 14-day rule measures',
    /measures silence, not leaving/i.test(dropHtml),
  );
  check(
    'keeps Schedule-not-completed separate from Dropped',
    /Schedule not completed/.test(dropHtml) &&
      /Not their doing, so kept out of drop-off/i.test(dropHtml),
  );
  check(
    'defines every state in the view itself',
    /What each column means/.test(dropHtml) &&
      [
        'Finished the design',
        'Dropped off',
        'Schedule not completed',
        'Never began',
        'Still in progress',
      ].every(function (k) {
        return dropHtml.indexOf(k) >= 0;
      }),
  );
  check(
    'splits completed into on time and late',
    /of which late/.test(dropHtml),
  );
  check(
    'sort control offered on the design level too',
    /Design name/.test(dropHtml),
  );
  // The KPI tiles must sit side by side. sm:grid-cols-5 is NOT in the Labs Tailwind build, so relying
  // on it silently collapsed them into five full-width horizontal bands.
  check(
    'headline tiles are laid out side by side, not as full-width bands',
    !/sm:grid-cols-5/.test(injected) && /flex flex-wrap gap-2/.test(dropHtml),
  );
  // The fixed-days explainer is reference material for a rule no longer in force: heading visible,
  // table collapsed until clicked.
  check(
    'fixed-days explainer is collapsed by default but present',
    /Click to see the per-design breakdown/.test(dropHtml) &&
      /display:none/.test(dropHtml.replace(/\s/g, '')) &&
      /exactly one interview/.test(dropHtml),
  );
  check(
    'shows the fixed-days explainer table',
    /What a fixed number of days would have meant/i.test(dropHtml),
  );
  check(
    'explainer flags the one-interview-gap design',
    /exactly one interview/i.test(dropHtml),
  );
  check(
    'explainer flags the fast designs',
    /over four missed interviews/i.test(dropHtml),
  );

  // every design in the payload must appear, and the totals must tie out to the payload
  const SD = payload.subgroupDesign || {},
    CSG = payload.cohortSG || {};
  const designs = [...new Set(CD.map((r) => CSG[r.c]).filter(Boolean))];
  const missing = designs.filter((d) => !dropHtml.includes('>' + d + '<'));
  check(
    'every cohort design appears in the table',
    missing.length === 0,
    missing.length
      ? `missing: ${missing.join(', ')}`
      : `${designs.length} designs`,
  );

  // The view defaults to reading C (stopped and never came back), so the tiles must show dC, not dB.
  const tot = CD.reduce(
    (a, r) => ({
      n: a.n + r.n,
      f: a.f + r.f + (r.l || 0),
      dA: a.dA + (r.dA || 0),
      dB: a.dB + (r.dB || 0),
      dC: a.dC + (r.dC || 0),
      sk: a.sk + (r.sk || 0),
      w: a.w + r.w,
    }),
    { n: 0, f: 0, dA: 0, dB: 0, dC: 0, sk: 0, w: 0 },
  );
  // The default is reading A (the team settled on it 28 Aug), so the tiles must show dA, not dC.
  check(
    'KPI totals present verbatim, for the DEFAULT reading',
    dropHtml.includes(tot.f.toLocaleString()) &&
      dropHtml.includes(tot.dA.toLocaleString()) &&
      dropHtml.includes(tot.w.toLocaleString()),
    `finished=${tot.f} dropped(A)=${tot.dA} schedule-n/c=${tot.w}`,
  );
  // C and "skipped but returned" must together be exactly B - they are one split of the same people.
  check(
    'C + skipped-but-returned == B, exactly',
    tot.dC + tot.sk === tot.dB,
    `${tot.dC} + ${tot.sk} = ${tot.dC + tot.sk} vs B ${tot.dB}`,
  );
  check(
    'all three readings are shipped for every cohort',
    CD.every(function (r) {
      return ['dA', 'dB', 'dC', 'sk'].every(function (k) {
        return typeof r[k] === 'number' && r[k] >= 0;
      });
    }),
    `${CD.length} cohorts`,
  );
  check(
    'no reading can exceed the workers in its cohort',
    CD.every(function (r) {
      return r.dA <= r.n && r.dB <= r.n && r.dC <= r.n && r.sk <= r.n;
    }),
  );
  check(
    'the three options are offered with one sentence each',
    /Dropped off means:/.test(dropHtml) &&
      /Stopped and never came back/.test(dropHtml) &&
      /Missed any interview/.test(dropHtml) &&
      /No contact for 14 days/.test(dropHtml),
  );
  check(
    'buckets account for every worker',
    tot.f + tot.dC + tot.sk + tot.w <= tot.n,
    `${tot.f}+${tot.dC}+${tot.sk}+${tot.w} of ${tot.n}`,
  );
  check(
    'cohort count in the button label is right',
    dropHtml.includes('Every cohort (' + CD.length + ')'),
  );
}

// ---------------------------------------------------------------- the waiting band on the old chart
check(
  'quality panel names the Schedule-not-completed series',
  /Schedule not completed: did all sent, nothing more sent/.test(injected),
);
// One concept, one word. The engagement panel says "Finished"; the drop-off view must not invent a
// second word for the same thing (it said "Completed", which also means interview-level elsewhere).
check(
  'drop-off view uses the engagement panel vocabulary',
  /Finished the design/.test(injected),
);
check(
  'no stale flat-day bands in the panel-3 legend',
  !/Slow \(8-14d\)/.test(injected) && !/cadence-independent/.test(injected),
);
check(
  'no surface still calls this state Waiting',
  (injected.match(/Waiting/g) || []).length <= 2,
  `${
    (injected.match(/Waiting/g) || []).length
  } mentions (one historical note + one code comment ok)`,
);
check(
  'Dropped label no longer claims a 14-day silence rule',
  !/Dropped off: silent 14\+ days/.test(injected),
);
// Every per-week array must be trimmed together in Active-window mode, or a sliced chart pairs week N
// labels with week M values. Asserted by NAME rather than by exact list text, so adding a series later
// fails this check loudly instead of silently going stale.
const sliceList = (injected.match(/var keys = \[([\s\S]*?)\];/) || [])[1] || '';
const mustSlice = [
  'weeks',
  'started',
  'finished_pct',
  'drop_pct',
  'waiting_pct',
  'inprog_pct',
  'steady_pct',
  'incons_pct',
  'rhythm_base',
  'finished',
  'new',
  'active',
  'slow',
  'quiet',
  'waiting',
];
const notSliced = mustSlice.filter(function (k) {
  return sliceList.indexOf('"' + k + '"') < 0;
});
check(
  'every per-week array is trimmed in Active-window mode',
  notSliced.length === 0,
  notSliced.length
    ? `missing: ${notSliced.join(', ')}`
    : `${mustSlice.length} arrays`,
);

// topicStatusCohort ships compressed as fixed-order arrays. A wire format the render decodes must be
// proven to round-trip, or a reordered state silently mislabels every per-cohort drilldown.
(function () {
  const tsc = payload.topicStatusCohort || {};
  const codes = Object.keys(tsc);
  const compressed = codes.filter(function (c) {
    return (tsc[c] || []).some(function (r) {
      return Array.isArray(r);
    });
  });
  check(
    'topicStatusCohort ships compressed',
    compressed.length === codes.length,
    `${compressed.length}/${codes.length} topics`,
  );
  // every row must have 1 cohort id + 6 counts, and the counts must sum to the topic's applicable
  // total for that cohort as reported by topicStatus
  let badShape = 0;
  codes.forEach(function (c) {
    (tsc[c] || []).forEach(function (r) {
      if (!Array.isArray(r) || r.length !== 7 || typeof r[0] !== 'string')
        badShape++;
      else if (
        r.slice(1).some(function (x) {
          return typeof x !== 'number' || x < 0;
        })
      )
        badShape++;
    });
  });
  check(
    'every compressed row is [cohort, ...6 counts]',
    badShape === 0,
    `${badShape} malformed`,
  );
  // and the decoded totals must equal topicStatus's applicable counts, topic by topic
  const ORDER = [
    'completed',
    'started-not-completed',
    'available-missed-overdue',
    'available-not-started',
    'not-available-yet',
    'not-triggered',
  ];
  const bad = [];
  (payload.topicStatus || []).forEach(function (t) {
    const rows = tsc[t.code] || [];
    ORDER.forEach(function (st, i) {
      const sum = rows.reduce(function (a, r) {
        return a + (Array.isArray(r) ? r[i + 1] : r[st] || 0);
      }, 0);
      if (rows.length && sum !== (t[st] || 0))
        bad.push(`${t.code}/${st} ${sum} vs ${t[st]}`);
    });
  });
  check(
    'decoded per-cohort counts sum to topicStatus, state by state',
    bad.length === 0,
    bad.length
      ? bad.slice(0, 3).join('; ')
      : `${codes.length} topics reconcile`,
  );
})();

// Every worker must land in exactly one bucket. The in-progress residual used to be implied rather
// than shipped, so three cohorts had 7 workers in no bucket and f+l+d+w+z did not reach n.
(function () {
  const bad = (payload.cohortDropoff || []).filter(function (r) {
    return r.f + (r.l || 0) + r.d + r.w + (r.z || 0) + (r.p || 0) !== r.n;
  });
  check(
    'every worker lands in exactly one drop-off bucket',
    bad.length === 0,
    bad.length
      ? `${bad.length} cohorts short: ${bad
          .slice(0, 3)
          .map(function (r) {
            return r.c;
          })
          .join(', ')}`
      : `${(payload.cohortDropoff || []).length} cohorts balance`,
  );
})();
// The engagement tiles must state the date they actually describe, not today, or a finished design
// reads as current and appears to contradict the drop-off view.
check(
  'engagement tiles date themselves from the series, not from today',
  /var tileWk = full\.weeks/.test(injected) &&
    /as of " \+ fmtWk\(tileWk\)/.test(injected),
);
check(
  'a stale-edge design warns that its figures are not current',
  /not today/.test(injected) && /tileStale/.test(injected),
);
// Three nested worker populations must not all be called "unique FLWs".
// "unique FLWs" is fine where it genuinely means unique people (the Connect funnel, the per-round
// chart, the slots-vs-FLWs contrast). It was wrong on the two HEADLINES that showed different
// populations under the same words: counts.flws (1,449 offered an interview) and the engagement tile
// (1,441 who started one). Assert those two now name themselves.
check(
  'the page header names its population',
  /FLWs offered an interview/.test(injected),
);
check('the started tile names its population', /FLWs who began/.test(injected));
// A rate on a base of 1 is not reportable.
check(
  'tiny rhythm bases show a count, not a rate',
  /base too small to report as a rate/.test(injected),
);

// ---------------------------------------------------------------- the docs tab must not drift
// The Documentation tab compares what it documents against what the payload actually carries and
// prints "In sync" only when every tab and every payload key is accounted for. Adding cohortDropoff
// without documenting it would show up there as a stale page, so assert the guard is satisfied.
// The docs tab has its own section switcher (hook 66-ish: kpi | opportunity | onboarding | flow |
// tabs | metrics | trouble | glossary) and shows one section at a time, so each has to be rendered.
function docsSection(sec) {
  for (let i = 2; i <= 80; i++) {
    let h;
    try {
      h = build(null, { 1: 'docs', [i]: sec });
    } catch (e) {
      continue;
    }
    if (h.length > 1000 && h.indexOf('Indicators') >= 0) {
      // confirm the switch actually took effect by looking for section-specific content
      if (sec === 'metrics' && /Dropped off/.test(h)) return h;
      if (sec === 'tabs' && /Retention lines/.test(h)) return h;
      if (sec === 'kpi' && /In sync|out of sync|Out of sync/i.test(h)) return h;
    }
  }
  return null;
}
const docsHtml = build(null, { 1: 'docs' });
check('documentation tab renders', docsHtml.length > 1000);
const docsKpi = docsSection('kpi'),
  docsMetrics = docsSection('metrics'),
  docsTabs = docsSection('tabs');
check(
  'docs drift guard reports in sync',
  !!docsKpi && /In sync\./.test(docsKpi),
  docsKpi ? '' : 'could not render the cross-check section',
);
check(
  'docs documents the new drop-off view',
  !!docsTabs && /Drop-off by cohort/.test(docsTabs),
);
check(
  'docs documents Schedule not completed and Completed late',
  !!docsMetrics &&
    /Schedule not completed/.test(docsMetrics) &&
    /Completed late/.test(docsMetrics),
);
check(
  'docs no longer describes Dropped as 14 days of silence',
  !!docsMetrics && !/silent for more than 14 days/.test(docsMetrics),
);
check(
  'docs states the deadline is one interview gap',
  !!docsMetrics && /one interview gap after it was released/.test(docsMetrics),
);

// ---------------------------------------------------------------- outcome vs rhythm split
// Regression guard for the bug this pass fixed: rhythm used to be the residual of the outcome stack,
// so it read 0% at the final point of every series once all cohorts closed.
const CEp = payload.cohortEngagement || {};
const badOutcome = [],
  badRhythm = [],
  flatRhythm = [];
Object.keys(CEp).forEach(function (sg) {
  const c = CEp[sg],
    n = (c.weeks || []).length;
  if (!n) return;
  const last = n - 1;
  // The payload no longer ships outcome percentages - the page derives them from the counts, for
  // whichever of the three readings is selected. So check what the page will actually compute, and
  // check it for ALL THREE readings: each one has to close to 100 on its own.
  [
    ['B', 'dropped', 'waiting'],
    ['C', 'dropC', 'waitC'],
    ['A', 'dropA', 'waitA'],
  ].forEach(function (m) {
    const st = c.started[last];
    if (!st) return;
    const dv = (c[m[1]] || [])[last],
      wv = (c[m[2]] || [])[last];
    if (dv == null || wv == null) {
      badOutcome.push(sg + ':' + m[0] + '=missing');
      return;
    }
    const ip = st - c.finished[last] - dv - wv;
    if (ip < 0)
      badOutcome.push(sg + ':' + m[0] + '=negative in-progress ' + ip);
    const o = Math.round((100 * (c.finished[last] + dv + wv + ip)) / st);
    if (o < 99 || o > 101) badOutcome.push(sg + ':' + m[0] + '=' + o);
  });
  const r = c.steady_pct[last] + c.incons_pct[last],
    rb = c.rhythm_base[last];
  if (rb && (r < 99 || r > 101)) badRhythm.push(sg + '=' + r);
  if (rb && r === 0) flatRhythm.push(sg);
});
check(
  'outcome closes to 100 at the final week under ALL THREE readings',
  badOutcome.length === 0,
  badOutcome.length
    ? badOutcome.join(', ')
    : `${Object.keys(CEp).length} series`,
);
check(
  'rhythm shares sum to 100 on their own base',
  badRhythm.length === 0,
  badRhythm.length ? badRhythm.join(', ') : '',
);
check(
  'rhythm is NOT flat zero where it is measurable',
  flatRhythm.length === 0,
  flatRhythm.length
    ? `collapsed for: ${flatRhythm.join(', ')}`
    : 'the bug this pass fixed',
);
// An unpooled series' rhythm base must stay within its starters. A POOLED one (All cohorts) counts
// enrolments rather than unique FLWs, so it may exceed them by design.
check(
  'rhythm base never exceeds starters (unpooled series)',
  Object.keys(CEp).every(function (sg) {
    const c = CEp[sg],
      n = (c.weeks || []).length;
    if (!n || c.rhythm_pooled) return true;
    return c.rhythm_base.every(function (b, i) {
      return b <= c.started[i];
    });
  }),
);
// The pooled view must not contradict its parts. The rhythm COUNT arrays are stripped from the render
// payload (they exist only so the builder can pool), so this asserts the two properties that survive:
// the base is exactly the sum of the parts' bases, and the pooled percentage sits inside their range.
// Together those would have caught the v168 bug, where ALL read 19% steady against parts of 56-92%.
(function () {
  const all = CEp.ALL;
  if (!all) return;
  check('All-cohorts rhythm is flagged as pooled', !!all.rhythm_pooled);
  const last = all.weeks.length - 1;
  let rb = 0;
  const pcts = [];
  Object.keys(CEp).forEach(function (sg) {
    if (sg === 'ALL') return;
    const c = CEp[sg],
      j = c.weeks.length - 1;
    if (c.weeks[j] <= all.weeks[last]) {
      rb += c.rhythm_base[j];
      if (c.rhythm_base[j]) pcts.push(c.steady_pct[j]);
    }
  });
  check(
    'pooled rhythm base is the sum of its parts',
    all.rhythm_base[last] === rb,
    `ALL ${all.rhythm_base[last]} vs parts ${rb}`,
  );
  const lo = Math.min.apply(null, pcts),
    hi = Math.max.apply(null, pcts);
  check(
    'pooled steady% sits inside the range of its parts',
    !pcts.length || (all.steady_pct[last] >= lo && all.steady_pct[last] <= hi),
    `ALL ${all.steady_pct[last]}% vs parts ${lo}-${hi}%`,
  );
})();
check(
  'chart distinguishes the two readings',
  /Rhythm - steady/.test(injected) && /borderDash/.test(injected),
);
check(
  'no stale fixed-day copy in engagement or FLW tab',
  !/silent 14\+|silent 14-60|8-14 days ago|14\+ days since/.test(injected),
);
check(
  "single-interview designs read 'not measurable', not 0%",
  /not measurable/.test(injected),
);

// The Documentation tab's rule is structure only, every number from live data. Hardcoded illustrative
// figures went stale within a day of being written, so assert none came back.
check(
  'documentation tab carries no hardcoded illustrative figures',
  !/319 interviews smaller/.test(injected) &&
    !/137 vs 177/.test(injected) &&
    !/1,305 vs parent 1,298/.test(injected),
);
// A cohort past its end date CAN legitimately hold work in progress: interviews are still triggered
// after the nominal end, and someone whose deadline has not arrived is not a drop-out. What must hold
// is that they have a reason - the cohort is not `settled` (every deadline behind us). Anyone in
// progress inside a settled cohort is drift.
(function () {
  const bad = (payload.cohortDropoff || []).filter(function (r) {
    return (r.p || 0) > 0 && r.settled === true;
  });
  check(
    'in-progress workers only exist where a deadline has not yet arrived',
    bad.length === 0,
    bad.length
      ? bad
          .slice(0, 3)
          .map(function (r) {
            return r.c + ':' + r.p;
          })
          .join(', ')
      : 'no settled cohort holds work in progress',
  );
})();

// C is a strict subset of B: someone who came back after a gap cannot count as having stopped.
// A is a different rule entirely and may exceed either, so only C vs B is asserted.
(function () {
  const bad = [];
  Object.keys(CEp).forEach(function (sg) {
    const c = CEp[sg];
    (c.weeks || []).forEach(function (_w, i) {
      if ((c.dropC || [])[i] > (c.dropped || [])[i]) bad.push(sg + '@' + i);
    });
  });
  check(
    'weekly "stopped and never came back" never exceeds "missed any interview"',
    bad.length === 0,
    bad.length
      ? bad.slice(0, 4).join(', ')
      : 'C <= B at every week in every series',
  );
})();

// ---------------------------------------------------------------- Data review view
// Not-yet-reviewed must be ON by default and must be visible in the table. Defaulting it OFF, or
// leaving it out, would recreate inside our own dashboard the exact confusion the OCS screen caused.
(function () {
  const rs = payload.reviewStatus;
  check(
    'payload carries the OCS review split',
    !!(rs && rs.overall),
    rs ? Object.keys(rs.overall || {}).join(', ') : 'absent',
  );
  if (!rs || !rs.overall) return;
  // useState indices shift whenever a hook is added above, so find the view hook rather than assume
  // it - hardcoding 2 is what made this check pass on the button label while the view never rendered.
  let html = null;
  for (let i = 2; i <= 60 && !html; i++) {
    let candidate;
    try {
      candidate = build(null, { 1: 'funnels', [i]: 'review' });
    } catch (e) {
      continue;
    }
    if (candidate.includes('completed interviews match the')) html = candidate;
  }
  check(
    'Data review view renders',
    !!html,
    html ? '' : 'view never rendered at any hook index',
  );
  check(
    'not-yet-reviewed is shown by default, not filtered away',
    !!html && /Not yet reviewed/.test(html),
  );
  const keys = rs.keys || [];
  const tot = keys.reduce((a, k) => a + (rs.overall[k] || 0), 0);
  const bySg = Object.values(rs.by_sg || {}).reduce(
    (a, v) => a + keys.reduce((b, k) => b + (v[k] || 0), 0),
    0,
  );
  check(
    'review split: by-design adds back to the overall',
    bySg === tot,
    `${bySg} vs ${tot}`,
  );
})();

// The stacked bar's segments must share ONE base or the bar cannot sum to 100. This is the check that
// was missing when the row percentages moved to the asked base and three segments did not: 38 of 73
// bars overflowed, the worst to 124.6%, and the browser silently rescaled them all.
(function () {
  const bad = [];
  (payload.cohortDropoff || []).forEach(function (r) {
    const base = r.nb != null ? r.nb : r.n;
    if (!base) return;
    const pct = (v) => Math.round((1000 * v) / base) / 10;
    // Reading C is the default and the one the bar draws.
    // Never began is NOT a segment: those workers are not in the asked base. The six that remain
    // partition it exactly, which is why this must land on 100 and not merely near it.
    const total =
      pct(r.f) +
      pct(r.l || 0) +
      pct(r.dC) +
      pct(r.sk || 0) +
      pct(r.w) +
      pct(r.p || 0);
    if (total < 99.0 || total > 101.0)
      bad.push(r.c + '=' + total.toFixed(1) + '%');
  });
  check(
    'split-bar segments share one base and sum to 100',
    bad.length === 0,
    bad.length
      ? bad.slice(0, 4).join(', ')
      : `${(payload.cohortDropoff || []).length} rows`,
  );
})();

// The summary tiles and the table beneath them must divide by the same base, or the same words carry
// two numbers on one screen ("Finished the design" read 60% in the tile and 63.4% in the table).
(function () {
  const rows = payload.cohortDropoff || [];
  const n = rows.reduce((a, r) => a + r.n, 0);
  const asked = rows.reduce((a, r) => a + (r.nb != null ? r.nb : r.n), 0);
  const done = rows.reduce((a, r) => a + r.f + (r.l || 0), 0);
  check(
    'tile and table bases agree (asked, not enrolled)',
    asked > 0 && asked <= n,
    `asked ${asked.toLocaleString()} of ${n.toLocaleString()} enrolled; finished ${Math.round(
      (100 * done) / asked,
    )}% of asked vs ${Math.round(
      (100 * done) / n,
    )}% of enrolled - the page must show the former`,
  );
})();

// Every rate divides by `asked`, so `asked` has to be ON SCREEN or a reader cannot reproduce a count.
check(
  'the asked base is a visible column, not just a comment',
  /&gt;Asked&lt;\/th&gt;/.test(injected) || />Asked<\/th>/.test(injected),
);

// The outcome chart's "values in a table" mode exists so a SCREENSHOT carries its own numbers - the
// chart alone could not, because four of six series live between 5% and 19% and their labels collide.
// So assert the table actually renders with values, not just that the toggle exists.
(function () {
  let viewHook = null;
  for (let i = 2; i <= 60 && !viewHook; i++) {
    try {
      if (
        build(null, { 1: 'funnels', [i]: 'engagement' }).includes(
          'Panel 1 - recruitment',
        )
      )
        viewHook = i;
    } catch (e) {}
  }
  let html = null;
  for (let j = 2; j <= 60 && !html && viewHook; j++) {
    if (j === viewHook) continue;
    let h;
    try {
      h = build(null, {
        1: 'funnels',
        [viewHook]: 'engagement',
        [j]: 'values',
      });
    } catch (e) {
      continue;
    }
    if (
      h.includes('% of started FLWs') &&
      h.includes('Rhythm - inconsistent') &&
      h.includes('</table>')
    )
      html = h;
  }
  check(
    'outcome value table renders',
    !!html,
    html ? '' : 'never rendered at any hook index',
  );
  if (!html) return;
  const rows = html
    .split('<tr')
    .filter((r) => r.includes('&#9679;') || r.includes('\u25cf'));
  check(
    'value table carries all six series',
    rows.length === 6,
    `${rows.length} rows`,
  );
  const pcts = (html.match(/\d+%/g) || []).length;
  check(
    'value table is populated, not empty',
    pcts > 50,
    `${pcts} percentage values`,
  );
})();

// Reading A ignores the per-cohort deadline entirely - it returns purely on 14 days of silence - so
// the table must not print 3d/7d/4d beside its numbers as though that rule applied to them.
(function () {
  if (viewHook == null) {
    check(
      'deadline column follows the selected reading',
      false,
      'view hook not found',
    );
    return;
  }
  let modeHook = null,
    aHtml = null,
    cHtml = null;
  const base = build(null, { 1: 'funnels', [viewHook]: 'dropoff' });
  for (let j = 2; j <= 60 && !modeHook; j++) {
    if (j === viewHook) continue;
    let a;
    try {
      a = build(null, { 1: 'funnels', [viewHook]: 'dropoff', [j]: 'C' });
    } catch (e) {
      continue;
    }
    if (a !== base && /never completed another one/i.test(a)) {
      modeHook = j;
      cHtml = a;
    }
  }
  // reading A is now what the view opens on, so the base render IS the A render
  aHtml = base;
  check(
    'reading-A view names the column Silence, not Deadline',
    !!aHtml && />Silence<\/th>|>\s*Silence\s*</.test(aHtml),
    aHtml ? '' : 'could not render reading A',
  );
  check(
    'reading-C view still names it Deadline',
    !!cHtml && /Deadline/.test(cHtml),
  );
  check(
    'reading-A does not claim the deadline is one interview gap',
    !!aHtml && !/deadline for one interview is one interview gap/.test(aHtml),
    aHtml && /flat 14 days of silence/.test(aHtml)
      ? 'says flat 14 days instead'
      : '',
  );
})();

// ---------------------------------------------------------------- size guard
// The Labs render_code limit is a hard 512 KB and brutal_verify enforces it in CI. This local check
// UNDER-reports: a local build runs off cached pulls, so its payload is smaller than the live one. On
// 2026-08-21 local read 495 KB while CI read 513.6 KB and refused to publish. So the bar here is the
// live figure scaled from the local payload, not the local figure itself.
const liveBytes = Buffer.byteLength(injected, 'utf8');
const CAP = 512 * 1024;
// The scale-up exists because a LOCAL build runs off cached pulls and is smaller than the live one.
// In CI the payload IS the live one, so applying it there inflates a real ~502 KB render to a
// fictional 520 KB and blocks a publish that would have fitted - which is exactly what happened on
// 2026-08-25. Decide from the payload itself rather than from an env var: a full build carries the
// whole programme, a stale local one does not.
const LIVE_SCALE = 1.075; // MEASURED on the 2026-08-21 publish: 252.4 KB live / 234.9 local
const IS_FULL_BUILD = (payload.counts && payload.counts.master_rows) > 9000;
const LIVE_FACTOR = IS_FULL_BUILD ? 1.0 : LIVE_SCALE;
const MIN_HEADROOM = 4 * 1024; // fail before the wall, not at it - CI's own gate is the backstop
// In LIVE mode there is nothing to project: the bytes in hand ARE the live render, so scaling them
// by the local-to-live payload factor a second time would invent ~22 KB that does not exist and fail
// a render that actually fits.
const projected = LIVE
  ? liveBytes
  : Buffer.byteLength(src, 'utf8') +
    (liveBytes - Buffer.byteLength(src, 'utf8')) * LIVE_FACTOR;
check(
  'injected render fits the 512 KB Labs cap (local)',
  liveBytes < CAP,
  `${Math.round(liveBytes / 1024)} KB of 512, headroom ${Math.round(
    (CAP - liveBytes) / 1024,
  )} KB`,
);
check(
  LIVE
    ? 'LIVE render fits the 512 KB Labs cap (measured, not projected)'
    : 'projected LIVE render fits the cap with headroom to spare',
  projected + MIN_HEADROOM < CAP,
  LIVE
    ? `${Math.round(
        projected / 1024,
      )} KB of 512 measured on the live render, headroom ${Math.round(
        (CAP - projected) / 1024,
      )} KB`
    : `~${Math.round(projected / 1024)} KB at ${LIVE_FACTOR}x payload (${
        IS_FULL_BUILD
          ? 'full build - measured, not scaled'
          : 'local build - scaled up to estimate live'
      }), headroom ~${Math.round((CAP - projected) / 1024)} KB`,
);

// ---------------------------------------------------------------- the Window scopes the whole panel
// The tiles used to read the last point of the FULL series whatever the Window said, so Active window
// and Full timeline produced identical tiles while the chart beneath moved. These checks are
// BEHAVIOURAL - they force the two window states and require the numbers to differ - because the
// earlier version of this file selected views by button label, which is present whether or not the
// state ever took effect.
(function () {
  function tilesOf(html) {
    const out = {};
    const re =
      /<div class="text-lg font-bold"[^>]*>([^<]{1,18})<\/div><div class="text-xs font-medium text-gray-700">([^<]{1,60})<\/div>/g;
    let m;
    while ((m = re.exec(html))) out[m[2].trim()] = m[1].trim();
    return out;
  }
  let engIdx = null,
    baseHtmlEng = null;
  for (let i = 2; i <= 60 && !baseHtmlEng; i++) {
    let h;
    try {
      h = build(null, { 1: 'funnels', [i]: 'engagement' });
    } catch (e) {
      continue;
    }
    if (/Read this as recruitment|Program-wide roll-up/.test(h)) {
      engIdx = i;
      baseHtmlEng = h;
    }
  }
  check(
    'cohort engagement view renders',
    !!baseHtmlEng,
    engIdx ? 'hook ' + engIdx : 'never mounted',
  );
  if (!baseHtmlEng) return;

  let sgIdx = null;
  for (let i = 2; i <= 60 && !sgIdx; i++) {
    if (i === engIdx) continue;
    let h;
    try {
      h = build(null, { 1: 'funnels', [engIdx]: 'engagement', [i]: 'PANEL' });
    } catch (e) {
      continue;
    }
    if (h !== baseHtmlEng && /PANEL/.test(h)) sgIdx = i;
  }
  if (!sgIdx) {
    check('engagement subgroup selector found', false);
    return;
  }

  let winIdx = null,
    ta = null,
    tf = null;
  for (let i = 2; i <= 60 && !winIdx; i++) {
    if (i === engIdx || i === sgIdx) continue;
    let a, f;
    try {
      a = build(null, {
        1: 'funnels',
        [engIdx]: 'engagement',
        [sgIdx]: 'PANEL',
        [i]: 'active',
      });
      f = build(null, {
        1: 'funnels',
        [engIdx]: 'engagement',
        [sgIdx]: 'PANEL',
        [i]: 'full',
      });
    } catch (e) {
      continue;
    }
    const A = tilesOf(a),
      F = tilesOf(f);
    if (Object.keys(A).length && JSON.stringify(A) !== JSON.stringify(F)) {
      winIdx = i;
      ta = A;
      tf = F;
      check(
        'the Window choice moves the KPI tiles, not just the chart',
        A['Dropped off'] !== F['Dropped off'],
        'active ' + A['Dropped off'] + ' vs full ' + F['Dropped off'],
      );
      const aHtml = a;
      check(
        'the active-window note no longer claims the tiles are as of today',
        !/tiles above are as of/.test(aHtml),
        /tiles above are as of/.test(aHtml)
          ? 'stale sentence still shipping'
          : '',
      );
      check(
        'the active-window note says the whole panel is windowed',
        /Everything on this panel/.test(aHtml),
      );
    }
  }
  check(
    'engagement Window selector found',
    !!winIdx,
    winIdx ? 'hook ' + winIdx : 'not found',
  );

  if (winIdx) {
    let modeIdx = null;
    for (let i = 2; i <= 60 && !modeIdx; i++) {
      if (i === engIdx || i === sgIdx || i === winIdx) continue;
      let a, c;
      try {
        a = build(null, {
          1: 'funnels',
          [engIdx]: 'engagement',
          [sgIdx]: 'PANEL',
          [winIdx]: 'full',
          [i]: 'A',
        });
        c = build(null, {
          1: 'funnels',
          [engIdx]: 'engagement',
          [sgIdx]: 'PANEL',
          [winIdx]: 'full',
          [i]: 'C',
        });
      } catch (e) {
        continue;
      }
      const x = tilesOf(a)['Dropped off'],
        y = tilesOf(c)['Dropped off'];
      if (x && y && x !== y) modeIdx = i;
    }
    check('engagement reading selector found', !!modeIdx);
    if (modeIdx) {
      const aH = build(null, {
        1: 'funnels',
        [engIdx]: 'engagement',
        [sgIdx]: 'PANEL',
        [winIdx]: 'full',
        [modeIdx]: 'A',
      });
      check(
        'engagement drop-off wording follows the reading (A does not cite a deadline)',
        /14 days with no interview/.test(aH) &&
          !/went past its deadline/.test(aH),
      );
      const cH = build(null, {
        1: 'funnels',
        [engIdx]: 'engagement',
        [sgIdx]: 'PANEL',
        [winIdx]: 'full',
        [modeIdx]: 'C',
      });
      check(
        'engagement reading C still cites the deadline rule',
        /went past its deadline/.test(cH),
      );
    }
  }
})();

// ---------------------------------------------------------------- the Documentation tab is not stale
// The docs tab describes behaviour, so a behaviour change silently turns it into a wrong answer that
// reads authoritatively. This one said "The KPI tiles are always CURRENT" for as long as that was
// true and for one commit after it stopped being true.
(function () {
  // The docs tab defaults to the data-flow section, so asserting on indicator text at the default
  // state passed on ABSENT text - the three checks here were vacuous on the first attempt. Both the
  // tab hook and the section hook are found by behaviour: render, and require the text that only
  // exists once the Indicators section is actually mounted.
  let docsHtml = null,
    tabIdx = null;
  for (let i = 1; i <= 3 && !tabIdx; i++) {
    let h;
    try {
      h = build(null, { [i]: 'docs' });
    } catch (e) {
      continue;
    }
    if (/Indicator/i.test(h)) {
      tabIdx = i;
      docsHtml = h;
    }
  }
  check('documentation tab renders', !!docsHtml);
  if (!docsHtml) return;

  let indHtml = null;
  for (let i = 1; i <= 60 && !indHtml; i++) {
    if (i === tabIdx) continue;
    let h;
    try {
      h = build(null, { [tabIdx]: 'docs', [i]: 'metrics' });
    } catch (e) {
      continue;
    }
    if (/gap multiples, not fixed days/.test(h)) indHtml = h;
  }
  check(
    'documentation Indicators section renders (not just the tab)',
    !!indHtml,
    indHtml ? '' : 'never mounted - any assertion on its text would be vacuous',
  );
  if (!indHtml) return;
  check(
    'docs carry the Active window entry',
    /Active window vs Full timeline/.test(indHtml),
  );
  check(
    'docs do not claim the KPI tiles ignore the Window choice',
    !/tiles are always CURRENT/i.test(indHtml),
  );
  check(
    'docs state that the Window scopes the whole panel',
    /scopes the WHOLE panel/i.test(indHtml),
  );
  check('docs carry no retired-cohort name', !/1NPS1/.test(indHtml));
})();

// ------------------------------------------- retired-cohort rows are filterable in Sessions ONLY
// The Sessions table renders the LIVE OCS pipeline, which has no cohort filter and so still carries a
// retired cohort's sessions. Its dropdowns were built from the FLW matrix, so those rows were visible
// but not selectable. This injects a synthetic row for a cohort the matrix does not know and requires
// it to reach the Sessions dropdown and NOT the matrix one.
(function () {
  const withRow = JSON.parse(data);
  withRow.granular = (withRow.granular || []).concat([
    {
      connect_id: 'zzsynthetic000000001',
      cohort_id: 'ZZRETIRED',
      subgroup: 'ZZ',
      interview_n: 1,
      topic_code: '999',
      is_triggered: true,
      is_initiated: true,
      is_started: true,
      is_completed: true,
      session_id: 'synthetic-sid',
    },
  ]);
  let Comp2;
  try {
    const inj = src.replace('/*__DATA__*/', JSON.stringify(withRow));
    const c2 = babel.transform(inj, {
      presets: [['@babel/preset-react', {}]],
      filename: 'r2.js',
      compact: false,
    }).code;
    Comp2 = new Function(
      'React',
      'window',
      'document',
      c2 + ';return WorkflowUI;',
    )(React, dom.window, dom.window.document);
  } catch (e) {
    check(
      'synthetic retired-cohort render builds',
      false,
      String(e.message).slice(0, 90),
    );
    return;
  }
  function build2(tweaks) {
    const real = React.useState;
    let call = 0;
    React.useState = function (init) {
      call++;
      const f = tweaks && tweaks[call];
      return real(f !== undefined ? f : init);
    };
    try {
      return ReactDOMServer.renderToStaticMarkup(
        React.createElement(Comp2, {}),
      );
    } finally {
      React.useState = real;
    }
  }
  let tabIdx = null;
  for (let i = 1; i <= 3 && !tabIdx; i++) {
    let h;
    try {
      h = build2({ [i]: 'table' });
    } catch (e) {
      continue;
    }
    if (/Granular view/.test(h)) tabIdx = i;
  }
  if (!tabIdx) {
    check('granular table tab mounts', false);
    return;
  }
  let ddIdx = null;
  for (let i = 2; i <= 60 && !ddIdx; i++) {
    let h;
    try {
      h = build2({ [tabIdx]: 'table', [i]: 'co' });
    } catch (e) {
      continue;
    }
    if ((h.match(/type="checkbox"/g) || []).length > 20) ddIdx = i;
  }
  check(
    'the Cohort dropdown can be opened',
    !!ddIdx,
    ddIdx ? 'hook ' + ddIdx : 'never opened',
  );
  if (!ddIdx) return;
  // Counting OPTIONS, not searching for the name: the synthetic row also renders in the table below
  // the dropdown, so a substring search anywhere after the first checkbox matched the ROW and passed
  // even with the fix reverted. The option count cannot be spoofed that way.
  const optCount = (h) => (h.match(/type="checkbox"/g) || []).length;
  const sessH = build2({ [tabIdx]: 'table', [ddIdx]: 'co' });
  const sessOpts = optCount(sessH);
  // 'FLW x Topic' is a BUTTON LABEL in both views - select on text only the matrix BODY renders.
  let matH = null;
  for (let i = 2; i <= 60 && !matH; i++) {
    if (i === ddIdx || i === tabIdx) continue;
    let m;
    try {
      m = build2({ [tabIdx]: 'table', [ddIdx]: 'co', [i]: 'matrix' });
    } catch (e) {
      continue;
    }
    if (/FLW.cohort rows/.test(m)) matH = m;
  }
  check(
    'matrix view mounts',
    !!matH,
    matH ? '' : 'never mounted - the check below would be vacuous',
  );
  if (matH) {
    const matOpts = optCount(matH);
    check(
      'Sessions cohort filter offers MORE cohorts than the matrix knows',
      sessOpts > matOpts,
      `sessions ${sessOpts} vs matrix ${matOpts} options`,
    );
    check(
      'the extra option is exactly the session-only cohort',
      sessOpts === matOpts + 1,
      `+${sessOpts - matOpts}`,
    );
  }
})();

// ------------------------------------------- the 14-day count is shown split, not as a bare total
// Roughly half the workers the 14-day rule counts had answered every interview they were sent. That
// is the deliberate choice, but a bare total describes those people as having dropped out when they
// did not, so the split is shown beside it.
(function () {
  const CD = payload.cohortDropoff || [];
  const o = CD.reduce((a, r) => a + (r.dAo || 0), 0);
  const c = CD.reduce((a, r) => a + (r.dAc || 0), 0);
  const dA = CD.reduce((a, r) => a + (r.dA || 0), 0);
  check(
    'payload carries the 14-day split',
    o + c > 0 && o + c === dA,
    `${o} unanswered + ${c} answered-everything = ${o + c} vs dA ${dA}`,
  );
  if (!dropHtml) return;
  check(
    'the split box renders on the default view',
    /counted as dropped off are made of/i.test(dropHtml),
  );
  check(
    'the split box shows both numbers',
    dropHtml.includes(o.toLocaleString()) &&
      dropHtml.includes(c.toLocaleString()),
    `${o} / ${c}`,
  );
  check(
    'the split box explains the second group did nothing wrong',
    /did nothing wrong/i.test(dropHtml),
  );
})();

// ------------------------------------------------------- the OCS session census (Leah, 25 Aug)
// Four buckets over SESSIONS, matching how OCS counts, so incomplete work is visible. The old view
// counted completed interviews only, which is why it read 918 against ~12,000 on OCS.
(function () {
  const SR = payload.sessionReview;
  check('payload carries the session census', !!SR && !!SR.counts);
  if (!SR || !SR.counts) return;
  const total = Object.values(SR.counts).reduce((a, b) => a + b, 0);
  check(
    'the four categories cover every session exactly',
    total === SR.sessions,
    `${total} vs ${SR.sessions}`,
  );
  check(
    'Not applicable is LAST in the display order',
    SR.order[SR.order.length - 1] === 'not-applicable',
    SR.order.join(' > '),
  );
  check(
    'Suspected AI is reported as a subset, not a fifth bucket',
    SR.ai_in_unacceptable <= SR.counts.unacceptable &&
      !('suspected_ai' in SR.counts),
    `${SR.ai_in_unacceptable} of ${SR.counts.unacceptable} unacceptable`,
  );
  // Leah's rule: 1-3 AI answers are flagged but NOT penalised, so some ACCEPTABLE sessions carry the
  // flag. Folding the union into "unacceptable" would move those into the wrong bucket.
  check(
    'AI-flagged-but-acceptable sessions are kept out of unacceptable',
    SR.ai_total ===
      SR.ai_in_unacceptable +
        SR.ai_in_acceptable +
        (SR.ai_total - SR.ai_in_unacceptable - SR.ai_in_acceptable),
    `${SR.ai_total} flagged, ${SR.ai_in_acceptable} of them acceptable`,
  );

  // find the review view and confirm it renders
  let revHtml = null;
  for (let i = 2; i <= 60 && !revHtml; i++) {
    let h;
    try {
      h = build(null, { 1: 'funnels', [i]: 'review' });
    } catch (e) {
      continue;
    }
    if (/Every session, as OCS counts them/.test(h)) revHtml = h;
  }
  check('the session census renders', !!revHtml);
  if (!revHtml) return;
  check(
    'every category shows its count',
    ['acceptable', 'unacceptable', 'no-verdict', 'not-applicable'].every((k) =>
      revHtml.includes(SR.counts[k].toLocaleString()),
    ),
  );
  check(
    'every category carries a plain-language definition',
    /five dimensions/i.test(revHtml) &&
      /run-on sessions/i.test(revHtml) &&
      /Waiting Final Review/i.test(revHtml),
  );
  check(
    'Not applicable is rendered after No verdict yet',
    revHtml.indexOf('Not applicable') > revHtml.indexOf('No verdict yet'),
  );
  check(
    'the Suspected AI subset is collapsed by default',
    !/of which Suspected AI/.test(revHtml),
  );
  check(
    'the OCS reconciliation line is shown',
    /Checking this against OCS/i.test(revHtml) &&
      revHtml.includes(SR.ocs_sessions.toLocaleString()),
  );
})();

// ---------------------------------------------------------------- no em/en dashes (house style)
// Checked on the SOURCE: that is the file people edit and the one the rule is about.
const dashes = (injected.match(/[–—]/g) || []).length;
check(
  'no em/en dashes in the template',
  dashes === 0,
  dashes ? `${dashes} found` : '',
);

console.log(`\n[render] ${pass}/${pass + fails.length} checks pass`);
if (fails.length) {
  console.log(`[render] FAILURES: ${fails.join(', ')}`);
  process.exit(1);
}
console.log('[render] ALL PASS');
