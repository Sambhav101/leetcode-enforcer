"""The full-screen blocker window (issue #5).

A frameless, always-on-top, full-screen pywebview window that presents a LeetCode
problem with a code editor and Submit. It releases only when the submission is
Accepted (DESIGN.md §4a/§4b). The escape hatch (#6), LLM hints (#7), and the
scheduler (#8) are wired in their own issues; here we build the surface and the
submit → verdict → release loop.

``webview`` is imported lazily inside ``run_blocker`` so this module (and its pure
helpers) can be imported/tested without a GUI backend.
"""

import os

from . import banks, leetcode
from .leetcode import Problem, SUPPORTED_LANGS

# Friendly labels for the languages we support (issue #16).
LANG_LABELS = {"python3": "Python", "cpp": "C++", "rust": "Rust"}

# CodeMirror is vendored locally and inlined into the page (issue #36) so the
# blocker renders instantly and offline — no CDN, no blocking-render white screen.
_VENDOR = os.path.join(os.path.dirname(__file__), "vendor", "codemirror")


def _read_vendor(name: str) -> str:
    try:
        with open(os.path.join(_VENDOR, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""   # falls back to the plain-textarea editor in JS


_CM_CSS = _read_vendor("cm.css") + "\n" + _read_vendor("material-darker.css")
# Order matters: simple.js defines CodeMirror.defineSimpleMode, which rust.js needs
# (without it rust highlighting silently falls back to plaintext — issue #40).
_CM_JS = "\n".join(_read_vendor(n) for n in (
    "cm.js", "clike.js", "python.js", "simple.js", "rust.js",
    "matchbrackets.js", "closebrackets.js"))


def resolve_fallback(fallback, enabled_banks, solved_slugs, *,
                     fetch=leetcode.fetch_problem) -> list:
    """Turn ``escape.choose_fallback`` output into actual Problems for the loop (#22).

    ``resolve`` mode re-fetches the user's recently solved slugs; ``easy`` mode draws
    fresh free-tier Easy problems from the curated banks (no history to re-serve).
    """
    if fallback["mode"] == "resolve":
        return [fetch(slug) for slug in fallback["slugs"]]
    return banks.select_easy_problems(enabled_banks, solved_slugs, fallback["count"],
                                      fetch=fetch)


def build_state(problem: Problem, languages=SUPPORTED_LANGS) -> dict:
    """Pure helper: the initial data the UI renders. Easy to unit-test."""
    langs = [
        {"slug": s, "label": LANG_LABELS.get(s, s),
         "starter": problem.starter_code(s) or ""}
        for s in languages
    ]
    return {
        "number": problem.number,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "url": problem.url,
        "topics": problem.topics,
        "content_html": problem.content_html,
        "languages": langs,
        "sample_testcase": problem.sample_testcase,
    }


class BlockerApi:
    """JS ↔ Python bridge for the blocker window."""

    def __init__(self, problem: Problem, languages=SUPPORTED_LANGS):
        self._problem = problem
        self._languages = languages
        self._released = False
        self._hint_level = 0
        self._downshift = False     # downshift loop active? (#22)
        self._queue = []            # fallback problems to clear before release
        self._qi = 0                # index of the current problem in the queue

    def state(self) -> dict:
        return build_state(self._problem, self._languages)

    def submit(self, lang: str, code: str) -> dict:
        """Submit to LeetCode; return a result dict the UI can render."""
        from . import credentials
        creds = credentials.load_credentials()
        if not creds:
            return {"ok": False, "error": "No LeetCode credentials. Run the setup to paste your cookie."}
        try:
            verdict = leetcode.submit_and_wait(self._problem, lang, code, creds)
        except leetcode.LeetCodeError as e:
            return {"ok": False, "error": str(e)}
        if verdict.accepted:
            from . import state
            state.record_solved(self._problem, lang)   # persist for quota/history (#9)
        return {
            "ok": True,
            "accepted": verdict.accepted,
            "status": verdict.status,
            "total_correct": verdict.total_correct,
            "total_testcases": verdict.total_testcases,
        }

    def run(self, lang: str, code: str, data_input: str) -> dict:
        """Run (not submit) against the given test input (#34)."""
        from . import credentials
        creds = credentials.load_credentials()
        if not creds:
            return {"ok": False, "error": "No LeetCode credentials. Run the setup to paste your cookie."}
        try:
            r = leetcode.run_and_wait(self._problem, lang, code, data_input, creds)
        except leetcode.LeetCodeError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "correct": r.ok, "status": r.status,
                "output": r.output, "expected": r.expected, "error": r.error}

    def hint(self, code: str = "", question: str = "") -> dict:
        """Return a progressive Socratic hint from the local LLM (issue #7)."""
        from . import helper
        self._hint_level += 1
        try:
            text = helper.get_hint(self._problem, code, question, level=self._hint_level)
        except helper.LLMError as e:
            self._hint_level -= 1
            return {"ok": False, "error": str(e)}
        return {"ok": True, "text": text, "level": self._hint_level}

    def start_downshift(self) -> dict:
        """First tier of the escape flow (#22): swap the hard problem for a queue of
        easier ones. Release happens only after the whole queue is Accepted.

        Re-serves the user's recently solved problems, or fresh Easy ones if there's
        no history (``escape.choose_fallback``). On a load failure (e.g. LeetCode
        down) returns ``ok=False`` so the UI can fall back to the give-up tier —
        the user is never trapped.
        """
        from . import config, escape as escape_mod, state
        cfg = config.load_config()
        solved = state.solved_slugs()
        fallback = escape_mod.choose_fallback(solved)
        try:
            queue = resolve_fallback(fallback, cfg["banks"], solved)
        except (leetcode.LeetCodeError, banks.NoProblemAvailable) as e:
            return {"ok": False, "error": str(e)}
        if not queue:
            return {"ok": False, "error": "Couldn't load downshift problems."}
        self._downshift = True
        self._queue = queue
        self._qi = 0
        self._problem = queue[0]
        return {"ok": True, "problem": build_state(queue[0], self._languages),
                "index": 1, "total": len(queue)}

    def advance_downshift(self) -> dict:
        """Move to the next problem in the downshift queue after an Accepted.

        Returns ``done=True`` once every fallback problem has been cleared (the UI
        then releases); otherwise returns the next problem and its 1-based position.
        """
        self._qi += 1
        if self._qi >= len(self._queue):
            return {"done": True}
        self._problem = self._queue[self._qi]
        return {"done": False, "problem": build_state(self._problem, self._languages),
                "index": self._qi + 1, "total": len(self._queue)}

    def escape(self, confirmation: str) -> dict:
        """Give up (last resort): requires the phrase; logs it and sets a 1h re-trigger.

        The downshift option (solve 3 past/easy problems first) is the UI loop wired
        in #22 once the state store/scheduler exist; this is the final give-up path.
        """
        from . import escape as escape_mod
        if not escape_mod.verify_phrase(confirmation):
            return {"ok": False, "error": f"Type exactly: {escape_mod.REQUIRED_PHRASE}"}
        next_trigger = escape_mod.record_giveup(self._problem.number, self._problem.title)
        self._release()
        return {"ok": True, "next_trigger": next_trigger.isoformat(timespec="seconds")}

    def release(self) -> bool:
        self._release()
        return True

    def _release(self):
        """Release the blocker.

        NOTE: calling pywebview ``window.destroy()`` synchronously from inside a
        js_api bridge call deadlocks the Cocoa main thread (window hangs / "not
        responding") — a reentrancy hazard of the synchronous webview bridge, the
        same issue memento hit. The proven workaround is a hard process exit: the
        blocker is the terminal action of its process and state is already saved
        before this runs. (The durable fix is the Phase-2 native rewrite, whose
        async message handler avoids this entirely. For the future daemon, run the
        blocker as a subprocess so this only exits the child — see #23.)
        """
        import os
        self._released = True
        os._exit(0)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<style>/*__CM_CSS__*/</style>
<script>/*__CM_JS__*/</script>
<style>
  :root { color-scheme: dark; }
  * { box-sizing:border-box; margin:0; -webkit-font-smoothing:antialiased; }
  body { height:100vh; background:#0e0f15; color:#eef0f6;
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
    display:flex; flex-direction:column; overflow:hidden; }
  .bar { display:flex; align-items:center; gap:12px; padding:14px 20px;
    border-bottom:0.5px solid rgba(255,255,255,0.10);
    background:linear-gradient(180deg, rgba(255,90,90,0.10), transparent); }
  .lock { font-size:13px; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; color:#ff8d8d; }
  .pnum { color:rgba(255,255,255,0.5); font-variant-numeric:tabular-nums; }
  .ptitle { font-size:16px; font-weight:650; }
  .diff { font-size:11px; font-weight:700; padding:2px 9px; border-radius:99px; }
  .diff.Easy { background:rgba(95,220,160,0.18); color:#5fdca0; }
  .diff.Medium { background:rgba(255,203,115,0.18); color:#ffcb73; }
  .diff.Hard { background:rgba(255,141,141,0.18); color:#ff8d8d; }
  .bar .spacer { flex:1; }
  .bar a { color:#8ea2ff; font-size:12px; text-decoration:none; }
  .main { flex:1; display:flex; min-height:0; }
  .left, .right { flex:1; min-width:0; overflow:auto; padding:20px 24px; }
  .left { border-right:0.5px solid rgba(255,255,255,0.10); }
  .left :is(p,pre,li) { line-height:1.55; color:rgba(238,240,246,0.88); margin-bottom:10px; }
  .left pre { background:rgba(255,255,255,0.05); padding:10px; border-radius:8px; overflow:auto; }
  .topics { margin-top:14px; display:flex; gap:6px; flex-wrap:wrap; }
  .tag { font-size:10px; padding:3px 8px; border-radius:99px; background:rgba(255,255,255,0.07); color:rgba(255,255,255,0.6); }
  .right { display:flex; flex-direction:column; gap:10px; }
  .row { display:flex; align-items:center; gap:10px; }
  select { font:inherit; font-size:13px; background:rgba(255,255,255,0.08); color:#eef0f6;
    border:0.5px solid rgba(255,255,255,0.16); border-radius:8px; padding:6px 10px; }
  textarea { flex:1; min-height:0; font-family:"SF Mono",Menlo,monospace; font-size:13px; line-height:1.5;
    background:#15171f; color:#eef0f6; border:0.5px solid rgba(255,255,255,0.14);
    border-radius:10px; padding:12px; resize:none; tab-size:4; }
  textarea:focus { outline:none; border-color:#8ea2ff; box-shadow:0 0 0 3px rgba(142,162,255,0.22); }
  .CodeMirror { flex:1; min-height:0; height:auto; border:0.5px solid rgba(255,255,255,0.14);
    border-radius:10px; font-family:"SF Mono",Menlo,monospace; font-size:13px; }
  .CodeMirror-focused { border-color:#8ea2ff; box-shadow:0 0 0 3px rgba(142,162,255,0.22); }
  .btn { font:inherit; font-size:13px; font-weight:600; border:none; border-radius:9px;
    padding:9px 16px; cursor:pointer; transition:filter .12s, transform .1s; }
  .btn:active { transform:scale(0.97); }
  .submit { background:linear-gradient(180deg,#54d99a,#34b97c); color:#04241a; }
  .ghost { background:rgba(255,255,255,0.10); color:#eef0f6; }
  .submit:disabled { opacity:.5; cursor:default; }
  #verdict { font-size:13px; font-weight:600; min-height:20px; }
  #verdict.ok { color:#5fdca0; } #verdict.bad { color:#ff8d8d; } #verdict.info { color:rgba(255,255,255,0.6); }
  .tlabel { font-size:10px; text-transform:uppercase; letter-spacing:1px; color:rgba(255,255,255,0.4); margin-top:2px; }
  .tin { flex:none; height:54px; font-family:"SF Mono",Menlo,monospace; font-size:12px;
    background:#15171f; color:#eef0f6; border:0.5px solid rgba(255,255,255,0.14);
    border-radius:8px; padding:8px; resize:none; }
  .tin:focus { outline:none; border-color:#8ea2ff; }
  #runresult { font-size:12px; font-variant-numeric:tabular-nums; min-height:16px; }
  #runresult.ok { color:#5fdca0; } #runresult.bad { color:#ff8d8d; } #runresult.info { color:rgba(255,255,255,0.6); }
  #hintbox { font-size:12px; color:rgba(238,240,246,0.82); background:rgba(142,162,255,0.08);
    border:0.5px solid rgba(142,162,255,0.20); border-radius:9px; padding:10px; display:none; }
  .footer { padding:8px 20px; border-top:0.5px solid rgba(255,255,255,0.08); text-align:right; }
  .escape { font-size:11px; color:rgba(255,255,255,0.35); background:none; border:none; cursor:pointer; }
  .escape:hover { color:rgba(255,141,141,0.8); }
  .ds { font-size:11px; font-weight:700; padding:2px 9px; border-radius:99px;
    background:rgba(142,162,255,0.18); color:#8ea2ff; display:none; }
  .overlay { position:fixed; inset:0; background:rgba(8,9,13,0.72); -webkit-backdrop-filter:blur(4px);
    backdrop-filter:blur(4px); display:none; align-items:center; justify-content:center; z-index:50; }
  .modal { width:min(460px,90vw); background:#171922; border:0.5px solid rgba(255,255,255,0.14);
    border-radius:16px; padding:22px; display:flex; flex-direction:column; gap:12px;
    box-shadow:0 24px 64px rgba(0,0,0,0.5); }
  .modal h2 { font-size:16px; font-weight:700; }
  .modal p { font-size:12px; color:rgba(255,255,255,0.6); line-height:1.5; }
  .tier { width:100%; text-align:left; padding:12px 14px; background:rgba(255,255,255,0.07);
    color:#eef0f6; border:0.5px solid rgba(255,255,255,0.12); }
  .tier:hover { filter:brightness(1.25); }
  .tier .sub { display:block; font-size:11px; font-weight:400; color:rgba(255,255,255,0.5); margin-top:3px; }
  .tier.danger:hover { border-color:rgba(255,141,141,0.5); }
  .cancel { background:none; border:none; color:rgba(255,255,255,0.4); font-size:12px; cursor:pointer; align-self:center; }
  .spin { display:inline-block; animation:spin 1s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style></head><body>
  <div class="bar">
    <span class="lock">🔒 Solve to continue</span>
    <span class="pnum" id="pnum"></span>
    <span class="ptitle" id="ptitle"></span>
    <span class="diff" id="diff"></span>
    <span class="ds" id="dsbanner"></span>
    <span class="spacer"></span>
    <a id="weblink" href="#" onclick="openLink();return false;">Open on LeetCode ↗</a>
  </div>
  <div class="main">
    <div class="left"><div id="content"></div><div class="topics" id="topics"></div></div>
    <div class="right">
      <div class="row">
        <select id="lang" onchange="loadStarter()"></select>
        <button class="btn ghost" onclick="getHint()">💡 Hint</button>
        <span class="spacer" style="flex:1"></span>
        <button class="btn ghost" id="runBtn" onclick="runCode()">▶ Run</button>
        <button class="btn submit" id="submitBtn" onclick="submit()">Submit</button>
      </div>
      <div id="verdict" class="info"></div>
      <div id="hintbox"></div>
      <textarea id="code" spellcheck="false"></textarea>
      <div class="tlabel">Test input (editable)</div>
      <textarea id="testinput" class="tin" spellcheck="false"></textarea>
      <div id="runresult" class="info"></div>
    </div>
  </div>
  <div class="footer"><button class="escape" onclick="openEscape()">I can't solve this</button></div>
  <div class="overlay" id="overlay">
    <div class="modal">
      <h2>Stuck on this one?</h2>
      <p>Quitting outright is the last resort. Try the easier path first.</p>
      <button class="btn tier" onclick="startDownshift()">⬇️ Downshift — solve easier problems instead
        <span class="sub">Re-serves recent problems (or Easy ones). The block clears once all are Accepted.</span></button>
      <button class="btn tier danger" onclick="giveUp()">🏳️ I give up
        <span class="sub">Releases now, logs it, and re-triggers after a 1-hour cooldown.</span></button>
      <button class="cancel" onclick="closeEscape()">Keep trying</button>
    </div>
  </div>
<script>
  let S=null, cm=null, downshiftMode=false;
  const CM_MODE={python3:'python', cpp:'text/x-c++src', rust:'rust'};
  const $=id=>document.getElementById(id);
  // editor abstraction: CodeMirror if available, else the plain <textarea> fallback
  function getCode(){ return cm ? cm.getValue() : $('code').value; }
  function setCode(v){ if(cm){ cm.setValue(v); } else { $('code').value=v; } }
  function setMode(slug){ if(cm){ cm.setOption('mode', CM_MODE[slug]||'text/plain'); } }
  function applyState(s){
    S=s;
    $('pnum').textContent='#'+S.number;
    $('ptitle').textContent=S.title;
    $('diff').textContent=S.difficulty; $('diff').className='diff '+S.difficulty;
    $('content').innerHTML=S.content_html||'<p>(no description)</p>';
    $('topics').innerHTML=S.topics.map(t=>'<span class="tag">'+t+'</span>').join('');
    const sel=$('lang'); sel.innerHTML=S.languages.map(l=>'<option value="'+l.slug+'">'+l.label+'</option>').join('');
    if(window.CodeMirror && !cm){
      cm=CodeMirror.fromTextArea($('code'), {
        lineNumbers:true, theme:'material-darker', matchBrackets:true, autoCloseBrackets:true,
        indentUnit:4, tabSize:4, indentWithTabs:false,
        extraKeys:{ Tab:c=>c.replaceSelection('    ','end'), 'Shift-Tab':c=>c.execCommand('indentLess') },
      });
    }
    $('testinput').value = S.sample_testcase || '';
    $('verdict').textContent=''; $('verdict').className='info';
    $('runresult').textContent='';
    loadStarter();
  }
  async function load(){ applyState(await window.pywebview.api.state()); }
  function loadStarter(){
    const l=S.languages.find(x=>x.slug===$('lang').value);
    setMode($('lang').value);
    setCode((l&&l.starter)||'');
  }
  function openLink(){ window.open(S.url); }
  async function submit(){
    const btn=$('submitBtn'), v=$('verdict');
    btn.disabled=true; v.className='info'; v.innerHTML='<span class="spin">⏳</span> Submitting & judging…';
    const r=await window.pywebview.api.submit($('lang').value, getCode());
    if(!r.ok){ v.className='bad'; v.textContent='⚠ '+r.error; btn.disabled=false; return; }
    if(r.accepted){ v.className='ok';
      if(downshiftMode){ v.textContent='✅ Accepted!'; advanceDownshift(); return; }
      v.textContent='✅ Accepted! Releasing…';
      setTimeout(()=>window.pywebview.api.release(), 1200); return; }
    v.className='bad'; v.textContent='❌ '+r.status+(r.total_correct!=null?(' ('+r.total_correct+'/'+r.total_testcases+')'):'');
    btn.disabled=false;
  }
  async function runCode(){
    const rr=$('runresult'), b=$('runBtn');
    b.disabled=true; rr.className='info'; rr.innerHTML='<span class="spin">▶</span> Running…';
    const r=await window.pywebview.api.run($('lang').value, getCode(), $('testinput').value);
    b.disabled=false;
    if(!r.ok){ rr.className='bad'; rr.textContent='⚠ '+r.error; return; }
    if(r.error){ rr.className='bad'; rr.textContent='Error: '+r.error; return; }
    rr.className = r.correct ? 'ok' : 'bad';
    let msg = r.correct ? '✔ Passed sample' : '✗ Mismatch';
    if(r.output) msg += ' · output: '+JSON.stringify(r.output);
    if(r.expected) msg += ' · expected: '+JSON.stringify(r.expected);
    rr.textContent = msg;
  }
  async function getHint(){
    const b=$('hintbox'); b.style.display='block'; b.innerHTML='<span class="spin">💡</span> Thinking on your local model…';
    const r=await window.pywebview.api.hint(getCode());
    b.textContent = r.ok ? ('Hint '+r.level+': '+r.text) : ('⚠ '+r.error);
  }
  function openEscape(){ $('overlay').style.display='flex'; }
  function closeEscape(){ $('overlay').style.display='none'; }
  function setDsBanner(i,n){ const b=$('dsbanner'); b.style.display='inline-block'; b.textContent='Downshift '+i+'/'+n; }
  async function startDownshift(){
    closeEscape();
    const v=$('verdict'); v.className='info'; v.innerHTML='<span class="spin">⬇️</span> Loading easier problems…';
    const r=await window.pywebview.api.start_downshift();
    if(!r.ok){ alert('Could not start downshift: '+r.error+'\n\nYou can still give up.'); v.textContent=''; return; }
    downshiftMode=true;
    applyState(r.problem);
    setDsBanner(r.index, r.total);
  }
  async function advanceDownshift(){
    const r=await window.pywebview.api.advance_downshift();
    if(r.done){ $('verdict').className='ok'; $('verdict').textContent='✅ Downshift complete! Releasing…';
      setTimeout(()=>window.pywebview.api.release(), 1200); return; }
    applyState(r.problem);
    setDsBanner(r.index, r.total);
    $('verdict').className='ok'; $('verdict').textContent='✓ Solved — next problem ('+r.index+'/'+r.total+')';
  }
  async function giveUp(){
    closeEscape();
    const typed=prompt('Give up — this WILL be logged and the app re-triggers in 1 hour.\nType exactly:  I GIVE UP');
    if(typed===null) return;
    const r=await window.pywebview.api.escape(typed);
    if(!r.ok) alert(r.error);
  }
  window.addEventListener('pywebviewready', load);
</script></body></html>"""

# Inline the vendored CodeMirror CSS/JS into the page (issue #36). Using .replace
# (not an f-string) since the assets contain braces.
_HTML = _TEMPLATE.replace("/*__CM_CSS__*/", _CM_CSS).replace("/*__CM_JS__*/", _CM_JS)


def run_blocker(problem: Problem, languages=SUPPORTED_LANGS, fullscreen=True):
    """Launch the blocker for ``problem`` (blocks until released).

    ``fullscreen=False`` opens a normal resizable window — handy for previewing the
    UI without the screen-takeover; the real app uses the default full-screen mode.
    """
    import webview
    api = BlockerApi(problem, languages)
    if fullscreen:
        webview.create_window(
            "leetcode-enforcer", html=_HTML, js_api=api,
            fullscreen=True, frameless=True, on_top=True,
        )
    else:
        webview.create_window(
            "leetcode-enforcer (preview)", html=_HTML, js_api=api,
            width=1000, height=680,
        )
    webview.start()
    return api
