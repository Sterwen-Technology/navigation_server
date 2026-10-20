// Registre des VUES: representations reutilisables d'une information.
// Une vue prend une valeur (et ses parametres d'echelle/couleur) et rend du
// HTML. Les blocs (js/ui/blocks.js) composent ces vues pour definir ce qui
// est affiche et comment.

import { escapeHtml, fmt } from '../common.js';

export { barView };
export { centeredBarView };
export { trendView };
export { textView };
export { fmtValue };

function fmtValue(value, unit = "") {
    if (value === 0 || value === null || value === undefined) return "--";
    if (typeof value === "number") {
        if (unit === "W" || unit === "Wh") return value.toFixed(0) + " " + unit;
        if (unit === "A" || unit === "V") return value.toFixed(1) + " " + unit;
        if (unit === "%") return value.toFixed(1) + " " + unit;
        return value.toFixed(2);
    }
    return escapeHtml(value);
}

// Barre unipolaire: remplissage de minVal a maxVal.
function barView(label, value, unit, color, minVal, maxVal) {
    const range = maxVal - minVal;
    const percent = range > 0 ? Math.min(Math.max((value - minVal) / range * 100, 0), 100) : 0;
    return `
    <div class="ems-bar">
        <div class="ems-bar-label">${escapeHtml(label)}</div>
        <div class="ems-bar-container">
            <div class="ems-bar-fill" style="height: ${percent}%; background: ${color}; bottom: 0; width: 100%;"></div>
        </div>
        <div class="ems-bar-value">${fmtValue(value, unit)}</div>
    </div>
`;
}

// Barre centree sur zero: remplissage vers le haut (positif) ou le bas
// (negatif), maxAbsValue correspondant a 50% de la hauteur.
function centeredBarView(label, value, unit, color, maxAbsValue) {
    const absValue = Math.abs(value);
    const percent = Math.min((absValue / maxAbsValue) * 50, 50);
    const isPositive = value >= 0;
    const fillClass = isPositive ? "positive" : "negative";
    const positionStyle = isPositive ? 'bottom: 50%' : 'top: 50%';

    return `
    <div class="ems-bar">
        <div class="ems-bar-label">${escapeHtml(label)}</div>
        <div class="ems-bar-container">
            <div class="ems-bar-fill ${fillClass}" style="height: ${percent}%; background: ${color};"></div>
            <div class="ems-bar-zero-line"></div>
        </div>
        <div class="ems-bar-value">${fmtValue(value, unit)}</div>
    </div>
`;
}

// Courbe de tendance (SVG inline).
function trendView(trend, canvasId, fieldName, unit) {
    if (!trend || !trend.samples || trend.samples.length === 0) return null;

    const values = trend.samples;
    const W = 100, H = 100;
    let dataValues = [];

    if (fieldName === "state_of_charge") {
        dataValues = values.map(v => v.state_of_charge || 0);
    } else {
        dataValues = values.map(v => {
            if (v.power !== undefined) return v.power;
            if (v.panel_power !== undefined) return v.panel_power;
            if (v.current !== undefined && v.voltage !== undefined) return v.current * v.voltage;
            return 0;
        });
    }

    const minVal = Math.min(...dataValues, 0);
    const maxVal = Math.max(...dataValues, 1);
    const range = maxVal - minVal || 1;

    const n = dataValues.length;
    const pts = dataValues.map((val, i) => {
        const x = n === 1 ? W / 2 : (i / (n - 1)) * W;
        const y = H - ((val - minVal) / range) * H;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");

    const area = `0,${H} ${pts} ${W},${H}`;

    return `
    <div class="ems-trend">
        <div class="ems-trend-canvas" id="${canvasId}">
            <svg class="ems-trend-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
                <polygon class="ems-trend-area" points="${area}"/>
                <polyline class="ems-trend-line" points="${pts}" fill="none"/>
            </svg>
            <div class="ems-trend-axis">${fmtValue(maxVal, unit)} max</div>
        </div>
    </div>
`;
}

// Texte simple.
function textView(label, value, unit = "") {
    return `
    <div class="ems-bar">
        <div class="ems-bar-label">${escapeHtml(label)}</div>
        <div class="ems-bar-value">${fmt(value, unit)}</div>
    </div>
`;
}
