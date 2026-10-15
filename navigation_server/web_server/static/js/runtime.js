// Indirection pour casser les cycles d'imports (ES modules tolèrent les
// cycles pour les appels différés, mais on rend ici le couplage explicite).
let _refresh = null;
let _showPage = null;

export function setRefresh(fn) { _refresh = fn; }
export function getRefresh() { return _refresh; }
export function setShowPage(fn) { _showPage = fn; }
export function getShowPage() { return _showPage; }
