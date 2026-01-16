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
      let calendarData = [];
      let authUserScopes = new Set();
      let authUserIsElfmin = false;
      let authTokensCache = [];
      let calendarSelected = {
        month: 1,
        image: "",
        title: "",
        artist_id: null,
        artist_name: "Forest"
      };
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

      function setStatusText(id, msg, kind){
        overlayLog("setStatusText", {id, msg, kind});
        const el = $(id);
        if (!el) return;
        el.textContent = msg;
        el.className = "status" + (kind ? " " + kind : "");
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

      let dashboardStatsLoaded = false;
      let dashboardStatsLoading = false;

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
        if (mediaBtn) mediaBtn.classList.toggle("hidden", !canBingo);
        if (calendarBtn) calendarBtn.classList.toggle("hidden", !canAdmin);
        if (tarotLinksBtn) tarotLinksBtn.classList.toggle("hidden", !canTarot);
        if (cardgameBtn) cardgameBtn.classList.toggle("hidden", !canCardgames);
        if (tarotDecksBtn) tarotDecksBtn.classList.toggle("hidden", !canTarot);
        if (artistsBtn) artistsBtn.classList.toggle("hidden", !canTarot);
        if (galleryBtn) galleryBtn.classList.toggle("hidden", !canTarot);
        const systemConfigBtn = $("menuSystemConfig");
        if (systemConfigBtn) systemConfigBtn.classList.toggle("hidden", !canAdmin);
        const dashboardAuthLink = $("dashboardXivAuthLink");
        if (dashboardAuthLink) dashboardAuthLink.classList.toggle("hidden", !canAdmin);

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


      function setStatus(msg, kind){
        overlayLog("setStatus", {msg, kind});
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
        overlayLog("loadAuthUser");
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
          let scopes = [];
          if (Array.isArray(rawScopes)){
            scopes = rawScopes.map(String);
          } else if (typeof rawScopes === "string"){
            scopes = rawScopes.split(/[ ,]+/).map(s => s.trim()).filter(Boolean);
          }
          authUserScopes = new Set(scopes);
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
        overlayLog("initAuthenticatedSession");
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



      function showPanel(which){
        overlayLog("showPanel", which);
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
        toggleClass("dashboardPanel", "hidden", which !== "dashboard");
        toggleClass("bingoPanel", "hidden", which !== "bingo");
        toggleClass("tarotLinksPanel", "hidden", which !== "tarotLinks");
        toggleClass("cardgameSessionsPanel", "hidden", which !== "cardgameSessions");
        toggleClass("tarotDecksPanel", "hidden", which !== "tarotDecks");
        toggleClass("contestPanel", "hidden", which !== "contests");
        toggleClass("mediaPanel", "hidden", which !== "media");
        if (which === "dashboard"){
          renderDashboardChangelog();
          loadDashboardStats();
        } else if (which === "media"){
          setMediaTab("upload");
          loadMediaLibrary();
          loadTarotArtists();
          updateMediaUploadDropDisplay(mediaUploadFile);
          updateMediaUploadState();
        }else if (which === "cardgameSessions"){
          loadCardgameDecks();
          loadCardgameSessions();
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

      function bindElement(id, callback){
        const el = $(id);
        if (!el){
          overlayLog("bindElement missing", id);
          return null;
        }
        overlayLog("bindElement", id);
        callback(el);
        return el;
      }

      function showPanelOnce(which){
        suppressPanelSave = true;
        showPanel(which);
        suppressPanelSave = false;
      }

      bindElement("menuDashboard", (el) => el.addEventListener("click", () => showPanel("dashboard")));
      bindElement("menuTarotLinks", (el) => {
        el.addEventListener("click", () => {
          if (!ensureScope("tarot:admin", "Tarot access required.")) return;
          showPanel("tarotLinks");
        });
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
      bindElement("menuTarotDecks", (el) => {
        el.addEventListener("click", () => {
          if (!ensureScope("tarot:admin", "Tarot access required.")) return;
          showPanel("tarotDecks");
        });
      });
      bindElement("menuContests", (el) => {
        el.addEventListener("click", () => {
          showPanel("contests");
          loadContestManagement();
          loadContestChannels();
          loadTarotClaimsDecks();
          loadTarotClaimsChannels();
        });
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
      bindMenuKey("menuTarotLinks");
      bindMenuKey("menuCardgameSessions");
      bindMenuKey("menuTarotDecks");
      bindMenuKey("menuContests");
      bindMenuKey("menuMedia");
      bindElement("menuMedia", (el) => {
        on("menuMedia", "click", () => {
          showPanel("media");
        });
      });
      bindElement("menuArtists", (el) => {
        on("menuArtists", "click", () => {
          if (!ensureScope("tarot:admin", "Tarot access required.")) return;
          $("artistModal").classList.add("show");
          loadTarotArtists();
        });
      });
      bindElement("menuCalendar", (el) => {
        el.addEventListener("click", () => {
          $("calendarModal").classList.add("show");
          loadCalendarAdmin();
        });
      });
      bindElement("menuGallery", (el) => {
        el.addEventListener("click", () => {
          if (!ensureScope("tarot:admin", "Tarot access required.")) return;
          $("galleryModal").classList.add("show");
          loadGalleryChannels();
          loadGallerySettings();
          // Gallery items are managed from Media Library.
          loadTarotArtists();
        });
      });
      bindElement("menuAuthRoles", (el) => {
        el.addEventListener("click", () => {
          if (!authUserIsElfmin){
            setStatus("Only elfministrators can manage auth roles.", "err");
            return;
          }
          $("authRolesModal").classList.add("show");
          loadAuthRoles();
        });
      });
      bindElement("menuAuthKeys", (el) => {
        el.addEventListener("click", () => {
          if (!authUserIsElfmin){
            setStatus("Only elfministrators can manage auth keys.", "err");
            return;
          }
          $("authTokensModal").classList.add("show");
          loadAuthTokens();
        });
      });
      bindElement("menuAuthTemp", (el) => {
        el.addEventListener("click", () => {
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
      });
      bindElement("menuSystemConfig", (el) => {
        el.addEventListener("click", () => {
          const modal = $("systemConfigModal");
          if (!modal){
            setSystemConfigStatus("System configuration UI not available.", "err");
            return;
          }
          modal.classList.add("show");
          loadSystemConfig();
        });
      });
      bindElement("systemConfigClose", (el) => {
        el.addEventListener("click", () => {
          const modal = $("systemConfigModal");
          if (modal){
            modal.classList.remove("show");
          }
        });
      });
      bindElement("systemConfigModal", (el) => {
        el.addEventListener("click", (event) => {
          if (event.target === el){
            el.classList.remove("show");
          }
        });
      });
      bindElement("systemXivSave", (el) => {
        el.addEventListener("click", () => saveSystemConfig("xivauth"));
      });
      bindElement("systemOpenAISave", (el) => {
        el.addEventListener("click", () => saveSystemConfig("openai"));
      });
      bindElement("dashboardStatsRefresh", (el) => {
        el.addEventListener("click", () => loadDashboardStats(true));
      });
      bindElement("dashboardChangelogToggle", (el) => {
        el.addEventListener("click", () => {
          const wrap = $("dashboardChangelogWrap");
          if (!wrap) return;
          wrap.classList.toggle("hidden");
        });
      });
      bindElement("contestRefresh", (el) => {
        el.addEventListener("click", () => loadContestManagement());
      });
      bindElement("contestChannelRefresh", (el) => {
        el.addEventListener("click", () => loadContestChannels());
      });
      bindElement("contestCreate", (el) => {
        el.addEventListener("click", () => createContest());
      });
      bindElement("contestEmojiSelect", (el) => {
        el.addEventListener("change", () => updateContestChannelPreview());
      });
      bindElement("contestChannelName", (el) => {
        el.addEventListener("input", () => updateContestChannelPreview());
      });
      bindElement("contestCreateChannelOpen", (el) => {
        el.addEventListener("click", () => {
          $("contestChannelModal").classList.add("show");
          loadContestChannels();
        });
      });
      bindElement("contestChannelClose", (el) => {
        el.addEventListener("click", () => {
          $("contestChannelModal").classList.remove("show");
        });
      });
      bindElement("contestChannelModal", (el) => {
        el.addEventListener("click", (event) => {
          if (event.target === el){
            $("contestChannelModal").classList.remove("show");
          }
        });
      });
      bindElement("contestPanel", (el) => {
        el.addEventListener("click", (event) => {
          const btn = event.target.closest(".contest-init");
          if (!btn) return;
          const channelId = btn.dataset.channel || "";
          if (channelId){
            $("contestChannel").value = channelId;
            setContestCreateStatus("Channel selected. Fill out details and create.", "ok");
          }
        });
      });
      bindElement("tarotClaimsRefresh", (el) => {
        el.addEventListener("click", () => {
          loadTarotClaimsDecks();
          loadTarotClaimsChannels();
        });
      });
      bindElement("tarotClaimsPost", (el) => {
        el.addEventListener("click", () => postTarotClaims());
      });
      bindElement("contestChannelCreate", (el) => {
        el.addEventListener("click", async () => {
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
      });


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


      // owner list loads automatically when selecting a game

      on("deckCreateClose", "click", () => {
        $("deckCreateModal").classList.remove("show");
      });
      on("mediaClose", "click", () => {
        $("mediaModal").classList.remove("show");
      });
      on("artistClose", "click", () => {
        $("artistModal").classList.remove("show");
      });
      on("calendarClose", "click", () => {
        $("calendarModal").classList.remove("show");
      });
      on("galleryClose", "click", () => {
        $("galleryModal").classList.remove("show");
      });
      on("galleryModal", "click", (event) => {
        if (event.target === $("galleryModal")){
          $("galleryModal").classList.remove("show");
        }
      });
      on("galleryImportOpen", "click", () => {
        $("galleryImportModal").classList.add("show");
        setGalleryImportStatus("Pick a channel to import.", "");
        loadGalleryChannels();
      });
      on("galleryImportClose", "click", () => {
        $("galleryImportModal").classList.remove("show");
      });
      on("galleryImportModal", "click", (event) => {
        if (event.target === $("galleryImportModal")){
          $("galleryImportModal").classList.remove("show");
        }
      });
      on("galleryImportRefresh", "click", () => loadGalleryChannels());
      on("galleryImportRun", "click", async () => {
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
      on("galleryChannelRefresh", "click", () => loadGalleryChannels());
      on("galleryChannelSave", "click", async () => {
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
      on("galleryChannelCreate", "click", async () => {
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
      on("calendarRefresh", "click", () => loadCalendarAdmin());
      on("calendarMonth", "change", (ev) => {
        const month = parseInt(ev.target.value || "1", 10);
        const entry = calendarData.find(e => e.month === month) || calendarData[0];
        if (entry){
          applyCalendarSelection(entry);
        }
      });
      on("calendarPick", "click", () => {
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
      on("calendarSave", "click", async () => {
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
      on("calendarClear", "click", async () => {
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
      on("authRolesClose", "click", () => {
        $("authRolesModal").classList.remove("show");
      });
      on("authRolesRefresh", "click", () => loadAuthRoles());
      on("authTokensClose", "click", () => {
        $("authTokensModal").classList.remove("show");
      });
      on("authTokensRefresh", "click", () => loadAuthTokens());
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
      on("authRolesList", "change", (ev) => {
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
      on("authRolesSave", "click", async () => {
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
      overlayToggle.addEventListener("change", () => {
        document.body.classList.toggle("overlay", overlayToggle.checked);
        overlayToggleBtn.classList.toggle("active", overlayToggle.checked);
        saveSettings();
      });
      overlayToggleBtn.addEventListener("click", () => {
        overlayToggle.checked = !overlayToggle.checked;
        overlayToggle.dispatchEvent(new Event("change"));
      });
      on("overlayExit", "click", () => {
        overlayToggle.checked = false;
        document.body.classList.remove("overlay");
        saveSettings();
      });
      on("uploadLibraryClose", "click", () => showLibraryModal(false));
      on("uploadLibraryRefresh", "click", () => loadLibrary(libraryKind));











