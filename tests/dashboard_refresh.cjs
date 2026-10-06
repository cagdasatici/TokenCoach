// Run against generated sample HTML: NODE_PATH=/tmp/tc-dashboard-tests/node_modules node tests/dashboard_refresh.cjs /tmp/tc-refresh.html
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const initial = JSON.parse(html.match(/<script[^>]*id="data"[^>]*>(.*?)<\/script>/s)[1]);
let count = 0, next = structuredClone(initial), fail = false, pending = null;
const intervals = [], errors = [];
const vc = new VirtualConsole(); vc.on('jsdomError', error => errors.push(error));
const dom = new JSDOM(html, {runScripts:'dangerously', url:'http://127.0.0.1:47821/?t=sample', pretendToBeVisual:true, virtualConsole:vc,
  beforeParse(w) {
    w.scrollTo = (x,y) => { w.testScroll = [x,y]; };
    w.setInterval = (fn,ms) => { intervals.push([fn,ms]); return intervals.length; };
    w.fetch = async (url) => { const action = String(url).startsWith("/api/"); count++; if (fail) throw Error('offline'); if (pending) await pending.promise; return {ok:true, json:async()=>action ? {ok:true} : structuredClone(next)}; };
    w.AbortSignal.timeout = () => undefined;
  }});
const w = dom.window;
function defer() { let resolve; const promise=new Promise(r=>resolve=r); return {promise,resolve}; }
async function run() {
  assert.deepEqual(errors, [], 'initial dashboard must render without JS errors');
  const initialCount = w.eval('P.length');
  w.eval('D.demo = false'); next.demo = false; // Exercise production freshness wording with synthetic data.
  w.eval("S.group='claude'; S.adv=true; S.q='a saved search'; save(); render();");
  next.generated += 301;
  next.advice_html = "<p>Updated synthetic advice</p>";
  next.live.indexed_at = next.generated;
  next.health.read_at = next.generated;
  next.prompts.push([...next.prompts[0]]); next.prompts.at(-1)[0] = 'new-test-prompt';
  await w.eval('requestRefresh(); refreshData()');
  await new Promise(r=>setImmediate(r));
  assert.equal(w.eval('P.length'), initialCount + 1);
  assert.equal(w.eval('H.read_at'), next.generated);
  assert.match(w.document.getElementById('latest-advice').textContent, /Updated synthetic advice/);
  assert.equal(w.eval('S.group'), 'claude');
  assert.equal(w.eval('S.adv'), true);
  assert.equal(w.eval('S.q'), 'a saved search');
  assert.deepEqual([...w.testScroll], [0,0]);

  const edit = w.document.querySelector('[data-act="edit"]');
  assert.ok(edit, 'sample lessons must support an actual editor interaction');
  edit.click();
  const rule = w.document.querySelector('.ed-rule'); rule.value = 'Unsaved rule stays';
  const beforeEdit = count;
  w.eval('requestRefresh()');
  assert.equal(count, beforeEdit);
  assert.equal(rule.value, 'Unsaved rule stays');
  assert.ok(w.eval('refreshDue'));
  w.document.querySelector('[data-act="edit-cancel"]').click();
  w.document.activeElement.blur();
  intervals.find(([,ms])=>ms===5000)[0]();
  await new Promise(r=>setImmediate(r));
  assert.ok(count > beforeEdit, 'deferred refresh runs after editor closes');

  pending = defer();
  const oldGenerated = w.eval('D.generated');
  next.generated += 301;
  const inFlight = w.eval('refreshData()');
  // Start an editor while the request is in flight. Its DOM must survive.
  w.document.querySelector('[data-act="edit"]').click();
  const lateRule = w.document.querySelector('.ed-rule'); lateRule.value = 'Late edit';
  pending.resolve(); await inFlight; pending = null;
  assert.equal(w.eval('D.generated'), oldGenerated);
  assert.equal(lateRule.value, 'Late edit');
  w.document.querySelector('[data-act="edit-cancel"]').click();
  w.document.activeElement.blur();

  pending = defer();
  const action = w.eval("api('template/delete', {id:1})");
  const actionCount = count;
  w.eval('requestRefresh()');
  assert.equal(count, actionCount, 'an API action defers refresh');
  pending.resolve(); await action; pending = null;

  fail = true;
  await w.eval('refreshData()');
  assert.equal(w.eval('D.generated'), oldGenerated);
  assert.match(w.document.getElementById('updated').textContent, /unavailable.*previous data/);
  fail = false;
  await w.eval('refreshData()');
  assert.equal(w.eval('D.generated'), next.generated);
  assert.deepEqual(errors, []);
  dom.window.close();
  const staticData = structuredClone(initial); staticData.live = null; staticData.demo = false;
  const staticHtml = html.replace(/(<script[^>]*id="data"[^>]*>).*?(<\/script>)/s, (_,a,b)=>a+JSON.stringify(staticData).replaceAll('</','<\\/')+b);
  let staticIntervals = 0;
  const staticDom = new JSDOM(staticHtml, {runScripts:'dangerously', url:'file:///tmp/sample.html', virtualConsole:vc, beforeParse(w) {
    w.setInterval = () => { staticIntervals++; };
  }});
  assert.equal(staticIntervals, 0, 'read-only copies must not refresh');
  assert.match(staticDom.window.document.getElementById('updated').textContent, /read-only copy/);
  staticDom.window.close();
  console.log('Dashboard refresh: fresh data, health, filters, deferred/late edits, scroll and outage recovery pass');
}
run().catch(e=>{ console.error(e); dom.window.close(); process.exitCode=1; });
