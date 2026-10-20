// Framework page/bloc: assemble dynamiquement les PAGES a partir de la
// configuration UI (js/ui/config.js). Chaque page est un ensemble de BLOCS,
// chaque bloc etant lie a une entite et a une vue (js/ui/blocks.js).
//
// Une page declaree avec "builtin": "services" est rendue par le code
// historique (collectors/system.js): la page Services est la page 0, non
// optionnelle et non reconfigurenable.
//
// Cycle de vie d'une page configuree:
//   - creation a la demande (premier affichage) puis rafraichissement
//     periodique tant qu'elle est active
//   - un meme endpoint n'est interroge qu'une seule fois par cycle, les
//     blocs partageant la meme source de donnees reutilisent la reponse

import { $ } from '../config.js';
import { apiGet } from '../api.js';
import { translateAllElements } from '../i18n.js';
import { t } from '../translations-bridge.js';
import { getBlockType } from './blocks.js';

export { initUiFramework };
export { buildNavForPages };
export { showConfiguredPage };
export { refreshConfiguredPage };
export { pageAvailabilityChanged };

const pageRegistry = new Map(); // pageId -> {config, element, timer, data, availability}
let configuredPages = [];
let currentPage = "services"; // page 0 par defaut
let showPageCallback = null;

// Applique un "selector" de type "a.0.b" sur la reponse d'un endpoint.
function selectData(data, selector) {
    if (!selector) return data;
    let cur = data;
    for (const part of selector.split(".")) {
        if (cur === null || cur === undefined) return undefined;
        if (/^\d+$/.test(part)) {
            cur = Array.isArray(cur) ? cur[parseInt(part, 10)] : undefined;
        } else {
            cur = (typeof cur === "object") ? cur[part] : undefined;
        }
    }
    return cur;
}

// Regroupe les blocs par endpoint pour ne faire qu'un fetch par cycle.
function groupBlocksByEndpoint(page) {
    const groups = new Map();
    for (const block of page.config.blocks || []) {
        const endpoint = block.datasource && block.datasource.endpoint;
        if (!endpoint) continue;
        if (!groups.has(endpoint)) groups.set(endpoint, []);
        groups.get(endpoint).push(block);
    }
    return groups;
}

async function fetchEndpointOnce(endpoint, cache) {
    if (cache.has(endpoint)) return cache.get(endpoint);
    const promise = apiGet(endpoint).catch(e => ({ ok: false, error: e.message }));
    cache.set(endpoint, promise);
    return promise;
}

async function refreshConfiguredPage(pageId) {
    const page = pageRegistry.get(pageId);
    if (!page || page.refreshing) return;
    page.refreshing = true;
    try {
        const cache = new Map();
        const groups = groupBlocksByEndpoint(page);
        for (const [endpoint, blocks] of groups) {
            const data = await fetchEndpointOnce(endpoint, cache);
            for (const block of blocks) {
                const blockEl = page.element.querySelector(`[data-block-id="${block.id}"]`);
                if (!blockEl) continue;
                const def = getBlockType(block.type);
                if (!def) {
                    blockEl.innerHTML = `<div class="empty">Unknown block type: ${block.type}</div>`;
                    continue;
                }
                const scoped = selectData(data, block.datasource.selector);
                const body = def.render(scoped, block.id);
                const titleEl = blockEl.querySelector(".ems-box-title");
                if (titleEl) titleEl.textContent = def.title();
                const bodyEl = blockEl.querySelector(".ems-block-body");
                if (bodyEl) bodyEl.innerHTML = body;
            }
        }
        translateAllElements();
    } finally {
        page.refreshing = false;
    }
}

function startPageTimer(pageId) {
    const page = pageRegistry.get(pageId);
    if (!page) return;
    const interval = page.config.refresh_interval || 10000;
    page.timer = setTimeout(async () => {
        if (currentPage === pageId && page.available !== false) {
            await refreshConfiguredPage(pageId).catch(() => {});
        }
        if (pageRegistry.get(pageId) === page) startPageTimer(pageId);
    }, interval);
}

// Cree (une fois) les elements DOM d'une page configuree.
function ensurePageElement(pageCfg) {
    let page = pageRegistry.get(pageCfg.id);
    if (page) return page;

    const pageEl = document.createElement("div");
    pageEl.id = `page-${pageCfg.id}`;
    pageEl.className = "page configured-page";
    pageEl.style.display = "none";

    let topBlocks = (pageCfg.blocks || []).filter(b => b.area !== "sources");
    let sourceBlocks = (pageCfg.blocks || []).filter(b => b.area === "sources");

    const topEl = document.createElement("div");
    topEl.className = "ems-top";
    for (const block of topBlocks) {
        topEl.appendChild(createBlockElement(block));
    }
    pageEl.appendChild(topEl);

    if (sourceBlocks.length > 0) {
        const sourcesEl = document.createElement("div");
        sourcesEl.className = "ems-sources";
        for (const block of sourceBlocks) {
            sourcesEl.appendChild(createBlockElement(block));
        }
        pageEl.appendChild(sourcesEl);
    }

    const main = document.querySelector("main");
    main.appendChild(pageEl);

    page = {
        config: pageCfg,
        element: pageEl,
        timer: null,
        refreshing: false,
        available: undefined,
    };
    pageRegistry.set(pageCfg.id, page);
    return page;
}

function createBlockElement(block) {
    const wrapper = document.createElement(block.area === "sources" ? "div" : "div");
    wrapper.className = block.area === "sources" ? "ems-box ems-source-block" : "ems-box";
    wrapper.dataset.blockId = block.id;
    wrapper.innerHTML = `
        <h2 class="ems-box-title"></h2>
        <div class="ems-block-body">
            <div class="empty" data-i18n="ems.loading">Loading...</div>
        </div>
    `;
    return wrapper;
}

// Construit la barre de navigation pour toutes les pages configurees.
// La page 0 (services) reste geree par le HTML statique existant.
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
        // Masque le bouton jusqu'a verification de disponibilite du service.
        if (pageCfg.availability_endpoint) btn.style.display = "none";
        nav.appendChild(btn);
    }
}

// Affiche une page configuree (ou la page 0 services).
function showConfiguredPage(pageId) {
    const pageCfg = configuredPages.find(p => p.id === pageId);
    if (!pageCfg) return false;

    const page = ensurePageElement(pageCfg);

    if (pageCfg.availability_endpoint && page.available === undefined) {
        checkPageAvailability(pageCfg);
    }
    if (page.available === false) return false;
    if (pageCfg.availability_endpoint && page.available !== true) {
        // Disponibilite pas encore confirmee: on affiche la page et la
        // verification en cours corrigera si le service est absent.
    }

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
        refreshConfiguredPage(pageId);
        if (!page.timer) startPageTimer(pageId);
    }

    // Masque les autres pages configurees
    for (const [id, other] of pageRegistry) {
        if (id !== pageId) {
            other.element.style.display = "none";
        }
    }
    return true;
}

async function checkPageAvailability(pageCfg) {
    const page = pageRegistry.get(pageCfg.id);
    if (!page || !pageCfg.availability_endpoint) return;
    try {
        const data = await apiGet(pageCfg.availability_endpoint);
        const available = data && (data.available !== undefined ? data.available : true);
        page.available = available;
        pageAvailabilityChanged(pageCfg.id, available);
    } catch (e) {
        page.available = false;
        pageAvailabilityChanged(pageCfg.id, false);
    }
}

// Met a jour la visibilite du bouton de navigation d'une page.
function pageAvailabilityChanged(pageId, available) {
    const btn = $(`nav-${pageId}`);
    if (btn) btn.style.display = available ? "" : "none";
    if (!available && currentPage === pageId) {
        const fallback = configuredPages.find(p => p.builtin === "services");
        if (fallback) showConfiguredPage(fallback.id);
    }
}

// Initialisation: appele par app.js apres chargement de la configuration.
async function initUiFramework(onShowPage) {
    showPageCallback = onShowPage;
    const { loadUiConfig } = await import("./config.js");
    const cfg = await loadUiConfig();
    buildNavForPages(cfg.pages);
    return cfg;
}
