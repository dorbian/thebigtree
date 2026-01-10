const grid = document.getElementById("grid");
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
  const USE_VIRTUAL = true;
  const PAGE_SIZE = 120;
  let gallerySeed = null;
  let galleryTotal = 0;
  let galleryLoading = false;
  const GALLERY_CACHE_KEY = "forest_gallery_cache_v1";
  let activeArtistFilter = null;
  const REACTIONS = [
    {id:"appreciation", label:"Appreciation"},
    {id:"inspired", label:"Inspired"},
    {id:"gratitude", label:"Gratitude"},
    {id:"craft", label:"Craft"}
  ];

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

  function openArtistModal(name, links){
    artistName.textContent = name || "Forest";
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
    imageModal.classList.add("show");
    imageModal.setAttribute("aria-hidden", "false");
    showImageInfo();
  }

  function closeImageModal(){
    imageModal.classList.remove("show");
    imageModal.setAttribute("aria-hidden", "true");
    imageModalImg.src = "";
    imageInfo.textContent = "";
  }

  function preloadThumbnails(items){
    if (!items || !items.length) return;
    const head = document.head || document.getElementsByTagName("head")[0];
    if (!head) return;
    const max = Math.min(12, items.length);
    for (let i = 0; i < max; i += 1){
      const item = items[i] || {};
      const href = item.thumb_url || item.url;
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

  async function loadBatch(offset){
    if (galleryLoading) return;
    galleryLoading = true;
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
      }else{
        galleryItems = galleryItems.concat(batch);
        if (USE_VIRTUAL){
          renderGrid();
        }else{
          appendGrid(batch);
        }
      }
      if (galleryItems.length < galleryTotal){
        const nextOffset = galleryItems.length;
        if ("requestIdleCallback" in window){
          requestIdleCallback(() => loadBatch(nextOffset));
        }else{
          setTimeout(() => loadBatch(nextOffset), 60);
        }
      }
    }catch(err){
      if (!galleryItems.length){
        grid.innerHTML = "<div class='muted'>Gallery unavailable.</div>";
      }
    }finally{
      galleryLoading = false;
    }
  }

  async function load(){
    const cached = readCachedGallery();
    if (cached && Array.isArray(cached.items) && cached.items.length){
      galleryItems = cached.items;
      gallerySeed = Number.isFinite(cached.seed) ? cached.seed : null;
      galleryTotal = Number(cached.total) || 0;
      preloadThumbnails(galleryItems);
      activeArtistFilter = null;
      if (filterRow) filterRow.style.display = "none";
      renderGrid();
      requestAnimationFrame(() => loadBatch(0));
      return;
    }
    grid.innerHTML = Array.from({length: 4}).map(() => `<div class="skeleton-card"></div>`).join("");
    galleryItems = [];
    gallerySeed = null;
    galleryTotal = 0;
    activeArtistFilter = null;
    if (filterRow) filterRow.style.display = "none";
    await loadBatch(0);
  }

  document.getElementById("artistClose").addEventListener("click", closeArtistModal);
  artistModal.addEventListener("click", (event) => {
    if (event.target === artistModal) closeArtistModal();
  });
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
  document.getElementById("imageClose").addEventListener("click", closeImageModal);
  imageModal.addEventListener("click", (event) => {
    if (event.target === imageModal) closeImageModal();
  });
  imageModal.addEventListener("mousemove", showImageInfo);
  grid.addEventListener("click", (event) => {
    const target = event.target;
    if (target.tagName === "IMG" && target.getAttribute("data-full")){
      event.preventDefault();
      const payload = target.getAttribute("data-full");
      if (!payload) return;
      try{
        const parsed = JSON.parse(decodeURIComponent(payload));
        openImageModal(parsed);
      }catch (err){}
      return;
    }
    if (target.classList && target.classList.contains("view-btn")){
      event.preventDefault();
      const payload = target.getAttribute("data-full");
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
    if (!artistLink) return;
    event.preventDefault();
    const payload = artistLink.getAttribute("data-artist");
    if (!payload) return;
    try{
      const parsed = JSON.parse(decodeURIComponent(payload));
      openArtistModal(parsed.name, parsed.links);
    }catch (err){
      openArtistModal("Forest", {});
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && imageModal.classList.contains("show")){
      closeImageModal();
    }
  });
  load();

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
      const reactionButton = grid.querySelector(`.reaction[data-item="${encodeURIComponent(itemId)}"][data-reaction="${reactionId}"]`);
      if (reactionButton){
        const count = Number((data.reactions || {})[reactionId] || 0);
        const countNode = reactionButton.querySelector(".reaction-count");
        if (countNode){
          countNode.textContent = String(count);
        }else{
          reactionButton.innerHTML = `<span>${getReactionLabel(reactionId)}</span> <span class="reaction-count">${count}</span>`;
        }
      }else if (!USE_VIRTUAL){
        renderGrid();
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

  function buildCardHtml(item){
    const artist = item.artist || {};
    const artistName = artist.name || "Forest";
    const title = item.title || "Untitled Offering";
    const artistLinks = artist.links || {};
    const origin = (item.origin || "").trim() || getOrigin(item);
    const type = getTypeBadge(item);
    const tags = getTags(item);
    const infoText = [title, artistName, origin].filter(Boolean).join(" - ");
    const artistPayload = encodeURIComponent(JSON.stringify({
      name: artistName,
      links: artistLinks
    }));
    const itemKey = getItemKey(item);
    const baseCounts = item.reactions || {};
    const reactionRow = REACTIONS.map(reaction => {
      const count = Number(baseCounts[reaction.id] || 0);
      return `
          <button class="reaction" data-reaction="${reaction.id}" data-item="${encodeURIComponent(itemKey)}" aria-label="${reaction.label}">
            <span>${reaction.label}</span> <span class="reaction-count">${count}</span>
          </button>
        `;
    }).join("");
    const imgUrl = item.thumb_url || item.url;
    const fallbackUrl = item.thumb_url ? (item.url || "") : (item.fallback_url || "");
    const fallbackAttr = fallbackUrl ? ` data-fallback="${fallbackUrl}"` : "";
    const fullPayload = encodeURIComponent(JSON.stringify({
      url: item.url,
      fallback_url: item.fallback_url || "",
      info: infoText,
      title: title
    }));
    const media = imgUrl
      ? `<img src="${imgUrl}" alt="${title}" loading="lazy" decoding="async"${fallbackAttr} data-full="${fullPayload}" onerror="if(this.dataset.fallback&&this.src!==this.dataset.fallback){this.src=this.dataset.fallback;}" />`
      : `<div class="muted" style="padding:18px;text-align:center">Offering image not available.</div>`;
    const viewButton = item.url
      ? `<button class="view-btn" data-full="${fullPayload}">View</button>`
      : `<button class="view-btn" disabled>View</button>`;
    const isActive = !activeArtistFilter || activeArtistFilter === artistName;
    return `
        <div class="card ${isActive ? "active" : ""}" data-artist="${artistName}">
          <div class="card-media">
            ${media}
          </div>
          <div class="card-body">
            <div class="artist-name">${artistName}</div>
            <div class="work-title">${title}</div>
            <div class="origin">${origin}</div>
            ${type ? `<div class="pill-row"><span class="type-pill">${type}</span></div>` : ""}
            ${tags.length ? `<div class="pill-row">${tags.map(t => `<span class="tag-pill">${t}</span>`).join("")}</div>` : ""}
            <a class="artist-link" href="#" data-artist="${artistPayload}">Artist details</a>
            <div class="reaction-row">${reactionRow}</div>
            <div class="card-actions">
              ${viewButton}
            </div>
          </div>
        </div>
      `;
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

  function renderGrid(){
    const items = Array.isArray(galleryItems) ? galleryItems : [];
    if (!items.length){
      grid.innerHTML = "<div class='muted'>The Forest awaits its next contribution.</div>";
      grid.style.height = "";
      return;
    }
    galleryRenderItems = items;
    grid.classList.toggle("filtering", !!activeArtistFilter);
    if (USE_VIRTUAL){
      scheduleVirtualRender();
      if (!virtualListening){
        virtualListening = true;
        window.addEventListener("scroll", scheduleVirtualRender, {passive: true});
        window.addEventListener("resize", scheduleVirtualRender);
      }
      return;
    }
    grid.classList.remove("virtualized");
    grid.style.height = "";
    grid.innerHTML = galleryRenderItems.map(buildCardHtml).join("");
  }

  function appendGrid(items){
    if (!Array.isArray(items) || !items.length) return;
    if (!grid.innerHTML){
      grid.innerHTML = items.map(buildCardHtml).join("");
      return;
    }
    grid.insertAdjacentHTML("beforeend", items.map(buildCardHtml).join(""));
  }

