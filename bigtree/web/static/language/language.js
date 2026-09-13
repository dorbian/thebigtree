(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let statusCache = null;
  let channelCache = [];
  let builtInPrompt = "";

  function authKey(){
    try{
      const parentStorage = window.parent && window.parent.localStorage;
      const key = parentStorage ? parentStorage.getItem("bt_api_key") : "";
      if (key) return key;
    }catch(_err){}
    try{
      return window.localStorage.getItem("bt_api_key") || window.sessionStorage.getItem("bt_api_key") || "";
    }catch(_err){
      return "";
    }
  }

  async function request(path, options = {}){
    const opts = {...options};
    opts.headers = {...(options.headers || {})};
    const key = authKey();
    if (key){
      opts.headers["X-API-Key"] = key;
      opts.headers.Authorization = `Bearer ${key}`;
    }
    if (opts.body && !opts.headers["Content-Type"]){
      opts.headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, opts);
    const text = await response.text();
    let payload = {};
    try{ payload = text ? JSON.parse(text) : {}; }
    catch(_err){ throw new Error(`Unexpected response (${response.status})`); }
    if (!response.ok || payload.ok === false){
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  function notice(message, kind = ""){
    const el = $("pageNotice");
    if (!message){
      el.textContent = "";
      el.className = "notice hidden";
      return;
    }
    el.textContent = message;
    el.className = `notice${kind ? " " + kind : ""}`;
  }

  function statusLine(message, kind = ""){
    const el = $("configStatus");
    el.textContent = message;
    el.className = `status-line${kind ? " " + kind : ""}`;
  }

  function stamp(value){
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  function escapeHtml(value){
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"
    })[ch]);
  }

  function renderStatus(language){
    statusCache = language || {};
    const features = statusCache.features || {};
    const runtime = statusCache.runtime || {};
    const memory = statusCache.memory_stats || {};
    const context = statusCache.context || {};

    $("metricProvider").textContent = statusCache.provider || "—";
    $("metricKey").textContent = `${statusCache.key_hint || "Not configured"} · ${statusCache.key_source || "unknown source"}`;
    $("metricModel").textContent = statusCache.model || "—";
    $("metricPriest").textContent = `Priest chat ${features.priest_chat ? "enabled" : "disabled"}`;
    $("metricResult").textContent = runtime.last_error ? "Error" : (runtime.last_success_at ? "OK" : "Never");
    $("metricUsage").textContent = runtime.last_success_at
      ? `${runtime.input_tokens ?? "?"} in · ${runtime.output_tokens ?? "?"} out · ${runtime.last_latency_ms ?? "?"} ms`
      : "No successful request recorded";
    $("metricMemory").textContent = features.memory ? "Enabled" : "Disabled";
    $("metricMemoryDetail").textContent = `${memory.pinned ?? 0} pinned · ${memory.conversation ?? 0} conversation rows · ${memory.users ?? 0} users`;

    $("configSource").textContent = `key: ${statusCache.key_source || "—"}`;
    $("provider").value = statusCache.provider || "openai";
    $("model").value = statusCache.model || "";
    $("temperature").value = statusCache.temperature ?? 0.7;
    $("maxTokens").value = statusCache.max_output_tokens ?? 400;
    $("apiKey").value = "";
    $("apiKey").placeholder = statusCache.key_configured
      ? `Current: ${statusCache.key_hint} — leave blank to keep`
      : "Paste provider API key";
    $("priestChat").checked = !!features.priest_chat;
    $("memoryEnabled").checked = !!features.memory;
    $("memoryTurns").value = features.memory_turns ?? 6;
    $("discordContext").checked = !!features.discord_context;

    builtInPrompt = context.default_system_prompt || "";
    $("systemPrompt").value = context.system_prompt || builtInPrompt;
    $("contextMode").textContent = context.uses_override ? "Custom context" : "Built-in context";
    $("logicList").innerHTML = (statusCache.logic || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");

    $("diagAttempt").textContent = stamp(runtime.last_attempt_at);
    $("diagSuccess").textContent = stamp(runtime.last_success_at);
    $("diagLatency").textContent = runtime.last_latency_ms == null ? "—" : `${runtime.last_latency_ms} ms`;
    $("diagInput").textContent = runtime.input_tokens ?? "—";
    $("diagOutput").textContent = runtime.output_tokens ?? "—";
    $("diagRequest").textContent = runtime.last_request_id || "—";
    $("diagError").textContent = runtime.last_error || "—";

    renderContextChannels(features.discord_context_channel_ids || []);
  }

  function renderChannels(channels, intent){
    channelCache = Array.isArray(channels) ? channels : [];
    const search = $("searchChannel");
    search.innerHTML = `<option value="">All readable channels</option>`;
    for (const channel of channelCache){
      const option = document.createElement("option");
      option.value = channel.id;
      option.textContent = channel.category ? `${channel.category} / #${channel.name}` : `#${channel.name}`;
      search.appendChild(option);
    }
    $("discordIntent").textContent = intent ? "message content available" : "message-content intent off";
    renderContextChannels(statusCache?.features?.discord_context_channel_ids || []);
  }

  function renderContextChannels(selectedIds){
    const selected = new Set((selectedIds || []).map(String));
    const select = $("contextChannels");
    select.innerHTML = "";
    for (const channel of channelCache){
      const option = document.createElement("option");
      option.value = channel.id;
      option.textContent = channel.category ? `${channel.category} / #${channel.name}` : `#${channel.name}`;
      option.selected = selected.has(String(channel.id));
      select.appendChild(option);
    }
    if (!channelCache.length){
      const option = document.createElement("option");
      option.textContent = "No readable text channels loaded";
      option.disabled = true;
      select.appendChild(option);
    }
  }

  function renderMemories(memories){
    const list = $("memoryList");
    if (!memories || !memories.length){
      list.textContent = "No memory has been stored yet.";
      return;
    }
    list.innerHTML = memories.map((memory) => {
      const scope = memory.scope_type === "user" ? `user ${memory.scope_id}` : "global";
      const pin = memory.pinned ? "pinned" : "recent";
      return `<article class="memory-row">
        <div class="memory-meta">
          <span>${escapeHtml(scope)}</span><span>·</span>
          <span>${escapeHtml(memory.kind)}</span><span>·</span>
          <span>${escapeHtml(memory.role)}</span><span>·</span>
          <span>${pin}</span><span>·</span>
          <span>${escapeHtml(stamp(memory.created_at))}</span>
        </div>
        <div class="memory-text">${escapeHtml(memory.content)}</div>
        <div class="memory-actions"><button class="danger-ghost" data-delete-memory="${memory.id}" type="button">Delete</button></div>
      </article>`;
    }).join("");
  }

  function renderSearch(results){
    const host = $("searchResults");
    if (!results || !results.length){
      host.textContent = "No matching recent messages found.";
      return;
    }
    host.innerHTML = results.map((row) => `<article class="search-result">
      <div class="search-meta">
        <span>#${escapeHtml(row.channel_name)}</span><span>·</span>
        <span>${escapeHtml(row.author_name)}</span><span>·</span>
        <span>${escapeHtml(stamp(row.timestamp))}</span><span>·</span>
        <span>score ${Number(row.score || 0).toFixed(1)}</span>
      </div>
      <div class="search-text">${escapeHtml(row.content)}</div>
      ${row.jump_url ? `<div class="memory-actions"><a href="${escapeHtml(row.jump_url)}" target="_blank" rel="noopener">Open in Discord ↗</a></div>` : ""}
    </article>`).join("");
  }

  async function loadStatus(){
    const payload = await request("/admin/language/status");
    renderStatus(payload.language || {});
  }

  async function loadChannels(){
    const payload = await request("/admin/language/discord/channels");
    renderChannels(payload.channels || [], !!payload.message_content_intent);
  }

  async function loadMemories(){
    const payload = await request("/admin/language/memories?limit=100");
    renderMemories(payload.memories || []);
  }

  async function loadAll(){
    notice("");
    try{
      await Promise.all([loadStatus(), loadChannels(), loadMemories()]);
    }catch(err){
      notice(err.message || "Unable to load Language Services.", "err");
    }
  }

  async function saveConfig(){
    const button = $("saveConfig");
    button.disabled = true;
    statusLine("Saving…");
    const selectedChannels = Array.from($("contextChannels").selectedOptions || []).map((option) => option.value).filter(Boolean);
    const payload = {
      provider: $("provider").value,
      model: $("model").value.trim(),
      temperature: Number($("temperature").value || 0.7),
      max_output_tokens: Number($("maxTokens").value || 400),
      enable_priest_chat: $("priestChat").checked,
      memory_enabled: $("memoryEnabled").checked,
      memory_turns: Number($("memoryTurns").value || 6),
      discord_context_enabled: $("discordContext").checked,
      discord_context_channel_ids: selectedChannels,
      system_prompt: $("systemPrompt").value.trim(),
    };
    const key = $("apiKey").value.trim();
    if (key) payload.api_key = key;
    try{
      const response = await request("/admin/language/config", {method:"POST", body:JSON.stringify(payload)});
      renderStatus(response.language || {});
      statusLine("Saved. New requests use these settings immediately.", "ok");
    }catch(err){
      statusLine(err.message || "Save failed.", "err");
    }finally{
      button.disabled = false;
    }
  }

  async function clearApiKey(){
    if (!window.confirm("Clear the API key stored in PostgreSQL? The service may fall back to an INI/environment key.")) return;
    try{
      const response = await request("/admin/language/config", {method:"POST", body:JSON.stringify({clear_api_key:true})});
      renderStatus(response.language || {});
      statusLine("Stored provider key cleared.", "ok");
    }catch(err){
      statusLine(err.message || "Unable to clear key.", "err");
    }
  }

  async function testProvider(){
    const button = $("testProvider");
    button.disabled = true;
    notice("Sending one small provider request…");
    try{
      const response = await request("/admin/language/test", {method:"POST", body:JSON.stringify({})});
      renderStatus(response.language || {});
      notice(`Provider reply: ${response.reply || "OK"}`);
    }catch(err){
      notice(err.message || "Provider test failed.", "err");
      try{ await loadStatus(); }catch(_err){}
    }finally{
      button.disabled = false;
    }
  }

  async function addMemory(){
    const content = $("memoryContent").value.trim();
    if (!content){
      notice("Enter a memory note first.", "err");
      return;
    }
    const scope = $("memoryScope").value;
    const scopeId = scope === "user" ? $("memoryUserId").value.trim() : "";
    if (scope === "user" && !/^\d+$/.test(scopeId)){
      notice("A Discord user memory needs a numeric user ID.", "err");
      return;
    }
    try{
      await request("/admin/language/memories", {
        method:"POST",
        body:JSON.stringify({content, scope_type:scope, scope_id:scopeId, kind:"note", pinned:true}),
      });
      $("memoryContent").value = "";
      await Promise.all([loadMemories(), loadStatus()]);
      notice("Memory pinned.");
    }catch(err){
      notice(err.message || "Unable to save memory.", "err");
    }
  }

  async function deleteMemory(id){
    try{
      await request(`/admin/language/memories/${encodeURIComponent(id)}`, {method:"DELETE"});
      await Promise.all([loadMemories(), loadStatus()]);
    }catch(err){
      notice(err.message || "Unable to delete memory.", "err");
    }
  }

  async function clearConversations(){
    if (!window.confirm("Clear all unpinned Priest conversation memory? Pinned notes will remain.")) return;
    try{
      const response = await request("/admin/language/memories/clear-conversations", {method:"POST", body:"{}"});
      await Promise.all([loadMemories(), loadStatus()]);
      notice(`Cleared ${response.deleted || 0} conversation memory rows.`);
    }catch(err){
      notice(err.message || "Unable to clear conversation memory.", "err");
    }
  }

  async function searchDiscord(){
    const query = $("searchQuery").value.trim();
    if (query.length < 2){
      $("searchResults").textContent = "Enter at least two characters to search.";
      return;
    }
    const channel = $("searchChannel").value;
    const params = new URLSearchParams({q:query, limit:"30"});
    if (channel) params.set("channel_id", channel);
    $("searchResults").textContent = "Searching recent Discord history…";
    try{
      const response = await request(`/admin/language/discord/search?${params.toString()}`);
      renderSearch(response.results || []);
    }catch(err){
      $("searchResults").textContent = err.message || "Discord search failed.";
    }
  }

  $("refreshAll").addEventListener("click", loadAll);
  $("saveConfig").addEventListener("click", saveConfig);
  $("clearApiKey").addEventListener("click", clearApiKey);
  $("testProvider").addEventListener("click", testProvider);
  $("restoreContext").addEventListener("click", () => {
    $("systemPrompt").value = builtInPrompt;
    $("contextMode").textContent = "Built-in context (pending save)";
  });
  $("memoryScope").addEventListener("change", () => {
    $("memoryUserWrap").classList.toggle("hidden", $("memoryScope").value !== "user");
  });
  $("addMemory").addEventListener("click", addMemory);
  $("clearConversations").addEventListener("click", clearConversations);
  $("memoryList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-memory]");
    if (!button) return;
    deleteMemory(button.dataset.deleteMemory);
  });
  $("searchDiscord").addEventListener("click", searchDiscord);
  $("searchQuery").addEventListener("keydown", (event) => {
    if (event.key === "Enter") searchDiscord();
  });

  loadAll();
})();
