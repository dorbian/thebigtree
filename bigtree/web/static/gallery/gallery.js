const grid = document.getElementById("feed");
  const headerSubtitle = document.getElementById("headerSubtitle");
  const headerContext = document.getElementById("headerContext");
  const artistModal = document.getElementById("artistModal");
  const artistName = document.getElementById("artistName");
  const artistLinks = document.getElementById("artistLinks");
  const artistFilterBtn = document.getElementById("artistFilterBtn");
  const filterRow = document.getElementById("filterRow");
  const filterName = document.getElementById("filterName");
  const filterClear = document.getElementById("filterClear");
  const imageModal = document.getElementById("imageModal");
  const imageModalImg = document.getElementById("imageModalImg");
  const imageInfo = document.getElementById("imageInfo");
  const detailTitle = document.getElementById("detailTitle");
  const detailArtist = document.getElementById("detailArtist");
  const detailOrigin = document.getElementById("detailOrigin");
  const detailActions = document.getElementById("detailActions");
  const detailTags = document.getElementById("detailTags");
  const postGameBanner = document.getElementById("postGameBanner");
  const postGameTitle = document.getElementById("postGameTitle");
  const postGameDismiss = document.getElementById("postGameDismiss");
  const postGameBody = document.getElementById("postGameBody");
  const joinGameBtn = document.getElementById("joinGameBtn");
  const walletUser = document.getElementById("walletUser");
  const walletLogin = document.getElementById("walletLogin");
  const returnPrompt = document.getElementById("returnPrompt");
  const returnClose = document.getElementById("returnClose");
  const returnTitle = document.getElementById("returnTitle");
  const returnBody = document.getElementById("returnBody");
  const artistFlavor = document.getElementById("artistFlavor");
  const toast = document.getElementById("toast");
  const suggestions = document.getElementById("suggestions");
  const suggestionsTitle = document.getElementById("suggestionsTitle");
  const suggestionsGrid = document.getElementById("suggestionsGrid");
  const imagePrev = document.getElementById("imagePrev");
  const imageNext = document.getElementById("imageNext");
  const detailLinks = document.getElementById("detailLinks");
  const detailWatermark = document.getElementById("detailWatermark");
  let imageInfoTimer = null;
  let galleryItems = [];
  let galleryRenderItems = [];
  let virtualCardHeight = 0;
  let virtualCols = 0;
  let virtualFrame = null;
  let virtualListening = false;
  const CARD_MIN_WIDTH = 220;
  const CARD_HEIGHT = 380;
  const VIRTUAL_BUFFER_ROWS = 2;
  const USE_VIRTUAL = false;
  const PAGE_SIZE = 20;
  let gallerySeed = null;
  let galleryTotal = 0;
  let galleryLoading = false;
  let gallerySettings = {};
  let inspirationLines = [];
  // Default: inject an inspiration card once every ~7 images.
  let inspirationEvery = 7;
  const GALLERY_CACHE_KEY = "forest_gallery_cache_v1";
  let activeArtistFilter = null;
  const REACTIONS = [
    {id:"appreciation", label:"Appreciate"},
    {id:"gratitude", label:"Gratitude"},
    {id:"inspired", label:"Remember"},
    {id:"craft", label:"Craft"}
  ];
  const CONTEXT_LABELS = {
    contest: {label: "Contest"},
    artifact: {label: "Artifact"},
    event: {label: "Event"},
    tarot: {label: "Tarot"}
  };
  // Inspirational copy is managed from the database (gallery system config).
  // If none is provided, we still inject a small set of default Forest lines so
  // the feed keeps its intended rhythm (~7 images, then text, repeat).
  const DEFAULT_FOREST_LINES = [
    "The Forest listens in quiet gratitude.",
    "Between branches, a small kindness takes root.",
    "A memory drifts past like pollen in sunlight.",
    "Rest your gaze here a moment — the path continues soon.",
    "The trees remember every offering.",
    "Softly now: breathe, and let wonder return.",
    "Some treasures are meant to be found slowly."
  ];
  const DIVIDER_LINES = [];
  const SESSION_BANNER_KEY = "forest_gallery_banner_dismissed";
  const SESSION_RETURN_KEY = "forest_gallery_return_prompt";
  let currentDetailIndex = -1;
  let scrollLinkedInit = false;
  const WALLET_TOKEN_KEY = "bigtree_user_token";

  const LINK_ORDER = ["instagram", "bluesky", "x", "artstation", "linktree", "website"];
  const LINK_LABELS = {
    instagram: "Instagram",
    bluesky: "Bluesky",
    x: "X",
    artstation: "ArtStation",
    linktree: "Linktree",
    website: "Website"
  };
  const LINK_ICONS = {
    instagram: "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M7 3h10a4 4 0 0 1 4 4v10a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4zm0 2a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H7zm5 3.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7zm0 2a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zm4.5-3a1 1 0 1 1 0 2 1 1 0 0 1 0-2z\"/></svg>",
    bluesky: "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 4c-2.4 0-4.7 2.1-6.1 3.7C4.7 9 4 10.7 4 12c0 2.9 2.5 4.5 5 4.5 1.2 0 2.3-.4 3-1.1.7.7 1.8 1.1 3 1.1 2.5 0 5-1.6 5-4.5 0-1.3-.7-3-1.9-4.3C16.7 6.1 14.4 4 12 4zm-3.8 8.6c-1.1 0-2.2-.6-2.2-1.8 0-.7.5-1.8 1.3-2.7 1.1-1.2 2.6-2.4 3.9-2.4.2 0 .4 0 .6.1-.9.7-1.6 1.7-2.1 2.6-.6 1-.9 1.9-.9 2.7 0 .5.1 1 .3 1.5-.2 0-.5 0-.9 0zm7.6 0c-.3 0-.7 0-.9 0 .2-.5.3-1 .3-1.5 0-.8-.3-1.7-.9-2.7-.5-.9-1.2-1.9-2.1-2.6.2-.1.4-.1.6-.1 1.3 0 2.8 1.2 3.9 2.4.8.9 1.3 2 1.3 2.7 0 1.2-1.1 1.8-2.2 1.8z\"/></svg>",
    x: "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M4 4h4.7l4.1 5.4L17.3 4H20l-6 7.7L20.3 20h-4.7l-4.5-5.9L6.8 20H4l6.5-8.4L4 4z\"/></svg>",
    artstation: "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 4l6.9 12H5.1L12 4zm-4.5 14H20l-1.7 2H9.1L7.5 18z\"/></svg>",
    linktree: "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 3l3 3-2 2h3v3h-3l2 2-3 3-3-3 2-2H6V8h3L9 6l3-3zm-1 11h2v7h-2v-7z\"/></svg>",
    website: "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm6.9 6H15a15.5 15.5 0 0 0-1.5-4.1A8.1 8.1 0 0 1 18.9 8zM12 4.1A13.7 13.7 0 0 1 13.6 8H10.4A13.7 13.7 0 0 1 12 4.1zM8.5 3.9A15.5 15.5 0 0 0 7 8H5.1a8.1 8.1 0 0 1 3.4-4.1zM4.1 10H7a16.7 16.7 0 0 0 0 4H4.1a8.1 8.1 0 0 1 0-4zm1 6H7a15.5 15.5 0 0 0 1.5 4.1A8.1 8.1 0 0 1 5.1 16zM12 19.9A13.7 13.7 0 0 1 10.4 16h3.2A13.7 13.7 0 0 1 12 19.9zm3.5.2A15.5 15.5 0 0 0 17 16h1.9a8.1 8.1 0 0 1-3.4 4.1zM16.9 14a16.7 16.7 0 0 0 0-4h2.9a8.1 8.1 0 0 1 0 4h-2.9z\"/></svg>"
  };
  const DEFAULT_LINK_ICON = "<svg viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path d=\"M10 3h10v10h-2V7.4l-9.3 9.3-1.4-1.4L16.6 6H10V3zM5 5h4v2H7v10h10v-2h2v4H5V5z\"/></svg>";

  function getReactionLabel(reactionId){
    const match = REACTIONS.find((reaction) => reaction.id === reactionId);
    return match ? match.label : reactionId;
  }

  function showToast(message){
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    toast.setAttribute("aria-hidden", "false");
    setTimeout(() => {
      toast.classList.remove("show");
      toast.setAttribute("aria-hidden", "true");
    }, 2200);
  }

  async function loadWalletUser(){
    if (!walletUser || !walletLogin) return;
    const token = window.localStorage.getItem(WALLET_TOKEN_KEY);
    if (!token){
      walletUser.style.display = "none";
      walletLogin.style.display = "block";
      return;
    }
    try{
      const res = await fetch("/user-area/me", {headers:{Authorization:`Bearer ${token}`}});
      const data = await res.json();
      if (!res.ok || !data.ok){
        throw new Error("invalid");
      }
      walletUser.textContent = data.user?.xiv_username || "Wallet";
      walletUser.style.display = "flex";
      walletLogin.style.display = "none";
    }catch(err){
      walletUser.style.display = "none";
      walletLogin.style.display = "flex";
    }
  }

  if (joinGameBtn){
    joinGameBtn.addEventListener("click", () => {
      const code = (prompt("Enter join code") || "").trim();
      if (!code) return;
      const target = `/cardgames/join?code=${encodeURIComponent(code)}`;
      window.location.assign(target);
    });
  }

  function openArtistModal(name, links){
    artistName.textContent = name || "Forest";
    if (artistFlavor){
      artistFlavor.textContent = "A frequent voice within the Forest.";
    }
    if (artistFilterBtn){
      artistFilterBtn.dataset.artist = name || "Forest";
    }
    const rawLinks = links || {};
    const ordered = LINK_ORDER.filter(key => rawLinks[key]);
    const extras = Object.keys(rawLinks)
      .filter(key => !LINK_ORDER.includes(key))
      .filter(key => rawLinks[key]);
    const allKeys = ordered.concat(extras);
    const linkItems = allKeys.map((key) => {
      const url = rawLinks[key];
      if (!url) return "";
      const label = LINK_LABELS[key] || key;
      const icon = LINK_ICONS[key] || DEFAULT_LINK_ICON;
      return `<a class="modal-link" href="${url}" target="_blank" rel="noreferrer">${icon}<span>${label}</span></a>`;
    }).filter(Boolean);
    artistLinks.innerHTML = linkItems.length
      ? linkItems.join("")
      : "<span class='muted'>No external links shared.</span>";
    artistModal.classList.add("show");
    artistModal.setAttribute("aria-hidden", "false");
  }

  function closeArtistModal(){
    artistModal.classList.remove("show");
    artistModal.setAttribute("aria-hidden", "true");
  }

  function showImageInfo(){
    imageModal.classList.add("show-info");
    if (imageInfoTimer) clearTimeout(imageInfoTimer);
    imageInfoTimer = setTimeout(() => {
      imageModal.classList.remove("show-info");
    }, 2000);
  }

  function renderDetailPanel(data){
    if (!data) return;
    document.body.classList.add("details-ready");
    if (detailTitle) detailTitle.textContent = data.title || "";
    if (detailArtist) detailArtist.textContent = data.artist ? `Offered by ${data.artist}` : "";
    if (detailLinks){
      const links = data.artist_links || {};
      const ordered = LINK_ORDER.filter(key => links[key]);
      const extras = Object.keys(links)
        .filter(key => !LINK_ORDER.includes(key))
        .filter(key => links[key]);
      const keys = ordered.concat(extras);
      const linkItems = keys.map((key) => {
        const url = links[key];
        if (!url) return "";
        const label = LINK_LABELS[key] || key;
        const icon = LINK_ICONS[key] || DEFAULT_LINK_ICON;
        return `<a href="${url}" target="_blank" rel="noreferrer">${icon}<span>${label}</span></a>`;
      }).filter(Boolean);
      // Always show direct media links if available.
      if (data.url){
        linkItems.unshift(`<a href="${data.url}" target="_blank" rel="noreferrer">${DEFAULT_LINK_ICON}<span>Open image</span></a>`);
      }
      if (!linkItems.length){
        detailLinks.innerHTML = "<span class='muted'>No external links shared.</span>";
      }else{
        detailLinks.innerHTML = linkItems.join("");
      }
    }
    if (detailOrigin) detailOrigin.textContent = data.origin || "";
    if (detailActions){
      detailActions.innerHTML = (data.actions || []).map((action) => {
        return `<button class="reaction" data-reaction="${action.id}" data-item="${encodeURIComponent(data.item_id)}">${action.label} <span class="reaction-count">${action.count}</span></button>`;
      }).join("");
    }
    if (detailTags){
      detailTags.innerHTML = (data.tags || []).map(tag => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("");
    }
  }

  function openImageModal(data){
    imageModalImg.onerror = null;
    imageModalImg.src = data.url;
    imageModalImg.alt = data.title || "";
    if (data.fallback_url){
      imageModalImg.dataset.fallback = data.fallback_url;
      imageModalImg.onerror = () => {
        if (imageModalImg.dataset.fallback && imageModalImg.src !== imageModalImg.dataset.fallback){
          imageModalImg.src = imageModalImg.dataset.fallback;
        }
      };
    }else{
      imageModalImg.dataset.fallback = "";
    }
    imageInfo.textContent = data.info || "";
    renderDetailPanel(data);
    if (detailWatermark){
      detailWatermark.textContent = data.artist || "";
    }
    if (data.item_id){
      currentDetailIndex = galleryItems.findIndex((item) => getItemKey(item) === data.item_id);
    }
    updateDetailNav();
    imageModal.classList.add("show");
    imageModal.setAttribute("aria-hidden", "false");
    showImageInfo();
  }

  function closeImageModal(){
    imageModal.classList.remove("show");
    imageModal.setAttribute("aria-hidden", "true");
    imageModalImg.src = "";
    imageInfo.textContent = "";
    if (detailWatermark) detailWatermark.textContent = "";
    updateDetailNav();
  }

  function preloadThumbnails(items){
    if (!items || !items.length) return;
    const head = document.head || document.getElementsByTagName("head")[0];
    if (!head) return;
    const max = Math.min(12, items.length);
    for (let i = 0; i < max; i += 1){
      const item = items[i] || {};
      const href = item.thumb_url;
      if (!href) continue;
      const link = document.createElement("link");
      link.rel = "preload";
      link.as = "image";
      link.href = href;
      head.appendChild(link);
    }
  }

  function readCachedGallery(){
    try{
      const raw = localStorage.getItem(GALLERY_CACHE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.items)) return null;
      return data;
    }catch(err){
      return null;
    }
  }

  function writeCachedGallery(payload){
    try{
      localStorage.setItem(GALLERY_CACHE_KEY, JSON.stringify(payload));
    }catch(err){}
  }
  function normalizeInspirationLines(raw){
    if (Array.isArray(raw)){
      return raw.map(line => String(line || "").trim()).filter(Boolean);
    }
    if (typeof raw === "string"){
      return raw
        .split("\n")
        .map(line => line.trim())
        .filter(Boolean);
    }
    return [];
  }

  // Artist can be returned as an object (preferred) or a string (legacy / manual entries).
  // Normalize so the UI always shows a name + links without crashing.
  function normalizeArtist(item){
    const raw = item ? item.artist : null;
    if (!raw) return {name: "Forest", links: {}};
    if (typeof raw === "string"){
      const name = raw.trim() || "Forest";
      return {name, links: {}};
    }
    if (typeof raw === "object"){
      const name = String(raw.name || raw.artist || raw.display_name || "Forest").trim() || "Forest";
      const links = (raw.links && typeof raw.links === "object") ? raw.links : {};
      return {name, links};
    }
    return {name: "Forest", links: {}};
  }

  function applyGallerySettings(settings){
    const cfg = settings || {};
    gallerySettings = cfg;
    // Layout is feed-based; columns are ignored here.
    // Backwards compat: earlier configs used singular keys.
    inspirationLines = normalizeInspirationLines(
      cfg.inspiration_texts || cfg.inspiration_text || cfg.inspirational_text || cfg.flair_text
    );
    const every = parseInt(cfg.inspiration_every || 0, 10);
    inspirationEvery = every > 0 ? every : 7;

    // All inspirational / flavor copy can be overridden from the database.
    if (headerSubtitle && cfg.header_subtitle){
      headerSubtitle.textContent = String(cfg.header_subtitle);
    }
    if (headerContext && cfg.header_context){
      headerContext.textContent = String(cfg.header_context);
    }
    if (postGameTitle && cfg.post_game_title){
      postGameTitle.textContent = String(cfg.post_game_title);
    }
    if (postGameBody && cfg.post_game_body){
      postGameBody.textContent = String(cfg.post_game_body);
    }
    if (returnTitle && cfg.return_title){
      returnTitle.textContent = String(cfg.return_title);
    }
    if (returnBody && cfg.return_body){
      returnBody.textContent = String(cfg.return_body);
    }
    if (suggestionsTitle && cfg.suggestions_title){
      suggestionsTitle.textContent = String(cfg.suggestions_title);
    }
  }

  async function loadBatch(offset){
    if (galleryLoading) return;
    galleryLoading = true;
    let scheduleNextOffset = null;
    try{
      const seedParam = gallerySeed !== null ? `&seed=${gallerySeed}` : "";
      const res = await fetch(`/api/gallery/images?limit=${PAGE_SIZE}&offset=${offset}${seedParam}`);
      const data = await res.json();
      if (!data.ok){
        if (!galleryItems.length){
          grid.innerHTML = "<div class='muted'>Gallery unavailable.</div>";
        }
        return;
      }
      if (data.settings){
        applyGallerySettings(data.settings);
      }
      if (gallerySeed === null && Number.isFinite(data.seed)){
        gallerySeed = data.seed;
      }
      galleryTotal = Number(data.total) || 0;
      const batch = data.items || [];
      if (offset === 0){
        galleryItems = batch;
        preloadThumbnails(galleryItems);
        writeCachedGallery({
          seed: gallerySeed,
          total: galleryTotal,
          items: galleryItems
        });
        renderGrid();
        // Always populate the right-hand detail panel immediately.
        // Use rAF so the DOM is guaranteed to exist before we query it.
        if (galleryItems.length) {
          requestAnimationFrame(() => setActiveDetailIndex(0));
        }
        if (!scrollLinkedInit){
          scrollLinkedInit = true;
          initScrollLinkedDetails();
        }
      }else{
        galleryItems = galleryItems.concat(batch);
        if (USE_VIRTUAL){
          renderGrid();
        }else{
          appendGrid(batch, offset);
        }
      }
      if (galleryItems.length < galleryTotal){
        scheduleNextOffset = galleryItems.length;
      }
    }catch(err){
      if (!galleryItems.length){
        grid.innerHTML = "<div class='muted'>Gallery unavailable.</div>";
      }
    }finally{
      galleryLoading = false;
      // Continue paging after the lock is released (reliable across browsers).
      if (scheduleNextOffset !== null){
        setTimeout(() => loadBatch(scheduleNextOffset), 0);
      }
    }
  }

  async function load(){
    // Always fetch fresh data from the server.
    // The server has its own cache invalidation when items are hidden/unhidden;
    // using localStorage here can temporarily surface stale (now-hidden) cards.
    grid.innerHTML = Array.from({length: 4}).map(() => `<div class="skeleton-card"></div>`).join("");
    galleryItems = [];
    gallerySeed = null;
    galleryTotal = 0;
    activeArtistFilter = null;
    if (filterRow) filterRow.style.display = "none";
    await loadBatch(0);
  }

  // Some pages/templates may not include the artist modal. Guard all bindings.
  const artistCloseBtn = document.getElementById("artistClose");
  if (artistCloseBtn) artistCloseBtn.addEventListener("click", closeArtistModal);

  if (artistModal) {
    artistModal.addEventListener("click", (event) => {
      if (event.target === artistModal) closeArtistModal();
    });
  }
  if (artistFilterBtn){
    artistFilterBtn.addEventListener("click", () => {
      const name = artistFilterBtn.dataset.artist || "";
      closeArtistModal();
      if (name){
        applyArtistFilter(name);
      }
    });
  }
  if (filterClear){
    filterClear.addEventListener("click", () => applyArtistFilter(null));
  }
  // Image modal may also be absent on some templates; guard bindings.
  const imageCloseBtn = document.getElementById("imageClose");
  if (imageCloseBtn) imageCloseBtn.addEventListener("click", closeImageModal);
  if (imageModal) {
    imageModal.addEventListener("click", (event) => {
      if (event.target === imageModal) closeImageModal();
    });
  }
  if (imageModal) {
    imageModal.addEventListener("mousemove", showImageInfo);
  }
  // Mobile: tapping the image opens the zoom modal.
  if (grid) grid.addEventListener("touchstart", (event) => {
    const target = event.target;
    const post = target.closest ? target.closest(".post") : null;
    if (!post) return;
    const payload = post.getAttribute("data-full");
    if (!payload) return;
    try{
      const parsed = JSON.parse(decodeURIComponent(payload));
      openImageModal(parsed);
    }catch (err){}
  }, {passive: true});
  if (postGameDismiss){
    postGameDismiss.addEventListener("click", () => {
      sessionStorage.setItem(SESSION_BANNER_KEY, "1");
      postGameBanner.classList.remove("show");
      postGameBanner.setAttribute("aria-hidden", "true");
    });
  }
  if (returnClose){
    returnClose.addEventListener("click", () => {
      sessionStorage.setItem(SESSION_RETURN_KEY, "1");
      returnPrompt.classList.remove("show");
      returnPrompt.setAttribute("aria-hidden", "true");
    });
  }
  if (detailActions){
    detailActions.addEventListener("click", (event) => {
      const target = event.target;
      const button = target.closest ? target.closest(".reaction") : null;
      if (!button) return;
      event.preventDefault();
      const reactionId = button.getAttribute("data-reaction");
      const itemKey = button.getAttribute("data-item");
      if (!reactionId || !itemKey) return;
      const decodedKey = decodeURIComponent(itemKey);
      postReaction(decodedKey, reactionId);
    });
  }
  if (imagePrev){
    imagePrev.addEventListener("click", () => navigateDetail(-1));
  }
  if (imageNext){
    imageNext.addEventListener("click", () => navigateDetail(1));
  }
  if (grid) grid.addEventListener("click", (event) => {
    const target = event.target;
    // Clicking a post opens the zoom modal.
    const post = target.closest ? target.closest(".post") : null;
    if (post && post.getAttribute("data-full")){
      event.preventDefault();
      // Also sync the right-hand detail panel when a post is clicked (even if the modal is used).
      const idx = parseInt(post.getAttribute("data-index") || "-1", 10);
      if (Number.isFinite(idx) && idx >= 0){
        setActiveDetailIndex(idx);
      }
      const payload = post.getAttribute("data-full");
      if (!payload) return;
      try{
        const parsed = JSON.parse(decodeURIComponent(payload));
        openImageModal(parsed);
      }catch (err){}
      return;
    }
    const reactionButton = target.closest ? target.closest(".reaction") : null;
    if (reactionButton){
      event.preventDefault();
      const reactionId = reactionButton.getAttribute("data-reaction");
      const itemKey = reactionButton.getAttribute("data-item");
      if (!reactionId || !itemKey) return;
      const decodedKey = decodeURIComponent(itemKey);
      postReaction(decodedKey, reactionId);
      return;
    }
    const artistLink = target.closest ? target.closest(".artist-link") : null;
    if (artistLink){
      event.preventDefault();
      const payload = artistLink.getAttribute("data-artist");
      if (!payload) return;
      try{
        const parsed = JSON.parse(decodeURIComponent(payload));
        openArtistModal(parsed.name, parsed.links);
      }catch (err){
        openArtistModal("Forest", {});
      }
      return;
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && imageModal.classList.contains("show")){
      closeImageModal();
    }
    if (imageModal.classList.contains("show") && (event.key === "ArrowLeft" || event.key === "ArrowRight")){
      event.preventDefault();
      if (event.key === "ArrowLeft") navigateDetail(-1);
      if (event.key === "ArrowRight") navigateDetail(1);
    }
  });
  loadWalletUser();
  load();
  maybeShowPostGameBanner();
  scheduleReturnPrompt();

  async function postReaction(itemId, reactionId){
    try{
      const res = await fetch("/api/gallery/reactions", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({item_id: itemId, reaction: reactionId})
      });
      const data = await res.json();
      if (!data.ok) return;
      const match = galleryItems.find(item => getItemKey(item) === itemId);
      if (match){
        match.reactions = data.reactions || {};
      }
      showToast("The Forest has received your offering.");
      // Refresh the right-side panel counts for the active item.
      if (currentDetailIndex >= 0){
        const current = galleryItems[currentDetailIndex];
        if (current && getItemKey(current) === itemId){
          renderDetailPanel(buildDetailPayload(current));
        }
      }
    }catch(err){}
  }
  function getItemKey(item){
    return item.item_id || item.id || item.image_id || item.url || `${item.title || "offering"}-${item.artist && item.artist.name ? item.artist.name : "forest"}`;
  }

  function getYear(item){
    if (item.year) return item.year;
    const ts = item.created_at || item.timestamp || item.created || null;
    if (!ts) return "";
    const value = Number(ts);
    if (!Number.isFinite(value)) return "";
    const ms = value > 1000000000000 ? value : value * 1000;
    const year = new Date(ms).getFullYear();
    return Number.isFinite(year) ? year : "";
  }

  function getOrigin(item){
    const eventName = item.event_name || item.event || item.rite || item.contest || item.origin || "";
    const year = getYear(item);
    const base = eventName ? `Offered during ${eventName}` : "Offered during the Forest rites";
    return year ? `${base} - ${year}` : base;
  }

  function getTypeBadge(item){
    const raw = item.type || item.origin_type || item.kind || item.category || "";
    if (raw) return raw;
    if (item.contest) return "Contest";
    if (item.rite) return "Rite";
    if (item.tarot || item.deck_id) return "Tarot";
    if (item.artifact) return "Artifact";
    return "";
  }

  function getTags(item){
    if (Array.isArray(item.tags)) return item.tags;
    if (Array.isArray(item.tag_list)) return item.tag_list;
    return [];
  }

  function isTextOnlyItem(item){
    if (!item) return false;
    const hasMedia = !!(item.url || item.thumb_url || item.fallback_url);
    if (hasMedia) return false;
    const title = String(item.title || item.text || "").trim();
    if (!title) return false;
    const artist = item.artist || {};
    const hasArtist = !!(artist.name || artist.id || artist.handle);
    if (hasArtist) return false;
    const rawType = String(item.type || item.origin_type || item.kind || item.category || "").toLowerCase();
    if (rawType.includes("inspiration") || rawType.includes("flair") || rawType.includes("text")){
      return true;
    }
    return true;
  }

  function escapeHtml(value){
    if (!value) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#x27;");
  }

  function applyArtistFilter(name){
    activeArtistFilter = name;
    if (filterRow){
      filterRow.style.display = name ? "flex" : "none";
    }
    if (filterName){
      filterName.textContent = name || "-";
    }
    renderGrid();
  }

  function buildCardHtml(item, index = 0){
    if (isTextOnlyItem(item)){
      return buildDividerHtml({text: item.title || item.text || ""});
    }
    const artist = normalizeArtist(item);
    const artistName = artist.name || "Forest";
    const title = item.title || "Untitled Offering";
    const artistLinks = artist.links || {};
    const origin = (item.origin || "").trim() || getOrigin(item);
    const tags = getTags(item);
    const itemKey = getItemKey(item);
    const baseCounts = item.reactions || {};
    // Prefer thumbs for speed, but always fall back to the full image if thumbs are missing or 404.
    // NOTE: do not rely on inline onerror handlers (CSP can block them). We wire errors via JS.
    const primaryUrl = item.thumb_url || item.url || "";
    let fallbackUrl = "";
    if (item.thumb_url && item.url && item.thumb_url !== item.url){
      fallbackUrl = item.url;
    }else if (item.fallback_url){
      fallbackUrl = item.fallback_url;
    }
    const fallbackAttr = fallbackUrl ? ` data-fallback="${fallbackUrl}"` : "";

    const payload = buildDetailPayload(item);
    const fullPayload = encodeURIComponent(JSON.stringify(payload));

    const media = primaryUrl
      ? `<img src="${primaryUrl}" alt="${escapeHtml(title)}" loading="lazy" decoding="async"${fallbackAttr} />`
      : `<div class="muted" style="padding:18px;text-align:center">Offering image not available.</div>`;

    // Minimal post: image in the middle. All metadata + links live in the right panel.
    return `
      <article class="post" data-index="${index}" data-full="${fullPayload}" aria-label="${escapeHtml(title)}">
        <div class="post-media">${media}<div class="artist-watermark" aria-hidden="true">${escapeHtml(artistName)}</div></div>
      </article>
    `;
  }

  function wireImageFallbacks(scope){
    const root = scope || document;
    const imgs = Array.from(root.querySelectorAll("img[data-fallback]"));
    imgs.forEach((img) => {
      if (img.dataset.fallbackWired === "1") return;
      img.dataset.fallbackWired = "1";
      img.addEventListener("error", () => {
        const fb = (img.dataset.fallback || "").trim();
        if (!fb) return;
        // Avoid loops.
        if (img.currentSrc === fb || img.src === fb) return;
        img.src = fb;
      });
    });
  }

  function scheduleVirtualRender(){
    if (virtualFrame) return;
    virtualFrame = requestAnimationFrame(() => {
      virtualFrame = null;
      renderVirtualGrid();
    });
  }

  function computeVirtualMetrics(){
    const style = getComputedStyle(grid);
    const colGap = parseFloat(style.columnGap) || 14;
    const rowGap = parseFloat(style.rowGap) || 20;
    const width = grid.clientWidth || grid.offsetWidth || 0;
    const cols = Math.max(1, Math.floor((width + colGap) / (CARD_MIN_WIDTH + colGap)));
    const colWidth = Math.max(CARD_MIN_WIDTH, Math.floor((width - colGap * (cols - 1)) / cols));
    return {cols, colWidth, colGap, rowGap};
  }

  function measureCardHeight(colWidth){
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.pointerEvents = "none";
    probe.style.left = "-9999px";
    probe.style.top = "0";
    probe.style.width = `${colWidth}px`;
    const sample = {
      title: "Untitled Offering",
      artist: {name: "Forest", links: {}},
      origin: "Offered during the Forest rites - 2024",
      type: "Artifact",
      tags: [],
      url: "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
      thumb_url: "data:image/gif;base64,R0lGODlhAQABAAAAACw=",
      reactions: {
        appreciation: 0,
        inspired: 0,
        gratitude: 0,
        craft: 0
      }
    };
    probe.innerHTML = buildCardHtml(sample);
    document.body.appendChild(probe);
    const card = probe.firstElementChild;
    const height = card ? card.getBoundingClientRect().height : CARD_HEIGHT;
    document.body.removeChild(probe);
    return Math.max(CARD_HEIGHT, Math.ceil(height) + 12);
  }

  function renderVirtualGrid(){
    const items = galleryRenderItems;
    if (!items.length){
      grid.innerHTML = "<div class='muted'>The Forest awaits its next contribution.</div>";
      grid.style.height = "";
      return;
    }
    grid.classList.add("virtualized");
    const {cols, colWidth, colGap, rowGap} = computeVirtualMetrics();
    if (cols !== virtualCols || !virtualCardHeight){
      virtualCols = cols;
      virtualCardHeight = measureCardHeight(colWidth);
      grid.style.setProperty("--card-width", `${colWidth}px`);
      grid.style.setProperty("--card-height", `${virtualCardHeight}px`);
    }
    const rowHeight = virtualCardHeight + rowGap;
    const totalRows = Math.ceil(items.length / cols);
    const totalHeight = Math.max(0, totalRows * rowHeight - rowGap);
    grid.style.height = `${totalHeight}px`;

    const scrollTop = window.scrollY;
    const gridTop = grid.getBoundingClientRect().top + scrollTop;
    const viewTop = Math.max(0, scrollTop - gridTop);
    const viewBottom = viewTop + window.innerHeight;
    const startRow = Math.max(0, Math.floor(viewTop / rowHeight) - VIRTUAL_BUFFER_ROWS);
    const endRow = Math.min(totalRows - 1, Math.ceil(viewBottom / rowHeight) + VIRTUAL_BUFFER_ROWS);
    const startIndex = startRow * cols;
    const endIndex = Math.min(items.length, (endRow + 1) * cols);

    grid.innerHTML = "";
    for (let i = startIndex; i < endIndex; i += 1){
      const item = items[i];
      const html = buildCardHtml(item);
      const temp = document.createElement("div");
      temp.innerHTML = html;
      const card = temp.firstElementChild;
      if (!card) continue;
      const row = Math.floor(i / cols);
      const col = i % cols;
      card.style.top = `${row * rowHeight}px`;
      card.style.left = `${col * (colWidth + colGap)}px`;
      card.style.width = `${colWidth}px`;
      card.style.height = `${virtualCardHeight}px`;
      grid.appendChild(card);
    }
  }

  function buildDividerHtml(item){
    const text = escapeHtml(item.text || item.title || "");
    return `
      <article class="post inspiration">
        <div class="inspiration-text">${text}</div>
      </article>
    `;
  }

  function insertDividers(items, startIndex = 0){
    const out = [];
    const dividerEvery = inspirationEvery || 7;
    const lines = (inspirationLines && inspirationLines.length) ? inspirationLines : DEFAULT_FOREST_LINES;
    for (let i = 0; i < items.length; i += 1){
      const globalIndex = startIndex + i;
      out.push({kind: "item", item: items[i], index: globalIndex});
      if (lines.length && (globalIndex + 1) % dividerEvery === 0){
        const pick = lines[Math.floor(Math.random() * lines.length)];
        if (pick){
          out.push({kind: "divider", text: pick});
        }
      }
    }
    return out;
  }

  let feedObserver = null;
  function wireFeedObserver(){
    if (!grid) return;
    if (feedObserver){
      try{ feedObserver.disconnect(); }catch(err){}
      feedObserver = null;
    }
    const posts = Array.from(grid.querySelectorAll(".post[data-index]"));
    if (!posts.length) return;
    feedObserver = new IntersectionObserver((entries) => {
      let best = null;
      for (const entry of entries){
        if (!entry.isIntersecting) continue;
        if (!best || entry.intersectionRatio > best.intersectionRatio){
          best = entry;
        }
      }
      if (!best) return;
      const idx = parseInt(best.target.getAttribute("data-index") || "-1", 10);
      if (!Number.isFinite(idx) || idx < 0) return;
      setActiveDetailIndex(idx);
    }, {root: null, rootMargin: '-40% 0px -40% 0px', threshold: [0.1, 0.25, 0.5, 0.75]});
    posts.forEach((el) => feedObserver.observe(el));
  }

  function setActiveDetailIndex(index){
    if (index < 0 || index >= galleryItems.length) return;
    const item = galleryItems[index];
    if (!item) return;
    currentDetailIndex = index;
    // Highlight active post
    document.querySelectorAll(".post.active").forEach((el) => el.classList.remove("active"));
    const active = grid.querySelector(`.post[data-index="${index}"]`);
    if (active){
      active.classList.add("active");
    }
    const payload = buildDetailPayload(item);
    renderDetailPanel(payload);
  }

  function renderGrid(){
    const items = Array.isArray(galleryItems) ? galleryItems : [];
    if (!items.length){
      grid.innerHTML = "<div class='muted'>The Forest awaits its next contribution.</div>";
      grid.style.height = "";
      return;
    }
    galleryRenderItems = insertDividers(items);
    grid.classList.toggle("filtering", !!activeArtistFilter);
    grid.classList.remove("virtualized");
    grid.style.height = "";
    grid.innerHTML = galleryRenderItems.map((entry) => {
      if (!entry) return "";
      if (entry.kind === "divider") return buildDividerHtml(entry);
      return buildCardHtml(entry.item, entry.index);
    }).join("");
    wireImageFallbacks(grid);
    wireFeedObserver();
    // Ensure the right panel shows something immediately.
    if (currentDetailIndex < 0 && items.length){
      setActiveDetailIndex(0);
    }
    renderSuggestions();
  }

  function appendGrid(items, startIndex){
    if (!Array.isArray(items) || !items.length) return;
    const baseIndex = Number.isFinite(startIndex) ? startIndex : Math.max(0, galleryItems.length - items.length);
    if (!grid.innerHTML){
      const batch = insertDividers(items, baseIndex);
      grid.innerHTML = batch.map((entry) => {
        if (!entry) return "";
        if (entry.kind === "divider") return buildDividerHtml(entry);
        return buildCardHtml(entry.item, entry.index);
      }).join("");
      wireImageFallbacks(grid);
      wireFeedObserver();
      return;
    }
    const batch = insertDividers(items, baseIndex);
    grid.insertAdjacentHTML("beforeend", batch.map((entry) => {
      if (!entry) return "";
      if (entry.kind === "divider") return buildDividerHtml(entry);
      return buildCardHtml(entry.item, entry.index);
    }).join(""));
    wireImageFallbacks(grid);
    wireFeedObserver();
    renderSuggestions();
  }

  function buildDetailPayload(item){
    const artist = normalizeArtist(item);
    const artistName = artist.name || "Forest";
    const title = item.title || "Untitled Offering";
    const origin = (item.origin || "").trim() || getOrigin(item);
    const itemKey = getItemKey(item);
    const baseCounts = item.reactions || {};
    return {
      url: item.url || item.thumb_url || "",
      fallback_url: item.fallback_url || "",
      info: [title, artistName, origin].filter(Boolean).join(" - "),
      title: title,
      artist: artistName,
      artist_links: artist.links || {},
      origin: origin,
      item_id: itemKey,
      actions: REACTIONS.map(reaction => ({
        id: reaction.id,
        label: reaction.label,
        count: Number(baseCounts[reaction.id] || 0)
      })),
      tags: getTags(item)
    };
  }

  function openDetailByIndex(index){
    if (index < 0 || index >= galleryItems.length) return;
    currentDetailIndex = index;
    const item = galleryItems[index];
    if (!item) return;
    openImageModal(buildDetailPayload(item));
  }

  function updateDetailNav(){
    if (!imagePrev || !imageNext) return;
    const hasItems = galleryItems.length > 0 && currentDetailIndex >= 0;
    imagePrev.disabled = !hasItems || currentDetailIndex <= 0;
    imageNext.disabled = !hasItems || currentDetailIndex >= galleryItems.length - 1;
  }

  function navigateDetail(delta){
    if (currentDetailIndex < 0) return;
    const nextIndex = currentDetailIndex + delta;
    if (nextIndex < 0 || nextIndex >= galleryItems.length) return;
    openDetailByIndex(nextIndex);
  }

  function renderSuggestions(){
    if (!suggestions || !suggestionsGrid) return;
    if (!galleryItems.length){
      suggestions.classList.remove("show");
      suggestions.setAttribute("aria-hidden", "true");
      return;
    }
    const cfgTitle = gallerySettings && gallerySettings.suggestions_title ? String(gallerySettings.suggestions_title) : "";
    if (suggestionsTitle && cfgTitle){
      suggestionsTitle.textContent = cfgTitle;
    }else if (suggestionsTitle){
      const titleVariants = [
        "The Forest suggests...",
        "Other offerings you may feel drawn to..."
      ];
      suggestionsTitle.textContent = titleVariants[Math.floor(Math.random() * titleVariants.length)];
    }
    let pool = [];
    if (activeArtistFilter){
      pool = galleryItems.filter(item => (item.artist && item.artist.name) === activeArtistFilter);
    }
    if (!pool.length){
      const anchor = galleryItems[0];
      const anchorEvent = anchor && (anchor.event_name || anchor.event || anchor.rite || anchor.origin);
      if (anchorEvent){
        pool = galleryItems.filter(item => (item.event_name || item.event || item.rite || item.origin) === anchorEvent);
      }
    }
    if (!pool.length){
      pool = galleryItems.slice();
    }
    const picks = [];
    const max = Math.min(6, pool.length);
    const used = new Set();
    while (picks.length < max && used.size < pool.length){
      const idx = Math.floor(Math.random() * pool.length);
      if (used.has(idx)) continue;
      used.add(idx);
      picks.push(pool[idx]);
    }
    suggestionsGrid.innerHTML = picks.map((item) => {
      const title = item.title || "Untitled Offering";
      const artistName = item.artist && item.artist.name ? item.artist.name : "Forest";
      const imgUrl = item.thumb_url || item.url || "";
      return `
        <div class="suggestions-card">
          ${imgUrl ? `<img src="${imgUrl}" alt="${title}" loading="lazy" decoding="async">` : ""}
          <div class="suggestions-title">${title}</div>
          <div class="suggestions-artist">Offered by ${artistName}</div>
        </div>
      `;
    }).join("");
    suggestions.classList.add("show");
    suggestions.setAttribute("aria-hidden", "false");
  }

  function maybeShowPostGameBanner(){
    if (!postGameBanner) return;
    if (sessionStorage.getItem(SESSION_BANNER_KEY)) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("source") !== "game_end") return;
    const gameName = params.get("game_name") || "the Forest";
    if (postGameTitle){
      postGameTitle.textContent = `Thank you for playing ${gameName} with us.`;
    }
    postGameBanner.classList.add("show");
    postGameBanner.setAttribute("aria-hidden", "false");
  }

  function scheduleReturnPrompt(){
    if (!returnPrompt) return;
    if (sessionStorage.getItem(SESSION_RETURN_KEY)) return;
    const showPrompt = () => {
      if (sessionStorage.getItem(SESSION_RETURN_KEY)) return;
      returnPrompt.classList.add("show");
      returnPrompt.setAttribute("aria-hidden", "false");
    };
    const onScroll = () => {
      if (window.scrollY > 1400){
        window.removeEventListener("scroll", onScroll);
        showPrompt();
      }
    };
    window.addEventListener("scroll", onScroll, {passive: true});
    setTimeout(showPrompt, 60000);
  }

  // ------------------------------------------------------------
  // Instagram-like behavior:
  // - the browser scrollbar drives the page
  // - as the user scrolls, the right panel updates to match
  //   the most-visible post in the center column.
  // ------------------------------------------------------------
  function initScrollLinkedDetails(){
    if (!grid) return;

    let lastItemId = null;

    const readPayload = (postEl) => {
      if (!postEl) return null;
      const encoded = postEl.getAttribute("data-full") || "";
      if (!encoded) return null;
      try{
        return JSON.parse(decodeURIComponent(encoded));
      }catch(err){
        return null;
      }
    };

    const setActiveFromPost = (postEl) => {
      const payload = readPayload(postEl);
      if (!payload) return;
      const id = payload.item_id || payload.url || "";
      if (id && id === lastItemId) return;
      lastItemId = id;
      renderDetailPanel(payload);
      if (detailWatermark) detailWatermark.textContent = payload.artist || "";
    };

    // Prefer the post that sits in the "center band" of the viewport.
    // Using rootMargin keeps side panels stable and makes the active post
    // switch predictably while scrolling.
    const observer = new IntersectionObserver((entries) => {
      let best = null;
      for (const entry of entries){
        if (!entry.isIntersecting) continue;
        if (!best || entry.intersectionRatio > best.intersectionRatio){
          best = entry;
        }
      }
      if (best) setActiveFromPost(best.target);
    }, {
      // The center column (.feed) is the scroll container.
      root: grid,
      // Wider "center band" so the right panel updates as soon as a card
      // approaches the center of the feed.
      rootMargin: "-25% 0px -25% 0px",
      threshold: [0.01, 0.12, 0.25, 0.4, 0.55]
    });

    const observePosts = () => {
      const posts = grid.querySelectorAll(".post[data-full]");
      posts.forEach((post) => observer.observe(post));
      // Initialize detail panel with the first post.
      if (posts.length) setActiveFromPost(posts[0]);
    };

    observePosts();

    // When the feed rerenders (paging/filter), re-observe.
    const mo = new MutationObserver(() => {
      // Disconnect and re-observe on next frame to avoid thrash.
      observer.disconnect();
      requestAnimationFrame(observePosts);
    });
    mo.observe(grid, {childList: true, subtree: true});
  }
