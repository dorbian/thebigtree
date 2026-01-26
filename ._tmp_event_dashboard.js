
    const EVENT_CODE = "{event_code}";
    
    const TOKEN_KEY = "bigtree_user_token";
    function getToken() {
      try { return window.localStorage.getItem(TOKEN_KEY); } catch(e) { return null; }
    }
    
    function authHeaders() {
      const token = getToken();
      if (!token) return {};
      return {"Authorization": `Bearer ${token}`};
    }
    
    async function jsonFetch(url, opts) {
      const res = await fetch(url, {
        credentials: "include",
        headers: {"Content-Type": "application/json", ...authHeaders()},
        ...opts,
      });
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch(e) { data = {ok: false, error: text || res.statusText}; }
      if (!res.ok && data && data.ok === undefined) data.ok = false;
      return data;
    }
    
    function showError(message) {
      const container = document.getElementById('errorContainer');
      container.innerHTML = `<div class="error">${message}</div>`;
    }
    
    function clearError() {
      document.getElementById('errorContainer').innerHTML = '';
    }
    
    async function loadDashboard() {
      try {
        clearError();
        
        // Load event info
        const eventData = await jsonFetch(`/api/events/${encodeURIComponent(EVENT_CODE)}`, {method: "GET"});
        if (!eventData.ok) throw new Error(eventData.error || "Unable to load event");
        
        const event = eventData.event || {};
        document.getElementById('dashboardTitle').textContent = `Dashboard: ${event.title || EVENT_CODE}`;
        
        const meta = [];
        if (event.venue_name) meta.push(`Venue: ${event.venue_name}`);
        if (event.currency_name) meta.push(`Currency: ${event.currency_name}`);
        meta.push(`Status: ${event.status || "active"}`);
        document.getElementById('dashboardMeta').textContent = meta.join(" · ");
        
        // Load statistics
        const statsData = await jsonFetch(`/api/events/${encodeURIComponent(EVENT_CODE)}/dashboard/stats`, {method: "GET"});
        if (!statsData.ok) throw new Error(statsData.error || "Unable to load statistics");
        
        const stats = statsData.stats || {};
        document.getElementById('playersCount').textContent = stats.players_count || 0;
        document.getElementById('gamesCount').textContent = stats.games_count || 0;
        
      } catch(err) {
        showError(err.message || "Unable to load dashboard");
      }
    }
    
    async function showPlayersModal() {
      try {
        document.getElementById('modalTitle').textContent = 'Registered Players';
        document.getElementById('modalBody').innerHTML = '<div class="loading">Loading players...</div>';
        document.getElementById('modal').classList.add('active');
        
        const data = await jsonFetch(`/api/events/${encodeURIComponent(EVENT_CODE)}/dashboard/players`, {method: "GET"});
        if (!data.ok) throw new Error(data.error || "Unable to load players");
        
        const players = data.players || [];
        
        if (players.length === 0) {
          document.getElementById('modalBody').innerHTML = '<div class="empty-state">No players registered yet</div>';
          return;
        }
        
        let html = '<div class="modal-section"><h3>Player List</h3><div class="detail-grid">';
        for (const player of players) {
          const joinedDate = player.joined_at ? new Date(player.joined_at).toLocaleString() : 'Unknown';
          html += `
            <div class="list-item">
              <div class="list-item-title">${player.name || 'Player #' + player.user_id}</div>
              <div class="list-item-meta">Joined: ${joinedDate} · Role: ${player.role || 'player'}</div>
            </div>
          `;
        }
        html += '</div></div>';
        
        document.getElementById('modalBody').innerHTML = html;
        
      } catch(err) {
        document.getElementById('modalBody').innerHTML = `<div class="error">${err.message || "Unable to load players"}</div>`;
      }
    }
    
    async function showGamesModal() {
      try {
        document.getElementById('modalTitle').textContent = 'Active Games';
        document.getElementById('modalBody').innerHTML = '<div class="loading">Loading games...</div>';
        document.getElementById('modal').classList.add('active');
        
        const data = await jsonFetch(`/api/events/${encodeURIComponent(EVENT_CODE)}/dashboard/games`, {method: "GET"});
        if (!data.ok) throw new Error(data.error || "Unable to load games");
        
        const games = data.games || [];
        
        if (games.length === 0) {
          document.getElementById('modalBody').innerHTML = '<div class="empty-state">No active games yet</div>';
          return;
        }
        
        let html = '<div class="modal-section"><h3>Game List</h3><div class="detail-grid">';
        for (const game of games) {
          const createdDate = game.created_at ? new Date(game.created_at).toLocaleString() : 'Unknown';
          html += `
            <div class="list-item">
              <div class="list-item-title">${game.title || game.game_id || 'Game'}</div>
              <div class="list-item-meta">Type: ${game.game_id || 'N/A'} · Status: ${game.status || 'active'} · Created: ${createdDate}</div>
            </div>
          `;
        }
        html += '</div></div>';
        
        document.getElementById('modalBody').innerHTML = html;
        
      } catch(err) {
        document.getElementById('modalBody').innerHTML = `<div class="error">${err.message || "Unable to load games"}</div>`;
      }
    }
    
    // Event listeners
    document.getElementById('playersKPI').addEventListener('click', showPlayersModal);
    document.getElementById('gamesKPI').addEventListener('click', showGamesModal);
    
    document.getElementById('modalClose').addEventListener('click', () => {
      document.getElementById('modal').classList.remove('active');
    });
    
    document.getElementById('modal').addEventListener('click', (e) => {
      if (e.target === document.getElementById('modal')) {
        document.getElementById('modal').classList.remove('active');
      }
    });
    
    // Load initial data
    loadDashboard();
    
    // Auto-refresh every 10 seconds
    setInterval(loadDashboard, 10000);
  