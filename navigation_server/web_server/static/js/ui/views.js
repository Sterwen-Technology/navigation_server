// Base widgets (rendus elementaires codes en dur) - doc/web_ui_modular.md
// section 5.4. Les widgets de la configuration (section widgets du YAML)
// parametrent ces rendus: unite, precision, couleur, echelle, ratio.
//
// Un base widget recoit un contexte normalise:
//   { label, value, series, unit, precision, colorCss, max, scaleLow,
//     scaleHigh, symmetric, ratioPercent }
// et rend le HTML de la vue.

import { escapeHtml } from '../common.js';

export { BASE_WIDGETS };
export { fmtValue };
export { resolveColor };
export { renderWidget };

const BASE_WIDGET_IDS = [
    "positive_viewgraph", "symmetric_viewgraph",
    "single_positive_curve", "single_symmetric_curve",
    "communication_indicator",
];

// --- Helpers ---------------------------------------------------------------

function fmtValue(value, unit = "", precision = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
    const n = Number(value);
    const fixed = n.toFixed(precision ?? 0);
    return `${fixed}${unit ? " " + unit : ""}`;
}

// Couleur: reference a la palette (nom) ou valeur CSS directe.
function resolveColor(colorRef, palette) {
    if (!colorRef) return "#334155";
    if (palette && palette[colorRef]) return palette[colorRef];
    return colorRef;
}

// Ratio 0-1 (convention protobuf) affiche en pourcentage - la conversion
// est de la responsabilite du widget, jamais du transport (doc section 4).
function displayValue(value, ratioPercent) {
    if (value === null || value === undefined) return value;
    const n = Number(value);
    return ratioPercent ? n * 100.0 : n;
}

// --- Viewgraphs (barres) ----------------------------------------------------
// Barre 0 en bas (positive) ou barre centree sur 0 (symmetric).
// Rendu identique a la version historique (classes CSS .ems-bar*).

function viewgraphHtml(ctx) {
    const value = displayValue(ctx.value, ctx.ratioPercent);
    const absValue = Math.abs(value || 0);
    let percent;
    if (ctx.symmetric) {
        percent = Math.min((absValue / (ctx.max || 1)) * 50, 50);
    } else {
        const range = ctx.max || 1;
        percent = Math.min(Math.max((absValue / range) * 100, 0), 100);
    }
    const isPositive = value >= 0;
    const fillClass = ctx.symmetric ? (isPositive ? "positive" : "negative") : "";
    // Symmetric viewgraph: 0 line in the middle - positive values grow
    // from the middle up (bottom: 50%), negative from the middle down
    // (top: 50%). Positive viewgraph: 0 at the bottom.
    const positionStyle = !ctx.symmetric ? 'bottom: 0' : (isPositive ? 'bottom: 50%' : 'top: 50%');

    return `
    <div class="ems-bar">
        <div class="ems-bar-label">${escapeHtml(ctx.label)}</div>
        <div class="ems-bar-container">
            <div class="ems-bar-fill ${fillClass}" style="height: ${percent}%; background: ${ctx.colorCss}; ${positionStyle}; width: 100%;"></div>
            ${ctx.symmetric ? '<div class="ems-bar-zero-line"></div>' : ''}
        </div>
        <div class="ems-bar-value">${fmtValue(value, ctx.unit, ctx.precision)}</div>
    </div>
`;
}

// --- Courbes ----------------------------------------------------------------
// Serie temporelle en SVG inline, sans axes (doc section 5.2).
// Echelle dynamic: recalculee sur la serie (min/max observes).

function curveHtml(ctx) {
    const series = (ctx.series || []).map(v => displayValue(v, ctx.ratioPercent));
    const W = 100, H = 100;
    if (!series.length) {
        return `<div class="ems-trend-canvas empty-curve">--</div>`;
    }
    const minVal = ctx.symmetric ? Math.min(...series, 0) : Math.min(...series, 0);
    const maxVal = Math.max(...series, 1);
    const range = maxVal - minVal || 1;
    const n = series.length;
    const pts = series.map((val, i) => {
        const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
        const y = H - ((val - minVal) / range) * H;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    const area = `0,${H} ${pts} ${W},${H}`;

    return `
    <div class="ems-trend-canvas" style="border-color:${ctx.colorCss}; border-width:1px; border-style:solid;">
        <svg class="ems-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
            <polygon class="ems-trend-area" points="${area}"/>
            <polyline class="ems-trend-line" points="${pts}" fill="none"/>
        </svg>
        <div class="ems-trend-axis">${fmtValue(maxVal, ctx.unit, 0)} max</div>
    </div>
`;
}

// --- Indicateur de communication (top_widget) -------------------------------

function communicationIndicatorHtml(ctx) {
    const ok = ctx.value !== false;
    return `<span class="ems-source-state-indicator ${ok ? '' : 'off'}"></span>`;
}

// --- Registre des base widgets ----------------------------------------------

const BASE_WIDGETS = {
    positive_viewgraph: (ctx) => viewgraphHtml({ ...ctx, symmetric: false }),
    symmetric_viewgraph: (ctx) => viewgraphHtml({ ...ctx, symmetric: true }),
    single_positive_curve: curveHtml,
    single_symmetric_curve: curveHtml,
    communication_indicator: communicationIndicatorHtml,
};

// Rend un widget parametre (definition de la section widgets) dans un contexte
// deja normalise par le framework (valeur ou serie + echelle resolue).
function renderWidget(widgetDef, ctx) {
    const renderer = BASE_WIDGETS[widgetDef.base_widget];
    if (!renderer) {
        return `<div class="empty">Unknown base widget: ${escapeHtml(widgetDef.base_widget || "")}</div>`;
    }
    return renderer(ctx);
}
