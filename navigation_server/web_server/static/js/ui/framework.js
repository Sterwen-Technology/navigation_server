// Framework page/bloc: assemble les PAGES depuis la configuration UI
// (doc/web_ui_modular.md section 2) et pilote les cycles de fetch par
// dataset (section 2.6):
//   - data    : a chaque cycle de rafraichissement de la page
//   - trend   : au meme cycle, uniquement si une vue le reference
//   - parameters : a l'activation de la page, si un titre, une echelle ou
//     un repeat le reference (re-fetch sur changement de contexte: a venir)
//
// Un bloc = entite + vues; les vues resolvent leurs valeurs par chemins
// explicites <dataset>/<name> (section 3.3). Les blocs repetes sont
// instancies une fois par item retourne par leur source (section 2.5).

import { $ } from '../config.js';
import { apiGet } from '../api.js';
import { translateAllElements } from '../i18n.js';
import { t } from '../translations-bridge.js';
import { STANDARD_DATASETS, loadUiConfig } from './config.js';
import { fmtValue, resolveColor, renderWidget } from './views.js';

export { initUiFramework };
export { buildNavForPages };
export { showConfiguredPage };
export { refreshConfiguredPage };
export { pageAvailabilityChanged };

// --- Etat global ---------------------------------------------------------

let uiConfig = null;
let widgetDefs = new Map();      // widget id -> definition
let blockTypeDefs = new Map();   // block_type id -> definition
let colorPalette = {};
const pageRegistry = new Map();  // page id -> {cfg, el, timer, refreshing, available, params}
let configuredPages = [];
let currentPage = "services";    // page 0 par defaut

// --- Normalisation -------------------------------------------------------

// Parse un endpoint en (base, service, instance) - section 3.2:
//   /api/<service>/<instance>/<dataset>[/<name>]  ou forme courte
//   /api/<service>/<dataset>
// Parse un endpoint en (base, service, instance, dataset primaire) -
// section 3.2. Formes acceptees:
//   /api/<service>/<instance>/<dataset>[/<name>]  (services multi-instances)
//   /api/<service>/<dataset>[/<name>]              (singletons: instance omise)
// Le dataset de l'endpoint est le dataset PRIMAIRE du bloc: les chemins de
// donnees des vues sans prefixe de dataset y resolvent (section 3.3).
function parseEndpoint(endpoint) {
    const parts = endpoint.replace(/^\//, "").split("/").filter(Boolean);
    if (parts[0] !== "api" || parts.length < 2) return null;
    const service = parts[1];
    let instance = 0;
    let dataset = "data";
    let name = null;
    if (parts.length > 2) {
        if (STANDARD_DATASETS.includes(parts[2])) {
            // forme courte: /api/<service>/<dataset>[/<name>]
            dataset = parts[2];
            name = parts[3] || null;
        } else {
            // forme complete: /api/<service>/<instance>/<dataset>[/<name>]
            instance = parts[2];
            if (parts.length > 3 && STANDARD_DATASETS.includes(parts[3])) {
                dataset = parts[3];
                name = parts[4] || null;
            }
        }
    }
    return { service, instance, dataset, name, base: `/api/${service}/${instance}` };
}

// Normalise un bloc de la configuration: soit il reference un block_type,
// soit il porte sa definition inline (section 2.4).
function normalizeBlock(block) {
    const typeDef = block.type ? blockTypeDefs.get(block.type) : null;
    const source = typeDef || block;
    const views = source.definition || [];
    // Dataset primaire du bloc: celui de l'endpoint s'il est specifie,
    // 'data' par defaut (bases des blocs repetes sans dataset).
    const parsed = block.endpoint ? parseEndpoint(block.endpoint) : null;
    return {
        id: block.id,
        typeDef,
        views,
        title: block.title || source.title || block.id,
        topWidget: source.top_widget || null,
        repeat: block.repeat || null,
        endpoint: block.endpoint || null,
        primaryDataset: parsed ? parsed.dataset : "data",
        width: Math.max(1, block.width || 1),
        position: block.position || null,
        priority: block.priority !== undefined ? block.priority : 100,
    };
}

// Datasets requis par un bloc: chemins de donnees des vues + titre +
// echelles des widgets (section 2.6 - un dataset n'est fetch que s'il sert).
function requiredDatasets(block) {
    const needed = new Set();
    const primary = block.primaryDataset || "data";
    for (const view of block.views) {
        // Chemin de donnee: <dataset>/<name> ou <name> seul - dans ce cas le
        // dataset PRIMAIRE du bloc (celui de l'endpoint) est implicite.
        const first = String(view.data || "").split("/")[0];
        const ds = STANDARD_DATASETS.includes(first) ? first : primary;
        needed.add(ds);
        const widget = view.widget ? widgetDefs.get(view.widget) : null;
        if (widget && widget.scale) {
            for (const key of ["max", "low", "high"]) {
                const p = widget.scale[key];
                if (typeof p === "string" && STANDARD_DATASETS.includes(p.split("/")[0])) {
                    needed.add(p.split("/")[0]);
                }
            }
        }
    }
    if (typeof block.title === "string" && block.title.includes("/") &&
        STANDARD_DATASETS.includes(block.title.split("/")[0])) {
        needed.add(block.title.split("/")[0]);
    }
    return needed;
}

// --- Resolution des chemins (section 3.3) --------------------------------

// Valeur scalaire: <dataset>/<name>, resolue dans le dataset du bloc;
// pour le dataset parameters: parametres du service du bloc d'abord, puis
// parametres de la page (section 3.3).
function resolveScalar(datasets, path, pageParams, defaultDataset) {
    if (path === null || path === undefined) return undefined;
    if (typeof path === "number") return path;
    const s = String(path);
    if (!s.includes("/")) {
        // Chemin sans dataset: resolution dans le dataset PRIMAIRE du bloc
        // (celui de l'endpoint, section 3.3); sinon valeur litterale.
        if (defaultDataset && datasets[defaultDataset] && s in datasets[defaultDataset]) {
            return datasets[defaultDataset][s];
        }
        const n = Number(s);
        return Number.isNaN(n) ? undefined : n;
    }
    const [ds, ...rest] = s.split("/");
    const name = rest.join("/");
    if (ds === "parameters") {
        // Section 3.3: parametres du service du bloc, sinon parametres de la page
        if (datasets.parameters && name in datasets.parameters) {
            return datasets.parameters[name];
        }
        if (pageParams && name in pageParams) {
            return pageParams[name];
        }
        return undefined;
    }
    const container = datasets[ds];
    if (!container) return undefined;
    return container[name];
}

// Serie temporelle: <dataset>/<name> - le champ name dans chaque sample
// (l'element de chemin 'samples' non significatif est omis, section 3.2).
function resolveSeries(datasets, path, defaultDataset) {
    const parts = String(path || "").split("/");
    const ds = STANDARD_DATASETS.includes(parts[0]) ? parts[0] : (defaultDataset || "data");
    const name = STANDARD_DATASETS.includes(parts[0]) ? parts[1] : parts[0];
    const container = datasets[ds];
    if (!container || !Array.isArray(container.samples)) return [];
    return container.samples.map(s => s[name]);
}

// Echelle d'un widget (section 5.7): fixed/dual/dynamic, les references
// sont des chemins (parameters/...) ou des valeurs litterales.
function resolveScale(scale, value, datasets, pageParams) {
    if (!scale || !scale.type || scale.type === "dynamic") {
        // Echelle dynamique: recalculee sur la valeur affichee (barees).
        return { max: Math.max(Math.abs(value) * 1.25, 1e-6) };
    }
    if (scale.type === "fixed") {
        return { max: resolveScalar(datasets, scale.max, pageParams) ?? 1.0 };
    }
    if (scale.type === "dual") {
        // low = seuil ET echelle basse; high = echelle haute (section 5.7).
        // low/high sont retournes au widget pour l'indicateur High/Low power
        // (derive par le front-end selon la meme regle que la bascule).
        const low = resolveScalar(datasets, scale.low, pageParams) ?? 1.0;
        const high = resolveScalar(datasets, scale.high, pageParams) ?? low * 5;
        return { max: Math.abs(value) <= low ? low : high, low, high };
    }
    return { max: 1.0 };
}

// --- Rendu d'un bloc ------------------------------------------------------

// Rend le titre d'un bloc (litteral ou chemin parameters/...).
function blockTitle(block, datasets, pageParams, fallback) {
    if (typeof block.title === "string" && block.title.includes("/")) {
        const v = resolveScalar(datasets, block.title, pageParams);
        if (v) return String(v);
        if (fallback) return fallback;
        return block.id;
    }
    return block.title;
}

// Rend le corps d'un bloc: viewgraphs a gauche (flex), courbes dans
// l'espace restant a droite (section 5.5).
function renderBlockBody(blockEl, block, datasets, pageParams, titleFallback) {
    const titleEl = blockEl.querySelector(".ui-block-title-text");
    if (titleEl) titleEl.textContent = blockTitle(block, datasets, pageParams, titleFallback);

    const statusEl = blockEl.querySelector(".ui-block-status");
    if (statusEl && block.topWidget) {
        const widget = widgetDefs.get(block.topWidget) || { base_widget: block.topWidget };
        // Live fields from the data dataset: the 3-state indicator
        // (ON/OFF/NO COM) is decided by the frontend from communication_ok
        // and state (specs section 5.4).
        const live = datasets.data || {};
        const ctx = {
            value: live.communication_ok,
            communication_ok: live.communication_ok,
            state: live.state,
        };
        statusEl.innerHTML = renderWidget(widget, ctx);
    }

    const bodyEl = blockEl.querySelector(".ui-block-body");
    if (!bodyEl) return;

    let bars = "";
    let trends = "";
    for (const view of block.views) {
        const widget = view.widget ? widgetDefs.get(view.widget) : null;
        if (!widget) {
            bodyEl.innerHTML = `<div class="empty">Unknown widget: ${view.widget || ""}</div>`;
            return;
        }
        const isCurve = (widget.base_widget || "").includes("curve");
        const ctx = {
            label: view.title || view.view,
            unit: widget.unit,
            precision: widget.precision ?? 0,
            colorCss: resolveColor(widget.color, colorPalette),
            ratioPercent: !!widget.ratio_percent,
        };
        if (isCurve) {
            ctx.series = resolveSeries(datasets, view.data, block.primaryDataset);
            trends += `<div class="ui-trend-item"><div class="ems-trend-title">${ctx.label || ""}</div>` +
                renderWidget(widget, ctx) + `</div>`;
        } else {
            // Valeur indéfinie (dataset absent ou champ manquant): la vue est
            // quand même rendue avec '--' - une vue ne doit pas disparaître
            // silencieusement, c'est un indice de diagnostic.
            ctx.value = resolveScalar(datasets, view.data, pageParams, block.primaryDataset) ?? null;
            const scale = resolveScale(widget.scale, ctx.value, datasets, pageParams);
            ctx.max = scale.max;
            ctx.scaleLow = scale.low;
            ctx.scaleHigh = scale.high;
            bars += renderWidget(widget, ctx);
        }
    }

    bodyEl.innerHTML = "";
    if (bars) {
        const barsEl = document.createElement("div");
        barsEl.className = "ui-viewgraphs";
        barsEl.innerHTML = bars;
        bodyEl.appendChild(barsEl);
    }
    if (trends) {
        const trendEl = document.createElement("div");
        trendEl.className = "ui-trend-zone";
        trendEl.innerHTML = trends;
        bodyEl.appendChild(trendEl);
    }
    if (!bars && !trends) {
        bodyEl.innerHTML = `<div class="empty" data-i18n="ems.loading">${t.t("ems.loading")}</div>`;
    }
    translateAllElements();
}

function createBlockElement(blockId, width, position, columns) {
    const el = document.createElement("div");
    el.className = "ems-box ui-block";
    el.dataset.blockId = blockId;
    const w = Math.min(width || 1, columns || 1);
    el.style.gridColumn = `span ${w}`;
    if (position && typeof position.row === "number") {
        el.style.gridRow = `${position.row + 1}`;
        if (typeof position.column === "number") {
            el.style.gridColumn = `${position.column + 1} / ${position.column + 1 + w}`;
        }
    }
    el.innerHTML = `
        <h2 class="ui-block-title"><span class="ui-block-title-text"></span><span class="ui-block-status"></span></h2>
        <div class="ui-block-body">
            <div class="empty" data-i18n="ems.loading">Loading...</div>
        </div>
    `;
    return el;
}

// --- Cycles de fetch (section 2.6) ---------------------------------------

// Fetch les datasets requis par un bloc, un appel par dataset.
async function fetchDatasets(base, datasets) {
    const results = {};
    const errors = [];
    await Promise.all([...datasets].map(async (ds) => {
        try {
            const json = await apiGet(`${base}/${ds}`);
            if (json && json.ok) {
                results[ds] = json;
            } else {
                errors.push(`${ds}: ${json && json.error ? json.error : "no data"}`);
            }
        } catch (e) {
            errors.push(`${ds}: ${e.message}`);
        }
    }));
    return { results, errors };
}

async function refreshSimpleBlock(page, block) {
    const blockEl = page.element.querySelector(`[data-block-id="${block.id}"]`);
    if (!blockEl) return;
    const parsed = parseEndpoint(block.endpoint);
    if (!parsed) {
        blockEl.querySelector(".ui-block-body").innerHTML =
            `<div class="empty">Invalid endpoint: ${block.endpoint}</div>`;
        return;
    }
    const { results, errors } = await fetchDatasets(parsed.base, requiredDatasets(block));
    if (!results.data && errors.length) {
        blockEl.querySelector(".ui-block-body").innerHTML =
            `<div class="empty">${errors[0]}</div>`;
        return;
    }
    renderBlockBody(blockEl, block, results, page.params, null);
}

async function refreshRepeatBlock(page, block) {
    const container = page.element.querySelector(`[data-block-container="${block.id}"]`);
    if (!container) return;
    let items = [];
    try {
        const json = await apiGet(block.repeat.source_endpoint);
        if (json && json.ok && Array.isArray(json.value)) {
            items = json.value;
        }
    } catch (e) {
        container.innerHTML = `<div class="empty">${e.message}</div>`;
        return;
    }

    // Le nombre d'instances suit la collection (section 2.5); le type de
    // bloc peut etre specialise par service (repeat.types, section 2.5):
    // les datasets des entites heterogenes n'exposent pas les memes champs
    // (ex. MPPT_Data.current/power vs DC_DC_Data.output_current/output_power).
    container.innerHTML = "";
    for (let idx = 0; idx < items.length; idx++) {
        const item = items[idx];
        const instanceId = `${block.id}-${idx}`;
        const base = block.repeat.block_endpoint
            .replace("{service}", item.service)
            .replace("{instance}", item.instance);
        const typeOverride = (block.repeat.types && block.repeat.types[item.service]) || null;
        const typeDef = typeOverride ? blockTypeDefs.get(typeOverride) : block.typeDef;
        if (typeOverride && !typeDef) {
            container.innerHTML += `<div class="empty">Unknown block type '${typeOverride}' for service ${item.service}</div>`;
            continue;
        }
        const instanceBlock = {
            id: instanceId,
            typeDef,
            views: (typeDef && typeDef.definition) || block.views,
            title: (typeDef && typeDef.title) || block.title,
            topWidget: (typeDef && typeDef.top_widget) || block.topWidget,
            endpoint: base,
            repeat: null,
            width: 1,
            position: null,
            priority: block.priority,
        };
        const blockEl = createBlockElement(instanceId, 1, null, columnsOf(page));
        container.appendChild(blockEl);
        const { results, errors } = await fetchDatasets(base, requiredDatasets(instanceBlock));
        if (!results.data && errors.length) {
            // Erreur visible dans l'instance (ex. service injoignable) - pas
            // de bloc muet.
            blockEl.querySelector(".ui-block-body").innerHTML =
                `<div class="empty">${errors[0]}</div>`;
            continue;
        }
        renderBlockBody(blockEl, instanceBlock, results, page.params, item.label);
    }
}

function columnsOf(page) {
    return (page.cfg.layout && page.cfg.layout.columns) || 1;
}

async function refreshConfiguredPage(pageId) {
    const page = pageRegistry.get(pageId);
    if (!page || page.refreshing) return;
    page.refreshing = true;
    try {
        const blocks = (page.cfg.blocks || []).map(normalizeBlock);
        for (const block of blocks) {
            if (block.repeat) {
                await refreshRepeatBlock(page, block);
            } else {
                await refreshSimpleBlock(page, block);
            }
        }
    } finally {
        page.refreshing = false;
    }
}

// --- Pages ----------------------------------------------------------------

// Cree (une fois) les elements DOM d'une page configuree: grille au nombre
// de colonnes du layout, blocs places par position explicite ou par
// priorite (section 2.3).
function ensurePageElement(pageCfg) {
    let page = pageRegistry.get(pageCfg.id);
    if (page) return page;

    const pageEl = document.createElement("div");
    pageEl.id = `page-${pageCfg.id}`;
    pageEl.className = "page configured-page";
    pageEl.style.display = "none";

    const columns = columnsOf({ cfg: pageCfg });
    const gridEl = document.createElement("div");
    gridEl.className = "ui-page-grid";
    gridEl.style.gridTemplateColumns = `repeat(${columns}, 1fr)`;

    const blocks = (pageCfg.blocks || []).map(normalizeBlock);
    // Positionnement: blocs avec position explicite d'abord (placee dans la
    // grille), puis les autres par priorite croissante (auto-flow).
    const explicit = blocks.filter(b => b.position);
    const auto = blocks.filter(b => !b.position).sort((a, b) => a.priority - b.priority);
    for (const block of explicit) {
        gridEl.appendChild(createBlockElement(block.id, block.width, block.position, columns));
    }
    for (const block of auto) {
        if (block.repeat) {
            // Bloc repete: le conteneur est place directement dans la grille
            // de la page (pas de bloc wrapper - il n'y a pas d'entite
            // associee au conteneur lui-meme). Les instances sont des blocs
            // independants de largeur 1, repartis sur les colonnes de la page.
            const containerEl = document.createElement("div");
            containerEl.className = "ui-repeat-container";
            containerEl.dataset.blockContainer = block.id;
            containerEl.style.gridTemplateColumns = `repeat(${columns}, 1fr)`;
            containerEl.style.gridColumn = "1 / -1";
            gridEl.appendChild(containerEl);
            continue;
        }
        gridEl.appendChild(createBlockElement(block.id, block.width, null, columns));
    }
    pageEl.appendChild(gridEl);
    document.querySelector("main").appendChild(pageEl);

    page = {
        cfg: pageCfg,
        element: pageEl,
        timer: null,
        refreshing: false,
        available: undefined,
        params: null,
    };
    pageRegistry.set(pageCfg.id, page);
    return page;
}

// Parametres de page (section 3.3): fetch a l'activation, uniquement si la
// page en declare un endpoint.
async function fetchPageParameters(page) {
    if (!page.cfg.parameters_endpoint) return;
    try {
        const json = await apiGet(page.cfg.parameters_endpoint);
        if (json && json.ok) page.params = json;
    } catch (e) {
        console.warn("Page parameters fetch failed:", e.message);
    }
}

function startPageTimer(pageId) {
    const page = pageRegistry.get(pageId);
    if (!page) return;
    const interval = page.cfg.refresh_interval || 10000;
    page.timer = setTimeout(async () => {
        if (currentPage === pageId && page.available !== false) {
            await refreshConfiguredPage(pageId).catch(() => {});
        }
        if (pageRegistry.get(pageId) === page) startPageTimer(pageId);
    }, interval);
}

async function checkPageAvailability(pageCfg) {
    const page = pageRegistry.get(pageCfg.id);
    if (!page || !pageCfg.availability_endpoint) return;
    try {
        const data = await apiGet(pageCfg.availability_endpoint);
        page.available = !!(data && data.available);
    } catch (e) {
        page.available = false;
    }
    pageAvailabilityChanged(pageCfg.id, page.available);
}

function pageAvailabilityChanged(pageId, available) {
    const btn = $(`nav-${pageId}`);
    if (btn) btn.style.display = available ? "" : "none";
    if (!available && currentPage === pageId) {
        const fallback = configuredPages.find(p => p.builtin === "services");
        if (fallback) showConfiguredPage(fallback.id);
    }
}

function buildNavForPages(pages) {
    configuredPages = pages;
    const nav = document.querySelector(".page-nav");
    if (!nav) return;
    for (const pageCfg of pages) {
        if (pageCfg.builtin === "services") continue;
        const btn = document.createElement("button");
        btn.id = `nav-${pageCfg.id}`;
        btn.className = "nav-btn";
        btn.dataset.i18n = pageCfg.title_i18n || "";
        btn.textContent = t.t(pageCfg.title_i18n) || pageCfg.title || pageCfg.id;
        btn.addEventListener("click", () => showConfiguredPage(pageCfg.id));
        if (pageCfg.availability_endpoint) btn.style.display = "none";
        nav.appendChild(btn);
    }
}

function showConfiguredPage(pageId) {
    const pageCfg = configuredPages.find(p => p.id === pageId);
    if (!pageCfg) return false;
    const page = ensurePageElement(pageCfg);

    if (pageCfg.availability_endpoint && page.available === undefined) {
        checkPageAvailability(pageCfg);
    }
    if (page.available === false) return false;

    currentPage = pageId;
    document.querySelectorAll(".page").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".nav-btn").forEach(el => el.classList.remove("active"));

    if (pageCfg.builtin === "services") {
        const servicesPage = $("services-page");
        if (servicesPage) servicesPage.classList.add("active");
        const servicesBtn = $("nav-services");
        if (servicesBtn) servicesBtn.classList.add("active");
    } else {
        page.element.style.display = "";
        page.element.classList.add("active");
        const btn = $(`nav-${pageCfg.id}`);
        if (btn) btn.classList.add("active");
        fetchPageParameters(page).then(() => refreshConfiguredPage(pageId));
        if (!page.timer) startPageTimer(pageId);
        for (const [id, other] of pageRegistry) {
            if (id !== pageId) other.element.style.display = "none";
        }
    }
    return true;
}

// --- Initialisation -------------------------------------------------------

async function initUiFramework() {
    uiConfig = await loadUiConfig();
    widgetDefs = new Map((uiConfig.widgets || []).map(w => [w.id, w]));
    blockTypeDefs = new Map((uiConfig.block_types || []).map(b => [b.id, b]));
    colorPalette = uiConfig.colors || {};
    buildNavForPages(uiConfig.pages);
    return uiConfig;
}
