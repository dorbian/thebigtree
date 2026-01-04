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
  const USE_VIRTUAL = false;
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

  function link(label, url){
    if (!url) return "";
    return `<a href="${url}" target="_blank" rel="noreferrer">${label}</a>`;
  }

  function openArtistModal(name, links){
    artistName.textContent = name || "Forest";
    if (artistFilterBtn){
      artistFilterBtn.dataset.artist = name || "Forest";
    }
    const linkItems = Object.entries(links || {})
      .filter(([, url]) => url)
      .map(([label, url]) => `<a href="${url}" target="_blank" rel="noreferrer">${label}</a>`);
    artistLinks.innerHTML = linkItems.length ? linkItems.join("") : "<span class='muted'>No external links shared.</span>";
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
      }else{
        galleryItems = galleryItems.concat(batch);
      }
      renderGrid();
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
    if (target.classList && target.classList.contains("reaction")){
      event.preventDefault();
      const reactionId = target.getAttribute("data-reaction");
      const itemKey = target.getAttribute("data-item");
      if (!reactionId || !itemKey) return;
      const decodedKey = decodeURIComponent(itemKey);
      postReaction(decodedKey, reactionId);
      return;
    }
    if (!target.classList || !target.classList.contains("artist-link")) return;
    event.preventDefault();
    const payload = target.getAttribute("data-artist");
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
      renderGrid();
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
            <span>${reaction.label}</span> ${count}
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

  function measureCardHeight(_colWidth){
    return CARD_HEIGHT;
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

