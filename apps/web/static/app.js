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
const crawlStatus = document.querySelector("#crawl-status");
const crawlRunButtons = document.querySelectorAll("[data-crawl-merchant]");
const merchantFilters = document.querySelectorAll(".merchant-filter");
const topNavLinks = document.querySelectorAll(".top-nav a");
const OPS_ADMIN_TOKEN_STORAGE_KEY = "electronicstar.opsAdminToken";
const CRAWL_MERCHANTS = [
  { slug: "materiel", name: "Materiel.net" },
  { slug: "ldlc", name: "LDLC" },
];

const appState = {
  selectedProductId: null,
  products: [],
  merchant: null,
};

function productDetailPath(productId) {
  return `/ui/product/${encodeURIComponent(productId)}`;
}

function productAbsoluteUrl(productId) {
  return `${window.location.origin}${productDetailPath(productId)}`;
}

function currentRouteProductId() {
  const match = window.location.pathname.match(/^\/ui\/product\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function isDemoRoute() {
  return /^\/ui\/demo\/?$/.test(window.location.pathname);
}

function isOpsRoute() {
  return /^\/ui\/ops\/?$/.test(window.location.pathname);
}

function resetRouteToSearch() {
  if (currentRouteProductId() || isDemoRoute() || isOpsRoute()) {
    history.pushState({}, "", "/ui/");
  }
}

function syncNavigation() {
  topNavLinks.forEach((link) => {
    const targetPath = new URL(link.href, window.location.origin).pathname;
    const isActive = targetPath === "/ui/ops"
      ? isOpsRoute()
      : !isOpsRoute();
    link.classList.toggle("is-active", isActive);
  });
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

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "en cours";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  return `${Math.round(seconds / 60)} min`;
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} o`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} Ko`;
  return `${(value / 1024 / 1024).toFixed(1)} Mo`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function merchantClass(value) {
  const normalized = (value || "").toLowerCase();
  if (normalized.includes("ldlc")) return "merchant-chip--ldlc";
  if (normalized.includes("materiel")) return "merchant-chip--materiel";
  return "merchant-chip--unknown";
}

function merchantDisplayName(slug) {
  return CRAWL_MERCHANTS.find((merchant) => merchant.slug === slug)?.name || slug;
}

function crawlStatusLabel(value) {
  const labels = {
    success: "OK",
    failed: "Erreur",
    running: "En cours",
    queued: "En attente",
  };
  return labels[value] || value || "Inconnu";
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
  syncNavigation();
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
            ${product.is_stale ? `<span class="stale-badge">Crawl ancien</span>` : ""}
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
  syncNavigation();
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

async function loadDemoRoute() {
  syncNavigation();
  appState.selectedProductId = null;
  appState.merchant = null;
  input.value = "lenovo";
  renderMerchantFilters();
  setLoading();
  resultTitle.textContent = "Démo ElectronicStar";
  resultCount.textContent = "Recherche";
  activeQuery.textContent = "demo: meilleur produit comparable";
  detailPanel.innerHTML = `
    <div class="empty-detail">
      <div class="empty-icon">↗</div>
      <h2>Préparation de la démo</h2>
      <p>Recherche du produit avec plusieurs marchands et historique de prix.</p>
    </div>
  `;

  try {
    const response = await fetch("/search/products?q=lenovo&size=10");
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    const product = findDemoProduct(data.items || []);

    if (!product) {
      throw new Error("No demo product");
    }

    history.replaceState({ productId: product.product_id }, "", productDetailPath(product.product_id));
    await loadProductRoute(product.product_id);
  } catch (error) {
    resultCount.textContent = "Erreur";
    resultList.innerHTML = "";
    setStateCard("error", "Démo indisponible", "Relance le seed de demo puis recharge /ui/demo.");
    detailPanel.innerHTML = `
      <div class="empty-detail">
        <div class="empty-icon">!</div>
        <h2>Démo indisponible</h2>
        <p>Aucun produit comparable n'est prêt pour l'instant.</p>
      </div>
    `;
  }
}

function findDemoProduct(products) {
  return products.find((product) => {
    const merchantCount = (product.merchants || product.merchant_ids || []).length;
    return merchantCount > 1;
  }) || products[0] || null;
}

async function loadOpsRoute() {
  syncNavigation();
  appState.selectedProductId = null;
  appState.products = [];
  renderMerchantFilters();
  resultTitle.textContent = "Pilotage des crawls";
  resultCount.textContent = "Ops";
  activeQuery.textContent = "ops: crawls";
  state.innerHTML = "";
  resultList.innerHTML = `<div class="skeleton"></div><div class="skeleton"></div>`;
  detailPanel.innerHTML = `
    <div class="detail-content">
      <div class="skeleton"></div>
    </div>
  `;

  const token = savedOpsAdminToken();
  if (!token) {
    renderOpsLocked("Cle admin requise", "Saisis la cle ops pour consulter les crawls et relancer les marchands.");
    return;
  }

  try {
    const response = await fetch("/ops/crawl-runs?limit=50", {
      headers: opsAdminHeaders(token),
    });
    if (response.status === 401 || response.status === 403) {
      forgetOpsAdminToken();
      renderOpsLocked("Cle admin invalide", "La cle stockee a ete refusee. Saisis une nouvelle cle.");
      return;
    }
    if (!response.ok) throw new Error(`API ${response.status}`);

    const data = await response.json();
    renderOpsDashboard(data.runs || []);
  } catch (error) {
    resultCount.textContent = "Erreur";
    resultList.innerHTML = "";
    setStateCard("error", "Ops indisponible", "Verifie que l'API tourne et que OPS_ADMIN_TOKEN est configure.");
    detailPanel.innerHTML = `
      <div class="empty-detail">
        <div class="empty-icon">!</div>
        <h2>Dashboard indisponible</h2>
        <p>Impossible de charger les statuts de crawl.</p>
      </div>
    `;
  }
}

function renderOpsLocked(title, message) {
  resultCount.textContent = "Verrouille";
  resultList.innerHTML = "";
  setStateCard("empty", title, message);
  detailPanel.innerHTML = `
    <div class="detail-content">
      <section class="detail-hero">
        <span class="thumb" aria-hidden="true">🔐</span>
        <div>
          <p class="eyebrow">Ops securise</p>
          <h2>${title}</h2>
          <p>${message}</p>
          <div class="detail-actions">
            <button class="copy-link-button" id="ops-token-button" type="button">Saisir la cle</button>
          </div>
        </div>
      </section>
    </div>
  `;
  document.querySelector("#ops-token-button")?.addEventListener("click", changeOpsAdminToken);
}

function renderOpsDashboard(runs) {
  const latestRun = runs[0] || null;
  const runningCount = runs.filter((run) => run.status === "running").length;
  const failedCount = runs.filter((run) => run.status === "failed").length;
  const successCount = runs.filter((run) => run.status === "success").length;
  resultCount.textContent = `${runs.length} ${runs.length > 1 ? "runs" : "run"}`;
  clearMessages();

  resultList.innerHTML = `
    <div class="ops-summary">
      <div class="ops-metric"><span>Total</span><strong>${runs.length}</strong></div>
      <div class="ops-metric"><span>En cours</span><strong>${runningCount}</strong></div>
      <div class="ops-metric"><span>Succes</span><strong>${successCount}</strong></div>
      <div class="ops-metric"><span>Erreurs</span><strong>${failedCount}</strong></div>
    </div>
    ${runs.length ? runs.map(renderOpsRunCard).join("") : `<div class="history-empty">Aucun crawl enregistre.</div>`}
  `;

  detailPanel.innerHTML = `
    <div class="detail-content">
      <section class="detail-hero">
        <span class="thumb" aria-hidden="true">⚙️</span>
        <div>
          <p class="eyebrow">Schedulers</p>
          <h2>LDLC & Materiel.net</h2>
          <div class="meta-row">
            ${CRAWL_MERCHANTS.map((merchant) => `
              <span class="merchant-chip ${merchantClass(merchant.slug)}">${merchant.name}</span>
            `).join("")}
            ${latestRun ? `<span class="crawl-status-badge">${crawlStatusLabel(latestRun.status)}</span>` : ""}
          </div>
          <div class="detail-actions">
            ${CRAWL_MERCHANTS.map((merchant) => `
              <button class="crawl-run-button" data-crawl-merchant="${merchant.slug}" type="button">Relancer ${merchant.name}</button>
            `).join("")}
            <button class="copy-link-button" id="ops-export-audit-csv-button" type="button">Exporter CSV</button>
            <button class="copy-link-button" id="ops-refresh-button" type="button">Rafraichir</button>
            <button class="copy-link-button" id="ops-change-token-button" type="button">Changer la cle</button>
          </div>
        </div>
      </section>
      ${latestRun ? renderOpsRunDetail(latestRun) : `<div class="history-empty">Aucun run a detailler.</div>`}
    </div>
  `;

  detailPanel.querySelectorAll("[data-crawl-merchant]").forEach((button) => {
    button.addEventListener("click", triggerCrawlRun);
  });
  document.querySelector("#ops-refresh-button")?.addEventListener("click", () => {
    loadOpsRoute();
    loadCrawlStatus();
  });
  document.querySelector("#ops-export-audit-csv-button")?.addEventListener("click", exportOpsOfferAuditCsv);
  document.querySelector("#ops-change-token-button")?.addEventListener("click", changeOpsAdminToken);
  if (latestRun) {
    renderOpsOfferAudit();
    renderOpsRawDocuments(latestRun.crawl_run_id);
    renderOpsStaleOffers();
  }
}

function renderOpsRunCard(run) {
  return `
    <article class="ops-run-card crawl-run--${run.status}">
      <div class="ops-run-main">
        <div class="ops-run-title">
          <span>${run.merchant_name}</span>
          <span class="crawl-status-badge">${crawlStatusLabel(run.status)}</span>
          <span class="range-badge">${run.run_type}</span>
        </div>
        <div class="ops-run-meta">${formatShortDate(run.started_at)} · ${run.crawl_run_id.slice(0, 8)}</div>
      </div>
      <div class="ops-cell"><span>Items</span><strong>${run.items_scraped}</strong></div>
      <div class="ops-cell"><span>Pages OK</span><strong>${run.pages_ok}</strong></div>
      <div class="ops-cell"><span>Pages KO</span><strong>${run.pages_failed}</strong></div>
      <div class="ops-cell"><span>Duree</span><strong>${formatDuration(run.duration_seconds)}</strong></div>
    </article>
  `;
}

function renderOpsRunDetail(run) {
  return `
    <section class="price-history">
      <div class="offers-head">
        <h3>Dernier run</h3>
        <span>${formatDuration(run.duration_seconds)}</span>
      </div>
      <div class="ops-detail-grid">
        ${renderOpsDetailRow("Statut", crawlStatusLabel(run.status))}
        ${renderOpsDetailRow("Debut", formatShortDate(run.started_at))}
        ${renderOpsDetailRow("Fin", run.ended_at ? formatShortDate(run.ended_at) : "En cours")}
        ${renderOpsDetailRow("Items", String(run.items_scraped))}
        ${renderOpsDetailRow("Pages", `${run.pages_ok} OK / ${run.pages_failed} KO`)}
        ${renderOpsDetailRow("Captcha", `${run.captcha_count} captcha / ${run.blocked_count} blocages`)}
        ${renderOpsDetailRow("Ingestion", run.ingest_enabled ? "Active" : "Desactive")}
        ${renderOpsDetailRow("Sortie", run.output_path || "N/A")}
        ${run.error_message ? renderOpsDetailRow("Erreur", run.error_message) : ""}
      </div>
    </section>
    <section class="price-history" id="ops-offer-audit-panel">
      <div class="offers-head">
        <h3>Audit prix</h3>
        <span id="ops-offer-audit-count">Chargement</span>
      </div>
      <div class="offer-audit-list" id="ops-offer-audit-body">
        <div class="skeleton skeleton--compact"></div>
      </div>
    </section>
    <section class="price-history" id="ops-raw-documents-panel">
      <div class="offers-head">
        <h3>Documents bruts</h3>
        <span id="ops-raw-documents-count">Chargement</span>
      </div>
      <div class="raw-document-list" id="ops-raw-documents-body">
        <div class="skeleton skeleton--compact"></div>
      </div>
    </section>
    <section class="price-history" id="ops-stale-offers-panel">
      <div class="offers-head">
        <h3>Offres a rafraichir</h3>
        <span id="ops-stale-offers-count">Chargement</span>
      </div>
      <div class="stale-offer-list" id="ops-stale-offers-body">
        <div class="skeleton skeleton--compact"></div>
      </div>
    </section>
  `;
}

function renderOpsDetailRow(label, value) {
  return `
    <div class="ops-detail-row">
      <span>${label}</span>
      <strong>${value}</strong>
    </div>
  `;
}

async function renderOpsRawDocuments(crawlRunId) {
  const count = document.querySelector("#ops-raw-documents-count");
  const body = document.querySelector("#ops-raw-documents-body");
  const token = savedOpsAdminToken();
  if (!count || !body || !crawlRunId || !token) return;

  try {
    const response = await fetch(`/ops/crawl-runs/${encodeURIComponent(crawlRunId)}/documents?limit=8`, {
      headers: opsAdminHeaders(token),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    const documents = data.documents || [];
    count.textContent = `${documents.length} ${documents.length > 1 ? "docs" : "doc"}`;
    body.innerHTML = documents.length
      ? documents.map(renderRawDocumentRow).join("")
      : `<div class="history-empty">Aucun document brut rattache a ce run.</div>`;
  } catch (error) {
    count.textContent = "Erreur";
    body.innerHTML = `<div class="history-empty">Documents bruts indisponibles.</div>`;
  }
}

function renderRawDocumentRow(document) {
  return `
    <article class="raw-document-row">
      <div>
        <strong>${document.http_status} · ${document.doc_type.toUpperCase()}</strong>
        <span>${escapeHtml(document.url)}</span>
      </div>
      <div class="raw-document-meta">
        <span>${formatBytes(document.content_length)}</span>
        <span>${document.payload_sha256.slice(0, 10)}</span>
      </div>
    </article>
  `;
}

async function renderOpsOfferAudit() {
  const count = document.querySelector("#ops-offer-audit-count");
  const body = document.querySelector("#ops-offer-audit-body");
  const token = savedOpsAdminToken();
  if (!count || !body || !token) return;

  try {
    const response = await fetch("/ops/offers/audit?limit=8", {
      headers: opsAdminHeaders(token),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    const offers = data.offers || [];
    count.textContent = `${offers.length} / ${data.total || 0} offres`;
    body.innerHTML = offers.length
      ? offers.map(renderOfferAuditRow).join("")
      : `<div class="history-empty">Aucune offre a auditer.</div>`;
  } catch (error) {
    count.textContent = "Erreur";
    body.innerHTML = `<div class="history-empty">Audit prix indisponible.</div>`;
  }
}

function renderOfferAuditRow(offer) {
  const source = offer.source_document;
  return `
    <article class="offer-audit-row">
      <div class="offer-audit-main">
        <div class="offer-audit-title">
          <span class="merchant-chip ${merchantClass(offer.merchant_slug)}">${escapeHtml(offer.merchant_name)}</span>
          <strong>${escapeHtml(offer.title)}</strong>
        </div>
        <span>${availabilityLabel(offer.availability)} · vu le ${formatShortDate(offer.last_seen_at)}</span>
        <span>${source ? `source ${source.http_status} · ${formatBytes(source.content_length)} · ${escapeHtml(source.payload_sha256.slice(0, 10))}` : "source manquante"}</span>
      </div>
      <div class="offer-audit-actions">
        <strong>${formatPrice(offer.total_amount)}</strong>
        ${offer.is_stale ? `<span class="stale-badge">Ancien</span>` : ""}
        <a class="copy-link-button" href="/ui/product/${encodeURIComponent(offer.product_id)}">Produit</a>
        <a class="copy-link-button" href="${escapeHtml(offer.product_url)}" target="_blank" rel="noreferrer">Offre</a>
      </div>
    </article>
  `;
}

async function exportOpsOfferAuditCsv() {
  const token = savedOpsAdminToken();
  if (!token) {
    changeOpsAdminToken();
    return;
  }

  try {
    const response = await fetch("/ops/offers/audit.csv?limit=500", {
      headers: opsAdminHeaders(token),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = csvFilenameFromResponse(response) || "electronicstar-offer-audit.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    setStateCard("error", "Export indisponible", "Impossible de generer le CSV d'audit des offres.");
  }
}

function csvFilenameFromResponse(response) {
  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  return match ? match[1] : "";
}

async function renderOpsStaleOffers() {
  const count = document.querySelector("#ops-stale-offers-count");
  const body = document.querySelector("#ops-stale-offers-body");
  const token = savedOpsAdminToken();
  if (!count || !body || !token) return;

  try {
    const response = await fetch("/ops/offers/stale?limit=8", {
      headers: opsAdminHeaders(token),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    const offers = data.offers || [];
    count.textContent = `${offers.length} / ${data.total || 0} anciennes`;
    body.innerHTML = offers.length
      ? offers.map(renderStaleOfferRow).join("")
      : `<div class="history-empty">Aucune offre ancienne a rafraichir.</div>`;
    body.querySelectorAll("[data-crawl-merchant]").forEach((button) => {
      button.addEventListener("click", triggerCrawlRun);
    });
  } catch (error) {
    count.textContent = "Erreur";
    body.innerHTML = `<div class="history-empty">Offres anciennes indisponibles.</div>`;
  }
}

function renderStaleOfferRow(offer) {
  const merchantName = offer.merchant_name || merchantDisplayName(offer.merchant_slug);
  return `
    <article class="stale-offer-row">
      <div class="stale-offer-main">
        <strong>${escapeHtml(offer.title)}</strong>
        <span>
          ${escapeHtml(merchantName)} · vu le ${formatShortDate(offer.last_seen_at)} · ${formatPrice(offer.total_amount)}
        </span>
      </div>
      <button class="copy-link-button stale-offer-action" data-crawl-merchant="${escapeHtml(offer.merchant_slug)}" type="button">
        Relancer ${escapeHtml(merchantName)}
      </button>
    </article>
  `;
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
            ${product.is_stale ? `<span class="stale-badge">Crawl ancien</span>` : ""}
          </div>
          <div class="detail-price">${formatPrice(bestTotal)}</div>
          <div class="price-range">Fourchette ${formatPrice(product.price_min)} - ${formatPrice(product.price_max)}</div>
          <div class="detail-actions">
            <button class="copy-link-button" type="button" data-copy-product-link="${product.product_id || appState.selectedProductId}">
              Copier le lien
            </button>
            <a class="export-link-button" href="/products/${encodeURIComponent(product.product_id || appState.selectedProductId)}/offers.csv">
              Export offres CSV
            </a>
            <a class="export-link-button" href="/products/${encodeURIComponent(product.product_id || appState.selectedProductId)}/price-history.csv">
              Export historique CSV
            </a>
            <span class="price-change-badge" id="price-change-badge">Variation en cours</span>
          </div>
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

  bindDetailActions(product.product_id || appState.selectedProductId);
  bindOfferSourceActions();
  renderPriceHistory(product.product_id || appState.selectedProductId);
}

function bindDetailActions(productId) {
  const copyButton = document.querySelector("[data-copy-product-link]");
  if (!copyButton || !productId) return;

  copyButton.addEventListener("click", () => {
    copyProductLink(productId, copyButton);
  });
}

async function copyProductLink(productId, button) {
  const originalLabel = button.textContent.trim();
  button.disabled = true;

  try {
    await copyText(productAbsoluteUrl(productId));
    button.textContent = "Lien copié";
  } catch (error) {
    button.textContent = "Copie impossible";
  } finally {
    window.setTimeout(() => {
      button.textContent = originalLabel;
      button.disabled = false;
    }, 1400);
  }
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function bindOfferSourceActions() {
  detailPanel.querySelectorAll("[data-offer-source-id]").forEach((button) => {
    button.addEventListener("click", showOfferSourceDocument);
  });
}

async function showOfferSourceDocument(event) {
  const button = event.currentTarget;
  const offerId = button.dataset.offerSourceId;
  const token = requestOpsAdminToken();
  if (!token || !offerId) return;

  const originalLabel = button.textContent.trim();
  button.disabled = true;
  button.textContent = "Source...";

  try {
    const response = await fetch(`/ops/offers/${encodeURIComponent(offerId)}/source-document`, {
      headers: opsAdminHeaders(token),
    });
    if (response.status === 401 || response.status === 403) {
      forgetOpsAdminToken();
      throw new Error("Token admin invalide");
    }
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    renderOfferSourceMessage(button, data.document);
  } catch (error) {
    renderOfferSourceMessage(button, null, true);
  } finally {
    button.textContent = originalLabel;
    button.disabled = false;
  }
}

function renderOfferSourceMessage(button, sourceDocument, hasError = false) {
  const card = button.closest(".offer-card");
  if (!card) return;

  let panel = card.querySelector(".source-document-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.className = "source-document-panel";
    card.appendChild(panel);
  }

  panel.classList.toggle("is-error", hasError);
  if (hasError) {
    panel.innerHTML = `
      <strong>Source indisponible</strong>
      <span>Verifie la cle admin puis recharge la source.</span>
    `;
    return;
  }

  if (!sourceDocument) {
    panel.innerHTML = `
      <strong>Aucune source brute</strong>
      <span>Aucun document crawl ne correspond a cette offre.</span>
    `;
    return;
  }

  panel.innerHTML = `
    <strong>${sourceDocument.http_status} · ${escapeHtml(sourceDocument.doc_type.toUpperCase())}</strong>
    <span>${escapeHtml(sourceDocument.url)}</span>
    <span>${formatBytes(sourceDocument.content_length)} · ${escapeHtml(sourceDocument.payload_sha256.slice(0, 10))}</span>
    ${sourceDocument.payload_path ? `<span>${escapeHtml(sourceDocument.payload_path)}</span>` : ""}
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
        ${offer.is_stale ? `<span class="stale-badge">Crawl ancien</span>` : ""}
      </div>
      <div class="offer-source-line">Vu le ${formatShortDate(offer.last_seen_at)}</div>
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
      <div class="offer-actions">
        <a class="offer-button" href="${offer.product_url}" target="_blank" rel="noreferrer">
          Voir l'offre
        </a>
        ${offer.offer_id ? `
          <button class="copy-link-button source-document-button" type="button" data-offer-source-id="${offer.offer_id}">
            Source crawl
          </button>
        ` : ""}
      </div>
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
    updatePriceChangeBadge(points);
    body.innerHTML = renderPriceHistoryBody(points);
  } catch (error) {
    count.textContent = "Erreur";
    updatePriceChangeBadge([]);
    body.innerHTML = `<div class="history-empty">Historique indisponible.</div>`;
  }
}

function updatePriceChangeBadge(points) {
  const badge = document.querySelector("#price-change-badge");
  if (!badge) return;

  const change = latestPriceChange(points);
  badge.className = "price-change-badge";

  if (!change) {
    badge.textContent = points.length > 0 ? "Prix stable" : "Pas encore de variation";
    return;
  }

  if (change.amount < 0) {
    badge.textContent = `Baisse ${formatSignedPrice(change.amount)}`;
    badge.classList.add("is-good");
    return;
  }

  if (change.amount > 0) {
    badge.textContent = `Hausse ${formatSignedPrice(change.amount)}`;
    badge.classList.add("is-bad");
    return;
  }

  badge.textContent = "Prix stable";
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

crawlRunButtons.forEach((button) => {
  button.addEventListener("click", triggerCrawlRun);
});

function renderMerchantFilters() {
  merchantFilters.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.merchant === appState.merchant);
  });
}

async function loadCrawlStatus() {
  if (!crawlStatus) return;
  const token = savedOpsAdminToken();
  if (!token) {
    crawlStatus.innerHTML = `<div class="crawl-status-empty">Cle admin requise</div>`;
    return;
  }

  try {
    const response = await fetch("/ops/crawl-runs/latest", {
      headers: opsAdminHeaders(token),
    });
    if (response.status === 401 || response.status === 403) {
      forgetOpsAdminToken();
      crawlStatus.innerHTML = `<div class="crawl-status-empty">Cle admin invalide</div>`;
      return;
    }
    if (!response.ok) throw new Error(`API ${response.status}`);
    const data = await response.json();
    renderCrawlStatus(data.runs || []);
  } catch (error) {
    crawlStatus.innerHTML = `<div class="crawl-status-empty">Indisponible</div>`;
  }
}

async function triggerCrawlRun(event) {
  const button = event?.currentTarget;
  if (!button) return;
  const merchant = button.dataset.crawlMerchant || "materiel";
  const merchantName = merchantDisplayName(merchant);
  const token = requestOpsAdminToken();
  if (!token) {
    if (crawlStatus) {
      crawlStatus.innerHTML = `<div class="crawl-status-empty">Cle admin requise</div>`;
    }
    return;
  }

  const originalLabel = button.textContent.trim();
  button.disabled = true;
  button.textContent = "Demande envoyée";

  try {
    const response = await fetch(`/ops/crawl-runs/${encodeURIComponent(merchant)}/run`, {
      method: "POST",
      headers: opsAdminHeaders(token),
    });
    if (response.status === 401 || response.status === 403) {
      forgetOpsAdminToken();
      throw new Error("Token admin invalide");
    }
    if (!response.ok) throw new Error(`API ${response.status}`);
    await loadCrawlStatus();
    if (isOpsRoute()) {
      await loadOpsRoute();
    }
  } catch (error) {
    if (crawlStatus) {
      crawlStatus.innerHTML = `<div class="crawl-status-empty">Relance ${merchantName} impossible</div>`;
    }
  } finally {
    window.setTimeout(() => {
      button.textContent = originalLabel;
      button.disabled = false;
      loadCrawlStatus();
      if (isOpsRoute()) {
        loadOpsRoute();
      }
    }, 1600);
  }
}

function savedOpsAdminToken() {
  return window.localStorage.getItem(OPS_ADMIN_TOKEN_STORAGE_KEY) || "";
}

function requestOpsAdminToken() {
  const savedToken = savedOpsAdminToken();
  if (savedToken) return savedToken;

  const token = window.prompt("Cle admin ops");
  const cleanToken = token ? token.trim() : "";
  if (!cleanToken) return "";

  window.localStorage.setItem(OPS_ADMIN_TOKEN_STORAGE_KEY, cleanToken);
  return cleanToken;
}

function forgetOpsAdminToken() {
  window.localStorage.removeItem(OPS_ADMIN_TOKEN_STORAGE_KEY);
}

function changeOpsAdminToken() {
  forgetOpsAdminToken();
  const token = requestOpsAdminToken();
  if (!token) {
    loadOpsRoute();
    loadCrawlStatus();
    return;
  }

  loadOpsRoute();
  loadCrawlStatus();
}

function opsAdminHeaders(token) {
  return {
    "X-Admin-Token": token,
  };
}

function renderCrawlStatus(runs) {
  if (!crawlStatus) return;
  if (runs.length === 0) {
    crawlStatus.innerHTML = `<div class="crawl-status-empty">Aucun crawl</div>`;
    return;
  }

  crawlStatus.innerHTML = runs.map((run) => `
    <article class="crawl-run crawl-run--${run.status}">
      <div>
        <strong>${run.merchant_name}</strong>
        <span>${run.items_scraped} items · ${formatShortDate(run.started_at)} · ${formatDuration(run.duration_seconds)}</span>
      </div>
      <span class="crawl-status-badge">${crawlStatusLabel(run.status)}</span>
    </article>
  `).join("");
}

window.addEventListener("popstate", () => {
  const productId = currentRouteProductId();
  if (productId) {
    loadProductRoute(productId);
  } else if (isDemoRoute()) {
    loadDemoRoute();
  } else if (isOpsRoute()) {
    loadOpsRoute();
  } else {
    appState.selectedProductId = null;
    searchProducts();
  }
});

const initialProductId = currentRouteProductId();
loadCrawlStatus();
if (initialProductId) {
  loadProductRoute(initialProductId);
} else if (isDemoRoute()) {
  loadDemoRoute();
} else if (isOpsRoute()) {
  loadOpsRoute();
} else {
  searchProducts();
}
