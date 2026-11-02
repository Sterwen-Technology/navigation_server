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

**NOTE generale: pour simplifier le travail du backend et du front end on peut envisager de restructurer les interfaces protobuf pour améliorer leur cohérence pour l'ensemble des entités. Egalement, les données ne doivent plus être dupliquées comme elles le sont aujourd'hui dans le "Energy Controller" (sauf pour les batteries car le contrôleur présente une vue consolidée)**

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

**Modification: plus de "block" préconfiguré. La configuration des blocks est aussi paramétrable. Voir plus bas**

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

### Positionnement des blocs

Les blocs doivent pouvoir être positionnés dans la page soit de manière automatique, soit de manière explicite (row, column)

### Schéma de configuration

**L'exemple est une ébauche de la définition des blocks et des entités conceptuelles associées (view, widgets)**

*Le fichier de définition est un exemple significatif, à ce stade il est incomplet*

```yaml
pages:
  - id: ems
    title_i18n: nav.ems
    layout:
      type: grid
      columns: 2
      rows: 4
    refresh_interval: 10000     # ms
    availability_endpoint: /api/energy_available
    parameters_endpoint: /api/energy/parameters     # parameters like scale
    blocks:
      - id: energy_summary
        title: Energy Controller  #  can be a translation reference
        position: (0, 0)
        width: 2    # means 2 columns (default 1)
        endpoint: /api/energy/data
        definition:
          - view: main_voltage
            title: Main Voltage
            data: main_voltage      # reference au Json - on peut mettre un chemin structuré
            widget: voltage_viewgraph  # definition générique
          - view: auxiliary_voltage
            title: Auxiliary Voltage
            data: auxiliary_voltage
            widget: voltage_viewgraph
          - view: production_power
            title: Production
            data: production_power
            widget: production_viewgraph
          - view: battery_power_balance
            title: Battery power
            data: battery_balance
            widget: power_balance
          - view: power_balance_trend
            title: Battery balance trend
            data: trend/battery_balance # there is a trick here as there is a sample field, but it is not significant here
        
      - id: energy-sources
        type: energy_source     # vue générique pour le block
        position: (auto, 0)
        width: 1    # one column (default)
        repeat:           # un bloc indépendant par item de la collection
          source_endpoint: /api/energy/parameters/sources # source de la répétition
          block_endpoint: /api/type/instance    # the endpoint est construit dynamiquement à partir de la source
               
    block_types:
      - id: energy_source
        title: parameters.label   # le préfixe du endpoint est implicite 
        top_widget: communication_indicator
        definition:
          - view: production_current
            title: Current
            data: data/current      # chemin des données relatif au endpoint
            widget: production_current_viewgraph
          - view: production_power
            title: Power
            data: data/power
            widget: production_viewgraph
          - view: power_trend
            title: Power trend
            data: trend/power
            widget: power_trend
            
    widgets:
      - id: voltage_viewgraph
        base_widget: positive_viewgraph # that is the hard coded part
        units: V
        precision: 2  # figures with 2 digits
        scale: fixed
        color: 'voltage_color_parameter'
        max_value: voltage_max_scale  # using the default parameters_endpoint
      - id: production_viewgraph
        base_widget: positive_viewgraph
        units: W
        precision: 0
        scale: dual
        max_value: [total_power_low, total_power_high]
      - id: power_balance
        base_widget: symmetric_viewgraph
        unit: W
        precision: 0
        color: 'power_color_parameter'    # to be defined somewhere - that is already the case
        scale: dual
        max_value: [total_power_low, total_power_high]
      - id: power_trend
        base_widget: single_positive_curve
        scale: dynamic
      - id: power_balance_trend
        base_widget: single_symmetric_curve
        scale: dynamic
        

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

## 5. Visualisation des données dans les blocs

Les données sont réparties dans les catégories suivantes :

| Type de donnée             | représentation interne | description                                                            | donnée(s) additionelle                |
|----------------------------|------------------------|------------------------------------------------------------------------|---------------------------------------|
| scalaire positif           | float                  | Nombre flottant positif                                                | valeur maximum d'affichage            |
| scalaire                   | float                  | nombre flottant                                                        | valeur absolue du maximum d'affichage |
| texte                      | string (utf_8)         | Chaine de caractères                                                   | nombre caractères maximum d'affichage |
| date                       | string                 | Date au format iso 8601 UTC                                            | N/A                                   |
| série temporelle tendance  | list[float]            | série de valeurs à intervalle fixe référencé par rapport temps courant | intervalle, valeur maximum            |     
| série temporelle régulière | list[float]            | série de valeur à intervalle fixe référencée par une date              | date, intervalle, valeur maximum      |

Les séries peuvent être avec des valeurs strictement positives ou bien négatives/positives


Les unités utilisées dans l'application sont les suivantes (liste non définitive)

| Grandeur physique | Unité              | Symbole | Type             |
|-------------------|--------------------|---------|------------------|
| Temps/Durée       | seconde            | s       | scalaire positif |
| Date              | N/A                | N/A     | date             |
| Tension (DDP)     | Volt               | V       | scalaire positif |
| Courant           | Ampère             | A       | Scalaire         |
| Puissance         | Watt               | W       | Scalaire         | 
| Energie           | Watt-heure         | Wh      | scalaire         |
| Pression          | hectoPascal        | hPa     | scalaire positif |
| Vitesse rotation  | revolution/minute  | RPM     | scalaire positif |
| Temperature       | Celsius            | °C      | scalaire         |

### Identification des données et chemin d'accès

Le chemin d'accès aux données peut être défini de la manière suivante:
/api/<service>/<instance>/<dataset>/<name>

- **service**: correspond au service au sens gRPC tel que défini par la directive *service* dans me protobuf
- **instance**: numero d'instance (0 par défaut) quand le service gère plusieurs instances. Il faut définir quels sont les services à instances multiples
- **dataset**: un message spécifique, correspondant à une structure Json entre serveur et client. Par défaut (et pour la partie énergie) on va avoir 4 *dataset* définis:
1. parameters: ce sont les données statiques ou semi-statiques qui ne sont rafraichies qu'au démarrage ou sur des changements de contexte qui le nécessitent
2. data: données instantanées
3. trend: données historiques immédiates - la dernière valuer est celle de l'instant présent. Cas spécifique les données historiques sont stockées dans le tableau 'samples', ce élément du chemin non significatif est omis dans le chemin de donnée.
4. history: données historiques - pas encore implémentées

- **name**: nom du champs protobuf/Json


Pour d'autres pages et hors contexte "energy", il pourra y avoir d'autres *dataset* définis.


## 6. Définition des vues/widgets

### viewgraph

Le viewgraph est un ensemble graphique constitué des éléments suivants:
- Un titre sur 2 lignes centrées (si le titre est un mot on provisionne toujours 2 lignes)
- Un rectangle colorié verticalement proportionnellement à la donnée repésentée avec deux variantes: 0 en bas (positive_viewgraph) ou 0 au milieu avec valeur positive au-dessus et valeurs négatives en dessous (symmetric_viewgraph). Dans ce dernier cas le zero est marqué par un trait horizontal.
- La valeur numérique (signée si symmetrique) avec la précision donnée en paramètre et suivi du symbole de l'unité

### courbes en fonction du temps

Deux variantes: positive_curve ou symmetric_curve. Même principe que pour les bargraph
Par défaut, il n'y a pas d'axes ni d'échelle tracés.

Il peut y avoir des widget avec une seule courbe ou avec deux courbes

### histogrammes

Même principes que les courbes mais avec un graphique en histogramme

### Dimensions des widgets

Les viewgraphs ont une taille fixe pour l'ensemble de l'application. Ces dimensions sont un paramètre global du front end. Il peut être eventuellement dynamique en fonction de la résolution de l'écran.
La hauteur est lié à la dimension du block, le nombre de widget que l'on peut instancier dans un bloc est donc limité. Il faut un message d'erreur visible si la vue générée n'est pas constructible.
Pour les courbes et histogrammes, ils prennent tout l'espace restant à droite dans le block.

### Réutilisation de l'existant

Les vues existantes doivent être réutilisées et adaptées, mais les principes et le look and feel de la version actuelle doivent être conservés. C'est la construction modulaire et la paramétrisation qui changent pas le résultat.

### Paramètres des widgets

| parameter | values or type | signification |
|-----------|----------------|---------------|
|  title    | string         |                |
|   unit        | string                 | Symbol of the units               |
|     color           |   symbol or value                     | reference to the color symbol or hard coded value |
|     precision         |      int [0, 3]                                 |      Number of  decimal digits (default 0)  |
|             data          | data path to values            |   reference relative to base enbpoint               |

Parameters can be configured as arrays when multiple values have to be displayed in the widget


