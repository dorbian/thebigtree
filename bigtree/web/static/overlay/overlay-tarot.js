// Tarot + cardgames overlay logic.

      let taSelectedCardId = "";

      window.taArtists = [];

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

      let deckEditHadSuits = false;
      let gallerySettingsCache = null;
      let galleryHiddenDecks = [];

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
      on("deckCreateSuitJson", "input", () => {
        if ($("deckCreateSuitPreset").value !== "custom"){
          $("deckCreateSuitPreset").value = "custom";
        }
      });
      on("deckEditSuitPreset", "change", (ev) => {
        const value = ev.target.value || "custom";
        if (value === "custom"){
          return;
        }
        $("deckEditSuitJson").value = formatSuitPresetJson(value);
      });
      on("deckEditSuitJson", "input", () => {
        if ($("deckEditSuitPreset").value !== "custom"){
          $("deckEditSuitPreset").value = "custom";
        }
      });

      on("deckCreateSubmit", "click", async () => {
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

      on("taCardLibrary", "click", () => {
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

      on("tCreateSession", "click", () => {
        $("sessionCreateModal").classList.add("show");
      });
      on("sessionCreateClose", "click", () => {
        $("sessionCreateModal").classList.remove("show");
      });
      on("sessionCreateSubmit", "click", async () => {
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

      on("tSessionRefresh", "click", () => loadTarotSessions());
      on("tSessionSelect", "change", (ev) => {
        const join = ev.target.value || "";
        const token = ev.target.selectedOptions.length ? (ev.target.selectedOptions[0].dataset.token || "") : "";
        $("tJoinCode").value = join;
        $("tPriestessToken").value = token;
        renderLinks(join, token);
      });

      on("tOpenOverlay", "click", () => {
        const code = $("tJoinCode").value.trim();
        if (!code){
          setStatus("Enter a join code.", "err");
          return;
        }
        const url = getOverlayUrl(code);
        renderLinks(code, $("tPriestessToken").value.trim());
        window.open(url, "_blank");
      });

      on("tOpenPlayer", "click", () => {
        const code = $("tJoinCode").value.trim();
        if (!code){
          setStatus("Enter a join code.", "err");
          return;
        }
        const url = getPlayerUrl(code);
        renderLinks(code, $("tPriestessToken").value.trim());
        window.open(url, "_blank");
      });

      on("tOpenPriestess", "click", () => {
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

      on("tCloseSession", "click", async () => {
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
          on("cgCreateSession", "click", () => {
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
          if ($("cgDeckRefresh")){
            on("cgDeckRefresh", "click", () => loadCardgameDecks());
          }
        on("cgSessionRefresh", "click", () => loadCardgameSessions());
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
        on("cgBackgroundUrl", "input", (ev) => {
          ev.target.dataset.artistId = "";
          ev.target.dataset.artistName = "";
          setCardgameBackgroundStatus(ev.target.value.trim());
        });
        on("cgOpenPlayer", "click", () => {
          const join = $("cgJoinCode").value.trim();
          const gameId = $("cgGameSelect").value;
          if (!join){
            setCardgameStatus("Enter a join code.", "err");
            return;
          }
          renderCardgameLinks(gameId, join, $("cgPriestessToken").value.trim());
          window.open(getCardgamePlayerUrl(gameId, join), "_blank");
        });
        on("cgOpenPriestess", "click", () => {
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
            renderCardgameLinks("", "", "");
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

      on("artistIndexRefresh", "click", () => loadTarotArtists());
      on("artistIndexSelect", "change", (ev) => {
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
      on("artistIndexSave", "click", async () => {
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
      on("artistIndexDelete", "click", async () => {
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

      on("mediaLibraryOpen", "click", () => {
        librarySelectHandler = null;
        showLibraryModal(true);
        loadLibrary("media");
        loadTarotArtists();
      });

      on("mediaLibraryRefresh", "click", () => loadMediaLibrary());
      on("mediaTabUploadBtn", "click", () => setMediaTab("upload"));
      on("mediaTabEditBtn", "click", () => setMediaTab("edit"));
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
      on("mediaBulkDelete", "click", async () => {
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
      on("mediaBulkHide", "click", async () => {
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
      on("mediaBulkShow", "click", async () => {
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
      on("mediaBulkSetArtist", "click", async () => {
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
      on("mediaBulkSetOrigin", "click", async () => {
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
      on("mediaBulkApplyLabel", "click", async () => {
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
      on("mediaBulkClearLabel", "click", async () => {
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
      on("mediaUploadFile", "change", (ev) => {
        const file = ev.target.files[0] || null;
        mediaUploadFile = file;
        updateMediaUploadDropDisplay(file);
        updateMediaUploadState();
      });
      on("mediaUploadTitleInput", "input", () => updateMediaUploadState());

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

      on("mediaUploadUpload", "click", async () => {
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

      on("mediaEditClear", "click", () => {
        clearMediaSelection();
      });

      on("mediaEditSave", "click", async () => {
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

      on("mediaEditCopy", "click", async () => {
        if (!currentMediaEdit) return;
        try{
          await navigator.clipboard.writeText(currentMediaEdit.url || "");
          showToast("Copied URL.", "ok");
        }catch(err){
          showToast("Copy failed.", "err");
        }
      });

      on("mediaEditOpen", "click", () => {
        if (!currentMediaEdit) return;
        const url = currentMediaEdit.url || "";
        if (url) window.open(url, "_blank");
      });

      on("mediaEditDelete", "click", async () => {
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

      on("mediaEditHide", "click", async () => {
        if (!currentMediaEdit) return;
        try{
          await setMediaHidden(currentMediaEdit, !currentMediaEdit.hidden);
          showToast(currentMediaEdit.hidden ? "Hidden from gallery." : "Shown in gallery.", "ok");
          applyMediaFilters();
        }catch(err){
          showToast("Hide failed.", "err");
        }
      });

      on("uploadLibraryFile", "change", (ev) => {
        const file = ev.target.files[0] || null;
        libraryUploadFile = file;
        updateUploadDropDisplay(file);
        updateUploadState();
      });
      on("uploadLibraryTitleInput", "input", () => updateUploadState());

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

      on("uploadLibraryUpload", "click", async () => {
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

      on("taCardSuit", "input", () => {
        const suitValue = $("taCardSuit").value.trim();
        taRenderSuitInfo(suitValue);
        taRenderThemeWeights({}, suitValue);
        taApplySuitThemeDefaults(suitValue);
        taSetDirty(true);
      });
      on("taCardNumber", "input", (ev) => {
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
      on("taDeckList", "click", (ev) => {
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

      on("taDeck", "change", async () => {
        await loadTarotDeck();
      });

      on("taAddDeck", "click", () => {
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

      on("taEditDeck", "click", async () => {
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

      on("deckEditClose", "click", () => {
        $("deckEditModal").classList.remove("show");
      });
      on("deckEditModal", "click", (event) => {
        if (event.target === $("deckEditModal")){
          $("deckEditModal").classList.remove("show");
        }
      });
      on("deckEditBackPick", "click", () => {
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

      on("deckEditTheme", "change", (ev) => {
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

      on("deckEditSubmit", "click", async () => {
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

      on("taDeleteDeck", "click", async () => {
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

      on("taSaveCard", "click", async () => {
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
