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
        'button.retry': 'Retry',
        
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
        'general.per_second': '/s',
        'general.close': 'Close',

        // Error messages
        'error.connection_lost': 'Web server connection lost',

        // Authentication
        'auth.title': 'Sign in',
        'auth.username': 'Username',
        'auth.password': 'Password',
        'auth.signin': 'Sign in',
        'auth.invalid': 'Invalid username or password',
        'auth.error': 'Authentication error',
        'auth.session_expired': 'Session expired, please sign in again',
        
        // Navigation
        'nav.services': 'Services',
        'nav.ems': 'Energy Management System',

        // EMS
        'ems.loading': 'Loading Energy Management System data...',
        'ems.error': 'Error loading EMS data',
        'ems.no_sources': 'No energy sources.',
        'ems.controller_title': 'Energy Controller',
        'ems.battery_title': 'Battery',
        'ems.main_voltage': 'Main Voltage',
        'ems.auxiliary_voltage': 'Auxiliary Voltage',
        'ems.production_power': 'Production',
        'ems.consumption_power': 'Consumption',
        'ems.energy_stock': 'Energy Stock',
        'ems.battery_balance': 'Battery Balance',
        'ems.battery_current': 'Current',
        'ems.state_of_charge': 'State of Charge',
        'ems.battery_power': 'Power',
        'ems.battery_energy': 'Energy',
        'ems.battery_trend': 'Battery Trend',
        'ems.source_trend': 'Trend',
        'ems.current': 'Current',
        'ems.power': 'Power',
        'ems.on': 'ON',
        'ems.off': 'OFF',
        'ems.no_communication': 'NO COM',
        'ems.type_0': 'Battery',
        'ems.type_1': 'Solar',
        'ems.type_2': 'Alternator',
        'ems.type_3': 'AC Charger',
        'ems.type_4': 'DC-DC Charger',
        'ems.type_5': 'Windmill',
        'ems.type_6': 'Hydro Generator',
        'ems.type_7': 'AC Generator',
        'ems.type_8': 'AC-DC Converter',

        // Engine
        'engine.title': 'Engine Data',
        'engine.voltage': 'Voltage',
        'engine.temperature': 'Temperature',
        'engine.total_hours': 'Total Hours',
        'engine.last_start': 'Last Start',
        'engine.last_stop': 'Last Stop',
        'engine.history': 'History',
        'engine.show_runs': 'Show Runs',
        'engine.show_events': 'Show Events',
        'engine.no_engines': 'No engines found.',
        'engine.no_runs': 'No runs found.',
        'engine.no_events': 'No events found.',
        'engine.start_time': 'Start Time',
        'engine.stop_time': 'Stop Time',
        'engine.duration_min': 'Duration (min)',
        'engine.avg_speed': 'Avg Speed',
        'engine.max_speed': 'Max Speed',
        'engine.time': 'Time',
        'engine.from_state': 'From',
        'engine.to_state': 'To',
        'engine.state_engine_off': 'Off',
        'engine.state_engine_on': 'On',
        'engine.state_engine_running': 'Running',
        'engine.state_stopped': 'Stopped',

        // MPPT (solar charge controller)
        'mppt.title': 'MPPT',
        'mppt.product': 'Product',
        'mppt.device_label': 'Label',
        'mppt.device_model': 'Model',
        'mppt.firmware': 'Firmware',
        'mppt.serial': 'Serial',
        'mppt.error': 'Error',
        'mppt.state': 'State',
        'mppt.mppt_state': 'MPPT',
        'mppt.day_max_power': 'Day max power',
        'mppt.day_power': 'Day energy',
        'mppt.details': 'Device details',
        'mppt.com_lost': 'Communication lost',
        'mppt.no_trend': 'No trend (communication lost)',
        'mppt.panel_voltage': 'Panel V',
        'mppt.voltage': 'Voltage',
        'mppt.current': 'Current',
        'mppt.panel_power': 'Panel P',
        'mppt.trend': 'Power trend',
        'mppt.trend_power': 'Panel power (W)',
        'mppt.no_trend': 'No trend data',

        // Battery
        'battery.title': 'Battery',
        'battery.device_model': 'Model',
        'battery.nominal_capacity': 'Nominal Capacity',
        'battery.nominal_voltage': 'Nominal Voltage',
        'battery.voltage': 'Voltage',
        'battery.current': 'Current',
        'battery.power': 'Power',
        'battery.state_of_charge': 'State of Charge',
        'battery.energy': 'Energy',
        'battery.details': 'Details',
        'battery.trend': 'Power Trend',
        'battery.label': 'Label'
    },
    fr: {
        // Navigation
        'nav.services': 'Services',
        'nav.ems': 'Système de Gestion d\'Énergie',

        // EMS
        'ems.loading': 'Chargement des données du système de gestion d\'énergie...',
        'ems.error': 'Erreur lors du chargement des données EMS',
        'ems.no_sources': 'Aucune source d\'énergie.',
        'ems.controller_title': 'Contrôleur Énergétique',
        'ems.battery_title': 'Batterie',
        'ems.main_voltage': 'Tension Principale',
        'ems.auxiliary_voltage': 'Tension Auxiliaire',
        'ems.production_power': 'Production',
        'ems.consumption_power': 'Consommation',
        'ems.energy_stock': 'Stock Énergétique',
        'ems.battery_balance': 'Équilibre Batterie',
        'ems.battery_current': 'Courant',
        'ems.state_of_charge': 'État de Charge',
        'ems.battery_power': 'Puissance',
        'ems.battery_energy': 'Énergie',
        'ems.battery_trend': 'Tendance Batterie',
        'ems.source_trend': 'Tendance',
        'ems.current': 'Courant',
        'ems.power': 'Puissance',
        'ems.on': 'ON',
        'ems.off': 'OFF',
        'ems.no_communication': 'PAS DE COM',
        'ems.type_0': 'Batterie',
        'ems.type_1': 'Solaire',
        'ems.type_2': 'Alternateur',
        'ems.type_3': 'Chargeur CA',
        'ems.type_4': 'Chargeur CC-CC',
        'ems.type_5': 'Éolienne',
        'ems.type_6': 'Générateur Hydro',
        'ems.type_7': 'Générateur CA',
        'ems.type_8': 'Convertisseur CA-CC',

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
        'button.retry': 'Reessayer',
        
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
        'general.per_second': '/s',
        'general.close': 'Fermer',

        // Error messages
        'error.connection_lost': 'Connexion au serveur web perdue',

        // Authentication
        'auth.title': 'Connexion',
        'auth.username': 'Utilisateur',
        'auth.password': 'Mot de passe',
        'auth.signin': 'Se connecter',
        'auth.invalid': 'Utilisateur ou mot de passe invalide',
        'auth.error': 'Erreur d\'authentification',
        'auth.session_expired': 'Session expiree, veuillez vous reconnecter',
        
        // Engine
        'engine.title': 'Donnees moteur',
        'engine.voltage': 'Tension',
        'engine.temperature': 'Temperature',
        'engine.total_hours': 'Heures totales',
        'engine.last_start': 'Dernier demarrage',
        'engine.last_stop': 'Dernier arret',
        'engine.history': 'Historique',
        'engine.show_runs': 'Afficher les runs',
        'engine.show_events': 'Afficher les evenements',
        'engine.no_engines': 'Aucun moteur trouve.',
        'engine.no_runs': 'Aucun run trouve.',
        'engine.no_events': 'Aucun evenement trouve.',
        'engine.start_time': 'Debut',
        'engine.stop_time': 'Fin',
        'engine.duration_min': 'Duree (min)',
        'engine.avg_speed': 'Vitesse moy',
        'engine.max_speed': 'Vitesse max',
        'engine.time': 'Heure',
        'engine.from_state': 'De',
        'engine.to_state': 'Vers',
        'engine.state_engine_off': 'Arrete',
        'engine.state_engine_on': 'Allume',
        'engine.state_engine_running': 'En marche',
        'engine.state_stopped': 'Stoppé',

        // MPPT (solar charge controller)
        'mppt.title': 'MPPT',
        'mppt.product': 'Produit',
        'mppt.device_label': 'Libelle',
        'mppt.device_model': 'Modele',
        'mppt.firmware': 'Firmware',
        'mppt.serial': 'Serie',
        'mppt.error': 'Erreur',
        'mppt.state': 'Etat',
        'mppt.mppt_state': 'MPPT',
        'mppt.day_max_power': 'Puissance max jour',
        'mppt.day_power': 'Energie jour',
        'mppt.details': 'Détails appareil',
        'mppt.com_lost': 'Communication perdue',
        'mppt.no_trend': 'Pas de tendance (communication perdue)',
        'mppt.panel_voltage': 'V panneau',
        'mppt.voltage': 'Tension',
        'mppt.current': 'Courant',
        'mppt.panel_power': 'P panneau',
        'mppt.trend': 'Tendance puissance',
        'mppt.trend_power': 'Puissance panneau (W)',
        'mppt.no_trend': 'Pas de tendance',

        // Battery
        'battery.title': 'Batterie',
        'battery.device_model': 'Modèle',
        'battery.nominal_capacity': 'Capacité Nominale',
        'battery.nominal_voltage': 'Tension Nominale',
        'battery.voltage': 'Tension',
        'battery.current': 'Courant',
        'battery.power': 'Puissance',
        'battery.state_of_charge': "État de Charge",
        'battery.energy': 'Énergie',
        'battery.details': 'Détails',
        'battery.trend': 'Tendance de Puissance',
        'battery.label': 'Étiquette'
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
// Export to global scope for access from inline scripts
window.t = t;

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
        // Don't throw for non-OK responses - just use default language
    } catch (e) {
        console.debug('Could not fetch language from server config, using default (en):', e);
        // Don't mark config errors as connection errors
        // Don't re-throw - language config failure shouldn't break the page
    }
}

// Initialize translations when the page loads
document.addEventListener('DOMContentLoaded', initWebTranslations);
