// Registre des BLOCS: un bloc est lie a une ENTITE et definit une VUE sur
// cette entite (quelles informations afficher et avec quelle representation).
// Chaque bloc expose:
//   title()     -> titre i18n du bloc
//   render(data, blockId) -> HTML complet du bloc pour les donnees recues
// Les blocs sont agences en pages par le framework (js/ui/framework.js) a
// partir de la configuration (js/ui/config.js).

import { escapeHtml } from '../common.js';
import { t } from '../translations-bridge.js';
import { barView, centeredBarView, trendView } from './views.js';
import { getEnergySourceTypeName } from './enums.js';

export { registerBlockType, getBlockType, BLOCK_TYPES };

const BLOCK_TYPES = new Map();

function registerBlockType(typeId, definition) {
    BLOCK_TYPES.set(typeId, definition);
}

function getBlockType(typeId) {
    return BLOCK_TYPES.get(typeId);
}

// Extrait une valeur numerique d'un objet {parsedValue} ou d'une primitive.
function getValue(objOrVal) {
    if (objOrVal && typeof objOrVal === 'object' && objOrVal.parsedValue !== undefined) {
        return objOrVal.parsedValue || 0;
    }
    return objOrVal || 0;
}

// --- Bloc: Energy Controller ------------------------------------------

registerBlockType("energy_controller", {
    title: () => t.t("ems.controller_title"),
    render(data, blockId) {
        if (!data) return `<div class="empty" data-i18n="ems.loading">${t.t("ems.loading")}</div>`;

        const totalPowerHigh = getValue(data.total_power_high) || 1000.0;
        const totalPowerLow = getValue(data.total_power_low) || 200.0;
        const productionPower = getValue(data.production_power);
        const isHighPower = Math.abs(productionPower) > totalPowerLow;
        const scaleTooltip = isHighPower ? 'Power Scale: High' : 'Power Scale: Low';
        const scaleIcon = isHighPower ? '⚡' : '◎';
        const scaleClass = isHighPower ? 'power-scale-icon high' : 'power-scale-icon low';

        let html = `<h2><span data-i18n="ems.controller_title">${escapeHtml(t.t("ems.controller_title"))}</span><span class="${scaleClass}" title="${scaleTooltip}">${scaleIcon}</span></h2>`;
        html += '<div class="ems-bars">';

        const powerMax = (v) => Math.abs(v) > totalPowerLow ? totalPowerHigh : totalPowerLow;

        html += barView(t.t("ems.main_voltage"), getValue(data.main_voltage), "V", "#0000ff", 0, getValue(data.maximum_main_voltage) || 30);
        html += barView(t.t("ems.auxiliary_voltage"), getValue(data.auxiliary_voltage), "V", "#55aaff", 0, getValue(data.maximum_main_voltage) || 30);
        html += barView(t.t("ems.production_power"), productionPower, "W", "#ff9900", 0, powerMax(productionPower));

        const consumptionPower = getValue(data.consumption_power);
        html += barView(t.t("ems.consumption_power"), consumptionPower, "W", "#ff9900", 0, powerMax(consumptionPower));

        const energyStockValue = getValue(data.energy_stock);
        const totalEnergyCapacity = getValue(data.total_energy_capacity) || Math.max(energyStockValue * 1.5, 1000);
        html += barView(t.t("ems.energy_stock"), energyStockValue, "Wh", "#9900ff", 0, totalEnergyCapacity);

        const batteryBalance = getValue(data.battery_balance);
        html += centeredBarView(t.t("ems.battery_balance"), batteryBalance, "W", "#ff9900", powerMax(batteryBalance));

        html += '</div>';
        return html;
    }
});

// --- Bloc: Battery ------------------------------------------------------

registerBlockType("battery", {
    title: () => t.t("ems.battery_title"),
    render(data, blockId) {
        if (!data) return `<div class="empty" data-i18n="ems.loading">${t.t("ems.loading")}</div>`;

        const battery = data;
        const batteryData = battery.battery_data || {};
        const batteryCurrent = getValue(batteryData.current);
        const highPowerScaleAmp = getValue(battery.high_power_scale_amp) || 50.0;
        const lowPowerScaleAmp = getValue(battery.low_power_scale_amp) || 10.0;
        const isHighPower = Math.abs(batteryCurrent) > lowPowerScaleAmp;
        const scaleTooltip = isHighPower ? 'Power Scale: High' : 'Power Scale: Low';
        const scaleIcon = isHighPower ? '⚡' : '◎';
        const scaleClass = isHighPower ? 'power-scale-icon high' : 'power-scale-icon low';

        let html = `<h2><span data-i18n="ems.battery_title">${escapeHtml(t.t("ems.battery_title"))}</span><span class="${scaleClass}" title="${scaleTooltip}">${scaleIcon}</span></h2>`;
        html += '<div class="ems-bars">';

        const currentMax = Math.abs(batteryCurrent) > lowPowerScaleAmp ? highPowerScaleAmp : lowPowerScaleAmp;
        html += centeredBarView(t.t("ems.battery_current"), batteryCurrent, "A", "#ff00ff", currentMax);

        const soc = getValue(batteryData.state_of_charge);
        html += barView(t.t("ems.state_of_charge"), soc, "%", "#ffff00", 0, 100);

        const batteryPower = getValue(batteryData.power);
        const nominalVoltage = getValue(battery.nominal_voltage) || 12.0;
        const highPowerScaleWatt = highPowerScaleAmp * nominalVoltage;
        const lowPowerScaleWatt = lowPowerScaleAmp * nominalVoltage;
        const powerMax = Math.abs(batteryPower) > lowPowerScaleWatt ? highPowerScaleWatt : lowPowerScaleWatt;
        html += centeredBarView(t.t("ems.battery_power"), batteryPower, "W", "#ff9900", powerMax);

        const batteryEnergy = getValue(batteryData.energy);
        const maxEnergy = soc > 0 ? batteryEnergy / (soc / 100.0) : 10000;
        html += barView(t.t("ems.battery_energy"), batteryEnergy, "Wh", "#9900ff", 0, maxEnergy);

        html += '</div>';

        const trend = trendView(battery.trend, `ems-battery-trend-${blockId}`, "state_of_charge", "%");
        if (trend) {
            html += `<div class="ems-trend-title" data-i18n="ems.battery_trend">${escapeHtml(t.t("ems.battery_trend"))}</div>`;
            html += trend;
        }
        return html;
    }
});

// --- Bloc: Energy Source (une entite par bloc) ------------------------
// Utilise avec repeat: true dans la configuration: le framework instancie
// un bloc independant par source, en nombre variable selon les donnees.

registerBlockType("energy_source", {
    title: (source) => (source && source.label) || "",
    render(source, blockId) {
        if (!source) return `<div class="empty" data-i18n="ems.no_sources">${escapeHtml(t.t("ems.no_sources"))}</div>`;

        const sourceData = source.source_data || {};
        const instance = source.instance_id || source.instance || 0;
        const label = source.label || ("Source " + instance);
        const typeName = getEnergySourceTypeName(source.type || 0);

        const current = getValue(sourceData.current);
        const power = getValue(sourceData.power);
        const communicationOk = sourceData.communication_ok !== undefined ? sourceData.communication_ok : true;
        const deviceOn = sourceData.device_on !== undefined ? sourceData.device_on : true;

        let html = '<div class="ems-source-header">';
        html += '<span class="ems-source-title">' + escapeHtml(label) + '</span>';
        html += '<span class="ems-source-type">' + escapeHtml(typeName) + '</span>';
        html += '<span class="ems-source-state">';
        if (!communicationOk) {
            html += '<span class="ems-source-state-indicator grey"></span>';
            html += '<span>' + escapeHtml(t.t("ems.no_communication")) + '</span>';
        } else {
            html += '<span class="ems-source-state-indicator ' + (deviceOn ? '' : 'off') + '"></span>';
            html += '<span>' + escapeHtml(deviceOn ? t.t("ems.on") : t.t("ems.off")) + '</span>';
        }
        html += '</span>';
        html += '</div>';
        html += '<div class="ems-source-body">';
        html += '<div class="ems-source-bars">';
        const sourceCurrentMax = Math.abs(current) > 10.0 ? 50.0 : 10.0;
        html += barView(t.t("ems.current"), Math.abs(current), "A", "#ff00ff", 0, sourceCurrentMax);
        const sourcePowerMax = Math.abs(power) > 100.0 ? 500.0 : 100.0;
        html += barView(t.t("ems.power"), Math.abs(power), "W", "#ff9900", 0, sourcePowerMax);
        html += '</div>';
        html += '<div class="ems-source-trend-container">';
        const trend = trendView(source.trend, `ems-source-trend-${blockId}`, "power", "W");
        if (trend) {
            html += `<div class="ems-trend-title" data-i18n="ems.source_trend">${escapeHtml(t.t("ems.source_trend"))}</div>`;
            html += trend;
        }
        html += '</div>';
        html += '</div>';
        return html;
    }
});
