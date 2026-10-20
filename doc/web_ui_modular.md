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

### Back-end (`navigation_server/web_server/web_server.py`)

- Option `--ui-config <fichier YAML>` : configuration des pages/blocs servie
  au démarrage. Exemple de référence : `conf/web_ui_default.yml`.
- Endpoint `/api/ui_config` : renvoie la configuration (404 si non fournie,
  le front utilise alors sa configuration embarquée par défaut).

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
```

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
