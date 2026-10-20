// Configuration UI par défaut: structure en pages -> blocs -> vues.
//
// Concepts:
//   - Une PAGE est un ensemble de blocs.
//   - Un BLOC est lie a une ENTITE et a une VUE sur cette entite.
//   - La VUE definit les informations affichees et leur representation
//     (barre, barre centree, courbe, texte...).
//   - Chaque entite correspond a un data collector du backend, lui-meme
//     adosse a un service gRPC.
//
// Cette configuration peut etre remplacee au demarrage du serveur web par un
// fichier fourni via l'option --ui-config (servi sur /api/ui_config).
//
// Schema d'un bloc:
//   {
//     id:        identifiant unique du bloc dans la page
//     type:      type de bloc enregistre dans le registre (js/ui/blocks.js)
//     entity:    nom de l'entite concernee (batterie, mppt, controleur...)
//     area:      zone de mise en page ("top", "sources"...)
//     datasource: { endpoint: chemin API, selector: chemin dans la reponse }
//   }

export const DEFAULT_UI_CONFIG = {
    version: 1,
    pages: [
        {
            id: "services",
            title_i18n: "nav.services",
            builtin: "services",
            optional: false,
        },
        {
            id: "ems",
            title_i18n: "nav.ems",
            refresh_interval: 10000,
            availability_endpoint: "/api/energy_available",
            blocks: [
                {
                    id: "energy-controller",
                    type: "energy_controller",
                    entity: "energy_controller",
                    area: "top",
                    datasource: { endpoint: "/api/energy" },
                },
                {
                    id: "battery",
                    type: "battery",
                    entity: "battery",
                    area: "top",
                    datasource: { endpoint: "/api/energy", selector: "batteries.0" },
                },
                {
                    id: "energy-sources",
                    type: "energy_source",
                    entity: "energy_source",
                    area: "sources",
                    repeat: true,
                    datasource: { endpoint: "/api/energy", selector: "sources" },
                },
            ],
        },
    ],
};

// Charge la configuration UI: /api/ui_config si le serveur en fournit une,
// sinon la configuration par defaut embarquee.
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
        console.warn("No server UI configuration, using default:", e);
    }
    return DEFAULT_UI_CONFIG;
}
