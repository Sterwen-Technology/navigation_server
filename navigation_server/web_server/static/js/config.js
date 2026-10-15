export { $ };
export { REFRESH_INTERVAL };
export { autoEnabled };
export { autoTimer };
export { backendConnected };
export { isRefreshing };
export { showHidden };

const REFRESH_INTERVAL = 5000;
let autoTimer = null;
let isRefreshing = false;
let autoEnabled = true;
let showHidden = false;  // Track whether to show hidden processes
let backendConnected = true; // Track if we can reach the web server (network-level)
const $ = (id) => document.getElementById(id);
