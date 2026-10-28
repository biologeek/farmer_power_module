# Odoo Garden

Module Odoo 19 (`odoo_garden`, version `19.0.1.2.0`, licence LGPL-3) pour la gestion d'une exploitation maraîchère : structure de la ferme (ferme, site, îlot, planche, avec surfaces et irrigation), catalogue (espèces, variétés liées aux produits, itinéraires techniques), planification (saisons, plan de culture, rétro-planning, besoins en semences), suivi des cultures et des actions sur planche, post-process, pertes et statistiques.

Le module dépend de `base`, `web`, `product`, `uom` et `mail` et s'installe comme une application (menu **Maraîchage**). Il est livré à la **phase 2** (planification) de la feuille de route (`docs/SPECIFICATIONS.md`, § 7).

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
static/src/js|xml|scss/   Actions client OWL (statistiques, Gantt du plan de culture) et styles
static/tests/tours/       Tour de test du Gantt
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
                │   ├── garden.season (Saison / plan de culture)
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
| `garden.season` | `garden_season.py` | `name`* (unique par société), `date_start`*, `date_end`*, `company_id`*, `state` (brouillon / validé / clôturé), `crop_ids`, `crop_count`, `notes` ; hérite de `mail.thread` |
| `garden.crop` | `garden_crop.py` | `name` (référence `T-2027-P12-01`, future étiquette de lot), `season_id`, `template_id`*, `variety_id`, `species_id` et `family` (liés, stockés), `bed_id`*, `bed_share` (%), `area` (m², calculée), `company_id` (lié à la planche), `state` (planifiée / semée / en place / en récolte / terminée / annulée), dates prévues `planned_sowing_date`, `planned_transplant_date`, `planned_harvest_start`, `planned_harvest_end`, dates réelles `date_start`, `date_end`, `occupation_start` / `occupation_end` (calculées), prévisionnel `planned_plant_qty`, `expected_yield_qty`, `expected_revenue`, `planned_seed_count`, `planned_seed_qty` (g), avertissements `has_overlap`, `overlap_share`, `overlap_warning`, `has_rotation_conflict`, `rotation_warning` (calculés, non stockés), `sowing_quantity`, `planted_quantity`, `quantity_harvested` (kg) et `value_harvested` (€) (saisis, conservés jusqu'aux phases 4-5), `notes`, `action_ids` ; hérite de `mail.thread` |
| `garden.season.plan.wizard` | `garden_season_plan_wizard.py` | Assistant transitoire : `season_id`, `template_id`, `bed_ids`, `target` (récolte / semis), `target_date`, `stagger_days`, `bed_share`, `preview` |
| `res.config.settings` (extension) | `res_config_settings.py` | `garden_seed_margin` (paramètre système `odoo_garden.seed_margin`, défaut 20 %) |
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
- **Maraîchage › Planification** : Saisons, Plan de culture (Gantt), Calendrier, Besoins en semences, Planifier en série (chef de culture)
- **Maraîchage › Production** : Cultures (avec un onglet Actions), Actions, Post-process, Pertes
- **Maraîchage › Statistiques** : Statistiques (Graphiques), Production
- **Maraîchage › Configuration** (chef de culture) : Espèces, Variétés, Itinéraires techniques, Types d'opération, Paramètres (administrateur : marge de semis), Produits maraîchers (produits filtrés sur ceux liés à une variété)

## Statistiques

Les écrans de statistiques sont des actions client OWL (`ir.actions.client`, déclarées dans `views/garden_statistics_views.xml`) qui appellent des méthodes Python via le service `orm` :

| Tag client | Méthode serveur | Contenu |
|---|---|---|
| `garden_statistics` | `garden.action.get_statistics_data()` | Camembert de la durée totale par type d'action ; barres empilées de la durée par culture et par type d'action (Chart.js) |
| `garden_production_statistics` | `garden.crop.get_production_statistics_data()` | Quantité (kg) et valeur (€) récoltées par mois (`date_end`, à défaut `date_start`), par planche et par culture |
| `garden_bed_occupancy` | `garden.bed.get_occupancy_data(domain, season_id, site_id)` | Plan de culture : voir la section « Planification » |

Les agrégations sont écrites en SQL brut (`self.env.cr.execute`) et ne tiennent donc pas compte des règles d'accès ni du multi-société.

## Planification (phase 2)

**Saison** : `garden.season` regroupe les cultures d'une année (brouillon, validé, clôturé). Les boutons de la saison changent l'état ; le bouton « Planifier en série » ouvre l'assistant.

**Référence de la culture** : `<initiale de l'espèce>-<année de la saison>-<code de la planche>-<numéro>` (ex. `T-2027-P12-01`), attribuée à la création et recalculée si la planche, l'itinéraire ou la saison change. Elle servira de nom de lot de traçabilité (phase 4).

**Rétro-planning** (`garden.crop.template._plan_dates`) :
- depuis le semis : repiquage = semis + `days_to_transplant` (vide en semis direct), début de récolte = semis + `days_to_maturity`, fin = début + `harvest_window_days` ;
- depuis la récolte visée : semis = début de récolte − `days_to_maturity`, puis le reste comme ci-dessus.

UX : saisir ou modifier le **semis prévu** recalcule repiquage, début et fin de récolte ; saisir ou modifier le **début de récolte prévu** recalcule le semis et les autres dates (onchange). Repiquage et fin de récolte restent modifiables à la main sans cascade. Changer d'itinéraire recalcule depuis le semis s'il est saisi, sinon depuis la récolte. Les boutons « Recalculer depuis le semis / la récolte » du formulaire appliquent la même logique, et la création par code complète les dates manquantes.

**Assistant de création en série** (`garden.season.plan.wizard`, réservé au chef de culture) : saison, itinéraire, planches, date de récolte ou de semis visée, décalage en jours entre planches successives (échelonnement) et part de planche. Il crée une culture par planche et ouvre la liste des cultures créées.

**Période d'occupation** d'une planche (`occupation_start` / `occupation_end`) : repiquage prévu pour les plants (autoproduits ou achetés), sinon début réel ou semis prévu ; jusqu'à la fin réelle, à défaut la fin de récolte prévue. Elle sert aux contrôles et à `current_crop_ids` de la planche.

**Contrôles** (avertissements uniquement, calculés sur la culture, affichés en bannière dans le formulaire, en colonnes dans la liste et dans le Gantt) :
- *chevauchement* : la somme des `bed_share` des cultures simultanées sur la planche (hors annulées) dépasse 100 %. Évalué à chaque début de période, pour ne pas additionner des cultures qui ne sont jamais présentes ensemble ;
- *rotation* : une culture de la même famille botanique a quitté la planche depuis moins de `rotation_years` (de l'espèce de la culture) ; la famille « Autre » n'est pas contrôlée.

**Étapes prévues** : `garden.crop._get_planned_steps()` retourne, triées par date, les étapes de l'itinéraire (`step`, `operation_type`, `date` = semis prévu + `day_offset`, `duration` en heures = durée attendue par m² × surface). **La création des opérations planifiées est reportée à la phase 3** (`garden.operation` n'existe pas encore) : ni bouton ni génération à la validation de la saison pour le moment.

**Besoins en semences** : par culture, `planned_plant_qty` (surface × densité, modifiable) puis `planned_seed_count` = plants / germination × (1 + marge) et `planned_seed_qty` (g) = graines / graines par gramme. Les plants achetés ne demandent aucune semence. La marge est le paramètre système `odoo_garden.seed_margin` (Maraîchage › Configuration › Paramètres, 20 % par défaut) ; la modifier recalcule les cultures. Le rapport (Planification › Besoins en semences) est un pivot / une liste de `garden.crop` groupés par variété et saison ; `garden.crop.get_seed_needs(domain)` retourne les mêmes totaux par variété. Aucun lien Achats (phase 7).

**Plan de culture (Gantt)** : action client OWL (`garden_bed_occupancy`), compatible Community, sans ressource externe. Filtres saison et site, planches regroupées par îlot (option « masquer les planches libres »), couleur par famille botanique, barre prévue hachurée (semis → fin de récolte) et barre réalisée pleine, icône d'avertissement, clic sur une barre pour ouvrir la culture. Les cultures simultanées d'une planche sont placées sur des lignes distinctes.

**Calendrier** : vue calendar des cultures non annulées (semis prévu → fin de récolte prévue, couleur par espèce).

## Contrôleur

`GET /odoo/garden` redirige un utilisateur connecté vers l'action des fermes, et un visiteur anonyme vers la page de connexion.

## Sécurité

Trois groupes sous le privilège **Maraîchage** (`security/garden_security.xml`), chacun impliquant le précédent ; l'ouvrier implique `base.group_user`. `admin` et `OdooBot` sont dans le groupe Gérant.

| Groupe | Structure (ferme, site, îlot, planche) | Catalogue (espèce, variété, itinéraire, type d'opération) | Cultures, actions, types d'action, post-process, pertes |
|---|---|---|---|
| Ouvrier | lecture | lecture | lecture, écriture, création (pas de suppression) ; saisons : lecture seule |
| Chef de culture | lecture, écriture, création | tous droits | tous droits |
| Gérant | tous droits | tous droits | tous droits |

Le menu racine est réservé au groupe Ouvrier (donc à tous ses groupes impliquants) et le menu Configuration au chef de culture. Un utilisateur interne sans groupe Maraîchage n'a aucun accès aux modèles.

Les saisons et l'assistant de planification en série sont réservés au chef de culture (et au gérant) en écriture ; l'ouvrier lit les saisons.

Règles multi-société (`ir.rule`, `company_id in company_ids`) sur `garden.farm`, `garden.site`, `garden.garden`, `garden.bed`, `garden.season` et `garden.crop`. Les modèles `garden.action`, `garden.postprocess` et `garden.loss` ne portent pas encore de société (ils seront remplacés aux phases 3 et 4).

## Tests

Le dossier `tests/` contient (tests `post_install`, `-at_install`) :
- `test_install.py` : chaîne ferme > site > îlot > planche > espèce > variété > itinéraire > culture > action, statistiques, données d'occupation, action `odoo_garden.action_garden_farm`, absence des modèles supprimés ;
- `test_structure.py` : société héritée, surfaces, unicité du code par site, archivage, cultures en place, règle multi-société ;
- `test_catalog.py` : espèces, variétés, densité et prix d'un itinéraire, étapes, types d'opération par défaut, lien produit / variété ;
- `test_security.py` : hiérarchie des groupes, droits de l'ouvrier, du chef de culture et du gérant ;
- `test_planning.py` : saisons (états, contraintes, droits, multi-société), référence et surface de la culture, prévisionnel, rétro-planning, étapes prévues, assistant de création en série (échelonnement, droits), chevauchement et rotation, besoins en semences et marge ;
- `test_gantt.py` : données du Gantt (groupes, lignes, filtres), vue calendrier, tour navigateur `garden_gantt_tour` ;
- `test_demo.py` : plan de culture de démonstration (ignoré sans données de démo).

Le tour navigateur nécessite Chrome et le paquet Python `websocket-client` ; sans lui Odoo l'ignore (« skipped »). Pour l'exécuter sans modifier l'environnement : `pip install --target /tmp/pylibs websocket-client` puis `PYTHONPATH=/tmp/pylibs ./run.sh ...`.

```
cd <racine du projet> && ./run.sh -d garden_test -i odoo_garden --test-enable --test-tags /odoo_garden --stop-after-init
```

La démo contient la saison 2027 (12 cultures dont un chevauchement sur N1-01 et une rotation sur S1-03 grâce à la tomate 2026) et une saison 2026 close. Les données de démonstration ne sont chargées qu'avec `--with-demo` (désactivées par défaut en Odoo 19). Ajouter `--http-port=<port>` si le serveur de développement tourne déjà.

## Points connus / à corriger

- **Opérations planifiées** : non générées en phase 2 (voir « Étapes prévues »), à brancher sur `_get_planned_steps()` en phase 3.
- **Référence des cultures existantes** : les cultures créées avant la phase 2 gardent la référence `/` après mise à jour.
- **Avertissements non stockés** : `has_overlap` et `has_rotation_conflict` ne sont pas filtrables dans la recherche.
- **Anciennes cultures** : `date_start` / `date_end` sont désormais les dates *réelles* ; les cultures sans dates prévues n'apparaissent pas dans le calendrier.
- **Paramètres** : l'écran de configuration est réservé à l'administrateur système (groupe `base.group_system`).
- **Chart.js** : chargé par une balise `<script>` dans le template OWL depuis un CDN, sans version fixée, avec un `setTimeout` de 50 ms avant le rendu ; les graphiques peuvent rester vides.
- **Manifeste** : `author` et `website` contiennent encore des valeurs par défaut.
- **`action_garden_statistics`** n'est rattachée à aucun menu.
- **Mise à jour depuis la phase 0** : les cultures existantes perdent leur lien vers l'ancien catalogue (`template_id` vide, contrainte NOT NULL non posée) ; aucune migration de données n'est fournie (aucune donnée de production, hypothèse 1).
- **Statistiques SQL** : toujours en SQL brut, sans règles d'accès ni multi-société (remplacées en phase 5).
- **Description du module** : Odoo interprète `README.md` en reStructuredText lors de l'installation et journalise des avertissements de syntaxe sans conséquence.

## À venir

La feuille de route complète (version payante intégrée aux applications Odoo) est décrite dans [`docs/SPECIFICATIONS.md`](docs/SPECIFICATIONS.md).

- Phase 3 : opérations et main-d'œuvre (génération des opérations planifiées à partir de `_get_planned_steps()`)
- Traçabilité de la graine au client
- Prise en compte des pertes dans les statistiques (taux de perte, rendement)
- Schéma visuel des sites et planches
