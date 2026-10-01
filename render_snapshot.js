/**
 * End-to-end snapshot of what the Interviews dashboard SHOWS, for before/after comparison.
 *
 * Why this exists: a "render-only" change can still move a number somewhere else on the page (a shared
 * helper, a hook index shift, a state default). The gates check the payload; this checks the screen.
 * It renders every tab under every view option the template offers and records all visible text, so
 * two builds can be diffed line by line. Any difference outside the screen you meant to change is a
 * regression until explained.
 *
 *   node render_snapshot.js <render.js> <out.json>     snapshot a COMPLETE render (DATA already inside,
 *                                                       e.g. one pulled off Labs)
 *   node render_snapshot.js --template <tpl.js> <data.json> <out.json>
 *                                                       strip comments, inject DATA, then snapshot
 *   node render_snapshot.js --diff <before.json> <after.json> [--allow <regex>]
 *                                                       compare; --allow names the states that are
 *                                                       EXPECTED to change (matched against the state key)
 *
 * Exit code of --diff is 1 if any state outside --allow changed, or if the two snapshots do not cover
 * the same states. A state that renders identically in both is counted, so "0 changed of 612" is a
 * statement about 612 screens, not about nothing.
 */
const fs = require('fs');
const os = require('os');
const cp = require('child_process');
const path = require('path');
const crypto = require('crypto');

function sha(s) {
  return crypto.createHash('sha256').update(s).digest('hex').slice(0, 16);
}

// ------------------------------------------------------------------------------------------ diff mode
if (process.argv[2] === '--diff') {
  const a = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  const b = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
  const ai = process.argv.indexOf('--allow');
  const allow = ai > 0 ? new RegExp(process.argv[ai + 1]) : null;
  const ka = Object.keys(a.states).sort();
  const kb = Object.keys(b.states).sort();
  const onlyA = ka.filter((k) => !(k in b.states));
  const onlyB = kb.filter((k) => !(k in a.states));
  let same = 0;
  const expected = [];
  const unexpected = [];
  for (const k of ka) {
    if (!(k in b.states)) continue;
    if (a.states[k] === b.states[k]) {
      same++;
      continue;
    }
    (allow && allow.test(k) ? expected : unexpected).push(k);
  }
  console.log(`before: ${a.source}  (${ka.length} states, data ${a.data_sha})`);
  console.log(`after:  ${b.source}  (${kb.length} states, data ${b.data_sha})`);
  console.log(`DATA identical: ${a.data_sha === b.data_sha ? 'YES' : 'NO'}`);
  console.log(
    `identical: ${same}   changed as expected: ${expected.length}   changed UNEXPECTEDLY: ${unexpected.length}`,
  );
  if (onlyA.length || onlyB.length)
    console.log(
      `state sets differ: only-before ${onlyA.length}, only-after ${onlyB.length}`,
    );
  const show = (k) => {
    const la = a.texts[a.states[k]];
    const lb = b.texts[b.states[k]];
    const sa = new Set(la);
    const sb = new Set(lb);
    const gone = la.filter((l) => !sb.has(l));
    const added = lb.filter((l) => !sa.has(l));
    console.log(`  ~ ${k}`);
    gone.slice(0, 12).forEach((l) => console.log(`      - ${l}`));
    added.slice(0, 12).forEach((l) => console.log(`      + ${l}`));
    if (!gone.length && !added.length)
      console.log('      (same lines, different ORDER)');
  };
  if (unexpected.length) {
    console.log('\nUNEXPECTED CHANGES:');
    unexpected.slice(0, 15).forEach(show);
  }
  if (expected.length && process.argv.includes('--show-expected')) {
    console.log('\nEXPECTED CHANGES (first 3):');
    expected.slice(0, 3).forEach(show);
  }
  const ok =
    !unexpected.length &&
    !onlyA.length &&
    !onlyB.length &&
    a.data_sha === b.data_sha;
  console.log(ok ? '\nRESULT: PASS' : '\nRESULT: FAIL');
  process.exit(ok ? 0 : 1);
}

// ------------------------------------------------------------------------------------ snapshot mode
const babel = require('@babel/core');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const { JSDOM } = require('jsdom');

let render, out, source;
if (process.argv[2] === '--template') {
  const tpl = process.argv[3];
  const stripped = path.join(os.tmpdir(), 'render_snapshot_stripped.js');
  cp.execFileSync(
    'node',
    [path.join(__dirname, 'strip_render_comments.js'), tpl, stripped],
    {
      stdio: 'pipe',
    },
  );
  const data = fs.readFileSync(process.argv[4], 'utf8').trim();
  render = fs.readFileSync(stripped, 'utf8').replace('/*__DATA__*/', data);
  out = process.argv[5];
  source = `${tpl} + ${process.argv[4]}`;
} else {
  render = fs.readFileSync(process.argv[2], 'utf8');
  out = process.argv[3];
  source = process.argv[2];
}

// DATA fingerprint, recovered the same string-aware way the harness does
function dataLiteral(code) {
  const m = code.match(/(?:const|var|let)\s+DATA\s*=\s*/);
  if (!m) return null;
  const start = code.indexOf('{', m.index);
  let depth = 0,
    inStr = false,
    esc = false;
  for (let i = start; i < code.length; i++) {
    const ch = code[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === '\\') esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === '{') depth++;
    else if (ch === '}' && --depth === 0) return code.slice(start, i + 1);
  }
  return null;
}
const dataStr = dataLiteral(render);
if (!dataStr) {
  console.error('no DATA literal found in render');
  process.exit(2);
}
const DATA = JSON.parse(dataStr);

// Hook map: the Nth React.useState call in source order is hook N at runtime (all are top level in
// WorkflowUI). The state variable name comes from the `x = X[0]` that follows each declaration.
const hookVars = [];
const decl = /var\s+(\w+)\s*=\s*React\.useState\(/g;
let mm;
while ((mm = decl.exec(render))) {
  const holder = mm[1];
  const nm = new RegExp('(\\w+)\\s*=\\s*' + holder + '\\[0\\]').exec(
    render.slice(mm.index),
  );
  hookVars.push(nm ? nm[1] : holder);
}

// Values each view control can take, read from the template's own buttons
const values = {};
const sb = /subBtn\((\w+),\s*"([^"]*)"/g;
while ((mm = sb.exec(render)))
  (values[mm[1]] = values[mm[1]] || new Set()).add(mm[2]);
// ...and from direct setter calls, e.g. setDocSec("glossary"), which some controls use instead
const st = /set([A-Z]\w*)\("([^"]+)"\)/g;
while ((mm = st.exec(render))) {
  const v = mm[1][0].toLowerCase() + mm[1].slice(1);
  (values[v] = values[v] || new Set()).add(mm[2]);
}
const tabs = [];
const tb = /activeTab === "(\w+)"/g;
while ((mm = tb.exec(render))) if (!tabs.includes(mm[1])) tabs.push(mm[1]);

// the engagement panel's cohort picker is a <select>, not a button: sweep every cohort it offers
if (DATA.cohortEngagement) {
  values.engSg = values.engSg || new Set();
  Object.keys(DATA.cohortEngagement).forEach((k) => values.engSg.add(k));
}
const code = babel.transformSync(render, {
  presets: [
    [require.resolve('@babel/preset-react'), { pragma: 'React.createElement' }],
  ],
  configFile: false,
  babelrc: false,
}).code;
const dom = new JSDOM(
  "<!doctype html><html><body><div id='root'></div></body></html>",
  {
    pretendToBeVisual: true,
  },
);
global.window = dom.window;
global.document = dom.window.document;
global.navigator = dom.window.navigator;
global.React = React;
dom.window.React = React;
const Comp = new Function(
  'React',
  'window',
  'document',
  code + '\n;return WorkflowUI;',
)(React, dom.window, dom.window.document);

const decoder = dom.window.document.createElement('textarea');
function textLines(html) {
  const t = html
    .replace(/<style[\s\S]*?<\/style>/g, '')
    .replace(/<script[\s\S]*?<\/script>/g, '')
    .replace(/<[^>]+>/g, '\n');
  decoder.innerHTML = t;
  return decoder.value
    .split('\n')
    .map((l) => l.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
}

let calls = 0;
function renderWith(forced) {
  const real = React.useState;
  let call = 0;
  React.useState = function (init) {
    call++;
    return real(call in forced ? forced[call] : init);
  };
  try {
    return ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, {}));
  } finally {
    React.useState = real;
    calls = Math.max(calls, call);
  }
}

const idx = (name) => hookVars.indexOf(name) + 1; // 1-based, 0 = not found
const TAB = idx('activeTab') || 1;
const states = {};
const texts = {};
function snap(key, forced) {
  let lines;
  try {
    lines = textLines(renderWith(forced));
  } catch (e) {
    lines = ['RENDER ERROR: ' + String(e.message).split('\n')[0]];
  }
  const h = sha(lines.join('\n'));
  texts[h] = lines;
  states[key] = h;
}

// 1) every tab, default view
for (const t of tabs) snap(`${t}`, { [TAB]: t });
// 2) every tab x every view-control value (single factor), and the funnels sub-views crossed with
//    every other control, since most controls only appear inside a sub-view
const ctrl = Object.keys(values).filter((v) => idx(v));
for (const t of tabs)
  for (const v of ctrl)
    for (const x of values[v])
      snap(`${t} | ${v}=${x}`, { [TAB]: t, [idx(v)]: x });
if (idx('funView'))
  for (const fv of values.funView || [])
    for (const v of ctrl)
      if (v !== 'funView')
        for (const x of values[v])
          snap(`funnels/${fv} | ${v}=${x}`, {
            [TAB]: 'funnels',
            [idx('funView')]: fv,
            [idx(v)]: x,
          });
// 3) the evaluations verdict checkboxes, one off at a time (row order used to depend on these)
if (idx('revInc')) {
  const base = { acceptable: true, unacceptable: true, 'not-reviewed': true };
  for (const by of values.revBy || ['sg'])
    for (const k of Object.keys(base))
      snap(`evaluations | revBy=${by} | ${k}=off`, {
        [TAB]: 'evaluations',
        [idx('revBy')]: by,
        [idx('revInc')]: Object.assign({}, base, { [k]: false }),
      });
}

fs.writeFileSync(
  out,
  JSON.stringify({
    source,
    data_sha: sha(dataStr),
    render_bytes: Buffer.byteLength(render, 'utf8'),
    hooks_parsed: hookVars.length,
    hooks_called: calls,
    tabs,
    states,
    texts,
  }),
);
console.log(
  `snapshot: ${Object.keys(states).length} states, ${
    Object.keys(texts).length
  } distinct screens, ` +
    `${tabs.length} tabs, hooks parsed ${
      hookVars.length
    } / called ${calls}, data ${sha(dataStr)}, ` +
    `render ${Buffer.byteLength(render, 'utf8')} bytes -> ${out}`,
);
if (hookVars.length !== calls)
  console.log(
    'WARNING: parsed hook count != runtime hook count; forced states may land on the wrong hook',
  );
const errs = Object.values(texts).filter(
  (l) => l[0] && l[0].startsWith('RENDER ERROR'),
).length;
if (errs) console.log(`WARNING: ${errs} screen(s) threw while rendering`);
