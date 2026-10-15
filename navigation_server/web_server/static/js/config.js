// État global partagé de l'application.
// Les primitives exportées d'un module ES sont des liaisons en lecture seule:
// l'état mutable est donc exposé via un objet unique, modifiable par propriété.
export const state = {
    autoTimer: null,
    isRefreshing: false,
    autoEnabled: true,
    showHidden: false,
    backendConnected: true,
};

export const REFRESH_INTERVAL = 5000;

export const $ = (id) => document.getElementById(id);
