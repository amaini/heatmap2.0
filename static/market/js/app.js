/* Stocks Heatmap Frontend
 * - CRUD via JSON APIs
 * - Debounced search + autocomplete
 * - Quotes fetching with timeout, retry and caching in localStorage
 * - Heatmap rendering with progress bars and colored tiles
 * - Auto refresh with countdown and last-refresh timestamp
 * - Connection status indicator and error handling
 * - Manage purchased lots via modal CRUD
 */
(function(){
  const cfg = window.HEATMAP_CONFIG || { csrftoken: '', timeout: 10 };

  // Local storage keys
  const LS = {
    sectors: 'hm.sectors.v1',
    tickers: 'hm.tickers.v1',
    quotes: 'hm.quotes.v1',
    autoRefresh: 'hm.autorefresh.v1',
    sidebar: 'hm.sidebarCollapsed.v1',
  };

  // Elements
  const heatmapEl = document.getElementById('heatmap');
  const connEl = document.getElementById('connStatus');
  const appRoot = document.querySelector('.app');
  const btnToggleSidebarPanel = document.getElementById('btnToggleSidebarPanel');
  const sidebarHandle = document.getElementById('sidebarHandle');
  const btnRefresh = document.getElementById('btnRefresh');
  const refreshSpinner = document.getElementById('refreshSpinner');
  const autoRefreshSel = document.getElementById('autoRefresh');
  const nextRefreshEl = document.getElementById('nextRefresh');
  const lastRefreshEl = document.getElementById('lastRefresh');
  const marketStatusEl = document.getElementById('marketStatus');
  const skeletonEl = document.getElementById('loadingSkeleton');
  const errorBox = document.getElementById('errorBox');

  const searchInput = document.getElementById('searchInput');
  const searchResults = document.getElementById('searchResults');

  const modalSector = document.getElementById('modalSector');
  const formSector = document.getElementById('formSector');
  const modalSectorTitle = document.getElementById('modalSectorTitle');

  const modalTicker = document.getElementById('modalTicker');
  const formTicker = document.getElementById('formTicker');
  const modalTickerTitle = document.getElementById('modalTickerTitle');
  const selectSector = document.getElementById('selectSector');
  const symbolSuggest = document.getElementById('symbolSuggest');
  const btnOpenColors = document.getElementById('btnOpenColors');
  const modalColors = document.getElementById('modalColors');
  const formColors = document.getElementById('formColors');
  const colorGain = document.getElementById('colorGain');
  const colorFlat = document.getElementById('colorFlat');
  const colorLoss = document.getElementById('colorLoss');

  const modalLots = document.getElementById('modalLots');
  const lotsList = document.getElementById('lotsList');
  const lotsTickerFilter = document.getElementById('lotsTickerFilter');
  const btnAddLot = document.getElementById('btnAddLot');

  const modalLotForm = document.getElementById('modalLotForm');
  const formLot = document.getElementById('formLot');
  const modalLotTitle = document.getElementById('modalLotTitle');
  const selectLotTicker = document.getElementById('selectLotTicker');

  // Copilot elements
  const btnCopilot = document.getElementById('btnCopilot');
  const modalCopilot = document.getElementById('modalCopilot');
  const copilotBody = document.getElementById('copilotBody');

  // API key UI
  const apiKeyInput = document.getElementById('apiKeyInput');
  const btnSaveApiKey = document.getElementById('btnSaveApiKey');
  const apiKeyStatus = document.getElementById('apiKeyStatus');

  // Move ticker modal elements
  const modalMoveTicker = document.getElementById('modalMoveTicker');
  const formMoveTicker = document.getElementById('formMoveTicker');
  const moveTickerId = document.getElementById('moveTickerId');
  const selectMoveSector = document.getElementById('selectMoveSector');
  const btnMoveAddLot = document.getElementById('btnMoveAddLot');
  const btnMoveManageLots = document.getElementById('btnMoveManageLots');

  // Rate limit tracker
  let reqCount = 0;
  let windowStart = Date.now();
  function trackRequest(){
    const now = Date.now();
    if (now - windowStart > 60_000){ windowStart = now; reqCount = 0; }
    reqCount += 1;
  }

  // Simple API helper with timeout + retry
  async function apiFetch(url, opts = {}, retry = 2) {
    trackRequest();
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), (cfg.timeout || 10) * 1000);
    const headers = Object.assign({ 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, opts.headers || {});
    if (opts.method && opts.method !== 'GET') headers['X-CSRFToken'] = cfg.csrftoken || '';
    try {
      const res = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts, { headers, signal: controller.signal }));
      clearTimeout(id);
      if (!res.ok) {
        let body = {};
        try { body = await res.json(); } catch(e) {}
        const err = new Error(body.error || res.statusText);
        err.status = res.status; err.code = body.code;
        throw err;
      }
      return await res.json();
    } catch (err) {
      clearTimeout(id);
      if (retry > 0 && (err.status === 429 || err.name === 'AbortError')) {
        const backoff = (Math.random() * 200) + (300 * Math.pow(2, (2 - retry)));
        console.log('[retry]', url, 'in', backoff, 'ms');
        await new Promise(r => setTimeout(r, backoff));
        return apiFetch(url, opts, retry - 1);
      }
      throw err;
    }
  }

  function setConn(status, message){
    connEl.classList.remove('connected','error');
    if (status === 'connected'){ connEl.textContent = message || 'Connected ✅'; connEl.classList.add('connected'); }
    else if (status === 'error'){ connEl.textContent = message || 'Error ❌'; connEl.classList.add('error'); }
    else { connEl.textContent = message || 'Connecting…'; }
  }

  function showSkeleton(count){
    skeletonEl.innerHTML = '';
    for(let i=0;i<count;i++){ const d = document.createElement('div'); d.className = 'skeleton-tile'; skeletonEl.appendChild(d); }
    skeletonEl.hidden = false;
  }
  function hideSkeleton(){ skeletonEl.hidden = true; }

  function showError(msg){ errorBox.textContent = msg; errorBox.hidden = false; }
  function clearError(){ errorBox.hidden = true; errorBox.textContent = ''; }

  function saveLS(key, value){ localStorage.setItem(key, JSON.stringify(value)); }
  function loadLS(key, fallback){ try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch(e){ return fallback; } }

  async function loadInitial(){
    setConn('connecting');
    showSkeleton(24);
    try {
      const [sectorsRes, tickersRes, mktRes] = await Promise.all([
        apiFetch('/api/sectors/'),
        apiFetch('/api/tickers/'),
        apiFetch('/api/market-status'),
      ]);
      const sectors = sectorsRes.sectors || [];
      const tickers = tickersRes.tickers || [];
      saveLS(LS.sectors, { ts: Date.now(), data: sectors });
      saveLS(LS.tickers, { ts: Date.now(), data: tickers });
      renderSelectors(sectors, tickers);
      renderHeatmap(sectors, tickers, loadLS(LS.quotes, {data:{}}).data || {});
      updateMarketStatus(mktRes.status);
      setConn('connected');
    } catch (e) {
      console.warn('Initial load error', e);
      const sectors = loadLS(LS.sectors, { data: [] }).data;
      const tickers = loadLS(LS.tickers, { data: [] }).data;
      renderSelectors(sectors, tickers);
      renderHeatmap(sectors, tickers, loadLS(LS.quotes, {data:{}}).data || {});
      setConn('error', 'Error ❌ (offline)');
      showError('Could not load data from server. Showing cached.');
    } finally {
      hideSkeleton();
    }
  }

  function renderSelectors(sectors, tickers){
    // sector select in ticker form
    selectSector.innerHTML = sectors.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
    // lots ticker selects
    const opts = tickers.map(t => `<option value="${t.id}">${t.symbol} — ${t.company_name || ''}</option>`).join('');
    lotsTickerFilter.innerHTML = `<option value="">All</option>` + opts;
    selectLotTicker.innerHTML = opts;
  }

  function groupBySector(sectors, tickers){
    const bySectorId = new Map(sectors.map(s => [s.id, { sector: s, items: [] }]));
    tickers.forEach(t => {
      const g = bySectorId.get(t.sector_id);
      if (g) g.items.push(t);
    });
    return Array.from(bySectorId.values());
  }

  function renderHeatmap(sectors, tickers, quotes){
    const groups = groupBySector(sectors, tickers);
    const frag = document.createDocumentFragment();
    groups.forEach(g => {
      const sec = document.createElement('div'); sec.className = 'sector';
      const title = document.createElement('div'); title.className = 'sector-title';
      title.innerHTML = `<span>${g.sector.name}</span> <button class="mini-btn" data-edit-sector="${g.sector.id}">Edit</button> <button class="mini-btn" data-del-sector="${g.sector.id}">Delete</button>`;
      sec.appendChild(title);
      const tiles = document.createElement('div'); tiles.className = 'tiles';
      tiles.dataset.sectorId = String(g.sector.id);
      tiles.addEventListener('dragover', (ev) => { ev.preventDefault(); tiles.classList.add('drop-target'); });
      tiles.addEventListener('dragleave', () => tiles.classList.remove('drop-target'));
      tiles.addEventListener('drop', async (ev) => {
        ev.preventDefault(); tiles.classList.remove('drop-target');
        const tid = ev.dataTransfer && ev.dataTransfer.getData('text/plain');
        if (!tid) return;
        const id = Number(tid);
        const newSector = Number(tiles.dataset.sectorId);
        const t = (loadLS(LS.tickers,{data:[]}).data || []).find(x => x.id === id);
        if (!t || t.sector_id === newSector) return;
        await moveTickerToSector(t, newSector);
      });
      g.items.forEach(t => { tiles.appendChild(makeTile(t, quotes[t.symbol])); });
      sec.appendChild(tiles); frag.appendChild(sec);
    });
    heatmapEl.innerHTML = '';
    heatmapEl.appendChild(frag);
  }

  function fmt(n, digits=2){ if(n === null || n === undefined || isNaN(n)) return '—'; return Number(n).toFixed(digits); }
  function tileClass(dp){ if (dp > 0.15) return 'tile gain'; if (dp < -0.15) return 'tile loss'; return 'tile flat'; }

  function makeTile(t, q){
    const div = document.createElement('div');
    const dp = q && typeof q.dp === 'number' ? q.dp : 0;
    div.className = tileClass(dp);
    div.classList.add('tile');
    div.setAttribute('draggable', 'true');
    div.dataset.tickerId = String(t.id);
    div.addEventListener('dragstart', (ev) => {
      try { ev.dataTransfer.setData('text/plain', String(t.id)); } catch(_){}
      div.classList.add('dragging');
    });
    div.addEventListener('dragend', () => div.classList.remove('dragging'));
    const price = q ? q.c : null; const pc = q ? q.pc : null; const h = q ? q.h : null; const l = q ? q.l : null; const pct = q && q.dp !== null && q.dp !== undefined ? q.dp : null; const change = q && q.d !== null && q.d !== undefined ? q.d : null;
    const pctText = pct !== null ? (pct >= 0 ? '+' : '') + fmt(pct, 2) + '%' : '—';
    div.title = `${t.symbol} ${t.company_name || ''}\nPrice: ${fmt(price)}  Prev: ${fmt(pc)}\nHigh: ${fmt(h)}  Low: ${fmt(l)}\nChange: ${fmt(change)} (${pctText})`;
    div.innerHTML = `
      <div class="tile-actions">
        <button class="icon" title="Edit Ticker" data-edit-ticker="${t.id}">✎</button>
        <button class="icon" title="Delete Ticker" data-del-ticker="${t.id}">🗑</button>
      </div>
      <div class="sym">${t.symbol}</div>
      <div class="name" title="${t.company_name || ''}">${t.company_name || ''}</div>
      <div class="price">${fmt(price)} <span class="change">${pctText}</span></div>
      <div class="progress"><span style="width:${progressPct(price, l, h)}%"></span></div>
    `;
    // Insert refresh icon into actions
    try {
      const actions = div.querySelector('.tile-actions');
      if (actions){
        const rb = document.createElement('button');
        rb.className = 'icon'; rb.title = 'Refresh'; rb.setAttribute('data-refresh-ticker', String(t.id)); rb.textContent = '⟳';
        actions.insertBefore(rb, actions.firstChild || null);
      }
    } catch(_){}
    // Label the daily range bar and add indicator + L/H labels
    try {
      const _day = div.querySelector('.progress');
      if (_day) {
        _day.classList.add('day');
        if (l != null && h != null){
          const pin = document.createElement('div');
          pin.className = 'pin';
          pin.style.left = `${positionPct(price, l, h)}%`;
          _day.appendChild(pin);

          const labels = document.createElement('div');
          labels.className = 'bar-labels day';
          labels.innerHTML = `<span>L ${fmt(l)}</span><span>H ${fmt(h)}</span>`;
          div.appendChild(labels);
        }
      }
    } catch(_){}
    // Add levels and previous close lines
    try {
      const levels = document.createElement('div');
      levels.className = 'levels';
      levels.textContent = `L ${fmt(l)} · C ${fmt(price)} · H ${fmt(h)}`;
      div.appendChild(levels);
      const prev = document.createElement('div');
      prev.className = 'prev';
      prev.textContent = `Prev: ${fmt(pc)}`;
      div.appendChild(prev);
    } catch(_){}
    // Add purchased lot summary and 52-week bar
    try {
      const qty = (typeof t.lots_qty === 'number') ? t.lots_qty : null;
      const avg = (typeof t.avg_cost === 'number') ? t.avg_cost : null;
      const totalCost = (typeof t.lots_cost === 'number') ? t.lots_cost : null;
      const mktVal = (qty && price) ? qty * price : null;
      const pl = (mktVal !== null && totalCost !== null) ? (mktVal - totalCost) : null;
      const plPct = (pl !== null && totalCost > 0) ? (pl / totalCost) * 100 : null;
      const metaParts = [];
      // include previous close first to avoid overlap and keep single info line
      metaParts.push(`Prev: ${fmt(pc)}`);
      if (qty) metaParts.push(`Qty ${fmt(qty,4)}`);
      if (avg) metaParts.push(`Avg $${fmt(avg,2)}`);
      if (pl !== null) metaParts.push(`P/L ${(pl>=0?'+':'')}$${fmt(pl,2)}${plPct!=null?` (${(plPct>=0?'+':'')}${fmt(plPct,2)}%)`:''}`);
      if (metaParts.length){
        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.textContent = metaParts.join(' · ');
        div.appendChild(meta);
        try { meta.textContent = metaParts.join(' · '); } catch(_) { meta.textContent = metaParts.join(' | '); }
      }
      // Ensure Prev is not shown in hover meta line
      try {
        var metas = div.querySelector('.meta');
        if (metas && metas.textContent) {
          var parts = metas.textContent.split(/\s*[·|]\s*/);
          parts = parts.filter(function(s){ return s && !/^Prev:/i.test(s); });
          metas.textContent = parts.join(' · ');
        }
      } catch(_){ }
      // 52-week progress
      const w52h = q && (q.week52High ?? q['week52High']);
      const w52l = q && (q.week52Low ?? q['week52Low']);
      if (w52h != null && w52l != null){
        const bar = document.createElement('div');
        bar.className = 'progress w52';
        bar.innerHTML = `<span style="width:${progressPct(price, w52l, w52h)}%"></span>`;
        const wpin = document.createElement('div');
        wpin.className = 'pin';
        try { wpin.style.left = `${positionPct(price, w52l, w52h)}%`; } catch(_) {}
        bar.appendChild(wpin);
        div.appendChild(bar);
        // Add labels for 52w
        const wlabels = document.createElement('div');
        wlabels.className = 'bar-labels w52';
        wlabels.innerHTML = `<span>L ${fmt(w52l)}</span><span>H ${fmt(w52h)}</span>`;
        div.appendChild(wlabels);
        // extend title
        div.title += `\nQty: ${qty ?? '—'}  Avg: ${avg ? '$'+fmt(avg,2) : '—'}  P/L: ${pl != null ? (pl>=0?'+':'')+'$'+fmt(pl,2) : '—'} (${plPct != null ? (plPct>=0?'+':'')+fmt(plPct,2)+'%' : '—'})\n52w: ${fmt(w52l)} – ${fmt(w52h)}`;
      }
    } catch(_){}
    // Click -> open Move Sector modal (ignore tile-actions clicks)
    div.addEventListener('click', (ev) => {
      if (ev.target && ev.target.closest && ev.target.closest('.tile-actions')) return;
      openMoveTickerModal(t);
    });
    return div;
  }

  function progressPct(c, l, h){
    if(c === null || l === null || h === null || isNaN(c) || isNaN(l) || isNaN(h) || h === l) return 50;
    const p = Math.max(0, Math.min(1, (c - l) / (h - l)));
    return 3 + p * 94; // leave small side margins
  }
  function positionPct(c, l, h){
    if(c === null || l === null || h === null || isNaN(c) || isNaN(l) || isNaN(h) || h === l) return 50;
    const p = Math.max(0, Math.min(1, (c - l) / (h - l)));
    return p * 100;
  }

  // Refresh logic
  let refreshTimer = null; let countdownTimer = null; let nextAt = null;
  function setAutoRefresh(seconds){
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    saveLS(LS.autoRefresh, seconds);
    if (seconds && seconds !== 'off'){
      const s = Number(seconds);
      scheduleNext(s);
      refreshTimer = setInterval(() => { scheduleNext(s); doRefresh(); }, s * 1000);
      countdownTimer = setInterval(() => updateCountdown(), 1000);
    } else {
      nextRefreshEl.textContent = '—';
    }
  }
  function scheduleNext(s){ nextAt = Date.now() + s * 1000; updateCountdown(); }
  function updateCountdown(){ if (!nextAt) return; const ms = Math.max(0, nextAt - Date.now()); const sec = Math.round(ms/1000); nextRefreshEl.textContent = `Next: ${sec}s`; }

  async function doRefresh(){
    clearError(); setConn('connecting'); btnRefresh.disabled = true; refreshSpinner.hidden = false;
    const tickers = (loadLS(LS.tickers, {data: []}).data) || [];
    const symbols = tickers.map(t => t.symbol);
    const start = performance.now();
    try {
      const res = await apiFetch('/api/quotes', { method: 'POST', body: JSON.stringify({ symbols }) });
      console.log('[quotes]', { tookMs: Math.round(performance.now() - start), size: Object.keys(res.quotes || {}).length, errors: res.errors });
      saveLS(LS.quotes, { ts: Date.now(), data: res.quotes });
      renderHeatmap(loadLS(LS.sectors, {data:[]}).data, tickers, res.quotes);
      lastRefreshEl.textContent = `Last: ${new Date().toLocaleTimeString()}`;
      setConn(Object.keys(res.errors||{}).length ? 'error' : 'connected');
      updateMarketStatus(res.marketStatus);
    } catch (e) {
      console.warn('quotes error', e);
      const cached = loadLS(LS.quotes, { data: {} }).data;
      if (Object.keys(cached).length){
        renderHeatmap(loadLS(LS.sectors, {data:[]}).data, tickers, cached);
        showError('Using cached quotes due to error: ' + (e.message || ''));
      } else {
        showError('Failed to refresh quotes: ' + (e.message || ''));
      }
      setConn('error');
    } finally {
      btnRefresh.disabled = false; refreshSpinner.hidden = true;
    }
  }

  function updateMarketStatus(status){
    if (!status) return; marketStatusEl.textContent = `Market: ${status.session}${status.isOpen ? ' (Open)' : ''}`;
  }

  // Search with debounce
  let searchTimer = null;
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    if (searchTimer) clearTimeout(searchTimer);
    if (!q){ searchResults.hidden = true; searchResults.innerHTML = ''; return; }
    searchTimer = setTimeout(async () => {
      try {
        const res = await apiFetch('/api/search?q=' + encodeURIComponent(q));
        const results = (res.results || []).slice(0, 20);
        renderSearch(results);
      } catch (e) {
        console.warn('search error', e);
        searchResults.hidden = true; searchResults.innerHTML = '';
      }
    }, 250);
  });
  function renderSearch(results){
    searchResults.innerHTML = results.map(r => `<div class="item" data-sym="${r.symbol}" data-name="${r.description}"><strong>${r.symbol}</strong> <span class="muted">${r.description}</span></div>`).join('');
    searchResults.hidden = results.length === 0;
  }
  searchResults.addEventListener('click', (e) => {
    const item = e.target.closest('.item'); if (!item) return;
    // Fill ticker form
    openTickerModal();
    formTicker.symbol.value = item.dataset.sym || '';
    formTicker.company_name.value = item.dataset.name || '';
    searchResults.hidden = true;
  });

  // Modals
  function openModal(el){ el.hidden = false; }
  function closeModal(el){ el.hidden = true; }
  document.querySelectorAll('[data-close]').forEach(btn => btn.addEventListener('click', (e) => {
    const modal = e.target.closest('.modal'); if (modal) closeModal(modal);
  }));

  // Buttons
  document.getElementById('btnAddSector').addEventListener('click', () => openSectorModal());
  document.getElementById('btnAddTicker').addEventListener('click', () => openTickerModal());
  document.getElementById('btnManageLots').addEventListener('click', async () => {
    await ensureTickersLoaded(true);
    openModal(modalLots); loadLots();
  });

  btnRefresh.addEventListener('click', doRefresh);
  autoRefreshSel.addEventListener('change', () => setAutoRefresh(autoRefreshSel.value));
  if (btnOpenColors) btnOpenColors.addEventListener('click', () => openModal(modalColors));
  // API key handlers
  (async function initApiKey(){
    try {
      const res = await apiFetch('/api/config');
      if (res.ok && res.config){
        // Do not prefill input to avoid showing any part of the key
        apiKeyInput.value = '';
        apiKeyStatus.textContent = res.config.hasKey ? 'Key set' : 'Not set';
      }
    } catch(_){}
  })();
  if (btnSaveApiKey){
    btnSaveApiKey.addEventListener('click', async () => {
      const key = (apiKeyInput.value || '').trim();
      try {
        const res = await apiFetch('/api/config', { method:'PUT', body: JSON.stringify({ finnhub_api_key: key }) });
        // Clear the input after save; do not show the key
        apiKeyInput.value = '';
        apiKeyStatus.textContent = res.config.hasKey ? 'Key set' : 'Not set';
        // Optional: refresh quotes to validate
        doRefresh();
      } catch(e){ alert('Failed to save key: ' + (e.message || '')); }
    });
  }
  if (btnCopilot) btnCopilot.addEventListener('click', async () => {
    if (modalCopilot) openModal(modalCopilot);
    if (copilotBody){
      copilotBody.innerHTML = '<div class="muted">Analyzing portfolio…</div>';
      try {
        const insights = await generateCopilotInsights(defaultCopilotThresholds());
        copilotBody.innerHTML = renderCopilot(insights);
        wireCopilotFilters(insights);
      } catch (e){
        copilotBody.innerHTML = `<div class="error">${(e && e.message) || 'Failed to analyze.'}</div>`;
      }
    }
  });

  // Sidebar toggle
  function applySidebarState(collapsed){
    if (collapsed){
      appRoot.classList.add('sidebar-collapsed');
      if (sidebarHandle){ sidebarHandle.hidden = false; sidebarHandle.textContent = '⮞'; sidebarHandle.title = 'Show panel'; }
    } else {
      appRoot.classList.remove('sidebar-collapsed');
      if (sidebarHandle){ sidebarHandle.hidden = true; }
      if (btnToggleSidebarPanel){ btnToggleSidebarPanel.textContent = '⮜'; btnToggleSidebarPanel.title = 'Hide panel'; }
    }
  }
  const savedSidebar = loadLS(LS.sidebar, false);
  applySidebarState(!!savedSidebar);
  function toggleSidebar(){
      const now = !appRoot.classList.contains('sidebar-collapsed');
      applySidebarState(now);
      saveLS(LS.sidebar, now);
  }
  if (btnToggleSidebarPanel) btnToggleSidebarPanel.addEventListener('click', toggleSidebar);
  if (sidebarHandle) sidebarHandle.addEventListener('click', toggleSidebar);

  // Heatmap delegated actions for edit/delete sector/ticker
  heatmapEl.addEventListener('click', (e) => {
    const btnRefT = e.target.closest && e.target.closest('[data-refresh-ticker]');
    if (btnRefT){
      const id = Number(btnRefT.getAttribute('data-refresh-ticker'));
      const tickers = loadLS(LS.tickers, {data:[]}).data;
      const t = tickers.find(x => x.id === id);
      if (t) refreshSingleTicker(t).catch(console.warn);
      e.stopPropagation(); return;
    }
    const btnEditSec = e.target.closest('[data-edit-sector]');
    if (btnEditSec){
      const id = Number(btnEditSec.getAttribute('data-edit-sector'));
      const sectors = loadLS(LS.sectors, {data:[]}).data;
      const s = sectors.find(x => x.id === id); if (s) openSectorModal(s);
      e.stopPropagation(); return;
    }
    const btnDelSec = e.target.closest('[data-del-sector]');
    if (btnDelSec){
      const id = Number(btnDelSec.getAttribute('data-del-sector'));
      if (!confirm('Delete this sector and its tickers?')) return;
      apiFetch('/api/sectors/', { method: 'DELETE', body: JSON.stringify({ id }) })
        .then(() => {
          const sectors = loadLS(LS.sectors, {data:[]}).data.filter(s => s.id !== id);
          const tickers = loadLS(LS.tickers, {data:[]}).data.filter(t => t.sector_id !== id);
          saveLS(LS.sectors, { ts: Date.now(), data: sectors });
          saveLS(LS.tickers, { ts: Date.now(), data: tickers });
          renderSelectors(sectors, tickers); renderHeatmap(sectors, tickers, loadLS(LS.quotes,{data:{}}).data);
        })
        .catch(e => alert('Error deleting sector: ' + (e.message || '')));
      e.stopPropagation(); return;
    }
    const btnEditT = e.target.closest('[data-edit-ticker]');
    if (btnEditT){
      const id = Number(btnEditT.getAttribute('data-edit-ticker'));
      const t = (loadLS(LS.tickers, {data:[]}).data).find(x => x.id === id);
      if (t) openTickerModal(t);
      e.stopPropagation(); return;
    }
    const btnDelT = e.target.closest('[data-del-ticker]');
    if (btnDelT){
      const id = Number(btnDelT.getAttribute('data-del-ticker'));
      if (!confirm('Delete this ticker?')) return;
      apiFetch('/api/tickers/', { method: 'DELETE', body: JSON.stringify({ id }) })
        .then(() => {
          const tickers = loadLS(LS.tickers, {data:[]}).data.filter(t => t.id !== id);
          saveLS(LS.tickers, { ts: Date.now(), data: tickers });
          renderSelectors(loadLS(LS.sectors,{data:[]}).data, tickers); renderHeatmap(loadLS(LS.sectors,{data:[]}).data, tickers, loadLS(LS.quotes,{data:{}}).data);
        })
        .catch(e => alert('Error deleting ticker: ' + (e.message || '')));
      e.stopPropagation(); return;
    }
  });

  // Sector modal
  function openSectorModal(sector){
    modalSectorTitle.textContent = sector ? 'Edit Sector' : 'Add Sector';
    formSector.id.value = sector ? sector.id : '';
    formSector.name.value = sector ? sector.name : '';
    openModal(modalSector);
  }
  formSector.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = { id: formSector.id.value || undefined, name: formSector.name.value };
    try {
      const res = await apiFetch('/api/sectors/', { method: payload.id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      // Update local cache
      const sectors = loadLS(LS.sectors, { data: [] }).data;
      if (payload.id){
        const idx = sectors.findIndex(s => s.id == payload.id); if (idx>=0) sectors[idx] = res.sector;
      } else { sectors.push(res.sector); }
      saveLS(LS.sectors, { ts: Date.now(), data: sectors });
      renderSelectors(sectors, loadLS(LS.tickers, {data:[]}).data);
      try { e.target.dataset.dirty = '0'; } catch(_){}
      closeModal(modalSector);
    } catch (e) {
      alert('Error saving sector: ' + (e.message || ''));
    }
  });

  // Ticker modal
  function openTickerModal(ticker){
    modalTickerTitle.textContent = ticker ? 'Edit Ticker' : 'Add Ticker';
    formTicker.id.value = ticker ? ticker.id : '';
    formTicker.symbol.value = ticker ? ticker.symbol : '';
    formTicker.company_name.value = ticker ? (ticker.company_name || '') : '';
    selectSector.value = ticker ? ticker.sector_id : selectSector.value;
    formTicker.security_type.value = ticker ? (ticker.security_type || '') : 'Common Stock';
    if (symbolSuggest) { symbolSuggest.hidden = true; symbolSuggest.innerHTML = ''; }
    openModal(modalTicker);
  }
  formTicker.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      id: formTicker.id.value || undefined,
      symbol: formTicker.symbol.value.trim().toUpperCase(),
      company_name: formTicker.company_name.value.trim(),
      sector: Number(selectSector.value),
      security_type: formTicker.security_type.value || 'Common Stock',
    };
    try {
      // Auto-fill company name via search if blank
      if (!payload.company_name && payload.symbol){
        try {
          const sRes = await apiFetch('/api/search?q=' + encodeURIComponent(payload.symbol));
          const hit = (sRes.results || []).find(r => r.symbol === payload.symbol);
          if (hit) payload.company_name = hit.description || payload.company_name;
        } catch (e) {}
      }
      const isCreate = !payload.id;
      const res = await apiFetch('/api/tickers/', { method: isCreate ? 'POST' : 'PUT', body: JSON.stringify(payload) });
      // Update cache
      const tickers = loadLS(LS.tickers, { data: [] }).data;
      if (isCreate){ tickers.push(res.ticker); }
      else { const i = tickers.findIndex(t => t.id == payload.id); if (i>=0) tickers[i] = res.ticker; }
      saveLS(LS.tickers, { ts: Date.now(), data: tickers });
      renderSelectors(loadLS(LS.sectors, {data:[]}).data, tickers);
      renderHeatmap(loadLS(LS.sectors, {data:[]}).data, tickers, loadLS(LS.quotes, {data:{}}).data);
      try { e.target.dataset.dirty = '0'; } catch(_){}
      closeModal(modalTicker);
      if (isCreate) { try { await refreshSingleTicker(res.ticker); } catch(_){} }
    } catch (e) { alert('Error saving ticker: ' + (e.message || '')); }
  });

  // Lots modal
  async function loadLots(){
    try {
      const params = lotsTickerFilter.value ? ('?ticker_id=' + encodeURIComponent(lotsTickerFilter.value)) : '';
      const res = await apiFetch('/api/lots/' + params);
      renderLots(res.lots || []);
    } catch(e){ alert('Error loading lots: ' + (e.message || '')); }
  }
  lotsTickerFilter.addEventListener('change', loadLots);
  btnAddLot.addEventListener('click', async () => {
    const tickers = await ensureTickersLoaded(true);
    if (!tickers.length){
      alert('Please add a ticker first.');
      openTickerModal();
      return;
    }
    modalLotTitle.textContent = 'Add Lot';
    formLot.reset();
    // Default select first ticker to avoid empty selection
    selectLotTicker.value = String(tickers[0].id);
    openModal(modalLotForm);
  });
  function renderLots(lots){
    lotsList.innerHTML = '';
    if (!lots.length){ lotsList.innerHTML = '<div class="muted">No lots</div>'; return; }
    lots.forEach(l => {
      const row = document.createElement('div'); row.className = 'lot-row';
      row.innerHTML = `
        <div>${l.ticker__symbol}</div>
        <div>${l.trade_date}</div>
        <div>${Number(l.quantity).toFixed(4)}</div>
        <div>$${Number(l.price).toFixed(4)}</div>
        <div>${l.notes || ''}</div>
        <div class="actions">
          <button class="btn btn-small" data-edit>Edit</button>
          <button class="btn btn-small" data-del>Delete</button>
        </div>
      `;
      row.querySelector('[data-edit]').addEventListener('click', () => {
        modalLotTitle.textContent = 'Edit Lot';
        formLot.id.value = l.id;
        selectLotTicker.value = String(l.ticker_id);
        formLot.quantity.value = l.quantity;
        formLot.price.value = l.price;
        formLot.trade_date.value = l.trade_date;
        formLot.notes.value = l.notes || '';
        openModal(modalLotForm);
      });
      row.querySelector('[data-del]').addEventListener('click', async () => {
        if (!confirm('Delete this lot?')) return;
        try {
          await apiFetch('/api/lots/', { method: 'DELETE', body: JSON.stringify({ id: l.id }) });
          loadLots();
          try {
            const tlist = loadLS(LS.tickers, {data:[]}).data;
            const t = tlist.find(x => x.id === l.ticker_id);
            if (t) await refreshSingleTicker(t);
          } catch(_){}
        } catch(e){ alert('Error deleting lot: ' + (e.message || '')); }
      });
      lotsList.appendChild(row);
    });
  }
  formLot.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      id: formLot.id.value || undefined,
      ticker: Number(selectLotTicker.value),
      quantity: Number(formLot.quantity.value),
      price: Number(formLot.price.value),
      trade_date: formLot.trade_date.value,
      notes: formLot.notes.value || '',
    };
    try {
      await apiFetch('/api/lots/', { method: payload.id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      try { e.target.dataset.dirty = '0'; } catch(_){}
      closeModal(modalLotForm);
      loadLots();
      try {
        const tlist = loadLS(LS.tickers, {data:[]}).data;
        const t = tlist.find(x => x.id === payload.ticker);
        if (t) await refreshSingleTicker(t);
      } catch(_){}
    } catch (e){ alert('Error saving lot: ' + (e.message || '')); }
  });

  // Init auto-refresh from localStorage
  const savedAuto = loadLS(LS.autoRefresh, 'off');
  autoRefreshSel.value = savedAuto;
  setAutoRefresh(savedAuto);

  // Initial load and first refresh
  loadInitial().then(() => doRefresh());

  // Helper: ensure tickers available; optionally fetch from API when empty
  async function ensureTickersLoaded(forceFetch){
    let tickers = (loadLS(LS.tickers, {data: []}).data) || [];
    if (tickers.length && !forceFetch) return tickers;
    try {
      const res = await apiFetch('/api/tickers/');
      tickers = res.tickers || [];
      saveLS(LS.tickers, { ts: Date.now(), data: tickers });
      renderSelectors(loadLS(LS.sectors,{data:[]}).data, tickers);
    } catch (e) {
      // keep existing cache
    }
    return tickers;
  }

  // Copilot: portfolio suggestions
  function defaultCopilotThresholds(){
    return {
      dp: 1.0,          // percent change for momentum signals
      nearHigh: 0.95,   // breakout if >= 95% of 52w range
      nearLow: 0.05,    // breakdown/oversold if <= 5%
      bounceDp: 0.4,    // oversold bounce minimum daily change
      meanDp: 1.0       // mean reversion trigger absolute dp
    };
  }

  async function generateCopilotInsights(thr){
    // Ensure we have latest tickers and quotes
    let sectors = (loadLS(LS.sectors, {data: []}).data) || [];
    let tickers = (loadLS(LS.tickers, {data: []}).data) || [];
    if (!tickers.length){ try { const tRes = await apiFetch('/api/tickers/'); tickers = tRes.tickers || []; saveLS(LS.tickers,{ts:Date.now(),data:tickers}); } catch(_){}}
    let quotes = (loadLS(LS.quotes, {data: {}}).data) || {};
    if (!Object.keys(quotes).length && tickers.length){
      try { const qRes = await apiFetch('/api/quotes', { method: 'POST', body: JSON.stringify({ symbols: tickers.map(t=>t.symbol) }) }); quotes = qRes.quotes || {}; saveLS(LS.quotes,{ts:Date.now(),data:quotes}); } catch(_){}
    }

    const buy = []; const sell = []; const hold = [];
    const signals = {
      momentumLong: [], momentumShort: [],
      breakoutHigh: [], breakdownLow: [],
      oversoldBounce: [], meanRevLong: [], meanRevShort: []
    };
    const sectorStats = new Map();
    let sumDp = 0, cntDp = 0, downCount = 0;

    for (const t of tickers){
      const q = quotes[t.symbol] || {};
      const price = toNum(q.c), pc = toNum(q.pc), dp = toNum(q.dp);
      const w52h = toNum(q.week52High), w52l = toNum(q.week52Low);
      const qty = toNum(t.lots_qty); const avg = toNum(t.avg_cost);
      const sectorId = t.sector_id;
      if (!sectorStats.has(sectorId)) sectorStats.set(sectorId, {dpSum:0, n:0});
      if (!isNaN(dp)) { const st = sectorStats.get(sectorId); st.dpSum+=dp; st.n++; sumDp+=dp; cntDp++; if (dp<0) downCount++; }

      if (!isNaN(dp)){
        if (dp >= thr.dp) signals.momentumLong.push(`${t.symbol}: ${dp.toFixed(2)}% today`);
        if (dp <= -thr.dp) signals.momentumShort.push(`${t.symbol}: ${dp.toFixed(2)}% today`);
      }
      if (!isNaN(w52h) && !isNaN(w52l) && w52h>w52l && !isNaN(price)){
        const pos52 = (price-w52l)/(w52h-w52l);
        if (pos52 >= thr.nearHigh && dp>0) signals.breakoutHigh.push(`${t.symbol}: near highs (${Math.round(pos52*100)}%), dp ${isNaN(dp)?'n/a':dp.toFixed(2)}%`);
        if (pos52 <= thr.nearLow && dp<0) signals.breakdownLow.push(`${t.symbol}: near lows (${Math.round(pos52*100)}%), dp ${isNaN(dp)?'n/a':dp.toFixed(2)}%`);
        if (pos52 <= thr.nearLow && !isNaN(dp) && dp>=thr.bounceDp) signals.oversoldBounce.push(`${t.symbol}: bounce ${dp.toFixed(2)}% near lows`);
      }

      if (qty && price){
        const plPct = (!isNaN(avg) && avg>0) ? ((price-avg)/avg)*100 : NaN;
        const pos52 = (!isNaN(w52h) && !isNaN(w52l) && w52h>w52l) ? (price-w52l)/(w52h-w52l) : NaN;
        // Heuristics
        if (!isNaN(plPct) && plPct > 12 && (!isNaN(dp) && dp < -0.3 || (!isNaN(pos52) && pos52>0.9))){
          sell.push(`${t.symbol}: +${plPct.toFixed(1)}% vs avg; consider trimming near strength${!isNaN(pos52)?` (52w ${Math.round(pos52*100)}%)`:''}.`);
        } else if (!isNaN(plPct) && plPct < -8 && (!isNaN(pos52) && pos52<0.25) && (!isNaN(dp) && dp>-0.2)){
          buy.push(`${t.symbol}: ${plPct.toFixed(1)}% below avg near 52w lows; consider adding on stabilization.`);
        } else if (!isNaN(plPct)){
          hold.push(`${t.symbol}: P/L ${plPct>=0?'+':''}${plPct.toFixed(1)}%; ${!isNaN(dp)?`daily ${dp.toFixed(2)}%`:'no daily'}; ${!isNaN(pos52)?`52w ${Math.round(pos52*100)}%`:'52w n/a'}.`);
        }
        // Mean reversion tags
        if (!isNaN(dp)){
          if (dp <= -thr.meanDp) signals.meanRevLong.push(`${t.symbol}: dp ${dp.toFixed(2)}% (potential snapback)`);
          if (dp >= thr.meanDp) signals.meanRevShort.push(`${t.symbol}: dp ${dp.toFixed(2)}% (overextended)`);
        }
      }
    }

    // Sector view
    const sectorDown = [];
    for (const s of sectors){
      const st = sectorStats.get(s.id); if (!st || !st.n) continue;
      const avg = st.dpSum / st.n; if (avg < -0.3) sectorDown.push({name:s.name, avg});
    }
    sectorDown.sort((a,b)=>a.avg-b.avg);

    const marketAvg = cntDp ? (sumDp/cntDp) : NaN;
    const marketMsg = isNaN(marketAvg) ? 'n/a' : `${marketAvg.toFixed(2)}% avg change (${downCount}/${cntDp} down)`;

    return { buy, sell, hold, sectorDown, marketMsg, signals, thr };
  }

  function toNum(x){ const n = Number(x); return isNaN(n)?NaN:n; }

  function renderCopilot(data){
    const esc = (s)=>String(s||'');
    const sec = (title, items)=>`<div class="section"><h4>${esc(title)}</h4>${items.length?items.map(i=>`<div class="item">• ${esc(i)}</div>`).join(''):`<div class="muted">No items</div>`}</div>`;
    const sectors = data.sectorDown.map(s=>`${s.name}: ${s.avg.toFixed(2)}%`).slice(0,6);
    const filters = `
      <div class="copilot-filters">
        <div class="row">
          <label><input type="checkbox" id="cpMomentumLong" checked /> Momentum Long</label>
          <label><input type="checkbox" id="cpMomentumShort" /> Momentum Short</label>
          <label><input type="checkbox" id="cpBreakoutHigh" checked /> Breakout High</label>
          <label><input type="checkbox" id="cpBreakdownLow" /> Breakdown Low</label>
          <label><input type="checkbox" id="cpOversoldBounce" checked /> Oversold Bounce</label>
          <label><input type="checkbox" id="cpMeanRevLong" /> Mean Rev Long</label>
          <label><input type="checkbox" id="cpMeanRevShort" /> Mean Rev Short</label>
        </div>
        <div class="row">
          <label>dp% <input type="number" step="0.1" id="cpDp" value="${data.thr.dp}" /></label>
          <label>nearHigh <input type="number" step="0.01" id="cpNearHigh" value="${data.thr.nearHigh}" /></label>
          <label>nearLow <input type="number" step="0.01" id="cpNearLow" value="${data.thr.nearLow}" /></label>
          <label>bounce dp% <input type="number" step="0.1" id="cpBounceDp" value="${data.thr.bounceDp}" /></label>
          <label>mean dp% <input type="number" step="0.1" id="cpMeanDp" value="${data.thr.meanDp}" /></label>
        </div>
        <div class="form-actions"><button type="button" id="cpApply" class="btn btn-primary">Apply</button></div>
      </div>`;
    const results = renderCopilotResults(data, gatherCopilotFilters());
    return filters + results + [
      sec('Suggested Sells (trim profits)', data.sell),
      sec('Suggested Buys (near 52w lows)', data.buy),
      sec('Holds (no strong signal)', data.hold),
      sec('Sectors Weak Today', sectors),
      sec('Market Snapshot', [data.marketMsg])
    ].join('');
  }

  function renderCopilotResults(data, f){
    const esc = (s)=>String(s||'');
    const sec = (title, items)=>`<div class="section"><h4>${esc(title)}</h4>${items.length?items.map(i=>`<div class="item">• ${esc(i)}</div>`).join(''):`<div class="muted">No items</div>`}</div>`;
    const blocks = [];
    if (f.momentumLong) blocks.push(sec('Momentum Long', data.signals.momentumLong));
    if (f.momentumShort) blocks.push(sec('Momentum Short', data.signals.momentumShort));
    if (f.breakoutHigh) blocks.push(sec('Breakout High', data.signals.breakoutHigh));
    if (f.breakdownLow) blocks.push(sec('Breakdown Low', data.signals.breakdownLow));
    if (f.oversoldBounce) blocks.push(sec('Oversold Bounce', data.signals.oversoldBounce));
    if (f.meanRevLong) blocks.push(sec('Mean Reversion Long', data.signals.meanRevLong));
    if (f.meanRevShort) blocks.push(sec('Mean Reversion Short', data.signals.meanRevShort));
    return `<div id="cpResults">${blocks.join('')}</div>`;
  }

  function gatherCopilotFilters(){
    const g = id => document.getElementById(id);
    return {
      momentumLong: g('cpMomentumLong')?.checked ?? true,
      momentumShort: g('cpMomentumShort')?.checked ?? false,
      breakoutHigh: g('cpBreakoutHigh')?.checked ?? true,
      breakdownLow: g('cpBreakdownLow')?.checked ?? false,
      oversoldBounce: g('cpOversoldBounce')?.checked ?? true,
      meanRevLong: g('cpMeanRevLong')?.checked ?? false,
      meanRevShort: g('cpMeanRevShort')?.checked ?? false,
      dp: Number(g('cpDp')?.value ?? 1.0),
      nearHigh: Number(g('cpNearHigh')?.value ?? 0.95),
      nearLow: Number(g('cpNearLow')?.value ?? 0.05),
      bounceDp: Number(g('cpBounceDp')?.value ?? 0.4),
      meanDp: Number(g('cpMeanDp')?.value ?? 1.0),
    };
  }

  function wireCopilotFilters(data){
    const apply = document.getElementById('cpApply');
    if (apply){
      apply.addEventListener('click', async () => {
        const f = gatherCopilotFilters();
        // Recompute signals using thresholds
        const fresh = await generateCopilotInsights({ dp: f.dp, nearHigh: f.nearHigh, nearLow: f.nearLow, bounceDp: f.bounceDp, meanDp: f.meanDp });
        const merged = Object.assign({}, fresh, { thr: fresh.thr });
        const results = renderCopilotResults(merged, f);
        const container = document.getElementById('cpResults');
        if (container) container.outerHTML = results;
      });
    }
  }

  // Single-ticker refresh helper
  async function refreshSingleTicker(t){
    try {
      const qres = await apiFetch('/api/quotes', { method: 'POST', body: JSON.stringify({ symbols: [t.symbol] }) });
      const qcache = loadLS(LS.quotes, { data: {} });
      qcache.data = Object.assign(qcache.data || {}, qres.quotes || {});
      saveLS(LS.quotes, qcache);
      const tres = await apiFetch('/api/tickers/?id=' + encodeURIComponent(t.id));
      const updated = (tres.tickers || [])[0];
      if (updated){
        const tcache = loadLS(LS.tickers, { data: [] });
        const idx = (tcache.data || []).findIndex(x => x.id === t.id);
        if (idx >= 0) tcache.data[idx] = updated; else (tcache.data || []).push(updated);
        saveLS(LS.tickers, tcache);
      }
      renderHeatmap(loadLS(LS.sectors,{data:[]}).data, loadLS(LS.tickers,{data:[]}).data, loadLS(LS.quotes,{data:{}}).data);
    } catch(e){ console.warn('refreshSingleTicker failed', e); }
  }

  // In-modal symbol autocomplete + auto company fill
  (function(){
    if (!formTicker) return;
    const symInput = formTicker.symbol;
    let timer = null;
    function renderSymbolSuggestions(results){
      if (!symbolSuggest) return;
      const items = (results || []).slice(0, 15).map(r => `
        <div class="item" data-sym="${r.symbol}" data-name="${r.description}">
          <strong>${r.symbol}</strong> <span class="muted">${r.description || ''}</span>
        </div>`).join('');
      symbolSuggest.innerHTML = items;
      symbolSuggest.hidden = !items;
    }
    async function fetchSuggestions(q){
      if (!q) { if (symbolSuggest){ symbolSuggest.hidden = true; symbolSuggest.innerHTML = ''; } return; }
      try {
        const res = await apiFetch('/api/search?q=' + encodeURIComponent(q));
        renderSymbolSuggestions(res.results || []);
      } catch(e){ symbolSuggest.hidden = true; }
    }
    symInput.addEventListener('input', () => {
      symInput.value = symInput.value.toUpperCase();
      if (timer) clearTimeout(timer);
      const q = symInput.value.trim();
      timer = setTimeout(() => fetchSuggestions(q), 250);
    });
    if (symbolSuggest){
      symbolSuggest.addEventListener('click', (e) => {
        const it = e.target.closest('.item'); if (!it) return;
        const sym = it.getAttribute('data-sym') || '';
        const name = it.getAttribute('data-name') || '';
        symInput.value = sym;
        if (formTicker.company_name && (!formTicker.company_name.value || formTicker.company_name.value.length < 2)){
          formTicker.company_name.value = name;
        }
        symbolSuggest.hidden = true;
        symbolSuggest.innerHTML = '';
      });
    }
    // On blur, if company blank, try to auto-populate from search
    symInput.addEventListener('blur', () => {
      setTimeout(async () => {
        if (!formTicker.company_name || formTicker.company_name.value.trim()) return;
        const sym = symInput.value.trim(); if (!sym) return;
        try {
          const res = await apiFetch('/api/search?q=' + encodeURIComponent(sym));
          const results = res.results || [];
          const exact = results.find(r => r.symbol === sym);
          const pick = exact || results[0];
          if (pick && pick.description){ formTicker.company_name.value = pick.description; }
        } catch(e){}
      }, 180);
    });
  })();

  // ========== Modal: click-outside to close with unsaved guard ==========
  function attachDirtyTracking(form){
    if (!form) return;
    form.dataset.dirty = form.dataset.dirty || '0';
    const mark = () => { form.dataset.dirty = '1'; };
    form.addEventListener('input', mark);
    form.addEventListener('change', mark);
  }
  function promptCloseModal(modal){
    if (!modal) return;
    const form = modal.querySelector('form');
    if (form && form.dataset.dirty === '1'){
      if (confirm('You have unsaved changes. Save before closing?')){ try { form.requestSubmit(); } catch(_){} return; }
    }
    closeModal(modal);
  }
  // track forms
  attachDirtyTracking(formSector);
  attachDirtyTracking(formTicker);
  attachDirtyTracking(formLot);
  attachDirtyTracking(formMoveTicker);
  attachDirtyTracking(formColors);
  // outside click
  document.querySelectorAll('.modal').forEach(m => {
    m.addEventListener('mousedown', (e) => { if (e.target === m) promptCloseModal(m); });
  });
  // ESC close
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape'){
      const open = Array.from(document.querySelectorAll('.modal')).find(x => !x.hasAttribute('hidden'));
      if (open) promptCloseModal(open);
    }
  });

  // Move Ticker modal + update helpers
  function openMoveTickerModal(t){
    const sectors = loadLS(LS.sectors, {data:[]}).data || [];
    if (selectMoveSector){
      selectMoveSector.innerHTML = sectors.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
      selectMoveSector.value = String(t.sector_id);
    }
    if (moveTickerId) moveTickerId.value = String(t.id);
    if (modalMoveTicker) openModal(modalMoveTicker);
  }

  async function moveTickerToSector(t, sectorId){
    const payload = {
      id: t.id,
      symbol: t.symbol,
      company_name: t.company_name || '',
      sector: Number(sectorId),
      security_type: t.security_type || 'Common Stock',
    };
    try {
      const res = await apiFetch('/api/tickers/', { method: 'PUT', body: JSON.stringify(payload) });
      const tickers = loadLS(LS.tickers, {data:[]}).data || [];
      const idx = tickers.findIndex(x => x.id === t.id);
      if (idx >= 0) tickers[idx] = res.ticker; else tickers.push(res.ticker);
      saveLS(LS.tickers, { ts: Date.now(), data: tickers });
      renderHeatmap(loadLS(LS.sectors,{data:[]}).data, tickers, loadLS(LS.quotes,{data:{}}).data);
    } catch(e){ alert('Failed to move ticker: ' + (e.message || '')); }
  }

  if (formMoveTicker){
    formMoveTicker.addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = Number(moveTickerId && moveTickerId.value);
      const t = (loadLS(LS.tickers, {data:[]}).data || []).find(x => x.id === id);
      if (!t) { if (modalMoveTicker) closeModal(modalMoveTicker); return; }
      await moveTickerToSector(t, Number(selectMoveSector.value));
      try { e.target.dataset.dirty = '0'; } catch(_){}
      if (modalMoveTicker) closeModal(modalMoveTicker);
    });
  }

  // Add Lot / Manage Lots buttons inside Move modal
  if (btnMoveAddLot){
    btnMoveAddLot.addEventListener('click', async () => {
      try {
        const id = Number(moveTickerId && moveTickerId.value);
        await ensureTickersLoaded(true);
        const t = (loadLS(LS.tickers, {data:[]}).data || []).find(x => x.id === id);
        if (!t) return;
        // Open Add Lot form preselected
        if (selectLotTicker){ selectLotTicker.value = String(t.id); }
        if (formLot){ formLot.reset(); }
        if (modalMoveTicker) closeModal(modalMoveTicker);
        if (modalLotForm){ modalLotTitle.textContent = 'Add Lot'; openModal(modalLotForm); }
      } catch(_){}
    });
  }
  if (btnMoveManageLots){
    btnMoveManageLots.addEventListener('click', async () => {
      try {
        const id = Number(moveTickerId && moveTickerId.value);
        if (modalMoveTicker) closeModal(modalMoveTicker);
        lotsTickerFilter.value = String(id);
        openModal(modalLots);
        loadLots();
      } catch(_){}
    });
  }
  // Color pickers for tile backgrounds
  (function(){
    if (!colorGain || !colorFlat || !colorLoss) return;
    const COLORS_KEY = 'hm.tileColors.v1';
    function applyColors(c){
      const root = document.documentElement;
      if (c.gain) root.style.setProperty('--tile-green', c.gain);
      if (c.flat) root.style.setProperty('--tile-neutral', c.flat);
      if (c.loss) root.style.setProperty('--tile-red', c.loss);
    }
    const saved = loadLS(COLORS_KEY, null);
    if (saved){
      colorGain.value = saved.gain || colorGain.value;
      colorFlat.value = saved.flat || colorFlat.value;
      colorLoss.value = saved.loss || colorLoss.value;
      applyColors(saved);
    }
    function save(){
      const c = { gain: colorGain.value, flat: colorFlat.value, loss: colorLoss.value };
      saveLS(COLORS_KEY, c);
      applyColors(c);
    }
    // live preview
    colorGain.addEventListener('input', () => applyColors({gain: colorGain.value}));
    colorFlat.addEventListener('input', () => applyColors({flat: colorFlat.value}));
    colorLoss.addEventListener('input', () => applyColors({loss: colorLoss.value}));
    if (formColors) formColors.addEventListener('submit', (e) => { e.preventDefault(); save(); try { e.target.dataset.dirty='0'; } catch(_){} if (modalColors) closeModal(modalColors); });
  })();
})();


