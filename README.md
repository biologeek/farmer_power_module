# Odoo Garden

Module Odoo 19 (`odoo_garden`, version `19.0.1.0.0`, licence LGPL-3) pour la gestion d'une exploitation maraîchère : structure de la ferme, catalogue de cultures, suivi des cultures et des actions sur planche, post-process, pertes et statistiques.

Le module ne dépend que de `base` et s'installe comme une application (menu **Maraîchage**).

## Installation

1. Copier le dossier du module dans un répertoire `addons` d'Odoo, sous le nom `odoo_garden` (les chemins des assets du manifeste supposent ce nom).
2. Redémarrer Odoo et mettre à jour la liste des applications.
3. Installer **Odoo Garden** depuis l'interface.

> Pour le développement, ce dossier est la source de vérité ; les modifications sont ensuite recopiées dans `odoo/custom_addons/odoo_garden` (voir `COPILOT.md`).

## Arborescence

```
__manifest__.py           Déclaration du module (données, assets)
controllers/
  odoo_garden.py          Route /odoo/garden (redirection vers l'application)
models/                   Modèles métier (un fichier par modèle)
views/                    Vues list/form, actions et menus
static/src/js|xml/        Actions client OWL (statistiques, occupation des planches)
security/
  ir.model.access.csv     Droits d'accès
tests/                    Tests Odoo (post_install)
```

## Modèle de données

```
garden.farm (Ferme)
└── garden.site (Site)
    └── garden.garden (Jardin)
        └── garden.bed (Planche)
            ├── garden.plot (Parcelle — temporaire, sans vue)
            ├── garden.crop (Culture) ──> garden.crop.catalog ──> garden.culture.mode
            │   └── garden.action ──> garden.action.type
            │       └── garden.postprocess
            └── garden.loss (Perte)
```

| Modèle | Fichier | Champs principaux |
|---|---|---|
| `garden.farm` | `garden_farm.py` | `name`, `site_ids` |
| `garden.site` | `garden_site.py` | `name`, `farm_id`*, `garden_ids` |
| `garden.garden` | `garden_garden.py` | `name`, `site_id`*, `bed_ids` |
| `garden.bed` | `garden_bed.py` | `name`, `garden_id`*, `action_ids` |
| `garden.plot` | `garden_plot.py` | `name`, `bed_id`* |
| `garden.culture.mode` | `garden_culture_mode.py` | `name`, `type` (plein air / sous serre), `distance` (cm), `nb_rangs` |
| `garden.crop.catalog` | `garden_variety.py` | `name`, `variety`, `supplier_id` (`res.partner`), `mode_culture`, `distance` et `nb_rangs` (liés au mode, modifiables), `duree_previsionnelle` (jours) |
| `garden.crop` | `garden_crop.py` | `catalog_id`*, `bed_id`*, `date_start`, `date_end`, `sowing_quantity`, `planted_quantity`, `quantity_harvested` (kg), `value_harvested` (€), `notes`, `action_ids` |
| `garden.action.type` | `garden_action_type.py` | `name`, `description` |
| `garden.action` | `garden_action.py` | `type_id`*, `crop_id`*, `bed_id` (lié à `crop_id.bed_id`, stocké), `date`, `duration` (minutes), `description` |
| `garden.postprocess` | `garden_postprocess.py` | `name`, `date`, `action_id`, `description` |
| `garden.loss` | `garden_loss.py` | `date`, `bed_id`, `quantity`, `reason` |

\* champ obligatoire.

## Menus

- **Maraîchage › Exploitation** : Fermes, Sites, Jardins, Planches, Catalogue de cultures
- **Maraîchage › Production** : Cultures (avec un onglet Actions), Actions, Post-process, Pertes
- **Maraîchage › Statistiques** : Statistiques (Graphiques), Production, Occupation des planches

## Statistiques

Les écrans de statistiques sont des actions client OWL (`ir.actions.client`, déclarées dans `views/garden_statistics_views.xml`) qui appellent des méthodes Python via le service `orm` :

| Tag client | Méthode serveur | Contenu |
|---|---|---|
| `garden_statistics` | `garden.action.get_statistics_data()` | Camembert de la durée totale par type d'action ; barres empilées de la durée par culture et par type d'action (Chart.js) |
| `garden_production_statistics` | `garden.crop.get_production_statistics_data()` | Quantité (kg) et valeur (€) récoltées par mois (`date_end`, à défaut `date_start`), par planche et par culture |
| `garden_bed_occupancy` | `garden.bed.get_occupancy_data(domain)` | Gantt : une ligne par planche, une barre par culture entre `date_start` et `date_end` |

Les agrégations sont écrites en SQL brut (`self.env.cr.execute`) et ne tiennent donc pas compte des règles d'accès ni du multi-société.

## Contrôleur

`GET /odoo/garden` redirige un utilisateur connecté vers l'action des fermes, et un visiteur anonyme vers la page de connexion.

## Sécurité

`security/ir.model.access.csv` accorde tous les droits à tous les utilisateurs, sans groupe, sur les modèles du module, y compris `garden.culture.mode` et `garden.plot`.

## Tests

Le dossier `tests/` contient un test d'installation (`TestGardenInstall`, taggé `post_install`, `-at_install`) : création de la chaîne ferme > site > jardin > planche > catalogue > culture > type d'action > action, vérification du champ `bed_id`, structure des données de statistiques et d'occupation, existence de l'action `odoo_garden.action_garden_farm`.

```
odoo-bin -d garden_test -i odoo_garden --test-enable --test-tags /odoo_garden --stop-after-init
```

## Points connus / à corriger

- **Chart.js** : chargé par une balise `<script>` dans le template OWL depuis un CDN, sans version fixée, avec un `setTimeout` de 50 ms avant le rendu ; les graphiques peuvent rester vides.
- **Manifeste** : `author` et `website` contiennent encore des valeurs par défaut.
- **`action_garden_statistics`** n'est rattachée à aucun menu.

## À venir

La feuille de route complète (version payante intégrée aux applications Odoo) est décrite dans [`docs/SPECIFICATIONS.md`](docs/SPECIFICATIONS.md).

- Traçabilité de la graine au client
- Rétro-planning basé sur `duree_previsionnelle`
- Prise en compte des pertes dans les statistiques (taux de perte, rendement)
- Schéma visuel des sites et planches
