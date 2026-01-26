const $ = (id) => document.getElementById(id);
      const statusEl = $("status");
      const loginStatusEl = $("loginStatus");
      const apiKeyEl = $("apiKeyLogin");
      const overlayToggle = $("overlayMode");
      const overlayToggleBtn = $("menuOverlayToggle");
      const storage = window.localStorage;
      const CONTEST_CATEGORY_ID = "1239558949351460904";
      const overlayLog = (...args) => {
        if (window.console && console.debug){
          console.debug("[overlay]", ...args);
        }
      };
      function on(id, event, handler){
        const el = $(id);
        if (!el){
          overlayLog("missing listener target", id, event);
          return false;
        }
        el.addEventListener(event, handler);
        return true;
      }
      let currentCard = null;
      let currentGame = null;
      let taSelectedCardId = "";
      let taTemplateCache = {tarot: null, playing: null};
      let taTemplatePurpose = "tarot";
      let lastCalledCount = 0;
      let lastCalloutNumber = null;
      let activeGameId = "";
      let currentOwner = "";
      window.taArtists = [];
      let calendarData = [];
      let authUserScopes = new Set();
      let previewScopesActive = false;
      let previewScopes = new Set();
      let authUserIsElfmin = false;
      let authTokensCache = [];
      let dashboardStatsLoaded = false;
      let dashboardStatsLoading = false;
      let dashboardLogsKind = "boot";
      let dashboardLogsLoading = false;
      let adminVenueId = null;
      let adminVenueName = "";
      let adminVenueDeckId = null;
      let adminVenueCurrency = null;
      let adminVenueGameBackgrounds = {};

      // Games list (admin:web)
      let gamesListVenues = [];
      let eventsVenues = [];
      let eventsCache = [];
      let gamesListState = {
        q: "",
        player: "",
        module: "",
        venue_id: "",
        include_inactive: true,
        page: 1,
        page_size: 50,
        total: 0,
      };
      let calendarSelected = {
        month: 1,
        image: "",
        title: "",
        artist_id: null,
        artist_name: "Forest"
      };
      let bingoCreateBgUrl = "";
      let authRoleIds = new Set();
      let authRoleScopes = {};
      let authRolesCache = [];
      const authScopeOptions = [
        {id: "*", label: "All access"},
        {id: "bingo:admin", label: "Bingo admin"},
        {id: "tarot:admin", label: "Tarot + cardgames admin"},
        {id: "cardgames:admin", label: "Cardgames admin"},
        {id: "tarot:control", label: "Tarot control"},
        {id: "admin:message", label: "Admin messages"},
        {id: "admin:announce", label: "Admin announce"},
        {id: "admin:web", label: "Admin web"},
        {id: "hunt:admin", label: "Hunt admin"}
      ];
      const SUIT_PRESETS = {
        forest: [
          {
            id: "Roots",
            name: "Roots",
            themes: {foundation: 3, memory: 2, stability: 3},
            keywords: ["home", "tradition", "endurance", "belonging"]
          },
          {
            id: "Canopy",
            name: "Canopy",
            themes: {growth: 3, connection: 3, hope: 2},
            keywords: ["healing", "community", "relationships", "renewal"]
          },
          {
            id: "Ember",
            name: "Ember",
            themes: {will: 3, conflict: 2, passion: 3},
            keywords: ["drive", "courage", "ambition", "trial"]
          },
          {
            id: "Whisper",
            name: "Whisper",
            themes: {secrets: 2, change: 3, curiosity: 3},
            keywords: ["insight", "illusion", "trickery", "exploration"]
          },
          {
            id: "Crown",
            name: "Crown of the Tree",
            themes: {fate: 3, cycles: 3, balance: 2},
            keywords: ["destiny", "turning point", "world forces"]
          }
        ],
        tarot: [
          {id: "Major", name: "Major", themes: {}, keywords: []},
          {id: "Wands", name: "Wands", themes: {}, keywords: []},
          {id: "Cups", name: "Cups", themes: {}, keywords: []},
          {id: "Swords", name: "Swords", themes: {}, keywords: []},
          {id: "Pentacles", name: "Pentacles", themes: {}, keywords: []}
        ],
        playing: [
          {id: "Hearts", name: "Hearts", themes: {}, keywords: []},
          {id: "Spades", name: "Spades", themes: {}, keywords: []},
          {id: "Clubs", name: "Clubs", themes: {}, keywords: []},
          {id: "Diamonds", name: "Diamonds", themes: {}, keywords: []}
        ]
      };

      function getBase(){
        // Use injected API_BASE_URL if available (dev mode with remote API)
        if (window.API_BASE_URL){
          return window.API_BASE_URL;
        }
        return window.location.origin;
      }

      let librarySelectHandler = null;
      let libraryKind = "";
      let libraryUploadFile = null;
      let mediaUploadFile = null;
      let mediaLibraryItems = [];
      let mediaVisibleItems = [];
      let mediaSelected = new Set();
      let mediaLastIndex = null;
      let deckEditHadSuits = false;
      let gallerySettingsCache = null;
      let galleryHiddenDecks = [];

      function setStatusText(id, msg, kind){
        const el = $(id);
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setStatValue(id, value){
        const el = $(id);
        if (!el) return;
        el.textContent = value === undefined || value === null ? "--" : String(value);
      }

      function renderDashboardStats(stats){
        overlayLog("renderDashboardStats", stats);
        if (!stats) return;
        setStatValue("dashStatDiscord", stats.discord_members ?? "--");
        setStatValue("dashStatPlayers", stats.players_engaged ?? "--");
        setStatValue("dashStatRegistered", stats.registered_users ?? "--");
        setStatValue("dashStatGames", stats.api_games ?? "--");
        setStatValue("dashStatVenues", stats.venues ?? "--");
        dashboardStatsLoaded = true;
      }

      async function loadDashboardStats(force = false){
        overlayLog("loadDashboardStats", {force, loading: dashboardStatsLoading, loaded: dashboardStatsLoaded});
        if (dashboardStatsLoading) return;
        if (dashboardStatsLoaded && !force){
          return;
        }
        if (!hasScope("admin:web")){
          overlayLog("loadDashboardStats skip: missing admin:web scope");
          setStatValue("dashStatDiscord", "--");
          setStatValue("dashStatPlayers", "--");
          setStatValue("dashStatRegistered", "--");
          setStatValue("dashStatGames", "--");
          setStatValue("dashStatVenues", "--");
          dashboardStatsLoaded = true;
          return;
        }
        dashboardStatsLoading = true;
        try{
          const resp = await jsonFetch("/admin/overlay/stats", {method: "GET"});
          overlayLog("loadDashboardStats response", resp);
          if (resp.ok){
            renderDashboardStats(resp.stats || {});
          }
        }catch(err){
          overlayLog("loadDashboardStats error", err);
          setStatValue("dashStatDiscord", "--");
          setStatValue("dashStatPlayers", "--");
          setStatValue("dashStatRegistered", "--");
          setStatValue("dashStatGames", "--");
          setStatValue("dashStatVenues", "--");
        }finally{
          dashboardStatsLoading = false;
        }
      }

      function setDashboardLogsActive(kind){
        const buttons = {
          boot: $("dashboardLogsBoot"),
          auth: $("dashboardLogsAuth"),
          upload: $("dashboardLogsUpload"),
        };
        Object.entries(buttons).forEach(([key, el]) => {
          if (!el) return;
          el.classList.toggle("active", key === kind);
        });
      }

      function renderDashboardLogs(lines, kind){
        const body = $("dashboardLogsBody");
        if (!body) return;
        // Show newest first so you don't have to scroll for the latest.
        const ordered = Array.isArray(lines) ? [...lines].reverse() : lines;
        const text = Array.isArray(ordered) ? ordered.join("\n") : String(ordered || "");
        body.textContent = text || "No log entries found.";
        body.scrollTop = 0;
        setDashboardLogsActive(kind);
      }

      async function loadDashboardLogs(kind = "boot", force = false){
        if (!hasScope("admin:web")) return;
        if (dashboardLogsLoading) return;
        if (!force && kind === dashboardLogsKind && $("dashboardLogsBody")?.textContent){
          setDashboardLogsActive(kind);
          return;
        }
        dashboardLogsLoading = true;
        const body = $("dashboardLogsBody");
        if (body){
          body.textContent = "Loading logs...";
        }
        try{
          const safeKind = ["boot", "auth", "upload"].includes(kind) ? kind : "boot";
          const resp = await jsonFetch(`/admin/logs?kind=${safeKind}&lines=200`, {method: "GET"});
          dashboardLogsKind = resp.kind || safeKind;
          const currentLabel = $("dashboardLogsCurrent");
          if (currentLabel){
            currentLabel.textContent = `Current: ${dashboardLogsKind}`;
          }
          renderDashboardLogs(resp.entries || [], dashboardLogsKind);
        }catch(err){
          if (body){
            body.textContent = err.message || "Unable to load logs.";
          }
        }finally{
          dashboardLogsLoading = false;
        }
      }

      function getGamesFilters(){
        return {
          q: $("gamesFilterQuery")?.value?.trim() || "",
          player: $("gamesFilterPlayer")?.value?.trim() || "",
          module: $("gamesFilterModule")?.value || "",
          venue_id: $("gamesFilterVenue")?.value || "",
          include_inactive: $("gamesFilterInactive")?.checked ?? true,
          page_size: parseInt($("gamesPageSize")?.value || "50", 10) || 50,
        };
      }

      function renderGamesListVenues(){
        const select = $("gamesFilterVenue");
        if (!select) return;
        const current = select.value || "";
        const options = [`<option value="">All venues</option>`]
          .concat((gamesListVenues || []).map(v => {
            const id = v.id ?? v.venue_id ?? "";
            const name = v.name || `Venue ${id}`;
            return `<option value="${String(id)}">${escapeHtml(name)}</option>`;
          }));
        select.innerHTML = options.join("");
        // Restore selection if still present
        if (current){
          select.value = current;
        }
      }

      async function loadGamesListVenues(force = false){
        if (!hasScope("admin:web")) return;
        if (gamesListVenues.length && !force){
          renderGamesListVenues();
          return;
        }
        try{
          const resp = await jsonFetch("/admin/venues", {method: "GET"});
          if (resp.ok){
            gamesListVenues = resp.venues || [];
          }
        }catch(err){
          gamesListVenues = [];
        }
        renderGamesListVenues();
      }

      // ---- Events panel ----

      function renderEventsVenues(){
        const select = $("eventsFilterVenue");
        const current = select ? (select.value || "") : "";
        const options = [`<option value="">All venues</option>`]
          .concat((eventsVenues || []).map(v => {
            const id = v.id ?? v.venue_id ?? "";
            const name = v.name || `Venue ${id}`;
            return `<option value="${String(id)}">${escapeHtml(name)}</option>`;
          }));
        if (select){
          select.innerHTML = options.join("");
          if (current) select.value = current;
        }
      }

      async function loadEventsVenues(force = false){
        if (!hasScope("admin:web") && !hasScope("event:host")) return;
        if (eventsVenues.length && !force){
          renderEventsVenues();
          return;
        }
        try{
          const resp = await jsonFetch("/admin/venues", {method: "GET"});
          if (resp.ok){
            eventsVenues = resp.venues || [];
          }
        }catch(err){
          eventsVenues = [];
        }
        renderEventsVenues();
      }

      function getEventsFilters(){
        return {
          q: $("eventsFilterQuery")?.value?.trim() || "",
          venue_id: $("eventsFilterVenue")?.value || "",
          include_ended: $("eventsFilterEnded")?.checked ?? true,
        };
      }

      function renderEventsList(){
        const body = $("eventsListBody");
        if (!body) return;
        const q = ($("eventsFilterQuery")?.value || "").trim().toLowerCase();
        let items = [...(eventsCache || [])];
        if (q){
          items = items.filter(e => String(e.event_code || "").toLowerCase().includes(q) || String(e.title || "").toLowerCase().includes(q));
        }
        const vid = $("eventsFilterVenue")?.value || "";
        if (vid){
          items = items.filter(e => String(e.venue_id || "") === String(vid));
        }
        const includeEnded = $("eventsFilterEnded")?.checked ?? true;
        if (!includeEnded){
          items = items.filter(e => (e.status || "") !== "ended");
        }

        if (!items.length){
          body.textContent = "No events found.";
          return;
        }

        const rows = items.map(e => {
          const code = escapeHtml(e.event_code || "-");
          const title = escapeHtml(e.title || "");
          const venue = escapeHtml(e.venue_name || "-");
          const status = escapeHtml(e.status || "active");
          const currency = escapeHtml(e.currency_name || "-");
          const wallet = e.wallet_enabled ? "Yes" : "No";
          const created = escapeHtml(e.created_at || "-");
          return `<tr class="venue-row" data-event-code="${escapeHtml(e.event_code || "")}">
            <td><code>${code}</code></td>
            <td>${title}</td>
            <td>${venue}</td>
            <td>${status}</td>
            <td>${currency}</td>
            <td>${wallet}</td>
            <td>${created}</td>
          </tr>`;
        }).join("");

        body.innerHTML = `
          <table class="tight-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Title</th>
                <th>Venue</th>
                <th>Status</th>
                <th>Currency</th>
                <th>Wallet</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>`;

        body.querySelectorAll("tr[data-event-code]").forEach(tr => {
          tr.addEventListener("click", () => {
            const code = tr.getAttribute("data-event-code") || "";
            const ev = (eventsCache || []).find(x => String(x.event_code || "") === String(code));
            if (!ev){
              return;
            }
            if (ev.event_code){
              const url = `/events/${encodeURIComponent(String(ev.event_code))}/dashboard`;
              loadIframe(url);
              return;
            }
            openEventModal(ev);
          });
        });
      }

      async function loadEventsList(force = false){
        if (!hasScope("admin:web") && !hasScope("event:host")) return;
        const body = $("eventsListBody");
        if (body && force){
          body.textContent = "Loading events...";
        }
        try{
          const f = getEventsFilters();
          const params = new URLSearchParams();
          if (f.q) params.set("q", f.q);
          if (f.venue_id) params.set("venue_id", f.venue_id);
          params.set("include_ended", f.include_ended ? "1" : "0");
          const resp = await jsonFetch(`/admin/events?${params.toString()}`, {method: "GET"});
          if (resp.ok){
            eventsCache = resp.events || [];
            renderEventsList();
          }
        }catch(err){
          eventsCache = [];
          renderEventsList();
        }
      }

      async function loadEventOptions(selectId){
        const select = $(selectId);
        if (!select) return;
        select.innerHTML = `<option value="">No event</option>`;
        try{
          const resp = await jsonFetch("/admin/events?include_ended=0", {method: "GET"});
          if (!resp.ok) throw new Error(resp.error || "Unable to load events");
          const items = (resp.events || []).filter(ev => String(ev.status || "").toLowerCase() !== "ended");
          items.forEach(ev => {
            const id = ev.id ?? ev.event_id ?? "";
            if (!id) return;
            const opt = document.createElement("option");
            const title = ev.title || ev.event_code || `Event ${id}`;
            const status = ev.status ? ` (${ev.status})` : "";
            opt.value = String(id);
            opt.textContent = `${title}${status}`;
            opt.dataset.code = ev.event_code || "";
            select.appendChild(opt);
          });
        }catch(err){
          select.innerHTML = `<option value="">No events available</option>`;
        }
      }

      function setEventBackgroundStatus(url){
        const el = $("eventBackgroundStatus");
        const img = $("eventBackgroundPreviewImg");
        const empty = $("eventBackgroundPreviewEmpty");
        const preview = $("eventBackgroundPreview");
        const modal = $("eventModal");
        const artist = modal?.dataset?.artist_name || "";
        if (!el) return;
        if (!url){
          el.textContent = "No background selected.";
          if (img) img.style.display = "none";
          if (empty) empty.style.display = "flex";
          if (preview) preview.style.display = "flex";
          return;
        }
        if (img){
          img.src = url;
          img.style.display = "block";
        }
        if (empty) empty.style.display = "none";
        if (preview) preview.style.display = "flex";
        el.textContent = artist ? `Selected (${artist})` : "Selected.";
      }

      function setEventGamesStatus(games){
        const el = $("eventGamesStatus");
        if (!el) return;
        const list = Array.isArray(games) ? games.filter(Boolean) : [];
        if (!list.length){
          el.textContent = "All games allowed (no filter).";
          return;
        }
        el.textContent = `Enabled: ${list.join(", ")}`;
      }

      function showEventGamesModal(show){
        const modal = $("eventGamesModal");
        if (!modal) return;
        modal.classList.toggle("show", !!show);
      }

      function syncEventGamesModalChecks(enabled){
        const set = new Set((enabled || []).map(x => String(x || "").trim().toLowerCase()).filter(Boolean));
        document.querySelectorAll("#eventGamesModal .event-game-check").forEach(cb => {
          const val = String(cb.value || "").trim().toLowerCase();
          cb.checked = set.has(val);
        });
      }

      function readEventGamesModalChecks(){
        const out = [];
        document.querySelectorAll("#eventGamesModal .event-game-check").forEach(cb => {
          if (cb.checked){
            const val = String(cb.value || "").trim().toLowerCase();
            if (val) out.push(val);
          }
        });
        return out;
      }

      function showEventWalletModal(show){
        const modal = $("eventWalletModal");
        if (!modal) return;
        modal.classList.toggle("show", !!show);
        if (!show){
          modal.dataset.player = "";
        }
      }

      function openEventWalletModal(playerName, balance, currency){
        const modal = $("eventWalletModal");
        const status = $("eventWalletStatus");
        const eventModal = $("eventModal");
        if (!modal || !eventModal) return;
        const walletEnabled = modal.dataset.wallet_enabled === "1" || eventModal.dataset.wallet_enabled === "1";
        const eventId = parseInt(eventModal.dataset.event_id || modal.dataset.event_id || "0", 10) || 0;
        if (!walletEnabled || !eventId){
          if (status) status.textContent = "Save the event and enable wallets first.";
          return;
        }
        modal.dataset.player = playerName || "";
        modal.dataset.event_id = String(eventId);
        modal.dataset.currency = currency || modal.dataset.currency || "";
        const playerLabel = $("eventWalletPlayerLabel");
        if (playerLabel) playerLabel.textContent = `Player: ${playerName || "-"}`;
        const balanceLabel = $("eventWalletBalanceLabel");
        const balanceText = currency ? `${balance || 0} ${currency}` : String(balance || 0);
        if (balanceLabel) balanceLabel.textContent = `Balance: ${balanceText}`;
        if (status) status.textContent = "Ready.";
        const amt = $("eventWalletAmount");
        if (amt){
          amt.disabled = false;
          amt.value = "";
        }
        const comment = $("eventWalletComment");
        if (comment){
          comment.disabled = false;
          comment.value = "";
        }
        showEventWalletModal(true);
      }

      function openEventModal(eventObj){
        const modal = $("eventModal");
        if (!modal) return;
        modal.classList.add("show");
        loadEventsVenues();
        const isNew = !eventObj || !eventObj.id;
        modal.dataset.event_id = String(eventObj?.id || "");
        modal.dataset.event_code = String(eventObj?.event_code || "");
        const walletModalRef = $("eventWalletModal");
        if (walletModalRef){
          walletModalRef.dataset.event_id = String(eventObj?.id || "");
          walletModalRef.dataset.currency = eventObj?.currency_name || "";
        }
        loadEventPlayers(eventObj?.id || 0);
        loadEventSummary(eventObj?.id || 0);
        $("eventModalTitle").textContent = isNew ? "Add event" : `Event: ${eventObj.title || eventObj.event_code}`;
        $("eventTitle").value = eventObj?.title || "";
        modal.dataset.venue_id = eventObj?.venue_id ? String(eventObj.venue_id) : "";
        modal.dataset.currency_name = eventObj?.currency_name || "";
        const venueDisplay = $("eventVenueDisplay");
        if (venueDisplay){
          const venueName = eventObj?.venue_name || eventObj?.venue || "Database-managed venue";
          venueDisplay.textContent = `Venue: ${venueName}`;
        }
        const currencyDisplay = $("eventCurrencyDisplay");
        if (currencyDisplay){
          const currencyName = eventObj?.currency_name || "";
          currencyDisplay.textContent = `Currency: ${currencyName || "(none)"}`;
        }
        $("eventWalletEnabled").checked = !!eventObj?.wallet_enabled;
        const carryEl = $("eventCarryOver");
        if (carryEl){
          const meta = eventObj?.metadata || {};
          carryEl.checked = !!(meta.carry_over || meta.carryover);
        }
        const joinWalletEl = $("eventJoinWalletAmount");
        if (joinWalletEl){
          const meta = eventObj?.metadata || {};
          const raw = meta.join_wallet_amount ?? meta.join_wallet_bonus ?? 0;
          joinWalletEl.value = String(raw || 0);
        }

        // Event background + enabled minigames
        const meta = eventObj?.metadata || {};
        const bg = String(meta.background_url || meta.background || "").trim();
        modal.dataset.background_url = bg;
        modal.dataset.artist_id = meta.background_artist_id || meta.backgroundArtistId || "";
        modal.dataset.artist_name = meta.background_artist_name || meta.backgroundArtistName || "";
        setEventBackgroundStatus(bg);
        const enabled = Array.isArray(meta.enabled_games)
          ? meta.enabled_games
          : (Array.isArray(meta.enabledGames) ? meta.enabledGames : []);
        modal.dataset.enabled_games = JSON.stringify(
          Array.isArray(enabled)
            ? enabled.map(x => String(x || "").trim().toLowerCase()).filter(Boolean)
            : []
        );
        setEventGamesStatus(getEventEnabledGames(modal));

        const walletAmount = $("eventWalletAmount");
        const walletSet = $("eventWalletSet");
        const walletStatus = $("eventWalletStatus");
        const walletComment = $("eventWalletComment");
        const walletEnabled = !!eventObj?.wallet_enabled;
        const walletModal = $("eventWalletModal");
        if (walletModal){
          walletModal.dataset.wallet_enabled = walletEnabled && !isNew ? "1" : "0";
        }
        modal.dataset.wallet_enabled = walletEnabled ? "1" : "0";
        if (walletAmount) walletAmount.disabled = !walletEnabled || isNew;
        if (walletComment) walletComment.disabled = !walletEnabled || isNew;
        if (walletSet) walletSet.disabled = !walletEnabled || isNew;
        if (walletStatus){
          walletStatus.textContent = walletEnabled ? "Ready." : "Wallet is disabled for this event.";
        }
        const playersNote = $("eventPlayersNote");
        if (playersNote){
          playersNote.textContent = (!walletEnabled || isNew)
            ? "Save the event and enable wallets to manage balances."
            : "Click a player to top up their wallet.";
        }

        const joinInfo = $("eventJoinInfo");
        const copyBtn = $("eventCopyJoin");
        const endBtn = $("eventEnd");
        if (eventObj?.event_code){
          const base = (window.location.origin || "").replace(/\/$/, "");
          const joinUrl = `${base}/events/${eventObj.event_code}`;
          if (joinInfo) joinInfo.innerHTML = `Join link: <a href="${joinUrl}" target="_blank" rel="noopener">${escapeHtml(joinUrl)}</a>`;
          if (copyBtn) copyBtn.style.display = "inline-flex";
          if (endBtn) endBtn.style.display = (eventObj.status === "ended") ? "none" : "inline-flex";
          }else{
            if (joinInfo) joinInfo.textContent = "Create the event to get a join link.";
            if (copyBtn) copyBtn.style.display = "none";
            if (endBtn) endBtn.style.display = "none";
          }
        }

        async function loadEventPlayers(eventId){
          const box = $("eventPlayersList");
          if (!box) return;
          const id = parseInt(String(eventId || "0"), 10) || 0;
          const walletEnabled = $("eventModal")?.dataset?.wallet_enabled === "1";
          const walletModalRef = $("eventWalletModal");
          if (!id){
            box.textContent = "Save the event to view registered players.";
            return;
          }
          box.textContent = "Loading players...";
          try{
            const resp = await jsonFetch(`/admin/events/${encodeURIComponent(String(id))}/players`, {method: "GET"});
            if (!resp.ok){
              throw new Error(resp.error || "Unable to load players");
            }
            const players = resp.players || [];
            const currency = resp.currency_name || resp.currency || resp.currencyName || walletModalRef?.dataset?.currency || "";
            if (walletModalRef) walletModalRef.dataset.currency = currency || "";
            if (!players.length){
              box.textContent = "No players have joined yet.";
              return;
            }
            const rows = players.map(p => {
              const name = String(p?.xiv_username || p?.user || "").trim() || "Unknown";
              const balanceRaw = p?.wallet_balance ?? p?.balance ?? p?.wallet ?? 0;
              const balanceLabel = currency ? `${balanceRaw} ${currency}` : String(balanceRaw);
              const btn = walletEnabled
                ? `<button class="btn-ghost" type="button" data-topup="${escapeHtml(name)}" data-balance="${escapeHtml(String(balanceRaw))}" data-currency="${escapeHtml(currency)}">Top up</button>`
                : "<span class=\"muted\" style=\"font-size:12px;\">Wallet disabled</span>";
              return `
                <div class="event-player-row" style="display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 10px; border:1px solid rgba(255,255,255,.08); border-radius:10px;">
                  <div>
                    <div style="font-weight:600;">${escapeHtml(name)}</div>
                    <div class="muted" style="font-size:12px;">Wallet: ${escapeHtml(balanceLabel || "-")}</div>
                  </div>
                  ${btn}
                </div>
              `;
            }).join("") || "<div class=\"muted\">No players have joined yet.</div>";
            box.innerHTML = rows;
            if (walletEnabled){
              box.querySelectorAll("button[data-topup]").forEach(btn => {
                btn.addEventListener("click", () => {
                  const player = btn.dataset.topup || "";
                  const bal = btn.dataset.balance || "-";
                  const cur = btn.dataset.currency || currency || "";
                  openEventWalletModal(player, bal, cur);
                });
              });
            }
          }catch(err){
            box.textContent = err.message || "Unable to load players.";
          }
        }

        async function loadEventSummary(eventId){
          const el = $("eventHouseTotal");
          if (!el) return;
          const id = parseInt(String(eventId || "0"), 10) || 0;
          if (!id){
            el.textContent = "House total: -";
            return;
          }
          el.textContent = "House total: loading...";
          try{
            const resp = await jsonFetch(`/admin/events/${encodeURIComponent(String(id))}/summary`, {method: "GET"});
            if (!resp.ok){
              throw new Error(resp.error || "Unable to load totals");
            }
            const totals = resp.totals || {};
            const net = totals.net ?? 0;
            const currency = resp.currency_name || "";
            const label = currency ? `${net} ${currency}` : String(net);
            el.textContent = `House total: ${label}`;
          }catch(err){
            el.textContent = "House total: unavailable";
          }
        }

      async function saveEventModal(){
        const modal = $("eventModal");
        if (!modal) return;
        const payload = {
          id: modal.dataset.event_id || "",
          event_code: modal.dataset.event_code || "",
          title: $("eventTitle")?.value?.trim() || "",
          venue_id: modal.dataset.venue_id || "",
          currency_name: modal.dataset.currency_name || "",
          wallet_enabled: $("eventWalletEnabled")?.checked || false,
          carry_over: $("eventCarryOver")?.checked || false,
          join_wallet_amount: $("eventJoinWalletAmount")?.value || "0",
          background_url: modal.dataset.background_url || "",
          enabled_games: getEventEnabledGames(modal),
        };
        const joinInfo = $("eventJoinInfo");
        if (joinInfo) joinInfo.textContent = "Saving...";
        try{
          const resp = await jsonFetch("/admin/events/upsert", {method: "POST", body: JSON.stringify(payload)});
          if (!resp.ok) throw new Error(resp.error || "save failed");
          const ev = resp.event;
          // Update cache
          const idx = (eventsCache || []).findIndex(x => x.id === ev.id);
          if (idx >= 0) eventsCache[idx] = ev; else eventsCache.unshift(ev);
          renderEventsList();
          openEventModal(ev);
        }catch(err){
          if (joinInfo) joinInfo.textContent = err.message || "Unable to save event.";
        }
      }

      async function endEventModal(){
        const modal = $("eventModal");
        if (!modal) return;
        const id = parseInt(modal.dataset.event_id || "0", 10) || 0;
        if (!id) return;
        const title = $("eventTitle")?.value?.trim() || modal.dataset.event_code || `Event ${id}`;
        if (!window.confirm(`End event "${title}"?

This will block new games from being created in this event, but existing games can still be finished.`)) return;
        const joinInfo = $("eventJoinInfo");
        if (joinInfo) joinInfo.textContent = "Ending event...";
        try{
          const resp = await jsonFetch("/admin/events/end", {method: "POST", body: JSON.stringify({event_id: id})});
          if (!resp.ok) throw new Error(resp.error || "end failed");
          await loadEventsList(true);
          const updated = (eventsCache || []).find(x => x.id === id);
          if (updated) openEventModal(updated);
          else modal.classList.remove("show");
        }catch(err){
          if (joinInfo) joinInfo.textContent = err.message || "Unable to end event.";
        }
      }

      function renderGamesList(result){
        const body = $("gamesListBody");
        const meta = $("gamesListMeta");
        const pageLabel = $("gamesPageLabel");
        if (!body) return;
        const games = result?.games || [];
        const total = result?.total || 0;
        const page = result?.page || 1;
        const pageSize = result?.page_size || gamesListState.page_size;
        gamesListState.total = total;
        gamesListState.page = page;
        gamesListState.page_size = pageSize;

        const start = total ? ((page - 1) * pageSize + 1) : 0;
        const end = Math.min(page * pageSize, total);
        if (meta){
          meta.textContent = total ? `Showing ${start}-${end} of ${total}` : "No games found.";
        }
        if (pageLabel){
          const pages = Math.max(1, Math.ceil((total || 0) / pageSize));
          pageLabel.textContent = `Page ${page} / ${pages}`;
        }

        if (!games.length){
          body.textContent = "No games match the current filters.";
          return;
        }

        const rows = games.map(g => {
          const id = escapeHtml(g.game_id || "-");
          const title = escapeHtml(g.title || "");
          const module = escapeHtml(g.module || "-");
          const status = escapeHtml(g.status || "-");
          const active = g.active ? "Yes" : "No";
          const players = Array.isArray(g.players) ? g.players.map(p => p.name).filter(Boolean).join(", ") : (g.players || "");
          const venue = escapeHtml(g.venue_name || "-");
          const claimed = escapeHtml(g.claimed_username || "-");
          const created = escapeHtml(g.created_at || "-");
          const join = escapeHtml(g.join_code || "");
          const subtitle = join ? `<div class="muted" style="font-size:12px;">Join: <code>${join}</code></div>` : "";
          const titleLine = title ? `<div style="font-weight:600;">${title}</div>` : "";
          return `<tr>
            <td><code>${id}</code>${subtitle}</td>
            <td>${module}</td>
            <td><span class="status-chip">${status}</span> <span class="muted">(${active})</span></td>
            <td>${escapeHtml(players || "-")}</td>
            <td>${venue}</td>
            <td>${claimed}</td>
            <td>${created}</td>
          </tr>`;
        }).join("");

        body.innerHTML = `
          <table class="games-list-table">
            <thead>
              <tr>
                <th>Game</th>
                <th>Module</th>
                <th>Status</th>
                <th>Players</th>
                <th>Venue</th>
                <th>Claimed by</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        `;
      }

      async function loadGamesList(force = false){
        if (!ensureScope("admin:web", "Admin web access required.")) return;
        const body = $("gamesListBody");
        if (body){
          body.textContent = force ? "Loading games..." : (body.textContent || "Loading games...");
        }
        const filters = getGamesFilters();
        const sameFilters =
          gamesListState.q === filters.q &&
          gamesListState.player === filters.player &&
          gamesListState.module === filters.module &&
          gamesListState.venue_id === filters.venue_id &&
          gamesListState.include_inactive === filters.include_inactive &&
          gamesListState.page_size === filters.page_size;

        if (!force && sameFilters && gamesListState.total && $("gamesListBody")?.innerHTML){
          return;
        }

        gamesListState.q = filters.q;
        gamesListState.player = filters.player;
        gamesListState.module = filters.module;
        gamesListState.venue_id = filters.venue_id;
        gamesListState.include_inactive = filters.include_inactive;
        gamesListState.page_size = filters.page_size;

        const params = new URLSearchParams();
        if (gamesListState.q) params.set("q", gamesListState.q);
        if (gamesListState.player) params.set("player", gamesListState.player);
        if (gamesListState.module) params.set("module", gamesListState.module);
        if (gamesListState.venue_id) params.set("venue_id", gamesListState.venue_id);
        params.set("include_inactive", gamesListState.include_inactive ? "1" : "0");
        params.set("page", String(gamesListState.page || 1));
        params.set("page_size", String(gamesListState.page_size || 50));

        try{
          const resp = await jsonFetch(`/admin/games/list?${params.toString()}`, {method: "GET"});
          if (!resp.ok){
            throw new Error(resp.error || "Unable to load games");
          }
          renderGamesList(resp);
        }catch(err){
          if (body){
            body.textContent = err.message || "Unable to load games.";
          }
        }
      }

      function hasScope(scope){
        if (previewScopesActive){
          return previewScopes.has("*") || previewScopes.has(scope);
        }
        return authUserScopes.has("*") || authUserScopes.has(scope);
      }

      function ensureScope(scope, msg){
        if (hasScope(scope)) return true;
        setStatus(msg || "Unauthorized.", "err");
        return false;
      }

      function ensureCardgamesScope(msg){
        if (hasScope("cardgames:admin") || hasScope("tarot:admin")) return true;
        const message = msg || "Cardgames access required.";
        setStatus(message, "err");
        setCardgameStatus(message, "err");
        return false;
      }

      function setLibraryStatus(msg, kind){
        setStatusText("uploadLibraryStatus", msg, kind);
      }

      function setMediaUploadStatus(msg, kind){
        setStatusText("mediaUploadStatus", msg, kind);
      }

      function setMediaLibraryStatus(msg, kind){
        setStatusText("mediaLibraryStatus", msg, kind);
      }

      function showToast(msg, kind){
        const stack = $("toastStack");
        if (!stack) return;
        const toast = document.createElement("div");
        toast.className = "toast" + (kind ? " " + kind : "");
        toast.textContent = msg;
        stack.appendChild(toast);
        setTimeout(() => {
          toast.remove();
        }, 2400);
      }

      async function setMediaHidden(item, hidden){
        if (!item) return;
        const itemId = item.item_id || (item.name ? `media:${item.name}` : "");
        if (!itemId) return;
        await jsonFetch("/api/gallery/hidden", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({item_id: itemId, hidden: !!hidden})
        }, true);
        item.hidden = !!hidden;
      }

      function updateUploadDropDisplay(file){
        const title = $("uploadLibraryDropTitle");
        const meta = $("uploadLibraryDropMeta");
        const cta = $("uploadLibraryDropCta");
        if (!title || !meta || !cta) return;
        if (file){
          title.textContent = `Selected: ${file.name}`;
          meta.textContent = `${Math.round(file.size / 1024)} KB`;
          cta.textContent = "Click to replace";
        }else{
          title.textContent = "Drag & drop an image";
          meta.textContent = "PNG, JPG, GIF, WEBP";
          cta.textContent = "or click to choose";
        }
      }

      function updateUploadState(){
        const file = libraryUploadFile || ($("uploadLibraryFile").files[0] || null);
        const title = $("uploadLibraryTitleInput").value.trim();
        const btn = $("uploadLibraryUpload");
        if (btn){
          btn.disabled = !(file && title);
        }
      }

      function formatSuitPresetJson(key){
        const preset = SUIT_PRESETS[key] || [];
        return JSON.stringify(preset, null, 2);
      }

      function parseSuitJson(raw){
        const text = (raw || "").trim();
        if (!text){
          return [];
        }
        const parsed = JSON.parse(text);
        if (!Array.isArray(parsed)){
          throw new Error("Suit definitions must be a JSON array.");
        }
        return parsed;
      }

      function updateMediaUploadDropDisplay(file){
        const title = $("mediaUploadDropTitle");
        const meta = $("mediaUploadDropMeta");
        const cta = $("mediaUploadDropCta");
        if (!title || !meta || !cta) return;
        if (file){
          title.textContent = `Selected: ${file.name}`;
          meta.textContent = `${Math.round(file.size / 1024)} KB`;
          cta.textContent = "Click to replace";
        }else{
          title.textContent = "Drag & drop an image";
          meta.textContent = "PNG, JPG, GIF, WEBP";
          cta.textContent = "or click to choose";
        }
      }

      function updateMediaUploadState(){
        const file = mediaUploadFile || ($("mediaUploadFile") ? $("mediaUploadFile").files[0] : null);
        const title = $("mediaUploadTitleInput") ? $("mediaUploadTitleInput").value.trim() : "";
        const btn = $("mediaUploadUpload");
        if (btn){
          btn.disabled = !(file && title);
        }
      }

      function showLibraryModal(show){
        $("uploadLibraryModal").classList.toggle("show", !!show);
        if (show){
          $("mediaModal").classList.remove("show");
          $("artistModal").classList.remove("show");
          $("calendarModal").classList.remove("show");
          updateUploadDropDisplay(libraryUploadFile);
          updateUploadState();
        }
      }

      async function loadLibrary(kind, opts){
        libraryKind = kind;
        const config = opts || {};
        const grid = config.grid || $("uploadLibraryGrid");
        const title = Object.prototype.hasOwnProperty.call(config, "title") ? config.title : $("uploadLibraryTitle");
        const setStatus = config.setStatus || setLibraryStatus;
        const onSelect = config.onSelect || librarySelectHandler;
        const showUse = Object.prototype.hasOwnProperty.call(config, "showUse") ? config.showUse : !!onSelect;
        const showCopy = !!config.showCopy;
        const onCardClick = config.onCardClick || null;
        const closeOnUse = config.closeOnUse !== false;
        if (title){
          title.textContent = config.titleText || "Media Library";
        }
        if (!grid){
          return;
        }
        if (!(hasScope("bingo:admin") || hasScope("tarot:admin") || hasScope("admin:web"))){
          setStatus("Media access requires permission.", "err");
          return;
        }
        grid.innerHTML = "";
        setStatus("Loading...", "");
        const path = "/api/media/list";
        try{
          const res = await fetch(path, {headers: {"X-API-Key": apiKeyEl.value.trim()}});
          if (res.status === 401){
            handleUnauthorized();
            throw new Error("Unauthorized");
          }
          const contentType = (res.headers.get("content-type") || "").toLowerCase();
          if (!contentType.includes("application/json")){
            const text = await res.text();
            const hint = text && text.startsWith("<!doctype") ? "HTML response returned." : "Non-JSON response returned.";
            throw new Error(`Media list failed (${res.status}). ${hint}`);
          }
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
          const items = data.items || [];
          if (!items.length){
            setStatus("No images found.", "err");
            return;
          }
        items.forEach(item => {
          const card = document.createElement("div");
          card.className = "preview-card library-card";
          card.dataset.filename = item.name || item.filename || "";
          if (onCardClick){
            card.addEventListener("click", () => onCardClick(item));
          }

          const img = document.createElement("img");
            img.src = item.url;
            img.alt = item.name || "image";
            if (item.fallback_url){
              img.dataset.fallback = item.fallback_url;
              img.addEventListener("error", () => {
                if (img.dataset.fallback && img.src !== img.dataset.fallback){
                  img.src = img.dataset.fallback;
                }
              });
            }

            const titleText = document.createElement("div");
            titleText.className = "library-card-title";
            titleText.textContent = item.title || item.name || "Untitled";

            const artist = document.createElement("div");
            artist.className = "library-card-artist";
            if (item.artist_id || item.artist_name){
              artist.textContent = "Artist: ";
              const artistBtn = document.createElement("button");
              artistBtn.type = "button";
              artistBtn.textContent = item.artist_name || item.artist_id || "Unknown";
              artistBtn.addEventListener("click", () => openArtistIndex(item.artist_id || "", setStatus));
              artist.appendChild(artistBtn);
            }else{
              artist.textContent = "Artist: Unassigned";
            }

            const badges = document.createElement("div");
            badges.className = "library-badges";
            const usedIn = Array.isArray(item.used_in) ? item.used_in : [];
            usedIn.forEach(label => {
              const badge = document.createElement("span");
              badge.className = "library-badge";
              badge.textContent = label;
              badges.appendChild(badge);
            });

            const actions = document.createElement("div");
            actions.className = "library-actions";
          if (showUse){
            const useBtn = document.createElement("button");
            useBtn.type = "button";
            useBtn.className = "btn-primary";
            useBtn.textContent = "Use";
            useBtn.addEventListener("click", (ev) => {
              ev.stopPropagation();
              if (onSelect){
                onSelect(item);
              }
              if (closeOnUse){
                showLibraryModal(false);
              }
              });
              actions.appendChild(useBtn);
            }
          if (showCopy){
            const copyBtn = document.createElement("button");
            copyBtn.type = "button";
            copyBtn.className = "btn-ghost";
            copyBtn.textContent = "Copy URL";
            copyBtn.addEventListener("click", async (ev) => {
              ev.stopPropagation();
              try{
                await navigator.clipboard.writeText(item.url || "");
                setStatus("Image URL copied.", "ok");
              }catch(err){
                setStatus("Copy failed.", "err");
                }
              });
              actions.appendChild(copyBtn);
            }

          if (authUserIsElfmin && item.delete_url){
            const del = document.createElement("button");
            del.type = "button";
            del.className = "btn-ghost btn-danger";
            del.textContent = "Delete";
            del.addEventListener("click", async (ev) => {
              ev.stopPropagation();
              const usage = usedIn.length ? `This image is used in: ${usedIn.join(", ")}.` : "";
              const prompt = usage
                ? `${usage} This image may be used elsewhere. Continue?`
                : "This image may be used elsewhere. Continue?";
              if (!confirm(prompt)) return;
                try{
                  const delUrl = item.delete_url || "";
                  if (!delUrl){
                    throw new Error("Delete not available");
                  }
                  const res = await fetch(delUrl, {method: "DELETE", headers: {"X-API-Key": apiKeyEl.value.trim()}});
                  const data = await res.json().catch(() => ({}));
                  if (!res.ok || data.ok === false){
                    throw new Error(data.error || "Delete failed");
                  }
                  await loadLibrary(libraryKind, config);
                }catch(err){
                  setStatus(err.message, "err");
                }
              });
              actions.appendChild(del);
            }

            card.appendChild(img);
            card.appendChild(titleText);
            card.appendChild(artist);
            if (usedIn.length){
              card.appendChild(badges);
            }
            card.appendChild(actions);
            grid.appendChild(card);
          });
          setStatus(showUse && onSelect ? "Pick an image." : "Library loaded.", "ok");
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      async function openArtistIndex(artistId, statusFn){
        const notify = statusFn || setLibraryStatus;
        if (!artistId){
          notify("No artist assigned.", "alert");
          return;
        }
        $("artistModal").classList.add("show");
        await loadTarotArtists();
        const select = $("artistIndexSelect");
        if (select){
          select.value = artistId;
          select.dispatchEvent(new Event("change"));
        }
      }

      function setCalendarStatus(msg, kind){
        setStatusText("calendarStatus", msg, kind);
      }

      function setMediaEditStatus(msg, kind){
        setStatusText("mediaEditStatus", msg, kind);
      }

      let currentMediaEdit = null;
      function setMediaTab(tab){
        const uploadBtn = $("mediaTabUploadBtn");
        const editBtn = $("mediaTabEditBtn");
        const uploadPanel = $("mediaTabUpload");
        const editPanel = $("mediaTabEdit");
        if (!uploadBtn || !editBtn || !uploadPanel || !editPanel) return;
        if (tab === "edit" && editBtn.disabled){
          tab = "upload";
        }
        uploadBtn.classList.toggle("active", tab === "upload");
        editBtn.classList.toggle("active", tab === "edit");
        uploadPanel.classList.toggle("active", tab === "upload");
        editPanel.classList.toggle("active", tab === "edit");
      }

        function updateMediaEditPanel(){
        const count = mediaSelected.size;
        const editBtn = $("mediaTabEditBtn");
        if (editBtn){
          editBtn.disabled = count === 0;
            editBtn.title = editBtn.disabled ? "Select an image to edit" : "";
            if (editBtn.disabled && editBtn.classList.contains("active")){
              setMediaTab("upload");
            }
          }
        const empty = $("mediaEditEmpty");
        const card = $("mediaEditCard");
        const meta = $("mediaEditMeta");
        const identity = $("mediaEditIdentity");
        const artistDisplay = $("mediaEditArtistDisplay");
        const originDisplay = $("mediaEditOriginDisplay");
        const hasSingle = count === 1 && currentMediaEdit;
        const canDelete = hasScope("admin:web");
        if (!hasSingle){
          if (card) card.classList.add("hidden");
          if (empty){
            empty.classList.remove("hidden");
            empty.textContent = count
              ? "Multiple images selected. Use bulk actions or select a single image to edit."
              : "Select an image to edit.";
          }
          $("mediaEditSave").disabled = true;
          $("mediaEditClear").disabled = count === 0;
          $("mediaEditCopy").disabled = true;
          $("mediaEditOpen").disabled = true;
          $("mediaEditDelete").disabled = true;
          $("mediaEditHide").disabled = true;
          if (meta) meta.textContent = "";
          const preview = $("mediaEditPreview");
          if (preview) preview.innerHTML = "";
          if (identity) identity.textContent = "-";
          if (artistDisplay) artistDisplay.textContent = "-";
          if (originDisplay) originDisplay.textContent = "-";
            setMediaEditStatus(count ? "Multiple selected." : "Select an image to edit.", "");
            return;
          }
          if (editBtn && !editBtn.disabled){
            setMediaTab("edit");
          }
          if (empty) empty.classList.add("hidden");
          if (card) card.classList.remove("hidden");
          $("mediaEditFilename").value = currentMediaEdit.name || "";
          $("mediaEditTitle").value = currentMediaEdit.title || "";
          $("mediaEditArtist").value = currentMediaEdit.artist_id || "";
          $("mediaEditOriginType").value = currentMediaEdit.origin_type || "Artifact";
          $("mediaEditOriginLabel").value = currentMediaEdit.origin_label || "";
          $("mediaEditType").value = currentMediaEdit.media_type || "";
          $("mediaEditVenue").value = currentMediaEdit.venue_id ? String(currentMediaEdit.venue_id) : "";
          $("mediaEditSave").disabled = false;
          $("mediaEditClear").disabled = false;
          $("mediaEditCopy").disabled = false;
          $("mediaEditOpen").disabled = false;
          $("mediaEditDelete").disabled = !currentMediaEdit.delete_url || !canDelete;
          const isHidden = currentMediaEdit.hidden === true
            || currentMediaEdit.hidden === "true"
            || currentMediaEdit.hidden === 1
            || currentMediaEdit.hidden === "1";
        $("mediaEditHide").disabled = false;
        $("mediaEditHide").textContent = isHidden ? "Show in gallery" : "Hide in gallery";
        if (identity) identity.textContent = currentMediaEdit.title || currentMediaEdit.name || "-";
        if (artistDisplay) artistDisplay.textContent = currentMediaEdit.artist_name || currentMediaEdit.artist_id || "Forest";
        const originText = [currentMediaEdit.origin_type || "", currentMediaEdit.origin_label || ""].filter(Boolean).join(" - ");
        if (originDisplay) originDisplay.textContent = originText || "Unlabeled";
          if (meta){
            meta.textContent = `filename: ${currentMediaEdit.name || ""}\nartist_id: ${currentMediaEdit.artist_id || "none"}\norigin_type: ${currentMediaEdit.origin_type || ""}\norigin_label: ${currentMediaEdit.origin_label || ""}\nmedia_type: ${currentMediaEdit.media_type || ""}\nvenue_id: ${currentMediaEdit.venue_id || ""}\nhidden: ${isHidden ? "yes" : "no"}`;
          }
        const preview = $("mediaEditPreview");
        if (preview){
          const img = document.createElement("img");
          img.src = currentMediaEdit.url || "";
          img.alt = currentMediaEdit.title || currentMediaEdit.name || "Preview";
          if (currentMediaEdit.fallback_url){
            img.dataset.fallback = currentMediaEdit.fallback_url;
            img.addEventListener("error", () => {
              if (img.dataset.fallback && img.src !== img.dataset.fallback){
                img.src = img.dataset.fallback;
              }
            });
          }
          preview.innerHTML = "";
          preview.appendChild(img);
        }
          setMediaEditStatus("Edit details and save.", "ok");
        }

        let mediaVenueCache = [];
        async function ensureMediaVenueOptions(){
          if (!hasScope("admin:web")) return;
          if (!mediaVenueCache.length){
            try{
              const resp = await jsonFetch("/admin/venues", {method:"GET"});
              mediaVenueCache = resp.venues || [];
            }catch(err){
              mediaVenueCache = [];
            }
          }
          populateMediaVenueSelects(mediaVenueCache);
        }

        function populateMediaVenueSelects(venues){
          const selects = ["mediaFilterVenue", "mediaUploadVenue", "mediaEditVenue"];
          selects.forEach((id) => {
            const el = $(id);
            if (!el) return;
            const current = el.value || "";
            const opts = [`<option value=\"\">All venues</option>`]
              .concat((venues || []).map(v => {
                const vid = v.id ?? v.venue_id ?? "";
                const name = v.name || `Venue ${vid}`;
                return `<option value=\"${escapeHtml(String(vid))}\">${escapeHtml(name)}</option>`;
              }));
            el.innerHTML = opts.join("");
            if (current && Array.from(el.options).some(o => o.value === current)){
              el.value = current;
            }else if (!current && adminVenueId){
              el.value = String(adminVenueId);
            }
          });
        }

        async function loadMediaLibrary(){
          const grid = $("mediaLibraryGrid");
          if (!grid) return;
          if (!(hasScope("bingo:admin") || hasScope("tarot:admin") || hasScope("admin:web"))){
            setMediaLibraryStatus("Media access requires permission.", "err");
          grid.innerHTML = "";
          return;
        }
          setMediaLibraryStatus("Refreshing...", "");
        grid.innerHTML = "";
        for (let i = 0; i < 8; i++){
          const skel = document.createElement("div");
          skel.className = "skeleton-card";
          grid.appendChild(skel);
        }
        try{
          const typeFilter = ($("mediaFilterType")?.value || "").trim();
          const venueFilter = ($("mediaFilterVenue")?.value || "").trim();
          const originFilter = ($("mediaFilterOriginType")?.value || "").trim();
          const params = new URLSearchParams();
          if (typeFilter) params.set("media_type", typeFilter);
          if (venueFilter) params.set("venue_id", venueFilter);
          if (originFilter) params.set("origin_type", originFilter);
          const url = params.toString() ? `/api/media/list?${params.toString()}` : "/api/media/list";
          const res = await apiFetch(url, {method: "GET"}, true);
          if (res.status === 401){
            handleUnauthorized();
            throw new Error("Unauthorized");
          }
          const contentType = (res.headers.get("content-type") || "").toLowerCase();
          if (!contentType.includes("application/json")){
            const text = await res.text();
            const hint = text && text.startsWith("<!doctype") ? "HTML response returned." : "Non-JSON response returned.";
            throw new Error(`Media list failed (${res.status}). ${hint}`);
          }
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
            mediaLibraryItems = data.items || [];
            mediaSelected.clear();
            mediaLastIndex = null;
            currentMediaEdit = null;
              applyMediaFilters();
              showToast("Library loaded.", "ok");
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
        }
      }

      function mediaKey(item){
        return item.name || item.filename || item.url || "";
      }

          function applyMediaFilters(){
            const searchEl = $("mediaToolbarSearch");
            const searchRaw = (searchEl ? searchEl.value : "").trim().toLowerCase();
            const artistEl = $("mediaFilterArtist");
            const typeEl = $("mediaFilterType");
            const originEl = $("mediaFilterOriginType");
            const venueEl = $("mediaFilterVenue");
            const labelEl = $("mediaFilterLabel");
            const artistFilter = (artistEl ? artistEl.value : "").trim();
            const typeFilter = (typeEl ? typeEl.value : "").trim();
            const originFilter = (originEl ? originEl.value : "").trim();
            const venueFilter = (venueEl ? venueEl.value : "").trim();
            const labelFilter = (labelEl ? labelEl.value : "any").trim();
            const sortEl = $("mediaToolbarSort");
            const sortMode = (sortEl ? sortEl.value : "new").trim();
            let items = mediaLibraryItems.slice();
            if (searchRaw){
              items = items.filter(item => {
                const hay = [
                  item.title,
                  item.artist_name,
                  item.artist_id,
                item.origin_label,
                item.origin_type,
                item.media_type,
                item.venue_id,
                item.name
              ].filter(Boolean).join(" ").toLowerCase();
              return hay.includes(searchRaw);
            });
          }
          if (artistFilter){
            items = items.filter(item => (item.artist_id || "") === artistFilter);
          }
          if (typeFilter){
            items = items.filter(item => (item.media_type || "") === typeFilter);
          }
          if (originFilter){
            items = items.filter(item => (item.origin_type || "") === originFilter);
          }
          if (venueFilter){
            items = items.filter(item => String(item.venue_id || "") === String(venueFilter));
          }
          if (labelFilter === "has"){
            items = items.filter(item => (item.origin_label || "").trim());
          }else if (labelFilter === "none"){
            items = items.filter(item => !(item.origin_label || "").trim());
          }
          if (sortMode === "old"){
            items.reverse();
          }else if (sortMode === "title"){
            items.sort((a, b) => (a.title || a.name || "").localeCompare(b.title || b.name || ""));
          }else if (sortMode === "artist"){
            items.sort((a, b) => (a.artist_name || a.artist_id || "").localeCompare(b.artist_name || b.artist_id || ""));
          }else if (sortMode === "gallery"){
            items.sort((a, b) => {
              const ga = (a.origin_label || "").toLowerCase();
              const gb = (b.origin_label || "").toLowerCase();
              if (ga !== gb) return ga.localeCompare(gb);
              return (a.title || a.name || "").localeCompare(b.title || b.name || "");
            });
          }
            mediaVisibleItems = items;
            renderMediaGrid(items);
            updateMediaFilterSummary({searchRaw, artistFilter, typeFilter, originFilter, venueFilter, labelFilter});
            updateMediaLibraryStatus(items.length, mediaLibraryItems.length, {searchRaw, artistFilter, typeFilter, originFilter, venueFilter, labelFilter});
          }

          function countActiveMediaFilters({searchRaw, artistFilter, typeFilter, originFilter, venueFilter, labelFilter}){
            let count = 0;
            if (searchRaw) count += 1;
            if (artistFilter) count += 1;
            if (typeFilter) count += 1;
            if (originFilter) count += 1;
            if (venueFilter) count += 1;
            if (labelFilter === "has" || labelFilter === "none") count += 1;
            return count;
          }

        function updateMediaFilterSummary(ctx){
          const summary = $("mediaFiltersSummary");
          if (!summary) return;
          const activeCount = countActiveMediaFilters(ctx);
          summary.textContent = `Filters (${activeCount} active)`;
        }

        function updateMediaLibraryStatus(visibleCount, totalCount, ctx){
          const activeCount = countActiveMediaFilters(ctx);
          if (activeCount > 0){
            setMediaLibraryStatus(`Filtered - ${visibleCount} of ${totalCount} items`, "ok");
            return;
          }
          setMediaLibraryStatus(`Library loaded - ${totalCount} items`, "ok");
        }

      function renderMediaGrid(items){
        const grid = $("mediaLibraryGrid");
        if (!grid) return;
        grid.innerHTML = "";
        if (!items.length){
          grid.innerHTML = "<div class=\"muted\">No images found.</div>";
          updateMediaBulkBar();
          updateMediaEditPanel();
          return;
        }
        items.forEach((item, idx) => {
          const key = mediaKey(item);
          const card = document.createElement("div");
          card.className = "preview-card library-card";
          card.dataset.filename = item.name || "";
          card.dataset.key = key;
          card.dataset.index = String(idx);
          card.tabIndex = 0;

          const checkbox = document.createElement("label");
          checkbox.className = "card-select";
          const boxInput = document.createElement("input");
          boxInput.type = "checkbox";
          boxInput.checked = mediaSelected.has(key);
          boxInput.addEventListener("click", (ev) => ev.stopPropagation());
          boxInput.addEventListener("change", (ev) => {
            ev.stopPropagation();
            toggleMediaSelection(item, idx, {toggle: true});
          });
          checkbox.appendChild(boxInput);
          card.appendChild(checkbox);

          const checkmark = document.createElement("div");
          checkmark.className = "card-check";
          checkmark.textContent = "OK";
          card.appendChild(checkmark);

          const img = document.createElement("img");
          img.src = item.url;
          img.alt = item.title || item.name || "image";
          if (item.fallback_url){
            img.dataset.fallback = item.fallback_url;
            img.addEventListener("error", () => {
              if (img.dataset.fallback && img.src !== img.dataset.fallback){
                img.src = img.dataset.fallback;
              }
            });
          }

          const titleText = document.createElement("div");
          titleText.className = "library-card-title";
          titleText.textContent = item.title || item.name || "Untitled";

          const artist = document.createElement("div");
          artist.className = "library-card-artist";
          artist.textContent = item.artist_name || item.artist_id || "Forest";

          const isHidden = item.hidden === true || item.hidden === "true" || item.hidden === 1 || item.hidden === "1";
          item.hidden = isHidden;
          const origin = document.createElement("div");
          origin.className = "library-card-origin muted";
          const originText = document.createElement("span");
          originText.className = "library-origin-text";
          originText.textContent = [item.origin_type, item.origin_label].filter(Boolean).join(" - ") || "Unlabeled";
          origin.appendChild(originText);

          const actions = document.createElement("div");
          actions.className = "library-actions";

          const openBtn = document.createElement("button");
          openBtn.type = "button";
          openBtn.className = "btn-ghost icon-action";
          openBtn.title = item.url ? "Open image" : "No image available";
          openBtn.innerHTML = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M10 3h10v10h-2V7.4l-9.3 9.3-1.4-1.4L16.6 6H10V3zM5 5h4v2H7v10h10v-2h2v4H5V5z\"/></svg>";
          openBtn.disabled = !item.url;
          openBtn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            if (openBtn.disabled) return;
            window.open(item.url, "_blank", "noopener");
          });
          actions.appendChild(openBtn);

          const hideBtn = document.createElement("button");
          hideBtn.type = "button";
          hideBtn.className = "btn-ghost icon-action";
          hideBtn.title = isHidden ? "Show in gallery" : "Hide from gallery";
          hideBtn.innerHTML = isHidden
            ? "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 5c5 0 9 4 10 7-1 3-5 7-10 7S3 15 2 12c1-3 5-7 10-7zm0 2c-3.4 0-6.4 2.4-7.7 5 1.3 2.6 4.3 5 7.7 5s6.4-2.4 7.7-5c-1.3-2.6-4.3-5-7.7-5zm0 2.5A2.5 2.5 0 1 1 12 15a2.5 2.5 0 0 1 0-5z\"/></svg>"
            : "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M2 5l2-2 18 18-2 2-3.5-3.5A10.9 10.9 0 0 1 12 19c-5 0-9-4-10-7a12.5 12.5 0 0 1 5.4-5.8L2 5zm5.7 5.7A3.5 3.5 0 0 0 12 15a3.4 3.4 0 0 0 2-.6l-1.5-1.5a1.5 1.5 0 0 1-1.9-1.9L7.7 10.7zM12 7c1 0 2 .4 2.7 1l-1.4 1.4A1.5 1.5 0 0 0 12 8.5c-.2 0-.4 0-.6.1L9.6 7.2A6.4 6.4 0 0 1 12 7zm6.3 2.1A11 11 0 0 1 22 12c-1 3-5 7-10 7-1.2 0-2.4-.2-3.4-.6l1.6-1.6c.6.1 1.2.2 1.8.2 3.4 0 6.4-2.4 7.7-5-.6-1.2-1.6-2.5-3-3.6l1.3-1.4z\"/></svg>";
          hideBtn.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try{
              await setMediaHidden(item, !isHidden);
              showToast(item.hidden ? "Hidden from gallery." : "Shown in gallery.", "ok");
              applyMediaFilters();
            }catch(err){
              showToast("Hide failed.", "err");
            }
          });
          actions.appendChild(hideBtn);

          const copyBtn = document.createElement("button");
          copyBtn.type = "button";
          copyBtn.className = "btn-ghost icon-action";
          copyBtn.title = "Copy URL";
          copyBtn.innerHTML = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M16 1H6a2 2 0 0 0-2 2v12h2V3h10V1zm3 4H10a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H10V7h9v14z\"/></svg>";
          copyBtn.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try{
              await navigator.clipboard.writeText(item.url || "");
              showToast("Copied URL.", "ok");
            }catch(err){
              showToast("Copy failed.", "err");
            }
          });
          actions.appendChild(copyBtn);

          const del = document.createElement("button");
          del.type = "button";
          del.className = "btn-ghost btn-danger icon-action";
          const canDelete = hasScope("admin:web");
          del.title = canDelete && item.delete_url ? "Delete" : "Delete not available";
          del.innerHTML = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M6 7h12v2H6zm3 2h2v9H9zm4 0h2v9h-2zM8 5h8l-1-1h-6l-1 1z\"/></svg>";
          del.disabled = !(canDelete && item.delete_url);
          del.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            if (del.disabled) return;
            if (!confirm("Delete this image? This cannot be undone.")) return;
            try{
              const res = await fetch(item.delete_url, {method: "DELETE", headers: {"X-API-Key": apiKeyEl.value.trim()}});
              const data = await res.json().catch(() => ({}));
              if (!res.ok || data.ok === false){
                throw new Error(data.error || "Delete failed");
              }
              showToast("Image deleted.", "ok");
              await loadMediaLibrary();
            }catch(err){
              showToast(err.message, "err");
            }
          });
          actions.appendChild(del);

          card.appendChild(img);
          card.appendChild(titleText);
          card.appendChild(artist);
          card.appendChild(origin);
          card.appendChild(actions);

          if (isHidden){
            card.classList.add("hidden-item");
            const hiddenIndicator = document.createElement("div");
            hiddenIndicator.className = "hidden-indicator";
            hiddenIndicator.title = "Hidden from public views";
            hiddenIndicator.innerHTML = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M2 5l2-2 18 18-2 2-3.5-3.5A10.9 10.9 0 0 1 12 19c-5 0-9-4-10-7a12.5 12.5 0 0 1 5.4-5.8L2 5zm5.7 5.7A3.5 3.5 0 0 0 12 15a3.4 3.4 0 0 0 2-.6l-1.5-1.5a1.5 1.5 0 0 1-1.9-1.9L7.7 10.7zM12 7c1 0 2 .4 2.7 1l-1.4 1.4A1.5 1.5 0 0 0 12 8.5c-.2 0-.4 0-.6.1L9.6 7.2A6.4 6.4 0 0 1 12 7zm6.3 2.1A11 11 0 0 1 22 12c-1 3-5 7-10 7-1.2 0-2.4-.2-3.4-.6l1.6-1.6c.6.1 1.2.2 1.8.2 3.4 0 6.4-2.4 7.7-5-.6-1.2-1.6-2.5-3-3.6l1.3-1.4z\"/></svg>";
            card.appendChild(hiddenIndicator);
          }

          card.addEventListener("click", (ev) => {
            toggleMediaSelection(item, idx, {shift: ev.shiftKey, multi: ev.ctrlKey || ev.metaKey});
          });
          card.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter" || ev.key === " "){
              ev.preventDefault();
              toggleMediaSelection(item, idx, {multi: ev.ctrlKey || ev.metaKey});
            }
          });

          if (mediaSelected.has(key)){
            card.classList.add("selected");
          }
          grid.appendChild(card);
        });
        updateMediaSelectionUI();
      }

      function toggleMediaSelection(item, index, opts){
        const key = mediaKey(item);
        if (!key) return;
        const shift = opts && opts.shift;
        const toggleOnly = opts && opts.toggle;
        if (shift && mediaLastIndex !== null){
          const [start, end] = index > mediaLastIndex ? [mediaLastIndex, index] : [index, mediaLastIndex];
          for (let i = start; i <= end; i++){
            const target = mediaVisibleItems[i];
            if (!target) continue;
            mediaSelected.add(mediaKey(target));
          }
        }else{
          if (mediaSelected.has(key)){
            mediaSelected.delete(key);
          }else{
            mediaSelected.add(key);
          }
        }
        mediaLastIndex = index;
        currentMediaEdit = mediaSelected.size ? item : null;
        updateMediaSelectionUI();
      }

      function updateMediaSelectionUI(){
        const cards = document.querySelectorAll("#mediaLibraryGrid .preview-card.library-card");
        cards.forEach(card => {
          const key = card.dataset.key || "";
          const selected = mediaSelected.has(key);
          card.classList.toggle("selected", selected);
          const checkbox = card.querySelector("input[type=checkbox]");
          if (checkbox) checkbox.checked = selected;
        });
        if (mediaSelected.size === 0){
          currentMediaEdit = null;
        }else if (currentMediaEdit && !mediaSelected.has(mediaKey(currentMediaEdit))){
          currentMediaEdit = mediaLibraryItems.find(item => mediaSelected.has(mediaKey(item))) || null;
        }
        updateMediaBulkBar();
        updateMediaEditPanel();
      }

        function updateMediaBulkBar(){
          const bar = $("mediaBulkBar");
          if (!bar) return;
          const count = mediaSelected.size;
          $("mediaBulkCount").textContent = `${count} selected`;
          bar.classList.toggle("active", count > 0);
          const indicator = $("mediaSelectionIndicator");
          if (indicator){
            indicator.textContent = `${count} selected`;
          }
          const deleteBtn = $("mediaBulkDelete");
          if (deleteBtn){
            const canDelete = hasScope("admin:web");
            deleteBtn.disabled = !canDelete || count === 0;
            deleteBtn.title = canDelete ? "Delete selected" : "Delete requires admin access";
          }
        }

      function clearMediaSelection(){
        mediaSelected.clear();
        mediaLastIndex = null;
        currentMediaEdit = null;
        updateMediaSelectionUI();
      }

      function getSelectedMediaItems(){
        return mediaLibraryItems.filter(item => mediaSelected.has(mediaKey(item)));
      }

      async function bulkUpdateMedia(payload){
        const items = getSelectedMediaItems();
        if (!items.length) return;
        for (const item of items){
          const body = {
            filename: item.name || "",
            title: payload.title != null ? payload.title : (item.title || ""),
            artist_id: payload.artist_id != null ? payload.artist_id : (item.artist_id || ""),
            artist_name: payload.artist_name || item.artist_name || "",
            origin_type: payload.origin_type != null ? payload.origin_type : (item.origin_type || ""),
            origin_label: payload.origin_label != null ? payload.origin_label : (item.origin_label || "")
          };
          const res = await fetch("/api/gallery/media/update", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-API-Key": apiKeyEl.value.trim()
            },
            body: JSON.stringify(body)
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok === false){
            throw new Error(data.error || "Bulk update failed");
          }
        }
      }

      function setAuthRolesStatus(msg, kind){
        const el = $("authRolesStatus");
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setAuthTokensStatus(msg, kind){
        const el = $("authTokensStatus");
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setAuthTempStatus(msg, kind){
        const el = $("authTempStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setSystemConfigStatus(msg, kind){
        const el = $("systemConfigStatus");
        if (!el) return;
        el.textContent = msg || "Ready.";
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setInputValue(id, value){
        const el = $(id);
        if (!el) return;
        el.value = value === undefined || value === null ? "" : String(value);
      }

      function setNumberValue(id, value){
        const el = $(id);
        if (!el) return;
        el.value = value === undefined || value === null ? "" : String(value);
      }

      function parseBoolean(value){
        if (typeof value === "boolean") return value;
        if (value === null || value === undefined) return false;
        return String(value).toLowerCase() === "true";
      }

      function normalizeNumber(value){
        if (value === null || value === undefined) return null;
        const trimmed = String(value).trim();
        if (!trimmed) return null;
        const num = Number(trimmed);
        return Number.isFinite(num) ? num : null;
      }

      async function loadSystemConfig(){
        setSystemConfigStatus("Loading configuration...", "");
        try{
          const data = await jsonFetch("/admin/system-config", {method:"GET"});
          const configs = data.configs || {};
          const xiv = configs.xivauth || {};
          const openai = configs.openai || {};
          setInputValue("systemXivVerifyUrl", xiv.verify_url || xiv.verifyUrl || "");
          setInputValue("systemXivApiKey", xiv.api_key || "");
          setInputValue("systemXivDefaultUsername", xiv.default_username || "");
          setInputValue("systemXivClientId", xiv.client_id || xiv.oauth_client_id || "");
          setInputValue("systemXivClientSecret", xiv.client_secret || xiv.oauth_client_secret || "");
          setInputValue("systemXivAuthorizeUrl", xiv.authorize_url || xiv.oauth_authorize_url || "");
          setInputValue("systemXivTokenUrl", xiv.token_url || xiv.oauth_token_url || "");
          setInputValue("systemXivScope", xiv.scope || xiv.scopes || "");
          setInputValue("systemXivRedirectUrl", xiv.redirect_url || xiv.oauth_redirect_url || "");
          setInputValue("systemXivTokenHeader", xiv.token_header || "");
          setInputValue("systemXivTokenPrefix", xiv.token_prefix || "");
          setInputValue("systemXivApiKeyHeader", xiv.api_key_header || "");
          setInputValue("systemXivStateSecret", xiv.state_secret || "");
          setNumberValue("systemXivTimeout", normalizeNumber(xiv.timeout_seconds ?? xiv.timeout));
          setInputValue("systemOpenAIKey", openai.api_key || "");
          setInputValue("systemOpenAIModel", openai.openai_model || openai.model || "");
          setNumberValue("systemOpenAITemperature", normalizeNumber(openai.openai_temperature ?? openai.temperature));
          setNumberValue("systemOpenAITokens", normalizeNumber(openai.openai_max_output_tokens ?? openai.max_tokens));
          const priestToggle = $("systemOpenAIEnablePriest");
          if (priestToggle){
            priestToggle.checked = parseBoolean(openai.enable_priest_chat);
          }
          setSystemConfigStatus("Configuration loaded.", "ok");
        }catch(err){
          setSystemConfigStatus(err.message || "Unable to load configuration.", "err");
        }
      }

      async function saveSystemConfig(section){
        setSystemConfigStatus("Saving...", "");
        const payload = {name: section, data: {}};
        if (section === "xivauth"){
          const data = {
            verify_url: ($("systemXivVerifyUrl")?.value || "").trim(),
            api_key: ($("systemXivApiKey")?.value || "").trim(),
            default_username: ($("systemXivDefaultUsername")?.value || "").trim(),
            client_id: ($("systemXivClientId")?.value || "").trim(),
            client_secret: ($("systemXivClientSecret")?.value || "").trim(),
            authorize_url: ($("systemXivAuthorizeUrl")?.value || "").trim(),
            token_url: ($("systemXivTokenUrl")?.value || "").trim(),
            scope: ($("systemXivScope")?.value || "").trim(),
            redirect_url: ($("systemXivRedirectUrl")?.value || "").trim(),
            token_header: ($("systemXivTokenHeader")?.value || "").trim(),
            token_prefix: ($("systemXivTokenPrefix")?.value || "").trim(),
            api_key_header: ($("systemXivApiKeyHeader")?.value || "").trim(),
            state_secret: ($("systemXivStateSecret")?.value || "").trim(),
          };
          const timeout = normalizeNumber($("systemXivTimeout")?.value);
          if (timeout !== null){
            data.timeout_seconds = timeout;
          }
          payload.data = data;
        }else{
          const data = {
            api_key: ($("systemOpenAIKey")?.value || "").trim(),
            openai_model: ($("systemOpenAIModel")?.value || "").trim(),
            enable_priest_chat: $("systemOpenAIEnablePriest")?.checked || false,
          };
          const temperature = normalizeNumber($("systemOpenAITemperature")?.value);
          if (temperature !== null){
            data.openai_temperature = temperature;
          }
          const tokens = normalizeNumber($("systemOpenAITokens")?.value);
          if (tokens !== null){
            data.openai_max_output_tokens = tokens;
          }
          payload.data = data;
        }
        try{
          await jsonFetch("/admin/system-config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
          });
          setSystemConfigStatus("Saved.", "ok");
          await loadSystemConfig();
        }catch(err){
          setSystemConfigStatus(err.message || "Save failed.", "err");
        }
      }

      function computeElfminAccess(scopes, source){
        if (source === "api_key"){
          return true;
        }
        const set = new Set(Array.from(scopes || []).map(String));
        return set.has("*") || set.has("admin:web");
      }

      function applyElfminVisibility(){
        const isElfmin = !!authUserIsElfmin;
        const authRolesBtn = $("menuAuthRoles");
        const authKeysBtn = $("menuAuthKeys");
        const authTempBtn = $("menuAuthTemp");
        const deckDeleteBtn = $("taDeleteDeck");
        if (authRolesBtn){
          authRolesBtn.classList.toggle("hidden", !isElfmin);
        }
        if (authKeysBtn){
          authKeysBtn.classList.toggle("hidden", !isElfmin);
        }
        if (authTempBtn){
          authTempBtn.classList.toggle("hidden", !isElfmin);
        }
        if (deckDeleteBtn){
          deckDeleteBtn.classList.toggle("hidden", !isElfmin);
          deckDeleteBtn.disabled = !isElfmin;
        }
      }

      function applyScopeVisibility(){
        const canBingo = hasScope("bingo:admin");
        const canTarot = hasScope("tarot:admin");
        const canCardgames = hasScope("cardgames:admin") || canTarot;
        const canAdmin = hasScope("admin:web");
        const canMedia = canBingo || canTarot || canAdmin;
        const canGallery = canTarot || canAdmin;
        const bingoBtn = $("menuBingo");
        const contestsBtn = $("menuContests");
        const mediaBtn = $("menuMedia");
        const calendarBtn = $("menuCalendar");
        const tarotLinksBtn = $("menuTarotLinks");
        const cardgameBtn = $("menuCardgameSessions");
        const tarotDecksBtn = $("menuTarotDecks");
        const artistsBtn = $("menuArtists");
        const galleryBtn = $("menuGallery");
        const crapsBtn = $("menuCraps");
        const slotsBtn = $("menuSlots");
        if (bingoBtn) bingoBtn.classList.toggle("hidden", !canBingo);
        if (contestsBtn) contestsBtn.classList.toggle("hidden", !canAdmin);
        if (mediaBtn) mediaBtn.classList.toggle("hidden", !canMedia);
        if (calendarBtn) calendarBtn.classList.toggle("hidden", !canAdmin);
        if (tarotLinksBtn) tarotLinksBtn.classList.toggle("hidden", !canTarot);
        if (cardgameBtn) cardgameBtn.classList.toggle("hidden", !canCardgames);
        if (tarotDecksBtn) tarotDecksBtn.classList.toggle("hidden", !canTarot);
        if (crapsBtn) crapsBtn.classList.toggle("hidden", !canCardgames);
        if (slotsBtn) slotsBtn.classList.toggle("hidden", !canCardgames);
        if (artistsBtn) artistsBtn.classList.toggle("hidden", !canGallery);
        if (galleryBtn) galleryBtn.classList.toggle("hidden", !canGallery);
        const systemConfigBtn = $("menuSystemConfig");
        if (systemConfigBtn) systemConfigBtn.classList.toggle("hidden", !canAdmin);
        const dashboardAuthLink = $("dashboardXivAuthLink");
        if (dashboardAuthLink) dashboardAuthLink.classList.toggle("hidden", !canAdmin);
        const dashboardLogsWrap = $("dashboardLogsWrap");
        if (dashboardLogsWrap) dashboardLogsWrap.classList.toggle("hidden", !canAdmin);

        const saved = getSavedPanel();
        const blocked =
          (!canBingo && (saved === "bingo" || saved === "bingoSessions" || saved === "media")) ||
          (!canAdmin && (saved === "contests")) ||
          (!canTarot && (saved === "tarotLinks" || saved === "tarotDecks")) ||
          (!canCardgames && (saved === "cardgameSessions" || saved === "craps" || saved === "slots"));
        if (blocked){
          showPanel("dashboard");
        }
      }

      function renderAuthTempRoles(){
        const select = $("authTempRole");
        if (!select) return;
        const keys = Object.keys(authRoleScopes || {});
        select.innerHTML = "";
        if (!keys.length){
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "No role scopes configured";
          select.appendChild(opt);
          updateAuthTempScopesPreview("");
          return;
        }
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Select access profile";
        select.appendChild(empty);
        keys.forEach((id) => {
          const role = (authRolesCache || []).find(r => String(r.id) === String(id));
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = role ? `${role.name} (${id})` : id;
          select.appendChild(opt);
        });
        updateAuthTempScopesPreview(select.value || "");
      }

      function renderAuthPreviewRoles(){
        const select = $("authPreviewRole");
        if (!select) return;
        const keys = Object.keys(authRoleScopes || {});
        select.innerHTML = "";
        if (!keys.length){
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "No role scopes configured";
          select.appendChild(opt);
          updateAuthPreviewScopesPreview("");
          return;
        }
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "Select access profile";
        select.appendChild(empty);
        keys.forEach((id) => {
          const role = (authRolesCache || []).find(r => String(r.id) === String(id));
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = role ? `${role.name} (${id})` : id;
          select.appendChild(opt);
        });
        updateAuthPreviewScopesPreview(select.value || "");
      }

      function updateAuthPreviewScopesPreview(roleId){
        const preview = $("authPreviewScopesPreview");
        if (!preview) return;
        const scopes = (authRoleScopes && roleId) ? (authRoleScopes[roleId] || []) : [];
        if (!roleId){
          preview.textContent = "Scopes: none";
          return;
        }
        preview.textContent = scopes.length ? `Scopes: ${scopes.join(", ")}` : "Scopes: (from role profile)";
        const scopesEl = $("authPreviewScopes");
        if (scopesEl && !scopesEl.value.trim() && scopes.length){
          scopesEl.value = scopes.join(", ");
        }
      }

      function updateAuthTempScopesPreview(roleId){
        const preview = $("authTempScopesPreview");
        if (!preview) return;
        const scopes = (authRoleScopes && roleId) ? (authRoleScopes[roleId] || []) : [];
        if (!roleId){
          preview.textContent = "Scopes: none";
          return;
        }
        preview.textContent = scopes.length ? `Scopes: ${scopes.join(", ")}` : "Scopes: (from role profile)";
        const scopesEl = $("authTempScopes");
        if (scopesEl && !scopesEl.value.trim() && scopes.length){
          scopesEl.value = scopes.join(", ");
        }
      }

      function updateAuthRoleIdsField(){
        authRoleIds = new Set(Object.keys(authRoleScopes || {}));
        $("authRoleIds").value = Array.from(authRoleIds).join(", ");
      }

      function normalizeAuthRoleScopes(map){
        const normalized = {};
        Object.entries(map || {}).forEach(([roleId, scopes]) => {
          const id = String(roleId).trim();
          if (!id) return;
          let list = [];
          if (Array.isArray(scopes)){
            list = scopes.map(s => String(s).trim()).filter(Boolean);
          } else if (typeof scopes === "string"){
            list = scopes.split(",").map(s => s.trim()).filter(Boolean);
          }
          if (list.includes("*")) list = ["*"];
          if (list.length){
            normalized[id] = list;
          }
        });
        return normalized;
      }

      function renderAuthRolesList(roles){
        if (!roles.length){
          $("authRolesList").textContent = "No roles found.";
          updateAuthRoleIdsField();
          return;
        }
        const headerCells = authScopeOptions.map(scope => `<th>${scope.label}</th>`).join("");
        const rows = roles.map(role => {
          const roleId = String(role.id);
          const roleName = role.name || roleId;
          const scopes = new Set((authRoleScopes[roleId] || []).map(String));
          const cells = authScopeOptions.map(scope => {
            const checked = scopes.has(scope.id) ? "checked" : "";
            const disabled = scopes.has("*") && scope.id !== "*" ? "disabled" : "";
            return `<td class="role-scope-cell"><input type="checkbox" data-role="${roleId}" data-scope="${scope.id}" ${checked} ${disabled}></td>`;
          }).join("");
          return `<tr><td class="role-name">${roleName}</td>${cells}</tr>`;
        }).join("");
        $("authRolesList").innerHTML = `<table class="role-table"><thead><tr><th>Role</th>${headerCells}</tr></thead><tbody>${rows}</tbody></table>`;
        updateAuthRoleIdsField();
      }

      async function loadAuthRoles(){
        setAuthRolesStatus("Loading roles...", "");
        $("authRolesList").textContent = "Loading...";
        try{
          const current = await jsonFetch("/api/auth/roles", {method:"GET"});
          authRoleScopes = normalizeAuthRoleScopes(current.role_scopes || {});
          if (!current.role_scopes_configured && !Object.keys(authRoleScopes).length && (current.role_ids || []).length){
            const legacy = {};
            (current.role_ids || []).forEach(id => {
              legacy[String(id)] = ["*"];
            });
            authRoleScopes = legacy;
          }
          const res = await jsonFetch("/discord/roles", {method:"GET"});
          const roles = res.roles || [];
          authRolesCache = roles;
          renderAuthRolesList(roles);
          renderAuthTempRoles();
          renderAuthPreviewRoles();
          setAuthRolesStatus("Ready.", "ok");
        }catch(err){
          setAuthRolesStatus(err.message, "err");
          $("authRolesList").textContent = "Failed to load roles.";
        }
      }

      function formatAuthTokenDuration(seconds){
        const total = Math.max(0, Number(seconds) || 0);
        if (!total) return "Expired";
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const secs = total % 60;
        if (hours > 0){
          return `${hours}h ${minutes}m`;
        }
        if (minutes > 0){
          return `${minutes}m ${secs}s`;
        }
        return `${secs}s`;
      }

      function formatAuthTokenExpiry(token){
        const duration = formatAuthTokenDuration(token.expires_in);
        if (!token.expires_at){
          return duration;
        }
        const stamp = new Date(Number(token.expires_at) * 1000);
        return `${duration} (${stamp.toLocaleString()})`;
      }

      function renderAuthTokensList(tokens){
        const list = $("authTokensList");
        list.innerHTML = "";
        if (!tokens || !tokens.length){
          list.textContent = "No keys loaded.";
          return;
        }
        const table = document.createElement("table");
        table.className = "role-table";
        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");
        ["User", "Token", "Scopes", "Expires", "Actions"].forEach(label => {
          const th = document.createElement("th");
          th.textContent = label;
          headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);
        const tbody = document.createElement("tbody");
        tokens.forEach(token => {
          const tr = document.createElement("tr");
          const userCell = document.createElement("td");
          userCell.textContent = token.user_name || token.user_id || "Unknown";
          const tokenCell = document.createElement("td");
          const code = document.createElement("code");
          code.className = "token-code";
          code.textContent = token.token || "";
          tokenCell.appendChild(code);
          const tokenMeta = document.createElement("div");
          tokenMeta.className = "token-actions";
          const copyBtn = document.createElement("button");
          copyBtn.className = "btn-ghost";
          copyBtn.textContent = "Copy";
          copyBtn.addEventListener("click", async () => {
            try{
              await navigator.clipboard.writeText(token.token || "");
              setAuthTokensStatus("Copied token.", "ok");
            }catch(err){
              setAuthTokensStatus("Copy failed.", "err");
            }
          });
          tokenMeta.appendChild(copyBtn);
          tokenCell.appendChild(tokenMeta);
          const scopeCell = document.createElement("td");
          scopeCell.textContent = (token.scopes || []).join(", ");
          const expiresCell = document.createElement("td");
          expiresCell.textContent = formatAuthTokenExpiry(token);
          const actionsCell = document.createElement("td");
          const deleteBtn = document.createElement("button");
          deleteBtn.className = "btn-ghost";
          deleteBtn.textContent = "Delete";
          deleteBtn.addEventListener("click", async () => {
            if (!confirm("Delete this auth key? This will revoke access.")){
              return;
            }
            try{
              const res = await fetch("/api/auth/tokens/" + encodeURIComponent(token.token || ""), {
                method: "DELETE",
                headers: {"X-API-Key": apiKeyEl.value.trim()}
              });
              const data = await res.json().catch(() => ({}));
              if (!res.ok || data.ok === false){
                throw new Error(data.error || "Delete failed");
              }
              await loadAuthTokens();
              setAuthTokensStatus("Auth key deleted.", "ok");
            }catch(err){
              setAuthTokensStatus(err.message, "err");
            }
          });
          actionsCell.appendChild(deleteBtn);
          tr.appendChild(userCell);
          tr.appendChild(tokenCell);
          tr.appendChild(scopeCell);
          tr.appendChild(expiresCell);
          tr.appendChild(actionsCell);
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        list.appendChild(table);
      }

      async function loadAuthTokens(){
        setAuthTokensStatus("Loading keys...", "");
        $("authTokensList").textContent = "Loading...";
        try{
          const res = await fetch("/api/auth/tokens", {headers: {"X-API-Key": apiKeyEl.value.trim()}});
          if (res.status === 401){
            handleUnauthorized();
            throw new Error("Unauthorized");
          }
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
          authTokensCache = data.tokens || [];
          renderAuthTokensList(authTokensCache);
          setAuthTokensStatus("Ready.", "ok");
        }catch(err){
          setAuthTokensStatus(err.message, "err");
          $("authTokensList").textContent = "Failed to load keys.";
        }
      }

      function renderCalendarPreview(){
        const preview = `${emoji} | ${name}`;
        preview.innerHTML = "";
        if (!calendarSelected.image){
          preview.textContent = "No image selected.";
          return;
        }
        const img = document.createElement("img");
        img.src = calendarSelected.image;
        img.alt = calendarSelected.title || "calendar";
        preview.appendChild(img);
      }

      function applyCalendarSelection(entry){
        calendarSelected = {
          month: entry.month,
          image: entry.image || "",
          title: entry.title || "",
          artist_id: (entry.artist && entry.artist.artist_id) || null,
          artist_name: (entry.artist && entry.artist.name) || "Forest"
        };
        $("calendarTitle").value = calendarSelected.title;
        $("calendarArtist").textContent = calendarSelected.artist_name || "Forest";
        renderCalendarPreview();
      }

      function populateCalendarMonths(){
        const select = $("calendarMonth");
        select.innerHTML = "";
        calendarData.forEach(entry => {
          const opt = document.createElement("option");
          opt.value = entry.month;
          opt.textContent = entry.month_name || `Month ${entry.month}`;
          select.appendChild(opt);
        });
        const current = calendarSelected.month || 1;
        select.value = String(current);
      }

      async function loadCalendarAdmin(){
        setCalendarStatus("Loading...", "");
        try{
          const res = await fetch("/api/gallery/calendar", {headers: {"X-API-Key": apiKeyEl.value.trim()}});
          if (res.status === 401){
            handleUnauthorized();
            throw new Error("Unauthorized");
          }
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
          calendarData = data.months || [];
          if (!calendarData.length){
            calendarData = [];
            setCalendarStatus("No calendar data.", "err");
            return;
          }
          populateCalendarMonths();
          const entry = calendarData.find(e => e.month === (calendarSelected.month || 1)) || calendarData[0];
          applyCalendarSelection(entry);
          setCalendarStatus("Ready.", "ok");
        }catch(err){
          setCalendarStatus(err.message, "err");
        }
      }

      function getGameId(){
        return ($("bGameId").dataset.gameId || "").trim();
      }

      function setGameId(id){
        const gid = (id || "").trim();
        $("bGameId").dataset.gameId = gid;
        $("bGameId").textContent = gid ? gid : "No game selected.";
      }

      function setStatus(msg, kind){
        const textEl = $("statusText");
        const timeEl = $("statusTime");
        if (textEl){
          textEl.textContent = msg;
        }else{
          statusEl.textContent = msg;
        }
        if (timeEl){
          const now = new Date();
          timeEl.textContent = now.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
        }
        statusEl.className = "status-bar status" + (kind ? " " + kind : "");
      }

      function getQueryParam(name){
        try{
          const params = new URLSearchParams(window.location.search);
          return params.get(name);
        }catch(err){
          return null;
        }
      }

      function removeTokenQueryParams(){
        if (!window.history || !window.history.replaceState) return;
        try{
          const url = new URL(window.location.href);
          ["token", "auth_token", "api_key"].forEach((key) => url.searchParams.delete(key));
          const clean = url.pathname + (url.search ? url.search : "");
          window.history.replaceState(null, "", clean);
        }catch(err){}
      }

      function setBingoStatus(msg, kind){
        const el = $("bingoStatus");
        if (el){
          el.textContent = msg;
          el.className = "status" + (kind ? " " + kind : "");
        }
        setStatus(msg, kind);
      }

      let bingoHistory = [];
      function setBingoLastAction(msg){
        const el = $("bLastAction");
        if (!el) return;
        el.textContent = msg ? `Last action: ${msg}` : "Last action: -";
      }

      function addBingoHistory(msg){
        if (!msg) return;
        const time = new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
        bingoHistory.unshift(`${time} - ${msg}`);
        bingoHistory = bingoHistory.slice(0, 5);
        const el = $("bHistory");
        if (!el) return;
        if (!bingoHistory.length){
          el.innerHTML = "<div class=\"muted\">No history yet.</div>";
          return;
        }
        el.innerHTML = bingoHistory.map(entry => `<div class="bingo-history-item">${entry}</div>`).join("");
      }

      function setBingoPrimaryAction(targetId){
        const ids = ["bStart", "bRoll", "bAdvanceStage"];
        ids.forEach(id => {
          const btn = $(id);
          if (!btn) return;
          const isPrimary = id === targetId;
          btn.classList.toggle("btn-primary", isPrimary);
          btn.classList.toggle("btn-ghost", !isPrimary);
        });
      }

      function updateBingoBuyState(game, called){
        const btn = $("bBuy");
        if (!btn) return;
        const ownerEl = $("bOwner");
        const qtyEl = $("bQty");
        const ownerOk = !!(ownerEl && ownerEl.value.trim());
        const qty = Number(qtyEl ? qtyEl.value : 1);
        const qtyOk = Number.isFinite(qty) && qty >= 1;
        const canBuy = !!(game && game.game_id && game.active !== false && !game.started && (!called || called.length === 0));
        btn.disabled = !(ownerOk && qtyOk && canBuy);
      }

      function updateSeedPotState(game){
        const btn = $("bSeedPotApply");
        if (!btn) return;
        const amtEl = $("bSeedPotAmount");
        const amount = Number(amtEl ? amtEl.value : 0);
        const ok = Number.isFinite(amount) && amount > 0 && game && game.game_id && game.active !== false;
        btn.disabled = !ok;
      }

      function applyTheme(color){
        const panel = $("bingoPanel");
        if (!panel){
          return;
        }
        if (!color){
          panel.style.removeProperty("--accent");
          panel.style.removeProperty("--accent-2");
          panel.style.removeProperty("--line");
          panel.style.removeProperty("--panel");
          return;
        }
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
        panel.style.setProperty("--accent", light);
        panel.style.setProperty("--accent-2", `#${hex}`);
        panel.style.setProperty("--line", dark);
        panel.style.setProperty("--panel", darker);
      }

      function loadSettings(){
        overlayLog("loadSettings");
        if (apiKeyEl){
          const saved = storage.getItem("bt_api_key") || "";
          const session = window.sessionStorage ? (window.sessionStorage.getItem("bt_api_key") || "") : "";
          apiKeyEl.value = saved || session;
        }
        if (overlayToggle){
          overlayToggle.checked = storage.getItem("bt_overlay") === "1";
          if (overlayToggle.checked) document.body.classList.add("overlay");
        }
        if (overlayToggleBtn && overlayToggle){
          overlayToggleBtn.classList.toggle("active", overlayToggle.checked);
        }
      }

      function applyTokenFromUrl(){
        const candidate = getQueryParam("token") || getQueryParam("auth_token") || getQueryParam("api_key");
        if (!candidate) return;
        overlayLog("applyTokenFromUrl", candidate);
        storage.setItem("bt_api_key", candidate);
        if (window.sessionStorage){
          window.sessionStorage.setItem("bt_api_key", candidate);
        }
        if (apiKeyEl){
          apiKeyEl.value = candidate;
        }
        removeTokenQueryParams();
      }

      function applyTempTokenFromUrl(){
        overlayLog("applyTempTokenFromUrl", window.location.search);
        try{
          const params = new URLSearchParams(window.location.search || "");
          const token = params.get("temp_token");
          if (!token) return;
          storage.setItem("bt_api_key", token);
          if (window.sessionStorage){
            window.sessionStorage.setItem("bt_api_key", token);
          }
          if (apiKeyEl){
            apiKeyEl.value = token;
          }
          params.delete("temp_token");
          const query = params.toString();
          const next = window.location.pathname + (query ? "?" + query : "") + window.location.hash;
          window.history.replaceState(null, "", next);
        }catch(err){}
      }

      function saveSettings(){
        if (apiKeyEl){
          storage.setItem("bt_api_key", apiKeyEl.value.trim());
          if (window.sessionStorage){
            window.sessionStorage.setItem("bt_api_key", apiKeyEl.value.trim());
          }
        }
        storage.setItem("bt_overlay", overlayToggle.checked ? "1" : "0");
      }

      function apiFetch(path, opts, withKey = true){
        const base = getBase();
        // Ensure path starts with / for absolute URL
        const cleanPath = path.startsWith('/') ? path : `/${path}`;
        const url = new URL(cleanPath, base).toString();
        console.debug("apiFetch:", {path, cleanPath, base, url});
        const options = opts || {};
        options.headers = options.headers || {};
        if (withKey){
          const key = (apiKeyEl && apiKeyEl.value.trim()) ||
            storage.getItem("bt_api_key") ||
            (window.sessionStorage ? (window.sessionStorage.getItem("bt_api_key") || "") : "");
          if (key){
            options.headers["X-API-Key"] = key;
            if (!options.headers["Authorization"]){
              options.headers["Authorization"] = `Bearer ${key}`;
            }
          }
        }
        return fetch(url, options);
      }

      async function jsonFetch(path, opts, withKey = true){
        const res = await apiFetch(path, opts, withKey);
        if (res.status === 401){
          handleUnauthorized();
          throw new Error("Unauthorized");
        }
        const contentType = (res.headers.get("content-type") || "").toLowerCase();
        const text = await res.text();
        
        // Check for non-JSON responses (likely HTML from proxy/gateway)
        if (!contentType.includes("application/json") && !text.trim().startsWith("{") && !text.trim().startsWith("[")){
          console.error("Non-JSON response:", {status: res.status, contentType, text: text.substring(0, 200)});
          throw new Error("Unexpected response from API. Check gateway/proxy routing.");
        }
        
        let data = {};
        try{
          data = text ? JSON.parse(text) : {};
        }catch(err){
          console.error("JSON parse error:", err, "Text:", text.substring(0, 200));
          data = {};
        }
        
        if (!res.ok){
          throw new Error((data && data.error) || "Request failed");
        }
        
        return data;
      }

      function handleUnauthorized(){
        // Do not wipe stored tokens; just surface the error.
        const msg = "Unauthorized. Check API key or scopes.";
        if (loginStatusEl){
          loginStatusEl.textContent = msg;
          loginStatusEl.className = "status err";
        }
        if (statusEl){
          statusEl.textContent = msg;
          statusEl.className = "status-bar status err";
        }
        showToast(msg, "err");
      }

      function clearAuthSession(message, kind){
        if (apiKeyEl){
          apiKeyEl.value = "";
        }
        try{
          storage.removeItem("bt_api_key");
          storage.setItem("bt_overlay", "0");
          if (window.sessionStorage){
            window.sessionStorage.removeItem("bt_api_key");
          }
        }catch(err){}
        const appView = document.getElementById("appView");
        const loginView = document.getElementById("loginView");
        if (appView) appView.classList.add("hidden");
        if (loginView) loginView.classList.remove("hidden");
        if (loginStatusEl){
          loginStatusEl.textContent = message || "Logged out.";
          loginStatusEl.className = "status" + (kind ? " " + kind : "");
        }
        if (overlayToggle){
          overlayToggle.checked = false;
        }
        document.body.classList.remove("overlay");
        if (overlayToggleBtn){
          overlayToggleBtn.classList.remove("active");
        }
        const brandUser = $("brandUser");
        const brandUserName = $("brandUserName");
        const brandUserIcon = $("brandUserIcon");
        const brandUserFallback = $("brandUserFallback");
        if (brandUser){
          if (brandUserName){
            brandUserName.textContent = "";
          }
          if (brandUserIcon){
            brandUserIcon.src = "";
            brandUserIcon.classList.add("hidden");
          }
          if (brandUserFallback){
            brandUserFallback.classList.remove("hidden");
          }
          brandUser.classList.add("hidden");
        }
      }

      async function loadAuthUser(){
        const brandUser = $("brandUser");
        const brandUserName = $("brandUserName");
        const brandUserIcon = $("brandUserIcon");
        const brandUserFallback = $("brandUserFallback");
        const brandUserVenue = $("brandUserVenue");
        if (!brandUser || !brandUserName || !brandUserIcon || !brandUserFallback){
          return;
        }
        try{
          const data = await jsonFetch("/api/auth/me", {method:"GET"}, true);
          const name = data.user_name || data.user_id || "";
          const icon = data.user_icon || "";
          const userId = data.user_id || "";
          const rawScopes = data.scopes || data.scope || data.permissions || [];
          const scopeList = Array.isArray(rawScopes)
            ? rawScopes.map(String)
            : String(rawScopes || "").split(",").map(s => s.trim()).filter(Boolean);
          authUserScopes = new Set(scopeList);
          authUserIsElfmin = computeElfminAccess(authUserScopes, data.source);
          applyElfminVisibility();
          applyScopeVisibility();
          const createdBy = $("bCreatedBy");
          if (createdBy){
            createdBy.value = userId ? String(userId) : "";
          }
          updateBingoCreatePayload();
          if (name){
            brandUserName.textContent = name;
            brandUser.classList.remove("hidden");
            if (icon){
              brandUserIcon.src = icon;
              brandUserIcon.classList.remove("hidden");
              brandUserFallback.classList.add("hidden");
            }else{
              brandUserIcon.src = "";
              brandUserIcon.classList.add("hidden");
              brandUserFallback.classList.remove("hidden");
            }
          }else{
            brandUserName.textContent = "";
            brandUser.classList.add("hidden");
          }
          if (brandUserVenue){
            brandUserVenue.textContent = "";
          }
          if (userId){
            await ensureAdminVenue(data.venue || null);
          }else{
            setBrandVenue(null);
          }
        }catch(err){
          brandUserName.textContent = "";
          brandUserIcon.src = "";
          brandUserIcon.classList.add("hidden");
          brandUserFallback.classList.remove("hidden");
          brandUser.classList.add("hidden");
          if (brandUserVenue){
            brandUserVenue.textContent = "";
          }
          adminVenueId = null;
          adminVenueName = "";
          adminVenueDeckId = null;
          adminVenueCurrency = null;
          adminVenueGameBackgrounds = {};
          authUserScopes = new Set();
          authUserIsElfmin = false;
          applyElfminVisibility();
          applyScopeVisibility();
          const createdBy = $("bCreatedBy");
          if (createdBy){
            createdBy.value = "";
          }
          updateBingoCreatePayload();
          clearAuthSession("Auth failed. Check your API key.", "err");
        }
      }

      function setBrandVenue(membership){
        const brandUserVenue = $("brandUserVenue");
        const name = membership ? (membership.name || membership.venue_name || "") : "";
        if (brandUserVenue){
          brandUserVenue.textContent = name || "";
        }
        adminVenueId = membership && membership.venue_id ? Number(membership.venue_id) : null;
        adminVenueName = name || "";
        adminVenueDeckId = membership && membership.deck_id ? String(membership.deck_id) : null;
        adminVenueCurrency = membership && membership.currency_name ? String(membership.currency_name) : null;
        adminVenueGameBackgrounds = (membership && membership.metadata && membership.metadata.game_backgrounds) ? membership.metadata.game_backgrounds : {};
      }

      async function loadAdminVenues(){
        const select = $("adminVenueSelect");
        if (!select) return [];
        select.innerHTML = `<option value="">Loading...</option>`;
        try{
          const resp = await jsonFetch("/admin/venues/list", {method:"GET"}, true);
          const venues = resp.venues || [];
          select.innerHTML = `<option value="">Select a venue</option>`;
          venues.forEach((v) => {
            const opt = document.createElement("option");
            opt.value = String(v.id ?? v.venue_id ?? "");
            opt.textContent = v.name || `Venue ${opt.value}`;
            select.appendChild(opt);
          });
          return venues;
        }catch(err){
          select.innerHTML = `<option value="">No venues available</option>`;
          return [];
        }
      }

      async function ensureAdminVenue(initialMembership){
        const modal = $("adminVenueModal");
        if (!modal) return;
        let membership = initialMembership || null;
        if (!membership){
          try{
            const resp = await jsonFetch("/admin/venue/me", {method:"GET"}, true);
            membership = resp.membership || null;
          }catch(err){
            membership = null;
          }
        }
        if (membership && membership.venue_id){
          setBrandVenue(membership);
          modal.classList.remove("show");
          return;
        }
        await loadAdminVenues();
        setBrandVenue(null);
        modal.classList.add("show");
        setStatusText("adminVenueStatus", "Pick a venue to continue.", "");
      }

      async function initAuthenticatedSession(){
        await loadAuthUser();
        applyScopeVisibility();
        const contestCategoryStatus = $("contestCategoryStatus");
        if (contestCategoryStatus){
          contestCategoryStatus.textContent = CONTEST_CATEGORY_ID;
        }
        if ($("contestChannelName") && !$("contestChannelName").value.trim()){
          $("contestChannelName").value = "elfoween";
        }
        updateContestChannelPreview();
        const saved = getSavedPanel();
        const canBingo = hasScope("bingo:admin");
        const canTarot = hasScope("tarot:admin");
        const canCardgames = hasScope("cardgames:admin") || canTarot;
        const canAdmin = hasScope("admin:web");
        const allowedPanels = new Set(["dashboard"]);
        if (canBingo){
          allowedPanels.add("bingo");
          allowedPanels.add("bingoSessions");
          allowedPanels.add("media");
        }
        if (canAdmin){
          allowedPanels.add("contests");
        }
        if (canTarot){
          allowedPanels.add("tarotLinks");
          allowedPanels.add("tarotDecks");
        }
        if (canCardgames){
          allowedPanels.add("cardgameSessions");
          allowedPanels.add("craps");
          allowedPanels.add("slots");
        }
        let nextPanel = saved || (canBingo ? "bingoSessions" : "dashboard");
        if (nextPanel === "bingo" && !getGameId()){
          nextPanel = "bingoSessions";
        }
        if (!allowedPanels.has(nextPanel)){
          nextPanel = "dashboard";
        }
        if (!getSeenDashboard()){
          showPanelOnce(canBingo ? "bingoSessions" : "dashboard");
          setSeenDashboard();
        } else {
          showPanel(nextPanel);
        }
        if (hasScope("bingo:admin")){
          loadGamesMenu();
          ensureBingoPolling();
        }
        if (hasScope("tarot:admin")){
          loadTarotDeckList();
          loadTarotSessionDecks();
          loadTarotSessions();
          loadTarotNumbers();
          loadTarotArtists();
        }
      }

      function showList(el, data){
        if (data && Array.isArray(data.cards)){
          if (!data.cards.length){
            el.textContent = "No cards loaded.";
            if (el.id === "taDeckList"){
              window.taDeckData = data;
              const deckLabel = (data.deck && (data.deck.name || data.deck.deck_id)) || "Deck";
              setTarotStatus(`Deck loaded: ${deckLabel} (0 cards)`, "ok");
              taUpdateContext(null);
              taDirty = false;
            }
            return;
          }
          const deckLabel = (data.deck && (data.deck.name || data.deck.deck_id)) || "";
          const header = deckLabel ? `<div class="list-header">Deck: ${deckLabel}</div>` : "";
          const items = data.cards.map(c => {
            const name = c.name || c.card_id || "Untitled";
            const id = c.card_id ? ` (${c.card_id})` : "";
            const suit = c.suit || "";
            const suitLower = suit.toLowerCase();
            const suitMap = {
              wands: "Clubs",
              cups: "Hearts",
              swords: "Spades",
              pentacles: "Diamonds",
              clubs: "Clubs",
              hearts: "Hearts",
              spades: "Spades",
              diamonds: "Diamonds"
            };
            const playingSuit = suitLower === "major" ? "" : (suitMap[suitLower] || "");
            const playingLabel = playingSuit && playingSuit.toLowerCase() !== suitLower ? playingSuit : "";
            const suitMeta = suit || playingLabel
              ? `<div class="muted">${suit || "-"}${playingLabel ? ` - ${playingLabel}` : ""}</div>`
              : "";
            return `<div class="list-card clickable" data-card-id="${c.card_id || ""}"><strong>${name}</strong><span class="muted">${id}</span>${suitMeta}</div>`;
          }).join("");
          el.innerHTML = header + items;
          if (el.id === "taDeckList"){
            window.taDeckData = data;
            taSyncCardSelection();
            const deckName = deckLabel || (data.deck && data.deck.deck_id) || "Deck";
            setTarotStatus(`Deck loaded: ${deckName} (${data.cards.length} cards)`, "ok");
            taUpdateContext(null);
            taDirty = false;
          }
          return;
        }
        el.textContent = JSON.stringify(data, null, 2);
      }

        function renderBingoState(data){
          const game = (data && data.game) || {};
          currentGame = game;
          applyTheme(game.theme_color || null);
          const gid = getGameId();
          if (gid !== activeGameId){
            activeGameId = gid;
            lastCalledCount = 0;
            lastCalloutNumber = null;
            bingoHistory = [];
            const historyEl = $("bHistory");
            if (historyEl){
              historyEl.innerHTML = "<div class=\"muted\">No history yet.</div>";
            }
            setBingoLastAction("");
          }
        $("bTitleVal").textContent = game.title || "No title";
        $("bHeaderVal").textContent = game.header_text || game.header || "No header";
        $("bStageVal").textContent = game.stage || "No stage";
        $("bPotVal").textContent = (game.pot != null ? `${formatGil(game.pot)} ${game.currency || ""}` : "No pot");
        const announceToggle = $("bAnnounceToggle");
        if (announceToggle){
          announceToggle.checked = !!game.announce_calls;
        }
        const announceBadge = $("bAnnounceBadge");
        if (announceBadge){
          announceBadge.textContent = announceToggle && announceToggle.checked ? "On" : "Off";
          announceBadge.className = "status-badge" + (announceToggle && announceToggle.checked ? " good" : "");
        }
        const statusBadge = $("bGameStatus");
          if (statusBadge){
            let label = "No game";
            let cls = "status-badge";
            if (game && game.game_id){
              if (game.active === false){
                label = "Finished";
                cls += " bad";
              } else if (game.started){
                label = "Running";
                cls += " good";
              } else {
                label = "Waiting to start";
                cls += " warn";
              }
            }
            statusBadge.textContent = label;
            statusBadge.className = cls;
          }
          const hasPendingClaims = Array.isArray(game.claims)
            && game.claims.some(c => c && c.pending);
          const statusText = $("bGameStatusText");
          const statusMeta = $("bGameStatusMeta");
          let stateKey = "waiting";
          let stateLabel = "Waiting to Start";
          if (!game || !game.game_id){
            stateKey = "waiting";
            stateLabel = "Waiting to Start";
          } else if (game.active === false){
            stateKey = "finished";
            stateLabel = "Finished";
          } else if (hasPendingClaims){
            stateKey = "stage";
            stateLabel = "Stage Complete";
          } else if (game.started){
            stateKey = "running";
            stateLabel = "Running";
          }
          if (statusText){
            statusText.textContent = stateLabel;
            statusText.className = `bingo-status-label status-${stateKey}`;
          }
          if (statusMeta){
            if (game && game.game_id){
              statusMeta.textContent = `${game.title || "Untitled"} - Stage: ${game.stage || "single"}`;
            } else {
              statusMeta.textContent = "No game selected.";
            }
          }
          if (stateKey === "waiting"){
            setBingoPrimaryAction("bStart");
          } else if (stateKey === "running"){
            setBingoPrimaryAction("bRoll");
          } else if (stateKey === "stage"){
            setBingoPrimaryAction("bAdvanceStage");
          } else {
            setBingoPrimaryAction("");
          }
        const contextPath = $("bContextPath");
        const contextMeta = $("bContextMeta");
        const contextTitle = $("bContextTitle");
        if (contextPath){
          const label = game.title || "No game selected";
          contextPath.textContent = `Bingo / Manager / ${label}`;
        }
        if (contextMeta){
          contextMeta.textContent = game.game_id ? `Managing ${game.game_id}` : "Pick a game to manage.";
        }
        if (contextTitle){
          contextTitle.textContent = game.game_id ? `${game.title || "Untitled"} (${game.game_id})` : "";
        }
          const called = Array.isArray(game.called) ? game.called : [];
          $("bCalled").textContent = called.length ? ("Called numbers: " + called.join(", ")) : "No numbers called yet.";
          updateBingoBuyState(game, called);
          updateSeedPotState(game);
          const startBtn = $("bStart");
          if (startBtn){
            startBtn.disabled = !(game.game_id && game.active !== false && !game.started);
          }
        const rollBtn = $("bRoll");
        if (rollBtn){
          rollBtn.disabled = !(game.active !== false && game.started);
        }
        const refreshBtn = $("bRefresh");
        if (refreshBtn){
          refreshBtn.disabled = !game.game_id;
        }
          const closeBtn = $("bCloseGame");
          if (closeBtn){
            closeBtn.disabled = !game.game_id;
          }
          const advanceBtn = $("bAdvanceStage");
          if (advanceBtn){
            advanceBtn.disabled = !game.game_id || game.active === false;
          }
          const viewBtn = $("bViewOwner");
          if (viewBtn){
            viewBtn.disabled = !game.game_id;
          }
        renderCalledGrid(called);
        const bgPath = game.background ? new URL(game.background, getBase()).toString() : "";
        const cardWrap = $("bCard");
        cardWrap.style.backgroundImage = bgPath ? `url('${bgPath}')` : "";
          const last = game.last_called != null ? game.last_called : (called.length ? called[called.length - 1] : null);
          if (last != null && last !== lastCalloutNumber){
            showCallout(`Called ${last}`);
            lastCalloutNumber = last;
            setBingoStatus(`Number called: ${last}`, "ok");
            setBingoLastAction(`Called ${last}`);
            addBingoHistory(`Called ${last}`);
          }
          if (!game.game_id){
            setBingoStatus("No game selected.", "alert");
          }
          lastCalledCount = called.length;
          renderClaims(game);
        }

      function renderClaims(game){
        const el = $("bClaims");
        if (!el) return;
        const claims = (game && Array.isArray(game.claims)) ? game.claims : [];
        if (!claims.length){
          el.innerHTML = "<div class=\"muted\">No claims yet.</div>";
          return;
        }
        el.innerHTML = "";
        claims.slice().reverse().forEach(c => {
          const row = document.createElement("div");
          row.style.padding = "8px 6px";
          row.style.borderBottom = "1px solid rgba(255,255,255,0.06)";
          const status = c.pending ? "pending" : (c.denied ? "denied" : "approved");
          const label = `${c.owner_name || "Unknown"} - ${c.card_id || ""} - ${c.stage || ""} - ${status}`;
          const wrap = document.createElement("div");
          wrap.style.display = "flex";
          wrap.style.alignItems = "center";
          wrap.style.justifyContent = "space-between";
          wrap.style.gap = "10px";
          const text = document.createElement("div");
          text.textContent = label;
          wrap.appendChild(text);
          if (c.pending){
            const btnWrap = document.createElement("div");
            btnWrap.style.display = "flex";
            btnWrap.style.gap = "8px";
            const btn = document.createElement("button");
            btn.textContent = "Confirm + Advance";
            btn.className = "btn-primary";
            btn.style.maxWidth = "160px";
              btn.onclick = async () => {
                try{
                  await jsonFetch("/bingo/claim-approve", {
                    method:"POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({game_id: game.game_id, card_id: c.card_id})
                  });
                  const adv = await jsonFetch("/bingo/advance-stage", {
                    method:"POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({game_id: game.game_id})
                  });
                  setBingoStatus(adv.ended ? "Claim approved. Game ended." : "Claim approved. Stage advanced.", "ok");
                  addBingoHistory(adv.ended ? "Claim approved - game ended" : "Claim approved - stage advanced");
                  setBingoLastAction("Claim approved");
                  await refreshBingo();
                }catch(err){
                  setBingoStatus(err.message, "err");
                }
              };
            const deny = document.createElement("button");
            deny.textContent = "Deny";
            deny.className = "btn-ghost";
            deny.style.maxWidth = "90px";
              deny.onclick = async () => {
                try{
                  await jsonFetch("/bingo/claim-deny", {
                    method:"POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({game_id: game.game_id, card_id: c.card_id})
                  });
                  setBingoStatus("Claim denied.", "ok");
                  addBingoHistory("Claim denied");
                  setBingoLastAction("Claim denied");
                  await refreshBingo();
                }catch(err){
                  setBingoStatus(err.message, "err");
                }
              };
            btnWrap.appendChild(btn);
            btnWrap.appendChild(deny);
            wrap.appendChild(btnWrap);
          }
          row.appendChild(wrap);
          el.appendChild(row);
        });
      }

      function formatGil(value){
        const raw = Number(value);
        if (!Number.isFinite(raw)) return String(value ?? "");
        return raw.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
      }

      function renderCard(card, called, header){
        currentCard = card;
        const headerEl = $("bCardHeader");
        const gridEl = $("bCardGrid");
        headerEl.innerHTML = "";
        gridEl.innerHTML = "";
        const letters = (header || "BING").slice(0,4).split("");
        while (letters.length < 4) letters.push(" ");
        letters.forEach(l => {
          const h = document.createElement("div");
          h.textContent = l;
          headerEl.appendChild(h);
        });
        if (!card || !Array.isArray(card.numbers)){
          gridEl.innerHTML = "<div style='grid-column:1/-1;color:var(--muted)'>No card loaded.</div>";
          return;
        }
        const calledSet = new Set(Array.isArray(called) ? called : []);
        const nums = card.numbers || [];
        const marks = card.marks || [];
        for (let r = 0; r < nums.length; r++){
          for (let c = 0; c < nums[r].length; c++){
            const cell = document.createElement("div");
            cell.className = "bingo-cell";
            const value = nums[r][c];
            const marked = (marks[r] && marks[r][c]) || calledSet.has(value);
            if (marked) cell.classList.add("marked");
            cell.textContent = value;
            gridEl.appendChild(cell);
          }
        }
      }

      function renderCalledGrid(called){
        const grid = $("bCalledGrid");
        grid.innerHTML = "";
        const calledSet = new Set(Array.isArray(called) ? called : []);
        if (!calledSet.size){
          const empty = document.createElement("div");
          empty.className = "bingo-called-empty";
          empty.textContent = "No numbers have been called.";
          grid.appendChild(empty);
          return;
        }
        const last = called && called.length ? called[called.length - 1] : null;
        for (let i = 1; i <= 40; i++){
          const btn = document.createElement("button");
          btn.className = "bingo-call-btn" + (calledSet.has(i) ? " active" : "");
          if (calledSet.has(i) && last === i){
            btn.classList.add("recent");
          }
          btn.textContent = i;
          btn.disabled = !calledSet.has(i);
          btn.onclick = () => markNumber(i);
          grid.appendChild(btn);
        }
      }

      function showCallout(text){
        let el = document.getElementById("bCallout");
        if (!el){
          el = document.createElement("div");
          el.id = "bCallout";
          el.className = "bingo-callout";
          document.body.appendChild(el);
        }
        el.textContent = text;
        el.classList.add("show");
        setTimeout(() => el.classList.remove("show"), 2200);
      }

      async function markNumber(num){
        const gid = getGameId();
        if (!gid || !currentCard || !Array.isArray(currentCard.numbers)){
          setBingoStatus("Load a card first.", "err");
          return;
        }
        const marks = [];
        for (let r = 0; r < currentCard.numbers.length; r++){
          for (let c = 0; c < currentCard.numbers[r].length; c++){
            if (currentCard.numbers[r][c] === num){
              marks.push({row: r, col: c});
            }
          }
        }
        if (marks.length === 0){
          setBingoStatus("Number not on this card.", "err");
          return;
        }
        try{
          for (const m of marks){
            await jsonFetch("/bingo/mark", {
              method:"POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({game_id: gid, card_id: currentCard.card_id, row: m.row, col: m.col})
            });
            if (currentCard.marks && currentCard.marks[m.row]){
              currentCard.marks[m.row][m.col] = true;
            }
          }
          renderCard(currentCard, currentGame && currentGame.called, currentGame && currentGame.header);
          setBingoStatus("Marked card.", "ok");
        }catch(err){
          setBingoStatus(err.message, "err");
        }
      }

      function renderGamesList(games){
        const el = $("bGames");
        if (!el){
          return;
        }
        if (!Array.isArray(games) || games.length === 0){
          el.textContent = "No active games. Create one in Discord.";
          return;
        }
        el.innerHTML = "";
        games.forEach(g => {
          const item = document.createElement("div");
          const title = g.title || "Bingo";
          item.innerHTML = `<strong>${title}</strong>`;
          item.style.cursor = "pointer";
          item.onclick = () => {
            setGameId(g.game_id || "");
            showPanel("bingo");
            refreshBingo();
            loadOwnersForGame();
            loadGamesMenu();
          };
          el.appendChild(item);
        });
      }

      function loadGamesMenu(){
        jsonFetch("/bingo/games", {method:"GET"})
          .then(data => {
            const list = (data.games || []).filter(g => g.active !== false);
            renderGamesList(data.games || []);
            const menu = $("menuGames");
            const menuParent = $("menuBingo");
            menu.innerHTML = "";
            let hasActive = false;
            list.forEach(g => {
              const row = document.createElement("div");
              row.className = "menu-game";
              row.tabIndex = 0;
              const created = g.created_at ? new Date(g.created_at * 1000).toLocaleString() : "Unknown date";
              row.innerHTML = `
                <span class="menu-game-title">${g.title ? g.title : "Untitled"}</span>
                <span class="menu-game-meta">${created}</span>
              `;
              row.onclick = () => {
                setGameId(g.game_id || "");
                showPanel("bingo");
                refreshBingo();
                loadOwnersForGame();
              // Selected game is indicated by menu highlight.
              };
              row.addEventListener("keydown", (ev) => {
                if (ev.key === "Enter" || ev.key === " "){
                  ev.preventDefault();
                  row.click();
                }
              });
              menu.appendChild(row);
              if (g.game_id && g.game_id === getGameId()){
                row.classList.add("active");
                hasActive = true;
              }
            });
            if (!list.length){
              menu.textContent = "No active games.";
            }
            if (menuParent){
              menuParent.classList.toggle("has-active", hasActive);
            }
            // Selected game is indicated by menu highlight.
          })
          .catch(() => {});
      }

      async function loadDiscordChannels(){
        const select = $("bChannelSelect");
        if (!select){
          return;
        }
        select.innerHTML = `<option value="">Loading...</option>`;
        try{
          const data = await jsonFetch("/discord/channels", {method:"GET"}, true);
          const channels = data.channels || [];
          select.innerHTML = "";
          if (!channels.length){
            select.innerHTML = `<option value="">No channels available</option>`;
            return;
          }
          let botlogsId = "";
          channels.forEach(ch => {
            const opt = document.createElement("option");
            opt.value = String(ch.id || "");
            const guild = ch.guild_name || ch.guild_id || "Guild";
            const category = ch.category ? ` / ${ch.category}` : "";
            const name = ch.name ? `#${ch.name}` : String(ch.id || "");
            opt.textContent = `${guild}${category} - ${name}`;
            select.appendChild(opt);
            if (!botlogsId && String(ch.name || "").toLowerCase() === "bot-logs"){
              botlogsId = opt.value;
            }
          });
          const current = $("bChannel").value.trim();
          if (current){
            select.value = current;
          }
          if (!select.value && select.options.length){
            select.value = botlogsId || select.options[0].value;
          }
          if (select.value){
            $("bChannel").value = select.value;
          }
          updateBingoCreatePayload();
        }catch(err){
          select.innerHTML = `<option value="">Failed to load</option>`;
          setStatus(err.message, "err");
        }
      }

      function showPanel(which){
        if (!suppressPanelSave){
          try{
            localStorage.setItem("overlay_panel", which);
          }catch(err){}
        }
        function toggleClass(id, name, state){
          const el = $(id);
          if (!el) return;
          el.classList.toggle(name, state);
        }
        toggleClass("menuDashboard", "active", which === "dashboard");
        toggleClass("menuBingo", "active", which === "bingo" || which === "bingoSessions");
        toggleClass("menuTarotLinks", "active", which === "tarotLinks");
        toggleClass("menuCardgameSessions", "active", which === "cardgameSessions");
        toggleClass("menuTarotDecks", "active", which === "tarotDecks");
        toggleClass("menuDiceEditor", "active", which === "diceEditor");
        toggleClass("menuSlotsEditor", "active", which === "slotsEditor");
        toggleClass("menuContests", "active", which === "contests");
        toggleClass("menuMedia", "active", which === "media");
        toggleClass("menuGamesList", "active", which === "gamesList");
        toggleClass("menuGamesEvents", "active", which === "events");
        toggleClass("menuCraps", "active", which === "craps");
        toggleClass("menuSlots", "active", which === "slots");
        // Venues are accessed via Dashboard buttons for now.
        toggleClass("dashboardPanel", "hidden", which !== "dashboard");
        toggleClass("bingoPanel", "hidden", which !== "bingo");
        toggleClass("bingoSessionsPanel", "hidden", which !== "bingoSessions");
        toggleClass("tarotLinksPanel", "hidden", which !== "tarotLinks");
        toggleClass("cardgameSessionsPanel", "hidden", which !== "cardgameSessions");
        toggleClass("tarotDecksPanel", "hidden", which !== "tarotDecks");
        toggleClass("diceEditorPanel", "hidden", which !== "diceEditor");
        toggleClass("slotsEditorPanel", "hidden", which !== "slotsEditor");
        toggleClass("crapsPanel", "hidden", which !== "craps");
        toggleClass("slotsPanel", "hidden", which !== "slots");
        toggleClass("contestPanel", "hidden", which !== "contests");
        toggleClass("mediaPanel", "hidden", which !== "media");
        toggleClass("gamesListPanel", "hidden", which !== "gamesList");
        toggleClass("eventsPanel", "hidden", which !== "events");
        toggleClass("venuesPanel", "hidden", which !== "venues");
        toggleClass("iframePanel", "hidden", which !== "iframe");
        if (which === "dashboard"){
          renderDashboardChangelog();
          loadDashboardStats();
          loadDashboardLogs(dashboardLogsKind);
        } else if (which === "diceEditor"){
          loadDiceSetList();
        } else if (which === "slotsEditor"){
          loadSlotMachineList();
        } else if (which === "venues"){
          loadVenuesPanel(true);
        } else if (which === "media"){
          setMediaTab("upload");
          ensureMediaVenueOptions().then(() => loadMediaLibrary());
          loadTarotArtists();
          updateMediaUploadDropDisplay(mediaUploadFile);
          updateMediaUploadState();
        }else if (which === "cardgameSessions"){
          const defaults = getCardgameDefaults();
          if (defaults){
            setCardgameDefaults(defaults);
          }else{
            if ($("cgGameSelect") && !$("cgGameSelect").value) $("cgGameSelect").value = "blackjack";
            if ($("cgPot") && !$("cgPot").value) $("cgPot").value = 0;
            if ($("cgCurrency") && !$("cgCurrency").value) $("cgCurrency").value = "gil";
          }
          loadCardgameDecks();
          loadCardgameSessions();
        }else if (which === "gamesList"){
          loadGamesListVenues();
          loadGamesList(true);
        }else if (which === "events"){
          loadEventsVenues();
          loadEventsList(true);
        }
      }

      // Load URL in iframe panel
      function loadIframe(url){
        const iframe = $("iframeContent");
        if (iframe){
          iframe.src = url;
        }
        showPanel("iframe");
      }

      function getSavedPanel(){
        try{
          return localStorage.getItem("overlay_panel") || "";
        }catch(err){
          return "";
        }
      }

      function getSeenDashboard(){
        try{
          return localStorage.getItem("overlay_seen_dashboard") === "1";
        }catch(err){
          return false;
        }
      }

      function setSeenDashboard(){
        try{
          localStorage.setItem("overlay_seen_dashboard", "1");
        }catch(err){}
      }

      let changelogLoaded = false;

      function escapeHtml(text){
        return String(text || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;");
      }

      function renderSimpleMarkdown(text){
        const lines = String(text || "").split(/\r?\n/);
        let html = "";
        let inList = false;
        function closeList(){
          if (inList){
            html += "</ul>";
            inList = false;
          }
        }
        lines.forEach((line) => {
          const raw = line.trim();
          if (!raw){
            closeList();
            return;
          }
          if (raw.startsWith("### ")){
            closeList();
            html += `<h5>${escapeHtml(raw.slice(4))}</h5>`;
            return;
          }
          if (raw.startsWith("## ")){
            closeList();
            const title = raw.slice(3).trim();
            const label = title.toLowerCase() === "unreleased" ? "Latest (auto-published)" : title;
            html += `<h4>${escapeHtml(label)}</h4>`;
            return;
          }
          if (raw.startsWith("# ")){
            closeList();
            html += `<h3>${escapeHtml(raw.slice(2))}</h3>`;
            return;
          }
          if (raw.startsWith("- ")){
            if (!inList){
              html += "<ul>";
              inList = true;
            }
            html += `<li>${escapeHtml(raw.slice(2))}</li>`;
            return;
          }
          closeList();
          html += `<p>${escapeHtml(raw)}</p>`;
        });
        closeList();
        return html || "<p>No changelog entries found.</p>";
      }

      async function renderDashboardChangelog(){
        const target = $("dashChangelog");
        if (!target || changelogLoaded) return;
        changelogLoaded = true;
        target.textContent = "Loading changelog...";
        const sources = [
          "https://raw.githubusercontent.com/dorbian/thebigtree/main/changelog.md",
          "/static/changelog.md"
        ];
        try{
          let text = "";
          for (const url of sources){
            const res = await fetch(url, {cache:"no-store"});
            if (!res.ok) continue;
            text = await res.text();
            if (text) break;
          }
          if (!text){
            throw new Error("Changelog not available.");
          }
          target.innerHTML = renderSimpleMarkdown(text);
        }catch(err){
          target.textContent = err.message || "Changelog not available.";
        }
      }

      let suppressPanelSave = false;

      function showPanelOnce(which){
        suppressPanelSave = true;
        showPanel(which);
        suppressPanelSave = false;
      }

      $("menuDashboard").addEventListener("click", () => showPanel("dashboard"));
      $("menuBingo").addEventListener("click", () => {
        showPanel("bingoSessions");
        loadGamesMenu();
      });
      
      // XIVAuth Users - load in iframe
      const dashboardXivAuthBtn = $("dashboardXivAuthLink");
      if (dashboardXivAuthBtn){
        dashboardXivAuthBtn.addEventListener("click", () => {
          if (!ensureScope("admin:web", "Admin web access required.")) return;
          loadIframe("/user-area/manage");
        });
      }
      
      const menuGamesList = $("menuGamesList");
      if (menuGamesList){
        menuGamesList.addEventListener("click", () => {
          if (!ensureScope("admin:web", "Admin web access required.")) return;
          showPanel("gamesList");
        });
      }
      const menuGamesEvents = $("menuGamesEvents");
      if (menuGamesEvents){
        menuGamesEvents.addEventListener("click", () => {
          if (!ensureScope("event:host", "Event host scope required.") && !ensureScope("admin:web", "Admin web access required.")) return;
          showPanel("events");
        });
      }
      on("menuBingoRefresh", "click", (ev) => {
        ev.stopPropagation();
        loadGamesMenu();
      });
      on("bSessionsRefresh", "click", () => loadGamesMenu());
      $("bChannelRefresh").addEventListener("click", () => loadDiscordChannels());
      $("bChannelSelect").addEventListener("change", (ev) => {
        const pick = ev.target.value || "";
        if (pick){
          $("bChannel").value = pick;
        }
        updateBingoCreatePayload();
      });
      $("menuCreateGame").addEventListener("click", (ev) => {
        ev.stopPropagation();
        $("bCreateModal").classList.add("show");
        $("bTitle").focus();
        $("bChannel").value = "";
        $("bChannelSelect").value = "";
        $("bAnnounceCalls").checked = false;
        $("bSeedPot").value = "0";
        if (adminVenueCurrency && $("bCurrency")){
          $("bCurrency").value = adminVenueCurrency;
        }
        const venueBingoBg = adminVenueGameBackgrounds ? (adminVenueGameBackgrounds.bingo || "") : "";
        bingoCreateBgUrl = venueBingoBg || "";
        $("bCreateBgStatus").textContent = bingoCreateBgUrl
          ? "Venue background applied."
          : "No background selected.";
        loadEventOptions("bCreateEventSelect");
        loadDiscordChannels();
        updateBingoCreatePayload();
      });
      $("menuTarotLinks").addEventListener("click", () => {
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        showPanel("tarotLinks");
      });
      const cardgameMenu = $("menuCardgameSessions");
      if (cardgameMenu){
        cardgameMenu.addEventListener("click", () => {
          if (!ensureCardgamesScope()) return;
          showPanel("cardgameSessions");
          const defaults = getCardgameDefaults();
          setCardgameDefaults(defaults || {});
          loadCardgameDecks();
          loadCardgameSessions();
        });
      }
      $("menuTarotDecks").addEventListener("click", () => {
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        showPanel("tarotDecks");
      });
      $("menuDiceEditor").addEventListener("click", () => {
        if (!ensureScope("dice:admin", "Dice access required.")) return;
        showPanel("diceEditor");
      });
      $("menuSlotsEditor").addEventListener("click", () => {
        if (!ensureScope("slots:admin", "Slots access required.")) return;
        showPanel("slotsEditor");
      });
      $("menuContests").addEventListener("click", () => {
        showPanel("contests");
        loadContestManagement();
        loadContestChannels();
        loadTarotClaimsDecks();
        loadTarotClaimsChannels();
      });
      function bindMenuKey(id){
        const el = $(id);
        if (!el) return;
        el.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " "){
            ev.preventDefault();
            el.click();
          }
        });
      }
      bindMenuKey("menuDashboard");
      bindMenuKey("menuBingo");
      bindMenuKey("menuTarotLinks");
      bindMenuKey("menuCardgameSessions");
      bindMenuKey("menuTarotDecks");
      bindMenuKey("menuDiceEditor");
      bindMenuKey("menuSlotsEditor");
      bindMenuKey("menuContests");
      bindMenuKey("menuMedia");
      bindMenuKey("menuGamesList");
      on("bAnnounceToggle", "change", async (ev) => {
        const gid = getGameId();
        if (!gid){
          setBingoStatus("Select a game first.", "err");
          ev.target.checked = false;
          return;
        }
        try{
          await jsonFetch("/bingo/" + encodeURIComponent(gid), {
            method:"PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({announce_calls: ev.target.checked})
          });
          const badge = $("bAnnounceBadge");
          if (badge){
            badge.textContent = ev.target.checked ? "On" : "Off";
            badge.className = "status-badge" + (ev.target.checked ? " good" : "");
          }
          setBingoStatus("Announce calls updated.", "ok");
        }catch(err){
          setBingoStatus(err.message, "err");
        }
      });
      $("menuMedia").addEventListener("click", () => {
        showPanel("media");
      });
      const menuCraps = $("menuCraps");
      if (menuCraps){
        menuCraps.addEventListener("click", () => {
          showPanel("craps");
        });
      }
      const menuSlots = $("menuSlots");
      if (menuSlots){
        menuSlots.addEventListener("click", () => {
          showPanel("slots");
        });
      }
      $("menuArtists").addEventListener("click", () => {
        if (!(hasScope("tarot:admin") || hasScope("admin:web"))){
          setStatus("Artist access requires admin permissions.", "err");
          return;
        }
        $("artistModal").classList.add("show");
        loadTarotArtists();
      });
      $("menuCalendar").addEventListener("click", () => {
        $("calendarModal").classList.add("show");
        loadCalendarAdmin();
      });
      $("menuGallery").addEventListener("click", () => {
        if (!(hasScope("tarot:admin") || hasScope("admin:web"))){
          setStatus("Gallery access requires admin permissions.", "err");
          return;
        }
        $("galleryModal").classList.add("show");
        loadGalleryChannels();
        loadGallerySettings();
        // Gallery items are managed from Media Library.
        loadTarotArtists();
      });
      $("menuAuthRoles").addEventListener("click", () => {
        if (!authUserIsElfmin){
          setStatus("Only elfministrators can manage auth roles.", "err");
          return;
        }
        $("authRolesModal").classList.add("show");
        loadAuthRoles();
      });
      $("menuAuthKeys").addEventListener("click", () => {
        if (!authUserIsElfmin){
          setStatus("Only elfministrators can manage auth keys.", "err");
          return;
        }
        $("authTokensModal").classList.add("show");
        loadAuthTokens();
      });
      $("menuAuthTemp").addEventListener("click", () => {
        if (!authUserIsElfmin){
          setStatus("Only elfministrators can generate temporary links.", "err");
          return;
        }
        const modal = $("authTempModal");
        if (!modal){
          setStatus("Temporary access UI not loaded.", "err");
          return;
        }
        modal.classList.add("show");
        loadAuthRoles();
        renderAuthTempRoles();
        setAuthTempStatus("Ready.", "");
      });
      const systemConfigBtn = $("menuSystemConfig");
      if (systemConfigBtn){
        systemConfigBtn.addEventListener("click", () => {
          const modal = $("systemConfigModal");
          if (!modal){
            setSystemConfigStatus("System configuration UI not available.", "err");
            return;
          }
          modal.classList.add("show");
          loadSystemConfig();
        });
      }
      on("systemConfigClose", "click", () => {
        const modal = $("systemConfigModal");
        if (modal){
          modal.classList.remove("show");
        }
      });
      on("systemConfigModal", "click", (event) => {
        const modal = $("systemConfigModal");
        if (event.target === modal){
          modal.classList.remove("show");
        }
      });
      on("systemXivSave", "click", () => saveSystemConfig("xivauth"));
      on("systemOpenAISave", "click", () => saveSystemConfig("openai"));
      on("dashboardStatsRefresh", "click", () => loadDashboardStats(true));
      on("dashboardLogsClose", "click", () => $("dashboardLogsModal")?.classList.remove("show"));
      on("dashboardLogsModal", "click", (ev) => {
        if (ev.target && ev.target.id === "dashboardLogsModal"){
          ev.currentTarget.classList.remove("show");
        }
      });
      on("dashboardLogsBoot", "click", () => {
        $("dashboardLogsCurrent").textContent = "Current: boot";
        $("dashboardLogsModal")?.classList.add("show");
        loadDashboardLogs("boot", true);
      });
      on("dashboardLogsAuth", "click", () => {
        $("dashboardLogsCurrent").textContent = "Current: auth";
        $("dashboardLogsModal")?.classList.add("show");
        loadDashboardLogs("auth", true);
      });
      on("dashboardLogsUpload", "click", () => {
        $("dashboardLogsCurrent").textContent = "Current: upload";
        $("dashboardLogsModal")?.classList.add("show");
        loadDashboardLogs("upload", true);
      });
      on("dashboardLogsRefresh", "click", () => loadDashboardLogs(dashboardLogsKind || "boot", true));
      on("pluginRepoCopy", "click", async () => {
        const url = ($("pluginRepoUrl")?.textContent || "").trim();
        if (!url){
          showToast("No link to copy.", "err");
          return;
        }
        try{
          await navigator.clipboard.writeText(url);
          showToast("Copied link.", "ok");
        }catch (err){
          showToast("Copy failed.", "err");
        }
      });
      // Venue management (dashboard)
      let venueCache = [];
      let venueMediaCache = [];
      let venueDeckCache = [];
      let venueDiscordUserCache = [];

      function _discordUserLabel(u){
        if (!u) return "";
        const did = u.discord_id || "";
        const dn = u.display_name || u.global_name || u.name || "";
        const nm = u.name || "";
        const best = dn || nm || String(did);
        const tag = (dn && nm && dn !== nm) ? ` (@${nm})` : "";
        return `${best}${tag} - ${did}`;
      }

      function renderVenueAdminsSelect(){
        const sel = $("venueAdminsSelect");
        if (!sel) return;
        const curSel = new Set(Array.from(sel.selectedOptions || []).map(o => String(o.value || "")).filter(Boolean));
        const opts = (venueDiscordUserCache || []).map(u => {
          const id = String(u.discord_id || "");
          if (!id) return "";
          const label = _discordUserLabel(u);
          return `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`;
        }).filter(Boolean);
        sel.innerHTML = opts.join("");
        Array.from(sel.options).forEach(o => { if (curSel.has(String(o.value))) o.selected = true; });
      }

      function syncVenueAdminsFromSelect(){
        const sel = $("venueAdminsSelect");
        const input = $("venueAdmins");
        if (!sel || !input) return;
        const ids = Array.from(sel.selectedOptions || []).map(o => String(o.value || "").trim()).filter(Boolean);
        input.value = ids.join(", ");
      }

      function applyVenueAdminsToSelect(ids){
        const sel = $("venueAdminsSelect");
        const input = $("venueAdmins");
        if (input) input.value = (ids || []).join(", ");
        if (!sel) return;
        const set = new Set((ids || []).map(x => String(x).trim()).filter(Boolean));
        Array.from(sel.options).forEach(o => { o.selected = set.has(String(o.value || "")); });
      }

      async function loadVenueDiscordUsers(){
        if (!ensureScope("admin:web", "Admin web scope required.")) return;
        try{
          const data = await jsonFetch("/admin/discord-users", {method:"GET"});
          venueDiscordUserCache = data.users || [];
        }catch(_e){
          venueDiscordUserCache = [];
        }
        renderVenueAdminsSelect();
        filterVenueAdmins();
      }

      function filterVenueAdmins(){
        const q = ($("venueAdminsFilter")?.value || "").trim().toLowerCase();
        const sel = $("venueAdminsSelect");
        if (!sel) return;
        Array.from(sel.options).forEach(o => {
          const txt = (o.textContent || "").toLowerCase();
          o.hidden = !!q && !txt.includes(q);
        });
      }

      function showVenueModal(show){
        const modal = $("venueModal");
        if (!modal) return;
        modal.classList.toggle("show", !!show);
      }

      function setVenueStatus(msg, kind){
        setStatusText("venueStatus", msg, kind);
      }

      function renderVenueSelect(){
        const sel = $("venueSelect");
        if (!sel) return;
        const cur = sel.value || "";
        const opts = [`<option value="">(pick a venue)</option>`]
          .concat((venueCache || []).map(v => `<option value="${String(v.id)}">${escapeHtml(v.name || `Venue ${v.id}`)}</option>`));
        sel.innerHTML = opts.join("");
        if (cur) sel.value = cur;
      }

      function renderVenueBackgroundSelect(){
        const ids = [
          "venueBackground",
          "venueBackgroundSlots",
          "venueBackgroundBlackjack",
          "venueBackgroundPoker",
          "venueBackgroundHighlow",
          "venueBackgroundCrapslite",
          "venueBackgroundTarot"
        ];
        ids.forEach((id) => {
          const sel = $(id);
          if (!sel) return;
          const cur = sel.value || "";
          const defaultLabel = id === "venueBackground" ? "(default)" : "(use venue default)";
          const opts = [`<option value="">${defaultLabel}</option>`]
            .concat((venueMediaCache || []).map(it => {
              const label = it.title || it.name || it.filename || "Image";
              return `<option value="${escapeHtml(it.url || "")}">${escapeHtml(label)}</option>`;
            }));
          sel.innerHTML = opts.join("");
          if (cur) sel.value = cur;
        });
      }

      function renderVenueDeckSelect(){
        const sel = $("venueDeck");
        if (!sel) return;
        const cur = sel.value || "";
        const opts = [`<option value="">(default)</option>`]
          .concat((venueDeckCache || []).map(d => {
            const id = d.id || d.deck || d.deck_id;
            if (!id) return "";
            const nm = d.name || d.title || id;
            return `<option value="${escapeHtml(String(id))}">${escapeHtml(String(nm))}</option>`;
          }).filter(Boolean));
        sel.innerHTML = opts.join("");
        if (cur) sel.value = cur;
      }

      async function loadVenueDeps(){
        // Load media + decks (best-effort)
        venueMediaCache = [];
        venueDeckCache = [];
        try{
          const res = await fetch("/api/media/list?media_type=background", {headers: {"X-API-Key": apiKeyEl.value.trim()}});
          if (res.status === 401){ handleUnauthorized(); throw new Error("Unauthorized"); }
          const data = await res.json();
          if (data.ok) venueMediaCache = data.items || [];
          if (data.ok && (!venueMediaCache || !venueMediaCache.length)){
            const fallback = await fetch("/api/media/list", {headers: {"X-API-Key": apiKeyEl.value.trim()}});
            if (fallback.status === 401){ handleUnauthorized(); throw new Error("Unauthorized"); }
            const fallbackData = await fallback.json();
            if (fallbackData.ok) venueMediaCache = fallbackData.items || [];
          }
        }catch(_e){ venueMediaCache = []; }
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          if (data && (data.ok || Array.isArray(data.decks))) venueDeckCache = data.decks || [];
        }catch(_e){ venueDeckCache = []; }
        renderVenueBackgroundSelect();
        renderVenueDeckSelect();
      }

      async function loadVenuesForModal(){
        if (!ensureScope("admin:web", "Admin web scope required.")) return;
        try{
          const data = await jsonFetch("/admin/venues", {method:"GET"});
          venueCache = data.venues || [];
        }catch(err){
          venueCache = [];
        }
        renderVenueSelect();
      }

      function setVenueFields(v){
        $("venueName").value = v?.name || "";
        $("venueCurrency").value = v?.currency_name || "";
        $("venueMinBet").value = String(v?.minimal_spend ?? 0);
        $("venueBackground").value = v?.background_image || "";
        $("venueDeck").value = v?.deck_id || "";
        const gameBackgrounds = (v?.metadata && v.metadata.game_backgrounds) ? v.metadata.game_backgrounds : {};
        $("venueBackgroundSlots").value = gameBackgrounds?.slots || "";
        $("venueBackgroundBlackjack").value = gameBackgrounds?.blackjack || "";
        $("venueBackgroundPoker").value = gameBackgrounds?.poker || "";
        $("venueBackgroundHighlow").value = gameBackgrounds?.highlow || "";
        $("venueBackgroundCrapslite").value = gameBackgrounds?.crapslite || "";
        $("venueBackgroundTarot").value = gameBackgrounds?.tarot || "";
        const ids = (v?.metadata && v.metadata.admin_discord_ids) ? v.metadata.admin_discord_ids : "";
        if (Array.isArray(ids)){
          $("venueAdmins").value = ids.join(", ");
        }else if (typeof ids === "string"){
          $("venueAdmins").value = ids;
        }else{
          $("venueAdmins").value = "";
        }

        // Sync multi-select UI
        let idsList = [];
        const rawIds = $("venueAdmins").value || "";
        idsList = rawIds.split(",").map(s => s.trim()).filter(Boolean);
        applyVenueAdminsToSelect(idsList);

        const delBtn = $("venueDelete");
        if (delBtn){
          const canDelete = !!v && !!v.id;
          delBtn.style.display = canDelete ? "inline-flex" : "none";
        }
      }

      async function openVenueModal(mode){
        const m = mode || {};
        showVenueModal(true);
        setVenueStatus("Loading...", "");
        
        // Load all dependencies in parallel
        await Promise.all([
          loadVenueDeps(),
          loadVenueDiscordUsers(),
          loadVenuesForModal()
        ]);
        
        if (m.id){
          const id = Number(m.id);
          const found = (venueCache || []).find(v => Number(v.id) === id) || null;
          if (found){
            $("venueSelect").value = String(found.id);
            setVenueFields(found);
          }else{
            $("venueSelect").value = "";
            setVenueFields(null);
          }
        }else if (m.new){
          $("venueSelect").value = "";
          setVenueFields(null);
        }else{
          // Load first venue into fields for convenience
          const first = venueCache && venueCache.length ? venueCache[0] : null;
          if (first){
            $("venueSelect").value = String(first.id);
            setVenueFields(first);
          }else{
            setVenueFields(null);
          }
        }
        setVenueStatus("Ready.", "");
      }

      on("dashboardVenueList", "click", () => {
        showPanelOnce("venues");
      });
      on("dashboardAddVenue", "click", () => openVenueModal({new:true}));
      on("venueClose", "click", () => showVenueModal(false));
      on("venueModal", "click", (ev) => { if (ev.target === $("venueModal")) showVenueModal(false); });
      on("venueNew", "click", () => { $("venueSelect").value = ""; setVenueFields(null); setVenueStatus("Creating new venue.", ""); });
      on("venueSelect", "change", () => {
        const id = parseInt($("venueSelect").value || "0", 10) || 0;
        const v = (venueCache || []).find(x => Number(x.id) === id) || null;
        setVenueFields(v);
      });

      on("venueAdminsSelect", "change", () => {
        syncVenueAdminsFromSelect();
      });
      on("venueAdminsFilter", "input", () => {
        filterVenueAdmins();
      });
      on("venueDelete", "click", async () => {
        if (!ensureScope("admin:web", "Admin web scope required.")) return;
        const venueId = parseInt($("venueSelect").value || "0", 10) || 0;
        if (!venueId){ setVenueStatus("Pick a venue to delete.", "err"); return; }
        const name = $("venueName").value.trim() || `Venue ${venueId}`;
        if (!window.confirm(`Delete venue "${name}"?

Games and events will keep their history, but this venue will be removed.`)) return;
        setVenueStatus("Deleting...", "");
        try{
          const resp = await jsonFetch("/admin/venues/delete", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify({venue_id: venueId})
          });
          if (!resp.ok) throw new Error(resp.error || "Delete failed");
          showToast("Venue deleted.", "ok");
          await loadVenuesForModal();
          await loadVenuesPanel(true);
          setVenueFields(null);
          $("venueSelect").value = "";
          setVenueStatus("Deleted.", "ok");
        }catch(err){
          setVenueStatus(err.message || String(err), "err");
        }
      });

      on("venueSave", "click", async () => {
        if (!ensureScope("admin:web", "Admin web scope required.")) return;
        const name = $("venueName").value.trim();
        if (!name){ setVenueStatus("Name is required.", "err"); return; }
        const currency = $("venueCurrency").value.trim();
        const bg = $("venueBackground").value || "";
        const deck = $("venueDeck").value || "";
        const game_backgrounds = {
          slots: $("venueBackgroundSlots").value || "",
          blackjack: $("venueBackgroundBlackjack").value || "",
          poker: $("venueBackgroundPoker").value || "",
          highlow: $("venueBackgroundHighlow").value || "",
          crapslite: $("venueBackgroundCrapslite").value || "",
          tarot: $("venueBackgroundTarot").value || "",
        };
        if (!currency){ setVenueStatus("Currency is required.", "err"); return; }
        if (!bg){ setVenueStatus("Background must be selected.", "err"); return; }
        if (!deck){ setVenueStatus("Card deck must be selected.", "err"); return; }
        const payload = {
          name,
          currency_name: currency || null,
          minimal_spend: parseInt($("venueMinBet").value || "0", 10) || 0,
          background_image: bg || null,
          deck_id: deck || null,
          admin_discord_ids: $("venueAdmins").value || null,
          game_backgrounds: game_backgrounds,
        };
        setVenueStatus("Saving...", "");
        try{
          const resp = await jsonFetch("/admin/venues/upsert", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify(payload)
          });
          if (!resp.ok) throw new Error(resp.error || "Save failed");
          showToast("Venue saved.", "ok");
          // Refresh caches
          await loadVenuesForModal();
          await loadGamesListVenues(true);
          const saved = resp.venue;
          if (saved && saved.id){
            $("venueSelect").value = String(saved.id);
            setVenueFields(saved);
          }
          setVenueStatus("Saved.", "ok");
        }catch(err){
          setVenueStatus(err.message || String(err), "err");
        }
      });

      // --- Venues panel (list view) ---
      let venuesPanelLoaded = false;
      const venuesPanelState = { q: "" };

      function venueMatchesQuery(v, q){
        if (!q) return true;
        const hay = [v?.name, v?.currency_name, v?.deck_id, v?.background_image].filter(Boolean).join(" ").toLowerCase();
        return hay.includes(q.toLowerCase());
      }

      function renderVenuesPanel(){
        const body = $("venuesListBody");
        if (!body) return;
        const q = (venuesPanelState.q || "").trim();
        const rows = (venueCache || []).filter(v => venueMatchesQuery(v, q));
        if (!rows.length){
          body.innerHTML = "<div class='muted'>No venues found.</div>";
          return;
        }
        body.innerHTML = `
          <table class="tight-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Currency</th>
                <th>Min bet</th>
                <th>Deck</th>
                <th>Background</th>
                <th>Admins</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(v => {
                const ids = (v.metadata && Array.isArray(v.metadata.admin_discord_ids)) ? v.metadata.admin_discord_ids : [];
                return `
                  <tr class="venue-row" data-venue-id="${escapeHtml(String(v.id))}">
                    <td><strong>${escapeHtml(v.name || "-")}</strong><div class="muted" style="font-size:12px;">#${escapeHtml(String(v.id))}</div></td>
                    <td>${escapeHtml(v.currency_name || "-")}</td>
                    <td>${escapeHtml(String(v.minimal_spend ?? 0))}</td>
                    <td>${escapeHtml(v.deck_id || "-")}</td>
                    <td class="muted" style="max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(v.background_image || "-")}</td>
                    <td class="muted">${ids.length ? escapeHtml(ids.join(", ")) : "-"}</td>
                  </tr>`;
              }).join("")}
            </tbody>
          </table>
        `;
        body.querySelectorAll(".venue-row").forEach(tr => {
          tr.addEventListener("click", () => {
            const id = Number(tr.getAttribute("data-venue-id"));
            openVenueModal({id});
          });
        });
      }

      async function loadVenuesPanel(force = false){
        if (!ensureScope("admin:web", "Admin web scope required.")) return;
        if (venuesPanelLoaded && !force){
          renderVenuesPanel();
          return;
        }
        venuesPanelLoaded = true;
        try{
          const data = await jsonFetch("/admin/venues", {method:"GET"});
          venueCache = data.venues || [];
        }catch(_e){
          venueCache = [];
        }
        renderVenuesPanel();
        loadGamesListVenues(true);
      }

      on("venuesRefresh", "click", () => loadVenuesPanel(true));
      on("venuesAdd", "click", () => openVenueModal({new:true}));
      on("venuesFilterQuery", "input", () => {
        venuesPanelState.q = $("venuesFilterQuery").value || "";
        renderVenuesPanel();
      });

      // Events panel controls
      on("eventsRefresh", "click", () => {
        loadEventsVenues(true);
        loadEventsList(true);
      });
      on("eventsAdd", "click", () => openEventModal({}));
      on("eventsFilterQuery", "keydown", (ev) => {
        if (ev.key === "Enter"){
          ev.preventDefault();
          loadEventsList(true);
        }
      });
      on("eventsFilterVenue", "change", () => loadEventsList(true));
      on("eventsFilterEnded", "change", () => loadEventsList(true));
      on("eventModalClose", "click", () => $("eventModal")?.classList.remove("show"));
      on("eventModal", "click", (ev) => {
        if (ev.target && ev.target.id === "eventModal"){
          ev.currentTarget.classList.remove("show");
        }
      });
      on("eventSave", "click", () => saveEventModal());
      on("eventEnd", "click", () => endEventModal());
      on("eventCopyJoin", "click", () => {
        const modal = $("eventModal");
        const code = modal?.dataset?.event_code || "";
        if (!code) return;
        const base = (window.location.origin || "").replace(/\/$/, "");
        const joinUrl = `${base}/events/${code}`;
        copyToClipboard(joinUrl);
      });

      // Event background helpers (uses media library selection)
      on("eventOpenMedia", "click", () => {
        librarySelectHandler = (item) => {
          const pick = item && (item.url || item.fallback_url || "");
          if (!pick){
            setStatusText("eventJoinInfo", "Select a media item first.", "err");
            return;
          }
          const modal = $("eventModal");
          if (!modal) return;
          modal.dataset.background_url = pick;
          modal.dataset.artist_id = item.artist_id || "";
          modal.dataset.artist_name = item.artist_name || item.artist_id || "";
          setEventBackgroundStatus(pick);
          showLibraryModal(false);
        };
        showLibraryModal(true);
        loadLibrary("media");
      });

      // Event minigames modal
      on("eventPickGames", "click", () => {
        const modal = $("eventModal");
        const enabled = getEventEnabledGames(modal);
        syncEventGamesModalChecks(enabled);
        showEventGamesModal(true);
      });
      ["eventGamesClose", "eventGamesCancel"].forEach(id => {
        on(id, "click", () => showEventGamesModal(false));
      });
      on("eventGamesModal", "click", (ev) => {
        if (ev.target && ev.target.id === "eventGamesModal"){
          showEventGamesModal(false);
        }
      });
      on("eventGamesClear", "click", () => {
        document.querySelectorAll("#eventGamesModal .event-game-check").forEach(cb => { cb.checked = false; });
      });
      on("eventGamesSave", "click", () => {
        const modal = $("eventModal");
        if (!modal) return;
        const enabled = readEventGamesModalChecks();
        modal.dataset.enabled_games = JSON.stringify(enabled);
        setEventGamesStatus(enabled);
        showEventGamesModal(false);
      });
      ["eventWalletModalClose", "eventWalletModalCancel"].forEach(id => {
        on(id, "click", () => showEventWalletModal(false));
      });
      on("eventWalletModal", "click", (ev) => {
        if (ev.target && ev.target.id === "eventWalletModal"){
          showEventWalletModal(false);
        }
      });
      on("eventWalletSet", "click", async () => {
        const modal = $("eventModal");
        const status = $("eventWalletStatus");
        const walletModal = $("eventWalletModal");
        const eventId = parseInt(walletModal?.dataset?.event_id || modal?.dataset?.event_id || "0", 10) || 0;
        const user = walletModal?.dataset?.player || "";
        const walletEnabled = walletModal?.dataset?.wallet_enabled === "1" || modal?.dataset?.wallet_enabled === "1";
        const amountRaw = $("eventWalletAmount")?.value || "0";
        const comment = $("eventWalletComment")?.value || "";
        const hostName = $("brandUserName")?.textContent?.trim() || "";
        const amount = parseInt(amountRaw, 10);
        if (!walletEnabled){
          if (status) status.textContent = "Wallet is disabled for this event.";
          return;
        }
        if (!eventId){
          if (status) status.textContent = "Save the event first.";
          return;
        }
        if (!user){
          if (status) status.textContent = "Pick a player.";
          return;
        }
        if (!comment.trim()){
          if (status) status.textContent = "Add a comment for the wallet change.";
          return;
        }
        if (!Number.isFinite(amount)){
          if (status) status.textContent = "Enter a valid amount.";
          return;
        }
        if (status) status.textContent = "Saving...";
        try{
          const resp = await jsonFetch(`/admin/events/${eventId}/wallets/set`, {
            method: "POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
              xiv_username: user,
              delta: amount,
              comment: comment,
              host_name: hostName
            })
          });
          if (!resp.ok){
            throw new Error(resp.error || "Unable to set wallet balance");
          }
          if (status) status.textContent = `Wallet balance is now ${resp.balance}.`;
          const commentEl = $("eventWalletComment");
          if (commentEl) commentEl.value = "";
          showEventWalletModal(false);
          await loadEventPlayers(eventId);
          await loadEventSummary(eventId);
        }catch(err){
          if (status) status.textContent = err.message || "Unable to set wallet balance.";
        }
      });

      on("dashboardChangelogToggle", "click", () => {
        const modal = $("changelogModal");
        if (!modal) return;
        modal.classList.add("show");
        renderDashboardChangelog();
      });

      on("changelogClose", "click", () => {
        const modal = $("changelogModal");
        if (!modal) return;
        modal.classList.remove("show");
      });

      on("changelogModal", "click", (ev) => {
        // Click backdrop to close.
        if (ev.target && ev.target.id === "changelogModal"){
          ev.currentTarget.classList.remove("show");
        }
      });

      // Games list controls
      on("gamesFilterApply", "click", () => {
        gamesListState.page = 1;
        loadGamesList(true);
      });
      on("gamesPrev", "click", () => {
        const next = Math.max(1, (gamesListState.page || 1) - 1);
        if (next === gamesListState.page) return;
        gamesListState.page = next;
        loadGamesList(true);
      });
      on("gamesNext", "click", () => {
        const pageSize = gamesListState.page_size || 50;
        const pages = Math.max(1, Math.ceil((gamesListState.total || 0) / pageSize));
        const next = Math.min(pages, (gamesListState.page || 1) + 1);
        if (next === gamesListState.page) return;
        gamesListState.page = next;
        loadGamesList(true);
      });
      on("gamesPageSize", "change", () => {
        gamesListState.page = 1;
        loadGamesList(true);
      });
      ["gamesFilterQuery", "gamesFilterPlayer"].forEach(id => {
        on(id, "keydown", (ev) => {
          if (ev.key === "Enter"){
            ev.preventDefault();
            gamesListState.page = 1;
            loadGamesList(true);
          }
        });
      });
      ["gamesFilterModule", "gamesFilterVenue", "gamesFilterInactive"].forEach(id => {
        on(id, "change", () => {
          gamesListState.page = 1;
          loadGamesList(true);
        });
      });
      $("contestRefresh").addEventListener("click", () => loadContestManagement());
      $("contestChannelRefresh").addEventListener("click", () => loadContestChannels());
      $("contestCreate").addEventListener("click", () => createContest());
      $("contestEmojiSelect").addEventListener("change", () => updateContestChannelPreview());
      $("contestChannelName").addEventListener("input", () => updateContestChannelPreview());
      $("contestCreateChannelOpen").addEventListener("click", () => {
        $("contestChannelModal").classList.add("show");
        loadContestChannels();
      });
      $("contestChannelClose").addEventListener("click", () => {
        $("contestChannelModal").classList.remove("show");
      });
      $("contestChannelModal").addEventListener("click", (event) => {
        if (event.target === $("contestChannelModal")){
          $("contestChannelModal").classList.remove("show");
        }
      });
      $("contestPanel").addEventListener("click", (event) => {
        const btn = event.target.closest(".contest-init");
        if (!btn) return;
        const channelId = btn.dataset.channel || "";
        if (channelId){
          $("contestChannel").value = channelId;
          setContestCreateStatus("Channel selected. Fill out details and create.", "ok");
        }
      });
      $("tarotClaimsRefresh").addEventListener("click", () => {
        loadTarotClaimsDecks();
        loadTarotClaimsChannels();
      });
      $("tarotClaimsPost").addEventListener("click", () => postTarotClaims());
      $("contestChannelCreate").addEventListener("click", async () => {
        try{
          const channelId = await createContestChannel();
          if (channelId){
            $("contestChannel").value = channelId;
          }
          $("contestChannelModal").classList.remove("show");
          await loadContestManagement();
        }catch(err){
          // status already handled
        }
      });

      let bingoRefreshTimer = null;
      function ensureBingoPolling(){
        if (bingoRefreshTimer){
          return;
        }
        bingoRefreshTimer = setInterval(() => {
          const gid = getGameId();
          if (!gid){
            return;
          }
          if ($("bingoPanel").classList.contains("hidden")){
            return;
          }
          refreshBingo();
        }, 3000);
      }

      function contestStatus(meta){
        if (!meta){
          return "unknown";
        }
        const raw = (meta.status || meta.state || meta.phase || "").toString().toLowerCase();
        if (["ended","closed","finished","complete","archived"].includes(raw)){
          return "ended";
        }
        if (["active","open","running","live","ongoing"].includes(raw)){
          return "active";
        }
        if (meta.ended === true || meta.closed === true || meta.finished === true){
          return "ended";
        }
        if (meta.active === false || meta.is_active === false || meta.open === false){
          return "ended";
        }
        return "active";
      }

      function setContestChannelStatus(msg, kind){
        const el = $("contestChannelStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function sanitizeChannelLabel(value){
        return String(value || "")
          .trim()
          .toLowerCase()
          .replace(/\s+/g, "-")
          .replace(/[^a-z0-9\-]/g, "");
      }

      function updateContestChannelPreview(){
        const emoji = ($("contestEmojiSelect") && $("contestEmojiSelect").value) || "*";
        const name = sanitizeChannelLabel($("contestChannelName").value || "elfoween") || "elfoween";
        const preview = `${emoji} | ${name}`;
        const el = $("contestChannelPreview");
        if (el){
          el.textContent = preview;
        }
        return preview;
      }

      function setContestCreateStatus(msg, kind){
        const el = $("contestCreateStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setTarotClaimsStatus(msg, kind){
        const el = $("tarotClaimsStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      async function loadTarotClaimsDecks(){
        const select = $("tarotClaimsDeck");
        if (!select) return;
        select.innerHTML = `<option value="">Loading...</option>`;
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          const decks = data.decks || [];
          const filtered = filterDecksByPurpose(decks, "tarot");
          const visibleDecks = filtered.length ? filtered : decks;
          select.innerHTML = "";
          visibleDecks.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.deck_id;
            opt.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            select.appendChild(opt);
          });
          if (!visibleDecks.length){
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No decks found.";
            select.appendChild(opt);
          }
        }catch(err){
          select.innerHTML = `<option value="">Failed to load decks</option>`;
          setTarotClaimsStatus(err.message, "err");
        }
      }

      async function loadTarotClaimsChannels(){
        const select = $("tarotClaimsChannel");
        if (!select) return;
        select.innerHTML = `<option value="">Loading...</option>`;
        try{
          const data = await jsonFetch("/discord/channels", {method:"GET"}, true);
          const channels = data.channels || [];
          select.innerHTML = "";
          channels.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.id;
            const parts = [];
            if (c.guild_name) parts.push(c.guild_name);
            if (c.category) parts.push(c.category);
            const label = parts.length ? `${parts.join(" / ")} / #${c.name}` : `#${c.name}`;
            opt.textContent = label;
            select.appendChild(opt);
          });
          if (!channels.length){
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No channels found.";
            select.appendChild(opt);
          }
        }catch(err){
          select.innerHTML = `<option value="">Failed to load channels</option>`;
          setTarotClaimsStatus(err.message, "err");
        }
      }

      async function postTarotClaims(){
        const deckId = $("tarotClaimsDeck").value || "";
        const channelId = $("tarotClaimsChannel").value || "";
        const claimLimit = Number($("tarotClaimsLimit").value || 2);
        if (!deckId){
          setTarotClaimsStatus("Pick a deck first.", "err");
          return;
        }
        if (!channelId){
          setTarotClaimsStatus("Pick a channel first.", "err");
          return;
        }
        setTarotClaimsStatus("Posting TarotCards board...", "");
        try{
          await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deckId) + "/claims/post", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({channel_id: channelId, claim_limit: claimLimit})
          }, true);
          setTarotClaimsStatus("TarotCards board posted.", "ok");
        }catch(err){
          setTarotClaimsStatus(err.message, "err");
        }
      }

      async function loadContestChannels(){
        const select = $("contestChannel");
        const templateSelect = $("contestTemplateChannel");
        if (!select) return;
        select.innerHTML = `<option value="">Loading...</option>`;
        if (templateSelect){
          templateSelect.innerHTML = `<option value="">Loading...</option>`;
        }
        try{
          const data = await jsonFetch("/discord/channels", {method:"GET"}, true);
          const channels = data.channels || [];
          select.innerHTML = "";
          if (templateSelect){
            templateSelect.innerHTML = "";
            const none = document.createElement("option");
            none.value = "";
            none.textContent = "(no template)";
            templateSelect.appendChild(none);
          }
          channels.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.id;
            const parts = [];
            if (c.guild_name) parts.push(c.guild_name);
            if (c.category) parts.push(c.category);
            const label = parts.length ? `${parts.join(" / ")} / #${c.name}` : `#${c.name}`;
            opt.textContent = label;
            select.appendChild(opt);
            if (templateSelect){
              const clone = document.createElement("option");
              clone.value = c.id;
              clone.textContent = label;
              templateSelect.appendChild(clone);
            }
          });
          if (!channels.length){
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No channels found.";
            select.appendChild(opt);
            if (templateSelect){
              const opt2 = document.createElement("option");
              opt2.value = "";
              opt2.textContent = "No channels found.";
              templateSelect.appendChild(opt2);
            }
          }
        }catch(err){
          select.innerHTML = `<option value="">Failed to load channels</option>`;
          if (templateSelect){
            templateSelect.innerHTML = `<option value="">Failed to load channels</option>`;
          }
          setContestCreateStatus(err.message, "err");
        }
      }

      async function createContestChannel(){
        const name = updateContestChannelPreview();
        const templateId = $("contestTemplateChannel").value || "";
        setContestChannelStatus("Creating channel...", "");
        try{
          const data = await jsonFetch("/api/contests/channel", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              name,
              category_id: CONTEST_CATEGORY_ID,
              template_channel_id: templateId || undefined
            })
          }, true);
          setContestChannelStatus(`Channel created: ${data.name}`, "ok");
          await loadContestChannels();
          $("contestChannel").value = String(data.channel_id || "");
          return String(data.channel_id || "");
        }catch(err){
          setContestChannelStatus(err.message, "err");
          throw err;
        }
      }

      let ownerFilter = "all";
      let ownerFilterData = {owner: "", cards: [], called: [], header: ""};

      async function loadGallerySettings(){
        try{
          const data = await jsonFetch("/api/gallery/settings", {method:"GET"}, true);
          const channelId = data.upload_channel_id ? String(data.upload_channel_id) : "";
          const select = $("galleryUploadChannel");
          if (select && channelId){
            select.value = channelId;
          }
          setGalleryChannelStatus(channelId ? "Upload channel set." : "Pick a channel to use for uploads.", channelId ? "ok" : "");
          const flairEl = $("galleryFlairText");
          if (flairEl){
            flairEl.value = String(data.flair_text || "");
          }
          const inspEveryEl = $("galleryInspirationEvery");
          if (inspEveryEl){
            inspEveryEl.value = data.inspiration_every ? String(data.inspiration_every) : "";
          }
          const inspTextEl = $("galleryInspirationText");
          if (inspTextEl){
            if (Array.isArray(data.inspiration_texts)){
              inspTextEl.value = data.inspiration_texts.join("\n");
            }else{
              inspTextEl.value = String(data.inspiration_texts || "");
            }
          }
          const messageTitleEl = $("galleryMessageTitle");
          if (messageTitleEl){
            messageTitleEl.value = String(data.message_title || "");
          }
          const messageBodyEl = $("galleryMessageBody");
          if (messageBodyEl){
            messageBodyEl.value = String(data.message_body || "");
          }
          setStatusText("galleryFlairStatus", "Ready.", "");
          setStatusText("galleryLayoutStatus", "Ready.", "");
        }catch(err){
          setGalleryChannelStatus(err.message, "err");
        }
      }

      async function loadGalleryChannels(){
        const select = $("galleryUploadChannel");
        const templateSelect = $("galleryChannelTemplate");
        const importSelect = $("galleryImportChannel");
        if (!select) return;
        select.innerHTML = `<option value="">Loading...</option>`;
        if (templateSelect){
          templateSelect.innerHTML = `<option value="">Loading...</option>`;
        }
        if (importSelect){
          importSelect.innerHTML = `<option value="">Loading...</option>`;
        }
        try{
          const data = await jsonFetch("/discord/channels", {method:"GET"}, true);
          const channels = data.channels || [];
          select.innerHTML = "";
          if (templateSelect){
            templateSelect.innerHTML = "";
            const none = document.createElement("option");
            none.value = "";
            none.textContent = "(no template)";
            templateSelect.appendChild(none);
          }
          if (importSelect){
            importSelect.innerHTML = "";
            const none = document.createElement("option");
            none.value = "";
            none.textContent = "(select channel)";
            importSelect.appendChild(none);
          }
          channels.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.id;
            const parts = [];
            if (c.guild_name) parts.push(c.guild_name);
            if (c.category) parts.push(c.category);
            const label = parts.length ? `${parts.join(" / ")} / #${c.name}` : `#${c.name}`;
            opt.textContent = label;
            select.appendChild(opt);
            if (templateSelect){
              const clone = document.createElement("option");
              clone.value = c.id;
              clone.textContent = label;
              templateSelect.appendChild(clone);
            }
            if (importSelect){
              const clone = document.createElement("option");
              clone.value = c.id;
              clone.textContent = label;
              importSelect.appendChild(clone);
            }
          });
          if (!channels.length){
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "No channels found.";
            select.appendChild(opt);
            if (templateSelect){
              const opt2 = document.createElement("option");
              opt2.value = "";
              opt2.textContent = "No channels found.";
              templateSelect.appendChild(opt2);
            }
            if (importSelect){
              const opt3 = document.createElement("option");
              opt3.value = "";
              opt3.textContent = "No channels found.";
              importSelect.appendChild(opt3);
            }
          }
        }catch(err){
          select.innerHTML = `<option value="">Failed to load channels</option>`;
          if (templateSelect){
            templateSelect.innerHTML = `<option value="">Failed to load channels</option>`;
          }
          if (importSelect){
            importSelect.innerHTML = `<option value="">Failed to load channels</option>`;
          }
          setGalleryChannelStatus(err.message, "err");
        }
      }

      function setGalleryChannelStatus(msg, kind){
        const el = $("galleryChannelStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function setGalleryImportStatus(msg, kind){
        const el = $("galleryImportStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      async function createContest(){
        let channelId = $("contestChannel").value;
        if (!channelId){
          setContestCreateStatus("Pick a channel first.", "err");
          return;
        }
        const body = {
          channel_id: channelId,
          title: $("contestTitle").value.trim(),
          description: $("contestDescription").value.trim(),
          rules: $("contestRules").value.trim(),
          deadline: $("contestDeadline").value.trim(),
          vote_emoji: $("contestEmoji").value.trim()
        };
        setContestCreateStatus("Creating contest...", "");
        try{
          const res = await jsonFetch("/api/contests/create", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
          }, true);
          setContestCreateStatus(`Contest created in channel ${res.channel_id}.`, "ok");
          await loadContestManagement();
        }catch(err){
          setContestCreateStatus(err.message, "err");
        }
      }

      async function loadContestManagement(){
        const allEl = $("contestAllList");
        const endedEl = $("contestEndedList");
        allEl.textContent = "Loading contests...";
        endedEl.textContent = "Loading contests...";
        try{
          const list = await jsonFetch("/contests", {method:"GET"}, true);
          const channels = list.channels || [];
          if (!channels.length){
            allEl.textContent = "No contests yet.";
            endedEl.textContent = "No ended contests yet.";
            return;
          }
          const details = await Promise.all(channels.map(async (id) => {
            try{
              return await jsonFetch("/contests/" + encodeURIComponent(id), {method:"GET"}, true);
            }catch(err){
              return {channel_id: id, error: err.message, exists: false};
            }
          }));
          const allCards = [];
          const endedCards = [];
          details.forEach(info => {
            const channelId = info.channel_id || info.channel || "";
            const meta = info.meta || null;
            const counts = info.counts || {};
            const status = contestStatus(meta);
            const name = meta ? (meta.name || meta.title || meta.contest_name || meta.label || "") : "";
            const channelName = meta ? (meta.channel_name || meta.channel || meta.channel_title || "") : "";
            const label = name || channelName ? (name || channelName) : `Contest ${channelId}`;
            const entries = counts.entries !== undefined ? `${counts.entries} entries` : "entries unknown";
            const statusLabel = status === "ended" ? "Ended" : status === "active" ? "Active" : "Unknown";
            const error = info.exists === false ? (info.error || "contest db missing") : info.error;
            const deadline = meta ? (meta.deadline || meta.ends_at || meta.end || "") : "";
            const deadlineLine = deadline ? `<div class=\"muted\">Deadline: ${deadline}</div>` : "";
            let errorLine = "";
            if (error){
              const hint = error.includes("contest db") ? "Contest database missing. Initialize to create metadata." : error;
              const action = channelId ? `<button class=\"btn-ghost contest-init\" data-channel=\"${channelId}\">Initialize</button>` : "";
              const actionLine = action ? `<div class=\"contest-actions\">${action}</div>` : "";
              errorLine = `<div class=\"status alert\">${hint}</div>${actionLine}`;
            }
            const card = `<div class=\"list-card\"><strong>${label}</strong><div class=\"muted\">${statusLabel} - ${entries}</div>${deadlineLine}${errorLine}</div>`;
            if (status === "ended"){
              endedCards.push(card);
            } else {
              allCards.push(card);
            }
          });
          allEl.innerHTML = allCards.length ? allCards.join("") : "No active contests.";
          endedEl.innerHTML = endedCards.length ? endedCards.join("") : "No ended contests yet.";
        }catch(err){
          allEl.textContent = "Failed to load contests.";
          endedEl.textContent = "Failed to load contests.";
          setStatus(err.message, "err");
        }
      }

      function updateBingoCreatePayload(){
        const el = $("bCreatePayload");
        if (!el){
          return;
        }
        const channelId = $("bChannelSelect").value || $("bChannel").value || "?";
        const createdBy = $("bCreatedBy").value || "?";
        const channelLabel = $("bChannelSelect").selectedOptions.length
          ? $("bChannelSelect").selectedOptions[0].textContent
          : "";
        const label = channelLabel ? ` (${channelLabel})` : "";
        el.textContent = `Payload preview: channel_id=${channelId}${label}, created_by=${createdBy}`;
      }

      
      // Bingo owner linking (XIVAuth)
      let bingoUsersCache = [];
      let bingoLinkOwnerName = "";

      function showBingoOwnerLinkModal(show){
        const modal = $("bOwnerLinkModal");
        if (!modal) return;
        modal.classList.toggle("show", !!show);
      }

      function renderBingoUserSelect(){
        const sel = $("bOwnerLinkSelect");
        if (!sel) return;
        const q = ($("bOwnerLinkFilter")?.value || "").trim().toLowerCase();
        const opts = (bingoUsersCache || []).map(u => {
          const id = u.id;
          if (!id) return "";
          const label = `${u.xiv_username || "?"}${u.world ? " @ " + u.world : ""} (id:${id})`;
          const hay = label.toLowerCase();
          if (q && !hay.includes(q)) return "";
          return `<option value="${escapeHtml(String(id))}">${escapeHtml(label)}</option>`;
        }).filter(Boolean);
        sel.innerHTML = opts.join("");
      }

      async function loadBingoUsers(){
        try{
          const data = await jsonFetch("/bingo/users", {method:"GET"});
          bingoUsersCache = data.users || [];
        }catch(_e){
          bingoUsersCache = [];
        }
        renderBingoUserSelect();
      }

      function openBingoOwnerLinkModal(ownerName){
        bingoLinkOwnerName = ownerName || "";
        const label = $("bOwnerLinkOwner");
        if (label) label.textContent = bingoLinkOwnerName || "-";
        setStatusText("bOwnerLinkStatus", "Pick a user to link.", "");
        showBingoOwnerLinkModal(true);
        loadBingoUsers();
      }

      on("bOwnerLinkClose", "click", () => showBingoOwnerLinkModal(false));
      on("bOwnerLinkModal", "click", (ev) => { if (ev.target === $("bOwnerLinkModal")) showBingoOwnerLinkModal(false); });
      on("bOwnerLinkFilter", "input", () => renderBingoUserSelect());
      on("bOwnerLinkSave", "click", async () => {
        const gid = getGameId();
        const sel = $("bOwnerLinkSelect");
        const userId = sel ? (sel.value || "") : "";
        if (!gid){ setStatusText("bOwnerLinkStatus", "Select a game first.", "err"); return; }
        if (!bingoLinkOwnerName){ setStatusText("bOwnerLinkStatus", "Missing owner.", "err"); return; }
        if (!userId){ setStatusText("bOwnerLinkStatus", "Pick a user.", "err"); return; }
        setStatusText("bOwnerLinkStatus", "Linking...", "");
        try{
          await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owners/link", {
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body: JSON.stringify({owner_name: bingoLinkOwnerName, user_id: parseInt(userId, 10)})
          });
          setStatusText("bOwnerLinkStatus", "Linked.", "ok");
          showToast("Bingo owner linked.", "ok");
          await loadOwnersForGame();
          setTimeout(() => showBingoOwnerLinkModal(false), 250);
        }catch(err){
          setStatusText("bOwnerLinkStatus", err.message || String(err), "err");
        }
      });
function getOwnerClaimStatus(ownerName){
        const claims = (currentGame && Array.isArray(currentGame.claims)) ? currentGame.claims : [];
        const pending = claims.some(c => c && c.owner_name === ownerName && c.pending);
        const denied = claims.some(c => c && c.owner_name === ownerName && c.denied);
        const approved = claims.some(c => c && c.owner_name === ownerName && !c.pending && !c.denied);
        if (pending) return {label: "Claim pending", cls: "warn"};
        if (approved) return {label: "Claim approved", cls: "good"};
        if (denied) return {label: "Claim denied", cls: "bad"};
        return {label: "No claim", cls: ""};
      }

      function renderOwnersList(owners){
        const el = $("bOwners");
        const empty = $("bOwnersEmpty");
        if (!Array.isArray(owners) || owners.length === 0){
          el.textContent = "";
          if (empty) empty.style.display = "flex";
          return;
        }
        if (empty) empty.style.display = "none";

        const table = document.createElement("table");
        table.className = "owners-table";
        table.innerHTML = `
          <thead>
            <tr>
              <th style="text-align:left">Player</th>
              <th style="text-align:left">XIVAuth</th>
              <th style="width:90px">Cards</th>
              <th style="width:180px">Claim</th>
              <th style="width:230px;text-align:right">Actions</th>
            </tr>
          </thead>
          <tbody></tbody>
        `;
        const tbody = table.querySelector("tbody");

        owners.forEach(o => {
          const ownerName = o.owner_name || "";
          const claim = getOwnerClaimStatus(ownerName);
          const badgeClass = claim.cls ? `status-badge ${claim.cls}` : "status-badge";
          const xiv = o.xiv || null;
          const xivLabel = xiv && (xiv.xiv_username || xiv.world)
            ? `${xiv.xiv_username || ""}${xiv.world ? " @ " + xiv.world : ""}`.trim()
            : "-";
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><strong>${escapeHtml(ownerName)}</strong></td>
            <td class="muted">${escapeHtml(xivLabel)}</td>
            <td>${escapeHtml(o.cards)}</td>
            <td><span class="${badgeClass}">${escapeHtml(claim.label)}</span></td>
            <td>
              <div class="owner-actions">
                <button class="btn-ghost icon-action owner-copy-btn" title="Copy player link" aria-label="Copy player link">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 1H6a2 2 0 0 0-2 2v12h2V3h10V1zm3 4H10a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H10V7h9v14z"/></svg>
                </button>
                <button class="btn-ghost icon-action owner-link-btn" title="Link to XIVAuth" aria-label="Link to XIVAuth">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.9 12a5 5 0 0 1 5-5h4v2h-4a3 3 0 1 0 0 6h4v2h-4a5 5 0 0 1-5-5zm7.1 1h2v-2h-2v2zm4-6h-4V5h4a5 5 0 0 1 0 10h-4v-2h4a3 3 0 1 0 0-6z"/></svg>
                </button>
                <button class="btn-ghost mini-btn owner-view-btn">Cards</button>
              </div>
            </td>
          `;
          const viewBtn = tr.querySelector(".owner-view-btn");
          const copyBtn = tr.querySelector(".owner-copy-btn");
          const linkBtn = tr.querySelector(".owner-link-btn");
          if (viewBtn) viewBtn.setAttribute("data-owner", ownerName);
          if (copyBtn) copyBtn.setAttribute("data-token", o.token || "");
          if (copyBtn) copyBtn.setAttribute("data-owner", ownerName);
          if (linkBtn) linkBtn.setAttribute("data-owner", ownerName);

          if (viewBtn){
            viewBtn.addEventListener("click", () => {
              const name = viewBtn.getAttribute("data-owner") || "";
              if (!name) return;
              const ownerInput = $("bOwner");
              if (ownerInput) ownerInput.value = name;
              updateBingoBuyState(currentGame, currentGame ? currentGame.called : []);
              loadOwnerCards(name);
              $("bOwnerModal").classList.add("show");
            });
          }

          if (copyBtn){
            copyBtn.addEventListener("click", async (ev) => {
              ev.stopPropagation();
              const gid = getGameId();
              const tokenInline = copyBtn.getAttribute("data-token") || "";
              const name = copyBtn.getAttribute("data-owner") || ownerName;
              if (!gid || !name){
                setBingoStatus("Select a game and player first.", "err");
                return;
              }
              try{
                let token = tokenInline;
                if (!token){
                  const data = await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owner/" + encodeURIComponent(name) + "/token", {method:"GET"});
                  token = data.token || "";
                }
                const base = getBase();
                const url = new URL("/bingo/owner?token=" + encodeURIComponent(token || ""), base).toString();
                await navigator.clipboard.writeText(url);
                setBingoStatus("Copied player link.", "ok");
              }catch(_err){
                setBingoStatus("Copy failed.", "err");
              }
            });
          }

          if (linkBtn){
            linkBtn.addEventListener("click", async (ev) => {
              ev.stopPropagation();
              const name = linkBtn.getAttribute("data-owner") || "";
              if (!name){
                setBingoStatus("Missing owner name.", "err");
                return;
              }
              openBingoOwnerLinkModal(name);
            });
          }

          if (tbody) tbody.appendChild(tr);
        });

        el.innerHTML = "";
        el.appendChild(table);
      }

      async function loadOwnersForGame(){
        const gid = getGameId();
        $("bOwnerCards").textContent = "No tickets loaded.";
        if (!gid){
          $("bOwners").textContent = "";
          const empty = $("bOwnersEmpty");
          if (empty) empty.style.display = "flex";
          return;
        }
        try{
          const data = await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owners", {method:"GET"});
          renderOwnersList(data.owners || []);
        }catch(err){
          setBingoStatus(err.message, "err");
        }
      }

      function renderOwnerCards(owner, cards, called, header){
        const el = $("bOwnerCards");
        const summary = $("bOwnerSummary");
        ownerFilterData = {owner, cards, called, header};
        if (summary){
          const path = summary.querySelector(".context-path");
          const meta = summary.querySelector(".context-meta");
          if (path) path.textContent = `Viewing cards for: ${owner || "-"}`;
          if (meta) meta.textContent = `Total cards: ${Array.isArray(cards) ? cards.length : 0}`;
        }
        let totalCalledCells = 0;
        let totalCells = 0;
        if (!Array.isArray(cards) || cards.length === 0){
          el.textContent = "No tickets for this player.";
          return;
        }
        el.innerHTML = "";
        const calledSet = new Set(Array.isArray(called) ? called : []);
        const headerText = (header || "BING").slice(0, 4).split("");
        while (headerText.length < 4) headerText.push(" ");
        cards.forEach((card, index) => {
          const wrap = document.createElement("div");
          wrap.className = "owner-card";
          wrap.classList.add("collapsed");
          const headerRow = document.createElement("div");
          headerRow.className = "owner-card-header";
          const titleWrap = document.createElement("div");
          const title = document.createElement("div");
          title.className = "owner-card-title";
          title.textContent = `Card ${index + 1}`;
          const id = document.createElement("div");
          id.className = "owner-card-id";
          const cardId = String(card.card_id || "");
          const suffix = cardId.length > 4 ? cardId.slice(-4) : cardId;
          id.textContent = suffix ? `...${suffix}` : "-";
          if (cardId){
            id.title = cardId;
          }
          titleWrap.appendChild(title);
          titleWrap.appendChild(id);
          const summaryWrap = document.createElement("div");
          summaryWrap.className = "owner-card-summary";
          const countEl = document.createElement("div");
          countEl.className = "owner-card-count";
          let numbers = card.numbers;
          if (typeof numbers === "string"){
            try{
              numbers = JSON.parse(numbers);
            }catch(err){
              numbers = null;
            }
          }
          if (!Array.isArray(numbers)){
            numbers = Array.isArray(card.grid)
              ? card.grid
              : (Array.isArray(card.card) ? card.card : []);
          }
          let cardCalled = 0;
          let cardTotal = 0;
          numbers.forEach((row) => {
            (row || []).forEach((value) => {
              cardTotal += 1;
              if (calledSet.has(value)){
                cardCalled += 1;
              }
            });
          });
          totalCells += cardTotal;
          totalCalledCells += cardCalled;
          countEl.textContent = `${cardCalled} / ${cardTotal || 0} called`;
          const progress = document.createElement("div");
          progress.className = "owner-card-progress";
          const fill = document.createElement("div");
          fill.className = "owner-card-progress-fill";
          const ratio = cardTotal ? (cardCalled / cardTotal) : 0;
          fill.style.width = `${Math.round(ratio * 100)}%`;
          progress.appendChild(fill);
          summaryWrap.appendChild(countEl);
          summaryWrap.appendChild(progress);
          if (cardTotal && cardCalled === cardTotal){
            const flag = document.createElement("span");
            flag.className = "owner-card-flag complete";
            flag.textContent = "Complete";
            summaryWrap.appendChild(flag);
          }else if (cardTotal && ratio >= 0.75){
            const flag = document.createElement("span");
            flag.className = "owner-card-flag near";
            flag.textContent = "Near-win";
            summaryWrap.appendChild(flag);
          }
          const toggle = document.createElement("button");
          toggle.type = "button";
          toggle.className = "owner-card-toggle";
          toggle.setAttribute("aria-label", "Collapse card");
          toggle.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10l5 5 5-5z"/></svg>';
          headerRow.appendChild(titleWrap);
          headerRow.appendChild(summaryWrap);
          headerRow.appendChild(toggle);
          const body = document.createElement("div");
          body.className = "owner-card-body";
          const cardHeader = document.createElement("div");
          cardHeader.className = "bingo-header";
          headerText.forEach((h, idx) => {
            const label = document.createElement("div");
            label.textContent = h;
            if (idx > 0){
              label.style.borderLeft = "1px solid rgba(255,255,255,.08)";
            }
            cardHeader.appendChild(label);
          });
          body.appendChild(cardHeader);
          const grid = document.createElement("div");
          grid.className = "bingo-grid";
          if (!numbers.length){
            const empty = document.createElement("div");
            empty.className = "status";
            empty.textContent = "No numbers available for this card.";
            body.appendChild(empty);
          }
          numbers.forEach((row, r) => {
            (row || []).forEach((value, c) => {
              const cell = document.createElement("div");
              cell.className = "bingo-cell";
              const isCalled = calledSet.has(value);
              const marked = (card.marks && card.marks[r] && card.marks[r][c]) || isCalled;
              if (marked) cell.classList.add("marked");
              if (isCalled) cell.classList.add("called");
              if (ownerFilter === "called" && !isCalled){
                cell.classList.add("filtered-out");
              }
              if (ownerFilter === "uncalled" && isCalled){
                cell.classList.add("filtered-out");
              }
              if (c > 0){
                cell.style.borderLeft = "1px solid rgba(255,255,255,.08)";
              }
              cell.textContent = value;
              if (isCalled){
                const mark = document.createElement("span");
                mark.className = "cell-mark";
                mark.textContent = "x";
                cell.appendChild(mark);
              }
              cell.onclick = () => {
                renderCard(card, called, header);
              };
              grid.appendChild(cell);
            });
          });
          if (numbers.length){
            body.appendChild(grid);
          }
          headerRow.addEventListener("click", () => {
            const isCollapsed = wrap.classList.contains("collapsed");
            const cardsEls = el.querySelectorAll(".owner-card");
            cardsEls.forEach((cardEl) => {
              cardEl.classList.add("collapsed");
            });
            if (isCollapsed){
              wrap.classList.remove("collapsed");
            }
          });
          toggle.addEventListener("click", (ev) => {
            ev.stopPropagation();
            const isCollapsed = wrap.classList.contains("collapsed");
            const cardsEls = el.querySelectorAll(".owner-card");
            cardsEls.forEach((cardEl) => {
              cardEl.classList.add("collapsed");
            });
            if (isCollapsed){
              wrap.classList.remove("collapsed");
            }
          });
          wrap.appendChild(headerRow);
          wrap.appendChild(body);
          el.appendChild(wrap);
        });
        const calledBtn = $("bOwnerFilterCalled");
        const uncalledBtn = $("bOwnerFilterUncalled");
        if (calledBtn && uncalledBtn){
          calledBtn.textContent = `Called (${totalCalledCells})`;
          uncalledBtn.textContent = `Uncalled (${Math.max(0, totalCells - totalCalledCells)})`;
          calledBtn.classList.toggle("active", ownerFilter === "called");
          uncalledBtn.classList.toggle("active", ownerFilter === "uncalled");
        }
        el.dataset.filter = ownerFilter;
      }
      async function loadOwnerCards(ownerName){
        const gid = getGameId();
        if (!gid || !ownerName){
          setBingoStatus("Enter game id and owner name.", "err");
          return;
        }
        ownerFilter = "all";
        try{
          const state = await jsonFetch("/bingo/" + encodeURIComponent(gid), {method:"GET"}, false);
          const data = await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owner/" + encodeURIComponent(ownerName) + "/cards", {method:"GET"}, false);
          renderBingoState(state);
          renderOwnerCards(ownerName, data.cards || [], state.game && state.game.called, state.game && state.game.header);
          setBingoStatus("Tickets loaded.", "ok");
        }catch(err){
          setBingoStatus(err.message, "err");
        }
      }

      // owner list loads automatically when selecting a game

      $("bCloseCreate").addEventListener("click", () => {
        $("bCreateModal").classList.remove("show");
      });
      $("deckCreateClose").addEventListener("click", () => {
        $("deckCreateModal").classList.remove("show");
      });
      $("mediaClose").addEventListener("click", () => {
        $("mediaModal").classList.remove("show");
      });
      $("artistClose").addEventListener("click", () => {
        $("artistModal").classList.remove("show");
      });
      $("calendarClose").addEventListener("click", () => {
        $("calendarModal").classList.remove("show");
      });
      $("galleryClose").addEventListener("click", () => {
        $("galleryModal").classList.remove("show");
      });
      $("galleryModal").addEventListener("click", (event) => {
        if (event.target === $("galleryModal")){
          $("galleryModal").classList.remove("show");
        }
      });
      $("galleryImportOpen").addEventListener("click", () => {
        $("galleryImportModal").classList.add("show");
        setGalleryImportStatus("Pick a channel to import.", "");
        loadGalleryChannels();
      });
      $("galleryImportClose").addEventListener("click", () => {
        $("galleryImportModal").classList.remove("show");
      });
      $("galleryImportModal").addEventListener("click", (event) => {
        if (event.target === $("galleryImportModal")){
          $("galleryImportModal").classList.remove("show");
        }
      });
      $("galleryImportRefresh").addEventListener("click", () => loadGalleryChannels());
      $("galleryImportRun").addEventListener("click", async () => {
        const channelId = $("galleryImportChannel").value || "";
        if (!channelId){
          setGalleryImportStatus("Pick a channel first.", "err");
          return;
        }
        setGalleryImportStatus("Importing...", "");
        const originType = $("galleryImportOriginType").value.trim();
        const originLabel = $("galleryImportOriginLabel").value.trim();
        try{
          const res = await jsonFetch("/api/gallery/import-channel", {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
              channel_id: channelId,
              origin_type: originType,
              origin_label: originLabel
            })
          }, true);
          const imported = res.imported || 0;
          const skipped = res.skipped || 0;
          setGalleryImportStatus(`Imported ${imported}. Skipped ${skipped}.`, "ok");
        }catch(err){
          setGalleryImportStatus(err.message, "err");
        }
      });
      $("bOwnerFilterCalled").addEventListener("click", () => {
        ownerFilter = ownerFilter === "called" ? "all" : "called";
        renderOwnerCards(
          ownerFilterData.owner,
          ownerFilterData.cards,
          ownerFilterData.called,
          ownerFilterData.header
        );
      });
      $("bOwnerFilterUncalled").addEventListener("click", () => {
        ownerFilter = ownerFilter === "uncalled" ? "all" : "uncalled";
        renderOwnerCards(
          ownerFilterData.owner,
          ownerFilterData.cards,
          ownerFilterData.called,
          ownerFilterData.header
        );
      });
      $("galleryChannelRefresh").addEventListener("click", () => loadGalleryChannels());
      $("galleryChannelSave").addEventListener("click", async () => {
        const channelId = $("galleryUploadChannel").value || "";
        try{
          await jsonFetch("/api/gallery/settings", {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({upload_channel_id: channelId || null})
          }, true);
          setGalleryChannelStatus("Upload channel saved.", "ok");
        }catch(err){
          setGalleryChannelStatus(err.message, "err");
        }
      });
      // Flair text UI removed
      $("galleryLayoutSave").addEventListener("click", async () => {
        const every = $("galleryInspirationEvery")?.value || "";
        const text = $("galleryInspirationText")?.value || "";
        const messageTitle = $("galleryMessageTitle")?.value || "";
        const messageBody = $("galleryMessageBody")?.value || "";
        setStatusText("galleryLayoutStatus", "Saving...", "");
        try{
          await jsonFetch("/api/gallery/settings", {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
              inspiration_every: every ? parseInt(every, 10) : null,
              inspiration_texts: String(text || ""),
              message_title: String(messageTitle || "").trim(),
              message_body: String(messageBody || "").trim()
            })
          }, true);
          setStatusText("galleryLayoutStatus", "Layout saved.", "ok");
        }catch(err){
          setStatusText("galleryLayoutStatus", err.message, "err");
        }
      });

      $("galleryChannelCreate").addEventListener("click", async () => {
        const name = $("galleryChannelName").value.trim();
        const categoryId = $("galleryChannelCategory").value.trim();
        const templateId = $("galleryChannelTemplate").value || "";
        if (!name){
          setGalleryChannelStatus("Enter a channel name.", "err");
          return;
        }
        if (!categoryId){
          setGalleryChannelStatus("Enter a category ID.", "err");
          return;
        }
        setGalleryChannelStatus("Creating channel...", "");
        try{
          const data = await jsonFetch("/api/gallery/upload-channel", {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({
              name,
              category_id: categoryId,
              template_channel_id: templateId || undefined
            })
          }, true);
          setGalleryChannelStatus(`Channel created: ${data.name}`, "ok");
          await loadGalleryChannels();
          $("galleryUploadChannel").value = String(data.channel_id || "");
        }catch(err){
          setGalleryChannelStatus(err.message, "err");
        }
      });
      $("calendarRefresh").addEventListener("click", () => loadCalendarAdmin());
      $("calendarMonth").addEventListener("change", (ev) => {
        const month = parseInt(ev.target.value || "1", 10);
        const entry = calendarData.find(e => e.month === month) || calendarData[0];
        if (entry){
          applyCalendarSelection(entry);
        }
      });
      $("calendarPick").addEventListener("click", () => {
        librarySelectHandler = (item) => {
          calendarSelected.image = item.url || "";
          calendarSelected.title = item.title || item.name || "";
          calendarSelected.artist_id = item.artist_id || null;
          calendarSelected.artist_name = item.artist_name || "Forest";
          $("calendarTitle").value = calendarSelected.title;
          $("calendarArtist").textContent = calendarSelected.artist_name || "Forest";
          renderCalendarPreview();
        };
        showLibraryModal(true);
        loadLibrary("media");
      });
      $("calendarSave").addEventListener("click", async () => {
        const month = parseInt($("calendarMonth").value || "1", 10);
        const title = $("calendarTitle").value.trim();
        const payload = {
          month: month,
          image: calendarSelected.image || "",
          title: title,
          artist_id: calendarSelected.artist_id || ""
        };
        if (!payload.image){
          setCalendarStatus("Pick an image first.", "err");
          return;
        }
        try{
          await jsonFetch("/api/gallery/calendar", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
          });
          setCalendarStatus("Saved.", "ok");
          await loadCalendarAdmin();
        }catch(err){
          setCalendarStatus(err.message, "err");
        }
      });
      $("calendarClear").addEventListener("click", async () => {
        const month = parseInt($("calendarMonth").value || "1", 10);
        try{
          await jsonFetch("/api/gallery/calendar", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({month: month, image: ""})
          });
          calendarSelected.image = "";
          calendarSelected.title = "";
          calendarSelected.artist_id = null;
          calendarSelected.artist_name = "Forest";
          $("calendarTitle").value = "";
          $("calendarArtist").textContent = "Forest";
          renderCalendarPreview();
          setCalendarStatus("Cleared.", "ok");
          await loadCalendarAdmin();
        }catch(err){
          setCalendarStatus(err.message, "err");
        }
      });
      $("authRolesClose").addEventListener("click", () => {
        $("authRolesModal").classList.remove("show");
      });
      $("authRolesRefresh").addEventListener("click", () => loadAuthRoles());
      $("authTokensClose").addEventListener("click", () => {
        $("authTokensModal").classList.remove("show");
      });
      $("authTokensRefresh").addEventListener("click", () => loadAuthTokens());
      const authTempClose = $("authTempClose");
      if (authTempClose){
        authTempClose.addEventListener("click", () => {
          const modal = $("authTempModal");
          if (modal) modal.classList.remove("show");
        });
      }
      const authTempRole = $("authTempRole");
      if (authTempRole){
        authTempRole.addEventListener("change", (ev) => {
          updateAuthTempScopesPreview(ev.target.value || "");
        });
      }
      const authTempGenerate = $("authTempGenerate");
      if (authTempGenerate){
        authTempGenerate.addEventListener("click", async () => {
          const roleEl = $("authTempRole");
          const scopesEl = $("authTempScopes");
          if (!roleEl || !scopesEl){
            setAuthTempStatus("Temporary access UI not loaded.", "err");
            return;
          }
          const roleId = roleEl.value.trim();
          const scopesRaw = scopesEl.value.trim();
          let scopes = scopesRaw ? scopesRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
          if (!scopes.length && roleId && authRoleScopes && authRoleScopes[roleId]){
            scopes = (authRoleScopes[roleId] || []).map(s => String(s).trim()).filter(Boolean);
          }
          if (!roleId && scopes.length === 0){
            setAuthTempStatus("Select a role profile or provide scopes.", "err");
            return;
          }
          if (roleId && scopes.length === 0){
            setAuthTempStatus("Selected profile has no scopes. Add a scopes override.", "err");
            return;
          }
        try{
          setAuthTempStatus("Generating...", "");
          const payload = {
            role_ids: roleId ? [roleId] : [],
            scopes: scopes,
            ttl_seconds: 6 * 60 * 60
          };
          const res = await jsonFetch("/api/auth/temp-links", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
          });
          const urlInput = $("authTempUrl");
          if (urlInput) urlInput.value = res.link_url || "";
          setAuthTempStatus("Link ready.", "ok");
        }catch(err){
          setAuthTempStatus(err.message || "Failed to create link.", "err");
        }
      });
      }
      const authTempCopy = $("authTempCopy");
      if (authTempCopy){
        authTempCopy.addEventListener("click", async () => {
          const urlInput = $("authTempUrl");
          const url = urlInput ? urlInput.value.trim() : "";
          if (!url){
          setAuthTempStatus("No link to copy.", "err");
          return;
        }
        try{
          await navigator.clipboard.writeText(url);
          setAuthTempStatus("Link copied.", "ok");
        }catch(err){
          setAuthTempStatus("Copy failed.", "err");
        }
        });
      }
      on("adminVenueAssign", "click", async () => {
        const select = $("adminVenueSelect");
        const id = parseInt(select?.value || "0", 10) || 0;
        if (!id){
          setStatusText("adminVenueStatus", "Pick a venue first.", "err");
          return;
        }
        setStatusText("adminVenueStatus", "Saving...", "");
        try{
          const resp = await jsonFetch("/admin/venue/assign", {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({venue_id: id})
          }, true);
          if (resp.membership){
            setBrandVenue(resp.membership);
          }
          $("adminVenueModal")?.classList.remove("show");
          setStatusText("adminVenueStatus", "Assigned.", "ok");
        }catch(err){
          setStatusText("adminVenueStatus", err.message || "Failed to assign venue.", "err");
        }
      });
      on("adminVenueCreate", "click", async () => {
        const name = ($("adminVenueCreateName")?.value || "").trim();
        if (!name){
          setStatusText("adminVenueStatus", "Enter a venue name.", "err");
          return;
        }
        setStatusText("adminVenueStatus", "Creating...", "");
        try{
          const resp = await jsonFetch("/admin/venues/create", {
            method:"POST",
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({name})
          }, true);
          if (resp.membership){
            setBrandVenue(resp.membership);
          }
          $("adminVenueModal")?.classList.remove("show");
          setStatusText("adminVenueStatus", "Created.", "ok");
        }catch(err){
          setStatusText("adminVenueStatus", err.message || "Failed to create venue.", "err");
        }
      });
      $("authRolesList").addEventListener("change", (ev) => {
        const input = ev.target;
        if (!input || input.tagName !== "INPUT") return;
        const roleId = input.getAttribute("data-role");
        const scope = input.getAttribute("data-scope");
        if (!roleId || !scope) return;
        const current = new Set((authRoleScopes[roleId] || []).map(String));
        if (input.checked){
          if (scope === "*"){
            current.clear();
            current.add("*");
          } else {
            current.delete("*");
            current.add(scope);
          }
        } else {
          current.delete(scope);
        }
        if (current.size){
          authRoleScopes[roleId] = Array.from(current);
        } else {
          delete authRoleScopes[roleId];
        }
        updateAuthRoleIdsField();
        renderAuthRolesList(authRolesCache || []);
      });
      $("authRolesSave").addEventListener("click", async () => {
        try{
          await jsonFetch("/api/auth/roles", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({role_scopes: authRoleScopes})
          });
          setAuthRolesStatus("Saved.", "ok");
        }catch(err){
          setAuthRolesStatus(err.message, "err");
        }
      });
      // Role preview interactions
      const authPreviewRole = $("authPreviewRole");
      if (authPreviewRole){
        authPreviewRole.addEventListener("change", (ev) => {
          updateAuthPreviewScopesPreview(ev.target.value || "");
        });
      }
      const authPreviewStart = $("authPreviewStart");
      if (authPreviewStart){
        authPreviewStart.addEventListener("click", () => {
          const roleEl = $("authPreviewRole");
          const scopesEl = $("authPreviewScopes");
          if (!roleEl || !scopesEl){
            $("authPreviewStatus").textContent = "Preview UI not loaded.";
            $("authPreviewStatus").className = "status err";
            return;
          }
          const roleId = (roleEl.value || "").trim();
          const scopesRaw = (scopesEl.value || "").trim();
          let scopes = scopesRaw ? scopesRaw.split(",").map(s => s.trim()).filter(Boolean) : [];
          if (!scopes.length && roleId && authRoleScopes && authRoleScopes[roleId]){
            scopes = (authRoleScopes[roleId] || []).map(s => String(s).trim()).filter(Boolean);
          }
          if (!roleId && scopes.length === 0){
            $("authPreviewStatus").textContent = "Select a role profile or provide scopes.";
            $("authPreviewStatus").className = "status err";
            return;
          }
          if (roleId && scopes.length === 0){
            $("authPreviewStatus").textContent = "Selected profile has no scopes. Add a scopes override.";
            $("authPreviewStatus").className = "status err";
            return;
          }
          previewScopes = new Set(scopes);
          previewScopesActive = true;
          $("authPreviewStatus").textContent = `Preview on: ${scopes.join(", ")}`;
          $("authPreviewStatus").className = "status ok";
          // Trigger any UI gates to re-evaluate
          // Example: reload venues/events list
          loadEventsVenues(true);
          loadGamesListVenues(true);
        });
      }
      const authPreviewStop = $("authPreviewStop");
      if (authPreviewStop){
        authPreviewStop.addEventListener("click", () => {
          previewScopesActive = false;
          previewScopes = new Set();
          $("authPreviewStatus").textContent = "Preview off.";
          $("authPreviewStatus").className = "status";
          loadEventsVenues(true);
          loadGamesListVenues(true);
        });
      }
      $("bOwnerClose").addEventListener("click", () => {
        $("bOwnerModal").classList.remove("show");
      });
      $("bPurchaseClose").addEventListener("click", () => {
        $("bPurchaseModal").classList.remove("show");
      });
      $("bPurchaseCopy").addEventListener("click", () => {
        const link = $("bPurchaseLink").value || "";
        if (!link){
          return;
        }
        try{
          navigator.clipboard.writeText(link);
          $("bPurchaseStatus").textContent = "Link copied.";
        }catch(err){
          $("bPurchaseStatus").textContent = "Copy failed.";
        }
      });

      on("loginBtn", "click", () => {
        if (!apiKeyEl.value.trim()){
          loginStatusEl.textContent = "Enter your API key.";
          loginStatusEl.className = "status err";
          return;
        }
        saveSettings();
        document.getElementById("loginView").classList.add("hidden");
        document.getElementById("appView").classList.remove("hidden");
        setStatus("Welcome to Bingo Control.", "ok");
        initAuthenticatedSession();
      });
      if (overlayToggle){
        overlayToggle.addEventListener("change", () => {
          document.body.classList.toggle("overlay", overlayToggle.checked);
          overlayToggleBtn.classList.toggle("active", overlayToggle.checked);
          saveSettings();
        });
      }
      if (overlayToggleBtn){
        overlayToggleBtn.addEventListener("click", () => {
          if (!overlayToggle) return;
          overlayToggle.checked = !overlayToggle.checked;
          overlayToggle.dispatchEvent(new Event("change"));
        });
      }
      on("overlayExit", "click", () => {
        if (overlayToggle){
          overlayToggle.checked = false;
        }
        document.body.classList.remove("overlay");
        saveSettings();
      });
      on("uploadLibraryClose", "click", () => showLibraryModal(false));
      on("uploadLibraryRefresh", "click", () => loadLibrary(libraryKind));

      on("deckCreateBackPick", "click", () => {
        librarySelectHandler = (item) => {
          $("deckCreateBackPick").dataset.backUrl = item.url || "";
          $("deckCreateBackPick").dataset.artistId = item.artist_id || "";
          const preview = $("deckCreateBackPreview");
          if (preview){
            preview.innerHTML = '<span class="preview-label">Back</span>';
            if (item.url){
              const img = document.createElement("img");
              img.src = item.url;
              preview.appendChild(img);
            }
          }
          setTarotStatus(item.url ? "Deck back selected." : "Pick a deck back.", "ok");
        };
        showLibraryModal(true);
        loadLibrary("media");
      });

      on("deckCreateSuitPreset", "change", (ev) => {
        const value = ev.target.value || "custom";
        if (value === "custom"){
          return;
        }
        $("deckCreateSuitJson").value = formatSuitPresetJson(value);
      });
      $("deckCreateSuitJson").addEventListener("input", () => {
        if ($("deckCreateSuitPreset").value !== "custom"){
          $("deckCreateSuitPreset").value = "custom";
        }
      });
      $("deckEditSuitPreset").addEventListener("change", (ev) => {
        const value = ev.target.value || "custom";
        if (value === "custom"){
          return;
        }
        $("deckEditSuitJson").value = formatSuitPresetJson(value);
      });
      $("deckEditSuitJson").addEventListener("input", () => {
        if ($("deckEditSuitPreset").value !== "custom"){
          $("deckEditSuitPreset").value = "custom";
        }
      });

      $("deckCreateSubmit").addEventListener("click", async () => {
        const id = $("deckCreateId").value.trim();
        if (!id){
          setTarotStatus("Deck id is required.", "err");
          return;
        }
        const backUrl = $("deckCreateBackPick").dataset.backUrl || "";
        if (!backUrl){
          setTarotStatus("Pick a deck back before creating the deck.", "err");
          return;
        }
        const name = $("deckCreateName").value.trim();
        const purpose = $("deckCreatePurpose").value || "tarot";
        const theme = $("deckCreateTheme").value || "classic";
        const seedChoice = $("deckCreateSeed").value || "none";
        const perHouse = Number($("deckCreatePerHouse").value || 0);
        const crownCount = Number($("deckCreateCrown").value || 0);
        const artistId = $("deckCreateBackPick").dataset.artistId || "";
        let suits = null;
        try{
          suits = parseSuitJson($("deckCreateSuitJson").value);
        }catch(err){
          setTarotStatus(err.message, "err");
          return;
        }
        try{
          await jsonFetch("/api/tarot/decks", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              deck_id: id,
              name: name || undefined,
              purpose,
              theme,
              suits: suits && suits.length ? suits : []
            })
          }, true);
          await jsonFetch("/api/tarot/decks/" + encodeURIComponent(id) + "/back", {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({back_image: backUrl, artist_id: artistId || undefined})
          }, true);
          if (seedChoice === "dummy"){
            await jsonFetch("/api/tarot/decks/" + encodeURIComponent(id) + "/seed", {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({per_house: perHouse, crown_count: crownCount})
            }, true);
          } else if (seedChoice === "default"){
            await jsonFetch("/api/tarot/decks/" + encodeURIComponent(id) + "/seed-template", {
              method: "POST",
              headers: {"Content-Type": "application/json"}
            }, true);
          }
          await loadTarotDeckList(id);
          $("deckCreateModal").classList.remove("show");
          setTarotStatus("Deck created.", "ok");
          await loadTarotDeck();
        }catch(err){
          setTarotStatus(err.message, "err");
        }
      });

      $("taCardLibrary").addEventListener("click", () => {
        librarySelectHandler = (item) => {
          window.taUploadedImageUrl = item.url || "";
          $("taCardArtist").value = item.artist_id || "";
          if (window.taDeckData && window.taDeckData.cards){
            const card = window.taDeckData.cards.find(c => c.card_id === taSelectedCardId);
            if (card){
              card.image = window.taUploadedImageUrl;
              taRenderPreviews(card);
            }
          }
          taSetDirty(true);
          setTarotStatus("Card image selected from library.", "ok");
        };
        showLibraryModal(true);
        loadLibrary("media");
      });

      $("bCreateBgLibrary").addEventListener("click", () => {
        librarySelectHandler = async (item) => {
          const gid = getGameId();
          if (!gid){
            bingoCreateBgUrl = item.url || "";
            $("bCreateBgStatus").textContent = bingoCreateBgUrl
              ? "Background selected for new game."
              : "No background selected.";
            return;
          }
          try{
            await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/background-from-media", {
              method:"POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({url: item.url})
            }, true);
            setStatus("Background applied from library.", "ok");
            await refreshBingo();
          }catch(err){
            setStatus(err.message, "err");
          }
        };
        showLibraryModal(true);
        loadLibrary("media");
      });

      $("bCreate").addEventListener("click", async () => {
        try{
          updateBingoCreatePayload();
            const eventSelect = $("bCreateEventSelect");
            const eventId = parseInt(eventSelect?.value || "0", 10) || 0;
            const eventCode = eventSelect?.selectedOptions?.length
              ? (eventSelect.selectedOptions[0].dataset.code || "")
              : "";
            const body = {
              title: $("bTitle").value,
              header_text: $("bHeader").value,
              price: Number($("bPrice").value || 0),
              currency: $("bCurrency").value || "gil",
              max_cards_per_player: Number($("bMaxCards").value || 10),
              seed_pot: Number($("bSeedPot").value || 0),
              channel_id: $("bChannelSelect").value || $("bChannel").value || "",
              created_by: $("bCreatedBy").value || "",
              announce_calls: $("bAnnounceCalls").checked,
              theme_color: $("bTheme").value || "",
              event_id: eventId || undefined,
              event_code: eventCode || undefined
            };
          const data = await jsonFetch("/bingo/create", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
          });
          setGameId(data.game.game_id || "");
          if (bingoCreateBgUrl){
            try{
              await jsonFetch("/bingo/" + encodeURIComponent(data.game.game_id || "") + "/background-from-media", {
                method:"POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({url: bingoCreateBgUrl})
              }, true);
              setStatus("Background applied from library.", "ok");
            }catch(err){
              setStatus(err.message, "err");
            }
            bingoCreateBgUrl = "";
            $("bCreateBgStatus").textContent = "No background selected.";
          }
          $("bCreateModal").classList.remove("show");
          setStatus("Bingo game created.", "ok");
          renderBingoState({game: data.game});
          loadGamesMenu();
          loadOwnersForGame();
        }catch(err){
          setStatus(err.message, "err");
        }
      });

      async function refreshBingo(){
        const gid = getGameId();
        if (!gid){
          showPanel("bingoSessions");
          loadGamesMenu();
          setBingoStatus("Select a game first.", "err");
          return;
        }
        try{
          const data = await jsonFetch("/bingo/" + encodeURIComponent(gid), {method:"GET"}, false);
          renderBingoState(data);
          setBingoStatus("Game refreshed.", "ok");
        }catch(err){
          setBingoStatus(err.message, "err");
        }
      }

      $("bRefresh").addEventListener("click", refreshBingo);
      const ownersRefresh = $("bOwnersRefreshIcon") || $("bOwnersRefresh");
      if (ownersRefresh){
        ownersRefresh.addEventListener("click", () => loadOwnersForGame());
      }

      $("bAdvanceStage").addEventListener("click", async () => {
        try{
          const btn = $("bAdvanceStage");
          if (btn) btn.disabled = true;
          const data = await jsonFetch("/bingo/advance-stage", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({game_id: getGameId()})
          });
          setBingoStatus(data.ended ? "Game closed." : "Stage advanced.", "ok");
          addBingoHistory(data.ended ? "Stage advanced and game ended" : "Stage advanced");
          setBingoLastAction(data.ended ? "Stage advanced and game ended" : "Stage advanced");
          await refreshBingo();
        }catch(err){
          setBingoStatus(err.message, "err");
        }finally{
          const btn = $("bAdvanceStage");
          if (btn) btn.disabled = false;
        }
      });

      $("bStart").addEventListener("click", async () => {
        try{
          const btn = $("bStart");
          if (btn) btn.disabled = true;
          const gid = getGameId();
          if (!gid){
            setBingoStatus("Select a game first.", "err");
            return;
          }
          await jsonFetch("/bingo/start", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({game_id: gid})
          });
          setBingoStatus("Game started.", "ok");
          addBingoHistory("Game started");
          setBingoLastAction("Game started");
          if (currentGame && currentGame.game_id === gid){
            currentGame.started = true;
            renderBingoState({game: currentGame});
          }
          await refreshBingo();
        }catch(err){
          setBingoStatus(err.message, "err");
        }finally{
          const btn = $("bStart");
          if (btn) btn.disabled = false;
        }
      });


      $("bRoll").addEventListener("click", async () => {
        try{
          const btn = $("bRoll");
          if (btn) btn.disabled = true;
          await jsonFetch("/bingo/roll", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({game_id: getGameId()})
          });
          setBingoStatus("Pulled random number.", "ok");
          await refreshBingo();
        }catch(err){
          setBingoStatus(err.message, "err");
        }finally{
          const btn = $("bRoll");
          if (btn) btn.disabled = false;
        }
      });

      document.addEventListener("keydown", (ev) => {
        if (ev.repeat) return;
        if (!ev.key || ev.key.toLowerCase() !== "n") return;
        const target = ev.target;
        const tag = target && target.tagName ? target.tagName.toLowerCase() : "";
        if (tag === "input" || tag === "textarea" || target.isContentEditable) return;
        const panel = $("bingoPanel");
        if (!panel || panel.classList.contains("hidden")) return;
        const btn = $("bRoll");
        if (!btn || btn.disabled) return;
        ev.preventDefault();
        btn.click();
      });

      $("bCloseGame").addEventListener("click", async () => {
        const gid = getGameId();
        if (!gid){
          setBingoStatus("Select a game first.", "err");
          return;
        }
        if (!confirm("This will end the game and lock all cards. Continue?")){
          return;
        }
        try{
          const btn = $("bCloseGame");
          if (btn) btn.disabled = true;
          await jsonFetch("/bingo/" + encodeURIComponent(gid), {method:"DELETE"});
          setGameId("");
          currentGame = null;
          $("bOwners").textContent = "";
          const ownersEmpty = $("bOwnersEmpty");
          if (ownersEmpty) ownersEmpty.style.display = "flex";
          const claimsEl = $("bClaims");
          if (claimsEl){
            claimsEl.textContent = "No claims yet.";
          }
          $("bTitleVal").textContent = "No title";
          $("bHeaderVal").textContent = "No header";
          $("bStageVal").textContent = "No stage";
          $("bPotVal").textContent = "No pot";
          $("bCalled").textContent = "No numbers called yet.";
          $("bCalledGrid").innerHTML = "";
          $("bCardHeader").innerHTML = "";
          $("bCardGrid").innerHTML = "";
          setBingoStatus("Game closed.", "ok");
          addBingoHistory("Game closed");
          setBingoLastAction("Game closed");
          await loadGamesMenu();
        }catch(err){
          setBingoStatus(err.message, "err");
        }finally{
          const btn = $("bCloseGame");
          if (btn) btn.disabled = false;
        }
      });


      const bOwnerInput = $("bOwner");
      if (bOwnerInput){
        bOwnerInput.addEventListener("input", () => updateBingoBuyState(currentGame, currentGame ? currentGame.called : []));
      }
      const bQtyInput = $("bQty");
      if (bQtyInput){
        bQtyInput.addEventListener("input", () => updateBingoBuyState(currentGame, currentGame ? currentGame.called : []));
      }
      const bSeedPotInput = $("bSeedPotAmount");
      if (bSeedPotInput){
        bSeedPotInput.addEventListener("input", () => updateSeedPotState(currentGame));
      }
      const bSeedPotApply = $("bSeedPotApply");
      if (bSeedPotApply){
        bSeedPotApply.addEventListener("click", async () => {
          try{
            bSeedPotApply.disabled = true;
            const gid = getGameId();
            if (!gid){
              setBingoStatus("Select a game first.", "err");
              return;
            }
            const amount = Number($("bSeedPotAmount").value || 0);
            if (!Number.isFinite(amount) || amount <= 0){
              setBingoStatus("Seed amount must be positive.", "err");
              return;
            }
            await jsonFetch("/bingo/seed", {
              method:"POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({game_id: gid, amount})
            });
            setBingoStatus("Pot seeded.", "ok");
            addBingoHistory(`Seeded pot +${amount}`);
            setBingoLastAction(`Seeded pot +${amount}`);
            await refreshBingo();
          }catch(err){
            setBingoStatus(err.message, "err");
          }finally{
            updateSeedPotState(currentGame);
          }
        });
      }

      $("bBuy").addEventListener("click", async () => {
        try{
          const buyBtn = $("bBuy");
          if (buyBtn) buyBtn.disabled = true;
          const gid = getGameId();
          const ownerName = $("bOwner").value.trim();
          const qty = Number($("bQty").value || 1);
          const countsPot = $("bCountsPot");
          const gift = countsPot ? !countsPot.checked : false;
          if (!ownerName){
            setBingoStatus("Owner name is required.", "err");
            return;
          }
          if (!Number.isFinite(qty) || qty < 1){
            setBingoStatus("Quantity must be at least 1.", "err");
            return;
          }
            const body = {
              game_id: gid,
              owner_name: ownerName,
              owner_user_id: ($("bOwnerId")?.value || "").trim() || null,
              quantity: qty,
              gift: gift
            };
          await jsonFetch("/bingo/buy", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
          });
          setBingoStatus(gift ? "Tickets gifted." : "Cards bought.", "ok");
          addBingoHistory(gift ? `Gifted ${qty} for ${ownerName}` : `Bought ${qty} for ${ownerName}`);
          setBingoLastAction(gift ? `Gifted ${qty} for ${ownerName}` : `Bought ${qty} for ${ownerName}`);
          await loadOwnersForGame();
          if (gid && ownerName){
            const data = await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owner/" + encodeURIComponent(ownerName) + "/token", {method:"GET"});
            const base = getBase();
            const url = new URL("/bingo/owner?token=" + encodeURIComponent(data.token || ""), base).toString();
            $("bPurchaseLink").value = url;
            $("bPurchaseStatus").textContent = "Share this link with the player.";
            $("bPurchaseModal").classList.add("show");
          }
        }catch(err){
          setBingoStatus(err.message, "err");
        }finally{
          updateBingoBuyState(currentGame, currentGame ? currentGame.called : []);
        }
      });

      on("bViewOwner", "click", () => {
        const gid = getGameId();
        const owner = $("bOwner").value.trim();
        if (!gid || !owner){
          setBingoStatus("Enter game id and owner name.", "err");
          return;
        }
        currentOwner = owner;
        jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owner/" + encodeURIComponent(owner) + "/token", {method:"GET"})
          .then(data => {
            const base = getBase();
            const url = new URL("/bingo/owner?token=" + encodeURIComponent(data.token || ""), base).toString();
            window.open(url, "_blank");
          })
          .catch(err => setStatus(err.message, "err"));
      });

      function getOverlayUrl(code){
        const base = getBase();
        return new URL("/elfministration/session/" + encodeURIComponent(code), base).toString();
      }

      function getPlayerUrl(code){
        const base = getBase();
        return new URL("/tarot/session/" + encodeURIComponent(code) + "?view=player", base).toString();
      }

      function getPriestessUrl(code, token){
        const base = getBase();
        const url = new URL("/tarot/session/" + encodeURIComponent(code), base);
        url.searchParams.set("view", "priestess");
        if (token) url.searchParams.set("token", token);
        return url.toString();
      }

      function renderLinks(code, token){
        const container = $("tLink");
        if (!container) return;
        const links = [];
        if (code){
          links.push(`<a href="${getPlayerUrl(code)}" target="_blank" rel="noreferrer">Player</a>`);
          links.push(`<a href="${getPriestessUrl(code, token)}" target="_blank" rel="noreferrer">Host</a>`);
        }
        container.innerHTML = links.length ? links.join(" | ") : "No join code entered.";
      }

      function setTarotBackgroundStatus(url){
        const preview = $("tBackgroundPreview");
        const img = $("tBackgroundPreviewImg");
        const clean = (url || "").trim();
        if (clean && preview && img){
          img.src = clean;
          preview.style.display = "block";
        }else if (preview){
          preview.style.display = "none";
        }
      }

      async function loadTarotSessionDecks(selectValue){
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          const decks = data.decks || [];
          const filtered = filterDecksByPurpose(decks, "tarot");
          const visibleDecks = filtered.length ? filtered : decks;
          const modalSelect = $("sessionCreateDeck");
          modalSelect.innerHTML = "";
          visibleDecks.forEach(d => {
            const opt2 = document.createElement("option");
            opt2.value = d.deck_id;
            opt2.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            modalSelect.appendChild(opt2);
          });
          // Use venue deck if available, otherwise fallback to selectValue or first deck
          const defaultDeck = selectValue || adminVenueDeckId || (visibleDecks[0] ? visibleDecks[0].deck_id : "elf-classic");
          modalSelect.value = defaultDeck;
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      $("tCreateSession").addEventListener("click", () => {
        loadTarotSessionDecks();
        $("sessionCreateModal").classList.add("show");
      });
      $("sessionCreateClose").addEventListener("click", () => {
        $("sessionCreateModal").classList.remove("show");
      });
      // Session creation background image file input
      $("sessionCreateBackground").addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file){
          const reader = new FileReader();
          reader.onload = (evt) => {
            const dataUrl = evt.target.result;
            $("sessionCreateBackgroundPreviewImg").src = dataUrl;
            $("sessionCreateBackgroundPreview").style.display = "block";
            $("sessionCreateBackground").dataset.backgroundUrl = dataUrl;
          };
          reader.readAsDataURL(file);
        }
      });

      // Session creation media library button
      $("sessionCreateOpenMedia").addEventListener("click", (e) => {
        e.preventDefault();
        if (e.shiftKey){
          $("sessionCreateBackground").click();
        } else {
          librarySelectHandler = (item) => {
            const pick = item && (item.url || item.fallback_url || "");
            if (!pick){
              setStatus("No media selected.", "err");
              return;
            }
            $("sessionCreateBackgroundPreviewImg").src = pick;
            $("sessionCreateBackgroundPreview").style.display = "block";
            $("sessionCreateBackground").dataset.backgroundUrl = pick;
            setStatus("Background set from media.", "ok");
            showLibraryModal(false);
          };
          showLibraryModal(true);
          loadLibrary("media");
        }
      });

      $("sessionCreateSubmit").addEventListener("click", async () => {
        try{
          const deck = $("sessionCreateDeck").value.trim() || "elf-classic";
          const spread = $("sessionCreateSpread").value.trim() || "single";
          const backgroundUrl = $("sessionCreateBackground").dataset.backgroundUrl || "";
          const data = await jsonFetch("/api/tarot/sessions", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({deck_id: deck, spread_id: spread, background_url: backgroundUrl})
          }, true);
          $("tJoinCode").value = data.joinCode || "";
          $("tPriestessToken").value = data.priestessToken || "";
          renderLinks(data.joinCode || "", data.priestessToken || "");
          setStatus("Session created.", "ok");
          await loadTarotSessions(data.joinCode || "");
          $("sessionCreateModal").classList.remove("show");
          if (data.joinCode){
            window.open(getPriestessUrl(data.joinCode, data.priestessToken || ""), "_blank");
          }
        }catch(err){
          setStatus(err.message, "err");
        }
      });

      async function loadTarotSessions(selectJoin){
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        try{
          const data = await jsonFetch("/api/tarot/sessions", {method:"GET"}, true);
          const select = $("tSessionSelect");
          select.innerHTML = "";
          const sessions = data.sessions || [];
          sessions.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.join_code || "";
            const created = s.created_at ? new Date(s.created_at * 1000).toLocaleString() : "unknown";
            opt.textContent = `${s.join_code || "-"} | ${s.deck_id || "-"} | ${s.spread_id || "-"} | ${s.status || "-"} | ${created}`;
            opt.dataset.token = s.priestess_token || "";
            select.appendChild(opt);
          });
          // Auto-select when requested, otherwise pick the first option if only one exists
          if (selectJoin){
            select.value = selectJoin;
          } else if (select.options.length === 1){
            select.selectedIndex = 0;
          }
          // Trigger change event to populate fields when a selection exists
          if (select.value){
            select.dispatchEvent(new Event('change'));
          }
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      // Casino session creation modal handlers
      $("casinoSessionCreateClose").addEventListener("click", () => {
        $("casinoSessionCreateModal").classList.remove("show");
      });

      // Casino session background file input
      $("casinoSessionCreateBackground").addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file){
          const reader = new FileReader();
          reader.onload = (evt) => {
            const dataUrl = evt.target.result;
            $("casinoSessionCreateBackgroundPreviewImg").src = dataUrl;
            $("casinoSessionCreateBackgroundPreview").style.display = "block";
            $("casinoSessionCreateBackground").dataset.backgroundUrl = dataUrl;
          };
          reader.readAsDataURL(file);
        }
      });

      // Casino session media library button
      $("casinoSessionCreateOpenMedia").addEventListener("click", (e) => {
        e.preventDefault();
        if (e.shiftKey){
          $("casinoSessionCreateBackground").click();
        } else {
          librarySelectHandler = (item) => {
            const pick = item && (item.url || item.fallback_url || "");
            if (!pick){
              setStatus("No media selected.", "err");
              return;
            }
            $("casinoSessionCreateBackgroundPreviewImg").src = pick;
            $("casinoSessionCreateBackgroundPreview").style.display = "block";
            $("casinoSessionCreateBackground").dataset.backgroundUrl = pick;
            setStatus("Background set from media.", "ok");
            showLibraryModal(false);
          };
          showLibraryModal(true);
          loadLibrary("media");
        }
      });

      // Update background when game type changes
      $("casinoSessionCreateGame").addEventListener("change", () => {
        updateCasinoSessionBackgroundFromGame();
      });

      $("casinoSessionCreateSubmit").addEventListener("click", async () => {
        try{
          const gameId = $("casinoSessionCreateGame").value.trim() || "blackjack";
          const deckId = $("casinoSessionCreateDeck").value.trim() || "";
          const pot = parseInt($("casinoSessionCreatePot").value || "0", 10) || 0;
          const currency = $("casinoSessionCreateCurrency").value.trim() || "";
          const backgroundUrl = $("casinoSessionCreateBackground").dataset.backgroundUrl || "";
          const eventSelect = $("casinoSessionCreateEventSelect");
          const eventId = parseInt(eventSelect?.value || "0", 10) || 0;
          const eventCode = eventSelect?.selectedOptions?.length
            ? (eventSelect.selectedOptions[0].dataset.code || "")
            : "";
          const payload = {
            game_id: gameId,
            deck_id: deckId,
            pot: pot,
            currency: currency,
            background_url: backgroundUrl,
            background_artist_id: "",
            background_artist_name: "",
            event_id: eventId || undefined,
            event_code: eventCode || undefined
          };
          await createCardgameSession(payload);
          $("casinoSessionCreateModal").classList.remove("show");
        }catch(err){
          setCardgameStatus(err.message, "err");
        }
      });

      async function loadCasinoSessionDefaults(){
        // Load decks
        if (!ensureCardgamesScope()) return;
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          const decks = data.decks || [];
          const filtered = filterDecksByPurpose(decks, "playing");
          const visibleDecks = filtered.length ? filtered : decks;
          const modalSelect = $("casinoSessionCreateDeck");
          modalSelect.innerHTML = "";
          visibleDecks.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.deck_id;
            opt.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            modalSelect.appendChild(opt);
          });
          // Use venue deck if available
          const defaultDeck = adminVenueDeckId || (visibleDecks[0] ? visibleDecks[0].deck_id : "");
          if (defaultDeck) modalSelect.value = defaultDeck;
        }catch(err){
          setStatus(err.message, "err");
        }

        // Set currency from venue
        $("casinoSessionCreateCurrency").value = adminVenueCurrency || "gil";
        
        // Set pot to 0 by default
        $("casinoSessionCreatePot").value = "0";

        // Set game to blackjack by default
        $("casinoSessionCreateGame").value = "blackjack";

        // Load background based on game type
        updateCasinoSessionBackgroundFromGame();

        // Load event options
        loadEventOptions("casinoSessionCreateEventSelect");
      }

      function updateCasinoSessionBackgroundFromGame(){
        const gameId = $("casinoSessionCreateGame").value || "blackjack";
        const backgroundUrl = adminVenueGameBackgrounds[gameId] || "";
        if (backgroundUrl){
          $("casinoSessionCreateBackgroundPreviewImg").src = backgroundUrl;
          $("casinoSessionCreateBackgroundPreview").style.display = "block";
          $("casinoSessionCreateBackground").dataset.backgroundUrl = backgroundUrl;
        } else {
          $("casinoSessionCreateBackgroundPreview").style.display = "none";
          $("casinoSessionCreateBackground").dataset.backgroundUrl = "";
        }
      }

      $("tSessionRefresh").addEventListener("click", () => loadTarotSessions());
      $("tSessionSelect").addEventListener("change", (ev) => {
        const join = ev.target.value || "";
        const token = ev.target.selectedOptions.length ? (ev.target.selectedOptions[0].dataset.token || "") : "";
        $("tJoinCode").value = join;
        $("tPriestessToken").value = token;
        renderLinks(join, token);
      });

      const tOpenOverlayBtn = $("tOpenOverlay");
      if (tOpenOverlayBtn){
        tOpenOverlayBtn.addEventListener("click", () => {
          const code = $("tJoinCode").value.trim();
          if (!code){
            setStatus("Enter a join code.", "err");
            return;
          }
          const url = getOverlayUrl(code);
          renderLinks(code, $("tPriestessToken").value.trim());
          window.open(url, "_blank");
        });
      }

      $("tOpenPlayer").addEventListener("click", () => {
        const code = $("tJoinCode").value.trim();
        if (!code){
          setStatus("Enter a join code.", "err");
          return;
        }
        const url = getPlayerUrl(code);
        renderLinks(code, $("tPriestessToken").value.trim());
        window.open(url, "_blank");
      });

      $("tOpenPriestess").addEventListener("click", () => {
        const code = $("tJoinCode").value.trim();
        if (!code){
          setStatus("Enter a join code.", "err");
          return;
        }
        const token = $("tPriestessToken").value.trim();
        const url = getPriestessUrl(code, token);
        renderLinks(code, token);
        // Open priestess view inside the iframe panel to keep sidebar visible
        loadIframe(url);
      });

      $("tCopyPlayer").addEventListener("click", async () => {
        const code = $("tJoinCode").value.trim();
        if (!code){
          setStatus("Enter a join code to copy the player link.", "err");
          return;
        }
        try{
          await navigator.clipboard.writeText(getPlayerUrl(code));
          showToast("Player link copied.", "ok");
        }catch(err){
          showToast("Copy failed.", "err");
        }
      });

      $("tCopyPriestess").addEventListener("click", async () => {
        const code = $("tJoinCode").value.trim();
        const token = $("tPriestessToken").value.trim();
        if (!code){
          setStatus("Enter a join code to copy the host link.", "err");
          return;
        }
        try{
          await navigator.clipboard.writeText(getPriestessUrl(code, token));
          showToast("Host link copied.", "ok");
        }catch(err){
          showToast("Copy failed.", "err");
        }
      });

      $("tCloseSession").addEventListener("click", async () => {
        const join = $("tJoinCode").value.trim();
        const token = $("tPriestessToken").value.trim();
        if (!join || !token){
          setStatus("Join code and priestess token required.", "err");
          return;
        }
        if (!confirm("Close this session? It will be removed from the list.")){
          return;
        }
        try{
          const state = await jsonFetch("/api/tarot/sessions/" + encodeURIComponent(join) + "/state?view=priestess", {method:"GET"}, true);
          const sessionId = state.state && state.state.session ? state.state.session.session_id : "";
          if (!sessionId){
            throw new Error("Session not found.");
          }
          await jsonFetch("/api/tarot/sessions/" + encodeURIComponent(sessionId), {
            method: "DELETE",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({token})
          });
          setStatus("Session closed.", "ok");
          await loadTarotSessions();
        }catch(err){
          setStatus(err.message, "err");
        }
      });

      const CARDGAME_DEFAULTS_KEY = "cardgame_defaults";

      function getCardgamePlayerUrl(gameId, joinCode){
        const base = getBase();
        return new URL(`/cardgames/${encodeURIComponent(gameId)}/session/${encodeURIComponent(joinCode)}`, base).toString();
      }

      function getCardgameHostUrl(gameId, joinCode, token){
        const base = getBase();
        const url = new URL(`/cardgames/${encodeURIComponent(gameId)}/session/${encodeURIComponent(joinCode)}`, base);
        url.searchParams.set("view", "priestess");
        if (token){
          url.searchParams.set("token", token);
        }
        return url.toString();
      }

      function setCardgameStatus(msg, kind){
        setStatusText("cgStatus", msg, kind);
        setStatus(msg, kind);
      }

      function renderCardgameLinks(gameId, joinCode, token){
        const target = $("cgLink");
        if (!target) return;
        const links = [];
        if (joinCode && gameId){
          links.push(`<a href="${getCardgamePlayerUrl(gameId, joinCode)}" target="_blank" rel="noreferrer">Player</a>`);
          links.push(`<a href="${getCardgameHostUrl(gameId, joinCode, token)}" target="_blank" rel="noreferrer">Host</a>`);
        }
        target.innerHTML = links.length ? links.join(" | ") : "No join code entered.";
      }

      function getCardgameDefaults(){
        try{
          const raw = localStorage.getItem(CARDGAME_DEFAULTS_KEY);
          return raw ? JSON.parse(raw) : null;
        }catch(err){
          return null;
        }
      }

      function saveCardgameDefaults(payload){
        try{
          localStorage.setItem(CARDGAME_DEFAULTS_KEY, JSON.stringify(payload || {}));
        }catch(err){}
      }

      function setCardgameDefaults(payload){
        if (!payload) return;
        if ($("cgGameSelect")) $("cgGameSelect").value = payload.game_id || "blackjack";
        if ($("cgDeckSelect") && payload.deck_id){
          $("cgDeckSelect").value = payload.deck_id;
        }
        if ($("cgPot")) $("cgPot").value = payload.pot || 0;
        if ($("cgCurrency")) $("cgCurrency").value = payload.currency || "gil";
        if ($("cgBackgroundUrl")){
          $("cgBackgroundUrl").value = payload.background_url || "";
          setCardgameBackgroundStatus($("cgBackgroundUrl").value);
        }
      }

      function persistCardgameDefaults(){
        const payload = {
          game_id: $("cgGameSelect") ? $("cgGameSelect").value : "blackjack",
          deck_id: $("cgDeckSelect") ? $("cgDeckSelect").value : "",
          pot: $("cgPot") ? parseInt(($("cgPot").value || "0").trim(), 10) || 0 : 0,
          currency: $("cgCurrency") ? $("cgCurrency").value.trim() : "",
          background_url: $("cgBackgroundUrl") ? $("cgBackgroundUrl").value.trim() : "",
          background_artist_id: $("cgBackgroundUrl") ? ($("cgBackgroundUrl").dataset.artistId || "") : "",
          background_artist_name: $("cgBackgroundUrl") ? ($("cgBackgroundUrl").dataset.artistName || "") : ""
        };
        saveCardgameDefaults(payload);
      }

      async function loadCardgameDecks(selectValue){
        if (!ensureCardgamesScope()) return;
        const select = $("cgDeckSelect");
        if (!select) return;
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          const decks = data.decks || [];
          const filtered = filterDecksByPurpose(decks, "playing");
          const visibleDecks = filtered.length ? filtered : decks;
          select.innerHTML = "";
          visibleDecks.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.deck_id;
            opt.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            select.appendChild(opt);
          });
          const defaults = getCardgameDefaults();
          const pick = selectValue || (defaults && defaults.deck_id) || (visibleDecks[0] ? visibleDecks[0].deck_id : "");
          if (pick) select.value = pick;
        }catch(err){
          select.innerHTML = `<option value="">Failed to load</option>`;
          setCardgameStatus(err.message, "err");
        }
      }

      async function loadCardgameSessions(selectJoin){
        if (!ensureCardgamesScope()) return;
        const select = $("cgSessionSelect");
        if (!select) return;
        if ($("cgCreateFromSelected")){
          $("cgCreateFromSelected").disabled = true;
        }
        try{
          const data = await jsonFetch("/api/cardgames/sessions", {method:"GET"}, true);
          const sessions = data.sessions || [];
          select.innerHTML = "";
          sessions.forEach(s => {
            const opt = document.createElement("option");
            opt.value = s.join_code || "";
            const created = s.created_at ? new Date(s.created_at * 1000).toLocaleString() : "unknown";
            const currency = s.currency || "gil";
            opt.textContent = `${s.game_id || "-"} | ${s.join_code || "-"} | ${s.deck_id || "-"} | ${s.status || "-"} | pot ${s.pot || 0} ${currency} | ${created}`;
            opt.dataset.token = s.priestess_token || "";
            opt.dataset.sessionId = s.session_id || "";
            opt.dataset.pot = s.pot || 0;
            opt.dataset.currency = s.currency || "";
            opt.dataset.gameId = s.game_id || "";
            opt.dataset.deckId = s.deck_id || "";
            opt.dataset.background = s.background_url || "";
            opt.dataset.backgroundArtistId = s.background_artist_id || "";
            opt.dataset.backgroundArtistName = s.background_artist_name || "";
            opt.dataset.status = s.status || "";
            select.appendChild(opt);
          });
          if (selectJoin){
            select.value = selectJoin;
          }
          const picked = select.selectedOptions.length ? select.selectedOptions[0] : null;
          if (picked && $("cgCreateFromSelected")){
            $("cgCreateFromSelected").disabled = (picked.dataset.status || "").toLowerCase() !== "live";
          }
        }catch(err){
          setCardgameStatus(err.message, "err");
        }
      }

      function setCardgameBackgroundStatus(url){
        const previewEl = $("cgBackgroundPreview");
        const imgEl = $("cgBackgroundPreviewImg");
        if (!previewEl || !imgEl) return;
        const artistName = $("cgBackgroundUrl").dataset.artistName || "";
        if (!url){
          previewEl.style.display = "none";
          return;
        }
        imgEl.src = url;
        imgEl.alt = artistName ? `Background by ${artistName}` : "Background preview";
        imgEl.title = artistName ? `Background by ${artistName}` : "Background preview";
        previewEl.style.display = "block";
      }

        async function createCardgameSession(payload){
          if (!ensureCardgamesScope()) return;
          setCardgameStatus("Creating session...", "");
          try{
            const data = await jsonFetch(`/api/cardgames/${payload.game_id}/sessions`, {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({
                pot: payload.pot || 0,
                deck_id: payload.deck_id || "",
                currency: payload.currency || "",
                background_url: payload.background_url || "",
                background_artist_id: payload.background_artist_id || "",
                background_artist_name: payload.background_artist_name || "",
                event_id: payload.event_id || undefined,
                event_code: payload.event_code || undefined,
                draft: true
              })
            }, true);
          if (!data || data.ok === false){
            throw new Error((data && data.error) || "Failed to create session");
          }
          const session = data.session || {};
          if (!session.join_code){
            throw new Error("Session created without a join code.");
          }
          $("cgJoinCode").value = session.join_code || "";
          $("cgPriestessToken").value = session.priestess_token || "";
          $("cgJoinCode").dataset.sessionId = session.session_id || "";
          $("cgJoinCode").dataset.gameId = session.game_id || payload.game_id || "";
          $("cgJoinCode").dataset.deckId = session.deck_id || payload.deck_id || "";
          saveCardgameDefaults({
            game_id: payload.game_id,
            deck_id: payload.deck_id,
            pot: payload.pot || 0,
            currency: payload.currency || "",
            background_url: payload.background_url || "",
            background_artist_id: payload.background_artist_id || "",
            background_artist_name: payload.background_artist_name || ""
          });
          setCardgameStatus("Session created.", "ok");
          await loadCardgameSessions(session.join_code || "");
        }catch(err){
          setCardgameStatus(err.message, "err");
        }
      }

      function getCardgameSessionGameId(){
        return $("cgJoinCode").dataset.gameId || $("cgGameSelect").value || "blackjack";
      }

      async function finishCardgameSession(){
        const join = $("cgJoinCode").value.trim();
        const token = $("cgPriestessToken").value.trim();
        const sessionId = $("cgJoinCode").dataset.sessionId || "";
        const gameId = getCardgameSessionGameId();
        if (!join || !token || !sessionId){
          setCardgameStatus("Select a session and host token.", "err");
          return;
        }
        if (!confirm("Finish this session?")){
          return;
        }
        try{
          await jsonFetch(`/api/cardgames/${gameId}/sessions/${encodeURIComponent(sessionId)}/finish`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({token})
          }, true);
          setCardgameStatus("Session finished.", "ok");
          await loadCardgameSessions();
        }catch(err){
          setCardgameStatus(err.message, "err");
        }
      }

        if ($("cgCreateSession")){
          $("cgCreateSession").addEventListener("click", () => {
            loadCasinoSessionDefaults();
            $("casinoSessionCreateModal").classList.add("show");
          });
          on("cgCreateFromSelected", "click", () => {
            const sel = $("cgSessionSelect");
            const opt = sel && sel.selectedOptions.length ? sel.selectedOptions[0] : null;
            if (!opt){
              setCardgameStatus("Select a session to clone.", "err");
              return;
            }
            if ((opt.dataset.status || "").toLowerCase() !== "live"){
              setCardgameStatus("Create next requires a live session.", "err");
              return;
            }
            createCardgameSession({
              game_id: opt.dataset.gameId || "blackjack",
              deck_id: opt.dataset.deckId || "",
              pot: parseInt(opt.dataset.pot || "0", 10) || 0,
              currency: opt.dataset.currency || "",
              background_url: opt.dataset.background || "",
              background_artist_id: opt.dataset.backgroundArtistId || "",
              background_artist_name: opt.dataset.backgroundArtistName || ""
            });
          });
        }

        on("cgSessionSelect", "change", (ev) => {
          const opt = ev.target.selectedOptions.length ? ev.target.selectedOptions[0] : null;
          const join = opt ? (opt.value || "") : "";
          const token = opt ? (opt.dataset.token || "") : "";
          const pot = opt ? (opt.dataset.pot || "") : "";
          const currency = opt ? (opt.dataset.currency || "") : "";
          const gameId = opt ? (opt.dataset.gameId || "blackjack") : "blackjack";
          const deckId = opt ? (opt.dataset.deckId || "") : "";
          const background = opt ? (opt.dataset.background || "") : "";
          const backgroundArtistId = opt ? (opt.dataset.backgroundArtistId || "") : "";
          const backgroundArtistName = opt ? (opt.dataset.backgroundArtistName || "") : "";
          const status = opt ? (opt.dataset.status || "") : "";
          const joinEl = $("cgJoinCode");
          if (joinEl){
            joinEl.value = join;
            joinEl.dataset.sessionId = opt ? (opt.dataset.sessionId || "") : "";
            joinEl.dataset.gameId = gameId;
            joinEl.dataset.deckId = deckId;
          }
          const tokenEl = $("cgPriestessToken");
          if (tokenEl) tokenEl.value = token;
          const potEl = $("cgPot");
          if (potEl) potEl.value = pot;
          const currencyEl = $("cgCurrency");
          if (currencyEl) currencyEl.value = currency || "gil";
          const gameSelectEl = $("cgGameSelect");
          if (gameSelectEl) gameSelectEl.value = gameId;
          if (deckId){
            const deckEl = $("cgDeckSelect");
            if (deckEl) deckEl.value = deckId;
          }
          if ($("cgBackgroundUrl")){
            $("cgBackgroundUrl").value = background;
            $("cgBackgroundUrl").dataset.artistId = backgroundArtistId;
            $("cgBackgroundUrl").dataset.artistName = backgroundArtistName;
            setCardgameBackgroundStatus(background);
          }
          if ($("cgCreateFromSelected")){
            $("cgCreateFromSelected").disabled = status.toLowerCase() !== "live";
          }
        });
        on("cgBackgroundUrl", "input", (ev) => {
          ev.target.dataset.artistId = "";
          ev.target.dataset.artistName = "";
          setCardgameBackgroundStatus(ev.target.value.trim());
        });
        on("cgOpenPlayer", "click", () => {
          const joinEl = $("cgJoinCode");
          if (!joinEl){
            setCardgameStatus("Select a session first.", "err");
            return;
          }
          const join = joinEl.value.trim();
          const gameId = $("cgGameSelect")?.value || joinEl.dataset.gameId || "crapslite";
          if (!join){
            setCardgameStatus("Enter a join code.", "err");
            return;
          }
          loadIframe(getCardgamePlayerUrl(gameId, join));
        });
        on("cgOpenPriestess", "click", () => {
          const joinEl = $("cgJoinCode");
          if (!joinEl){
            setCardgameStatus("Select a session first.", "err");
            return;
          }
          const join = joinEl.value.trim();
          const gameId = $("cgGameSelect")?.value || joinEl.dataset.gameId || "crapslite";
          if (!join){
            setCardgameStatus("Enter a join code.", "err");
            return;
          }
          const tokenEl = $("cgPriestessToken");
          const token = tokenEl ? tokenEl.value.trim() : "";
          loadIframe(getCardgameHostUrl(gameId, join, token));
        });
        on("cgCopyPlayer", "click", async () => {
          const joinEl = $("cgJoinCode");
          if (!joinEl){
            setCardgameStatus("Select a session first.", "err");
            return;
          }
          const join = joinEl.value.trim();
          const gameId = joinEl.dataset.gameId || "blackjack";
          if (!join){
            setCardgameStatus("Enter a join code to copy the player link.", "err");
            return;
          }
          try{
            await navigator.clipboard.writeText(getCardgamePlayerUrl(gameId, join));
            showToast("Player link copied.", "ok");
          }catch(err){
            showToast("Copy failed.", "err");
          }
        });
        on("cgCopyPriestess", "click", async () => {
          const joinEl = $("cgJoinCode");
          if (!joinEl){
            setCardgameStatus("Select a session first.", "err");
            return;
          }
          const join = joinEl.value.trim();
          const token = $("cgPriestessToken") ? $("cgPriestessToken").value.trim() : "";
          const gameId = joinEl.dataset.gameId || "blackjack";
          if (!join){
            setCardgameStatus("Enter a join code to copy the host link.", "err");
            return;
          }
          try{
            await navigator.clipboard.writeText(getCardgameHostUrl(gameId, join, token));
            showToast("Host link copied.", "ok");
          }catch(err){
            showToast("Copy failed.", "err");
          }
        });
        on("cgFinishSession", "click", () => finishCardgameSession());
        on("cgDeleteSession", "click", async () => {
          const join = $("cgJoinCode").value.trim();
          const token = $("cgPriestessToken").value.trim();
          const sessionId = $("cgJoinCode").dataset.sessionId || "";
          const gameId = getCardgameSessionGameId();
          if (!join || !token || !sessionId){
            setCardgameStatus("Select a session and host token.", "err");
            return;
          }
          if (!confirm("Delete this session now?")){
            return;
          }
          try{
            await jsonFetch(`/api/cardgames/${gameId}/sessions/${encodeURIComponent(sessionId)}/delete`, {
              method: "POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({token})
            }, true);
            $("cgJoinCode").value = "";
            $("cgJoinCode").dataset.sessionId = "";
            $("cgPriestessToken").value = "";
            setCardgameStatus("Session deleted.", "ok");
            await loadCardgameSessions();
          }catch(err){
            setCardgameStatus(err.message, "err");
          }
        });
        on("cgUseSelectedMedia", "click", () => {
          const pick = currentMediaEdit ? (currentMediaEdit.url || currentMediaEdit.fallback_url || "") : "";
          if (!pick){
            setCardgameStatus("Select a media item first.", "err");
            return;
          }
          $("cgBackgroundUrl").value = pick;
          setCardgameBackgroundStatus(pick);
        });
        on("cgOpenMedia", "click", () => {
          librarySelectHandler = (item) => {
            const pick = item && (item.url || item.fallback_url || "");
            if (!pick){
              setCardgameStatus("Select a media item first.", "err");
              return;
            }
            $("cgBackgroundUrl").value = pick;
            $("cgBackgroundUrl").dataset.artistId = item.artist_id || "";
            $("cgBackgroundUrl").dataset.artistName = item.artist_name || item.artist_id || "";
            setCardgameBackgroundStatus(pick);
            setCardgameStatus("Background selected.", "ok");
            showLibraryModal(false);
          };
          showLibraryModal(true);
          loadLibrary("media");
        });
        const defaults = getCardgameDefaults();
        if (defaults){
          setCardgameDefaults(defaults);
        }

      let taNumbers = [];
      let taSuitDefs = [];
      let taSuitLookup = {};

      function taThemeLabel(theme){
        return (theme || "").replace(/_/g, " ");
      }

      function taNormalizeSuitKey(value){
        return String(value || "").trim().toLowerCase();
      }

      function taSetSuitDefinitions(defs){
        taSuitDefs = Array.isArray(defs) ? defs : [];
        taSuitLookup = {};
        taSuitDefs.forEach(def => {
          if (!def) return;
          const id = taNormalizeSuitKey(def.id);
          const name = taNormalizeSuitKey(def.name);
          if (id) taSuitLookup[id] = def;
          if (name) taSuitLookup[name] = def;
        });
        taUpdateSuitList();
      }

      function taUpdateSuitList(){
        const list = $("taSuitList");
        if (!list) return;
        const defaults = ["Major", "Wands", "Cups", "Swords", "Pentacles", "Hearts", "Spades", "Clubs", "Diamonds"];
        const extra = taSuitDefs.map(def => def && (def.name || def.id)).filter(Boolean);
        const combined = Array.from(new Set(defaults.concat(extra)));
        list.innerHTML = combined.map(value => `<option value="${value}"></option>`).join("");
      }

      function taFindSuitDef(value){
        const key = taNormalizeSuitKey(value);
        if (!key) return null;
        return taSuitLookup[key] || null;
      }

      function taParseRoman(value){
        const roman = String(value || "").trim().toUpperCase();
        if (!roman) return NaN;
        const map = {I:1, V:5, X:10, L:50, C:100, D:500, M:1000};
        let total = 0;
        let prev = 0;
        for (let i = roman.length - 1; i >= 0; i -= 1){
          const num = map[roman[i]];
          if (!num) return NaN;
          if (num < prev){
            total -= num;
          } else {
            total += num;
            prev = num;
          }
        }
        return total;
      }

      function taParseCardNumber(value){
        const text = String(value).trim();
        if (!text) return NaN;
        if (/^\d+$/.test(text)) return parseInt(text, 10);
        return taParseRoman(text);
      }

      function taToRoman(num){
        const n = Number(num);
        if (!Number.isFinite(n) || n <= 0) return "";
        const map = [
          [1000, "M"], [900, "CM"], [500, "D"], [400, "CD"],
          [100, "C"], [90, "XC"], [50, "L"], [40, "XL"],
          [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]
        ];
        let out = "";
        let remaining = Math.floor(n);
        map.forEach(([val, sym]) => {
          while (remaining >= val){
            out += sym;
            remaining -= val;
          }
        });
        return out;
      }

      function taFormatCardNumber(value){
        if (String(value || "").trim() === "0") return "0";
        const num = taParseCardNumber(value);
        if (num === 0) return "0";
        return num ? taToRoman(num) || String(value || "") : "";
      }

      let taDirty = false;
      let taSuppressDirty = false;

      function setTarotStatus(msg, kind){
        const el = $("taDeckStatus");
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
      }

      function taSetDirty(state){
        if (taSuppressDirty) return;
        taDirty = !!state;
        if (taDirty){
          setTarotStatus("Unsaved changes", "alert");
        }
      }

      function taUpdateThemeRow(row, value){
        const fill = row.querySelector(".theme-fill");
        const valueEl = row.querySelector(".theme-value");
        const weight = Math.max(0, Math.min(5, parseInt(value, 10) || 0));
        if (fill){
          fill.style.width = `${(weight / 5) * 100}%`;
        }
        if (valueEl){
          valueEl.textContent = `${weight} / 5`;
        }
      }

      function taSnippet(text, limit = 120){
        const clean = String(text || "").trim();
        if (!clean) return "";
        if (clean.length <= limit) return clean;
        return clean.slice(0, limit - 3) + "...";
      }

      function taUpdateContext(card){
        const deckName = window.taDeckData && window.taDeckData.deck
          ? (window.taDeckData.deck.name || window.taDeckData.deck.deck_id || "")
          : "";
        const deckId = window.taDeckData && window.taDeckData.deck ? window.taDeckData.deck.deck_id : "";
        const cardLabel = card && (card.name || card.card_id) ? (card.name || card.card_id) : "No card selected";
        const path = $("taContextPath");
        const meta = $("taContextMeta");
        const deckMeta = $("taContextDeck");
        if (path){
          path.textContent = `Deck Editor / Forest / ${cardLabel}`;
        }
        if (meta){
          meta.textContent = card ? `Editing ${cardLabel}` : "Pick a card to edit.";
        }
        if (deckMeta){
          deckMeta.textContent = deckId ? `${deckName} (${deckId})` : "";
        }
      }

      function taNormalizePurpose(purpose){
        const value = String(purpose || "").trim().toLowerCase();
        return value === "playing" ? "playing" : "tarot";
      }

      function filterDecksByPurpose(decks, purpose){
        const target = taNormalizePurpose(purpose);
        return (decks || []).filter(d => taNormalizePurpose(d && d.purpose) === target);
      }

      function taGetDeckPurpose(){
        const deck = window.taDeckData && window.taDeckData.deck ? window.taDeckData.deck : null;
        return taNormalizePurpose(deck && deck.purpose);
      }

      async function taLoadTemplateOptions(){
        const select = $("taCardTemplate");
        if (!select) return;
        const purpose = taGetDeckPurpose();
        taTemplatePurpose = purpose;
        let cards = taTemplateCache[purpose];
        if (!cards){
          try{
            const data = await jsonFetch("/api/tarot/templates?purpose=" + encodeURIComponent(purpose), {method:"GET"}, true);
            cards = Array.isArray(data.cards) ? data.cards : [];
            taTemplateCache[purpose] = cards;
          }catch(err){
            select.innerHTML = "<option value=\"\">Failed to load templates</option>";
            const hint = $("taCardTemplateHint");
            if (hint) hint.textContent = "Template cards unavailable.";
            return;
          }
        }
        const current = select.value;
        select.innerHTML = "";
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = purpose === "playing" ? "Pick a playing card..." : "Pick a tarot card...";
        select.appendChild(empty);
        cards.forEach(card => {
          const opt = document.createElement("option");
          const id = card.card_id || card.id || "";
          opt.value = id;
          const name = card.name || card.title || id || "Card";
          const suit = card.suit || "";
          const number = (card.number !== undefined && card.number !== null) ? card.number : "";
          const suffix = (suit || number) ? ` (${[number, suit].filter(Boolean).join(" ")})` : "";
          opt.textContent = name + suffix;
          select.appendChild(opt);
        });
        select.value = current || "";
        const hint = $("taCardTemplateHint");
        if (hint){
          hint.textContent = purpose === "playing"
            ? "Pick a playing card to prefill this card."
            : "Pick a tarot card to prefill this card.";
        }
      }

      function taApplyTemplateCard(card){
        if (!card) return;
        const existing = window.taDeckData && window.taDeckData.cards
          ? window.taDeckData.cards.find(c => c.card_id === (card.card_id || card.id))
          : null;
        if (existing){
          taLoadCard(existing);
          return;
        }
        taSuppressDirty = true;
        taSelectedCardId = "";
        $("taCardId").value = card.card_id || card.id || "";
        $("taCardName").value = card.name || card.title || "";
        $("taCardSuit").value = card.suit || "";
        $("taCardNumber").value = (card.number !== undefined && card.number !== null) ? card.number : "";
        $("taCardTags").value = (card.tags || []).join(", ");
        $("taCardFlavor").value = card.flavor_text || "";
        $("taCardUpright").value = card.upright || "";
        $("taCardReversed").value = card.reversed || "";
        $("taCardArtist").value = card.artist_id || "";
        window.taUploadedImageUrl = card.image || "";
        taRenderThemeWeights(card.themes || {}, card.suit || "");
        taRenderSuitInfo(card.suit || "");
        taRenderNumberInfo($("taCardNumber").value);
        taApplySuitThemeDefaults(card.suit || "");
        taRenderPreviews({
          name: $("taCardName").value.trim(),
          number: $("taCardNumber").value.trim(),
          image: window.taUploadedImageUrl || "",
          suit: $("taCardSuit").value.trim(),
          upright: $("taCardUpright").value.trim(),
          reversed: $("taCardReversed").value.trim()
        });
        taUpdateContext(null);
        taSuppressDirty = false;
        taSetDirty(true);
      }

      function taRenderThemeWeights(weights, suitValue){
        const grid = $("taCardThemes");
        const hint = $("taCardThemesHint");
        if (!grid) return;
        grid.innerHTML = "";
        const suitDef = taFindSuitDef(suitValue);
        const themes = suitDef && suitDef.themes ? Object.keys(suitDef.themes) : [];
        if (!suitValue){
          if (hint) hint.textContent = "Select a suit to see theme weights.";
          return;
        }
        if (!suitDef){
          if (hint) hint.textContent = "Suit not defined for this deck.";
          return;
        }
        if (!themes.length){
          if (hint) hint.textContent = "No theme weights available for this suit.";
          return;
        }
        if (hint) hint.textContent = "Adjust theme weights for this card.";
        themes.forEach(theme => {
          const row = document.createElement("div");
          row.className = "theme-weight";
          row.dataset.theme = theme;
          const label = document.createElement("label");
          label.textContent = taThemeLabel(theme);
          const bar = document.createElement("div");
          bar.className = "theme-bar";
          const fill = document.createElement("div");
          fill.className = "theme-fill";
          bar.appendChild(fill);
          const input = document.createElement("input");
          input.type = "range";
          input.min = "0";
          input.max = "5";
          input.step = "1";
          input.value = weights && weights[theme] ? weights[theme] : 0;
          const value = document.createElement("div");
          value.className = "theme-value";
          row.appendChild(label);
          row.appendChild(bar);
          row.appendChild(input);
          row.appendChild(value);
          taUpdateThemeRow(row, input.value);
          input.addEventListener("input", () => {
            taUpdateThemeRow(row, input.value);
            taSetDirty(true);
          });
          grid.appendChild(row);
        });
      }

      function taSetCardThemeWeights(weights){
        const grid = $("taCardThemes");
        if (!grid){
          return;
        }
        if (!grid.children.length){
          taRenderThemeWeights(weights || {}, $("taCardSuit").value.trim());
          return;
        }
        grid.querySelectorAll(".theme-weight").forEach(row => {
          const theme = row.dataset.theme;
          const input = row.querySelector("input");
          if (!input) return;
          input.value = weights && weights[theme] ? weights[theme] : 0;
          taUpdateThemeRow(row, input.value);
        });
      }

      function taGetCardThemeWeights(){
        const grid = $("taCardThemes");
        const out = {};
        if (!grid) return out;
        grid.querySelectorAll(".theme-weight").forEach(row => {
          const theme = row.dataset.theme;
          const input = row.querySelector("input");
          if (!input) return;
          const value = parseInt(input.value, 10);
          if (Number.isFinite(value) && value > 0){
            out[theme] = value;
          }
        });
        return out;
      }

      function taApplySuitThemeDefaults(suitValue){
        if (!suitValue) return;
        const current = taGetCardThemeWeights();
        if (Object.keys(current).length){
          return;
        }
        const suitDef = taFindSuitDef(suitValue);
        if (!suitDef || !suitDef.themes) return;
        taSetCardThemeWeights(suitDef.themes);
      }

      function taRenderSuitInfo(value){
        const box = $("taSuitInfo");
        if (!box) return;
        const suitDef = taFindSuitDef(value);
        if (!suitDef){
          box.textContent = value ? "Suit not defined for this deck." : "Pick a suit to see details.";
          return;
        }
        const themes = Object.entries(suitDef.themes || {}).map(([k, v]) => `${k} (${v})`).join(", ");
        const keywords = (suitDef.keywords || []).join(", ");
        const upright = keywords ? `Upright: ${keywords}.` : "Upright: -";
        const reversed = keywords ? `Reversed: blocked or twisted ${keywords}.` : "Reversed: -";
        const title = suitDef.name || suitDef.id || "Suit";
        box.innerHTML = `<strong>${title}</strong><br><span class="muted">${themes || "No themes set."}</span><br><span class="muted">${keywords || "No keywords set."}</span><br>${upright}<br>${reversed}`;
      }

      function taRenderNumberInfo(value){
        const box = $("taNumberInfo");
        if (!box) return;
        const num = taParseCardNumber(value);
        if (!Number.isFinite(num)){
          box.textContent = "Pick a number to see details.";
          return;
        }
        const digits = String(num).split("").map(d => parseInt(d, 10));
        let sum = digits.reduce((acc, d) => acc + d, 0);
        while (sum > 10){
          sum = String(sum).split("").reduce((acc, d) => acc + parseInt(d, 10), 0);
        }
        const picks = [];
        digits.forEach(d => { if (!picks.includes(d)) picks.push(d); });
        if (sum > 0 && !picks.includes(sum)) picks.push(sum);
        if (num === 0 && !picks.includes(0)) picks.push(0);
        const rows = picks.map(pick => {
          const entry = taNumbers.find(n => Number(n.number) === pick);
          const label = entry && entry.label ? ` - ${entry.label}` : "";
          const meaning = entry && entry.meaning ? entry.meaning : "";
          return `<div><strong>${pick}${label}</strong><br>${meaning}</div>`;
        }).join("<div style=\"height:6px\"></div>");
        box.innerHTML = rows || "No number details found.";
      }

      function taRenderPreviews(card){
        const front = $("taFrontPreview");
        const back = $("taBackPreview");
        const backUrl = window.taDeckData && window.taDeckData.deck ? window.taDeckData.deck.back_image : "";
        const theme = (window.taDeckData && window.taDeckData.deck && window.taDeckData.deck.theme) || "classic";
        front.dataset.cardTheme = theme;
        front.classList.add("card-object", "hover-flip");
        back.classList.add("card-object");
        front.innerHTML = '<span class="preview-label">Front</span>';
        back.innerHTML = '<span class="preview-label">Back</span>';
        if (card && card.image){
          const img = document.createElement("img");
          img.src = card.image;
          front.appendChild(img);
        }
        if (card && card.number !== undefined && card.number !== null){
          const number = document.createElement("div");
          number.className = "card-number";
          number.textContent = taFormatCardNumber(card.number);
          front.appendChild(number);
        }
        if (card && card.name){
          const title = document.createElement("div");
          title.className = "card-title";
          title.textContent = card.name;
          front.appendChild(title);
        }
        if (card && (card.upright || card.reversed)){
          const meaning = document.createElement("div");
          meaning.className = "card-meaning";
          const up = document.createElement("div");
          up.className = "meaning-line upright";
          up.textContent = "Upright: " + taSnippet(card.upright || "", 120);
          const rev = document.createElement("div");
          rev.className = "meaning-line reversed";
          rev.textContent = "Reversed: " + taSnippet(card.reversed || "", 120);
          meaning.appendChild(up);
          meaning.appendChild(rev);
          front.appendChild(meaning);
        }
        if (backUrl){
          const img = document.createElement("img");
          img.src = backUrl;
          back.appendChild(img);
        }
      }

      function taLoadCard(card){
        if (!card) return;
        taSuppressDirty = true;
        taSelectedCardId = card.card_id || "";
        $("taCardId").value = card.card_id || "";
        $("taCardName").value = card.name || "";
        $("taCardSuit").value = card.suit || "";
        $("taCardNumber").value = (card.number !== undefined && card.number !== null) ? card.number : "";
        $("taCardTags").value = (card.tags || []).join(", ");
        $("taCardFlavor").value = card.flavor_text || "";
        $("taCardUpright").value = card.upright || "";
        $("taCardReversed").value = card.reversed || "";
        $("taCardArtist").value = card.artist_id || "";
        window.taUploadedImageUrl = card.image || "";
        taRenderThemeWeights(card.themes || {}, card.suit || "");
        taRenderSuitInfo(card.suit || "");
        taRenderNumberInfo($("taCardNumber").value);
        taApplySuitThemeDefaults(card.suit || "");
        taRenderPreviews(card);
        taSyncCardSelection();
        taUpdateContext(card);
        const templateSelect = $("taCardTemplate");
        if (templateSelect){
          templateSelect.value = card.card_id || "";
        }
        taDirty = false;
        taSuppressDirty = false;
      }

      function taSyncCardSelection(){
        const list = $("taDeckList");
        if (!list) return;
        list.querySelectorAll(".list-card").forEach(el => {
          const active = taSelectedCardId && el.dataset.cardId === taSelectedCardId;
          el.classList.toggle("active", active);
        });
        if (window.taDeckData && window.taDeckData.cards && taSelectedCardId){
          const match = window.taDeckData.cards.find(c => c.card_id === taSelectedCardId);
          if (match){
            taRenderPreviews(match);
          }
        } else {
          taUpdateContext(null);
        }
      }

      async function loadTarotNumbers(){
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        try{
          const data = await jsonFetch("/api/tarot/numbers", {method:"GET"}, true);
          taNumbers = data.numbers || [];
          const input = $("taCardNumber");
          const list = $("taNumberList");
          if (!input || !list){
            return;
          }
          const current = input.value || "";
          list.innerHTML = "";
          taNumbers.forEach(n => {
            const opt = document.createElement("option");
            opt.value = n.number;
            opt.textContent = n.label ? `${n.number} - ${n.label}` : String(n.number);
            list.appendChild(opt);
          });
          input.value = current;
          taRenderNumberInfo(input.value);
        }catch(err){
          setTarotStatus(`Failed to load numbers: ${err.message || "unknown error"}`, "err");
        }
      }

      async function loadTarotArtists(){
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        try{
          const data = await jsonFetch("/api/tarot/artists", {method:"GET"}, true);
          const artists = data.artists || [];
          window.taArtists = artists;
        const selects = ["uploadLibraryArtist", "mediaUploadArtist", "mediaEditArtist", "mediaBulkArtist", "artistIndexSelect"];
        selects.forEach(id => {
          const sel = $(id);
          if (!sel) return;
          const current = sel.value;
          sel.innerHTML = "";
          const none = document.createElement("option");
          none.value = "";
          none.textContent = id === "mediaBulkArtist" ? "Select artist" : "(none)";
          sel.appendChild(none);
          artists.forEach(a => {
            const opt = document.createElement("option");
            opt.value = a.artist_id || "";
            opt.textContent = a.name ? `${a.name} (${a.artist_id})` : (a.artist_id || "");
            sel.appendChild(opt);
          });
          if (current){
            sel.value = current;
          }
        });
        const filter = $("mediaFilterArtist");
        if (filter){
          const current = filter.value;
          filter.innerHTML = "";
          const any = document.createElement("option");
          any.value = "";
          any.textContent = "All artists";
          filter.appendChild(any);
          artists.forEach(a => {
            const opt = document.createElement("option");
            opt.value = a.artist_id || "";
            opt.textContent = a.name ? `${a.name} (${a.artist_id})` : (a.artist_id || "");
            filter.appendChild(opt);
          });
          if (current){
            filter.value = current;
          }
        }
        }catch(err){
          window.taArtists = [];
          setStatus("Failed to load artists.", "err");
        }
      }

      $("artistIndexRefresh").addEventListener("click", () => loadTarotArtists());
      $("artistIndexSelect").addEventListener("change", (ev) => {
        const pick = (window.taArtists || []).find(a => a.artist_id === ev.target.value);
        if (!pick){
          $("artistIndexId").value = "";
          $("artistIndexName").value = "";
          $("artistIndexInstagram").value = "";
          $("artistIndexBluesky").value = "";
          $("artistIndexX").value = "";
          $("artistIndexArtstation").value = "";
          $("artistIndexWebsite").value = "";
          $("artistIndexLinktree").value = "";
          return;
        }
        $("artistIndexId").value = pick.artist_id || "";
        $("artistIndexName").value = pick.name || "";
        const links = pick.links || {};
        $("artistIndexInstagram").value = links.instagram || "";
        $("artistIndexBluesky").value = links.bluesky || "";
        $("artistIndexX").value = links.x || "";
        $("artistIndexArtstation").value = links.artstation || "";
        $("artistIndexWebsite").value = links.website || "";
        $("artistIndexLinktree").value = links.linktree || "";
      });
      $("artistIndexSave").addEventListener("click", async () => {
        try{
          const body = {
            artist_id: $("artistIndexId").value.trim() || undefined,
            name: $("artistIndexName").value.trim(),
            links: {
              instagram: $("artistIndexInstagram").value.trim(),
              bluesky: $("artistIndexBluesky").value.trim(),
              x: $("artistIndexX").value.trim(),
              artstation: $("artistIndexArtstation").value.trim(),
              website: $("artistIndexWebsite").value.trim(),
              linktree: $("artistIndexLinktree").value.trim()
            }
          };
          const res = await fetch("/api/tarot/artists", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-API-Key": apiKeyEl.value.trim()
            },
            body: JSON.stringify(body)
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
          await loadTarotArtists();
          setStatus("Artist saved.", "ok");
        }catch(err){
          setStatus(err.message, "err");
        }
      });
      $("artistIndexDelete").addEventListener("click", async () => {
        const artistId = $("artistIndexId").value.trim();
        if (!artistId){
          setStatus("Select an artist to delete.", "err");
          return;
        }
        if (!confirm("Delete this artist? Cards will keep the artist_id but links will no longer resolve.")){
          return;
        }
        try{
          const res = await fetch("/api/tarot/artists/" + encodeURIComponent(artistId), {
            method: "DELETE",
            headers: {"X-API-Key": apiKeyEl.value.trim()}
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
          $("artistIndexId").value = "";
          $("artistIndexName").value = "";
          $("artistIndexInstagram").value = "";
          $("artistIndexBluesky").value = "";
          $("artistIndexX").value = "";
          $("artistIndexArtstation").value = "";
          $("artistIndexWebsite").value = "";
          $("artistIndexLinktree").value = "";
          await loadTarotArtists();
          setStatus("Artist deleted.", "ok");
        }catch(err){
          setStatus(err.message, "err");
        }
      });

      $("mediaLibraryOpen").addEventListener("click", () => {
        librarySelectHandler = null;
        showLibraryModal(true);
        loadLibrary("media");
        loadTarotArtists();
      });

      $("mediaLibraryRefresh").addEventListener("click", () => loadMediaLibrary());
      $("mediaTabUploadBtn").addEventListener("click", () => setMediaTab("upload"));
      $("mediaTabEditBtn").addEventListener("click", () => setMediaTab("edit"));
      const mediaToolbarSearch = $("mediaToolbarSearch");
      if (mediaToolbarSearch){
        mediaToolbarSearch.addEventListener("input", () => applyMediaFilters());
      }
      const mediaFilterArtist = $("mediaFilterArtist");
      if (mediaFilterArtist){
        mediaFilterArtist.addEventListener("change", () => applyMediaFilters());
      }
      const mediaFilterType = $("mediaFilterType");
      if (mediaFilterType){
        mediaFilterType.addEventListener("change", () => loadMediaLibrary());
      }
      const mediaFilterOriginType = $("mediaFilterOriginType");
      if (mediaFilterOriginType){
        mediaFilterOriginType.addEventListener("change", () => applyMediaFilters());
      }
      const mediaFilterVenue = $("mediaFilterVenue");
      if (mediaFilterVenue){
        mediaFilterVenue.addEventListener("change", () => loadMediaLibrary());
      }
      const mediaFilterLabel = $("mediaFilterLabel");
      if (mediaFilterLabel){
        mediaFilterLabel.addEventListener("change", () => applyMediaFilters());
      }
      const mediaToolbarSort = $("mediaToolbarSort");
      if (mediaToolbarSort){
        mediaToolbarSort.addEventListener("change", () => applyMediaFilters());
      }
        const mediaFilterClear = $("mediaFilterClear");
        if (mediaFilterClear){
          mediaFilterClear.addEventListener("click", () => {
            const artist = $("mediaFilterArtist");
            const type = $("mediaFilterType");
            const origin = $("mediaFilterOriginType");
            const venue = $("mediaFilterVenue");
            const label = $("mediaFilterLabel");
            if (artist) artist.value = "";
            if (type) type.value = "";
            if (origin) origin.value = "";
            if (venue) venue.value = "";
            if (label) label.value = "any";
            loadMediaLibrary();
          });
        }
      $("mediaBulkDelete").addEventListener("click", async () => {
        if (!hasScope("admin:web")){
          setMediaLibraryStatus("Delete requires admin access.", "err");
          showToast("Delete requires admin access.", "err");
          return;
        }
        const items = getSelectedMediaItems();
        if (!items.length) return;
        if (!confirm(`Delete ${items.length} image(s)? This cannot be undone.`)) return;
        try{
          setMediaLibraryStatus("Deleting...", "");
          for (const item of items){
            if (!item.delete_url) continue;
            const res = await fetch(item.delete_url, {method: "DELETE", headers: {"X-API-Key": apiKeyEl.value.trim()}});
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data.ok === false){
              throw new Error(data.error || "Delete failed");
            }
          }
          showToast("Images deleted.", "ok");
          await loadMediaLibrary();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
          showToast(err.message, "err");
        }
      });
      $("mediaBulkHide").addEventListener("click", async () => {
        const items = getSelectedMediaItems();
        if (!items.length) return;
        try{
          setMediaLibraryStatus("Hiding...", "");
          for (const item of items){
            await setMediaHidden(item, true);
          }
          showToast("Images hidden.", "ok");
          applyMediaFilters();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
          showToast(err.message, "err");
        }
      });
      $("mediaBulkShow").addEventListener("click", async () => {
        const items = getSelectedMediaItems();
        if (!items.length) return;
        try{
          setMediaLibraryStatus("Showing...", "");
          for (const item of items){
            await setMediaHidden(item, false);
          }
          showToast("Images shown.", "ok");
          applyMediaFilters();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
          showToast(err.message, "err");
        }
      });
      $("mediaBulkSetArtist").addEventListener("click", async () => {
        const artistId = $("mediaBulkArtist").value.trim();
        const artistName = $("mediaBulkArtist").selectedOptions.length
          ? $("mediaBulkArtist").selectedOptions[0].textContent.trim()
          : "";
        if (!artistId){
          showToast("Pick an artist.", "err");
          return;
        }
        try{
          setMediaLibraryStatus("Updating artists...", "");
          await bulkUpdateMedia({artist_id: artistId, artist_name: artistName});
          showToast("Artists updated.", "ok");
          await loadMediaLibrary();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
        }
      });
      $("mediaBulkSetOrigin").addEventListener("click", async () => {
        const originType = $("mediaBulkOriginType").value.trim();
        if (!originType){
          showToast("Pick an origin type.", "err");
          return;
        }
        try{
          setMediaLibraryStatus("Updating origin type...", "");
          await bulkUpdateMedia({origin_type: originType});
          showToast("Origin type updated.", "ok");
          await loadMediaLibrary();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
        }
      });
      $("mediaBulkApplyLabel").addEventListener("click", async () => {
        const label = $("mediaBulkLabel").value.trim();
        if (!label){
          showToast("Enter a label.", "err");
          return;
        }
        try{
          setMediaLibraryStatus("Updating labels...", "");
          await bulkUpdateMedia({origin_label: label});
          showToast("Labels updated.", "ok");
          await loadMediaLibrary();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
        }
      });
      $("mediaBulkClearLabel").addEventListener("click", async () => {
        try{
          setMediaLibraryStatus("Clearing labels...", "");
          await bulkUpdateMedia({origin_label: ""});
          showToast("Labels cleared.", "ok");
          $("mediaBulkLabel").value = "";
          await loadMediaLibrary();
        }catch(err){
          setMediaLibraryStatus(err.message, "err");
        }
      });
      $("mediaUploadFile").addEventListener("change", (ev) => {
        const file = ev.target.files[0] || null;
        mediaUploadFile = file;
        updateMediaUploadDropDisplay(file);
        updateMediaUploadState();
      });
      $("mediaUploadTitleInput").addEventListener("input", () => updateMediaUploadState());

      const mediaDrop = $("mediaUploadDrop");
      if (mediaDrop){
        mediaDrop.addEventListener("click", () => $("mediaUploadFile").click());
        mediaDrop.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " "){
            ev.preventDefault();
            $("mediaUploadFile").click();
          }
        });
        mediaDrop.addEventListener("dragover", (ev) => {
          ev.preventDefault();
          mediaDrop.classList.add("dragover");
        });
        mediaDrop.addEventListener("dragleave", () => mediaDrop.classList.remove("dragover"));
        mediaDrop.addEventListener("drop", (ev) => {
          ev.preventDefault();
          mediaDrop.classList.remove("dragover");
          const file = ev.dataTransfer && ev.dataTransfer.files ? ev.dataTransfer.files[0] : null;
          if (file){
            mediaUploadFile = file;
            updateMediaUploadDropDisplay(file);
            updateMediaUploadState();
          }
        });
      }

        $("mediaUploadUpload").addEventListener("click", async () => {
          const file = mediaUploadFile || ($("mediaUploadFile").files[0] || null);
          if (!file){
            setMediaUploadStatus("Select an image to upload.", "err");
            return;
          }
        const title = $("mediaUploadTitleInput").value.trim();
        if (!title){
          setMediaUploadStatus("Enter a title before uploading.", "err");
          return;
        }
        try{
          $("mediaUploadUpload").disabled = true;
          setMediaUploadStatus("Uploading...", "");
          const fd = new FormData();
          fd.append("file", file);
          fd.append("title", title);
            const artistId = $("mediaUploadArtist").value.trim();
            if (artistId) fd.append("artist_id", artistId);
            const originType = $("mediaUploadOriginType").value.trim();
            const originLabel = $("mediaUploadOriginLabel").value.trim();
            if (originType) fd.append("origin_type", originType);
            if (originLabel) fd.append("origin_label", originLabel);
            const mediaType = $("mediaUploadType").value.trim();
            const venueId = $("mediaUploadVenue").value.trim();
            if (mediaType) fd.append("media_type", mediaType);
            if (venueId) fd.append("venue_id", venueId);
            if ($("mediaUploadHidden")?.checked) fd.append("hidden", "1");
            const res = await fetch("/api/media/upload", {
              method: "POST",
              headers: {"X-API-Key": apiKeyEl.value.trim()},
            body: fd
          });
          const text = await res.text();
          let data = {};
          try{
            data = text ? JSON.parse(text) : {};
          }catch(err){
            const msg = (res.status === 401 || res.status === 403)
              ? "Unauthorized. Check API key."
              : "Upload failed (non-JSON response).";
            throw new Error(msg);
          }
          if (!res.ok || data.ok === false) throw new Error(data.error || "Failed");
          $("mediaUploadFile").value = "";
          $("mediaUploadTitleInput").value = "";
          $("mediaUploadOriginLabel").value = "";
          mediaUploadFile = null;
          updateMediaUploadDropDisplay(null);
          setMediaUploadStatus("Upload complete.", "ok");
          await loadMediaLibrary();
        }catch(err){
          setMediaUploadStatus(err.message, "err");
        }finally{
          updateMediaUploadState();
        }
      });

      $("mediaEditClear").addEventListener("click", () => {
        clearMediaSelection();
      });

      $("mediaEditSave").addEventListener("click", async () => {
        if (!currentMediaEdit){
          setMediaEditStatus("Select an image first.", "err");
          return;
        }
        const filename = $("mediaEditFilename").value.trim();
        if (!filename){
          setMediaEditStatus("Missing filename.", "err");
          return;
        }
        const title = $("mediaEditTitle").value.trim();
        const artistId = $("mediaEditArtist").value.trim();
          const artistName = $("mediaEditArtist").selectedOptions.length
            ? $("mediaEditArtist").selectedOptions[0].textContent.trim()
            : "";
          const originType = $("mediaEditOriginType").value.trim();
          const originLabel = $("mediaEditOriginLabel").value.trim();
          const mediaType = $("mediaEditType").value.trim();
          const venueId = $("mediaEditVenue").value.trim();
          try{
            $("mediaEditSave").disabled = true;
            setMediaEditStatus("Saving...", "");
            const res = await fetch("/api/gallery/media/update", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-API-Key": apiKeyEl.value.trim()
            },
              body: JSON.stringify({
                filename,
                title,
                artist_id: artistId,
                artist_name: artistName,
                origin_type: originType,
                origin_label: originLabel,
                media_type: mediaType,
                venue_id: venueId
              })
            });
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok === false){
            throw new Error(data.error || "Save failed");
          }
          setMediaEditStatus("Changes saved.", "ok");
          showToast("Changes saved.", "ok");
          await loadMediaLibrary();
        }catch(err){
          setMediaEditStatus(err.message, "err");
        }finally{
          $("mediaEditSave").disabled = !currentMediaEdit;
        }
      });

      $("mediaEditCopy").addEventListener("click", async () => {
        if (!currentMediaEdit) return;
        try{
          await navigator.clipboard.writeText(currentMediaEdit.url || "");
          showToast("Copied URL.", "ok");
        }catch(err){
          showToast("Copy failed.", "err");
        }
      });

      $("mediaEditOpen").addEventListener("click", () => {
        if (!currentMediaEdit) return;
        const url = currentMediaEdit.url || "";
        if (url) window.open(url, "_blank");
      });

      $("mediaEditDelete").addEventListener("click", async () => {
        if (!currentMediaEdit || !currentMediaEdit.delete_url) return;
        if (!hasScope("admin:web")){
          setMediaEditStatus("Delete requires admin access.", "err");
          showToast("Delete requires admin access.", "err");
          return;
        }
        if (!confirm("Delete this image? This cannot be undone.")) return;
        try{
          const res = await fetch(currentMediaEdit.delete_url, {method: "DELETE", headers: {"X-API-Key": apiKeyEl.value.trim()}});
          const data = await res.json().catch(() => ({}));
          if (!res.ok || data.ok === false){
            throw new Error(data.error || "Delete failed");
          }
          showToast("Image deleted.", "ok");
          await loadMediaLibrary();
        }catch(err){
          showToast(err.message, "err");
        }
      });

      $("mediaEditHide").addEventListener("click", async () => {
        if (!currentMediaEdit) return;
        try{
          await setMediaHidden(currentMediaEdit, !currentMediaEdit.hidden);
          showToast(currentMediaEdit.hidden ? "Hidden from gallery." : "Shown in gallery.", "ok");
          applyMediaFilters();
        }catch(err){
          showToast("Hide failed.", "err");
        }
      });

      $("uploadLibraryFile").addEventListener("change", (ev) => {
        const file = ev.target.files[0] || null;
        libraryUploadFile = file;
        updateUploadDropDisplay(file);
        updateUploadState();
      });
      $("uploadLibraryTitleInput").addEventListener("input", () => updateUploadState());

      const uploadDrop = $("uploadLibraryDrop");
      if (uploadDrop){
        uploadDrop.addEventListener("click", () => $("uploadLibraryFile").click());
        uploadDrop.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter" || ev.key === " "){
            ev.preventDefault();
            $("uploadLibraryFile").click();
          }
        });
        uploadDrop.addEventListener("dragover", (ev) => {
          ev.preventDefault();
          uploadDrop.classList.add("dragover");
        });
        uploadDrop.addEventListener("dragleave", () => uploadDrop.classList.remove("dragover"));
        uploadDrop.addEventListener("drop", (ev) => {
          ev.preventDefault();
          uploadDrop.classList.remove("dragover");
          const file = ev.dataTransfer && ev.dataTransfer.files ? ev.dataTransfer.files[0] : null;
          if (file){
            libraryUploadFile = file;
            updateUploadDropDisplay(file);
            updateUploadState();
          }
        });
      }

      $("uploadLibraryUpload").addEventListener("click", async () => {
        const file = libraryUploadFile || $("uploadLibraryFile").files[0];
        if (!file){
          setLibraryStatus("Select an image to upload.", "err");
          return;
        }
        const title = $("uploadLibraryTitleInput").value.trim();
        if (!title){
          setLibraryStatus("Enter a title before uploading.", "err");
          return;
        }
        try{
          $("uploadLibraryUpload").disabled = true;
          setLibraryStatus("Uploading...", "");
          const fd = new FormData();
          fd.append("file", file);
          fd.append("title", title);
          const artistId = $("uploadLibraryArtist").value.trim();
          if (artistId) fd.append("artist_id", artistId);
          if ($("uploadLibraryHidden")?.checked) fd.append("hidden", "1");
          const res = await fetch("/api/media/upload", {
            method: "POST",
            headers: {"X-API-Key": apiKeyEl.value.trim()},
            body: fd
          });
          const text = await res.text();
          let data = {};
          try{
            data = text ? JSON.parse(text) : {};
          }catch(err){
            const msg = (res.status === 401 || res.status === 403)
              ? "Unauthorized. Check API key."
              : "Upload failed (non-JSON response).";
            throw new Error(msg);
          }
          if (!res.ok || data.ok === false) throw new Error(data.error || "Failed");
          $("uploadLibraryFile").value = "";
          $("uploadLibraryTitleInput").value = "";
          libraryUploadFile = null;
          updateUploadDropDisplay(null);
          setLibraryStatus("Upload complete.", "ok");
          await loadLibrary("media");
        }catch(err){
          setLibraryStatus(err.message, "err");
        }finally{
          updateUploadState();
        }
      });

      $("taCardSuit").addEventListener("input", () => {
        const suitValue = $("taCardSuit").value.trim();
        taRenderSuitInfo(suitValue);
        taRenderThemeWeights({}, suitValue);
        taApplySuitThemeDefaults(suitValue);
        taSetDirty(true);
      });
      $("taCardNumber").addEventListener("input", (ev) => {
        taRenderNumberInfo(ev.target.value);
        taRenderPreviews({
          name: $("taCardName").value.trim(),
          number: ev.target.value,
          image: window.taUploadedImageUrl || ""
        });
        taSetDirty(true);
      });
      ["taCardId", "taCardName", "taCardTags", "taCardFlavor", "taCardUpright", "taCardReversed"].forEach((id) => {
        const el = $(id);
        if (!el) return;
        el.addEventListener("input", () => {
          taSetDirty(true);
          if (id === "taCardName"){
            taRenderPreviews({
              name: $("taCardName").value.trim(),
              number: $("taCardNumber").value.trim(),
              image: window.taUploadedImageUrl || ""
            });
          }
        });
      });
      const templateSelect = $("taCardTemplate");
      if (templateSelect){
        templateSelect.addEventListener("change", () => {
          const pick = templateSelect.value;
          if (!pick) return;
          const purpose = taGetDeckPurpose();
          const cards = taTemplateCache[purpose] || [];
          const card = cards.find(c => (c.card_id || c.id) === pick);
          if (card){
            taApplyTemplateCard(card);
          }
        });
      }
      const newCardBtn = $("taNewCard");
      if (newCardBtn){
        newCardBtn.addEventListener("click", () => {
          taSelectedCardId = "";
          $("taCardId").value = "";
          $("taCardName").value = "";
          $("taCardSuit").value = "";
          $("taCardNumber").value = "";
          $("taCardTags").value = "";
          $("taCardFlavor").value = "";
          $("taCardUpright").value = "";
          $("taCardReversed").value = "";
          $("taCardArtist").value = "";
          window.taUploadedImageUrl = "";
          taRenderNumberInfo("");
          taSetCardThemeWeights({});
          const templateSelect = $("taCardTemplate");
          if (templateSelect){
            templateSelect.value = "";
          }
          taRenderPreviews(null);
          taUpdateContext(null);
          taSetDirty(false);
        });
      }
      $("taDeckList").addEventListener("click", (ev) => {
        const target = ev.target.closest(".list-card");
        if (!target || !target.dataset.cardId || !window.taDeckData) return;
        const card = (window.taDeckData.cards || []).find(c => c.card_id === target.dataset.cardId);
        if (card){
          taLoadCard(card);
        }
      });
      async function loadTarotDeck(){
        try{
          const deck = $("taDeck").value.trim() || "elf-classic";
          const data = await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck), {method:"GET"}, true);
          showList($("taDeckList"), data);
          await taLoadTemplateOptions();
          const templateSelect = $("taCardTemplate");
          if (templateSelect){
            templateSelect.value = "";
          }
          taSetSuitDefinitions(data.deck && Array.isArray(data.deck.suits) ? data.deck.suits : []);
          taRenderPreviews(null);
          const deckName = (data.deck && (data.deck.name || data.deck.deck_id)) || deck;
          const count = Array.isArray(data.cards) ? data.cards.length : 0;
          setTarotStatus(`Deck loaded: ${deckName} (${count} cards)`, "ok");
          taUpdateContext(null);
          taDirty = false;
        }catch(err){
          setTarotStatus(err.message, "err");
        }
      }

      async function loadGallerySettings(){
        try{
          const data = await jsonFetch("/api/gallery/settings", {method:"GET"}, true);
          gallerySettingsCache = data || {};
          galleryHiddenDecks = Array.isArray(data.hidden_decks) ? data.hidden_decks : [];
        }catch(err){
          gallerySettingsCache = null;
          galleryHiddenDecks = [];
        }
      }

      $("taDeck").addEventListener("change", async () => {
        await loadTarotDeck();
      });

      $("taAddDeck").addEventListener("click", () => {
        $("deckCreateId").value = "";
        $("deckCreateName").value = "";
        $("deckCreatePurpose").value = "tarot";
        $("deckCreateTheme").value = "classic";
        $("deckCreateSeed").value = "none";
        $("deckCreatePerHouse").value = "4";
        $("deckCreateCrown").value = "1";
        $("deckCreateSuitPreset").value = "forest";
        $("deckCreateSuitJson").value = formatSuitPresetJson("forest");
        $("deckCreateBackPick").dataset.backUrl = "";
        $("deckCreateBackPick").dataset.artistId = "";
        $("deckCreateBackPreview").innerHTML = '<span class="preview-label">Back</span>';
        $("deckCreateModal").classList.add("show");
      });

      $("taEditDeck").addEventListener("click", async () => {
        const deck = $("taDeck").value.trim();
        if (!deck){
          setTarotStatus("Pick a deck to edit.", "err");
          return;
        }
        try{
          await loadGallerySettings();
          if (!window.taDeckData || !window.taDeckData.deck || window.taDeckData.deck.deck_id !== deck){
            const data = await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck), {method:"GET"}, true);
            showList($("taDeckList"), data);
          }
          const deckData = window.taDeckData && window.taDeckData.deck ? window.taDeckData.deck : {};
          $("deckEditName").value = deckData.name || "";
          $("deckEditPurpose").value = deckData.purpose || "tarot";
          $("deckEditTheme").value = deckData.theme || "classic";
          const suits = Array.isArray(deckData.suits) ? deckData.suits : [];
          deckEditHadSuits = suits.length > 0;
          if (suits.length){
            $("deckEditSuitPreset").value = "custom";
            $("deckEditSuitJson").value = JSON.stringify(suits, null, 2);
          }else{
            $("deckEditSuitPreset").value = "forest";
            $("deckEditSuitJson").value = formatSuitPresetJson("forest");
          }
          const backUrl = deckData.back_image || "";
          const preview = $("deckEditBackPreview");
          if (preview){
            preview.innerHTML = '<span class="preview-label">Back</span>';
            if (backUrl){
              const img = document.createElement("img");
              img.src = backUrl;
              preview.appendChild(img);
            }
          }
          $("deckEditBackPick").dataset.backUrl = backUrl;
          $("deckEditBackPick").dataset.artistId = deckData.back_artist_id || "";
          const hideToggle = $("deckEditHideGallery");
          if (hideToggle){
            hideToggle.checked = galleryHiddenDecks.includes(deck);
          }
          $("deckEditModal").classList.add("show");
        }catch(err){
          setTarotStatus(err.message, "err");
        }
      });

      $("deckEditClose").addEventListener("click", () => {
        $("deckEditModal").classList.remove("show");
      });
      $("deckEditModal").addEventListener("click", (event) => {
        if (event.target === $("deckEditModal")){
          $("deckEditModal").classList.remove("show");
        }
      });
      $("deckEditBackPick").addEventListener("click", () => {
        librarySelectHandler = (item) => {
          $("deckEditBackPick").dataset.backUrl = item.url || "";
          $("deckEditBackPick").dataset.artistId = item.artist_id || "";
          const preview = $("deckEditBackPreview");
          if (preview){
            preview.innerHTML = '<span class="preview-label">Back</span>';
            if (item.url){
              const img = document.createElement("img");
              img.src = item.url;
              preview.appendChild(img);
            }
          }
          setTarotStatus(item.url ? "Deck back selected." : "Pick a deck back.", "ok");
        };
        showLibraryModal(true);
        loadLibrary("media");
      });

      $("deckEditTheme").addEventListener("change", (ev) => {
        const theme = ev.target.value || "classic";
        if (!window.taDeckData) window.taDeckData = {};
        window.taDeckData.deck = window.taDeckData.deck || {};
        window.taDeckData.deck.theme = theme;
        taRenderPreviews({
          name: $("taCardName").value.trim(),
          number: $("taCardNumber").value.trim(),
          image: window.taUploadedImageUrl || ""
        });
      });

      $("deckEditSubmit").addEventListener("click", async () => {
        const deck = $("taDeck").value.trim();
        if (!deck){
          setTarotStatus("Pick a deck to edit.", "err");
          return;
        }
        const name = $("deckEditName").value.trim();
        const purpose = $("deckEditPurpose").value || "tarot";
        const theme = $("deckEditTheme").value || "classic";
        const backUrl = $("deckEditBackPick").dataset.backUrl || "";
        const artistId = $("deckEditBackPick").dataset.artistId || "";
        let suits = null;
        try{
          suits = parseSuitJson($("deckEditSuitJson").value);
        }catch(err){
          setTarotStatus(err.message, "err");
          return;
        }
        if (!deckEditHadSuits && (!suits || !suits.length)){
          setTarotStatus("Choose a suit preset to migrate this deck.", "err");
          return;
        }
        try{
          await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck), {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              name: name || undefined,
              purpose,
              theme,
              suits: suits && suits.length ? suits : []
            })
          }, true);
          if (backUrl){
            await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck) + "/back", {
              method:"PUT",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({back_image: backUrl, artist_id: artistId || undefined})
            }, true);
          }
          const hideToggle = $("deckEditHideGallery");
          if (hideToggle){
            const wantHidden = hideToggle.checked;
            const nextHidden = new Set(galleryHiddenDecks || []);
            if (wantHidden){
              nextHidden.add(deck);
            }else{
              nextHidden.delete(deck);
            }
            galleryHiddenDecks = Array.from(nextHidden);
            await jsonFetch("/api/gallery/settings", {
              method:"POST",
              headers: {"Content-Type": "application/json"},
              body: JSON.stringify({hidden_decks: galleryHiddenDecks})
            }, true);
          }
          $("deckEditModal").classList.remove("show");
          await loadTarotDeck();
          setTarotStatus("Deck updated.", "ok");
        }catch(err){
          setTarotStatus(err.message, "err");
        }
      });

      $("taDeleteDeck").addEventListener("click", async () => {
        if (!authUserIsElfmin){
          setTarotStatus("Only elfministrators can delete decks.", "err");
          return;
        }
        const deck = $("taDeck").value.trim();
        if (!deck){
          setTarotStatus("Pick a deck to delete.", "err");
          return;
        }
        if (!confirm("This deck will fall from the forest. Continue?")){
          return;
        }
        try{
          await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck), {method:"DELETE"}, true);
          setTarotStatus("Deck deleted.", "ok");
          await loadTarotDeckList();
          $("taDeckList").textContent = "No deck loaded.";
          taSelectedCardId = "";
          taRenderPreviews(null);
        }catch(err){
          setTarotStatus(err.message, "err");
        }
      });

      $("taSaveCard").addEventListener("click", async () => {
        try{
          const deck = $("taDeck").value.trim() || "elf-classic";
          const tags = $("taCardTags").value.split(",").map(t => t.trim()).filter(Boolean);
          const body = {
            card_id: $("taCardId").value.trim() || undefined,
            name: $("taCardName").value.trim(),
            suit: $("taCardSuit").value.trim(),
            number: $("taCardNumber").value.trim() || undefined,
            image: window.taUploadedImageUrl || undefined,
            artist_id: $("taCardArtist").value.trim() || undefined,
            tags,
            flavor_text: $("taCardFlavor").value.trim() || undefined,
            upright: $("taCardUpright").value.trim(),
            reversed: $("taCardReversed").value.trim(),
            themes: taGetCardThemeWeights(),
            artist_links: undefined
          };
          const saved = await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck) + "/cards", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body)
          });
          $("taCardId").value = "";
          $("taCardName").value = "";
          $("taCardSuit").value = "";
          $("taCardNumber").value = "";
          window.taUploadedImageUrl = "";
          $("taCardTags").value = "";
          $("taCardFlavor").value = "";
          $("taCardUpright").value = "";
          $("taCardReversed").value = "";
          $("taCardArtist").value = "";
          const templateSelect = $("taCardTemplate");
          if (templateSelect){
            templateSelect.value = "";
          }
          taRenderNumberInfo("");
          taSetCardThemeWeights({});
          taSelectedCardId = (saved && saved.card && saved.card.card_id) ? saved.card.card_id : (body.card_id || "");
          taDirty = false;
          await loadTarotDeck();
          setTarotStatus("Saved", "ok");
        }catch(err){
          setTarotStatus(err.message, "err");
        }
      });

      async function loadTarotDeckList(selectValue, autoLoad = true){
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          const decks = data.decks || [];
          const select = $("taDeck");
          select.innerHTML = "";
          decks.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.deck_id;
            const purposeLabel = d.purpose ? ` • ${d.purpose}` : "";
            opt.textContent = d.name ? `${d.name} (${d.deck_id})${purposeLabel}` : `${d.deck_id}${purposeLabel}`;
            select.appendChild(opt);
          });
          select.value = selectValue || "elf-classic";
          if (autoLoad && select.value){
            await loadTarotDeck();
          }
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      // ========== Dice Editor ==========
      let diceSelectedFaceId = "";
      let diceFaces = [];

      function setDiceStatus(msg, kind){
        const statusEl = $("diceSetStatus");
        if (!statusEl) return;
        statusEl.textContent = msg || "";
        statusEl.className = "status" + (kind ? " status-" + kind : "");
      }

      async function loadDiceSetList(selectValue, autoLoad = true){
        if (!ensureScope("dice:admin", "Dice access required.")) return;
        try{
          const data = await jsonFetch("/api/dice/sets", {method:"GET"}, true);
          const sets = data.dice_sets || [];
          const select = $("diceSet");
          select.innerHTML = "";
          sets.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.dice_id;
            opt.textContent = d.name ? `${d.name} (${d.dice_id})` : d.dice_id;
            select.appendChild(opt);
          });
          select.value = selectValue || (sets.length > 0 ? sets[0].dice_id : "");
          if (autoLoad && select.value){
            await loadDiceSet();
          }
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      async function loadDiceSet(){
        try{
          const dice_id = $("diceSet").value.trim();
          if (!dice_id){
            $("diceFaceList").textContent = "No dice set loaded.";
            setDiceStatus("Pick a dice set to begin.", "ok");
            return;
          }
          const data = await jsonFetch("/api/dice/sets/" + encodeURIComponent(dice_id), {method:"GET"}, true);
          diceFaces = data.faces || [];
          
          // Load sprite config from metadata
          if (data.dice_set && data.dice_set.metadata){
            diceSpriteSheet = data.dice_set.metadata.sprite_sheet || "";
            diceSpriteCols = data.dice_set.metadata.sprite_cols || 3;
            diceSpriteRows = data.dice_set.metadata.sprite_rows || 4;
            $("diceSpriteSheetUrl").value = diceSpriteSheet;
            $("diceSpriteCols").value = diceSpriteCols;
            $("diceSpriteRows").value = diceSpriteRows;
            renderDiceSymbolPicker();
          }
          
          renderDiceFaceList();
          const setName = (data.dice_set && (data.dice_set.name || data.dice_set.dice_id)) || dice_id;
          const count = diceFaces.length;
          setDiceStatus(`Dice set loaded: ${setName} (${count} faces)`, "ok");
        }catch(err){
          setDiceStatus(err.message, "err");
        }
      }

      function renderDiceFaceList(){
        const listEl = $("diceFaceList");
        if (!listEl) return;
        if (!diceFaces || diceFaces.length === 0){
          listEl.textContent = "No faces yet.";
          return;
        }
        listEl.innerHTML = "";
        diceFaces.forEach(face => {
          const item = document.createElement("div");
          item.className = "list-item" + (face.face_id === diceSelectedFaceId ? " selected" : "");
          item.textContent = face.name || face.face_id;
          item.addEventListener("click", () => loadDiceFace(face));
          listEl.appendChild(item);
        });
      }

      function loadDiceFace(face){
        diceSelectedFaceId = face.face_id;
        $("diceFaceId").value = face.face_id || "";
        $("diceFaceName").value = face.name || "";
        $("diceFaceValue").value = face.value || 0;
        $("diceFaceWeight").value = face.weight || 1;
        $("diceFaceGridX").value = face.grid_x || 0;
        $("diceFaceGridY").value = face.grid_y || 0;
        $("diceFaceDescription").value = face.description || "";
        $("diceFaceEffect").value = face.effect || "";
        updateDiceSymbolPreview();
        renderDiceFaceList();
      }

      // Dice sprite sheet management
      let diceSpriteSheet = "";
      let diceSpriteCols = 3;
      let diceSpriteRows = 4;

      function renderDiceSymbolPicker(){
        const picker = $("diceFaceSymbolPicker");
        if (!picker) return;
        
        if (!diceSpriteSheet){
          picker.innerHTML = '<div class="muted">Configure sprite sheet first</div>';
          return;
        }

        picker.innerHTML = "";
        const totalSymbols = diceSpriteCols * diceSpriteRows;
        
        for (let i = 0; i < totalSymbols; i++){
          const col = i % diceSpriteCols;
          const row = Math.floor(i / diceSpriteCols);
          
          const item = document.createElement("div");
          item.className = "symbol-picker-item";
          item.style.backgroundImage = `url(${diceSpriteSheet})`;
          
          // Calculate background position to show one symbol
          const percentX = (col / (diceSpriteCols - 1)) * 100;
          const percentY = (row / (diceSpriteRows - 1)) * 100;
          item.style.backgroundPosition = `${percentX}% ${percentY}%`;
          item.style.backgroundSize = `${diceSpriteCols * 100}% ${diceSpriteRows * 100}%`;
          
          item.dataset.col = col;
          item.dataset.row = row;
          
          item.addEventListener("click", () => {
            $("diceFaceGridX").value = col;
            $("diceFaceGridY").value = row;
            updateDiceSymbolPreview();
            
            // Highlight selected
            picker.querySelectorAll(".symbol-picker-item").forEach(el => el.classList.remove("selected"));
            item.classList.add("selected");
          });
          
          picker.appendChild(item);
        }
      }

      function updateDiceSymbolPreview(){
        const preview = $("diceFacePreviewSprite");
        if (!preview || !diceSpriteSheet) return;
        
        const col = parseInt($("diceFaceGridX").value) || 0;
        const row = parseInt($("diceFaceGridY").value) || 0;
        
        preview.style.backgroundImage = `url(${diceSpriteSheet})`;
        const percentX = (col / (diceSpriteCols - 1)) * 100;
        const percentY = (row / (diceSpriteRows - 1)) * 100;
        preview.style.backgroundPosition = `${percentX}% ${percentY}%`;
        preview.style.backgroundSize = `${diceSpriteCols * 100}% ${diceSpriteRows * 100}%`;
      }

      // Media picker for dice faces
      let mediaPickerTarget = null;
      let allMediaItems = [];

      async function loadMediaItems(){
        try{
          const response = await jsonFetch("/api/gallery/admin/items", {method:"GET"}, true);
          allMediaItems = response.items || [];
          renderMediaPicker();
        }catch(err){
          console.error("Failed to load media items:", err);
        }
      }

      function renderMediaPicker(){
        const grid = $("mediaPickerGrid");
        if (!grid) return;
        
        const filterType = $("mediaTypeFilter") ? $("mediaTypeFilter").value : "";
        let filtered = allMediaItems;
        
        if (filterType){
          filtered = allMediaItems.filter(item => {
            const meta = item.metadata || {};
            return meta.media_type === filterType;
          });
        }
        
        grid.innerHTML = "";
        if (filtered.length === 0){
          grid.innerHTML = '<div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: #999;">No media items found</div>';
          return;
        }
        
        filtered.forEach(item => {
          const div = document.createElement("div");
          div.style.cssText = "cursor: pointer; border: 2px solid #444; border-radius: 4px; overflow: hidden; transition: all 0.2s;";
          div.innerHTML = `
            <img src="${item.thumb_url || item.url}" style="width: 100%; height: 120px; object-fit: cover; display: block;">
            <div style="padding: 0.5rem; font-size: 0.8rem; color: #aaa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${item.title || item.filename}</div>
          `;
          div.addEventListener("mouseenter", () => {
            div.style.borderColor = "#4a9eff";
            div.style.boxShadow = "0 0 8px rgba(74, 158, 255, 0.5)";
          });
          div.addEventListener("mouseleave", () => {
            div.style.borderColor = "#444";
            div.style.boxShadow = "none";
          });
          div.addEventListener("click", () => {
            selectMediaForFace(item);
          });
          grid.appendChild(div);
        });
      }

      function selectMediaForFace(item){
        if (!mediaPickerTarget) return;
        $("diceFaceImageUrl").value = item.url;
        closeMediaPicker();
      }

      function openMediaPicker(target){
        mediaPickerTarget = target;
        const modal = $("mediaPickerModal");
        if (modal) modal.style.display = "block";
        loadMediaItems();
      }

      function closeMediaPicker(){
        const modal = $("mediaPickerModal");
        if (modal) modal.style.display = "none";
        mediaPickerTarget = null;
      }

      // Event listeners for media picker
      if ($("diceFaceLibrary")){
        $("diceFaceLibrary").addEventListener("click", () => openMediaPicker("dice_face"));
      }
      if ($("mediaPickerClose")){
        $("mediaPickerClose").addEventListener("click", closeMediaPicker);
      }
      if ($("mediaTypeFilter")){
        $("mediaTypeFilter").addEventListener("change", renderMediaPicker);
      }
      if ($("mediaPickerModal")){
        $("mediaPickerModal").addEventListener("click", (e) => {
          if (e.target.id === "mediaPickerModal") closeMediaPicker();
        });
      }

      $("diceSet").addEventListener("change", async () => {
        await loadDiceSet();
      });

      $("diceAddSet").addEventListener("click", async () => {
        const dice_id = prompt("Enter dice set ID:");
        if (!dice_id) return;
        const name = prompt("Enter dice set name:");
        try{
          await jsonFetch("/api/dice/sets", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({dice_id, name: name || dice_id, sides: 6})
          }, true);
          await loadDiceSetList(dice_id);
          setDiceStatus("Dice set created.", "ok");
        }catch(err){
          setDiceStatus(err.message, "err");
        }
      });

      $("diceEditSet").addEventListener("click", async () => {
        const dice_id = $("diceSet").value.trim();
        if (!dice_id){
          setDiceStatus("Pick a dice set to edit.", "err");
          return;
        }
        const name = prompt("Enter new name:");
        if (!name) return;
        try{
          await jsonFetch("/api/dice/sets/" + encodeURIComponent(dice_id), {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name})
          }, true);
          await loadDiceSetList(dice_id);
          setDiceStatus("Dice set updated.", "ok");
        }catch(err){
          setDiceStatus(err.message, "err");
        }
      });

      $("diceDeleteSet").addEventListener("click", async () => {
        const dice_id = $("diceSet").value.trim();
        if (!dice_id){
          setDiceStatus("Pick a dice set to delete.", "err");
          return;
        }
        if (!confirm("Delete this dice set?")){
          return;
        }
        try{
          await jsonFetch("/api/dice/sets/" + encodeURIComponent(dice_id), {method:"DELETE"}, true);
          setDiceStatus("Dice set deleted.", "ok");
          await loadDiceSetList();
          $("diceFaceList").textContent = "No dice set loaded.";
          diceSelectedFaceId = "";
        }catch(err){
          setDiceStatus(err.message, "err");
        }
      });

      $("diceNewFace").addEventListener("click", () => {
        diceSelectedFaceId = "";
        $("diceFaceId").value = "";
        $("diceFaceName").value = "";
        $("diceFaceValue").value = "1";
        $("diceFaceWeight").value = "1";
        $("diceFaceGridX").value = "0";
        $("diceFaceGridY").value = "0";
        $("diceFaceDescription").value = "";
        $("diceFaceEffect").value = "";
        renderDiceFaceList();
      });

      $("diceSaveSpriteConfig").addEventListener("click", async () => {
        const dice_id = $("diceSet").value.trim();
        if (!dice_id){
          setDiceStatus("Pick a dice set first.", "err");
          return;
        }
        diceSpriteSheet = $("diceSpriteSheetUrl").value.trim();
        diceSpriteCols = parseInt($("diceSpriteCols").value) || 3;
        diceSpriteRows = parseInt($("diceSpriteRows").value) || 4;
        
        try{
          await jsonFetch("/api/dice/sets/" + encodeURIComponent(dice_id), {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              metadata: {
                sprite_sheet: diceSpriteSheet,
                sprite_cols: diceSpriteCols,
                sprite_rows: diceSpriteRows
              }
            })
          }, true);
          renderDiceSymbolPicker();
          setDiceStatus("Sprite sheet config saved.", "ok");
        }catch(err){
          setDiceStatus(err.message, "err");
        }
      });

      $("diceSaveFace").addEventListener("click", async () => {
        const dice_id = $("diceSet").value.trim();
        if (!dice_id){
          setDiceStatus("Pick a dice set first.", "err");
          return;
        }
        const face = {
          face_id: $("diceFaceId").value.trim() || Date.now().toString(),
          name: $("diceFaceName").value.trim(),
          value: parseInt($("diceFaceValue").value) || 0,
          weight: parseFloat($("diceFaceWeight").value) || 1,
          grid_x: parseInt($("diceFaceGridX").value) || 0,
          grid_y: parseInt($("diceFaceGridY").value) || 0,
          description: $("diceFaceDescription").value.trim(),
          effect: $("diceFaceEffect").value.trim()
        };
        try{
          const existingIndex = diceFaces.findIndex(f => f.face_id === face.face_id);
          if (existingIndex >= 0){
            diceFaces[existingIndex] = face;
          }else{
            diceFaces.push(face);
          }
          await jsonFetch("/api/dice/sets/" + encodeURIComponent(dice_id) + "/faces", {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({faces: diceFaces})
          }, true);
          diceSelectedFaceId = face.face_id;
          await loadDiceSet();
          setDiceStatus("Face saved.", "ok");
        }catch(err){
          setDiceStatus(err.message, "err");
        }
      });

      // ========== Slots Editor ==========
      let slotsSelectedSymbolId = "";
      let slotsSymbols = [];
      let slotsSpriteSheet = "";
      let slotsSpriteCols = 3;
      let slotsSpriteRows = 4;

      function setSlotsStatus(msg, kind){
        const statusEl = $("slotsMachineStatus");
        if (!statusEl) return;
        statusEl.textContent = msg || "";
        statusEl.className = "status" + (kind ? " status-" + kind : "");
      }

      function renderSymbolPicker(){
        const picker = $("slotsSymbolPicker");
        if (!picker) return;
        
        if (!slotsSpriteSheet){
          picker.innerHTML = '<div class="muted">Configure sprite sheet first</div>';
          return;
        }

        picker.innerHTML = "";
        const totalSymbols = slotsSpriteCols * slotsSpriteRows;
        
        for (let i = 0; i < totalSymbols; i++){
          const col = i % slotsSpriteCols;
          const row = Math.floor(i / slotsSpriteCols);
          
          const item = document.createElement("div");
          item.className = "symbol-picker-item";
          item.style.backgroundImage = `url(${slotsSpriteSheet})`;
          
          // Calculate background position to show one symbol
          const percentX = (col / (slotsSpriteCols - 1)) * 100;
          const percentY = (row / (slotsSpriteRows - 1)) * 100;
          item.style.backgroundPosition = `${percentX}% ${percentY}%`;
          item.style.backgroundSize = `${slotsSpriteCols * 100}% ${slotsSpriteRows * 100}%`;
          
          item.dataset.col = col;
          item.dataset.row = row;
          
          item.addEventListener("click", () => {
            $("slotsSymbolGridX").value = col;
            $("slotsSymbolGridY").value = row;
            updateSymbolPreview();
            
            // Highlight selected
            picker.querySelectorAll(".symbol-picker-item").forEach(el => el.classList.remove("selected"));
            item.classList.add("selected");
          });
          
          picker.appendChild(item);
        }
      }

      function updateSymbolPreview(){
        const preview = $("slotsSymbolPreview");
        if (!preview || !slotsSpriteSheet) return;
        
        const col = parseInt($("slotsSymbolGridX").value) || 0;
        const row = parseInt($("slotsSymbolGridY").value) || 0;
        
        preview.style.backgroundImage = `url(${slotsSpriteSheet})`;
        const percentX = (col / (slotsSpriteCols - 1)) * 100;
        const percentY = (row / (slotsSpriteRows - 1)) * 100;
        preview.style.backgroundPosition = `${percentX}% ${percentY}%`;
        preview.style.backgroundSize = `${slotsSpriteCols * 100}% ${slotsSpriteRows * 100}%`;
      }

      function setSlotsStatus(msg, kind){
        const statusEl = $("slotsMachineStatus");
        if (!statusEl) return;
        statusEl.textContent = msg || "";
        statusEl.className = "status" + (kind ? " status-" + kind : "");
      }

      async function loadSlotMachineList(selectValue, autoLoad = true){
        if (!ensureScope("slots:admin", "Slots access required.")) return;
        try{
          const data = await jsonFetch("/api/slots/machines", {method:"GET"}, true);
          const machines = data.machines || [];
          const select = $("slotMachine");
          select.innerHTML = "";
          machines.forEach(m => {
            const opt = document.createElement("option");
            opt.value = m.machine_id;
            opt.textContent = m.name ? `${m.name} (${m.machine_id})` : m.machine_id;
            select.appendChild(opt);
          });
          select.value = selectValue || (machines.length > 0 ? machines[0].machine_id : "");
          if (autoLoad && select.value){
            await loadSlotMachine();
          }
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      async function loadSlotMachine(){
        try{
          const machine_id = $("slotMachine").value.trim();
          if (!machine_id){
            $("slotsSymbolList").textContent = "No slot machine loaded.";
            setSlotsStatus("Pick a machine to begin.", "ok");
            return;
          }
          const data = await jsonFetch("/api/slots/machines/" + encodeURIComponent(machine_id), {method:"GET"}, true);
          slotsSymbols = data.symbols || [];
          
          // Load sprite config from metadata
          const metadata = data.machine?.metadata || {};
          slotsSpriteSheet = metadata.sprite_sheet || "";
          slotsSpriteCols = metadata.sprite_cols || 3;
          slotsSpriteRows = metadata.sprite_rows || 4;
          
          $("slotsSpriteSheet").value = slotsSpriteSheet;
          $("slotsSpriteCols").value = slotsSpriteCols;
          $("slotsSpriteRows").value = slotsSpriteRows;
          
          renderSymbolPicker();
          renderSlotsSymbolList();
          
          const machineName = (data.machine && (data.machine.name || data.machine.machine_id)) || machine_id;
          const count = slotsSymbols.length;
          setSlotsStatus(`Slot machine loaded: ${machineName} (${count} symbols)`, "ok");
        }catch(err){
          setSlotsStatus(err.message, "err");
        }
      }

      function renderSlotsSymbolList(){
        const listEl = $("slotsSymbolList");
        if (!listEl) return;
        if (!slotsSymbols || slotsSymbols.length === 0){
          listEl.textContent = "No symbols yet.";
          return;
        }
        listEl.innerHTML = "";
        slotsSymbols.forEach(symbol => {
          const item = document.createElement("div");
          item.className = "list-item" + (symbol.symbol_id === slotsSelectedSymbolId ? " selected" : "");
          item.textContent = symbol.name || symbol.symbol_id;
          item.addEventListener("click", () => loadSlotsSymbol(symbol));
          listEl.appendChild(item);
        });
      }

      function loadSlotsSymbol(symbol){
        slotsSelectedSymbolId = symbol.symbol_id;
        $("slotsSymbolId").value = symbol.symbol_id || "";
        $("slotsSymbolName").value = symbol.name || "";
        $("slotsSymbolGridX").value = symbol.grid_x !== undefined ? symbol.grid_x : 0;
        $("slotsSymbolGridY").value = symbol.grid_y !== undefined ? symbol.grid_y : 0;
        $("slotsSymbolRarity").value = symbol.rarity || "common";
        $("slotsSymbolPayout").value = symbol.payout || 1;
        $("slotsSymbolPaylines").value = symbol.paylines || "";
        $("slotsSymbolDescription").value = symbol.description || "";
        updateSymbolPreview();
        renderSlotsSymbolList();
        
        // Highlight in picker
        const picker = $("slotsSymbolPicker");
        if (picker){
          picker.querySelectorAll(".symbol-picker-item").forEach(el => {
            const col = parseInt(el.dataset.col);
            const row = parseInt(el.dataset.row);
            if (col === symbol.grid_x && row === symbol.grid_y){
              el.classList.add("selected");
            }else{
              el.classList.remove("selected");
            }
          });
        }
      }

      $("slotMachine").addEventListener("change", async () => {
        await loadSlotMachine();
      });

      $("slotsSaveSpriteConfig").addEventListener("click", async () => {
        const machine_id = $("slotMachine").value.trim();
        if (!machine_id){
          setSlotsStatus("Pick a machine first.", "err");
          return;
        }
        
        slotsSpriteSheet = $("slotsSpriteSheet").value.trim();
        slotsSpriteCols = parseInt($("slotsSpriteCols").value) || 3;
        slotsSpriteRows = parseInt($("slotsSpriteRows").value) || 4;
        
        try{
          await jsonFetch("/api/slots/machines/" + encodeURIComponent(machine_id), {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              metadata: {
                sprite_sheet: slotsSpriteSheet,
                sprite_cols: slotsSpriteCols,
                sprite_rows: slotsSpriteRows
              }
            })
          }, true);
          
          renderSymbolPicker();
          setSlotsStatus("Sprite config saved.", "ok");
        }catch(err){
          setSlotsStatus(err.message, "err");
        }
      });

      $("slotsAddMachine").addEventListener("click", async () => {
        const machine_id = prompt("Enter slot machine ID:");
        if (!machine_id) return;
        const name = prompt("Enter machine name:");
        try{
          await jsonFetch("/api/slots/machines", {
            method:"POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({machine_id, name: name || machine_id, reel_count: 3})
          }, true);
          await loadSlotMachineList(machine_id);
          setSlotsStatus("Slot machine created.", "ok");
        }catch(err){
          setSlotsStatus(err.message, "err");
        }
      });

      $("slotsEditMachine").addEventListener("click", async () => {
        const machine_id = $("slotMachine").value.trim();
        if (!machine_id){
          setSlotsStatus("Pick a machine to edit.", "err");
          return;
        }
        const name = prompt("Enter new name:");
        if (!name) return;
        try{
          await jsonFetch("/api/slots/machines/" + encodeURIComponent(machine_id), {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({name})
          }, true);
          await loadSlotMachineList(machine_id);
          setSlotsStatus("Slot machine updated.", "ok");
        }catch(err){
          setSlotsStatus(err.message, "err");
        }
      });

      $("slotsDeleteMachine").addEventListener("click", async () => {
        const machine_id = $("slotMachine").value.trim();
        if (!machine_id){
          setSlotsStatus("Pick a machine to delete.", "err");
          return;
        }
        if (!confirm("Delete this slot machine?")){
          return;
        }
        try{
          await jsonFetch("/api/slots/machines/" + encodeURIComponent(machine_id), {method:"DELETE"}, true);
          setSlotsStatus("Slot machine deleted.", "ok");
          await loadSlotMachineList();
          $("slotsSymbolList").textContent = "No slot machine loaded.";
          slotsSelectedSymbolId = "";
        }catch(err){
          setSlotsStatus(err.message, "err");
        }
      });

      $("slotsNewSymbol").addEventListener("click", () => {
        slotsSelectedSymbolId = "";
        $("slotsSymbolId").value = "";
        $("slotsSymbolName").value = "";
        $("slotsSymbolGridX").value = "0";
        $("slotsSymbolGridY").value = "0";
        $("slotsSymbolRarity").value = "common";
        $("slotsSymbolPayout").value = "1";
        $("slotsSymbolPaylines").value = "";
        $("slotsSymbolDescription").value = "";
        updateSymbolPreview();
        renderSlotsSymbolList();
      });

      $("slotsSaveSymbol").addEventListener("click", async () => {
        const machine_id = $("slotMachine").value.trim();
        if (!machine_id){
          setSlotsStatus("Pick a machine first.", "err");
          return;
        }
        const symbol = {
          symbol_id: $("slotsSymbolId").value.trim() || Date.now().toString(),
          name: $("slotsSymbolName").value.trim(),
          grid_x: parseInt($("slotsSymbolGridX").value) || 0,
          grid_y: parseInt($("slotsSymbolGridY").value) || 0,
          rarity: $("slotsSymbolRarity").value || "common",
          payout: parseFloat($("slotsSymbolPayout").value) || 1,
          paylines: $("slotsSymbolPaylines").value.trim(),
          description: $("slotsSymbolDescription").value.trim()
        };
        try{
          const existingIndex = slotsSymbols.findIndex(s => s.symbol_id === symbol.symbol_id);
          if (existingIndex >= 0){
            slotsSymbols[existingIndex] = symbol;
          }else{
            slotsSymbols.push(symbol);
          }
          await jsonFetch("/api/slots/machines/" + encodeURIComponent(machine_id) + "/symbols", {
            method:"PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({symbols: slotsSymbols})
          }, true);
          slotsSelectedSymbolId = symbol.symbol_id;
          await loadSlotMachine();
          setSlotsStatus("Symbol saved.", "ok");
        }catch(err){
          setSlotsStatus(err.message, "err");
        }
      });

      applyTokenFromUrl();
      applyTempTokenFromUrl();
      loadSettings();
      if (apiKeyEl.value.trim()){
        document.getElementById("loginView").classList.add("hidden");
        document.getElementById("appView").classList.remove("hidden");
        initAuthenticatedSession();
      }
      renderCard(null, [], "BING");
