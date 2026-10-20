# Web UI — Architecture modulaire page / bloc

## 1. Concepts formalisés

L'interface Web est organisée selon une modularité à deux niveaux :

| Concept | Définition |
|---|---|
| **Page** | Un ensemble de blocs. La page est l'unité de navigation (barre de navigation). |
| **Bloc** | Lié à une **entité** ; définit une **vue** sur cette entité (quelles informations sont affichées). |
| **Vue** | La représentation des informations : texte, barre, barre centrée, courbe de tendance... |
| **Entité** | Un concept applicatif (contrôleur d'énergie, batterie, source d'énergie, MPPT, chargeur DC-DC, moteur...). Chaque entité correspond à un **data collector** du backend, lui-même adossé à un **service gRPC**. |

Chaîne de responsabilité complète :

```
Page (ex: Energy Management)
  └─ Bloc (ex: "battery") — lié à l'entité "battery"
       └─ Vue (barre centrée, barre, courbe...)
            └─ Données : endpoint API (/api/battery/<process>)
                 └─ Data collector (web_server/data_collectors.py)
                      └─ Service gRPC (BatteryService)
```

Correspondance endpoint ↔ service gRPC : `ENDPOINT_SERVICE_MAP` dans
`navigation_server/web_server/data_collectors.py` (battery, mppt, energy,
dc_dc, engine, nmea2000, gnss, network, console...).

### Règles

1. **La page Services est la page 0** : toujours présente, non optionnelle,
   rendue par le code historique (`static/js/collectors/system.js`).
2. Toute autre page est **déclarée par configuration** et assemblée par le
   framework page/bloc.
3. Un bloc déclare sa **source de données** (endpoint + sélecteur JSON) et son
   **type** (enregistré dans le registre de blocs).
4. Les blocs partageant un même endpoint ne déclenchent qu'**un seul fetch**
   par cycle de rafraîchissement.

## 2. Implémentation

### Front-end (`navigation_server/web_server/static/js/ui/`)

| Module | Rôle |
|---|---|
| `config.js` | Configuration UI par défaut (structure pages/blocs) + chargement depuis `/api/ui_config` avec repli sur la config embarquée. |
| `framework.js` | Assemblage des pages : création du DOM, navigation, rafraîchissement périodique par page, gestion de disponibilité (masquage du bouton de nav si le service est absent). |
| `blocks.js` | Registre des types de blocs (`registerBlockType`). Chaque bloc est lié à une entité et définit sa vue (composition de vues élémentaires). |
| `views.js` | Registre des vues élémentaires : `barView`, `centeredBarView`, `trendView`, `textView`. |
| `enums.js` | Tables enum protobuf → noms lisibles, partagées avec les collectors. |

`static/js/collectors/energy_mgmt.js` est désormais un pont de compatibilité :
`showPage()` délègue au framework.

### Back-end (`navigation_server/web_server/`)

Deux façons de fournir la configuration au démarrage :

1. **Fichier YAML du process web** (mode déploiement, `WebTopServer`) : clé
   `ui_config` dans le bloc `Main` de `web_server.yml`. C'est le mode normal
   de déploiement (`run_server conf/web_server.yml`).
2. **Ligne de commande** (mode test autonome) : option `--ui-config <fichier>`
   de `web_main()`.

Dans les deux cas, le décodage est fait par `yaml.safe_load()` :

- `WebTopServer.__init__` (`web_top_server.py`) lit la clé `ui_config`,
  décode le fichier et transmet le dict à `NavigationWebServer(ui_config=...)`.
- `web_main()` (`web_server.py`) fait de même pour l'option `--ui-config`.

La configuration est validée (dict avec clé `pages`), puis servie telle
  quelle au front-end via l'endpoint `/api/ui_config` (404 si absente → le
  front utilise sa configuration embarquée par défaut). Le décodage final en
  objets pages/blocs est fait côté navigateur par `js/ui/config.js`
  (`loadUiConfig()`) et `js/ui/framework.js`.

Exemple de référence : `conf/web_ui_default.yml`.

### Schéma de configuration

```yaml
pages:
  - id: ems
    title_i18n: nav.ems
    refresh_interval: 10000     # ms
    availability_endpoint: /api/energy_available
    blocks:
      - id: battery
        type: battery          # type enregistré dans js/ui/blocks.js
        entity: battery
        area: top              # zone de mise en page
        datasource:
          endpoint: /api/energy
          selector: batteries.0   # chemin dans la réponse JSON
      - id: energy-sources
        type: energy_source
        entity: energy_source
        area: sources
        repeat: true           # un bloc indépendant par item de la collection
        datasource:
          endpoint: /api/energy
          selector: sources
```

### Blocs répétés (`repeat: true`)

Quand un bloc déclare `repeat: true`, le framework instancie **un bloc
indépendant par item** de la collection pointée par le sélecteur — leur
nombre suit les données (ex. nombre de sources d'énergie actives). Chaque
instance reçoit l'item correspondant et un identifiant unique
(`<id du bloc>-<index>`).

### Zones de mise en page (`area`)

Chaque zone est une grille CSS indépendante, nommée librement dans la
configuration (classe `area-<nom>`) :
- demi-largeur par défaut (2 colonnes), repli 1 colonne sous 768px ;
- `area: full` pour un bloc en pleine largeur ;
- une zone personnalisée peut être stylée via `.page-area.area-<nom>` dans
  `main.css`.

## 3. Ajouter une nouvelle page ou un nouveau bloc

1. Créer (ou réutiliser) un type de bloc : `registerBlockType("mon_type", {...})`
   dans `js/ui/blocks.js`, en composant les vues de `js/ui/views.js`.
2. Déclarer la page et ses blocs dans la configuration (fichier YAML passé à
   `--ui-config`, ou `DEFAULT_UI_CONFIG` dans `js/ui/config.js` pour la valeur
   par défaut).
3. Aucune modification du HTML ni de la navigation n'est nécessaire : le
   framework construit les boutons de navigation et les pages dynamiquement.

## 4. Rationalisation entités / services (déviation EnergyController)

Le concept impose : *les informations d'une entité proviennent directement de
son service gRPC dédié*. La version 3.0.5 comporte une déviation :
`EnergyControllerData` intègre (recopie) des informations des entités
Batteries, MPPT et chargeur DC-DC, qui possèdent pourtant leur propre service
gRPC.

La cible est que chaque bloc de la page EMS consomme directement les endpoints
de ses entités :

| Bloc | Entité | Endpoint cible |
|---|---|---|
| Energy Controller | energy_controller | `/api/energy` (données propres : tensions, production, consommation, stock, balance) |
| Battery | battery | `/api/battery/<process>` (BatteryService) |
| Sources (MPPT, DC-DC...) | energy_source / mppt / dc_dc | `/api/mppt/<process>`, `/api/dc_dc/<process>` |

Cette rationalisation nécessite d'alléger `EnergyController` côté
`energy_mgmt/` et possiblement les `.proto` : elle constitue une itération
distincte, à traiter avec le périmètre back-end correspondant. En attendant,
la configuration par défaut de la page EMS utilise l'endpoint `/api/energy`
(qui agrège) — le basculement vers les endpoints dédiés ne requerra qu'un
changement de configuration, pas de code front-end.
