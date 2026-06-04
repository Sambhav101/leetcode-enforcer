"""The full-screen blocker window (issue #5).

A frameless, always-on-top, full-screen pywebview window that presents a LeetCode
problem with a code editor and Submit. It releases only when the submission is
Accepted (DESIGN.md §4a/§4b). The escape hatch (#6), LLM hints (#7), and the
scheduler (#8) are wired in their own issues; here we build the surface and the
submit → verdict → release loop.

``webview`` is imported lazily inside ``run_blocker`` so this module (and its pure
helpers) can be imported/tested without a GUI backend.
"""

from . import leetcode
from .leetcode import Problem, SUPPORTED_LANGS

# Friendly labels for the languages we support (issue #16).
LANG_LABELS = {"python3": "Python", "cpp": "C++", "rust": "Rust"}


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
    }


class BlockerApi:
    """JS ↔ Python bridge for the blocker window."""

    def __init__(self, problem: Problem, languages=SUPPORTED_LANGS):
        self._problem = problem
        self._languages = languages
        self._released = False

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
        return {
            "ok": True,
            "accepted": verdict.accepted,
            "status": verdict.status,
            "total_correct": verdict.total_correct,
            "total_testcases": verdict.total_testcases,
        }

    def hint(self) -> dict:
        # Wired to the Socratic local-LLM helper in issue #7.
        return {"text": "Hints arrive in issue #7 (local Ollama helper)."}

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
        import webview
        self._released = True
        for w in list(webview.windows):
            try:
                w.destroy()
            except Exception:
                pass


_HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/material-darker.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/clike/clike.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/rust/rust.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/closebrackets.min.js"></script>
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
  #hintbox { font-size:12px; color:rgba(238,240,246,0.82); background:rgba(142,162,255,0.08);
    border:0.5px solid rgba(142,162,255,0.20); border-radius:9px; padding:10px; display:none; }
  .footer { padding:8px 20px; border-top:0.5px solid rgba(255,255,255,0.08); text-align:right; }
  .escape { font-size:11px; color:rgba(255,255,255,0.35); background:none; border:none; cursor:pointer; }
  .escape:hover { color:rgba(255,141,141,0.8); }
  .spin { display:inline-block; animation:spin 1s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
</style></head><body>
  <div class="bar">
    <span class="lock">🔒 Solve to continue</span>
    <span class="pnum" id="pnum"></span>
    <span class="ptitle" id="ptitle"></span>
    <span class="diff" id="diff"></span>
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
        <button class="btn submit" id="submitBtn" onclick="submit()">Submit</button>
      </div>
      <div id="verdict" class="info"></div>
      <div id="hintbox"></div>
      <textarea id="code" spellcheck="false"></textarea>
    </div>
  </div>
  <div class="footer"><button class="escape" onclick="escapeHatch()">emergency exit</button></div>
<script>
  let S=null, editor=null;
  const CM_MODE={python3:'python', cpp:'text/x-c++src', rust:'rust'};
  const $=id=>document.getElementById(id);
  async function load(){
    S=await window.pywebview.api.state();
    $('pnum').textContent='#'+S.number;
    $('ptitle').textContent=S.title;
    $('diff').textContent=S.difficulty; $('diff').className='diff '+S.difficulty;
    $('content').innerHTML=S.content_html||'<p>(no description)</p>';
    $('topics').innerHTML=S.topics.map(t=>'<span class="tag">'+t+'</span>').join('');
    const sel=$('lang'); sel.innerHTML=S.languages.map(l=>'<option value="'+l.slug+'">'+l.label+'</option>').join('');
    editor=CodeMirror.fromTextArea($('code'), {
      lineNumbers:true, theme:'material-darker', matchBrackets:true, autoCloseBrackets:true,
      indentUnit:4, tabSize:4, indentWithTabs:false,
      extraKeys:{ Tab:cm=>cm.replaceSelection('    ','end'), 'Shift-Tab':cm=>cm.execCommand('indentLess') },
    });
    loadStarter();
  }
  function loadStarter(){
    const l=S.languages.find(x=>x.slug===$('lang').value);
    editor.setOption('mode', CM_MODE[$('lang').value]||'text/plain');
    editor.setValue((l&&l.starter)||'');
  }
  function openLink(){ window.open(S.url); }
  async function submit(){
    const btn=$('submitBtn'), v=$('verdict');
    btn.disabled=true; v.className='info'; v.innerHTML='<span class="spin">⏳</span> Submitting & judging…';
    const r=await window.pywebview.api.submit($('lang').value, editor.getValue());
    if(!r.ok){ v.className='bad'; v.textContent='⚠ '+r.error; btn.disabled=false; return; }
    if(r.accepted){ v.className='ok'; v.textContent='✅ Accepted! Releasing…';
      setTimeout(()=>window.pywebview.api.release(), 1200); return; }
    v.className='bad'; v.textContent='❌ '+r.status+(r.total_correct!=null?(' ('+r.total_correct+'/'+r.total_testcases+')'):'');
    btn.disabled=false;
  }
  async function getHint(){ const r=await window.pywebview.api.hint(); const b=$('hintbox'); b.style.display='block'; b.textContent=r.text; }
  async function escapeHatch(){
    const typed=prompt('Emergency exit — this WILL be logged.\nType exactly:  I GIVE UP');
    if(typed===null) return;
    const r=await window.pywebview.api.escape(typed);
    if(!r.ok) alert(r.error);
  }
  window.addEventListener('pywebviewready', load);
</script></body></html>"""


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
