document.addEventListener("DOMContentLoaded", () => {
  const TOKEN_KEY = "bigtree_user_token";
  const loginLink = document.getElementById("loginLink");
  const logoutBtn = document.getElementById("logoutBtn");
  const userName = document.getElementById("userName");
  const gamesContainer = document.getElementById("gamesContainer");
  const activeEventsContainer = document.getElementById("activeEventsContainer");
  const activeGamesContainer = document.getElementById("activeGamesContainer");
  const pastEventsContainer = document.getElementById("pastEventsContainer");
  const pastGamesContainer = document.getElementById("pastGamesContainer");
  const headerClaim = document.getElementById("headerClaim");
  const claimJoinCode = document.getElementById("claimJoinCode");
  const claimJoinBtn = document.getElementById("claimJoinBtn");
  const claimMessage = document.getElementById("claimMessage");
  const gameDetailModal = document.getElementById("gameDetailModal");
  const gameDetailBody = document.getElementById("gameDetailBody");
  const gameDetailTitle = document.getElementById("gameDetailTitle");
  const gameDetailClose = document.getElementById("gameDetailClose");
  const eventDetailModal = document.getElementById("eventDetailModal");
  const eventDetailTitle = document.getElementById("eventDetailTitle");
  const eventDetailBody = document.getElementById("eventDetailBody");
  const eventDetailClose = document.getElementById("eventDetailClose");
  let gameLookup = {};
  let eventLookup = {};

  function escapeHtml(value){
    const text = value === undefined || value === null ? "" : String(value);
    return text.replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
  }

  function setMessage(target, text, tone="muted"){
    if(!target) return;
    target.textContent = text || "";
    target.className = tone;
  }

  function getToken(){
    return window.localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token){
    if(token){
      window.localStorage.setItem(TOKEN_KEY, token);
    }else{
      window.localStorage.removeItem(TOKEN_KEY);
    }
  }

  function authHeaders(){
    const token = getToken();
    if(!token) return {};
    return {"Authorization": `Bearer ${token}`};
  }

  let currentUserName = "";
  function setUserHeader(user){
    if(user && user.xiv_username){
      currentUserName = user.xiv_username;
      userName.textContent = user.xiv_username;
      userName.style.display = "inline-flex";
      loginLink.style.display = "none";
      logoutBtn.style.display = "inline-flex";
      headerClaim.style.display = "flex";
    }else{
      currentUserName = "";
      userName.textContent = "";
      userName.style.display = "none";
      loginLink.style.display = "inline-flex";
      logoutBtn.style.display = "none";
      headerClaim.style.display = "none";
    }
  }

  function applyTokenFromUrl(){
    const params = new URLSearchParams(window.location.search);
    const token = params.get("user_token");
    if(!token){
      return false;
    }
    setToken(token);
    const url = new URL(window.location.href);
    url.searchParams.delete("user_token");
    window.history.replaceState({}, "", url.toString());
    return true;
  }

  async function loadCurrentUser(){
    const token = getToken();
    if(!token){
      setUserHeader(null);
      return false;
    }
    try{
      const res = await fetch("/user-area/me", {headers: authHeaders()});
      const data = await res.json();
      if(!res.ok || !data.ok){
        throw new Error(data.error || "Invalid session");
      }
      setUserHeader(data.user);
      return true;
    }catch(err){
      setToken("");
      setUserHeader(null);
      return false;
    }
  }

  async function fetchGames(){
    const token = getToken();
    if(!token){
      if (activeGamesContainer) activeGamesContainer.textContent = "Login to view your game history.";
      if (pastGamesContainer) pastGamesContainer.textContent = "";
      return;
    }
    try{
      const res = await fetch("/user-area/games?all=1", {headers: authHeaders()});
      const data = await res.json();
      if(!res.ok || !data.ok){
        throw new Error(data.error || "Failed to load games");
      }
      const games = data.games || [];
      const activeGames = games.filter(g => !!g.active);
      const pastGames = games.filter(g => !g.active);
      renderGames(activeGames, activeGamesContainer);
      renderGames(pastGames, pastGamesContainer, {emptyText: "No past games found yet."});
    }catch(err){
      if (activeGamesContainer) activeGamesContainer.textContent = err.message || "Unable to load games.";
      if (pastGamesContainer) pastGamesContainer.textContent = "";
    }
  }

  function renderGames(games, target, opts){
    const options = opts || {};
    gameLookup = {};
    if(!target) return;
    if(!games || !games.length){
      target.innerHTML = `<div class='muted'>${escapeHtml(options.emptyText || "No games found yet.")}</div>`;
      return;
    }
    games.forEach((game) => {
      if(game && game.game_id){
        gameLookup[game.game_id] = game;
      }
    });
    target.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Game</th>
            <th>Type</th>
            <th>Status</th>
            <th>Paid</th>
            <th>Outcome</th>
            <th>Player page</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          ${games.map(renderGameRow).join("")}
        </tbody>
      </table>
    `;
  }

  function buildPlayerUrl(game){
    if(!game){
      return "";
    }
    const moduleId = game.module || "game";
    if(moduleId === "cardgames"){
      if(!game.join_code) return "";
      const payload = game.payload || {};
      const gameId = payload.game_id || payload.gameId;
      if(!gameId){
        return "";
      }
      return `/cardgames/${encodeURIComponent(gameId)}/session/${encodeURIComponent(game.join_code)}`;
    }
    if(moduleId === "tarot"){
      if(!game.join_code) return "";
      return `/tarot/session/${encodeURIComponent(game.join_code)}`;
    }
    if(moduleId === "bingo"){
      // Prefer owner token (join_code) unless it matches the game id.
      const gid = game.game_id ? String(game.game_id) : "";
      const joinCode = game.join_code ? String(game.join_code) : "";
      const joinIsGame = joinCode && gid && joinCode === gid;
      if(joinCode && !joinIsGame){
        return `/bingo/owner?token=${encodeURIComponent(joinCode)}`;
      }
      let owner = game.claimed_username ? String(game.claimed_username) : (currentUserName || "");
      if (!owner && Array.isArray(game.players)){
        const match = game.players.find(p => {
          const role = String((p || {}).role || "").toLowerCase();
          return role === "owner" || role === "host" || role === "dealer" || role === "caller";
        });
        if (match && match.name){
          owner = String(match.name);
        }
      }
      if(gid && owner){
        return `/bingo/owner?game=${encodeURIComponent(gid)}&owner=${encodeURIComponent(owner)}`;
      }
      return "";
    }
    return "";
  }

  function formatGameType(game){
    const moduleId = (game.module || "").toLowerCase();
    if (moduleId === "cardgames"){
      const payload = game.payload || {};
      const raw = payload.game_id || payload.gameId || "";
      return raw ? String(raw) : "Cardgame";
    }
    if (moduleId === "bingo") return "Bingo";
    if (moduleId === "tarot") return "Tarot";
    return moduleId ? moduleId : "Game";
  }

  function getGameTitle(game){
    const title = game.title || game.name;
    if (title) return String(title);
    return formatGameType(game);
  }

  function getGamePaid(game){
    const meta = game.metadata || {};
    const paid = game.pot ?? meta.price;
    if (paid === undefined || paid === null || paid === ""){
      return "-";
    }
    const currency = game.currency || "";
    return currency ? `${paid} ${currency}` : String(paid);
  }

  function formatDateOnly(value){
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleDateString();
  }

  function renderGameRow(game){
    const title = getGameTitle(game);
    const status = game.active ? "active" : "ended";
    const outcome = game.active ? "-" : (game.outcome || status);
    const playerUrl = buildPlayerUrl(game);
    const playerLink = playerUrl ? `<a href="${escapeHtml(playerUrl)}" target="_blank" rel="noreferrer">Open</a>` : "-";
    return `
      <tr class="game-row" data-game-id="${escapeHtml(game.game_id)}">
        <td>${escapeHtml(title)}</td>
        <td>${escapeHtml(formatGameType(game))}</td>
        <td><span class="status-chip">${escapeHtml(status)}</span></td>
        <td>${escapeHtml(getGamePaid(game))}</td>
        <td>${escapeHtml(outcome)}</td>
        <td>${playerLink}</td>
        <td>${escapeHtml(formatDateOnly(game.created_at))}</td>
      </tr>
    `;
  }

  function openGameModal(game){
    if(!game){
      return;
    }
    gameDetailTitle.textContent = getGameTitle(game);
    const status = game.active ? "active" : "ended";
    const playerUrl = buildPlayerUrl(game);
    const details = [
      {label: "Title", value: getGameTitle(game)},
      {label: "Type", value: formatGameType(game)},
      {label: "Status", value: status},
      {label: "Outcome", value: game.active ? "-" : (game.outcome || status)},
      {label: "Paid", value: getGamePaid(game)},
      {label: "Winnings", value: game.winnings || "-"},
      {label: "Join key", value: game.join_code || "-"},
      {label: "Player page", value: playerUrl || "-", link: playerUrl || ""},
      {label: "Created", value: formatDateOnly(game.created_at)},
      {label: "Ended", value: game.ended_at || "-"},
    ];
    gameDetailBody.innerHTML = `
      <div class="detail-grid">
        ${details.map(detail => `
          <div class="detail-item">
            <span>${escapeHtml(detail.label)}</span>
            ${detail.link ? `<a href="${escapeHtml(detail.link)}" target="_blank" rel="noreferrer">${escapeHtml(detail.value)}</a>` : escapeHtml(detail.value)}
          </div>
        `).join("")}
      </div>
    `;
    gameDetailModal.classList.add("open");
  }

  function closeGameModal(){
    gameDetailModal.classList.remove("open");
  }

  async function fetchEvents(){
    const token = getToken();
    if(!token){
      if (activeEventsContainer) activeEventsContainer.textContent = "Login to view your events.";
      if (pastEventsContainer) pastEventsContainer.textContent = "";
      return;
    }
    try{
      const res = await fetch("/user-area/events?all=1", {headers: authHeaders()});
      const data = await res.json();
      if(!res.ok || !data.ok){
        throw new Error(data.error || "Failed to load events");
      }
      const events = data.events || [];
      const activeEvents = events.filter(ev => (ev.status || "") === "active");
      const pastEvents = events.filter(ev => (ev.status || "") !== "active");
      renderEvents(activeEvents, activeEventsContainer, {emptyText: "No active events right now."});
      renderEvents(pastEvents, pastEventsContainer, {emptyText: "No past events found yet."});
    }catch(err){
      if (activeEventsContainer) activeEventsContainer.textContent = err.message || "Unable to load events.";
      if (pastEventsContainer) pastEventsContainer.textContent = "";
    }
  }

  function renderEvents(events, target, opts){
    const options = opts || {};
    eventLookup = {};
    if (!target) return;
    if(!events || !events.length){
      target.innerHTML = `<div class='muted'>${escapeHtml(options.emptyText || "No events found yet.")}</div>`;
      return;
    }
    events.forEach((ev) => {
      if (ev && ev.event_code){
        eventLookup[ev.event_code] = ev;
      }
    });
    target.innerHTML = `
      <table>
        <thead>
          <tr>
            <th>Event</th>
            <th>Status</th>
            <th>Venue</th>
            <th>Wallet</th>
            <th>Games</th>
          </tr>
        </thead>
        <tbody>
          ${events.map(renderEventRow).join("")}
        </tbody>
      </table>
    `;
  }

  function renderEventRow(ev){
    const code = ev.event_code || "";
    const title = ev.title || code || "Event";
    const status = ev.status || "-";
    const venue = ev.venue_name || "-";
    const currency = ev.currency_name || "-";
    const walletAmount = ev.wallet_enabled ? `${ev.wallet_balance ?? 0}` : "-";
    const wallet = (walletAmount !== "-" && currency !== "-") ? `${walletAmount} ${currency}` : walletAmount;
    const gamesCount = ev.games_count ?? 0;
    const eventLink = status === "active" && code
      ? `<div style="margin-top:6px;"><a href="/events/${encodeURIComponent(code)}" target="_blank" rel="noreferrer">Open event</a></div>`
      : "";
    return `
      <tr class="event-row" data-event-code="${escapeHtml(code)}">
        <td>${escapeHtml(title)}<div class="muted" style="font-size:12px;"><code>${escapeHtml(code)}</code></div>${eventLink}</td>
        <td><span class="status-chip">${escapeHtml(status)}</span></td>
        <td>${escapeHtml(venue)}</td>
        <td>${escapeHtml(wallet)}</td>
        <td>${escapeHtml(currency)}</td>
        <td>${escapeHtml(String(gamesCount))}</td>
      </tr>
    `;
  }

  async function openEventModalByCode(code){
    if (!code) return;
    eventDetailTitle.textContent = "Event details";
    eventDetailBody.innerHTML = "<div class='muted'>Loading...</div>";
    eventDetailModal.classList.add("open");
    try{
      const res = await fetch(`/user-area/events/${encodeURIComponent(code)}`, {headers: authHeaders()});
      const data = await res.json();
      if (!res.ok || !data.ok){
        throw new Error(data.error || "Unable to load event");
      }
      const ev = data.event || {};
      const games = data.games || [];
      const walletEnabled = !!ev.wallet_enabled;
      const walletBalance = data.wallet_balance ?? null;
      const walletUsable = !!data.wallet_usable;
      const walletHistory = Array.isArray(data.wallet_history) ? data.wallet_history : [];
      const status = ev.status || "-";
      const currency = ev.currency_name || "-";
      const venue = ev.venue_name || "-";
      const usableText = walletEnabled ? (walletUsable ? "usable in new events" : "not usable in new events") : "-";
      const historyRows = walletHistory.length ? `
        <table style="margin-top:12px;">
          <thead><tr><th>Time</th><th>Change</th><th>Balance</th><th>Reason</th></tr></thead>
          <tbody>
            ${walletHistory.map(h => {
              const delta = Number(h.delta ?? 0);
              const sign = delta > 0 ? "+" : "";
              const reason = String(h.reason || "update");
              const meta = h.metadata || {};
              const gameTag = meta.game_id ? ` (${escapeHtml(String(meta.game_id))})` : "";
              const hostTag = meta.host_name ? ` Aú ${escapeHtml(String(meta.host_name))}` : "";
              const commentTag = meta.comment ? ` Aú ${escapeHtml(String(meta.comment))}` : "";
              return `
                <tr>
                  <td>${escapeHtml(String(h.created_at || ""))}</td>
                  <td>${escapeHtml(`${sign}${delta}`)}</td>
                  <td>${escapeHtml(String(h.balance ?? 0))}</td>
                  <td>${escapeHtml(reason)}${gameTag}${hostTag}${commentTag}</td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      ` : "<div class='muted' style='margin-top:12px;'>No wallet activity yet.</div>";
      const gameRows = games.length ? `
        <table style="margin-top:12px;">
          <thead><tr><th>Game</th><th>Type</th><th>Status</th><th>Outcome</th><th>Join key</th></tr></thead>
          <tbody>
            ${games.map(g => `
              <tr class="game-row" data-game-id="${escapeHtml(g.game_id || "")}">
                <td>${escapeHtml(g.title || g.game_id || "Game")}</td>
                <td>${escapeHtml(g.module || "-")}</td>
                <td>${escapeHtml(g.active ? "active" : "ended")}</td>
                <td>${escapeHtml(g.outcome || "-")}</td>
                <td><code>${escapeHtml(g.join_code || "-")}</code></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      ` : "<div class='muted' style='margin-top:12px;'>No games recorded for this event yet.</div>";

      eventDetailTitle.textContent = ev.title || ev.event_code || "Event details";
      eventDetailBody.innerHTML = `
        <div class="detail-grid">
          <div class="detail-item"><span>Event code</span>${escapeHtml(ev.event_code || "-")}</div>
          <div class="detail-item"><span>Status</span>${escapeHtml(status)}</div>
          <div class="detail-item"><span>Venue</span>${escapeHtml(venue)}</div>
          <div class="detail-item"><span>Currency</span>${escapeHtml(currency)}</div>
          <div class="detail-item"><span>Wallet enabled</span>${walletEnabled ? "Yes" : "No"}</div>
          <div class="detail-item"><span>Wallet balance</span>${walletEnabled ? escapeHtml(String(walletBalance ?? 0)) : "-"}</div>
          <div class="detail-item"><span>Wallet carry-over</span>${walletEnabled ? (data.carry_over ? "Yes" : "No") : "-"}</div>
          <div class="detail-item"><span>Usable later</span>${walletEnabled ? escapeHtml(usableText) : "-"}</div>
        </div>
        <div class="section-title" style="margin-top:16px;">Wallet history</div>
        ${walletEnabled ? historyRows : "<div class='muted' style='margin-top:12px;'>Wallet is disabled for this event.</div>"}
        ${gameRows}
      `;
    }catch(err){
      eventDetailBody.innerHTML = `<div class='status-error'>${escapeHtml(err.message || "Unable to load event.")}</div>`;
    }
  }

  function closeEventModal(){
    eventDetailModal.classList.remove("open");
  }

  async function claimByJoinCode(){
    const token = getToken();
    if(!token){
      setMessage(claimMessage, "Please login first.", "status-error");
      return;
    }
    const joinCode = claimJoinCode.value.trim();
    if(!joinCode){
      setMessage(claimMessage, "Enter a join key to claim.", "status-error");
      return;
    }
    setMessage(claimMessage, "Checking join key...", "muted");
    try{
      const res = await fetch("/user-area/claim-join", {
        method: "POST",
        headers: {"Content-Type":"application/json", ...authHeaders()},
        body: JSON.stringify({join_code: joinCode}),
      });
      const data = await res.json();
      if(!res.ok || !data.ok){
        if(res.status === 409 && data.game && data.game.claimed_username){
          throw new Error(`Already claimed by ${data.game.claimed_username}.`);
        }
        throw new Error(data.error || "Unable to claim join key.");
      }
      claimJoinCode.value = "";
      setMessage(claimMessage, "Game claimed. It will show in your list.", "status-ok");
      await fetchGames();
      await fetchEvents();
    }catch(err){
      setMessage(claimMessage, err.message || "Claim failed.", "status-error");
    }
  }

  function handleGamesTableClick(event){
    if (event.target && event.target.tagName === "A"){
      return;
    }
    const row = event.target.closest(".game-row");
    if(!row){
      return;
    }
    const gameId = row.getAttribute("data-game-id");
    const game = gameLookup[gameId];
    openGameModal(game);
  }

  if (activeGamesContainer) activeGamesContainer.addEventListener("click", handleGamesTableClick);
  if (pastGamesContainer) pastGamesContainer.addEventListener("click", handleGamesTableClick);

  function handleEventsTableClick(event){
    const row = event.target.closest(".event-row");
    if(!row) return;
    const code = row.getAttribute("data-event-code") || "";
    openEventModalByCode(code);
  }
  if (activeEventsContainer) activeEventsContainer.addEventListener("click", handleEventsTableClick);
  if (pastEventsContainer) pastEventsContainer.addEventListener("click", handleEventsTableClick);

  claimJoinBtn.addEventListener("click", claimByJoinCode);
  logoutBtn.addEventListener("click", () => {
    setToken("");
    setUserHeader(null);
    if (activeGamesContainer) activeGamesContainer.textContent = "Login to view your game history.";
    if (pastGamesContainer) pastGamesContainer.textContent = "";
    if (activeEventsContainer) activeEventsContainer.textContent = "Login to view your events.";
    if (pastEventsContainer) pastEventsContainer.textContent = "";
  });
  gameDetailClose.addEventListener("click", closeGameModal);
  gameDetailModal.addEventListener("click", (event) => {
    if(event.target === gameDetailModal){
      closeGameModal();
    }
  });
  if (eventDetailClose) eventDetailClose.addEventListener("click", closeEventModal);
  if (eventDetailModal){
    eventDetailModal.addEventListener("click", (event) => {
      if(event.target === eventDetailModal){
        closeEventModal();
      }
    });
  }

  applyTokenFromUrl();
  loadCurrentUser().then(() => Promise.all([fetchGames(), fetchEvents()]));
});
