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
    }catch(_err){ return ""; }
  }

  async function request(path, options = {}){
    const opts = {...options};
    opts.headers = {...(options.headers || {})};
    const key = authKey();
    if (key){
      opts.headers["X-API-Key"] = key;
      opts.headers.Authorization = `Bearer ${key}`;
    }
    if (opts.body && !opts.headers["Content-Type"]) opts.headers["Content-Type"] = "application/json";
    const response = await fetch(path, opts);
    const text = await response.text();
    let payload = {};
    try{ payload = text ? JSON.parse(text) : {}; }
    catch(_err){ throw new Error(`Unexpected response (${response.status})`); }
    if (!response.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  function notice(message, kind = ""){
    const el = $("pageNotice");
    if (!message){ el.textContent = ""; el.className = "notice hidden"; return; }
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

  function bytes(value){
    let n = Number(value || 0);
    if (!Number.isFinite(n) || n <= 0) return "0 B";
    const units = ["B","KB","MB","GB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1){ n /= 1024; i += 1; }
    return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
  }

  function escapeHtml(value){
    return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;"
    })[ch]);
  }

  function providerLabel(id){
    const providers = statusCache?.providers || [];
    return providers.find((item) => item.id === id)?.label || id || "—";
  }

  function renderStatus(language){
    statusCache = language || {};
    const features = statusCache.features || {};
    const runtime = statusCache.runtime || {};
    const memory = statusCache.memory_stats || {};
    const context = statusCache.context || {};
    const reverence = statusCache.reverence || {};
    const storage = statusCache.storage || {};

    $("metricProvider").textContent = providerLabel(statusCache.provider);
    $("metricKey").textContent = `${statusCache.key_hint || "Not configured"} · ${statusCache.key_source || "unknown"} · ${statusCache.key_kind || "key"}`;
    $("metricModel").textContent = statusCache.model || "—";
    $("metricReasoning").textContent = `Reasoning ${statusCache.reasoning_mode || "—"}`;
    $("metricAudience").textContent = features.priest_chat ? "Enabled" : "Disabled";
    $("metricPriest").textContent = `Priest gate preserved · reverence ${reverence.enabled ? "on" : "off"}`;
    $("metricResult").textContent = runtime.last_error ? "Error" : (runtime.last_success_at ? "OK" : "Never");
    $("metricUsage").textContent = runtime.last_success_at
      ? `${runtime.input_tokens ?? "?"} in · ${runtime.output_tokens ?? "?"} out · ${runtime.last_latency_ms ?? "?"} ms`
      : "No successful request recorded";
    $("metricMemory").textContent = features.memory ? "Enabled" : "Disabled";
    $("metricMemoryDetail").textContent = `${memory.pinned ?? 0} pinned · ${memory.conversation ?? 0} conversation rows · ${bytes(memory.content_bytes)}`;

    $("configSource").textContent = `key: ${statusCache.key_source || "—"}`;
    $("provider").value = statusCache.provider || "openai";
    $("model").value = statusCache.model || "";
    $("temperature").value = statusCache.temperature ?? 0.7;
    $("maxTokens").value = statusCache.max_output_tokens ?? 400;
    $("reasoningMode").value = statusCache.reasoning_mode || "automatic";
    $("keyKind").value = statusCache.key_kind || "—";
    $("apiKey").value = "";
    $("apiKey").placeholder = statusCache.key_configured
      ? `Current: ${statusCache.key_hint} — leave blank to keep`
      : "Paste provider API key";
    $("providerHelp").textContent = statusCache.provider === "minimax"
      ? "MiniMax M3 supports adaptive/on/off reasoning. sk-cp Token Plan and sk-api pay-as-you-go keys are stored only in PostgreSQL."
      : "OpenAI remains available as a provider. The selected provider credential is stored only in PostgreSQL.";
    $("checkQuota").disabled = statusCache.provider !== "minimax";

    $("priestChat").checked = !!features.priest_chat;
    $("memoryEnabled").checked = !!features.memory;
    $("memoryTurns").value = features.memory_turns ?? 6;
    $("memoryRetention").value = features.memory_retention_days ?? 90;
    $("memoryRowCap").value = features.memory_global_row_cap ?? 5000;
    $("storageDetail").textContent = `${storage.persistent_backend || "PostgreSQL"} · ${memory.conversation ?? 0}/${features.memory_global_row_cap ?? 5000} conversation rows · ${bytes(memory.content_bytes)} text · no local-disk memory archive`;

    $("reverenceEnabled").checked = reverence.enabled !== false;
    $("requireAddress").checked = reverence.require_proper_address !== false;
    $("priestFamiliarity").checked = reverence.priest_familiarity !== false;
    $("emergencyOverride").checked = reverence.emergency_override !== false;
    $("reverenceStrictness").value = reverence.strictness || "moderate";
    $("casualPolicy").value = reverence.casual_policy || "correct_only";
    $("acceptedTitles").value = (reverence.accepted_titles || []).join("\n");
    $("reverenceState").textContent = reverence.enabled === false ? "disabled" : `${reverence.strictness || "moderate"} · ${reverence.casual_policy === "correct_then_answer" ? "correct + answer" : "correct first"}`;

    $("discordContext").checked = !!features.discord_context;
    builtInPrompt = context.default_system_prompt || "";
    $("systemPrompt").value = context.system_prompt || builtInPrompt;
    $("contextMode").textContent = context.uses_override ? "Custom context" : "Built-in context";
    $("logicList").innerHTML = (statusCache.logic || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");

    const summary = runtime.context_summary || {};
    $("ctxReverence").textContent = summary.reverence || "—";
    $("ctxPinned").textContent = summary.pinned_memories ?? "—";
    $("ctxHistory").textContent = summary.history_messages ?? "—";
    $("ctxDiscord").textContent = summary.discord_excerpts ?? "—";
    $("ctxAllowed").textContent = summary.knowledge_allowed == null ? "—" : (summary.knowledge_allowed ? "yes" : "no — ritual correction only");

    $("diagProvider").textContent = providerLabel(runtime.provider || statusCache.provider);
    $("diagModel").textContent = runtime.model || statusCache.model || "—";
    $("diagReasoning").textContent = runtime.reasoning_mode || statusCache.reasoning_mode || "—";
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
    if (!memories || !memories.length){ list.textContent = "No memory has been stored yet."; return; }
    list.innerHTML = memories.map((memory) => {
      const scope = memory.scope_type === "user" ? `user ${memory.scope_id}` : "global";
      const pin = memory.pinned ? "pinned" : "recent";
      return `<article class="memory-row">
        <div class="memory-meta"><span>${escapeHtml(scope)}</span><span>·</span><span>${escapeHtml(memory.kind)}</span><span>·</span><span>${escapeHtml(memory.role)}</span><span>·</span><span>${pin}</span><span>·</span><span>${escapeHtml(stamp(memory.created_at))}</span></div>
        <div class="memory-text">${escapeHtml(memory.content)}</div>
        <div class="memory-actions"><button class="danger-ghost" data-delete-memory="${memory.id}" type="button">Delete</button></div>
      </article>`;
    }).join("");
  }

  function renderSearch(results){
    const host = $("searchResults");
    if (!results || !results.length){ host.textContent = "No matching recent messages found."; return; }
    host.innerHTML = results.map((row) => `<article class="search-result">
      <div class="search-meta"><span>#${escapeHtml(row.channel_name)}</span><span>·</span><span>${escapeHtml(row.author_name)}</span><span>·</span><span>${escapeHtml(stamp(row.timestamp))}</span><span>·</span><span>score ${Number(row.score || 0).toFixed(1)}</span></div>
      <div class="search-text">${escapeHtml(row.content)}</div>
      ${row.jump_url ? `<div class="memory-actions"><a href="${escapeHtml(row.jump_url)}" target="_blank" rel="noopener">Open in Discord ↗</a></div>` : ""}
    </article>`).join("");
  }

  async function loadStatus(){ const payload = await request("/admin/language/status"); renderStatus(payload.language || {}); }
  async function loadChannels(){ const payload = await request("/admin/language/discord/channels"); renderChannels(payload.channels || [], !!payload.message_content_intent); }
  async function loadMemories(){ const payload = await request("/admin/language/memories?limit=100"); renderMemories(payload.memories || []); }

  async function loadAll(){
    notice("");
    try{ await Promise.all([loadStatus(), loadChannels(), loadMemories()]); }
    catch(err){ notice(err.message || "Unable to load Language Services.", "err"); }
  }

  function reverencePayload(){
    return {
      enabled: $("reverenceEnabled").checked,
      strictness: $("reverenceStrictness").value,
      require_proper_address: $("requireAddress").checked,
      casual_policy: $("casualPolicy").value,
      priest_familiarity: $("priestFamiliarity").checked,
      emergency_override: $("emergencyOverride").checked,
      accepted_titles: $("acceptedTitles").value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
    };
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
      reasoning_mode: $("reasoningMode").value,
      enable_priest_chat: $("priestChat").checked,
      memory_enabled: $("memoryEnabled").checked,
      memory_turns: Number($("memoryTurns").value || 6),
      memory_retention_days: Number($("memoryRetention").value || 90),
      memory_global_row_cap: Number($("memoryRowCap").value || 5000),
      discord_context_enabled: $("discordContext").checked,
      discord_context_channel_ids: selectedChannels,
      system_prompt: $("systemPrompt").value.trim(),
      reverence: reverencePayload(),
    };
    const key = $("apiKey").value.trim();
    if (key) payload.api_key = key;
    try{
      const response = await request("/admin/language/config", {method:"POST", body:JSON.stringify(payload)});
      renderStatus(response.language || {});
      statusLine("Saved. New Priest audiences use these settings immediately.", "ok");
    }catch(err){ statusLine(err.message || "Save failed.", "err"); }
    finally{ button.disabled = false; }
  }

  async function clearApiKey(){
    if (!window.confirm(`Clear the stored ${providerLabel($("provider").value)} key from PostgreSQL?`)) return;
    try{
      const response = await request("/admin/language/config", {method:"POST", body:JSON.stringify({provider:$("provider").value, clear_api_key:true})});
      renderStatus(response.language || {});
      statusLine("Stored provider key cleared.", "ok");
    }catch(err){ statusLine(err.message || "Unable to clear key.", "err"); }
  }

  async function testProvider(){
    const button = $("testProvider");
    button.disabled = true;
    notice("Sending one small provider request…");
    try{
      const response = await request("/admin/language/test", {method:"POST", body:"{}"});
      renderStatus(response.language || {});
      notice(`Provider reply: ${response.reply || "OK"}`);
    }catch(err){ notice(err.message || "Provider test failed.", "err"); try{ await loadStatus(); }catch(_err){} }
    finally{ button.disabled = false; }
  }

  async function checkQuota(){
    const button = $("checkQuota");
    button.disabled = true;
    $("quotaStatus").textContent = "Checking MiniMax Token Plan quota…";
    try{
      const response = await request("/admin/language/quota");
      if (!response.supported){
        $("quotaStatus").textContent = response.message || "Quota lookup unavailable for this key type.";
      }else{
        const q = response.quota || {};
        const compact = Object.entries(q).slice(0, 8).map(([k,v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
        $("quotaStatus").textContent = compact || "MiniMax returned quota status successfully.";
      }
    }catch(err){ $("quotaStatus").textContent = err.message || "Quota lookup failed."; }
    finally{ button.disabled = statusCache?.provider !== "minimax"; }
  }

  async function addMemory(){
    const content = $("memoryContent").value.trim();
    if (!content){ notice("Enter a memory note first.", "err"); return; }
    const scope = $("memoryScope").value;
    const scopeId = scope === "user" ? $("memoryUserId").value.trim() : "";
    if (scope === "user" && !/^\d+$/.test(scopeId)){ notice("A Discord user memory needs a numeric user ID.", "err"); return; }
    try{
      await request("/admin/language/memories", {method:"POST", body:JSON.stringify({content, scope_type:scope, scope_id:scopeId, kind:"note", pinned:true})});
      $("memoryContent").value = "";
      await Promise.all([loadMemories(), loadStatus()]);
      notice("Memory pinned.");
    }catch(err){ notice(err.message || "Unable to save memory.", "err"); }
  }

  async function deleteMemory(id){
    try{ await request(`/admin/language/memories/${encodeURIComponent(id)}`, {method:"DELETE"}); await Promise.all([loadMemories(), loadStatus()]); }
    catch(err){ notice(err.message || "Unable to delete memory.", "err"); }
  }

  async function clearConversations(){
    if (!window.confirm("Clear all unpinned Priest conversation memory? Pinned notes remain.")) return;
    try{
      const response = await request("/admin/language/memories/clear-conversations", {method:"POST", body:"{}"});
      await Promise.all([loadMemories(), loadStatus()]);
      notice(`Cleared ${response.deleted || 0} conversation memory rows.`);
    }catch(err){ notice(err.message || "Unable to clear conversation memory.", "err"); }
  }

  async function pruneMemory(){
    try{
      const response = await request("/admin/language/memories/prune", {method:"POST", body:"{}"});
      renderStatus(response.language || {});
      await loadMemories();
      notice(`Pruned ${response.deleted || 0} expired/excess conversation rows.`);
    }catch(err){ notice(err.message || "Unable to prune memory.", "err"); }
  }

  async function searchDiscord(){
    const query = $("searchQuery").value.trim();
    if (query.length < 2){ $("searchResults").textContent = "Enter at least two characters to search."; return; }
    const channel = $("searchChannel").value;
    const params = new URLSearchParams({q:query, limit:"30"});
    if (channel) params.set("channel_id", channel);
    $("searchResults").textContent = "Searching recent Discord history…";
    try{ const response = await request(`/admin/language/discord/search?${params.toString()}`); renderSearch(response.results || []); }
    catch(err){ $("searchResults").textContent = err.message || "Discord search failed."; }
  }

  $("provider").addEventListener("change", () => {
    const provider = $("provider").value;
    const current = $("model").value.trim();
    if (provider === "minimax" && (!current || /^gpt-/i.test(current))) $("model").value = "MiniMax-M3";
    if (provider === "openai" && (!current || /^MiniMax-/i.test(current))) $("model").value = "gpt-4o-mini";
    $("apiKey").value = "";
    $("keyKind").value = "save/select provider to resolve";
    $("checkQuota").disabled = provider !== "minimax";
    $("providerHelp").textContent = provider === "minimax"
      ? "MiniMax: use sk-cp for Token Plan or sk-api for pay-as-you-go. The key is persisted in PostgreSQL only."
      : "OpenAI project/API keys remain supported and are persisted in PostgreSQL only.";
  });
  $("refreshAll").addEventListener("click", loadAll);
  $("saveConfig").addEventListener("click", saveConfig);
  $("clearApiKey").addEventListener("click", clearApiKey);
  $("testProvider").addEventListener("click", testProvider);
  $("checkQuota").addEventListener("click", checkQuota);
  $("restoreContext").addEventListener("click", () => { $("systemPrompt").value = builtInPrompt; $("contextMode").textContent = "Built-in context (pending save)"; });
  $("memoryScope").addEventListener("change", () => { $("memoryUserWrap").classList.toggle("hidden", $("memoryScope").value !== "user"); });
  $("addMemory").addEventListener("click", addMemory);
  $("clearConversations").addEventListener("click", clearConversations);
  $("pruneMemory").addEventListener("click", pruneMemory);
  $("memoryList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-delete-memory]");
    if (button) deleteMemory(button.dataset.deleteMemory);
  });
  $("searchDiscord").addEventListener("click", searchDiscord);
  $("searchQuery").addEventListener("keydown", (event) => { if (event.key === "Enter") searchDiscord(); });

  loadAll();
})();
