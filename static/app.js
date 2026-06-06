/**
 * Comparador de Precios — Frontend Logic
 * Handles authentication, product search, and results rendering.
 */

const API_BASE = '';
let accessCode = '';
let supermercados = {};
let selectedSupers = new Set();

// ─── DOM Elements ───────────────────────────────────────────────────

const authOverlay    = document.getElementById('auth-overlay');
const authInput      = document.getElementById('auth-code-input');
const authBtn        = document.getElementById('auth-btn');
const authError      = document.getElementById('auth-error');
const appContainer   = document.getElementById('app-container');
const productsInput  = document.getElementById('products-input');
const superSelector  = document.getElementById('super-selector');
const searchBtn      = document.getElementById('search-btn');
const loadingEl      = document.getElementById('loading');
const loadingSubtext = document.getElementById('loading-subtext');
const errorMessage   = document.getElementById('error-message');
const resultsSection = document.getElementById('results-section');
const summaryGrid    = document.getElementById('summary-grid');
const productsDetail = document.getElementById('products-detail');
const timestampEl    = document.getElementById('timestamp');


// ─── Authentication ─────────────────────────────────────────────────

async function authenticate(code) {
  try {
    const res = await fetch(`${API_BASE}/api/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });

    const data = await res.json();
    if (data.success) {
      accessCode = code;
      authOverlay.classList.add('hidden');
      appContainer.style.display = 'block';
      await loadSupermercados();
      productsInput.focus();
    } else {
      authError.textContent = 'Código incorrecto. Intentá de nuevo.';
      authInput.style.borderColor = '#f43f5e';
      setTimeout(() => {
        authInput.style.borderColor = '';
      }, 2000);
    }
  } catch (err) {
    authError.textContent = 'Error de conexión. ¿Está corriendo el servidor?';
  }
}

authBtn.addEventListener('click', () => authenticate(authInput.value));
authInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') authenticate(authInput.value);
  authError.textContent = '';
});


// ─── Load Supermarkets ──────────────────────────────────────────────

async function loadSupermercados() {
  try {
    const res = await fetch(`${API_BASE}/api/supermercados`, {
      headers: { 'X-Access-Code': accessCode },
    });
    supermercados = await res.json();

    // Select all by default
    selectedSupers = new Set(Object.keys(supermercados));
    renderSuperSelector();
  } catch (err) {
    console.error('Error loading supermercados:', err);
  }
}

function renderSuperSelector() {
  superSelector.innerHTML = '';

  for (const [key, info] of Object.entries(supermercados)) {
    const chip = document.createElement('div');
    chip.className = `super-chip ${selectedSupers.has(key) ? 'active' : ''}`;
    chip.dataset.key = key;
    chip.innerHTML = `
      <span class="chip-emoji">${info.logo_emoji}</span>
      <span>${info.nombre}</span>
      <span class="chip-check">${selectedSupers.has(key) ? '✓' : ''}</span>
    `;

    chip.addEventListener('click', () => {
      if (selectedSupers.has(key)) {
        if (selectedSupers.size > 1) {
          selectedSupers.delete(key);
        }
      } else {
        selectedSupers.add(key);
      }
      renderSuperSelector();
    });

    superSelector.appendChild(chip);
  }
}


// ─── Search ─────────────────────────────────────────────────────────

async function buscarPrecios() {
  const rawText = productsInput.value.trim();
  if (!rawText) {
    showError('Ingresá al menos un producto en la lista.');
    return;
  }

  const productos = rawText
    .split('\n')
    .map(line => line.trim())
    .filter(line => line.length > 0);

  if (productos.length === 0) {
    showError('Ingresá al menos un producto en la lista.');
    return;
  }

  if (productos.length > 30) {
    showError('Máximo 30 productos por consulta.');
    return;
  }

  hideError();
  setLoading(true);

  try {
    const res = await fetch(`${API_BASE}/api/buscar`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Access-Code': accessCode,
      },
      body: JSON.stringify({
        productos,
        supermercados: Array.from(selectedSupers),
        resultados_por_producto: 3,
      }),
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.error || 'Error del servidor');
    }

    const data = await res.json();
    renderResults(data);

  } catch (err) {
    showError(`Error: ${err.message}`);
  } finally {
    setLoading(false);
  }
}

searchBtn.addEventListener('click', buscarPrecios);
productsInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault();
    buscarPrecios();
  }
});


// ─── Render Results ─────────────────────────────────────────────────

function renderResults(data) {
  const { resultados, resumen, timestamp, supermercados_info } = data;

  // ── Summary Cards ──
  renderSummary(resumen);

  // ── Product Details ──
  renderProductDetails(resultados, supermercados_info);

  // ── Timestamp ──
  timestampEl.textContent = `Última consulta: ${timestamp} · Los precios pueden variar`;

  // ── Show results ──
  resultsSection.classList.remove('hidden');
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderSummary(resumen) {
  summaryGrid.innerHTML = '';

  // Find the maximum number of products found by any supermarket
  let maxFound = 0;
  for (const data of Object.values(resumen)) {
    if (data.encontrados > maxFound) {
      maxFound = data.encontrados;
    }
  }

  // Find cheapest among those that found the maximum number of products
  let minTotal = Infinity;
  let cheapestKey = '';

  if (maxFound > 0) {
    for (const [key, data] of Object.entries(resumen)) {
      if (data.encontrados === maxFound && data.total < minTotal) {
        minTotal = data.total;
        cheapestKey = key;
      }
    }
  }

  // Sort by completeness (found count desc), then by total price (asc)
  const sorted = Object.entries(resumen).sort((a, b) => {
    if (a[1].encontrados !== b[1].encontrados) {
      return b[1].encontrados - a[1].encontrados;
    }
    return a[1].total - b[1].total;
  });

  sorted.forEach(([key, data], index) => {
    const info = data.info;
    const isCheapest = key === cheapestKey && data.encontrados > 0;
    const totalProductos = data.encontrados + data.no_encontrados.length;

    const card = document.createElement('div');
    card.className = `summary-card ${isCheapest ? 'cheapest' : ''}`;
    card.style.setProperty('--card-color', info.color);
    card.style.animationDelay = `${index * 0.1}s`;

    const noEncontradosList = data.no_encontrados.length > 0
      ? `<div style="margin-top:8px; font-size:11px; color:var(--text-muted);">
           No encontrados: ${data.no_encontrados.join(', ')}
         </div>`
      : '';

    card.innerHTML = `
      <div class="super-name">
        <span class="super-emoji">${info.logo_emoji}</span>
        ${info.nombre}
      </div>
      <div class="total-price">
        ${data.encontrados > 0 ? '$' + formatPrice(data.total) : 'Sin resultados'}
      </div>
      <div class="found-count">
        ${data.encontrados} de ${totalProductos} productos encontrados
      </div>
      <div class="cheapest-badge">
        ✨ Más barato
      </div>
      ${noEncontradosList}
    `;

    summaryGrid.appendChild(card);
  });
}

function renderProductDetails(resultados, supermercadosInfo) {
  productsDetail.innerHTML = '';

  for (const [query, porSuper] of Object.entries(resultados)) {
    const group = document.createElement('div');
    group.className = 'product-group';

    group.innerHTML = `
      <div class="product-group-title">
        🔍 Resultados para: <span class="query-text">"${escapeHTML(query)}"</span>
      </div>
    `;

    const grid = document.createElement('div');
    grid.className = 'product-results-grid';

    let hasAnyProduct = false;

    for (const [superKey, data] of Object.entries(porSuper)) {
      const productos = data.productos || [];
      const info = supermercadosInfo[superKey] || {};

      if (productos.length === 0) {
        continue;
      }

      hasAnyProduct = true;

      productos.forEach(producto => {
        const card = createProductCard(producto, info);
        grid.appendChild(card);
      });
    }

    if (!hasAnyProduct) {
      grid.innerHTML = `
        <div class="not-found-msg" style="grid-column: 1 / -1;">
          No se encontraron resultados para "${escapeHTML(query)}" en ningún supermercado
        </div>
      `;
    }

    group.appendChild(grid);
    productsDetail.appendChild(group);
  }
}

function createProductCard(producto, superInfo) {
  const card = document.createElement('div');
  card.className = 'product-card';

  const imgHTML = producto.imagen_url
    ? `<img class="product-img" src="${producto.imagen_url}" alt="" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
       <div class="product-img-placeholder" style="display:none;">📦</div>`
    : `<div class="product-img-placeholder">📦</div>`;

  const promoHTML = producto.tiene_promo
    ? `<span class="original-price">$${formatPrice(producto.precio)}</span>
       <span class="promo-tag">${producto.promo_descripcion || 'PROMO'}</span>`
    : '';

  const brandHTML = producto.marca
    ? `<div class="product-brand">${escapeHTML(producto.marca)}</div>`
    : '';

  const linkWrapper = producto.url_producto
    ? `<a href="${producto.url_producto}" target="_blank" rel="noopener" style="text-decoration:none; color:inherit;">`
    : '';
  const linkClose = producto.url_producto ? '</a>' : '';

  card.innerHTML = `
    ${imgHTML}
    <div class="product-info">
      <div class="product-super-tag">
        ${superInfo.logo_emoji || '🛒'} ${superInfo.nombre || producto.supermercado}
      </div>
      ${linkWrapper}
      <div class="product-name">${escapeHTML(producto.nombre)}</div>
      ${linkClose}
      ${brandHTML}
      <div class="product-pricing">
        <span class="current-price">$${formatPrice(producto.precio_final)}</span>
        ${promoHTML}
      </div>
    </div>
  `;

  return card;
}


// ─── UI Helpers ─────────────────────────────────────────────────────

function setLoading(active) {
  loadingEl.classList.toggle('active', active);
  searchBtn.disabled = active;
  if (active) {
    resultsSection.classList.add('hidden');
    searchBtn.innerHTML = `<div class="spinner"></div> Buscando...`;

    // Rotate loading messages
    const messages = [
      'Consultando Carrefour...',
      'Consultando Disco...',
      'Consultando Super Mami...',
      'Consultando Cordiez...',
      'Comparando precios...',
    ];
    let i = 0;
    window._loadingInterval = setInterval(() => {
      loadingSubtext.textContent = messages[i % messages.length];
      i++;
    }, 2000);
  } else {
    searchBtn.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      Buscar precios
    `;
    clearInterval(window._loadingInterval);
  }
}

function showError(msg) {
  errorMessage.textContent = msg;
  errorMessage.classList.add('visible');
}

function hideError() {
  errorMessage.textContent = '';
  errorMessage.classList.remove('visible');
}

function formatPrice(price) {
  if (!price && price !== 0) return '—';
  return new Intl.NumberFormat('es-AR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
