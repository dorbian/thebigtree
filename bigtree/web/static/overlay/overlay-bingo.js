// Bingo-specific overlay logic.

      let currentCard = null;
      let currentGame = null;

      let lastCalledCount = 0;
      let lastCalloutNumber = null;
      let activeGameId = "";
      let currentOwner = "";

      let bingoCreateBgUrl = "";

      function getGameId(){
        return ($("bGameId").dataset.gameId || "").trim();
      }

      function setGameId(id){
        const gid = (id || "").trim();
        $("bGameId").dataset.gameId = gid;
        $("bGameId").textContent = gid ? gid : "No game selected.";
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
        overlayLog("loadGamesMenu");
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
          .catch(err => {
            overlayLog("loadGamesMenu error", err);
          });
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

      bindElement("menuBingo", (el) => el.addEventListener("click", () => showPanel("bingo")));
      bindElement("menuBingoRefresh", (el) => {
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          loadGamesMenu();
        });
      });
      bindElement("bChannelRefresh", (el) => el.addEventListener("click", () => loadDiscordChannels()));
      bindElement("bChannelSelect", (el) => el.addEventListener("change", (ev) => {
        const pick = ev.target.value || "";
        if (pick){
          $("bChannel").value = pick;
        }
        updateBingoCreatePayload();
      }));
      bindElement("menuCreateGame", (el) => {
        el.addEventListener("click", (ev) => {
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
      });

      bindMenuKey("menuBingo");

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
        el.innerHTML = "";
        owners.forEach(o => {
          const item = document.createElement("div");
          item.className = "owner-row";
          const claim = getOwnerClaimStatus(o.owner_name || "");
          const badgeClass = claim.cls ? `status-badge ${claim.cls}` : "status-badge";
          item.innerHTML = `
            <div class="owner-row-main">
              <div class="owner-row-name">
                <strong>${o.owner_name}</strong>
                <span class="${badgeClass}">${claim.label}</span>
              </div>
              <button class="btn-ghost owner-view-btn" data-owner="${o.owner_name}">View Cards (${o.cards})</button>
            </div>
          `;
          const viewBtn = item.querySelector(".owner-view-btn");
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
          el.appendChild(item);
        });
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

      on("bCloseCreate", "click", () => {
        $("bCreateModal").classList.remove("show");
      });

      on("bOwnerFilterCalled", "click", () => {
        ownerFilter = ownerFilter === "called" ? "all" : "called";
        renderOwnerCards(
          ownerFilterData.owner,
          ownerFilterData.cards,
          ownerFilterData.called,
          ownerFilterData.header
        );
      });
      on("bOwnerFilterUncalled", "click", () => {
        ownerFilter = ownerFilter === "uncalled" ? "all" : "uncalled";
        renderOwnerCards(
          ownerFilterData.owner,
          ownerFilterData.cards,
          ownerFilterData.called,
          ownerFilterData.header
        );

      on("bOwnerClose", "click", () => {
        $("bOwnerModal").classList.remove("show");
      });
      on("bPurchaseClose", "click", () => {
        $("bPurchaseModal").classList.remove("show");
      });
      on("bPurchaseCopy", "click", () => {
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

      on("bCreateBgLibrary", "click", () => {
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

      on("bCreate", "click", async () => {
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

      on("bRefresh", "click", refreshBingo);
      on("bOwnersRefresh", "click", () => loadOwnersForGame());

      on("bAdvanceStage", "click", async () => {
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

      on("bStart", "click", async () => {
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


      on("bRoll", "click", async () => {
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

      on("bCloseGame", "click", async () => {
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

      on("bBuy", "click", async () => {
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
