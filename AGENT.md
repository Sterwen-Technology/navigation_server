# AGENTS.md — Navigation Server

## Project overview
Serveur de navigation maritime (NMEA 0183/2000, gRPC). Python (Poetry), protobuf pour
l'API gRPC, interface web embarquée.

## Structure du dépôt
Racine du projet : /mnt/meaban/Sterwen-Tech-SW/navigation_server

Tous les fichiers et chemins indiqués en suivant sont relatifs à cette racine.

- `navigation_server/` — package racine de l'application.
- `navigation_server/server_main.py` - module principal de tous les process du système
- `navigation_server/web_server/` — serveur web + UI (`static/`, `data_collectors.py`). inclus le web serveur backend (data_collectors.py) et le front end.
- `navigation_server/agent/` — agent système (démarrage/contrôle des processus).
- `navigation_server/network/` - service de gestion du réseau colocalisé avec l'agent.
- `navigation_server/router_common/` Package des classes et fonctions communes - NE PAS EDITER
- `navigation_server/router_core/` — code Python spécifique au routage des messages NMEA - NE PAS EDITER
- `navigation_server/navigation_clients` - classes proxy clientes pour accès gRPC à utiliser impérativement si elles existent et à créer si nécessaire
- `navigation_server/<autress packages>` - Ce sont les packages applicatifs qui ne doivent pas être édités sans instructions explicites
- `protobuf/` — définitions .proto. Source de vérité. Toute modification ici impacte possiblement l'application, le back-end ET le front : NE JAMAIS les réverter pour « limiter son périmètre ».
- `navigation_server/generated/` — code Python généré à partir des .proto.
  NE JAMAIS éditer À LA MAIN. Régénérer via `gen_proto`.
- `doc/` — documentation d'architecture et configuration
- `conf/` - fichiers de configuration Yaml exemples
- `reference_conf/STNC-Labo/` - Fichier de configuration référence pour l'installation cible de test
- `python_lib/` - Libraires Python modifiées pour le projet - Normalement plus utilisé

## Commandes
- Installation : `poetry install --all-extras`. Les packages sont gérés dans l'environnement virtuel généré par Poetry.
- Régénérer protobuf : `gen_proto`
- Lancer un process (serveur) : `./run_server` (voir `doc/` pour la config)
- Lancer Python `python3` si on est dans l'environnement projet sinon `poetry run python3`

## Règles de périmètre (IMPORTANT)
1. Un prompt = un périmètre. Si la demande concerne l'UI/web, ne toucher QUE
   `navigation_server/web_server/`. Si elle concerne le back-end, ne PAS toucher
   `web_server/`.
2. Les fichiers `protobuf/*.proto` sont partagés front/back : avant de les modifier,
   le signaler explicitement dans la réponse. Ne jamais les réinitialiser ou réverter.
3. Après modification d'un `.proto`, TOUJOURS régénérer (`gen_proto`) 

## Commandes git interdites
- `git checkout -- <fichier>`, `git restore <fichier>`, `git checkout .` :
  INTERDIT (détruit le travail non commité).
- `git reset --hard` : INTERDIT.
- `git clean` : INTERDIT.
- Pour annuler ses propres changements dans le périmètre assigné : demander
  d'abord à l'utilisateur, ou utiliser `git stash push -- <chemins>`.
- Avant toute commande git destructrice sur des fichiers HORS périmètre :
  DEMANDER d'abord. En cas de doute : demander.

## Discipline de travail
1. Vérifier `git status` au début de la session ; signaler tout travail non commité
   existant avant de commencer.
2. Faire des modifications minimales et ciblées ; rester dans le périmètre.
3. Après chaque unité de travail validée : proposer un commit (message court,
   convention existante du dépôt, ex. "Web UI: <description>").
4. Ne jamais reformater ou « nettoyer » du code non concerné par la tâche.


## Conventions code
- Python : suivre le style existant du fichier modifié (pas de reformatage global).
- Les commentaires dans le code sont en anglais.
- Pas de nouvelle dépendance sans le signaler explicitement.
- Tous les imports doivent se faire dans la section imports en tête de fichier dans l'ordre suivant :
- import sur les packages standards
- import sur les packages externes (importés)
- import sur les packages internes sans duplication, avec une ligne par package. Les packagesinternes doivent toujours être préfixés par `navigation_server`
- Les imports sur package internes doivent être faits u niveau package, pas au niveau module sauf pour `generated`
- Si un symbole n'est pas trouvé au niveau package, ne pas importer depuis le module, demander explicitement si nécessaire
- Aucun accès aux membres privés de classes.