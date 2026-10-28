# Odoo Garden

Module Odoo 19 (`odoo_garden`, version `19.0.1.6.0`, licence LGPL-3) pour la gestion d'une exploitation maraîchère : structure de la ferme (ferme, site, îlot, planche, avec surfaces et irrigation), catalogue (espèces, variétés liées aux produits, itinéraires techniques), planification (saisons, plan de culture, rétro-planning, besoins en semences), opérations et main-d'œuvre (travail planifié puis réalisé, chronomètre, coût, répartition sur les cultures), stock (intrants consommés, récoltes en entrée de stock avec lot de culture, pertes et rebuts, traçabilité), ventes et rentabilité (chiffre d'affaires attribué aux cultures, marge, tableau de bord), conformité française (registre phytosanitaire, délai avant récolte, registre de fertilisation, export de certification bio).

Le module dépend de `base`, `web`, `product`, `uom`, `mail`, `hr`, `stock`, `account`, `sale_management` et `sale_stock` et s'installe comme une application (menu **Maraîchage**). Il est livré à la **phase 6** (conformité) de la feuille de route (`docs/SPECIFICATIONS.md`, § 7).

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
  garden_compliance.py    Export XLSX des registres réglementaires
models/                   Modèles métier (un fichier par modèle)
views/                    Vues list/form, actions et menus
static/src/js|xml|scss/   Actions client OWL (Gantt du plan de culture, tableau de bord de rentabilité) et styles
static/tests/tours/       Tours de test (Gantt, « Ma journée », tableau de bord, registres de conformité)
report/
  garden_bed_report.xml   Étiquettes QR des planches (rapport QWeb PDF)
  garden_compliance_report.xml  Registres phytosanitaire et de fertilisation (rapport QWeb PDF, A4 paysage)
security/
  garden_security.xml     Catégorie, privilège, groupes et règles multi-société
  ir.model.access.csv     Droits d'accès par groupe
data/                     Types d'opération par défaut, emplacements virtuels de stock (noupdate), activation des registres réglementaires
demo/                     Données de démonstration (ferme, sites, îlots, planches, catalogue, opérations, stock, récoltes et factures clients)
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
                │   ├── garden.operation.allocation ──> garden.operation ──> garden.operation.type
                │   │                                        ├── garden.operation.worker ──> hr.employee
                │   │                                        ├── garden.operation.input ──> stock.move (consommation)
                │   │                                        ├── stock.move (récolte, avec stock.lot)
                │   │                                        └── (scope) cultures / planches / îlot
                │   ├── stock.lot (lots de récolte, garden_crop_id)
                │   └── garden.loss (Perte) ──> stock.scrap (après récolte)
product.template ──(garden_variety_ids, calculé)── garden.variety
```

| Modèle | Fichier | Champs principaux |
|---|---|---|
| `garden.farm` | `garden_farm.py` | `name`*, `company_id`* (défaut : société courante), `site_ids`, `active` |
| `garden.site` | `garden_site.py` | `name`*, `farm_id`*, `company_id` (lié à la ferme, stocké), `partner_id`, `latitude`, `longitude`, `garden_ids`, `active` |
| `garden.garden` (« Îlot ») | `garden_garden.py` | `name`*, `code`, `site_id`*, `company_id` (lié), `culture_type` (plein air / sous abri), `irrigation_type` (goutte-à-goutte / aspersion / manuel / aucun), `irrigation_flow` (L/h), `area` (somme des planches, stockée), `bed_ids`, `active` |
| `garden.bed` | `garden_bed.py` | `name`*, `code` (unique par site), `garden_id`*, `site_id` et `company_id` (liés, stockés), `length`, `width`, `area` (stockée), `soil_type`, `notes`, `active`, `crop_ids`, `current_crop_ids` (calculé à la date du jour), `operation_ids` (opérations directes), `operation_count` ; hérite de `mail.thread` |
| `garden.species` | `garden_species.py` | `name`* (unique), `family`*, `rotation_years` (défaut 3), `variety_ids`, `active` |
| `garden.variety` | `garden_variety.py` | `name`*, `species_id`*, `supplier_id`, `seed_product_id`, `harvest_product_id` (`product.product`), `seeds_per_gram`, `germination_rate` (%), `organic_status`, `template_ids`, `active` |
| `garden.crop.template` | `garden_crop_template.py` | `name`*, `variety_id`*, `species_id` (lié), `culture_type`, `propagation` (+ `plant_product_id`), `row_count`, `row_spacing`, `plant_spacing`, `density` (calculée), `days_to_transplant`, `days_to_maturity`, `harvest_window_days`, `expected_yield`, `expected_price` (défaut : prix de vente du produit récolté), `step_ids`, `active` |
| `garden.crop.template.step` | `garden_crop_template.py` | `template_id`*, `sequence`, `operation_type_id`*, `day_offset`, `expected_duration` (h/m²) |
| `garden.operation.type` | `garden_operation_type.py` | `name`*, `category`* (préparation du sol, semis, repiquage, plantation, irrigation, désherbage, fertilisation, traitement, paillage, récolte, après récolte, autre), `default_scope`*, `requires_quantity` (calculé d'après la catégorie, modifiable), `icon` (classe Font Awesome, calculée, modifiable), `description`, `sequence`, `active` ; remplace `garden.action.type` |
| `garden.season` | `garden_season.py` | `name`* (unique par société), `date_start`*, `date_end`*, `company_id`*, `state` (brouillon / validé / clôturé), `crop_ids`, `crop_count`, `notes` ; hérite de `mail.thread` |
| `garden.crop` | `garden_crop.py` | `name` (référence `T-2027-P12-01`, future étiquette de lot), `season_id`, `template_id`*, `variety_id`, `species_id` et `family` (liés, stockés), `bed_id`*, `bed_share` (%), `area` (m², calculée), `company_id` (lié à la planche), `state` (planifiée / semée / en place / en récolte / terminée / annulée), dates prévues `planned_sowing_date`, `planned_transplant_date`, `planned_harvest_start`, `planned_harvest_end`, dates réelles `date_start`, `date_end`, `occupation_start` / `occupation_end` (calculées), prévisionnel `planned_plant_qty`, `expected_yield_qty`, `expected_revenue`, `planned_seed_count`, `planned_seed_qty` (g), avertissements `has_overlap`, `overlap_share`, `overlap_warning`, `has_rotation_conflict`, `rotation_warning` (calculés, non stockés), `sowing_quantity`, `planted_quantity`, `harvested_qty` (calculé et stocké : somme des mouvements de récolte), `lot_ids` / `lot_count` (lots de récolte), `harvest_move_ids` (chef de culture), `loss_ids`, `loss_count`, `loss_qty`, `loss_rate` (calculés), `notes`, `operation_ids` (opérations directes), `allocation_ids`, `labour_hours`, `labour_cost` et `input_cost` (calculés depuis les répartitions), `operation_count` ; boutons intelligents Opérations, Récolté, Pertes, Traçabilité, Lots ; `quantity_harvested` et `value_harvested` (saisis) sont supprimés ; hérite de `mail.thread` |
| `garden.season.plan.wizard` | `garden_season_plan_wizard.py` | Assistant transitoire : `season_id`, `template_id`, `bed_ids`, `target` (récolte / semis), `target_date`, `stagger_days`, `bed_share`, `preview` |
| `res.config.settings` (extension) | `res_config_settings.py` | `garden_seed_margin` (paramètre système `odoo_garden.seed_margin`, défaut 20 %), `garden_default_hourly_rate` (paramètre système `odoo_garden.default_hourly_rate`, défaut 15 par heure), et `garden_stock_location_id`, `garden_production_location_id`, `garden_consumption_location_id` (liés à la société, voir « Stock ») ; **phase 6** : `garden_compliance_enabled` (paramètre `odoo_garden.compliance_enabled`, registres réglementaires) |
| `garden.operation` | `garden_operation.py` | `name` (proposé : type et cible), `type_id`*, `category` (liée), `state`* (planifiée / en cours / faite / annulée), `planned_date`, `date`, `company_id`*, `scope`* (culture / planche / îlot) avec `crop_ids`, `bed_ids` ou `garden_id`, `garden_main_id` (îlot principal, stocké), `employee_ids` (`hr.employee`), `duration` (h par employé, `float_time`), `worker_ids`, `total_hours`, `labour_cost` (chef de culture et gérant), `timer_start`, récolte (`harvest_product_id`, `harvest_qty`, `harvest_uom_id`), irrigation (`water_volume`), traitement (`target`, `weather_notes`), `input_ids`, `input_cost` (chef de culture et gérant), `move_ids` (mouvements de stock, chef de culture), `template_step_id`, `allocation_ids`, `allocation_warning`, `description` ; hérite de `mail.thread` et `hr.mixin` ; remplace `garden.action` et `garden.postprocess` ; **phase 6** : `dar_override`, `dar_override_reason`, `dar_override_user_id` (gérant), `dar_warning` (calculé) |
| `garden.operation.worker` | `garden_operation_worker.py` | `operation_id`*, `employee_id`* (unique par opération), `duration` (h), `labour_cost` (chef de culture et gérant), `company_id` (lié) |
| `garden.operation.allocation` | `garden_operation_allocation.py` | `operation_id`*, `crop_id`*, `share` (%), `hours`, `labour_cost` et `input_cost` (chef de culture et gérant), `company_id`, `date`, `type_id`, `category`, `bed_id`, `template_id`, `variety_id` (liés, stockés) |
| `garden.operation.input` | `garden_operation_input.py` | `operation_id`*, `product_id`* (produits avec un type d'intrant), `garden_input_type` et `tracking` (liés), `quantity`*, `uom_id`*, `lot_id`, `move_id` (dernier mouvement de consommation), `consumed`, `unit_cost` et `cost` (chef de culture et gérant), `company_id` (lié), `sequence` ; **phase 6** : `treated_area` (surface traitée), `dose` (par hectare, calculée) |
| `hr.employee` (extension) | `hr_employee.py` | `garden_hourly_cost` (coût horaire maraîchage, chef de culture et gérant) |
| `garden.loss` | `garden_loss.py` | `crop_id`*, `date`*, `stage`* (avant / après récolte), `product_id` (proposé d'après la variété), `quantity`*, `uom_id`*, `quantity_ref` (convertie dans l'unité du produit), `cause`* (maladie, ravageur, météo, invendu, autre), `notes`, `scrap_id`, `lot_id` (lié), `bed_id` et `company_id` (liés, stockés) ; hérite de `mail.thread` |
| `garden.traceability` | `garden_traceability.py` | Modèle transitoire en lecture seule : `lot_id`, `crop_id`, `lot_ids`, `operation_ids`, `input_ids`, `seed_input_ids`, `seed_lot_ids`, `seed_receipt_line_ids`, `harvest_line_ids`, `out_line_ids`, `usage_input_ids` (calculés en sudo) |
| `res.company` (extension) | `res_company.py` | `garden_production_location_id`, `garden_consumption_location_id`, `garden_stock_location_id` |
| `stock.move` (extension) | `stock_move.py` | `garden_operation_id`, `garden_crop_id`, `garden_kind` (consommation, annulation de consommation, récolte, annulation de récolte), `garden_reverse_of_id`, `garden_reversal_ids` |
| `stock.lot` (extension) | `stock_move.py`, `garden_traceability.py` | `garden_crop_id` (culture d'origine), `action_garden_traceability()` |
| `product.template` (extension) | `product_template.py` | `garden_input_type` (semence, plant, engrais, amendement, phytosanitaire, substrat, autre), `garden_variety_ids` et `is_garden_product` (calculés, avec recherche ; un produit avec un type d'intrant est un produit maraîcher) ; **phase 6** : `amm_number`, `pre_harvest_interval_days` (DAR), `is_organic_allowed`, `nitrogen_content` (%), modifiables par le chef de culture |
| `garden.crop` (extension phase 6) | `garden_crop.py` | `harvest_allowed_from` et `harvest_allowed_warning` (calculés, délai avant récolte) |
| `garden.compliance.wizard` | `garden_compliance.py` | Écran transitoire des registres : `register` (phytosanitaire, fertilisation, bio), `date_from`, `date_to`, `season_id`, `crop_ids`, lignes `line_ids` (calculées par l'ORM) |
| `garden.compliance.line` | `garden_compliance.py` | Ligne transitoire d'un registre : date, saison, culture, planche, parcelle, produit, n° AMM, quantité, surface traitée, dose, opérateur, cible, conditions ; azote (`nitrogen_kg`, `nitrogen_per_ha`) ; bio (`organic_crop`, `organic_allowed`, `alert`, `lot_id`) |

\* champ obligatoire.

Supprimés en phase 1 : `garden.plot`, `garden.culture.mode`, `garden.crop.catalog` (ses champs sont repris par `garden.crop.template`, `garden.variety` et `garden.species`). Les tables PostgreSQL correspondantes ne sont pas supprimées par Odoo lors de la mise à jour.

Supprimés en phase 3 : `garden.action`, `garden.action.type` (fusionné dans `garden.operation.type`) et `garden.postprocess` (remplacés par `garden.operation`). Leurs tables restent orphelines après la mise à jour, sans migration de données (aucune donnée de production, hypothèse 1).

Notes :
- `density` (plants/m²) = 10 000 / (`row_spacing` × `plant_spacing`), avec les écartements en cm ; `row_count` est informatif.
- `soil_type` est une sélection (sableux, limoneux, argileux, limono-argileux, humifère, autre).
- Unicité du code de planche : contrainte SQL `UNIQUE (site_id, code)` ; plusieurs planches sans code sont acceptées.

## Menus

- **Maraîchage › Ma journée** : kanban mobile des opérations du jour et en retard (voir « Opérations et main-d'œuvre »)
- **Maraîchage › Exploitation** : Fermes, Sites, Îlots, Planches
- **Maraîchage › Planification** : Saisons, Plan de culture (Gantt), Calendrier, Besoins en semences, Planifier en série (chef de culture)
- **Maraîchage › Production** : Cultures (avec les onglets Opérations, Récoltes et Pertes), Opérations (onglet Intrants), Calendrier des opérations, Pertes, Lots de récolte
- **Maraîchage › Rentabilité** (gérant) : Tableau de bord, Rapport de rentabilité (pivot, graphique, liste ; actualisé à l'ouverture), Paramètres de rentabilité (administrateur)
- **Maraîchage › Conformité (registres réglementaires, France)** (chef de culture et gérant) : Registre phytosanitaire, Registre de fertilisation, Export certification bio (voir « Conformité »)
- **Maraîchage › Statistiques** : Temps de travail (pivot et graphique sur les répartitions)
- **Maraîchage › Configuration** (chef de culture) : Espèces, Variétés, Itinéraires techniques, Types d'opération, Paramètres (administrateur : marge de semis), Produits maraîchers (produits filtrés sur ceux liés à une variété)

## Statistiques et plan de culture

Le Gantt (`garden_bed_occupancy`, `garden.bed.get_occupancy_data(domain, season_id, site_id)`, voir « Planification ») reste une action client OWL. Les anciens écrans « Statistiques (Graphiques) » et « Production » (Chart.js par CDN, SQL brut) sont supprimés en phase 5 : les heures par catégorie sont dans **Statistiques › Temps de travail** (pivot et graphique natifs sur `garden.operation.allocation`) et le tableau de bord, la production et les ratios dans la rentabilité (voir ci-dessous).

## Ventes et rentabilité (phase 5)

**Avancement des cultures** (§ 3.4, point 3, rattrapé) : quand une opération passe à « faite », les cultures qui lui sont réparties avancent : semis -> « semée », plantation ou repiquage -> « en place », première récolte -> « en récolte ». L'état ne recule jamais (rouvrir une opération ne défait rien), une culture terminée ou annulée n'est pas touchée. `date_start` reçoit la date du premier semis, repiquage ou plantation fait, seulement s'il est vide (jamais d'écrasement d'une saisie manuelle). `date_end` n'est pas touchée par les récoltes (la culture occupe la planche jusqu'à sa fin, ce qui garde les contrôles de chevauchement et la répartition des opérations d'îlot cohérents) : elle est renseignée, si vide, quand la culture passe à « terminée » (date de la dernière récolte faite, à défaut le jour même).

**Champs de la culture** : `labour_hours`, `labour_cost`, `input_cost`, `loss_rate` (stockés depuis les phases précédentes) ; `revenue`, `fixed_cost`, `margin`, `margin_per_hour`, `margin_per_m2`, `revenue_gap`, `sale_line_count` (**non stockés**, `compute_sudo`) ; `yield_gap`, `hours_gap`, `expected_hours`, `occupation_days`. Choix : le chiffre d'affaires dépend de factures (autre modèle, modifiables à tout moment), donc pas de champ stocké à recalculer ; il est recalculé à chaque lecture, le cache étant invalidé quand une facture change d'état. Le rapport de rentabilité en garde une copie. `margin = revenue - labour_cost - input_cost - fixed_cost`. Coûts, CA et marges sont réservés au chef de culture et au gérant (`groups=`) ; l'ouvrier ne voit que les heures et les écarts physiques. Les factures sont lues en `sudo()` dans le service `garden.revenue` : ni l'ouvrier ni le chef n'ont accès à la comptabilité.

**Charges fixes** (option) : paramètre `odoo_garden.fixed_cost_per_m2` (coût annuel par m²) ; imputées = coût/m² x surface x jours d'occupation / 365 (jours d'occupation = fin - début d'occupation + 1, périodes prévues à défaut de réelles). Actives seulement si le paramètre est > 0.

**Attribution du chiffre d'affaires** (`garden.revenue`, paramètre `odoo_garden.revenue_method`, défaut `prorata`). Sont comptées les lignes de produit des factures (`out_invoice`) et avoirs (`out_refund`) clients comptabilisés (`posted`). Le montant d'une ligne est son HT en monnaie de la société (`-balance`, converti par la comptabilité au taux de la date de facture ; négatif pour un avoir). Les ventes du Point de Vente ne sont pas prises en compte (phase 7).
- *Par lot* : ligne de facture -> ligne de commande (`sale_line_ids`) -> mouvements de livraison (`stock.move.sale_line_id`, module `sale_stock`) -> lignes de mouvement avec lot -> lot de culture (`stock.lot.garden_crop_id`). Le montant est réparti au prorata des quantités livrées par lot sur la ligne de commande (retours clients déduits). La part livrée sur un lot qui n'est pas un lot de culture, ou sans lot, n'est attribuée à aucune culture. Une facture sans commande de vente n'est pas attribuée par lot. **`sale_stock` est ajouté aux dépendances** car c'est lui qui relie la ligne de commande à ses mouvements de stock (`sale` seul ne le permet pas).
- *Au prorata* : pour chaque produit récolté et chaque mois de la facture (date comptable), le CA du produit est réparti entre les cultures au prorata de leurs quantités récoltées ce mois-là (mouvements de récolte terminés, annulations déduites, seules les quantités positives comptent). Un mois sans récolte du produit n'attribue rien : le CA n'est pas inventé. Un avoir réduit le CA du mois selon la même répartition.

**Rapport `garden.crop.profitability`** (§ 5.1) : une ligne par culture non annulée (saison, site, îlot, planche, espèce, famille, variété, surface, jours d'occupation, heures, coûts, récolte, CA, marge, ratios, prévu et écarts). *Choix de conception* : plutôt qu'une vue SQL qui dupliquerait en SQL l'attribution par lot ou au prorata mensuel, la règle n'existe qu'une fois, en Python (`garden.revenue`) ; le modèle est une table stockée remplie par `refresh()` (ORM, `sudo`), appelée à l'ouverture des menus Rapport et Tableau de bord, par le bouton « Actualiser » et par un cron quotidien. Les données peuvent donc être légèrement en retard entre deux ouvertures. Les ratios (marge/h, marge/m², rendement, taux de perte) sont des moyennes pondérées (ratio des sommes) dans les vues pivot et graphique, via `_read_group_select`, seul endroit où du SQL est écrit. Les montants sont dans la monnaie de chaque société : les additionner entre sociétés de monnaies différentes n'a pas de sens.

**Tableau de bord** (action client `garden_dashboard`, gérant) : chiffre d'affaires, marge, heures, marge par espèce, heures par catégorie d'opération, CA mensuel, 10 meilleures et 10 moins bonnes cultures à l'heure. Barres en HTML/CSS (OWL pur, aucune librairie externe).

**Fiche culture** : onglet « Rentabilité » (chef et gérant) et bouton « Ventes » qui liste les lignes attribuées (modèle transitoire `garden.crop.sale`, rempli en `sudo`) sans exposer les factures.

## Conformité (phase 6)

Fonctionnalités propres à la réglementation française (spécifications § 3.6), regroupées dans le menu **Conformité (registres réglementaires, France)**, réservé au chef de culture et au gérant. Elles sont isolées pour ne pas apparaître comme une obligation locale sur d'autres marchés (voir « Paramètre »). Dates, fuseaux : les dates sont celles de réalisation des opérations (`garden.operation.date`).

**Produits** (`product.template`, onglet « Maraîchage » de la fiche produit) : `amm_number` et `pre_harvest_interval_days` (DAR en jours, ≥ 0) pour les phytosanitaires, `is_organic_allowed` pour les phytosanitaires, engrais, amendements et substrats, `nitrogen_content` (% d'azote en masse, 0 à 100) pour les engrais. Ils ne sont visibles que du chef de culture et du gérant. Comme aucun groupe maraîchage n'implique de droit sur les produits, `product.template.write` s'exécute en `sudo` quand l'utilisateur est chef de culture, n'a pas le droit d'écriture sur les produits **et** ne modifie que `garden_input_type` et ces quatre champs ; toute autre modification suit les droits habituels (vérifié par test). La création d'un produit reste réservée aux droits Inventaire ou Ventes.

**Intrants** (`garden.operation.input`) : `treated_area` (m², proposée d'après la cible de l'opération : surface occupée des cultures, des planches ou de l'îlot ; modifiable si une partie seulement est traitée ; figée une fois l'opération faite, comme les autres champs verrouillés) et `dose` (quantité × 10 000 / surface traitée, donc par hectare, dans l'unité de la ligne). La cible (`target`), les conditions (`weather_notes`) et l'opérateur (employés de l'opération et lignes de temps) existent déjà depuis les phases 3 et 4 et sont réutilisés.

**Écran des registres** (`garden.compliance.wizard`, modèle transitoire, accès chef de culture et gérant) : choix de la période (`date_from`, `date_to`, sur la date de réalisation), de la saison et des cultures, boutons **Calculer** (liste), **Imprimer (PDF)** et **Exporter (XLSX)**. *Choix de conception* (cohérent avec `garden.revenue` de la phase 5, mais plus simple) : les lignes sont des enregistrements transitoires (`garden.compliance.line`) recalculés par l'ORM à chaque demande (donc jamais périmés), à partir des intrants des opérations **faites** ; aucune vue SQL ni donnée à actualiser. Les données sont lues en `sudo` (le chef de culture n'a pas les droits sur les employés) mais limitées aux sociétés autorisées de l'utilisateur. Une opération répartie sur plusieurs cultures donne une ligne par culture, avec la quantité et la surface traitée au prorata de la répartition ; une opération faite sans culture en place n'apparaît que sans filtre de saison ni de culture.

- **Registre phytosanitaire** : intrants de type phytosanitaire ; date, culture, parcelle (site / îlot / planche), surface traitée, produit, n° AMM, dose par hectare, quantité utilisée, opérateur, cible, conditions. PDF : rapport QWeb `odoo_garden.report_garden_compliance` (A4 paysage, `ir.actions.report` sur le modèle de l'écran). XLSX : contrôleur `GET /odoo_garden/compliance/xlsx/<id>` (`xlsxwriter`, comme les exports XLSX d'Odoo), qui refuse les utilisateurs sans droit.
- **Registre de fertilisation** : intrants de type engrais ; azote apporté `nitrogen_kg` = quantité en kg × teneur / 100 (conversion d'unité par `uom._has_common_reference` : un engrais en litres ou sans teneur est listé avec 0 et une remarque), `nitrogen_per_ha` = `nitrogen_kg` × 10 000 / surface fertilisée. **Unité retenue : kg N/ha** (les « unités d'azote » de la réglementation). La synthèse par planche et par saison (pivot, PDF et deuxième onglet XLSX) additionne les kg N et les kg N/ha des apports : chaque apport est ramené à l'hectare de sa surface fertilisée, une planche amendée deux fois cumule les deux doses.
- **Export certification bio** (XLSX uniquement, trois onglets) : « Semences » (par culture : statut bio de la variété, fournisseur de la variété, semences et plants utilisés, lots, origine de la réception d'après la traçabilité amont de la phase 4, date de réception), « Intrants » (intrants par culture et saison, avec le lot et `is_organic_allowed`) et « Alertes bio ». Une culture est *bio* si sa variété a le statut « Bio » ; un engrais, amendement, phytosanitaire ou substrat dont `is_organic_allowed` n'est pas coché, utilisé sur une culture bio, est signalé en rouge dans la liste, dans un bandeau et dans l'onglet d'alertes. Un produit non renseigné compte comme non autorisé.

**Délai avant récolte (DAR)** : une opération de catégorie récolte **faite** (à la validation, à la création directe à « faite » ou à la modification de sa date, de son périmètre ou de son état) dont la date est antérieure à la fin du DAR d'un traitement de la même culture lève une `ValidationError` bloquante, pour chaque culture concernée (récolte multiple, de planche ou d'îlot : cultures de la répartition). Règle : un traitement est une opération faite répartie sur la culture avec un intrant phytosanitaire dont le produit a un DAR > 0 ; il bloque si `date du traitement <= date de récolte < date du traitement + DAR` (récolte possible à partir du jour « traitement + DAR » inclus) ; traitements annulés, planifiés, d'une autre culture ou postérieurs à la récolte ignorés ; produits sans DAR ne bloquent pas. Le contrôle s'applique à tout utilisateur, y compris le chef de culture. **Dérogation** : `dar_override`, `dar_override_reason` (obligatoire) et `dar_override_user_id`, champs réservés au gérant (`groups=`, onglet « Récolte » de l'opération) ; le chef de culture et l'ouvrier ne les lisent ni ne les écrivent (`AccessError`) mais peuvent terminer une récolte déjà dérogée par un gérant. La dérogation est tracée dans le fil de discussion à l'activation (qui et pourquoi, champs suivis) puis à l'usage (note listant les cultures et traitements concernés). Avertissement en amont : bandeau rouge `dar_warning` sur la récolte non faite (date contrôlée = date de réalisation, à défaut le jour de la validation) ; la culture affiche `harvest_allowed_from` (fin du DAR du dernier traitement) et un bandeau tant qu'il n'est pas échu.

**Paramètre** `odoo_garden.compliance_enabled` (Paramètres > Maraîchage > Conformité, activé par défaut). Le menu est rattaché au groupe technique `group_garden_compliance`, impliqué par le chef de culture (donc par le gérant) tant que le paramètre est actif : le décocher retire cette implication (`res.config.settings.set_values`), ce qui masque les menus ; les écrans, impressions et exports lèvent en plus une erreur. À l'installation et à la mise à jour, `_garden_init_compliance` active le paramètre s'il n'a jamais été réglé, sans réactiver des registres désactivés. Le contrôle du DAR n'est pas désactivé par ce paramètre (il ne concerne que les produits qui ont un délai).

**Démo** : bouillie bordelaise avec un numéro d'AMM **fictif** (`AMM-DEMO-0000000 (numéro fictif)`) et un DAR de 7 jours, engrais organique à 5 % d'azote, deux traitements (tomate le 12 juin 2027, laitue le 20 avril 2027), la fertilisation de la tomate (12 kg = 0,6 kg d'azote) et les récoltes de la démo, conformes (tomate : 38 jours après le traitement).

## Planification (phase 2)

**Saison** : `garden.season` regroupe les cultures d'une année (brouillon, validé, clôturé). Les boutons de la saison changent l'état ; le bouton « Planifier en série » ouvre l'assistant.

**Référence de la culture** : `<initiale de l'espèce>-<année de la saison>-<code de la planche>-<numéro>` (ex. `T-2027-P12-01`), attribuée à la création et recalculée si la planche, l'itinéraire ou la saison change. Elle sert de nom de lot de traçabilité (phase 4).

**Rétro-planning** (`garden.crop.template._plan_dates`) :
- depuis le semis : repiquage = semis + `days_to_transplant` (vide en semis direct), début de récolte = semis + `days_to_maturity`, fin = début + `harvest_window_days` ;
- depuis la récolte visée : semis = début de récolte − `days_to_maturity`, puis le reste comme ci-dessus.

UX : saisir ou modifier le **semis prévu** recalcule repiquage, début et fin de récolte ; saisir ou modifier le **début de récolte prévu** recalcule le semis et les autres dates (onchange). Repiquage et fin de récolte restent modifiables à la main sans cascade. Changer d'itinéraire recalcule depuis le semis s'il est saisi, sinon depuis la récolte. Les boutons « Recalculer depuis le semis / la récolte » du formulaire appliquent la même logique, et la création par code complète les dates manquantes.

**Assistant de création en série** (`garden.season.plan.wizard`, réservé au chef de culture) : saison, itinéraire, planches, date de récolte ou de semis visée, décalage en jours entre planches successives (échelonnement) et part de planche. Il crée une culture par planche et ouvre la liste des cultures créées.

**Période d'occupation** d'une planche (`occupation_start` / `occupation_end`) : repiquage prévu pour les plants (autoproduits ou achetés), sinon début réel ou semis prévu ; jusqu'à la fin réelle, à défaut la fin de récolte prévue. Elle sert aux contrôles et à `current_crop_ids` de la planche.

**Contrôles** (avertissements uniquement, calculés sur la culture, affichés en bannière dans le formulaire, en colonnes dans la liste et dans le Gantt) :
- *chevauchement* : la somme des `bed_share` des cultures simultanées sur la planche (hors annulées) dépasse 100 %. Évalué à chaque début de période, pour ne pas additionner des cultures qui ne sont jamais présentes ensemble ;
- *rotation* : une culture de la même famille botanique a quitté la planche depuis moins de `rotation_years` (de l'espèce de la culture) ; la famille « Autre » n'est pas contrôlée.

**Étapes prévues** : `garden.crop._get_planned_steps()` retourne, triées par date, les étapes de l'itinéraire (`step`, `operation_type`, `date` = semis prévu + `day_offset`, `duration` en heures = durée attendue par m² × surface). La génération des opérations planifiées correspondantes est décrite dans « Opérations et main-d'œuvre ».

**Besoins en semences** : par culture, `planned_plant_qty` (surface × densité, modifiable) puis `planned_seed_count` = plants / germination × (1 + marge) et `planned_seed_qty` (g) = graines / graines par gramme. Les plants achetés ne demandent aucune semence. La marge est le paramètre système `odoo_garden.seed_margin` (Maraîchage › Configuration › Paramètres, 20 % par défaut) ; la modifier recalcule les cultures. Le rapport (Planification › Besoins en semences) est un pivot / une liste de `garden.crop` groupés par variété et saison ; `garden.crop.get_seed_needs(domain)` retourne les mêmes totaux par variété. Aucun lien Achats (phase 7).

**Plan de culture (Gantt)** : action client OWL (`garden_bed_occupancy`), compatible Community, sans ressource externe. Filtres saison et site, planches regroupées par îlot (option « masquer les planches libres »), couleur par famille botanique, barre prévue hachurée (semis → fin de récolte) et barre réalisée pleine, icône d'avertissement, clic sur une barre pour ouvrir la culture. Les cultures simultanées d'une planche sont placées sur des lignes distinctes.

**Calendrier** : vue calendar des cultures non annulées (semis prévu → fin de récolte prévue, couleur par espèce).

## Opérations et main-d'œuvre (phase 3)

**Opération** (`garden.operation`) : un travail planifié puis réalisé, qui remplace les anciennes actions et le post-process (lavage et conditionnement sont des types de la catégorie « après récolte »). États : planifiée, en cours, faite, annulée. Le libellé est proposé d'après le type et la cible. Le **périmètre** est une ou plusieurs cultures, une ou plusieurs planches, ou un îlot ; il est proposé d'après le type d'opération (`default_scope`) et la cible correspondante est obligatoire.

**Boutons** : Démarrer (passe en cours et lance le chronomètre), Arrêter le chrono (ajoute le temps écoulé à la durée), Terminer (arrête le chrono, passe à « faite » et renseigne la date du jour), Annuler et Remettre en planifiée. Une opération de type « récolte » (`requires_quantity`) ne peut pas être terminée sans quantité récoltée.

**Temps et coût** :
- `duration` est la durée *par employé* en heures (widget `float_time`). Le temps total `total_hours` vaut la somme des lignes de détail (`garden.operation.worker`) s'il y en a, sinon `duration` × nombre d'employés ; une opération sans employé compte pour une personne.
- `labour_cost` = Σ durée × taux horaire de l'employé. Le taux vient de `hr.employee.garden_hourly_cost` ; à 0 (ou sans employé), c'est le taux par défaut `odoo_garden.default_hourly_rate` (Paramètres, 15 par heure). Le champ `hourly_cost` n'existe que dans `hr_hourly_cost` (non requis, réservé aux officiers RH) : il n'est donc pas utilisé.
- Les coûts (`labour_cost` de l'opération, des lignes, des répartitions et de la culture, `garden_hourly_cost` de l'employé) ne sont visibles que du chef de culture et du gérant (`groups=` sur les champs, vues comprises). Modifier `garden_hourly_cost` suppose en plus le droit d'écriture sur les employés (officier RH).
- Changer le taux par défaut recalcule le coût des opérations. Changer le taux d'un employé recalcule automatiquement celui de ses opérations.

**Champs par catégorie** : récolte (`harvest_product_id` proposé d'après la variété, `harvest_qty`, `harvest_uom_id`) ; irrigation (`water_volume` = durée × débit de l'îlot, modifiable) ; traitement (`target`, `weather_notes`). La récolte crée une entrée en stock et les intrants des mouvements de consommation (voir « Stock »).

**Répartition** (`garden.operation.allocation`), calculée quand l'opération passe à « faite », recalculée si l'opération est modifiée et supprimée si elle est rouverte :
- périmètre culture : les cultures choisies ;
- périmètre planche ou îlot : les cultures en place sur ces planches (ou sur les planches de l'îlot) à la date de réalisation (à défaut la date prévue), hors cultures annulées ;
- chaque culture reçoit une part (`share`, en %) proportionnelle à sa surface occupée (`area`), ou une part égale si toutes les surfaces sont nulles ; `hours` et `labour_cost` sont la part du temps total et du coût de l'opération ;
- sans culture en place, aucune ligne n'est créée : bannière d'avertissement et note dans le fil de discussion, sans blocage.

**Génération des opérations planifiées** : `garden.crop._generate_operations()` crée, d'après `_get_planned_steps()`, une opération planifiée par étape de l'itinéraire (type, date = semis prévu + décalage, durée = h/m² × surface). Elle est idempotente (clé : culture + `template_step_id` ; une étape déjà générée, même annulée ou faite, n'est pas recréée) et ignore les cultures sans semis prévu, terminées ou annulées. Elle est lancée par le bouton « Générer les opérations » de la culture et de la saison validée, et par la validation de la saison.

**Ma journée** (menu racine) : kanban mobile regroupé par îlot, avec l'icône du type, la date prévue (en retard en rouge), la durée, les employés et les boutons Démarrer / Terminer. Filtres par défaut « Du jour et en retard » (`planned_date <= context_today()`, états planifiée ou en cours) et « Mes opérations » (`employee_ids.user_id = uid`) : retirer ce dernier pour voir toute l'équipe. Le **calendrier des opérations** (date prévue, couleur par type) est dans Production.

**Étiquettes QR** : l'impression de planches (menu Imprimer de la liste ou bouton « Étiquette QR » du formulaire) produit un PDF d'une étiquette par planche (site, îlot, nom, code, surface, QR code). Le QR code est une image du contrôleur `/report/barcode/` encodant `{web.base.url}/odoo/action-odoo_garden.action_garden_bed/{id}`, qui ouvre la planche. La planche a aussi un bouton « Nouvelle opération » et un bouton intelligent « Opérations ».

## Stock : intrants, récoltes, pertes, traçabilité (phase 4)

**Emplacements** (par société, champs de `res.company`, réglables dans Paramètres › Stock) : « Production maraîchage » et « Consommation maraîchage » (usage `production`, créés à l'installation : données XML pour la société principale, `create_missing_garden_locations` pour les autres sociétés, `res.company.create` pour les nouvelles) et l'emplacement de stockage (entrée des récoltes, sortie des intrants ; vide = stock principal du premier entrepôt de la société). Les mouvements sont créés en `sudo()` ciblé, avec la société de l'opération : l'ouvrier n'a aucun droit sur les mouvements, quants, rebuts ou lots en écriture.

**Intrants** (`garden.operation.input`, onglet « Intrants » de l'opération) : seuls les produits dont le type d'intrant maraîcher (`garden_input_type`) est renseigné sont proposés ; le lot est obligatoire pour un produit suivi par lots. À la validation « faite », chaque ligne génère un mouvement stock > « Consommation maraîchage » daté de l'opération, et son coût unitaire (coût standard du produit converti dans l'unité de la ligne) est figé. `input_cost` est cumulé sur l'opération, réparti dans `garden.operation.allocation.input_cost` au prorata de la part (comme `labour_cost`) et sommé sur la culture ; ces coûts ne sont visibles que du chef de culture et du gérant. Il n'y a pas de contrôle de stock disponible (le stock peut devenir négatif, comme dans Inventaire).

**Récoltes** : à la validation d'une opération de récolte, `harvest_qty` (en `harvest_uom_id`) entre en stock depuis « Production maraîchage ». La quantité est répartie entre les cultures au prorata de la répartition de l'opération (reste d'arrondi sur la dernière culture) : un mouvement par culture et, si le produit est suivi par lots (suivi par numéro de série non géré), un lot nommé d'après la référence de la culture (`stock.lot.garden_crop_id`), réutilisé aux récoltes suivantes. Un produit sans suivi par lots entre sans lot. Sans culture en place à la date (récolte de planche ou d'îlot), un produit non suivi entre en stock sans culture (note dans le fil de discussion) ; un produit suivi par lots bloque la validation. Le produit récolté est obligatoire. `garden.crop.harvested_qty` (stocké) est la somme des mouvements de récolte terminés moins leurs annulations, en unité du produit (supposée être le kg) : c'est la source de vérité des statistiques.

**Annulation** : réouvrir une opération faite (« Remettre en planifiée ») ou la supprimer ne supprime aucun mouvement : un **mouvement inverse** (même lot, même quantité, `garden_kind` = annulation, `garden_reverse_of_id`) est créé, ce qui conserve l'historique de stock ; une nouvelle validation crée de nouveaux mouvements. Tant qu'une opération est faite, ses intrants et, pour une récolte déjà en stock, sa quantité, son produit, son unité, son périmètre et sa date sont verrouillés (message d'erreur : rouvrez-la d'abord). Annuler une opération non faite ne touche pas au stock.

**Pertes** (`garden.loss`) : une perte *avant récolte* n'a aucun effet sur le stock ; une perte *après récolte* crée et valide un `stock.scrap` sur le lot de la culture (emplacement où le lot est en stock, à défaut l'emplacement de stockage), après contrôle du stock disponible, daté du jour de la perte. Elle est ensuite verrouillée (seules la cause et les notes se modifient) et ne peut pas être supprimée : corriger par un ajustement d'inventaire. Taux de perte de la culture (`loss_rate`, widget pourcentage) = pertes / (récolte + pertes), avec les quantités converties dans l'unité du produit récolté : les pertes avant récolte sont donc supposées saisies en kg (ou une unité convertible).

**Traçabilité** : `garden.traceability` (modèle transitoire, ORM uniquement, sans vue SQL) s'ouvre par le bouton « Traçabilité maraîchage » du lot (formulaire `stock.lot`, qui affiche aussi la culture) ou « Traçabilité » de la culture. *Amont* : culture, opérations faites (directes ou réparties), intrants consommés, lots de semence ou de plant (intrants de type semence/plant des opérations de semis, repiquage ou plantation) et leur réception fournisseur, entrées de récolte. *Aval* : sorties du lot lues dans `stock.move.line` (lignes terminées qui quittent un emplacement interne vers un emplacement non interne : livraisons, ventes, point de vente, rebuts, consommation), sans dépendre du module Ventes, et opérations qui ont consommé le lot comme intrant (utile depuis un lot de semence). Aucun coût n'y figure.

**Données de démonstration** (`demo/garden_stock_demo.xml`) : produits d'intrants (semence de tomate en grammes avec lot, terreau, engrais, bouillie bordelaise) avec stock initial, semis / fertilisation / traitement avec intrants, récolte de 45 kg de tomates sur le lot de la culture, une perte avant récolte et une après récolte (rebut) ; la récolte de laitue de la phase 3 reste un exemple de produit non stockable.

## Contrôleur

`GET /odoo/garden` redirige un utilisateur connecté vers l'action des fermes, et un visiteur anonyme vers la page de connexion.

## Sécurité

Trois groupes sous le privilège **Maraîchage** (`security/garden_security.xml`), chacun impliquant le précédent ; l'ouvrier implique `base.group_user`. `admin` et `OdooBot` sont dans le groupe Gérant.

| Groupe | Structure (ferme, site, îlot, planche) | Catalogue (espèce, variété, itinéraire, type d'opération) | Cultures, pertes | Opérations et intrants |
|---|---|---|---|
| Ouvrier | lecture | lecture | lecture, écriture, création (pas de suppression) ; saisons : lecture seule | lecture, écriture, création, sans suppression ; ses opérations seulement (voir ci-dessous) ; aucun coût |
| Chef de culture | lecture, écriture, création | tous droits | tous droits | tout sauf suppression ; voit tous les coûts, le CA et les marges |
| Gérant | tous droits | tous droits | tous droits | tous droits |

Le menu racine est réservé au groupe Ouvrier (donc à tous ses groupes impliquants) et le menu Configuration au chef de culture. Un utilisateur interne sans groupe Maraîchage n'a aucun accès aux modèles.

**Rentabilité** : `garden.crop.profitability` est en lecture seule et réservé au gérant (règle multi-société) ; le tableau de bord aussi. Le chef de culture lit le CA et la marge de ses cultures (fiche culture, bouton Ventes) sans accès aux factures (`account.move` / `account.move.line` refusés, vérifié par test) ; l'ouvrier ne lit ni coûts, ni CA, ni marge.

**Conformité** : les registres (`garden.compliance.wizard` et `garden.compliance.line`) et leurs menus sont réservés au chef de culture et au gérant (droits d'accès et groupe technique `group_garden_compliance`) ; l'ouvrier n'y accède pas (ni par l'interface ni par l'API). La dérogation au DAR est réservée au gérant. L'ouvrier ne voit ni les champs réglementaires des produits ni les coûts. Les registres ne contiennent aucun coût.

Les saisons et l'assistant de planification en série sont réservés au chef de culture (et au gérant) en écriture ; l'ouvrier lit les saisons.

Règles multi-société (`ir.rule`, `company_id in company_ids`) sur `garden.farm`, `garden.site`, `garden.garden`, `garden.bed`, `garden.season` et `garden.crop`. Les opérations, leurs lignes de temps (`garden.operation.worker`), leurs intrants (`garden.operation.input`), leurs répartitions et les pertes (`garden.loss`) portent `company_id` et ont leur règle multi-société.

**Stock** : les groupes maraîchage n'impliquent aucun groupe Inventaire. L'ouvrier peut lire les lots (`stock.lot`, pour choisir le lot d'un intrant), saisir des intrants, des récoltes et des pertes dans ses opérations, mais n'écrit pas dans le stock directement (aucun droit sur `stock.move`, `stock.scrap`, création de lot ou de quant ; les mouvements sont créés par le serveur). Le chef de culture lit en plus les mouvements de stock (`stock.move`). Comme tout utilisateur interne, l'ouvrier garde les droits de lecture standard d'Inventaire (emplacements, quants) et de lecture/écriture des lignes de mouvement (`stock.move.line`) accordés à `base.group_user`. Les coûts d'intrants (`unit_cost`, `cost`, `input_cost`) sont masqués à l'ouvrier (champs et vues).

**Règle ouvrier** (`ir.rule`) : un ouvrier ne voit et ne modifie que les opérations où il est employé (`employee_ids.user_id`) ou qui n'ont aucun employé ; une règle du groupe chef de culture lève cette restriction. Démarrer une opération sans employé y affecte l'employé de l'utilisateur. Les répartitions sont créées par le serveur (droits élevés) : l'ouvrier et le chef de culture ne peuvent que les lire, seul le gérant peut les modifier. Les lignes de temps par employé et les lignes d'intrants suivent les droits de l'opération (l'ouvrier peut les créer et les supprimer, tant que l'opération n'est pas faite pour les intrants).

## Tests

Le dossier `tests/` contient (tests `post_install`, `-at_install`) :
- `test_install.py` : chaîne ferme > site > îlot > planche > espèce > variété > itinéraire > culture > opération, données d'occupation, absence des anciens écrans de statistiques, action `odoo_garden.action_garden_farm`, absence des modèles supprimés ;
- `test_structure.py` : société héritée, surfaces, unicité du code par site, archivage, cultures en place, règle multi-société ;
- `test_catalog.py` : espèces, variétés, densité et prix d'un itinéraire, étapes, types d'opération par défaut, lien produit / variété ;
- `test_security.py` : hiérarchie des groupes, droits de l'ouvrier, du chef de culture et du gérant ;
- `test_planning.py` : saisons (états, contraintes, droits, multi-société), référence et surface de la culture, prévisionnel, rétro-planning, étapes prévues, assistant de création en série (échelonnement, droits), chevauchement et rotation, besoins en semences et marge ;
- `test_gantt.py` : données du Gantt (groupes, lignes, filtres), vue calendrier, tours navigateur `garden_gantt_tour` et `garden_my_day_tour` (« Ma journée » : démarrer puis terminer une opération) ;
- `test_operations.py` : opérations (valeurs par défaut, périmètre, états, irrigation, récolte), main-d'œuvre (coût durée × employés, détail par employé, taux par défaut, chronomètre, coûts masqués à l'ouvrier), répartition (culture, planche, îlot, prorata de surface, aucune culture, recalcul), génération idempotente des opérations planifiées, statistiques de temps (répartitions), « Ma journée » (domaine du jour, vues) et règle ouvrier ;
- `test_labels.py` : URL du QR code, résolution de la route `/odoo/action-...`, rendu HTML du rapport d'étiquettes, route `/report/barcode` (ignorée si reportlab n'a pas de moteur PNG), boutons de la planche ;
- `test_stock_setup.py` : emplacements virtuels par société, emplacement de stockage par défaut, paramètres ;
- `test_stock_inputs.py` : type d'intrant, consommation (mouvement, valeur figée, conversion d'unité, lot obligatoire), annulation et nouvelle validation, verrou, suppression, répartition du coût d'intrants, emplacement de stockage personnalisé, droits de l'ouvrier (aucun accès au stock global ni aux coûts) ;
- `test_stock_harvest.py` : entrée en stock, lot de culture, produit sans lot, répartition entre cultures (et reste d'arrondi), récolte de planche, réutilisation du lot, annulation, verrou, unités, `harvested_qty`, droits de l'ouvrier ;
- `test_stock_losses.py` : perte avant / après récolte (rebut sur le lot), stock insuffisant, verrou, taux de perte, unités, droits, règle multi-société ;
- `test_stock_traceability.py` : traçabilité amont (opérations, intrants, lots de semence et leur réception) et aval (livraison, rebut), lot de semence, culture à plusieurs lots, lecture de l'écran par l'ouvrier et le chef, boutons et menu ;
- `test_progress.py` : états et dates réelles des cultures pilotés par les opérations (jamais en arrière, saisies manuelles respectées, fin à la clôture, cohérence de l'occupation) ;
- `test_revenue.py` : attribution du CA au prorata (mois sans récolte, avoir, devise étrangère, annulation de récolte) et par lot (plusieurs lots, lot hors culture, avoir, retour client), marge, marge/h, marge/m², charges fixes, écart prévu / réalisé, droits (ouvrier, chef sans accès aux factures), bouton Ventes ;
- `test_profitability.py` : contenu du rapport, idempotence, ratios pondérés, droits, règle multi-société, ouverture et cron, données du tableau de bord ;
- `test_compliance_fields.py` : champs réglementaires des produits (contraintes, écriture limitée par le chef de culture, vue), surface traitée et dose ;
- `test_compliance_dar.py` : blocage dans le délai (limites incluses), création directe à « faite », dérogation du gérant et traçabilité, chef de culture et ouvrier sans dérogation, absence de blocage (produit sans DAR, traitement annulé, planifié, postérieur ou d'une autre culture), récolte sur plusieurs cultures et de planche, avertissement et date « récolte possible à partir du » ;
- `test_compliance_registers.py` : registre phytosanitaire (contenu, répartition entre cultures, filtres période / saison / cultures, droits, multi-société, XLSX lu avec `openpyxl`, PDF au niveau HTML QWeb, téléchargement HTTP), registre de fertilisation (azote, conversion d'unités, synthèse, XLSX, PDF, pivot), export bio (alertes, onglets), paramètre `compliance_enabled` (menus, groupe, blocage, mise à jour), tour navigateur `garden_compliance_tour` ;
- `test_demo.py` : plan de culture, opérations, intrants, récolte, pertes et traçabilité de démonstration (ignoré sans données de démo).

Le tour navigateur nécessite Chrome et le paquet Python `websocket-client` ; sans lui Odoo l'ignore (« skipped »). Pour l'exécuter sans modifier l'environnement : `pip install --target /tmp/pylibs websocket-client` puis `PYTHONPATH=/tmp/pylibs ./run.sh ...`.

```
cd <racine du projet> && ./run.sh -d garden_test -i odoo_garden --test-enable --test-tags /odoo_garden --stop-after-init
```

Les tests sont lancés sans `--with-demo` par défaut ; avec elle, `test_demo.py` s'exécute aussi (un échec du chargement des données de démo n'est qu'un avertissement dans le journal : le vérifier). La démo contient la saison 2027 (12 cultures dont un chevauchement sur N1-01 et une rotation sur S1-03 grâce à la tomate 2026), une saison 2026 close, trois employés (plus l'employé administrateur de `hr`, avec un coût horaire), des opérations faites (dont un arrosage d'îlot réparti 40 / 40 / 20 % entre trois cultures le 10 juin 2027, un désherbage de deux planches, une récolte et un détail par employé), des récoltes (tomate, carotte, courgette, laitue) et des factures clients comptabilisées (dont un avoir et une vente livrée sur le lot de la tomate) pour la rentabilité, des opérations planifiées autour de la date du jour pour « Ma journée » et les opérations prévues par les itinéraires de la saison 2027. Les données de démonstration ne sont chargées qu'avec `--with-demo` (désactivées par défaut en Odoo 19). Ajouter `--http-port=<port>` si le serveur de développement tourne déjà.

## Points connus / à corriger

- **Opérations générées** : changer le semis prévu d'une culture après génération ne décale pas les opérations déjà créées (relancer la génération ne les met pas à jour) ; une opération supprimée est recréée à la relance, une opération annulée ne l'est pas.
- **Répartition figée** : la répartition d'une opération faite n'est recalculée que si l'opération est modifiée ; un changement ultérieur de période d'occupation d'une culture ne la met pas à jour.
- **Coût horaire** : `garden_hourly_cost` s'édite dans l'onglet Paramètres de l'employé, réservé aux officiers RH ; le chef de culture le voit mais ne peut pas l'écrire sans droit RH. `hr_hourly_cost` n'est pas pris en charge.
- **Étiquettes QR** : l'image PNG du QR code est produite par reportlab (`renderPM`), qui nécessite `rlPyCairo` ou `_rl_renderPM` ; absent de l'environnement de développement local (le rendu PDF n'y a pas été vérifié, ni wkhtmltopdf). Le QR code dépend de `web.base.url`.
- **Chronomètre** : la durée est ajoutée par employé ; démarrer le chronomètre d'une opération déjà en cours ne fait rien tant qu'il tourne.
- **Référence des cultures existantes** : les cultures créées avant la phase 2 gardent la référence `/` après mise à jour.
- **Avertissements non stockés** : `has_overlap` et `has_rotation_conflict` ne sont pas filtrables dans la recherche.
- **Anciennes cultures** : `date_start` / `date_end` sont désormais les dates *réelles* ; les cultures sans dates prévues n'apparaissent pas dans le calendrier.
- **Paramètres** : l'écran de configuration est réservé à l'administrateur système (groupe `base.group_system`).
- **Rétrogradation** : rouvrir une opération faite ne ramène pas l'état ni `date_start` de la culture en arrière ; `date_end` n'est renseignée qu'à la clôture manuelle de la culture.
- **Unités de la récolte et des pertes** : `harvested_qty` et `loss_rate` additionnent les quantités dans l'unité du produit récolté, sans contrôle qu'il s'agit de kg ; les pertes avant récolte exprimées en plants fausseraient le taux.
- **Stock des intrants** : la consommation n'est pas bloquée si le stock est insuffisant (quant négatif) ; le coût vient du coût standard du produit (pas de valorisation FIFO / AVCO ni de comptabilité de stock).
- **Rebut** : une perte après récolte est irréversible depuis le module (ajustement d'inventaire).
- **Lot de récolte** : nommé d'après la référence de la culture au moment de la première récolte ; renommer ensuite la culture ne renomme pas le lot (le lien reste `garden_crop_id`).
- **Tests de mise à jour** : pour tester `-u` sur une copie de base (`pg_dump`), copier aussi le filestore (`odoo-data/filestore/<base>`), sinon les bundles d'assets référencés par la copie sont introuvables et le tour du Gantt échoue (page sans CSS).
- **Accès aux lots** : l'ouvrier lit tous les lots de sa société (nécessaire au choix du lot d'un intrant).
- **Rentabilité** : le rapport est une copie stockée actualisée à l'ouverture, au bouton et chaque nuit ; le CA par lot exige des produits suivis par lots et des factures issues de commandes de vente (sinon utiliser le prorata) ; le CA du Point de Vente n'est pas compté (phase 7) ; les paramètres de rentabilité s'enregistrent dans l'écran de configuration, réservé à l'administrateur système.
- **Attribution au prorata** : suppose que le produit facturé est le produit récolté (`harvest_product_id`) et la même unité ; le mois est celui de la date comptable de la facture.
- **Conformité** : le rendu PDF des registres n'a été vérifié qu'au niveau HTML QWeb (pas de moteur wkhtmltopdf dans l'environnement de développement) ; les registres sont des lignes transitoires recalculées à chaque ouverture (jamais archivées : exporter le fichier pour le conserver) ; les produits non renseignés (`is_organic_allowed` décoché par défaut) sont signalés en bio ; le DAR suppose un `date` de réalisation (une récolte faite sans date est contrôlée à la date prévue) ; l'azote n'est calculé que pour des engrais exprimés dans une unité de masse (pas de conversion de densité des engrais liquides) ; le groupe `group_garden_compliance` est ajouté au chef de culture à l'activation du paramètre et, dans une base ayant reçu un état intermédiaire de la phase 6, le menu peut garder aussi le groupe chef de culture (lien additif de la mise à jour).
- **Manifeste** : `author` et `website` contiennent encore des valeurs par défaut.
- **Mise à jour depuis la phase 0** : les cultures existantes perdent leur lien vers l'ancien catalogue (`template_id` vide, contrainte NOT NULL non posée) ; aucune migration de données n'est fournie (aucune donnée de production, hypothèse 1).
- **Description du module** : Odoo interprète `README.md` en reStructuredText lors de l'installation et journalise des avertissements de syntaxe sans conséquence.

## À venir

La feuille de route complète (version payante intégrée aux applications Odoo) est décrite dans [`docs/SPECIFICATIONS.md`](docs/SPECIFICATIONS.md).

- Schéma visuel des sites et planches
