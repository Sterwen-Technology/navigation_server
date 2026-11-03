// Configuration UI: chargement et acces normalise (doc/web_ui_modular.md
// section 2). Le serveur sert la configuration sur /api/ui_config (module
// web_server/ui_config.py, qui charge et valide le YAML au demarrage).
// Le DEFAULT embarque ci-dessous est un filet de securite uniquement - il
// reprend le fichier de reference conf/web_ui_default.yml.

export const STANDARD_DATASETS = ["parameters", "data", "trend"];

export const DEFAULT_UI_CONFIG = {
    version: 2,
    colors: {
        voltage: "#0000ff",
        auxiliary_voltage: "#55aaff",
        power: "#ff9900",
        current: "#ff00ff",
        state_of_charge: "#ffff00",
        energy: "#9900ff",
    },
    widgets: [
        { id: "voltage_viewgraph", base_widget: "positive_viewgraph", unit: "V", precision: 2, color: "voltage", scale: { type: "fixed", max: "parameters/max_voltage_scale" } },
        { id: "auxiliary_voltage_viewgraph", base_widget: "positive_viewgraph", unit: "V", precision: 2, color: "auxiliary_voltage", scale: { type: "fixed", max: "parameters/max_voltage_scale" } },
        { id: "production_viewgraph", base_widget: "positive_viewgraph", unit: "W", precision: 0, color: "power", scale: { type: "dual", low: "parameters/total_power_low", high: "parameters/total_power_high" } },
        { id: "power_balance", base_widget: "symmetric_viewgraph", unit: "W", precision: 0, color: "power", scale: { type: "dual", low: "parameters/total_power_low", high: "parameters/total_power_high" } },
        { id: "power_balance_trend", base_widget: "single_symmetric_curve", scale: { type: "dynamic" } },
        { id: "state_of_charge_viewgraph", base_widget: "positive_viewgraph", unit: "%", precision: 1, color: "state_of_charge", ratio_percent: true, scale: { type: "fixed", max: 100 } },
        { id: "energy_stock_viewgraph", base_widget: "positive_viewgraph", unit: "Wh", precision: 0, color: "energy", scale: { type: "fixed", max: "parameters/total_energy_capacity" } },
        { id: "production_current_viewgraph", base_widget: "positive_viewgraph", unit: "A", precision: 1, color: "current", scale: { type: "fixed", max: 50 } },
        { id: "power_trend", base_widget: "single_positive_curve", scale: { type: "dynamic" } },
    ],
    block_types: [
        {
            id: "energy_source",
            title: "parameters/label",
            top_widget: "communication_indicator",
            definition: [
                { view: "current", title: "Current", data: "data/current", widget: "production_current_viewgraph" },
                { view: "power", title: "Power", data: "data/power", widget: "production_viewgraph" },
                { view: "power_trend", title: "Power trend", data: "trend/power", widget: "power_trend" },
            ],
        },
    ],
    pages: [
        { id: "services", title_i18n: "nav.services", builtin: "services", optional: false },
        {
            id: "ems",
            title_i18n: "nav.ems",
            layout: { columns: 2 },
            refresh_interval: 10000,
            availability_endpoint: "/api/energy_available",
            parameters_endpoint: "/api/energy/0/parameters",
            blocks: [
                {
                    id: "energy_summary", title: "Energy Controller", priority: 1,
                    position: { row: 0, column: 0 }, width: 2, endpoint: "/api/energy/0/data",
                    definition: [
                        { view: "main_voltage", title: "Main Voltage", data: "data/main_voltage", widget: "voltage_viewgraph" },
                        { view: "auxiliary_voltage", title: "Auxiliary Voltage", data: "data/auxiliary_voltage", widget: "auxiliary_voltage_viewgraph" },
                        { view: "production_power", title: "Production", data: "data/production_power", widget: "production_viewgraph" },
                        { view: "battery_power_balance", title: "Battery power", data: "data/battery_balance", widget: "power_balance" },
                        { view: "state_of_charge", title: "State of charge", data: "data/state_of_charge", widget: "state_of_charge_viewgraph" },
                        { view: "energy_stock", title: "Energy stock", data: "data/energy_stock", widget: "energy_stock_viewgraph" },
                        { view: "power_balance_trend", title: "Battery balance trend", data: "trend/battery_balance", widget: "power_balance_trend" },
                    ],
                },
                {
                    id: "energy-sources", type: "energy_source", priority: 2,
                    repeat: { source_endpoint: "/api/energy/0/parameters/sources", block_endpoint: "/api/{service}/{instance}" },
                },
            ],
        },
    ],
};

// Charge la configuration UI: /api/ui_config (deja validee au demarrage par
// le backend), repli sur la configuration embarquee si le serveur n'en sert
// pas (404) ou si la reponse est incoherente.
export async function loadUiConfig() {
    try {
        const resp = await fetch("/api/ui_config", { cache: "no-store", credentials: "include" });
        if (resp.ok) {
            const cfg = await resp.json();
            if (cfg && Array.isArray(cfg.pages) && cfg.pages.length > 0) {
                return cfg;
            }
        }
    } catch (e) {
        console.warn("No server UI configuration, using embedded default:", e);
    }
    return DEFAULT_UI_CONFIG;
}
