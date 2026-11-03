// Pont de compatibilite: l'ancienne page EMS monolithique est desormais
// assemblee par le framework page/bloc (js/ui/) a partir de la configuration
// UI (schema doc/web_ui_modular.md section 2). Ce module conserve l'export
// showPage utilise par app.js et le HTML statique.

import {
  showConfiguredPage
} from '../ui/framework.js';

export { getEnergySourceTypeName, getVeErrorName, getVeMpptName, getVeOffReasonName, getVeStateName } from '../ui/enums.js';

// Affiche une page (page 0 "services" ou page configuree).
export function showPage(page) {
    if (page === "services") {
        showConfiguredPage("services");
        return;
    }
    if (!showConfiguredPage(page)) {
        // Page inconnue ou indisponible: retour a la page 0.
        showConfiguredPage("services");
    }
}
