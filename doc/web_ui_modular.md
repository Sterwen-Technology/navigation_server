# Web UI — Architecture modulaire page / bloc

> Version de travail (français). Version de base anglaise :
> `doc/web_ui_modular_en.md`.

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
            └─ Données : chemin de données (/api/<service>/<instance>/data/<name>)
                 └─ Data collector (web_server/data_collectors.py)
                      └─ Service gRPC (BatteryService)
```

Correspondance endpoint ↔ service gRPC : `ENDPOINT_SERVICE_MAP` dans
`navigation_server/web_server/data_collectors.py` (battery, mppt, energy,
dc_dc, engine, nmea2000, gnss, network, console...).

### Règles générales

1. **La page Services est la page 0** : toujours présente, non optionnelle,
   rendue par le code historique (`static/js/collectors/system.js`).
2. Toute autre page est **déclarée par configuration** et assemblée par le
   framework page/bloc.
3. Il n'y a **pas de bloc préconfiguré** : la définition d'un bloc (les vues
   qu'il contient) fait partie de la configuration, sur la base de types de
   blocs et de widgets paramétrés.
4. **Un service gRPC expose trois datasets** : `parameters` (statique /
   semi-statique), `data` (instantané), `trend` (historique immédiat).
   Voir §7 (rationalisation protobuf).
5. **Pas de duplication de données entre entités**, sauf deux exceptions
   assumées :
   - la vue **consolidée** présentée par l'Energy Controller (ex.
     `battery_balance`, `state_of_charge`), qui est sa raison d'être ;
   - la reprise de quelques champs **live** dans le dataset `data` d'un
     service (ex. `communication_ok`, `state`) pour éviter d'aller chercher
     en permanence le dataset `parameters`. Les données semi-statiques
     restent dans `parameters`.

## 2. Configuration de l'interface

La configuration est déclarative. Elle définit : les **widgets** (vues
élémentaires paramétrées), les **types de blocs** (définitions de blocs
réutilisables) et les **pages** (assemblage de blocs).

### 2.1 Structure du fichier

Trois sections **globales** (non imbriquées dans les pages) :

| Section | Rôle | Réutilisation |
|---|---|---|
| `widgets` | Widgets paramétrés, construits sur des base widgets codés en dur | entre types de blocs et pages |
| `block_types` | Types de blocs réutilisables (titre, widget d'état, liste de vues) | entre pages |
| `pages` | Pages : mise en page, blocs, endpoints, cycle de rafraîchissement | — |

Un bloc d'une page peut soit référencer un `block_type`, soit porter sa
`definition` inline (surcharge ponctuelle, pas de réutilisation).

### 2.2 Schéma de référence

*Exemple significatif mais incomplet à ce stade : la liste définitive des
widgets sera consolidée en fin de conception.*

```yaml
# --- Widgets (globaux) ---------------------------------------------
widgets:
  - id: voltage_viewgraph
    base_widget: positive_viewgraph
    unit: V
    precision: 2            # nombre de décimales (défaut 0)
    color: voltage          # référence à la palette de couleurs
    scale: {type: fixed, max: parameters/max_voltage_scale}

  - id: production_viewgraph
    base_widget: positive_viewgraph
    unit: W
    precision: 0
    scale:
      type: dual
      low: parameters/total_power_low
      high: parameters/total_power_high

  - id: power_balance
    base_widget: symmetric_viewgraph
    unit: W
    precision: 0
    color: power
    scale:
      type: dual
      low: parameters/total_power_low
      high: parameters/total_power_high

  - id: power_trend
    base_widget: single_positive_curve
    scale: {type: dynamic}

  - id: power_balance_trend
    base_widget: single_symmetric_curve
    scale: {type: dynamic}

# --- Types de blocs (globaux) --------------------------------------
block_types:
  - id: energy_source
    title: parameters/label        # chemin relatif au service du bloc
    top_widget: communication_indicator
    definition:
      - view: current
        title: Current
        data: data/current         # dataset toujours explicite
        widget: production_current_viewgraph
      - view: power
        title: Power
        data: data/power
        widget: production_viewgraph
      - view: power_trend
        title: Power trend
        data: trend/power          # un dataset différent => un fetch de plus
        widget: power_trend

# --- Pages ----------------------------------------------------------
pages:
  - id: ems
    title_i18n: nav.ems
    layout:
      columns: 2
    refresh_interval: 10000        # ms
    availability_endpoint: /api/energy_available
    blocks:
      - id: energy_summary
        title: Energy Controller
        priority: 1
        position: {row: 0, column: 0}
        width: 2                    # 2 colonnes (défaut 1)
        endpoint: /api/energy/0/data
        definition:
          - view: main_voltage
            title: Main Voltage
            data: data/main_voltage
            widget: voltage_viewgraph
          - view: auxiliary_voltage
            title: Auxiliary Voltage
            data: data/auxiliary_voltage
            widget: voltage_viewgraph
          - view: production_power
            title: Production
            data: data/production_power
            widget: production_viewgraph
          - view: battery_power_balance
            title: Battery power
            data: data/battery_balance
            widget: power_balance
          - view: power_balance_trend
            title: Battery balance trend
            data: trend/battery_balance

      - id: energy-sources
        type: energy_source
        priority: 2
        repeat:
          source_endpoint: /api/energy/0/parameters/sources
          block_endpoint: /api/{service}/{instance}
```

### 2.3 Pages et mise en page

Chaque page déclare un `layout` : grille à `columns` colonnes (les lignes
s'adaptent au contenu ; pas de notion de `rows` figée).

Le positionnement d'un bloc est **explicite ou automatique** :

| Clé | Signification |
|---|---|
| `position: {row: R, column: C}` | position explicite dans la grille (0-indexé) |
| `width: N` | largeur en colonnes (défaut 1) |
| `priority: P` | ordre de placement automatique : les blocs sans `position` sont placés par priorité croissante (1 = le plus important), puis dans l'ordre de déclaration en cas d'égalité |

Le **priority** reflète la hiérarchie de l'information sur la page : les
blocs les plus importants sont placés en premier (haut/gauche), indépendamment
de l'ordre d'écriture de la configuration.

### 2.4 Blocs

Un bloc déclare :

| Clé | Signification |
|---|---|
| `id` | identifiant unique dans la page |
| `title` | texte brut ou chemin de données (`parameters/label`) ou clé i18n |
| `type` | référence à un `block_type` (mutuellement exclusif avec `definition`) |
| `definition` | définition inline des vues (surcharge ponctuelle) |
| `endpoint` | chemin de données du dataset primaire du bloc (`/api/<service>/<instance>/<dataset>`) |
| `process` | **optionnel** : qualification du process hôte, requise uniquement si le service est hébergé par plusieurs process (§3.1) |
| `position`, `width`, `priority` | mise en page (§2.3) |
| `repeat` | bloc répété (§2.5) |

Chaque vue (`definition`) déclare : `view` (identifiant), `title`,
`data` (chemin relatif — voir §3.3) et `widget` (référence à un widget
paramétré).

### 2.5 Blocs répétés (`repeat`)

Un bloc répété est instancié **une fois par item** retourné par son endpoint
source — le nombre d'instances suit les données de l'application (ex. nombre
de sources d'énergie actives).

```yaml
repeat:
  source_endpoint: /api/energy/0/parameters/sources
  block_endpoint: /api/{service}/{instance}
```

- `source_endpoint` : endpoint retournant la collection décrivant les items
  (au moins `service` et `instance` par item ; l'item peut aussi porter
  `process` si le service est hébergé par plusieurs process, §3.1).
- `block_endpoint` : gabarit de l'adresse de **base** de chaque instance
  (`/api/<service>/<instance>`), construit par substitution des
  placeholders `{service}` et `{instance}` depuis l'item. Le dataset primaire
  est déterminé par les vues du type de bloc (§2.4) et les chemins `data`
  explicites de chaque vue.
- Le `title` du bloc et les chemins `data` des vues sont relatifs à
  l'endpoint de l'instance.
- Chaque instance reçoit un identifiant unique `<id du bloc>-<index>`.

### 2.6 Cycles de fetch des endpoints

Les fetches sont **explicites et pilotés par l'usage** — un dataset n'est
interrogé que si un élément affiché l'utilise :

| Dataset | Cycle de fetch |
|---|---|
| `data` | à chaque cycle de rafraîchissement de la page (`refresh_interval`), un seul fetch par endpoint même si plusieurs vues/blocs le partagent |
| `trend` | au même cycle, **uniquement si au moins une vue du bloc référence un chemin `trend/...`** (correspond à une requête protobuf `GetTrend` distincte) |
| `parameters` | une fois à l'activation de la page, puis re-fetch sur changement de contexte (keepalive `system_changed`) ; **uniquement si** un titre, un widget (`scale`) ou un `repeat` le référence |

Optimisations futures possibles (non traitées dans un premier temps) :
fréquence distincte pour `trend`, regroupement de requêtes, cache côté
backend. La simplicité d'abord — ce schéma est de toute façon plus efficace
que la situation actuelle où le backend interroge tous les datasets à chaque
cycle.

## 3. Chemins de données

### 3.1 Process, services et instances

**Les services gRPC sont hébergés dans des process.** Le lien
process ↔ service est établi par le backend (configuration des process,
status de l'agent) et **n'apparaît pas dans les chemins de données de
l'UI**. La configuration UI référence des entités (service + instance),
jamais des process directement.

Deux dimensions distinctes doivent être distinguées :

| Notion | Définition | Exemples |
|---|---|---|
| **service multi-instance** | un service qui gère plusieurs entités de même type **dans le même process** ; l'instance identifie l'entité dans le process | `battery`, `mppt`, `dc_dc`, `engine` |
| **service multi-process** | un même type de service hébergé par **plusieurs process** ; singleton dans chaque process, mais plusieurs exemplaires dans le système | `console` (présent dans chaque process) |

L'adresse complète d'une entité côté backend est donc le triplet
**(service, process, instance)** — instance valant 0 pour les services
singleton dans leur process.

**Règle de résolution du process** (backend, à partir du status de l'agent) :

1. Le service est hébergé par **un seul process** → résolution implicite
   (cas de tous les services de la page EMS, hébergés dans le process
   `energy` ; c'est un cas particulier, pas une généralité).
2. Le service est hébergé par **plusieurs process** (ex. `console`) → la
   configuration doit qualifier le process explicitement, via la clé
   `process:` du bloc (§2.4) ou de l'item de `repeat` (§2.5).
3. Service introuvable ou process non qualifié alors que le service est
   multi-process → erreur visible dans le bloc.

### 3.2 Chemins d'accès aux données

Le chemin d'accès aux données suit le schéma :

```
/api/<service>/<instance>/<dataset>/<name>
```

- **service** : le service au sens gRPC (directive `service` du protobuf)
- **instance** : numéro d'instance (0 par défaut) pour les services
  multi-instances (§3.1) ; le process est résolu par le backend (§3.1),
  éventuellement qualifié par la clé `process:` du bloc
- **dataset** : un message protobuf spécifique (structure JSON entre serveur
  et client). Quatre datasets :
  1. `parameters` : données statiques ou semi-statiques, rafraîchies au
     démarrage ou sur changement de contexte
  2. `data` : valeurs instantanées
  3. `trend` : historique immédiat — la dernière valeur est celle de
     l'instant présent. Cas spécifique : les valeurs sont stockées dans le
     tableau `samples` ; cet élément de chemin non significatif est omis.
  4. `history` : historique long — pas encore implémenté
- **name** : nom du champ protobuf/JSON

D'autres datasets pourront être définis pour d'autres pages, hors contexte
« energy ».

### 3.3 Chemins relatifs des vues

Le **dataset est toujours explicite** dans les chemins de données des vues :

- `data` d'une vue = `<dataset>/<name>`, ex. `data/main_voltage`,
  `trend/power`, `parameters/label`. Le dataset de l'`endpoint` du bloc est
  le dataset **primaire** (celui qui motive le fetch du bloc) ; une vue peut
  référencer un autre dataset (fetch supplémentaire, §2.6).
- Les chemins de widget (`scale.max`/`low`/`high`, `color` paramétré,
  `title`) se résolvent : d'abord dans les `parameters` **du service du
  bloc** (`/api/<service>/<instance>/parameters`), sinon dans le dataset
  `parameters` de la page (endpoint `parameters_endpoint` de la page, s'il
  est déclaré — les paramètres de page sont valides pour l'ensemble de
  celle-ci).

## 4. Visualisation des données dans les blocs

Les données sont réparties dans les catégories suivantes :

| Type de donnée             | représentation interne | description                                                            | donnée(s) additionnelle                |
|----------------------------|------------------------|------------------------------------------------------------------------|---------------------------------------|
| scalaire positif           | float                  | Nombre flottant positif                                                | valeur maximum d'affichage            |
| scalaire                   | float                  | nombre flottant                                                        | valeur absolue du maximum d'affichage |
| texte                      | string (utf_8)         | Chaîne de caractères                                                   | nombre caractères maximum d'affichage |
| date                       | string                 | Date au format iso 8601 UTC                                            | N/A                                   |
| série temporelle tendance  | list[float]            | série de valeurs à intervalle fixe référencé par rapport temps courant | intervalle, valeur maximum            |
| série temporelle régulière | list[float]            | série de valeur à intervalle fixe référencée par une date              | date, intervalle, valeur maximum      |

Les séries peuvent être avec des valeurs strictement positives ou bien
négatives/positives.

Les unités utilisées dans l'application sont les suivantes (liste non
définitive) :

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

**Convention des ratios** : les ratios (ex. `state_of_charge`) sont toujours
représentés **entre 0 et 1** dans les messages protobuf. L'interface les
affiche en **pourcentage 0-100** ; la conversion est de la responsabilité
du widget (paramètre d'affichage), jamais du transport.

## 5. Widgets

### 5.1 Viewgraph

Le viewgraph est un ensemble graphique constitué des éléments suivants :
- Un titre sur 2 lignes centrées (si le titre est un mot on provisionne
  toujours 2 lignes)
- Un rectangle colorié verticalement proportionnellement à la donnée
  représentée avec deux variantes : 0 en bas (`positive_viewgraph`) ou 0 au
  milieu avec valeurs positives au-dessus et négatives en dessous
  (`symmetric_viewgraph`). Dans ce dernier cas le zéro est marqué par un
  trait horizontal.
- La valeur numérique (signée si symétrique) avec la précision donnée en
  paramètre, suivie du symbole de l'unité.

### 5.2 Courbes en fonction du temps

Deux variantes : `positive_curve` ou `symmetric_curve`. Même principe que
pour les bargraph. Par défaut, il n'y a pas d'axes ni d'échelle tracés.

Il peut y avoir des widgets avec une seule courbe ou avec deux courbes.

### 5.3 Histogrammes

Même principe que les courbes mais avec un graphique en histogramme.

### 5.4 Base widgets (liste consolidée)

*Liste suffisante pour la partie énergie ; elle pourra être étendue pour
d'autres pages, sans remettre en cause les principes.*

| base_widget | Description |
|---|---|
| `positive_viewgraph` | barre 0 en bas |
| `symmetric_viewgraph` | barre centrée sur 0 |
| `single_positive_curve` | une courbe, valeurs positives |
| `single_symmetric_curve` | une courbe, valeurs signées |
| `dual_curve` | deux courbes superposées |
| `positive_histogram` / `symmetric_histogram` | histogrammes |
| `communication_indicator` | indicateur d'état de communication (top_widget) |
| `text_value` | texte simple |

### 5.5 Dimensions des widgets

Les viewgraphs ont une taille fixe pour l'ensemble de l'application. Ces
dimensions sont un paramètre global du front-end (`widget_defaults`). Il
peut être éventuellement dynamique en fonction de la résolution de l'écran.
La hauteur est liée à la dimension du bloc ; le nombre de widgets
instanciables dans un bloc est donc limité. **Il faut un message d'erreur
visible si la vue générée n'est pas constructible.** Pour les courbes et
histogrammes, ils prennent tout l'espace restant à droite dans le bloc.

### 5.6 Paramètres des widgets

| parameter | values or type | signification |
|-----------|----------------|---------------|
| title     | string         | titre affiché |
| unit      | string         | symbole de l'unité |
| color     | string         | référence à la palette de couleurs (nom) ou valeur codée |
| precision | int [0, 3]     | nombre de décimales (défaut 0) |
| scale     | object (§5.7)  | définition d'échelle : `{type: fixed\|dual\|dynamic, ...}` |
| data      | chemin de données | référence relative à l'endpoint du bloc, dataset explicite |

Les paramètres peuvent être configurés en tableaux quand plusieurs valeurs
doivent être affichées dans le widget (ex. `dual_curve` avec deux chemins
`data` et deux `color`).

### 5.7 Définition d'échelle (`scale`)

L'échelle d'affichage est définie par un objet structuré (les valeurs de
référence sont des chemins de données, résolus selon §3.3, ou des valeurs
numériques littérales) :

```yaml
scale: {type: fixed, max: parameters/max_voltage_scale}

scale:
  type: dual
  low: parameters/total_power_low      # échelle basse ET seuil de bascule
  high: parameters/total_power_high    # échelle haute

scale: {type: dynamic}
```

| Type | Signification |
|---|---|
| `fixed` | échelle constante ; `max` = valeur (ou chemin) du maximum affichable |
| `dual` | double échelle à bascule automatique : le widget affiche sur l'échelle basse tant que \|valeur\| ≤ `low`, sinon sur l'échelle haute ; `low` sert à la fois de seuil et d'échelle basse, `high` est l'échelle haute |
| `dynamic` | recalculée sur la série affichée (min/max observés) |

### 5.8 Palette de couleurs

Les couleurs sont référencées par nom dans la configuration
(ex. `color: voltage`) et résolues dans une palette globale déclarée au
niveau du front-end (paramètre `colors` de la configuration UI), avec
possible valeur codée directe.

## 6. Chargement de la configuration

Deux façons de fournir la configuration au démarrage :

1. **Fichier YAML du process web** (mode déploiement, `WebTopServer`) : clé
   `ui_config` dans le bloc `Main` de `web_server.yml` (`run_server
   conf/web_server.yml`).
2. **Ligne de commande** (mode test autonome) : option `--ui-config
   <fichier>` de `web_main()`.

Dans les deux cas, le décodage est fait par `yaml.safe_load()` :
`WebTopServer.__init__` (`web_top_server.py`) lit la clé `ui_config`, décode
le fichier et transmet le dict à `NavigationWebServer(ui_config=...)` ;
`web_main()` fait de même pour l'option `--ui-config`.

La configuration est validée (dict avec clé `pages`), puis servie telle
quelle au front-end via `/api/ui_config` (404 si absente → le front utilise
sa configuration embarquée par défaut). Le décodage final en objets
pages/blocs est fait côté navigateur par `js/ui/config.js` (`loadUiConfig()`)
et `js/ui/framework.js`.

Exemple de référence : `conf/web_ui_default.yml`.

## 7. Rationalisation des services protobuf

### 7.1 Structure standard d'un service

Chaque service expose systématiquement **trois datasets** = trois messages
protobuf et trois rpc :

| Dataset | Message | Rpc (proposition de nommage standard) |
|---|---|---|
| `parameters` | `<Service>_Parameters` | `GetParameters` |
| `data` | `<Service>_Data` | `GetData` |
| `trend` | `<Service>_Trend` | `GetTrend` |

Le nommage actuel (`GetInformation`/`GetValues`) sera rationalisé dans ce
sens au cours du travail protobuf. Les services de configuration/commande
(`SetConfiguration`, `DeviceCommand`) restent hors de ce périmètre.

### 7.2 Rationalisation EnergyController

La déviation historique (`EnergyControllerData` recopiait les données des
batteries, MPPT et chargeurs DC-DC, qui ont leur propre service gRPC) est
corrigée : `EnergyControllerData` ne contient plus que la vue consolidée du
contrôleur (tensions, production, consommation, stock, balance, état de
charge). Chaque entité est servie par son service dédié.

| Bloc | Entité | Endpoint |
|---|---|---|
| Energy Controller | energy_controller | `/api/energy/0/...` |
| Battery | battery | `/api/battery/<instance>/...` |
| Sources (MPPT, DC-DC...) | mppt, dc_dc | `/api/mppt/<instance>/...`, `/api/dc_dc/<instance>/...` |

**Compatibilité** : le serveur Web est considéré comme faisant partie de
l'application : pas de contrainte de compatibilité wire entre versions —
l'application (process serveurs) et le serveur Web sont mis à jour
simultanément. La renumérotation de champs dans `energy.proto` (ex.
`MPPT_device` absorbant `MPPT_parameters`) est donc sans réserve. Après
modification d'un `.proto`, toujours régénérer (`gen_proto`) ; les impacts
backend (`energy_mgmt/`, `data_collectors.py`, simulator) et la configuration
UI par défaut (sélecteurs `batteries.0`/`sources` supprimés) sont à traiter
dans la même itération.

## 8. Ajouter une nouvelle page ou un nouveau bloc

1. Créer ou réutiliser des **widgets** (section `widgets`) sur la base des
   base widgets codés en dur (`js/ui/views.js`).
2. Créer ou réutiliser un **type de bloc** (section `block_types`) ou
   définir les vues inline dans le bloc.
3. Déclarer la page et ses blocs (section `pages`) : mise en page
   (`layout`, `position`/`priority`), endpoints, cycle de rafraîchissement.
4. Aucune modification du HTML ni de la navigation n'est nécessaire : le
   framework construit les boutons de navigation et les pages dynamiquement.

## 9. Réutilisation de l'existant

Les vues existantes doivent être réutilisées et adaptées, mais les principes
et le look and feel de la version actuelle doivent être conservés. C'est la
construction modulaire et la paramétrisation qui changent, pas le résultat.
