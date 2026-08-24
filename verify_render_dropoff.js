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
const src = fs.readFileSync(TEMPLATE, 'utf8');
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

const injected = src.replace('/*__DATA__*/', data);
check('DATA placeholder was substituted', !injected.includes('/*__DATA__*/'));

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
const payload = JSON.parse(data);
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
    'states the deadline is one interview gap',
    /one interview gap/i.test(dropHtml),
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
        'Completed',
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

  const tot = CD.reduce(
    (a, r) => ({ n: a.n + r.n, f: a.f + r.f, d: a.d + r.d, w: a.w + r.w }),
    { n: 0, f: 0, d: 0, w: 0 },
  );
  check(
    'KPI totals present verbatim',
    dropHtml.includes(tot.f.toLocaleString()) &&
      dropHtml.includes(tot.d.toLocaleString()) &&
      dropHtml.includes(tot.w.toLocaleString()),
    `finished=${tot.f} dropped=${tot.d} waiting=${tot.w}`,
  );
  check(
    'buckets account for every worker',
    tot.f + tot.d + tot.w <= tot.n,
    `${tot.f}+${tot.d}+${tot.w} of ${tot.n}`,
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
  const o =
    c.finished_pct[last] +
    c.drop_pct[last] +
    c.waiting_pct[last] +
    c.inprog_pct[last];
  if (o < 99 || o > 101) badOutcome.push(sg + '=' + o);
  const r = c.steady_pct[last] + c.incons_pct[last],
    rb = c.rhythm_base[last];
  if (rb && (r < 99 || r > 101)) badRhythm.push(sg + '=' + r);
  if (rb && r === 0) flatRhythm.push(sg);
});
check(
  'outcome shares sum to 100 at the final week',
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

// ---------------------------------------------------------------- size guard
// The Labs render_code limit is a hard 512 KB and brutal_verify enforces it in CI. This local check
// UNDER-reports: a local build runs off cached pulls, so its payload is smaller than the live one. On
// 2026-08-21 local read 495 KB while CI read 513.6 KB and refused to publish. So the bar here is the
// live figure scaled from the local payload, not the local figure itself.
const liveBytes = Buffer.byteLength(injected, 'utf8');
const CAP = 512 * 1024;
const LIVE_FACTOR = 1.075; // MEASURED on the 2026-08-21 publish: 252.4 KB live / 234.9 local
const MIN_HEADROOM = 4 * 1024; // fail before the wall, not at it - CI's own gate is the backstop
const projected =
  Buffer.byteLength(src, 'utf8') +
  (liveBytes - Buffer.byteLength(src, 'utf8')) * LIVE_FACTOR;
check(
  'injected render fits the 512 KB Labs cap (local)',
  liveBytes < CAP,
  `${Math.round(liveBytes / 1024)} KB of 512, headroom ${Math.round(
    (CAP - liveBytes) / 1024,
  )} KB`,
);
check(
  'projected LIVE render fits the cap with headroom to spare',
  projected + MIN_HEADROOM < CAP,
  `~${Math.round(
    projected / 1024,
  )} KB projected at ${LIVE_FACTOR}x payload, headroom ~${Math.round(
    (CAP - projected) / 1024,
  )} KB`,
);

// ---------------------------------------------------------------- no em/en dashes (house style)
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
