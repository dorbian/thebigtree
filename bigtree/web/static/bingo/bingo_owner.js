document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(location.search);
  const game = params.get('game') || '';
  let resolvedGame = game;
  let owner = params.get('owner') || '';
  const token = params.get('token') || '';
  const grid = document.getElementById('list');
  const summary = document.getElementById('summary');
  const calledEl = document.getElementById('called');
  const contextPath = document.getElementById('contextPath');
  const contextMeta = document.getElementById('contextMeta');
  const contextStatus = document.getElementById('contextStatus');
  const potValue = document.getElementById('potValue');
  const stageValue = document.getElementById('stageValue');
  const headerValue = document.getElementById('headerValue');
  const payoutSingle = document.getElementById('payoutSingle');
  const payoutDouble = document.getElementById('payoutDouble');
  const payoutFull = document.getElementById('payoutFull');
  const claimBtn = document.getElementById('claimBtn');
  const claimMsg = document.getElementById('claimMsg');
  const autoDabEl = document.getElementById('autoDab');
  const bingoOverlay = document.getElementById('bingoOverlay');
  const callBall = document.getElementById('callBall');
  let selectedCardId = '';
  let localBingoPressed = false;
  let lastBallNumber = null;
  let callBallTimer = null;
  let redirected = false;

  function marksKey(cardId){
    return `bingo_marks_${resolvedGame}_${cardId}`;
  }

  function loadLocalMarks(cardId){
    try{
      const raw = localStorage.getItem(marksKey(cardId));
      return raw ? JSON.parse(raw) : [];
    }catch(e){ return []; }
  }

  function saveLocalMarks(cardId, marks){
    try{
      localStorage.setItem(marksKey(cardId), JSON.stringify(marks));
    }catch(e){}
  }

  function buildMarksForCard(card, calledSet){
    const nums = card.numbers || [];
    const marks = [];
    for(let r=0;r<nums.length;r++){
      marks[r] = [];
      for(let c=0;c<nums[r].length;c++){
        marks[r][c] = calledSet.has(nums[r][c]);
      }
    }
    return marks;
  }

  function buildDisplayMarks(card, calledSet, localMarks, autoMark){
    const nums = card.numbers || [];
    const marks = [];
    for(let r=0;r<nums.length;r++){
      marks[r] = [];
      for(let c=0;c<nums[r].length;c++){
        const local = localMarks[r] && localMarks[r][c];
        const called = autoMark && calledSet.has(nums[r][c]);
        marks[r][c] = !!local || called;
      }
    }
    return marks;
  }

  function hasWinningLine(marks){
    const size = marks.length;
    if (!size) return false;
    const width = marks[0].length;
    for(let r=0;r<size;r++){
      if (marks[r] && marks[r].every(Boolean)) return true;
    }
    for(let c=0;c<width;c++){
      let ok = true;
      for(let r=0;r<size;r++){
        if (!marks[r] || !marks[r][c]){
          ok = false;
          break;
        }
      }
      if (ok) return true;
    }
    if (size === width){
      let diag1 = true;
      let diag2 = true;
      for(let i=0;i<size;i++){
        if (!marks[i][i]) diag1 = false;
        if (!marks[i][size - 1 - i]) diag2 = false;
      }
      if (diag1 || diag2) return true;
    }
    return false;
  }

  function shortenCardId(cardId){
    const raw = String(cardId || "");
    if (!raw) return "-";
    if (raw.length <= 8) return raw;
    return `${raw.slice(0, 4)}...${raw.slice(-4)}`;
  }

  async function fetchOwnerCards(){
    if (token){
      const r = await fetch(`/bingo/owner-token/${encodeURIComponent(token)}`);
      return r.ok ? await r.json() : null;
    }
    const r = await fetch(`/bingo/${encodeURIComponent(game)}/owner/${encodeURIComponent(owner)}/cards`);
    return r.ok ? await r.json() : null;
  }

  async function fetchState(){
    if (token){
      return null;
    }
    const r = await fetch(`/bingo/${encodeURIComponent(game)}`);
    return r.ok ? await r.json() : null;
  }

  function render(data, state){
    if(!data || !state){
      grid.innerHTML = '<p>Missing or invalid query parameters.</p>';
      if (contextMeta) contextMeta.textContent = "Missing game data.";
      if (contextStatus) contextStatus.textContent = "No game loaded.";
      return;
    }
    const cards = data.cards || [];
    const g = state.game || {};
    const called = Array.isArray(g.called) ? g.called : [];
    const bg = g.background ? new URL(g.background, location.origin).toString() : "";
    document.body.style.backgroundImage = bg ? `url('${bg}')` : "";
    applyTheme(g.theme_color || null);
    owner = data.owner || owner;
    resolvedGame = (g.game_id || resolvedGame);
    const title = g.title || "Bingo";
    const cardCount = cards.length;
    if (contextPath) contextPath.textContent = `My Cards / ${title}`;
    if (contextMeta) contextMeta.textContent = `Viewing cards for ${owner || "-"} (${cardCount} card(s))`;
    summary.textContent = `Loaded ${cardCount} card(s) for ${owner || "-"}.`;
    potValue.textContent = `${formatGil(g.pot != null ? g.pot : 0)} ${g.currency || ""}`.trim();
    payoutSingle.textContent = g.payouts && g.payouts.single != null ? `${formatGil(g.payouts.single)} ${g.currency || ""}`.trim() : "-";
    payoutDouble.textContent = g.payouts && g.payouts.double != null ? `${formatGil(g.payouts.double)} ${g.currency || ""}`.trim() : "-";
    payoutFull.textContent = g.payouts && g.payouts.full != null ? `${formatGil(g.payouts.full)} ${g.currency || ""}`.trim() : "-";
    stageValue.textContent = g.stage || "-";
    headerValue.textContent = g.header_text || g.header || "BING";
    if (!selectedCardId && cards.length){
      selectedCardId = cards[0].card_id;
    }
    const gameActive = g.active !== false;
    if (contextStatus) contextStatus.textContent = gameActive ? "Game running." : "Game closed.";
    if (!gameActive){
      if (!redirected){
        redirected = true;
        setTimeout(() => {
          window.location.assign("/");
        }, 1500);
      }
    }
    const claims = Array.isArray(g.claims) ? g.claims : [];
    const hasPending = claims.some(c => c.pending);
    const ownerClaims = claims.filter(c => (c.owner_name || "") === owner);
    const deniedClaim = ownerClaims.find(c => !c.pending && c.denied);
    const deniedMessage = deniedClaim ? "Claim denied." : "";
    if (deniedMessage){
      claimMsg.textContent = deniedMessage;
      localBingoPressed = false;
    } else if (!hasPending){
      localBingoPressed = false;
    }
    bingoOverlay.classList.toggle("show", hasPending || localBingoPressed);
    calledEl.textContent = called.length ? called.join(", ") : "No numbers called yet.";
    const lastCalled = g.last_called || (called.length ? called[called.length - 1] : null);
    if (lastCalled && lastCalled !== lastBallNumber){
      showCallBall(lastCalled);
      lastBallNumber = lastCalled;
    }
    grid.innerHTML = '';
    if (!cards.length){
      grid.innerHTML = '<p class="muted">No cards loaded.</p>';
      return;
    }
    const header = (g.header || "BING").slice(0,4).split("");
    while(header.length < 4) header.push(" ");
    const calledSet = new Set(called);
    let selectedWin = false;
    cards.forEach((card, index)=>{
      const el = document.createElement('div');
      el.className = 'card';
      const localMarks = loadLocalMarks(card.card_id);
      const displayMarks = buildDisplayMarks(card, calledSet, localMarks, autoDabEl.checked);
      const win = hasWinningLine(buildMarksForCard(card, calledSet));
      if (win) el.classList.add('card-winning');
      if (card.card_id === selectedCardId){
        el.classList.add('selected');
        selectedWin = win;
      }
      const cardHeader = document.createElement('div');
      cardHeader.className = 'card-header';
      const title = document.createElement('div');
      title.className = 'card-id';
      title.textContent = `Card ${index + 1}`;
      const meta = document.createElement('div');
      meta.className = 'card-meta';
      const cardIdLabel = shortenCardId(card.card_id);
      meta.textContent = `ID ${cardIdLabel}`;
      if (card.card_id === selectedCardId){
        meta.textContent += " | Selected";
      }
      cardHeader.appendChild(title);
      cardHeader.appendChild(meta);
      el.appendChild(cardHeader);
      const body = document.createElement('div');
      body.className = 'card-body';
      const headerRow = document.createElement('div');
      headerRow.className = 'header';
      header.forEach(h=>{
        const d = document.createElement('div');
        d.textContent = h;
        headerRow.appendChild(d);
      });
      body.appendChild(headerRow);
      const gridEl = document.createElement('div');
      gridEl.className = 'bingo-grid';
      const nums = card.numbers || [];
      for(let r=0;r<nums.length;r++){
        for(let c=0;c<nums[r].length;c++){
          const n = nums[r][c];
          const cell = document.createElement('div');
          cell.className = 'cell';
          const isCalled = calledSet.has(n);
          const isCalledDisplay = autoDabEl.checked && isCalled;
          const isMarked = displayMarks[r] && displayMarks[r][c];
          const isLocal = localMarks[r] && localMarks[r][c];
          if (isMarked) cell.classList.add('marked');
          if (isCalledDisplay) cell.classList.add('called');
          if (lastCalled && lastCalled === n) cell.classList.add('recent');
          cell.textContent = n;
          if (isCalledDisplay){
            const mark = document.createElement('span');
            mark.className = 'cell-mark';
            mark.textContent = 'v';
            cell.appendChild(mark);
          } else if (isLocal){
            const dot = document.createElement('span');
            dot.className = 'cell-dot';
            dot.textContent = 'o';
            cell.appendChild(dot);
          }
          cell.onclick = (ev) => {
            ev.stopPropagation();
            localMarks[r] = localMarks[r] || [];
            localMarks[r][c] = !localMarks[r][c];
            saveLocalMarks(card.card_id, localMarks);
            render(data, state);
          };
          gridEl.appendChild(cell);
        }
      }
      body.appendChild(gridEl);
      el.appendChild(body);
      el.onclick = () => {
        selectedCardId = card.card_id;
        claimMsg.textContent = "";
        render(data, state);
      };
      grid.appendChild(el);
    });
    const claimReady = gameActive && selectedCardId && selectedWin;
    claimBtn.disabled = !claimReady;
    if (deniedMessage){
      claimMsg.textContent = deniedMessage;
    } else if (!gameActive){
      claimMsg.textContent = "Game ended.";
    } else if (!selectedCardId){
      claimMsg.textContent = "Select a card to claim.";
    } else if (!selectedWin){
      claimMsg.textContent = "No winning line yet.";
    } else {
      claimMsg.textContent = "";
    }
  }

  claimBtn.addEventListener('click', async () => {
    if (!selectedCardId){
      const data = await fetchOwnerCards();
      if (data && Array.isArray(data.cards) && data.cards.length){
        selectedCardId = data.cards[0].card_id;
      }else{
        return;
      }
    }
    try{
      const r = await fetch('/bingo/claim-public', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({game_id: resolvedGame, card_id: selectedCardId, owner_name: owner})
      });
      const j = await r.json();
      claimMsg.textContent = j.message || (j.ok ? 'Claim sent.' : 'Claim failed.');
      localBingoPressed = true;
      bingoOverlay.classList.add("show");
    }catch(e){
      claimMsg.textContent = 'Claim failed.';
    }
  });

  autoDabEl.addEventListener('change', async () => {
    const [data, state] = await Promise.all([fetchOwnerCards(), fetchState()]);
    if (token && data && data.game){
      render(data, {game: data.game});
    }else{
      render(data, state);
    }
  });

  function applyTheme(color){
    if (!color) return;
    const root = document.documentElement;
    const hex = color.startsWith("#") ? color.slice(1) : color;
    if (hex.length !== 6) return;
    const r = parseInt(hex.slice(0,2), 16);
    const g = parseInt(hex.slice(2,4), 16);
    const b = parseInt(hex.slice(4,6), 16);
    const mix = (c, t, p) => Math.round(c + (t - c) * p);
    const toHex = (v) => v.toString(16).padStart(2, "0");
    const dark = `#${toHex(mix(r, 0, 0.6))}${toHex(mix(g, 0, 0.6))}${toHex(mix(b, 0, 0.6))}`;
    const darker = `#${toHex(mix(r, 0, 0.8))}${toHex(mix(g, 0, 0.8))}${toHex(mix(b, 0, 0.8))}`;
    const light = `#${toHex(mix(r, 255, 0.35))}${toHex(mix(g, 255, 0.35))}${toHex(mix(b, 255, 0.35))}`;
    root.style.setProperty("--accent", light);
    root.style.setProperty("--accent-2", `#${hex}`);
    root.style.setProperty("--line", dark);
    root.style.setProperty("--panel", darker);
  }
  async function tick(){
    const [data, state] = await Promise.all([fetchOwnerCards(), fetchState()]);
    if (token && data && data.game){
      render(data, {game: data.game});
    }else{
      render(data, state);
    }
  }
  setInterval(tick, 2000);
  tick();

  function formatGil(value){
    const raw = Number(value);
    if (!Number.isFinite(raw)) return String(value ?? "");
    return raw.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function showCallBall(number){
    if (!callBall) return;
    callBall.textContent = number;
    callBall.classList.remove("show");
    void callBall.offsetWidth;
    callBall.classList.add("show");
    if (callBallTimer){
      clearTimeout(callBallTimer);
    }
    callBallTimer = setTimeout(() => {
      callBall.classList.remove("show");
    }, 2100);
  }
});
