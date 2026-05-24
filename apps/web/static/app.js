const form = document.querySelector("#search-form");
const input = document.querySelector("#search-input");
const brandFilter = document.querySelector("#brand-filter");
const minPriceFilter = document.querySelector("#min-price-filter");
const maxPriceFilter = document.querySelector("#max-price-filter");
const applyFilters = document.querySelector("#apply-filters");
const resultTitle = document.querySelector("#result-title");
const resultCount = document.querySelector("#result-count");
const activeQuery = document.querySelector("#active-query");
const state = document.querySelector("#state");
const resultList = document.querySelector("#result-list");
const detailPanel = document.querySelector("#detail-panel");
const merchantFilters = document.querySelectorAll(".merchant-filter");

const appState = {
  selectedProductId: null,
  products: [],
  merchant: null,
};

function productDetailPath(productId) {
  return `/ui/product/${encodeURIComponent(productId)}`;
}

function currentRouteProductId() {
  const match = window.location.pathname.match(/^\/ui\/product\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function resetRouteToSearch() {
  if (currentRouteProductId()) {
    history.pushState({}, "", "/ui/");
  }
}

function formatPrice(value) {
  if (value === null || value === undefined) return "Prix indisponible";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
  }).format(value);
}

function formatSignedPrice(value) {
  if (value === null || value === undefined) return "N/A";
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatPrice(value)}`;
}

function formatShortDate(value) {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatDay(value) {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(value));
}

function merchantClass(value) {
  const normalized = (value || "").toLowerCase();
  if (normalized.includes("ldlc")) return "merchant-chip--ldlc";
  if (normalized.includes("materiel")) return "merchant-chip--materiel";
  return "merchant-chip--unknown";
}

function availabilityLabel(value) {
  const labels = {
    in_stock: "En stock",
    out_of_stock: "Rupture",
    preorder: "Précommande",
    unknown: "Disponibilité inconnue",
  };
  return labels[value] || value || "Disponibilité inconnue";
}

function productIcon(product) {
  const text = `${product.title} ${product.category_path || ""}`.toLowerCase();
  if (text.includes("lenovo") || text.includes("portable") || text.includes("pc")) return "💻";
  if (text.includes("tv") || text.includes("television")) return "📺";
  return "🎧";
}

function setStateCard(kind, title, message) {
  state.innerHTML = `
    <div class="state-card state-card--${kind}">
      <strong>${title}</strong>
      <span>${message}</span>
    </div>
  `;
}

function setLoading() {
  state.innerHTML = "";
  resultList.innerHTML = `
    <div class="skeleton"></div>
    <div class="skeleton"></div>
    <div class="skeleton"></div>
  `;
}

function clearMessages() {
  state.innerHTML = "";
}

function buildSearchParams() {
  const params = new URLSearchParams();
  params.set("q", input.value.trim() || "xiaomi");
  params.set("size", "20");

  const brand = brandFilter.value.trim();
  const minPrice = minPriceFilter.value.trim();
  const maxPrice = maxPriceFilter.value.trim();

  if (brand) params.set("brand", brand.toLowerCase());
  if (minPrice) params.set("min_price", minPrice);
  if (maxPrice) params.set("max_price", maxPrice);
  if (appState.merchant) params.set("merchant", appState.merchant);

  return params;
}

async function searchProducts(options = {}) {
  const { autoSelect = true } = options;
  const params = buildSearchParams();
  const query = params.get("q");
  resultTitle.textContent = `Résultats pour « ${query} »`;
  activeQuery.textContent = `query: ${query}`;
  renderMerchantFilters();
  setLoading();

  try {
    const response = await fetch(`/search/products?${params.toString()}`);
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();

    appState.products = data.items;
    resultCount.textContent = `${data.total} ${data.total > 1 ? "produits" : "produit"}`;
    renderResults(data.items);

    if (data.items.length === 0) {
      setStateCard("empty", "Aucun résultat", "Essaie une autre marque, une référence MPN ou un budget plus large.");
    } else {
      clearMessages();
      if (autoSelect && !appState.selectedProductId) {
        selectProduct(data.items[0].product_id);
      }
    }
  } catch (error) {
    resultCount.textContent = "Erreur";
    resultList.innerHTML = "";
    setStateCard("error", "API indisponible", "Vérifie que le backend tourne sur http://localhost:8000.");
  }
}

function renderResults(products) {
  resultList.innerHTML = products.map((product) => {
    const isSelected = product.product_id === appState.selectedProductId;
    const hasRange = product.price_min !== product.price_max;
    const merchantCount = (product.merchants || product.merchant_ids || []).length;
    const label = merchantCount > 1 ? `${merchantCount} marchands` : `${merchantCount} marchand`;

    return `
      <a class="result-card ${isSelected ? "is-selected" : ""}" href="${productDetailPath(product.product_id)}" data-product-id="${product.product_id}">
        <span class="thumb" aria-hidden="true">${productIcon(product)}</span>
        <span class="result-main">
          <span class="result-title">${product.title}</span>
          <span class="meta-row">
            ${product.brand ? `<span class="brand-chip">${product.brand}</span>` : ""}
            <span class="stock-badge">En stock</span>
            <span class="range-badge">${label}</span>
            ${renderSearchMerchantChips(product)}
          </span>
        </span>
        <span class="price-box">
          <span class="price-label">${hasRange ? "A partir de" : "Prix"}</span>
          <span class="price-amount">${formatPrice(product.price_min)}</span>
          ${hasRange ? `<span class="price-range">jusqu'a ${formatPrice(product.price_max)}</span>` : ""}
        </span>
      </a>
    `;
  }).join("");

  document.querySelectorAll("[data-product-id]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      selectProduct(link.dataset.productId);
    });
  });
}

function renderSearchMerchantChips(product) {
  const merchants = product.merchants || [];
  return merchants.map((merchant) => `
    <span class="merchant-chip ${merchantClass(merchant.merchant_slug)}">${merchant.merchant_name}</span>
  `).join("");
}

async function selectProduct(productId, options = {}) {
  const { updateUrl = true } = options;
  appState.selectedProductId = productId;
  if (updateUrl && currentRouteProductId() !== productId) {
    history.pushState({ productId }, "", productDetailPath(productId));
  }
  renderResults(appState.products);

  const product = appState.products.find((item) => item.product_id === productId) || {};
  detailPanel.innerHTML = `
    <div class="detail-content">
      <div class="skeleton"></div>
    </div>
  `;

  try {
    const response = await fetch(`/products/${productId}`);
    if (!response.ok) throw new Error(`API ${response.status}`);
    const detail = await response.json();
    renderDetail({ ...product, ...detail }, detail.offers);
  } catch (error) {
    detailPanel.innerHTML = `
      <div class="empty-detail">
        <div class="empty-icon">!</div>
        <h2>Offres indisponibles</h2>
        <p>Impossible de charger les offres pour ce produit.</p>
      </div>
    `;
  }
}

async function loadProductRoute(productId) {
  appState.selectedProductId = productId;
  renderMerchantFilters();
  setLoading();
  resultTitle.textContent = "Détail produit";
  resultCount.textContent = "Chargement";
  activeQuery.textContent = `produit: ${productId.slice(0, 8)}`;
  detailPanel.innerHTML = `
    <div class="detail-content">
      <div class="skeleton"></div>
    </div>
  `;

  try {
    const response = await fetch(`/products/${encodeURIComponent(productId)}`);
    if (!response.ok) throw new Error(`API ${response.status}`);
    const detail = await response.json();
    const querySeed = detail.brand || detail.title.split(/\s+/)[0] || "xiaomi";

    input.value = querySeed;
    renderDetail(detail, detail.offers || []);
    await searchProducts({ autoSelect: false });
  } catch (error) {
    resultCount.textContent = "Erreur";
    resultList.innerHTML = "";
    setStateCard("error", "Produit introuvable", "Vérifie l'UUID ou relance une recherche.");
    detailPanel.innerHTML = `
      <div class="empty-detail">
        <div class="empty-icon">!</div>
        <h2>Produit introuvable</h2>
        <p>Ce détail produit n'est pas disponible.</p>
      </div>
    `;
  }
}

function renderDetail(product, offers) {
  const sortedOffers = [...offers].sort((a, b) => {
    const totalA = a.price_amount + a.shipping_amount;
    const totalB = b.price_amount + b.shipping_amount;
    return totalA - totalB;
  });

  const bestTotal = sortedOffers.length
    ? sortedOffers[0].price_amount + sortedOffers[0].shipping_amount
    : product.price_min;

  detailPanel.innerHTML = `
    <div class="detail-content">
      <section class="detail-hero">
        <span class="thumb" aria-hidden="true">${productIcon(product)}</span>
        <div>
          <p class="eyebrow">${product.brand || "Produit"}</p>
          <h2>${product.title}</h2>
          <div class="meta-row">
            <span class="range-badge">${product.canonical_key}</span>
            <span class="stock-badge">En stock</span>
          </div>
          <div class="detail-price">${formatPrice(bestTotal)}</div>
          <div class="price-range">Fourchette ${formatPrice(product.price_min)} - ${formatPrice(product.price_max)}</div>
        </div>
      </section>

      <section class="price-history" id="price-history-panel">
        <div class="offers-head">
          <h3>Historique des prix</h3>
          <span id="price-history-count">Chargement</span>
        </div>
        <div class="price-history-body" id="price-history-body">
          <div class="skeleton skeleton--compact"></div>
        </div>
      </section>

      <div class="offers-head">
        <h3>Offres marchands</h3>
        <span>${sortedOffers.length} ${sortedOffers.length > 1 ? "offres" : "offre"}</span>
      </div>

      <div class="offer-list">
        ${sortedOffers.map((offer, index) => renderOffer(offer, index === 0)).join("")}
      </div>
    </div>
  `;

  renderPriceHistory(product.product_id || appState.selectedProductId);
}

function renderOffer(offer, isBest) {
  const total = offer.price_amount + offer.shipping_amount;
  const merchantName = offer.merchant_name || offer.merchant_slug || offer.merchant_id.slice(0, 8);
  const merchantStyleKey = offer.merchant_slug || merchantName;

  return `
    <article class="offer-card ${isBest ? "is-best" : ""}">
      <div class="offer-top">
        <span class="merchant-chip ${merchantClass(merchantStyleKey)}">${merchantName}</span>
        ${isBest ? `<span class="best-badge">Meilleur prix</span>` : `<span class="stock-badge">${availabilityLabel(offer.availability)}</span>`}
      </div>
      <div class="offer-money">
        <div>
          <div class="money-label">Produit</div>
          <div class="money-value">${formatPrice(offer.price_amount)}</div>
        </div>
        <div>
          <div class="money-label">Livraison</div>
          <div class="money-value">${formatPrice(offer.shipping_amount)}</div>
        </div>
        <div>
          <div class="money-label">Total</div>
          <div class="money-value total">${formatPrice(total)}</div>
        </div>
      </div>
      <a class="offer-button" href="${offer.product_url}" target="_blank" rel="noreferrer">
        Voir l'offre
      </a>
    </article>
  `;
}

async function renderPriceHistory(productId) {
  const body = document.querySelector("#price-history-body");
  const count = document.querySelector("#price-history-count");
  if (!body || !count || !productId) return;

  try {
    const response = await fetch(`/products/${encodeURIComponent(productId)}/price-history`);
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    if (appState.selectedProductId !== productId) return;

    const points = data.points || [];
    count.textContent = `${points.length} ${points.length > 1 ? "points" : "point"}`;
    body.innerHTML = renderPriceHistoryBody(points);
  } catch (error) {
    count.textContent = "Erreur";
    body.innerHTML = `<div class="history-empty">Historique indisponible.</div>`;
  }
}

function renderPriceHistoryBody(points) {
  if (points.length === 0) {
    return `<div class="history-empty">Aucun relevé de prix pour le moment.</div>`;
  }

  const totals = points.map((point) => point.total_amount);
  const best = Math.min(...totals);
  const latestByMerchant = latestPointsByMerchant(points);
  const currentBest = Math.min(...latestByMerchant.map((point) => point.total_amount));
  const change = latestPriceChange(points);

  return `
    <div class="history-metrics">
      <div>
        <span>Meilleur actuel</span>
        <strong>${formatPrice(currentBest)}</strong>
      </div>
      <div>
        <span>Plus bas observé</span>
        <strong>${formatPrice(best)}</strong>
      </div>
      <div>
        <span>Dernière variation</span>
        <strong class="${changeClass(change)}">${change ? formatSignedPrice(change.amount) : "N/A"}</strong>
      </div>
    </div>
    <div class="history-bars" aria-label="Historique des prix">
      ${renderHistoryBars(points)}
    </div>
    <div class="history-list">
      ${points.slice(-5).reverse().map(renderHistoryPoint).join("")}
    </div>
  `;
}

function latestPointsByMerchant(points) {
  const byMerchant = new Map();
  points.forEach((point) => {
    byMerchant.set(point.merchant_id, point);
  });
  return [...byMerchant.values()];
}

function latestPriceChange(points) {
  const byOffer = new Map();
  points.forEach((point) => {
    const group = byOffer.get(point.offer_id) || [];
    group.push(point);
    byOffer.set(point.offer_id, group);
  });

  return [...byOffer.values()]
    .filter((group) => group.length > 1)
    .map((group) => {
      const previous = group[group.length - 2];
      const latest = group[group.length - 1];
      return {
        amount: latest.total_amount - previous.total_amount,
        capturedAt: latest.captured_at,
      };
    })
    .sort((a, b) => new Date(b.capturedAt) - new Date(a.capturedAt))[0] || null;
}

function changeClass(change) {
  if (!change || change.amount === 0) return "history-change";
  return change.amount < 0 ? "history-change is-good" : "history-change is-bad";
}

function renderHistoryBars(points) {
  const visiblePoints = points.slice(-8);
  const totals = visiblePoints.map((point) => point.total_amount);
  const min = Math.min(...totals);
  const max = Math.max(...totals);
  const spread = Math.max(max - min, 1);

  return visiblePoints.map((point) => {
    const height = 26 + ((point.total_amount - min) / spread) * 54;
    return `
      <div class="history-bar" title="${point.merchant_name} - ${formatPrice(point.total_amount)}">
        <span style="height: ${height}px"></span>
        <small>${formatDay(point.captured_at)}</small>
      </div>
    `;
  }).join("");
}

function renderHistoryPoint(point) {
  return `
    <div class="history-row">
      <span class="merchant-chip ${merchantClass(point.merchant_slug)}">${point.merchant_name}</span>
      <span>${formatShortDate(point.captured_at)}</span>
      <strong>${formatPrice(point.total_amount)}</strong>
    </div>
  `;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  appState.selectedProductId = null;
  resetRouteToSearch();
  searchProducts();
});

applyFilters.addEventListener("click", () => {
  appState.selectedProductId = null;
  resetRouteToSearch();
  searchProducts();
});

merchantFilters.forEach((button) => {
  button.addEventListener("click", () => {
    const nextMerchant = button.dataset.merchant;
    appState.merchant = appState.merchant === nextMerchant ? null : nextMerchant;
    appState.selectedProductId = null;
    resetRouteToSearch();
    searchProducts();
  });
});

function renderMerchantFilters() {
  merchantFilters.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.merchant === appState.merchant);
  });
}

window.addEventListener("popstate", () => {
  const productId = currentRouteProductId();
  if (productId) {
    loadProductRoute(productId);
  } else {
    appState.selectedProductId = null;
    searchProducts();
  }
});

const initialProductId = currentRouteProductId();
if (initialProductId) {
  loadProductRoute(initialProductId);
} else {
  searchProducts();
}
