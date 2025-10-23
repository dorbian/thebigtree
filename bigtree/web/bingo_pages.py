# bigtree/web/bingo_pages.py
# Two standalone, pretty HTML pages embedded as strings.

BINGO_CARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bingo — Play</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
:root{
  --bg:#0b1220;
  --panel:#0f172a;
  --muted:#94a3b8;
  --text:#e2e8f0;
  --accent:#60a5fa;
  --accent-2:#f472b6;
  --ok:#22c55e;
  --err:#ef4444;
  --ring:#334155;

  --cell:70px;
  --gap:10px;
  --radius:14px;
  --shadow:0 8px 30px rgba(2,8,23,.25);
}

*{box-sizing:border-box}
html,body{margin:0;padding:0;background:linear-gradient(180deg,#0b1220,#0a0f1a);color:var(--text);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial,"Noto Sans","Apple Color Emoji","Segoe UI Emoji";min-height:100%}

.container{max-width:1100px;margin:0 auto;padding:24px}
.card{background:var(--panel);border:1px solid #1f2937;border-radius:var(--radius);box-shadow:var(--shadow);padding:22px}

.header{
  display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px
}
.title{font-weight:800;letter-spacing:.3px}
.badges{display:flex;gap:8px;flex-wrap:wrap}
.badge{border:1px solid #243244;background:#0b1220; border-radius:999px;padding:6px 10px;color:#dbeafe;font-size:12px}
.badge.accent{border-color:#1d4ed8;background:#0a122a}
.info{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 0}
.kv{border:1px solid #1f2a44;border-radius:10px;padding:6px 10px;color:#cbd5e1;background:#0c1426}

.flex{display:flex;gap:18px;flex-wrap:wrap}
.left{flex:1 1 360px}
.right{flex:1 1 260px}

.gridhead{display:grid;grid-template-columns:repeat(4,var(--cell));gap:var(--gap);margin-bottom:6px}
.headcell{background:#0a1224;border:1px solid var(--ring);border-radius:12px;text-align:center;font-weight:900;letter-spacing:1px;padding:8px 0;color:#c7d2fe}

.grid{display:grid;grid-template-columns:repeat(4,var(--cell));gap:var(--gap)}
.cell{
  width:var(--cell);height:var(--cell);
  display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:22px;
  background:#0b1326;border:1px solid var(--ring);border-radius:12px;color:#e2e8f0;
  transition:.18s transform,.18s box-shadow,.18s background,.18s color;
  cursor:pointer;
}
.cell:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(2,8,23,.35)}
.cell.marked{background:#124b26;border-color:#14532d;color:#bbf7d0}
.cell.called{outline:2px dashed #22c55e;outline-offset:-6px}

.actions{display:flex;gap:10px;margin-top:16px;align-items:center;flex-wrap:wrap}
.btn{
  border:1px solid #1d4ed8;background:#0a122a;color:#dbeafe;border-radius:10px;padding:10px 14px;font-weight:700;cursor:pointer;
}
.btn.ok{border-color:#166534;background:#0a1f15;color:#bbf7d0}
.btn:disabled{opacity:.6;cursor:not-allowed}

.panel{background:#0a1224;border:1px solid var(--ring);border-radius:12px;padding:14px}

.calledWrap{display:grid;grid-template-columns:1fr;gap:10px}
.latest{
  display:flex;align-items:center;justify-content:center;
  font-size:42px;font-weight:900;letter-spacing:1px;
  height:80px;background:#0b1326;border:1px solid var(--ring);border-radius:12px;color:#93c5fd;
}
.calledGrid{display:grid;grid-template-columns:repeat(8,1fr);gap:6px}
.calledItem{
  text-align:center;padding:6px 0;border-radius:8px;background:#0b1326;border:1px solid var(--ring);color:#cbd5e1;font-weight:700
}

.claims{margin-top:10px;font-size:.95rem;color:#cbd5e1}
.claims ul{margin:6px 0 0;padding-left:18px}
.claimedPage{opacity:.5;filter:grayscale(1)}

.footer{margin-top:16px;color:var(--muted);font-size:12px;text-align:center}
a{color:#93c5fd;text-decoration:none}
a:hover{text-decoration:underline}
</style>
</head>
<body>
  <div class="container">
    <div class="card">
      <div class="header">
        <div>
          <div class="title">🎲 <span id="gTitle">Bingo</span></div>
          <div class="badges">
            <span class="badge">Game: <code id="gId">—</code></span>
            <span class="badge accent">Stage: <strong id="gStage">single</strong></span>
          </div>
          <div class="info">
            <span class="kv">Pot: <strong id="gPot">0</strong> <span id="gCur">gil</span></span>
            <span class="kv">Payouts — 1L:<strong id="p1">0</strong> • 2L:<strong id="p2">0</strong> • Full:<strong id="p3">0</strong></span>
          </div>
        </div>
        <div class="panel right">
          <div class="calledWrap">
            <div class="latest" id="latest">—</div>
            <div class="calledGrid" id="calledGrid"></div>
          </div>
        </div>
      </div>

      <div class="left">
        <div class="gridhead" id="gridHead"></div>
        <div class="grid" id="grid"></div>
        <div class="actions">
          <button class="btn ok" id="claimBtn">I have BINGO!</button>
          <button class="btn" id="refreshBtn">Refresh</button>
          <span id="status" style="color:#94a3b8"></span>
        </div>
        <div class="claims">
          <strong>Claims so far:</strong>
          <ul id="claimsList"></ul>
        </div>
      </div>
      <div class="footer">Tip: click a number to mark it. Latest called is shown big on the right.</div>
    </div>
  </div>

<script>
(function(){
  const qs = new URLSearchParams(location.search);
  const game = qs.get("game") || "";
  const card = qs.get("card") || "";
  const token = qs.get("token") || "";
  const api = (path) => token ? `${path}${path.includes('?')?'&':'?'}token=${encodeURIComponent(token)}` : path;

  const gridEl = document.getElementById('grid');
  const headEl = document.getElementById('gridHead');
  const calledGrid = document.getElementById('calledGrid');
  const latestEl = document.getElementById('latest');
  const claimBtn = document.getElementById('claimBtn');
  const refreshBtn = document.getElementById('refreshBtn');
  const statusEl = document.getElementById('status');
  const claimsList = document.getElementById('claimsList');

  document.getElementById('gId').textContent = game;

  async function jget(url){ const r = await fetch(api(url)); return await r.json(); }
  async function jpost(url, body){ const r = await fetch(api(url), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); return await r.json(); }

  function renderHeaderLetters(header){
    headEl.innerHTML = "";
    const txt = (header || "BING").slice(0,4).padEnd(4,' ');
    for(let i=0;i<4;i++){
      const d = document.createElement('div');
      d.className = 'headcell';
      d.textContent = txt[i];
      headEl.appendChild(d);
    }
  }

  function renderCard(cardData, called){
    gridEl.innerHTML = "";
    const nums = cardData.numbers || [];
    const marks = cardData.marks || [];
    for(let r=0;r<4;r++){
      for(let c=0;c<4;c++){
        const v = nums[r][c];
        const cell = document.createElement('div');
        cell.className = 'cell';
        if ((marks[r]||[])[c]) cell.classList.add('marked');
        if (called && called.indexOf(v) >= 0) cell.classList.add('called');
        cell.textContent = v;
        cell.addEventListener('click', async () => {
          const res = await jpost('/bingo/mark', {game_id: game, card_id: card, row: r, col: c});
          if (res.ok){
            cell.classList.add('marked');
            statusEl.textContent = "Marked.";
          }else{
            statusEl.textContent = res.message || "Error marking.";
          }
        });
        gridEl.appendChild(cell);
      }
    }
  }

  function renderCalled(called){
    calledGrid.innerHTML = "";
    if (!called || !called.length){ latestEl.textContent = "—"; return; }
    latestEl.textContent = String(called[called.length-1]);
    for(const n of called){
      const d = document.createElement('div');
      d.className = 'calledItem';
      d.textContent = n;
      calledGrid.appendChild(d);
    }
  }

  function renderClaims(state){
    const list = (state.game && state.game.claims) || [];
    claimsList.innerHTML = "";
    list.sort((a,b)=>(a.ts||0)-(b.ts||0));
    for(const c of list){
      const li = document.createElement('li');
      li.textContent = `${c.owner_name} (${c.stage})`;
      claimsList.appendChild(li);
    }
  }

  async function refresh(){
    const state = await jget(`/bingo/${encodeURIComponent(game)}`);
    if (!state || !state.active){ statusEl.textContent = "Game not active."; return; }
    const g = state.game;
    document.getElementById('gTitle').textContent = g.title || "Bingo";
    document.getElementById('gStage').textContent = g.stage || "single";
    document.getElementById('gPot').textContent = g.pot || 0;
    document.getElementById('gCur').textContent = g.currency || "gil";
    const pays = g.payouts || {single:0,double:0,full:0};
    document.getElementById('p1').textContent = pays.single||0;
    document.getElementById('p2').textContent = pays.double||0;
    document.getElementById('p3').textContent = pays.full||0;

    renderHeaderLetters(g.header || "BING");
    renderCalled(g.called || []);
    renderClaims(state);

    const cd = await jget(`/bingo/${encodeURIComponent(game)}/card/${encodeURIComponent(card)}`);
    if (!cd || !cd.ok){ statusEl.textContent = "Card not found."; return; }
    renderCard(cd.card, g.called || []);

    if (cd.card.claimed){
      claimBtn.disabled = true;
      document.body.classList.add('claimedPage');
    }else{
      claimBtn.disabled = false;
      document.body.classList.remove('claimedPage');
    }
  }

  claimBtn.addEventListener('click', async () => {
    const res = await jpost('/bingo/claim', { game_id: game, card_id: card });
    if (res.ok){
      claimBtn.disabled = true;
      document.body.classList.add('claimedPage');
      statusEl.textContent = "Claim sent!";
    }else{
      statusEl.textContent = res.message || "Claim failed.";
    }
  });
  refreshBtn.addEventListener('click', refresh);

  // initial + poll
  refresh();
  setInterval(refresh, 5000);
})();
</script>
</body>
</html>
"""

BINGO_OWNER_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Bingo — My Cards</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
:root{
  --bg:#0b1220;
  --panel:#0f172a;
  --muted:#94a3b8;
  --text:#e2e8f0;
  --accent:#60a5fa;
  --accent-2:#f472b6;
  --ok:#22c55e;
  --ring:#334155;

  --cell:60px;
  --gap:8px;
  --radius:14px;
  --shadow:0 8px 30px rgba(2,8,23,.25);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:linear-gradient(180deg,#0b1220,#0a0f1a);color:var(--text);font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,"Helvetica Neue",Arial,"Noto Sans","Apple Color Emoji","Segoe UI Emoji";min-height:100%}
.container{max-width:1200px;margin:0 auto;padding:24px}
.card{background:var(--panel);border:1px solid #1f2937;border-radius:var(--radius);box-shadow:var(--shadow);padding:22px}

.header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.title{font-weight:800;letter-spacing:.3px}
.badges{display:flex;gap:8px;flex-wrap:wrap}
.badge{border:1px solid #243244;background:#0b1220; border-radius:999px;padding:6px 10px;color:#dbeafe;font-size:12px}
.badge.accent{border-color:#1d4ed8;background:#0a122a}
.info{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 0}
.kv{border:1px solid #1f2a44;border-radius:10px;padding:6px 10px;color:#cbd5e1;background:#0c1426}

.top{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}
.panel{background:#0a1224;border:1px solid var(--ring);border-radius:12px;padding:14px}
.calledWrap{display:grid;grid-template-columns:1fr;gap:10px}
.latest{display:flex;align-items:center;justify-content:center;font-size:40px;font-weight:900;height:74px;background:#0b1326;border:1px solid var(--ring);border-radius:12px;color:#93c5fd}
.calledGrid{display:grid;grid-template-columns:repeat(8,1fr);gap:6px}
.calledItem{text-align:center;padding:6px 0;border-radius:8px;background:#0b1326;border:1px solid var(--ring);color:#cbd5e1;font-weight:700}

.claims{margin-top:8px;font-size:.95rem;color:#cbd5e1}
.claimsBar strong{font-weight:800}
.claimsBar{margin-top:6px}

.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-top:16px}
.cardwrap{background:#0b1326;border:1px solid var(--ring);border-radius:12px;padding:12px}
.cardwrap.claimed{opacity:.45;filter:grayscale(1)}

.gridhead{display:grid;grid-template-columns:repeat(4,var(--cell));gap:var(--gap);margin-bottom:6px}
.headcell{background:#0a1224;border:1px solid var(--ring);border-radius:10px;text-align:center;font-weight:900;letter-spacing:1px;padding:6px 0;color:#c7d2fe}
.grid{display:grid;grid-template-columns:repeat(4,var(--cell));gap:var(--gap)}
.cell{
  width:var(--cell);height:var(--cell);
  display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:20px;background:#0b1326;border:1px solid var(--ring);border-radius:10px;color:#e2e8f0;
  transition:.18s transform,.18s background,.18s color;
  cursor:pointer;
}
.cell:hover{transform:translateY(-1px)}
.cell.marked{background:#124b26;border-color:#14532d;color:#bbf7d0}
.cell.called{outline:2px dashed #22c55e;outline-offset:-6px}

.actions{display:flex;gap:8px;margin-top:8px;align-items:center}
.btn{border:1px solid #1d4ed8;background:#0a122a;color:#dbeafe;border-radius:10px;padding:8px 12px;font-weight:700;cursor:pointer}
.btn.ok{border-color:#166534;background:#0a1f15;color:#bbf7d0}
.btn:disabled{opacity:.6;cursor:not-allowed}

.footer{margin-top:14px;color:var(--muted);font-size:12px;text-align:center}
a{color:#93c5fd;text-decoration:none}
a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <div class="header">
      <div>
        <div class="title">🎲 <span id="gTitle">Bingo</span></div>
        <div class="badges">
          <span class="badge">Game: <code id="gId">—</code></span>
          <span class="badge">Owner: <strong id="ownerTag">—</strong></span>
          <span class="badge accent">Stage: <strong id="gStage">single</strong></span>
        </div>
        <div class="info">
          <span class="kv">Pot: <strong id="gPot">0</strong> <span id="gCur">gil</span></span>
          <span class="kv">Payouts — 1L:<strong id="p1">0</strong> • 2L:<strong id="p2">0</strong> • Full:<strong id="p3">0</strong></span>
        </div>
        <div class="claims claimsBar" id="claimsBox"><strong>Claims:</strong> —</div>
      </div>
      <div class="panel">
        <div class="calledWrap">
          <div class="latest" id="latest">—</div>
          <div class="calledGrid" id="calledGrid"></div>
        </div>
      </div>
    </div>

    <div class="cards" id="cards"></div>
    <div class="footer">Tip: click a number to mark it. Use the green button to claim when you win.</div>
  </div>
</div>

<script>
(function(){
  const qs = new URLSearchParams(location.search);
  const game = qs.get("game") || "";
  const owner = qs.get("owner") || "";
  const token = qs.get("token") || "";
  const api = (path) => token ? `${path}${path.includes('?')?'&':'?'}token=${encodeURIComponent(token)}` : path;

  document.getElementById('gId').textContent = game;
  document.getElementById('ownerTag').textContent = owner;

  async function jget(url){ const r = await fetch(api(url)); return await r.json(); }
  async function jpost(url, body){ const r = await fetch(api(url), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); return await r.json(); }

  function formatStage(s){ return s==="single"?"Single line":s==="double"?"Double line":"Whole card"; }

  function renderHeaderLetters(el, header){
    el.innerHTML = "";
    const txt = (header || "BING").slice(0,4).padEnd(4,' ');
    for(let i=0;i<4;i++){
      const d = document.createElement('div');
      d.className = 'headcell';
      d.textContent = txt[i];
      el.appendChild(d);
    }
  }

  function renderCalled(called){
    const calledGrid = document.getElementById('calledGrid');
    const latestEl = document.getElementById('latest');
    calledGrid.innerHTML = "";
    if (!called || !called.length){ latestEl.textContent = "—"; return; }
    latestEl.textContent = String(called[called.length-1]);
    for(const n of called){
      const d = document.createElement('div');
      d.className = 'calledItem';
      d.textContent = n;
      calledGrid.appendChild(d);
    }
  }

  function renderClaimsBar(state){
    const box = document.getElementById('claimsBox');
    const claims = (state.game && state.game.claims) || [];
    if (!claims.length){ box.innerHTML = "<strong>Claims:</strong> —"; return; }
    const parts = claims
      .sort((a,b)=>(a.ts||0)-(b.ts||0))
      .map(c => `${c.owner_name} (${c.stage})`);
    box.innerHTML = "<strong>Claims:</strong> " + parts.join(" • ");
  }

  function makeCardTile(gameHeader, gameCalled, gId, card){
    const wrap = document.createElement('div');
    wrap.className = 'cardwrap';
    if (card.claimed) wrap.classList.add('claimed');

    const head = document.createElement('div');
    head.className = 'gridhead';
    renderHeaderLetters(head, gameHeader);
    wrap.appendChild(head);

    const grid = document.createElement('div');
    grid.className = 'grid';

    const nums = card.numbers || [];
    const marks = card.marks || [];
    for(let r=0;r<4;r++){
      for(let c=0;c<4;c++){
        const v = nums[r][c];
        const cell = document.createElement('div');
        cell.className = 'cell';
        if ((marks[r]||[])[c]) cell.classList.add('marked');
        if (gameCalled && gameCalled.indexOf(v) >= 0) cell.classList.add('called');
        cell.textContent = v;
        cell.addEventListener('click', async () => {
          const res = await jpost('/bingo/mark', { game_id: gId, card_id: card.card_id, row: r, col: c });
          if (res.ok) cell.classList.add('marked');
        });
        grid.appendChild(cell);
      }
    }
    wrap.appendChild(grid);

    const actions = document.createElement('div');
    actions.className = 'actions';
    const btn = document.createElement('button');
    btn.className = 'btn ok';
    btn.textContent = 'I have BINGO!';
    btn.disabled = !!card.claimed;
    btn.addEventListener('click', async () => {
      const res = await jpost('/bingo/claim', { game_id: gId, card_id: card.card_id });
      if (res.ok){ btn.disabled = true; wrap.classList.add('claimed'); }
      else { alert(res.message || "Claim failed."); }
    });
    actions.appendChild(btn);
    wrap.appendChild(actions);
    return wrap;
  }

  async function refresh(){
    const state = await jget(`/bingo/${encodeURIComponent(game)}`);
    if (!state || !state.active) return;
    const g = state.game;
    document.getElementById('gTitle').textContent = g.title || "Bingo";
    document.getElementById('gStage').textContent = g.stage || "single";
    document.getElementById('gPot').textContent = g.pot || 0;
    document.getElementById('gCur').textContent = g.currency || "gil";
    document.getElementById('p1').textContent = (g.payouts||{}).single || 0;
    document.getElementById('p2').textContent = (g.payouts||{}).double || 0;
    document.getElementById('p3').textContent = (g.payouts||{}).full || 0;

    renderCalled(g.called || []);
    renderClaimsBar(state);

    // cards for owner
    const data = await jget(`/bingo/${encodeURIComponent(game)}/owner/${encodeURIComponent(owner)}/cards`);
    const cards = (data && data.cards) || [];
    const container = document.getElementById('cards');
    container.innerHTML = "";
    for (const cd of cards){
      container.appendChild(makeCardTile(g.header || "BING", g.called || [], g.game_id, cd));
    }
  }

  // Render static keys present in header actions
  // (small spans required in header)
  const topInfo = document.createElement('div');
  topInfo.innerHTML = `
    <span class="kv">Pot: <strong id="gPot">0</strong> <span id="gCur">gil</span></span>
    <span class="kv">Payouts — 1L:<strong id="p1">0</strong> • 2L:<strong id="p2">0</strong> • Full:<strong id="p3">0</strong></span>
  `;

  // initial + poll
  refresh();
  setInterval(refresh, 5000);
})();
</script>
</body>
</html>
"""
