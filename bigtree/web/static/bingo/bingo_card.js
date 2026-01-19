document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(location.search);
  const game = params.get('game') || '';
  const cardId = params.get('card') || '';

  const app = document.getElementById('app');

  async function fetchCard(){
    const r = await fetch(`/bingo/${encodeURIComponent(game)}/card/${encodeURIComponent(cardId)}`);
    return r.ok ? (await r.json()).card : null;
  }
  async function fetchState(){
    const r = await fetch(`/bingo/${encodeURIComponent(game)}`);
    return r.ok ? await r.json() : null;
  }

  function marksKey(){
    return `bingo_marks_${game}_${cardId}`;
  }

  function loadLocalMarks(){
    try{
      const raw = localStorage.getItem(marksKey());
      return raw ? JSON.parse(raw) : [];
    }catch(e){ return []; }
  }

  function saveLocalMarks(marks){
    try{
      localStorage.setItem(marksKey(), JSON.stringify(marks));
    }catch(e){}
  }

  function render(card, state){
    if(!card || !state){ app.innerHTML = '<p>Missing or invalid game/card parameters.</p>'; return; }
    const called = (state.game && state.game.called) || [];
    const bg = state.game && state.game.background ? new URL(state.game.background, location.origin).toString() : "";
    document.body.style.backgroundImage = bg
      ? `linear-gradient(160deg, rgba(11,22,17,.95), rgba(11,22,17,.7)), url('${bg}')`
      : "";
    applyTheme(state.game && state.game.theme_color ? state.game.theme_color : null);
    const header = (state.game && (state.game.header_text || state.game.header)) || "BING";
    const nums = card.numbers || [];
    const localMarks = loadLocalMarks();
    let html = `<div><strong>Owner:</strong> ${card.owner_name || ''}</div>`;
    html += `<div class="called">${called.length ? ("Called numbers: " + called.join(", ")) : "Called numbers: -"}</div>`;
    html += `<div style="margin:8px 0"><button id="claimBtn">I have BINGO!</button><span id="claimMsg" class="muted" style="margin-left:8px"></span></div>`;
    html += '<div class="bingo-grid">';
    for(let r=0;r<nums.length;r++){
      for(let c=0;c<nums[r].length;c++){
        const n = nums[r][c];
        const marked = (localMarks[r] && localMarks[r][c]) || called.includes(n);
        html += `<div class="cell ${marked?'marked':''}" data-r="${r}" data-c="${c}">${n}</div>`;
      }
    }
    html += '</div>';
    app.innerHTML = html;
    const claimBtn = document.getElementById('claimBtn');
    const claimMsg = document.getElementById('claimMsg');
    claimBtn.addEventListener('click', async () => {
      try{
        const r = await fetch('/bingo/claim-public', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({game_id: game, card_id: cardId, owner_name: card.owner_name || ''})
        });
        const j = await r.json();
        claimMsg.textContent = j.message || (j.ok ? 'Claim sent.' : 'Claim failed.');
      }catch(e){
        claimMsg.textContent = 'Claim failed.';
      }
    });
    app.querySelectorAll('.cell').forEach(el=>{
      el.addEventListener('click', () => {
        const r = Number(el.dataset.r);
        const c = Number(el.dataset.c);
        localMarks[r] = localMarks[r] || [];
        localMarks[r][c] = !localMarks[r][c];
        saveLocalMarks(localMarks);
        render(card, state);
      });
    });
  }

  async function tick(){
    const [card, state] = await Promise.all([fetchCard(), fetchState()]);
    render(card, state);
  }
  setInterval(tick, 1500);
  tick();

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
});
