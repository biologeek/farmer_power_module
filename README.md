# Odoo Garden

Module Odoo 19 (`odoo_garden`, version `19.0.1.1.0`, licence LGPL-3) pour la gestion d'une exploitation maraîchère : structure de la ferme (ferme, site, îlot, planche, avec surfaces et irrigation), catalogue (espèces, variétés liées aux produits, itinéraires techniques), suivi des cultures et des actions sur planche, post-process, pertes et statistiques.

Le module dépend de `base`, `web`, `product`, `uom` et `mail` et s'installe comme une application (menu **Maraîchage**). Il est livré à la **phase 1** de la feuille de route (`docs/SPECIFICATIONS.md`, § 7).

## Installation

1. Copier le dossier du module dans un répertoire `addons` d'Odoo, sous le nom `odoo_garden` (les chemins des assets du manifeste supposent ce nom).
2. Redémarrer Odoo et mettre à jour la liste des applications.
3. Installer **Odoo Garden** depuis l'interface.

> Pour le développement, ce dossier est la source de vérité ; les modifications sont ensuite recopiées dans `odoo/custom_addons/odoo_garden` (voir `COPILOT.md`).

## Arborescence

```
__manifest__.py           Déclaration du module (dépendances, données, démo, assets)
controllers/
  odoo_garden.py          Route /odoo/garden (redirection vers l'application)
models/                   Modèles métier (un fichier par modèle)
views/                    Vues list/form, actions et menus
static/src/js|xml/        Actions client OWL (statistiques, occupation des planches)
security/
  garden_security.xml     Catégorie, privilège, groupes et règles multi-société
  ir.model.access.csv     Droits d'accès par groupe
data/                     Types d'opération par défaut (noupdate)
demo/                     Données de démonstration (ferme, sites, îlots, planches, catalogue)
tests/                    Tests Odoo (post_install)
```

## Modèle de données

```
res.company
└── garden.farm (Ferme)
    └── garden.site (Site)
        └── garden.garden (Îlot — secteur d'irrigation)
            └── garden.bed (Planche)
                ├── garden.crop (Culture) ──> garden.crop.template (Itinéraire) ──> garden.variety ──> garden.species
                │   │                               └── garden.crop.template.step ──> garden.operation.type
                │   └── garden.action ──> garden.action.type
                │       └── garden.postprocess
                └── garden.loss (Perte)
product.template ──(garden_variety_ids, calculé)── garden.variety
```

| Modèle | Fichier | Champs principaux |
|---|---|---|
| `garden.farm` | `garden_farm.py` | `name`*, `company_id`* (défaut : société courante), `site_ids`, `active` |
| `garden.site` | `garden_site.py` | `name`*, `farm_id`*, `company_id` (lié à la ferme, stocké), `partner_id`, `latitude`, `longitude`, `garden_ids`, `active` |
| `garden.garden` (« Îlot ») | `garden_garden.py` | `name`*, `code`, `site_id`*, `company_id` (lié), `culture_type` (plein air / sous abri), `irrigation_type` (goutte-à-goutte / aspersion / manuel / aucun), `irrigation_flow` (L/h), `area` (somme des planches, stockée), `bed_ids`, `active` |
| `garden.bed` | `garden_bed.py` | `name`*, `code` (unique par site), `garden_id`*, `site_id` et `company_id` (liés, stockés), `length`, `width`, `area` (stockée), `soil_type`, `notes`, `active`, `crop_ids`, `current_crop_ids` (calculé à la date du jour), `action_ids` ; hérite de `mail.thread` |
| `garden.species` | `garden_species.py` | `name`* (unique), `family`*, `rotation_years` (défaut 3), `variety_ids`, `active` |
| `garden.variety` | `garden_variety.py` | `name`*, `species_id`*, `supplier_id`, `seed_product_id`, `harvest_product_id` (`product.product`), `seeds_per_gram`, `germination_rate` (%), `organic_status`, `template_ids`, `active` |
| `garden.crop.template` | `garden_crop_template.py` | `name`*, `variety_id`*, `species_id` (lié), `culture_type`, `propagation` (+ `plant_product_id`), `row_count`, `row_spacing`, `plant_spacing`, `density` (calculée), `days_to_transplant`, `days_to_maturity`, `harvest_window_days`, `expected_yield`, `expected_price` (défaut : prix de vente du produit récolté), `step_ids`, `active` |
| `garden.crop.template.step` | `garden_crop_template.py` | `template_id`*, `sequence`, `operation_type_id`*, `day_offset`, `expected_duration` (h/m²) |
| `garden.operation.type` | `garden_operation_type.py` | `name`*, `category`*, `default_scope`*, `sequence`, `active` (version minimale ; `garden.action.type` sera fusionné en phase 3) |
| `garden.crop` | `garden_crop.py` | `template_id`*, `variety_id` et `species_id` (liés, stockés), `bed_id`*, `company_id` (lié à la planche), `date_start`, `date_end`, `sowing_quantity`, `planted_quantity`, `quantity_harvested` (kg), `value_harvested` (€), `notes`, `action_ids` |
| `garden.action.type` | `garden_action_type.py` | `name`, `description` |
| `garden.action` | `garden_action.py` | `type_id`*, `crop_id`*, `bed_id` (lié à `crop_id.bed_id`, stocké), `date`, `duration` (minutes), `description` |
| `garden.postprocess` | `garden_postprocess.py` | `name`, `date`, `action_id`, `description` |
| `garden.loss` | `garden_loss.py` | `date`, `bed_id`, `quantity`, `reason` |
| `product.template` (extension) | `product_template.py` | `garden_variety_ids` et `is_garden_product` (calculés, avec recherche) |

\* champ obligatoire.

Supprimés en phase 1 : `garden.plot`, `garden.culture.mode`, `garden.crop.catalog` (ses champs sont repris par `garden.crop.template`, `garden.variety` et `garden.species`). Les tables PostgreSQL correspondantes ne sont pas supprimées par Odoo lors de la mise à jour.

Notes :
- `density` (plants/m²) = 10 000 / (`row_spacing` × `plant_spacing`), avec les écartements en cm ; `row_count` est informatif.
- `soil_type` est une sélection (sableux, limoneux, argileux, limono-argileux, humifère, autre).
- Unicité du code de planche : contrainte SQL `UNIQUE (site_id, code)` ; plusieurs planches sans code sont acceptées.

## Menus

- **Maraîchage › Exploitation** : Fermes, Sites, Îlots, Planches
- **Maraîchage › Production** : Cultures (avec un onglet Actions), Actions, Post-process, Pertes
- **Maraîchage › Statistiques** : Statistiques (Graphiques), Production, Occupation des planches
- **Maraîchage › Configuration** (chef de culture) : Espèces, Variétés, Itinéraires techniques, Types d'opération, Produits maraîchers (produits filtrés sur ceux liés à une variété)

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

Trois groupes sous le privilège **Maraîchage** (`security/garden_security.xml`), chacun impliquant le précédent ; l'ouvrier implique `base.group_user`. `admin` et `OdooBot` sont dans le groupe Gérant.

| Groupe | Structure (ferme, site, îlot, planche) | Catalogue (espèce, variété, itinéraire, type d'opération) | Cultures, actions, types d'action, post-process, pertes |
|---|---|---|---|
| Ouvrier | lecture | lecture | lecture, écriture, création (pas de suppression) |
| Chef de culture | lecture, écriture, création | tous droits | tous droits |
| Gérant | tous droits | tous droits | tous droits |

Le menu racine est réservé au groupe Ouvrier (donc à tous ses groupes impliquants) et le menu Configuration au chef de culture. Un utilisateur interne sans groupe Maraîchage n'a aucun accès aux modèles.

Règles multi-société (`ir.rule`, `company_id in company_ids`) sur `garden.farm`, `garden.site`, `garden.garden`, `garden.bed` et `garden.crop`. Les modèles `garden.action`, `garden.postprocess` et `garden.loss` ne portent pas encore de société (ils seront remplacés aux phases 3 et 4).

## Tests

Le dossier `tests/` contient (tests `post_install`, `-at_install`) :
- `test_install.py` : chaîne ferme > site > îlot > planche > espèce > variété > itinéraire > culture > action, statistiques, données d'occupation, action `odoo_garden.action_garden_farm`, absence des modèles supprimés ;
- `test_structure.py` : société héritée, surfaces, unicité du code par site, archivage, cultures en place, règle multi-société ;
- `test_catalog.py` : espèces, variétés, densité et prix d'un itinéraire, étapes, types d'opération par défaut, lien produit / variété ;
- `test_security.py` : hiérarchie des groupes, droits de l'ouvrier, du chef de culture et du gérant.

```
cd <racine du projet> && ./run.sh -d garden_test -i odoo_garden --test-enable --test-tags /odoo_garden --stop-after-init
```

Les données de démonstration ne sont chargées qu'avec `--with-demo` (désactivées par défaut en Odoo 19). Ajouter `--http-port=<port>` si le serveur de développement tourne déjà.

## Points connus / à corriger

- **Chart.js** : chargé par une balise `<script>` dans le template OWL depuis un CDN, sans version fixée, avec un `setTimeout` de 50 ms avant le rendu ; les graphiques peuvent rester vides.
- **Manifeste** : `author` et `website` contiennent encore des valeurs par défaut.
- **`action_garden_statistics`** n'est rattachée à aucun menu.
- **Mise à jour depuis la phase 0** : les cultures existantes perdent leur lien vers l'ancien catalogue (`template_id` vide, contrainte NOT NULL non posée) ; aucune migration de données n'est fournie (aucune donnée de production, hypothèse 1).
- **Statistiques SQL** : toujours en SQL brut, sans règles d'accès ni multi-société (remplacées en phase 5).
- **Description du module** : Odoo interprète `README.md` en reStructuredText lors de l'installation et journalise des avertissements de syntaxe sans conséquence.

## À venir

La feuille de route complète (version payante intégrée aux applications Odoo) est décrite dans [`docs/SPECIFICATIONS.md`](docs/SPECIFICATIONS.md).

- Phase 2 : saisons, états et prévisions des cultures, rétro-planning (`days_to_maturity` de l'itinéraire)
- Traçabilité de la graine au client
- Prise en compte des pertes dans les statistiques (taux de perte, rendement)
- Schéma visuel des sites et planches
