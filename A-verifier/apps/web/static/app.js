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

function formatPrice(value) {
  if (value === null || value === undefined) return "Prix indisponible";
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
  }).format(value);
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

async function searchProducts() {
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
      if (!appState.selectedProductId) {
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
      <button class="result-card ${isSelected ? "is-selected" : ""}" data-product-id="${product.product_id}">
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
      </button>
    `;
  }).join("");

  document.querySelectorAll("[data-product-id]").forEach((button) => {
    button.addEventListener("click", () => selectProduct(button.dataset.productId));
  });
}

function renderSearchMerchantChips(product) {
  const merchants = product.merchants || [];
  return merchants.map((merchant) => `
    <span class="merchant-chip ${merchantClass(merchant.merchant_slug)}">${merchant.merchant_name}</span>
  `).join("");
}

async function selectProduct(productId) {
  appState.selectedProductId = productId;
  renderResults(appState.products);

  const product = appState.products.find((item) => item.product_id === productId);
  detailPanel.innerHTML = `
    <div class="detail-content">
      <div class="skeleton"></div>
    </div>
  `;

  try {
    const response = await fetch(`/products/${productId}/offers`);
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    renderDetail(product, data.offers);
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

      <div class="offers-head">
        <h3>Offres marchands</h3>
        <span>${sortedOffers.length} ${sortedOffers.length > 1 ? "offres" : "offre"}</span>
      </div>

      <div class="offer-list">
        ${sortedOffers.map((offer, index) => renderOffer(offer, index === 0)).join("")}
      </div>
    </div>
  `;
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

form.addEventListener("submit", (event) => {
  event.preventDefault();
  appState.selectedProductId = null;
  searchProducts();
});

applyFilters.addEventListener("click", () => {
  appState.selectedProductId = null;
  searchProducts();
});

merchantFilters.forEach((button) => {
  button.addEventListener("click", () => {
    const nextMerchant = button.dataset.merchant;
    appState.merchant = appState.merchant === nextMerchant ? null : nextMerchant;
    appState.selectedProductId = null;
    searchProducts();
  });
});

function renderMerchantFilters() {
  merchantFilters.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.merchant === appState.merchant);
  });
}

searchProducts();
