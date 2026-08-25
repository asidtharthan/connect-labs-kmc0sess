/**
 * Reprint the render template with its comments removed, for SHIPPING only.
 *
 * The template is injected into Labs verbatim, comments and all, and this codebase comments heavily on
 * purpose - the reasoning next to a rule is what makes the render auditable months later. That costs
 * 27 KB of a hard 512 KB render_code limit, and the limit was down to 2 KB of headroom.
 *
 * So: the SOURCE keeps every comment, and only the published copy is stripped. Babel parses and
 * reprints (no presets, no transforms) so JSX survives untouched and nothing is minified beyond
 * dropping comments - a mangled reprint would be far worse than a large file.
 *
 * The data placeholder is itself a comment, so the caller swaps it for a string literal first and
 * puts the real payload back afterwards. That also keeps the payload byte-identical to
 * render_data.json, which brutal_verify checks.
 *
 *   node strip_render_comments.js <in.js> <out.js>
 */
const fs = require('fs');
const babel = require('@babel/core');

const [, , inPath, outPath] = process.argv;
if (!inPath || !outPath) {
  console.error('usage: node strip_render_comments.js <in.js> <out.js>');
  process.exit(2);
}
const src = fs.readFileSync(inPath, 'utf8');
const TOKEN = '"__DATA_PLACEHOLDER__"';
if (!src.includes('/*__DATA__*/')) {
  console.error('ABORT: template has no /*__DATA__*/ placeholder');
  process.exit(1);
}
const out = babel.transformSync(src.replace('/*__DATA__*/', TOKEN), {
  configFile: false,
  babelrc: false,
  comments: false,
  compact: false,
  parserOpts: { plugins: ['jsx'] },
});
if (!out || !out.code.includes(TOKEN)) {
  console.error('ABORT: data placeholder did not survive the reprint');
  process.exit(1);
}
// Hand back a template with the ORIGINAL placeholder so the caller's inject step is unchanged.
fs.writeFileSync(outPath, out.code.replace(TOKEN, '/*__DATA__*/'), 'utf8');
const a = Buffer.byteLength(src) / 1024,
  b = Buffer.byteLength(out.code) / 1024;
console.log(
  `[strip] ${a.toFixed(1)} KB -> ${b.toFixed(1)} KB code (comments removed for shipping, source untouched)`,
);
