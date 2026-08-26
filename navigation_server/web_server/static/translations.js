// Navigation Server Web Interface Translations
// This file provides multilingual support for the web interface
// Language is determined by the server configuration (language parameter in YAML)

const TRANSLATIONS = {
    en: {
        // Connection status
        'status.connected': 'connected',
        'status.disconnected': 'disconnected',
        
        // Header
        'header.title': 'Navigation Server',
        'header.agent': 'agent: {address}',
        
        // Buttons (trivial ones stay in English as per requirements)
        'button.refresh': 'Refresh',
        'button.start': 'Start',
        'button.stop': 'Stop',
        'button.restart': 'Restart',
        'button.halt': 'Halt',
        'button.reboot': 'Reboot',
        'button.apply': 'Apply',
        'button.close': 'Close',
        'button.back': 'Back',
        
        // Auto-refresh
        'auto_refresh.label': 'Auto refresh (5s)',
        
        // Main page
        'main.no_data': 'No data. Click ↻ to refresh.',
        'main.no_processes': 'No processes registered.',
        
        // System summary
        'system.host': 'Host',
        'system.ip_address': 'IP Address',
        'system.started': 'Started',
        'system.configuration': 'Configuration',
        'system.restart_app': 'Restart App',
        
        // Process states
        'state.RUNNING': 'RUNNING',
        'state.STOPPED': 'STOPPED',
        'state.NOT_STARTED': 'NOT STARTED',
        'state.SUSPENDED': 'SUSPENDED',
        
        // Process card
        'process.pid': 'PID',
        'process.grpc_port': 'gRPC Port',
        'process.version': 'Version',
        'process.started': 'Started',
        'process.status': 'Status',
        'process.error': 'Error',
        'process.control': 'Control',
        'process.systemd': 'systemd',
        
        // Server info
        'server.running': 'running',
        'server.stopped': 'stopped',
        'server.connections': 'conn.',
        
        // Coupler info
        'coupler.class': 'Class',
        'coupler.protocol': 'Protocol',
        'coupler.device_state': 'Device State',
        'coupler.msg_in_out': 'Msg in/out',
        'coupler.rate_in_out': 'Rate in/out',
        'coupler.trace': 'Trace',
        'coupler.activated': 'activated',
        'coupler.inactive': 'inactive',
        
        // Console
        'console.title': 'Console',
        'console.servers': 'TCP/UDP Servers',
        'console.couplers': 'Couplers',
        'console.no_servers': 'No servers.',
        'console.no_couplers': 'No couplers.',
        'console.start_stream': 'Click Start to start the log stream...',
        'console.stream_started': '--- Stream started ---',
        'console.stream_stopped': '--- Stream stopped ---',
        
        // Network
        'network.title': 'Network Configuration',
        'network.nm_status': 'NetworkManager',
        'network.nm_active': 'active',
        'network.nm_inactive': 'inactive',
        'network.global_configs': 'Global Configurations',
        'network.apply_config': 'Apply configuration "{config}" ?',
        'network.interfaces': 'Interfaces',
        'network.no_interfaces': 'No interfaces.',
        
        // NMEA2000
        'nmea2000.title': 'NMEA2000',
        'nmea2000.controller': 'NMEA2000 Controller',
        'nmea2000.channel': 'Channel',
        'nmea2000.status': 'Status',
        'nmea2000.incoming': 'Incoming',
        'nmea2000.outgoing': 'Outgoing',
        'nmea2000.devices': 'Devices',
        'nmea2000.no_devices': 'No NMEA2000 devices.',
        'nmea2000.device': 'NMEA2000 Device',
        'nmea2000.address': 'Address',
        'nmea2000.proxy': 'Proxy',
        'nmea2000.manufacturer': 'Manufacturer',
        'nmea2000.product': 'Product',
        'nmea2000.pgn_stats': 'PGN Statistics',
        'nmea2000.incoming_label': 'Incoming',
        'nmea2000.outgoing_label': 'Outgoing',
        'nmea2000.start_trace': 'Start Trace',
        'nmea2000.stop_trace': 'Stop Trace',
        
        // System commands
        'command.halt_confirm': 'Confirm: stop the system?',
        'command.reboot_confirm': 'Confirm: reboot the system?',
        'command.navigation_restart_confirm': 'Confirm: restart ALL processes (including the agent)?',
        
        // Toast messages
        'toast.refresh_error': 'Refresh error: {error}',
        'toast.error': 'Error: {error}',
        'toast.ok': 'OK',
        'toast.failure': 'failure',
        
        // Log
        'log.title': 'Logs',
        'log.start': 'Start',
        'log.stop': 'Stop',
        
        // General
        'general.loading': 'Loading...',
        'general.empty': 'None',
        'general.not_connected': 'Not connected',
        'general.unknown': 'Unknown',
        'general.msg': 'msg',
        'general.per_second': '/s'
    },
    fr: {
        // Connection status
        'status.connected': 'connecte',
        'status.disconnected': 'deconnecte',
        
        // Header
        'header.title': 'Navigation Server',
        'header.agent': 'agent: {address}',
        
        // Buttons (trivial ones stay in English as per requirements)
        'button.refresh': 'Rafraichir',
        'button.start': 'Start',
        'button.stop': 'Stop',
        'button.restart': 'Restart',
        'button.halt': 'Halt',
        'button.reboot': 'Reboot',
        'button.apply': 'Appliquer',
        'button.close': 'Fermer',
        'button.back': 'Retour',
        
        // Auto-refresh
        'auto_refresh.label': 'Rafraich. auto (5s)',
        
        // Main page
        'main.no_data': 'Aucune donnee. Cliquez sur ↻ pour rafraichir.',
        'main.no_processes': 'Aucun processus enregistre.',
        
        // System summary
        'system.host': 'Hote',
        'system.ip_address': 'Adresse IP',
        'system.started': 'Demarre le',
        'system.configuration': 'Configuration',
        'system.restart_app': 'Redemarrer App',
        
        // Process states
        'state.RUNNING': 'RUNNING',
        'state.STOPPED': 'STOPPED',
        'state.NOT_STARTED': 'NOT STARTED',
        'state.SUSPENDED': 'SUSPENDED',
        
        // Process card
        'process.pid': 'PID',
        'process.grpc_port': 'Port gRPC',
        'process.version': 'Version',
        'process.started': 'Demarre',
        'process.status': 'Statut',
        'process.error': 'Erreur',
        'process.control': 'Controle',
        'process.systemd': 'systemd',
        
        // Server info
        'server.running': 'running',
        'server.stopped': 'stopped',
        'server.connections': 'conn.',
        
        // Coupler info
        'coupler.class': 'Classe',
        'coupler.protocol': 'Protocole',
        'coupler.device_state': 'Etat device',
        'coupler.msg_in_out': 'Msg in/out',
        'coupler.rate_in_out': 'Debit in/out',
        'coupler.trace': 'Trace',
        'coupler.activated': 'activee',
        'coupler.inactive': 'inactive',
        
        // Console
        'console.title': 'Console',
        'console.servers': 'Serveurs TCP/UDP',
        'console.couplers': 'Coupleurs',
        'console.no_servers': 'Aucun serveur.',
        'console.no_couplers': 'Aucun coupleur.',
        'console.start_stream': 'Cliquez sur Start pour demarrer le flux de logs...',
        'console.stream_started': '--- Flux demarre ---',
        'console.stream_stopped': '--- Flux arrete ---',
        
        // Network
        'network.title': 'Configuration reseau',
        'network.nm_status': 'NetworkManager',
        'network.nm_active': 'actif',
        'network.nm_inactive': 'inactif',
        'network.global_configs': 'Configurations globales',
        'network.apply_config': 'Appliquer la configuration reseau "{config}" ?',
        'network.interfaces': 'Interfaces',
        'network.no_interfaces': 'Aucune interface.',
        
        // NMEA2000
        'nmea2000.title': 'NMEA2000',
        'nmea2000.controller': 'NMEA2000 Controller',
        'nmea2000.channel': 'Channel',
        'nmea2000.status': 'Status',
        'nmea2000.incoming': 'Incoming',
        'nmea2000.outgoing': 'Outgoing',
        'nmea2000.devices': 'Devices',
        'nmea2000.no_devices': 'No NMEA2000 devices.',
        'nmea2000.device': 'NMEA2000 Device',
        'nmea2000.address': 'Address',
        'nmea2000.proxy': 'Proxy',
        'nmea2000.manufacturer': 'Manufacturer',
        'nmea2000.product': 'Product',
        'nmea2000.pgn_stats': 'PGN Statistics',
        'nmea2000.incoming_label': 'Incoming',
        'nmea2000.outgoing_label': 'Outgoing',
        'nmea2000.start_trace': 'Start Trace',
        'nmea2000.stop_trace': 'Stop Trace',
        
        // System commands
        'command.halt_confirm': 'Confirmer : arreter le systeme ?',
        'command.reboot_confirm': 'Confirmer : redemarrer le systeme ?',
        'command.navigation_restart_confirm': 'Confirmer : redemarrer TOUS les processus (y compris l\'agent) ?',
        
        // Toast messages
        'toast.refresh_error': 'Erreur de rafraichissement : {error}',
        'toast.error': 'Erreur: {error}',
        'toast.ok': 'OK',
        'toast.failure': 'echec',
        
        // Log
        'log.title': 'Logs',
        'log.start': 'Start',
        'log.stop': 'Stop',
        
        // General
        'general.loading': 'Chargement...',
        'general.empty': 'Aucun',
        'general.not_connected': 'Non connecte',
        'general.unknown': 'Inconnu',
        'general.msg': 'msg',
        'general.per_second': '/s'
    }
};

// Translation manager
class WebTranslationManager {
    constructor() {
        this.currentLanguage = 'en'; // Default to English
        this.translations = TRANSLATIONS;
    }
    
    setLanguage(lang) {
        if (this.translations[lang]) {
            this.currentLanguage = lang;
            console.log('Web UI language set to:', lang);
            this.translateAllElements();
        } else {
            console.warn('Language not supported:', lang, 'Falling back to English');
            this.currentLanguage = 'en';
        }
    }
    
    getLanguage() {
        return this.currentLanguage;
    }
    
    translate(key, ...args) {
        const langTranslations = this.translations[this.currentLanguage];
        if (!langTranslations) {
            return key;
        }
        
        let translation = langTranslations[key];
        if (translation === undefined) {
            // Fallback to English
            if (this.currentLanguage !== 'en' && this.translations.en) {
                translation = this.translations.en[key];
            }
            if (translation === undefined) {
                console.debug('Translation not found for key:', key);
                return key;
            }
        }
        
        // Replace placeholders
        if (args.length > 0) {
            for (let i = 0; i < args.length; i++) {
                translation = translation.replace(`{${i}}`, args[i]);
            }
            // Also support named placeholders
            if (args[0] && typeof args[0] === 'object') {
                for (const [name, value] of Object.entries(args[0])) {
                    translation = translation.replace(`{${name}}`, value);
                }
            }
        }
        
        return translation;
    }
    
    // Convenience method
    t(key, ...args) {
        return this.translate(key, ...args);
    }
    translateAllElements() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (key) el.textContent = this.t(key);
        });
        document.querySelectorAll('[data-i18n-text]').forEach(el => {
            const key = el.getAttribute('data-i18n-text');
            if (key) el.textContent = this.t(key);
        });
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            if (key) el.title = this.t(key);
        });
    }
}

// Global translation manager instance
const t = new WebTranslationManager();

// Function to format a value (from the original code)
function fmt(v) {
    return v === 0 || v ? escapeHtml(v) : "--";
}

// Function to escape HTML (from the original code)
function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

// Initialize translation from server configuration
async function initWebTranslations() {
    try {
        const configResponse = await fetch('/api/config', { cache: 'no-store' });
        if (configResponse.ok) {
            const config = await configResponse.json();
            if (config.language) {
                t.setLanguage(config.language);
            }
        }
    } catch (e) {
        console.debug('Could not fetch language from server config, using default (en):', e);
    }
}

// Initialize translations when the page loads
document.addEventListener('DOMContentLoaded', initWebTranslations);
