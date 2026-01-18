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
      let lastCalledCount = 0;
      let lastCalloutNumber = null;
      let activeGameId = "";
      let currentOwner = "";
      window.taArtists = [];
      let calendarData = [];
      let authUserScopes = new Set();
      let authUserIsElfmin = false;
      let authTokensCache = [];
      let dashboardStatsLoaded = false;
      let dashboardStatsLoading = false;
      let dashboardLogsKind = "boot";
      let dashboardLogsLoading = false;

      // Games list (admin:web)
      let gamesListVenues = [];
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
        dashboardStatsLoaded = true;
      }

      async function loadDashboardStats(force = false){
        overlayLog("loadDashboardStats", {force, loading: dashboardStatsLoading, loaded: dashboardStatsLoaded});
        if (dashboardStatsLoading) return;
        if (dashboardStatsLoaded && !force){
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
        return authUserScopes.has("*") || authUserScopes.has(scope);
      }

      function ensureScope(scope, msg){
        if (hasScope(scope)) return true;
        setStatus(msg || "Unauthorized.", "err");
        return false;
      }

      function ensureCardgamesScope(msg){
        if (hasScope("cardgames:admin") || hasScope("tarot:admin")) return true;
        setStatus(msg || "Cardgames access required.", "err");
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
          meta.textContent = `filename: ${currentMediaEdit.name || ""}\nartist_id: ${currentMediaEdit.artist_id || "none"}\norigin_type: ${currentMediaEdit.origin_type || ""}\norigin_label: ${currentMediaEdit.origin_label || ""}\nhidden: ${isHidden ? "yes" : "no"}`;
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
          const res = await apiFetch("/api/media/list", {method: "GET"}, true);
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
          const originEl = $("mediaFilterOriginType");
          const labelEl = $("mediaFilterLabel");
          const artistFilter = (artistEl ? artistEl.value : "").trim();
          const originFilter = (originEl ? originEl.value : "").trim();
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
              item.name
            ].filter(Boolean).join(" ").toLowerCase();
            return hay.includes(searchRaw);
          });
        }
        if (artistFilter){
          items = items.filter(item => (item.artist_id || "") === artistFilter);
        }
        if (originFilter){
          items = items.filter(item => (item.origin_type || "") === originFilter);
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
        }
          mediaVisibleItems = items;
          renderMediaGrid(items);
          updateMediaFilterSummary({searchRaw, artistFilter, originFilter, labelFilter});
          updateMediaLibraryStatus(items.length, mediaLibraryItems.length, {searchRaw, artistFilter, originFilter, labelFilter});
        }

        function countActiveMediaFilters({searchRaw, artistFilter, originFilter, labelFilter}){
          let count = 0;
          if (searchRaw) count += 1;
          if (artistFilter) count += 1;
          if (originFilter) count += 1;
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
        if (bingoBtn) bingoBtn.classList.toggle("hidden", !canBingo);
        if (contestsBtn) contestsBtn.classList.toggle("hidden", !canAdmin);
        if (mediaBtn) mediaBtn.classList.toggle("hidden", !canMedia);
        if (calendarBtn) calendarBtn.classList.toggle("hidden", !canAdmin);
        if (tarotLinksBtn) tarotLinksBtn.classList.toggle("hidden", !canTarot);
        if (cardgameBtn) cardgameBtn.classList.toggle("hidden", !canCardgames);
        if (tarotDecksBtn) tarotDecksBtn.classList.toggle("hidden", !canTarot);
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
          (!canBingo && (saved === "bingo" || saved === "media")) ||
          (!canAdmin && (saved === "contests")) ||
          (!canTarot && (saved === "tarotLinks" || saved === "tarotDecks")) ||
          (!canCardgames && (saved === "cardgameSessions"));
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
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
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
        overlayToggle.checked = storage.getItem("bt_overlay") === "1";
        if (overlayToggle.checked) document.body.classList.add("overlay");
        overlayToggleBtn.classList.toggle("active", overlayToggle.checked);
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
        const url = new URL(path, base).toString();
        const options = opts || {};
        options.headers = options.headers || {};
        if (withKey){
          const key = apiKeyEl ? apiKeyEl.value.trim() : "";
          if (key) options.headers["X-API-Key"] = key;
        }
        return fetch(url, options);
      }

      async function jsonFetch(path, opts, withKey = true){
        const res = await apiFetch(path, opts, withKey);
        if (res.status === 401){
          handleUnauthorized();
          throw new Error("Unauthorized");
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok){
          throw new Error(data.error || "Request failed");
        }
        return data;
      }

      function handleUnauthorized(){
        clearAuthSession("Unauthorized. Please log in again.", "err");
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
        document.getElementById("appView").classList.add("hidden");
        document.getElementById("loginView").classList.remove("hidden");
        if (loginStatusEl){
          loginStatusEl.textContent = message || "Logged out.";
          loginStatusEl.className = "status" + (kind ? " " + kind : "");
        }
        overlayToggle.checked = false;
        document.body.classList.remove("overlay");
        overlayToggleBtn.classList.remove("active");
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
        }catch(err){
          brandUserName.textContent = "";
          brandUserIcon.src = "";
          brandUserIcon.classList.add("hidden");
          brandUserFallback.classList.remove("hidden");
          brandUser.classList.add("hidden");
          authUserScopes = new Set();
          authUserIsElfmin = false;
          applyElfminVisibility();
          applyScopeVisibility();
          const createdBy = $("bCreatedBy");
          if (createdBy){
            createdBy.value = "";
          }
          updateBingoCreatePayload();
        }
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
        }
        let nextPanel = saved || (canBingo ? "bingo" : "dashboard");
        if (!allowedPanels.has(nextPanel)){
          nextPanel = "dashboard";
        }
        if (!getSeenDashboard()){
          showPanelOnce("dashboard");
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
          item.style.padding = "8px 6px";
          item.style.borderBottom = "1px solid rgba(255,255,255,0.06)";
          const title = g.title || "Bingo";
          const created = g.created_at ? new Date(g.created_at * 1000).toLocaleString() : "Unknown date";
          const status = g.active ? "active" : "ended";
          const deleteBtn = !g.active ? `<button data-delete="${g.game_id}" class="btn-ghost" style="max-width:90px">Delete</button>` : "";
          item.innerHTML = `\n            <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">\n              <div><strong>${title}</strong> - ${created} <span class="muted">(${status})</span></div>\n              ${deleteBtn}\n            </div>`;
          item.style.cursor = "pointer";
          item.onclick = () => {
            setGameId(g.game_id || "");
            refreshBingo();
            loadOwnersForGame();
            loadGamesMenu();
          };
          const del = item.querySelector("button[data-delete]");
          if (del){
            del.addEventListener("click", async (ev) => {
              ev.stopPropagation();
              if (!confirm("Delete this game? This cannot be undone.")){
                return;
              }
              try{
                await jsonFetch("/bingo/" + encodeURIComponent(g.game_id), {method:"DELETE"});
                setStatus("Game deleted.", "ok");
                await loadGamesMenu();
              }catch(err){
                setStatus(err.message, "err");
              }
            });
          }
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
        toggleClass("menuBingo", "active", which === "bingo");
        toggleClass("menuTarotLinks", "active", which === "tarotLinks");
        toggleClass("menuCardgameSessions", "active", which === "cardgameSessions");
        toggleClass("menuTarotDecks", "active", which === "tarotDecks");
        toggleClass("menuContests", "active", which === "contests");
        toggleClass("menuMedia", "active", which === "media");
        toggleClass("menuGamesList", "active", which === "gamesList");
        toggleClass("dashboardPanel", "hidden", which !== "dashboard");
        toggleClass("bingoPanel", "hidden", which !== "bingo");
        toggleClass("tarotLinksPanel", "hidden", which !== "tarotLinks");
        toggleClass("cardgameSessionsPanel", "hidden", which !== "cardgameSessions");
        toggleClass("tarotDecksPanel", "hidden", which !== "tarotDecks");
        toggleClass("contestPanel", "hidden", which !== "contests");
        toggleClass("mediaPanel", "hidden", which !== "media");
        toggleClass("gamesListPanel", "hidden", which !== "gamesList");
        if (which === "dashboard"){
          renderDashboardChangelog();
          loadDashboardStats();
          loadDashboardLogs(dashboardLogsKind);
        } else if (which === "media"){
          setMediaTab("upload");
          loadMediaLibrary();
          loadTarotArtists();
          updateMediaUploadDropDisplay(mediaUploadFile);
          updateMediaUploadState();
        }else if (which === "cardgameSessions"){
          loadCardgameDecks();
          loadCardgameSessions();
        }else if (which === "gamesList"){
          loadGamesListVenues();
          loadGamesList(true);
        }
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
      $("menuBingo").addEventListener("click", () => showPanel("bingo"));
      const menuGamesList = $("menuGamesList");
      if (menuGamesList){
        menuGamesList.addEventListener("click", () => {
          if (!ensureScope("admin:web", "Admin web access required.")) return;
          showPanel("gamesList");
        });
      }
      $("menuBingoRefresh").addEventListener("click", (ev) => {
        ev.stopPropagation();
        loadGamesMenu();
      });
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
        bingoCreateBgUrl = "";
        $("bCreateBgStatus").textContent = "No background selected.";
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
      bindMenuKey("menuContests");
      bindMenuKey("menuMedia");
      bindMenuKey("menuGamesList");
      $("bAnnounceToggle").addEventListener("change", async (ev) => {
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
      on("dashboardLogsBoot", "click", () => loadDashboardLogs("boot", true));
      on("dashboardLogsAuth", "click", () => loadDashboardLogs("auth", true));
      on("dashboardLogsUpload", "click", () => loadDashboardLogs("upload", true));
      on("dashboardLogsRefresh", "click", () => loadDashboardLogs(dashboardLogsKind || "boot", true));
      // Venue management (dashboard)
      let venueCache = [];
      let venueMediaCache = [];
      let venueDeckCache = [];

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
        const sel = $("venueBackground");
        if (!sel) return;
        const cur = sel.value || "";
        const opts = [`<option value="">(default)</option>`]
          .concat((venueMediaCache || []).map(it => {
            const label = it.title || it.name || it.filename || "Image";
            return `<option value="${escapeHtml(it.url || "")}">${escapeHtml(label)}</option>`;
          }));
        sel.innerHTML = opts.join("");
        if (cur) sel.value = cur;
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
          const res = await fetch("/api/media/list", {headers: {"X-API-Key": apiKeyEl.value.trim()}});
          if (res.status === 401){ handleUnauthorized(); throw new Error("Unauthorized"); }
          const data = await res.json();
          if (data.ok) venueMediaCache = data.items || [];
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
        const ids = (v?.metadata && v.metadata.admin_discord_ids) ? v.metadata.admin_discord_ids : "";
        if (Array.isArray(ids)){
          $("venueAdmins").value = ids.join(", ");
        }else if (typeof ids === "string"){
          $("venueAdmins").value = ids;
        }else{
          $("venueAdmins").value = "";
        }
      }

      function openVenueModal(mode){
        const m = mode || {};
        showVenueModal(true);
        setVenueStatus("Loading...", "");
        loadVenueDeps();
        loadVenuesForModal().then(() => {
          if (m.new){
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
        });
      }

      on("dashboardVenueList", "click", () => openVenueModal({new:false}));
      on("dashboardAddVenue", "click", () => openVenueModal({new:true}));
      on("venueClose", "click", () => showVenueModal(false));
      on("venueModal", "click", (ev) => { if (ev.target === $("venueModal")) showVenueModal(false); });
      on("venueNew", "click", () => { $("venueSelect").value = ""; setVenueFields(null); setVenueStatus("Creating new venue.", ""); });
      on("venueSelect", "change", () => {
        const id = parseInt($("venueSelect").value || "0", 10) || 0;
        const v = (venueCache || []).find(x => Number(x.id) === id) || null;
        setVenueFields(v);
      });
      on("venueSave", "click", async () => {
        if (!ensureScope("admin:web", "Admin web scope required.")) return;
        const name = $("venueName").value.trim();
        if (!name){ setVenueStatus("Name is required.", "err"); return; }
        const currency = $("venueCurrency").value.trim();
        const bg = $("venueBackground").value || "";
        const deck = $("venueDeck").value || "";
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
      on("dashboardChangelogToggle", "click", () => {
        const wrap = $("dashboardChangelogWrap");
        if (!wrap) return;
        wrap.classList.toggle("hidden");
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
          select.innerHTML = "";
          decks.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.deck_id;
            opt.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            select.appendChild(opt);
          });
          if (!decks.length){
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
        // Table layout: easiest to scan/scroll with large groups
        const table = document.createElement("table");
        table.className = "owners-table";
        table.innerHTML = `
          <thead>
            <tr>
              <th style="text-align:left">Player</th>
              <th style="width:90px">Cards</th>
              <th style="width:180px">Claim</th>
              <th style="width:170px;text-align:right">Actions</th>
            </tr>
          </thead>
          <tbody></tbody>
        `;
        const tbody = table.querySelector("tbody");

        owners.forEach(o => {
          const ownerName = o.owner_name || "";
          const claim = getOwnerClaimStatus(ownerName);
          const badgeClass = claim.cls ? `status-badge ${claim.cls}` : "status-badge";
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><strong>${escapeHtml(ownerName)}</strong></td>
            <td>${escapeHtml(o.cards)}</td>
            <td><span class="${badgeClass}">${escapeHtml(claim.label)}</span></td>
            <td>
              <div class="owner-actions">
                <button class="btn-ghost icon-action owner-copy-btn" title="Copy player link" aria-label="Copy player link">
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 1H6a2 2 0 0 0-2 2v12h2V3h10V1zm3 4H10a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H10V7h9v14z"/></svg>
                </button>
                <button class="btn-ghost mini-btn owner-view-btn">Cards</button>
              </div>
            </td>
          `;
          const viewBtn = tr.querySelector(".owner-view-btn");
          const copyBtn = tr.querySelector(".owner-copy-btn");
          if (viewBtn) viewBtn.setAttribute("data-owner", ownerName);
          if (copyBtn) copyBtn.setAttribute("data-owner", ownerName);
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
              const name = copyBtn.getAttribute("data-owner") || "";
              const gid = getGameId();
              if (!gid || !name){
                setBingoStatus("Select a game and player first.", "err");
                return;
              }
              try{
                const data = await jsonFetch("/bingo/" + encodeURIComponent(gid) + "/owner/" + encodeURIComponent(name) + "/token", {method:"GET"});
                const base = getBase();
                const url = new URL("/bingo/owner?token=" + encodeURIComponent(data.token || ""), base).toString();
                await navigator.clipboard.writeText(url);
                setBingoStatus("Copied player link.", "ok");
              }catch(err){
                setBingoStatus("Copy failed.", "err");
              }
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
              theme_color: $("bTheme").value || ""
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
        if (ev.key.toLowerCase() !== "n") return;
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
          $("bClaims").textContent = "No claims yet.";
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
              owner_user_id: $("bOwnerId").value.trim() || null,
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

      $("bViewOwner").addEventListener("click", () => {
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
        return new URL("/overlay/session/" + encodeURIComponent(code), base).toString();
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
        const links = [];
        if (code){
          links.push(`<a href="${getPlayerUrl(code)}" target="_blank" rel="noreferrer">Player</a>`);
          links.push(`<a href="${getPriestessUrl(code, token)}" target="_blank" rel="noreferrer">Priestess</a>`);
          links.push(`<a href="${getOverlayUrl(code)}" target="_blank" rel="noreferrer">Overlay</a>`);
        }
        $("tLink").innerHTML = links.length ? links.join(" | ") : "No join code entered.";
      }

      async function loadTarotSessionDecks(selectValue){
        if (!ensureScope("tarot:admin", "Tarot access required.")) return;
        try{
          const data = await jsonFetch("/api/tarot/decks", {method:"GET"}, true);
          const decks = data.decks || [];
          const modalSelect = $("sessionCreateDeck");
          modalSelect.innerHTML = "";
          decks.forEach(d => {
            const opt2 = document.createElement("option");
            opt2.value = d.deck_id;
            opt2.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            modalSelect.appendChild(opt2);
          });
          modalSelect.value = selectValue || (decks[0] ? decks[0].deck_id : "elf-classic");
        }catch(err){
          setStatus(err.message, "err");
        }
      }

      $("tCreateSession").addEventListener("click", () => {
        $("sessionCreateModal").classList.add("show");
      });
      $("sessionCreateClose").addEventListener("click", () => {
        $("sessionCreateModal").classList.remove("show");
      });
      $("sessionCreateSubmit").addEventListener("click", async () => {
        try{
          const deck = $("sessionCreateDeck").value.trim() || "elf-classic";
          const spread = $("sessionCreateSpread").value.trim() || "single";
          const data = await jsonFetch("/api/tarot/sessions", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({deck_id: deck, spread_id: spread})
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
          if (selectJoin){
            select.value = selectJoin;
          }
        }catch(err){
          setStatus(err.message, "err");
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

      $("tOpenOverlay").addEventListener("click", () => {
        const code = $("tJoinCode").value.trim();
        if (!code){
          setStatus("Enter a join code.", "err");
          return;
        }
        const url = getOverlayUrl(code);
        renderLinks(code, $("tPriestessToken").value.trim());
        window.open(url, "_blank");
      });

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
        window.open(url, "_blank");
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
          select.innerHTML = "";
          decks.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.deck_id;
            opt.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
            select.appendChild(opt);
          });
          const defaults = getCardgameDefaults();
          const pick = selectValue || (defaults && defaults.deck_id) || (decks[0] ? decks[0].deck_id : "");
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
            opt.textContent = `${s.join_code || "-"} | ${s.game_id || "-"} | ${s.deck_id || "-"} | ${s.status || "-"} | pot ${s.pot || 0} ${currency} | ${created}`;
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
        const el = $("cgBackgroundStatus");
        if (!el) return;
        const artistName = $("cgBackgroundUrl").dataset.artistName || "";
        if (!url){
          el.textContent = "No background selected.";
          return;
        }
        el.textContent = artistName ? `Background selected - ${artistName}.` : "Background selected.";
      }

        async function createCardgameSession(payload){
          if (!ensureCardgamesScope()) return;
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
                draft: true
              })
            }, true);
          const session = data.session || {};
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
          renderCardgameLinks(payload.game_id, session.join_code || "", session.priestess_token || "");
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
            const payload = {
              game_id: $("cgGameSelect").value,
              deck_id: $("cgDeckSelect").value,
              pot: parseInt(($("cgPot").value || "0").trim(), 10) || 0,
              currency: ($("cgCurrency").value || "").trim(),
              background_url: ($("cgBackgroundUrl").value || "").trim(),
              background_artist_id: $("cgBackgroundUrl").dataset.artistId || "",
              background_artist_name: $("cgBackgroundUrl").dataset.artistName || ""
            };
            createCardgameSession(payload);
          });
        ["cgPot", "cgCurrency", "cgDeckSelect", "cgGameSelect", "cgBackgroundUrl"].forEach(id => {
          const el = $(id);
          if (!el) return;
          el.addEventListener("change", () => persistCardgameDefaults());
          el.addEventListener("blur", () => persistCardgameDefaults());
        });
          $("cgCreateFromSelected").addEventListener("click", () => {
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
          if ($("cgDeckRefresh")){
            $("cgDeckRefresh").addEventListener("click", () => loadCardgameDecks());
          }
        $("cgSessionRefresh").addEventListener("click", () => loadCardgameSessions());
        $("cgSessionSelect").addEventListener("change", (ev) => {
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
          $("cgJoinCode").value = join;
          $("cgJoinCode").dataset.sessionId = opt ? (opt.dataset.sessionId || "") : "";
          $("cgJoinCode").dataset.gameId = gameId;
          $("cgJoinCode").dataset.deckId = deckId;
          $("cgPriestessToken").value = token;
          $("cgPot").value = pot;
          $("cgCurrency").value = currency || "gil";
          $("cgGameSelect").value = gameId;
          if (deckId){
            $("cgDeckSelect").value = deckId;
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
          renderCardgameLinks(gameId, join, token);
        });
        $("cgBackgroundUrl").addEventListener("input", (ev) => {
          ev.target.dataset.artistId = "";
          ev.target.dataset.artistName = "";
          setCardgameBackgroundStatus(ev.target.value.trim());
        });
        $("cgOpenPlayer").addEventListener("click", () => {
          const join = $("cgJoinCode").value.trim();
          const gameId = $("cgGameSelect").value;
          if (!join){
            setCardgameStatus("Enter a join code.", "err");
            return;
          }
          renderCardgameLinks(gameId, join, $("cgPriestessToken").value.trim());
          window.open(getCardgamePlayerUrl(gameId, join), "_blank");
        });
        $("cgOpenPriestess").addEventListener("click", () => {
          const join = $("cgJoinCode").value.trim();
          const gameId = $("cgGameSelect").value;
          if (!join){
            setCardgameStatus("Enter a join code.", "err");
            return;
          }
          const token = $("cgPriestessToken").value.trim();
          renderCardgameLinks(gameId, join, token);
          window.open(getCardgameHostUrl(gameId, join, token), "_blank");
        });
        $("cgFinishSession").addEventListener("click", () => finishCardgameSession());
        $("cgDeleteSession").addEventListener("click", async () => {
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
            renderCardgameLinks("", "", "");
            setCardgameStatus("Session deleted.", "ok");
            await loadCardgameSessions();
          }catch(err){
            setCardgameStatus(err.message, "err");
          }
        });
        $("cgUseSelectedMedia").addEventListener("click", () => {
          const pick = currentMediaEdit ? (currentMediaEdit.url || currentMediaEdit.fallback_url || "") : "";
          if (!pick){
            setCardgameStatus("Select a media item first.", "err");
            return;
          }
          $("cgBackgroundUrl").value = pick;
          setCardgameBackgroundStatus(pick);
        });
        $("cgOpenMedia").addEventListener("click", () => {
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
      const mediaFilterOriginType = $("mediaFilterOriginType");
      if (mediaFilterOriginType){
        mediaFilterOriginType.addEventListener("change", () => applyMediaFilters());
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
          const origin = $("mediaFilterOriginType");
          const label = $("mediaFilterLabel");
          if (artist) artist.value = "";
          if (origin) origin.value = "";
          if (label) label.value = "any";
          applyMediaFilters();
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
          const res = await fetch("/api/media/upload", {
            method: "POST",
            headers: {"X-API-Key": apiKeyEl.value.trim()},
            body: fd
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
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
              origin_label: originLabel
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
          const res = await fetch("/api/media/upload", {
            method: "POST",
            headers: {"X-API-Key": apiKeyEl.value.trim()},
            body: fd
          });
          const data = await res.json();
          if (!data.ok) throw new Error(data.error || "Failed");
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
          await jsonFetch("/api/tarot/decks/" + encodeURIComponent(deck) + "/cards", {
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
          taRenderNumberInfo("");
          taSetCardThemeWeights({});
          taSelectedCardId = body.card_id || "";
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
            opt.textContent = d.name ? `${d.name} (${d.deck_id})` : d.deck_id;
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

      applyTokenFromUrl();
      applyTempTokenFromUrl();
      loadSettings();
      if (apiKeyEl.value.trim()){
        document.getElementById("loginView").classList.add("hidden");
        document.getElementById("appView").classList.remove("hidden");
        initAuthenticatedSession();
      }
      renderCard(null, [], "BING");



