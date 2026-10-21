// Pont de compatibilite: l'ancienne page EMS monolithique est desormais
// assemblee par le framework page/bloc (js/ui/) a partir de la configuration
// UI. Ce module conserve les exports historiques utilises par app.js et les
// collectors (battery, mppt, dc_dc) pour les tables d'enum.

import {
  getEnergySourceTypeName, getVeErrorName, getVeMpptName, getVeOffReasonName, getVeStateName
} from '../ui/enums.js';
import {
  showConfiguredPage
} from '../ui/framework.js';
import {
  barView as createEmsBar, centeredBarView as createEmsCenteredBar, fmtValue as emsFmt
} from '../ui/views.js';

export { createEmsBar, createEmsCenteredBar, emsFmt };
export { getEnergySourceTypeName, getVeErrorName, getVeMpptName, getVeOffReasonName, getVeStateName };

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

// Le rafraichissement EMS est gere par le framework (timer par page).
export function startEmsRefresh() {}
