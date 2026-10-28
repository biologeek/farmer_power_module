# Odoo Garden — Spécifications fonctionnelles et techniques (v2)

Document de cadrage pour transformer le module actuel en application payante de gestion maraîchère, intégrée aux applications standard d'Odoo (Inventaire, Ventes, Employés, Achats, Point de vente).

Il est destiné à l'agent de développement : chaque phase (§ 7) est autonome, testable et livrable séparément.

---

## 1. Le besoin, vu du maraîcher

> « J'ai une ferme répartie sur deux sites. Sur chaque site, j'ai des îlots : des groupes de planches arrosées ensemble par le même secteur d'irrigation. Une planche porte trois ou quatre cultures dans l'année. Pour chacune je sème, je repique, je plante, j'arrose, je désherbe, je traite, je récolte, je lave, je conditionne. Je vends au marché, en AMAP, à deux restaurants et à une épicerie.
>
> Ce que je veux savoir : **combien me rapporte chaque culture, par heure de travail et par m²**. Pour ça il faut que le temps passé, les semences, le terreau, les traitements et les ventes soient au même endroit. Je veux aussi préparer mon plan de culture l'hiver, savoir quoi semer cette semaine, commander mes graines, tenir mon registre phyto sans y passer mes soirées, et retrouver d'où vient une salade si un client se plaint. »

Ce qu'il en découle :

| Besoin | Fonctionnalité |
|---|---|
| Décrire l'exploitation | Ferme › Site › Îlot (secteur d'irrigation) › Planche, avec surfaces |
| Savoir quoi cultiver et comment | Espèces (familles pour la rotation), variétés liées aux produits, itinéraires techniques |
| Préparer la saison | Plan de culture annuel, rétro-planning depuis la date de récolte visée, besoins en semences, contrôle de la rotation et des chevauchements |
| Savoir quoi faire aujourd'hui | Opérations planifiées générées automatiquement, vue « Ma journée » sur téléphone |
| Mesurer le travail | Opérations chronométrées, par employé, réparties automatiquement sur les cultures concernées |
| Suivre les intrants | Consommation de semences, plants, engrais et traitements depuis l'inventaire |
| Récolter et stocker | La récolte crée une entrée en stock du produit vendu, avec lot de traçabilité |
| Vendre | Ventes, factures et caisse (marchés) remontées sur la culture d'origine |
| Mesurer la rentabilité | Marge par culture, par planche, par espèce, par heure et par m², prévu / réalisé |
| Être en règle | Registre phytosanitaire, délai avant récolte, registre de fertilisation, export pour la certification bio |
| Tracer | De la graine (lot fournisseur) au client (lot vendu) |

---

## 2. État actuel et écarts

Le module actuel (voir `README.md`) pose la hiérarchie et quelques écrans, mais ne dépend que de `base` : aucune intégration, aucun coût, aucune planification.

| Domaine | Existant | Statut | Écart à combler |
|---|---|---|---|
| Structure | `garden.farm`, `garden.site`, `garden.garden`, `garden.bed`, `garden.plot` | Partiel | Pas de surface ni de dimensions, pas de notion d'irrigation sur l'îlot, pas de société, `garden.plot` inutile |
| Catalogue | `garden.crop.catalog`, `garden.culture.mode` | Partiel | Pas d'espèce ni de famille botanique, aucun lien avec `product.product`, pas d'étapes d'itinéraire, pas de rendement attendu |
| Cultures | `garden.crop` (dates, quantités semées/plantées, récolte et valeur saisies à la main) | Partiel | Pas d'état (planifiée / en cours / terminée), pas de surface occupée, récolte et chiffre d'affaires saisis au lieu d'être calculés |
| Opérations | `garden.action` + `garden.action.type` (durée en minutes, une seule culture) | Partiel | Pas d'employé, de coût, d'état planifié/réalisé, d'intrants ni d'opération sur plusieurs planches ou un îlot entier |
| Post-process | `garden.postprocess` (nom, date, action) | Minimal | À fusionner dans les opérations (catégorie « après récolte ») |
| Pertes | `garden.loss` (planche, quantité, raison) | Minimal | Pas de lien à la culture, à l'unité ou au stock (rebut) |
| Traçabilité | Vue orpheline vers un modèle inexistant | Absent | Lots de stock de la semence à la vente |
| Rétro-planning | — | Absent | Calcul des dates depuis la récolte visée |
| Statistiques | 3 actions client OWL, SQL brut, Chart.js via CDN, méthode dupliquée | Fragile | Remplacer par un modèle de reporting et les vues natives pivot/graphique ; garder le Gantt d'occupation |
| Intégrations | Aucune | Absent | Stock, Ventes, Employés, Achats, PdV |
| Sécurité | Tous droits à tous, 2 modèles sans accès | Insuffisant | Groupes, règles multi-société |
| Qualité | Pas de tests, de données de démo, de traductions ni de `.gitignore` | Absent | Requis pour la publication sur l'Odoo Apps Store |
| Bugs connus | Route `/odoo/garden` en 404, domaine/contexte du Gantt, `view_mode="tree"` | — | Phase 0 |

**Ce qui est conservé** : la hiérarchie, les noms techniques `garden.*`, le Gantt d'occupation des planches (OWL), l'organisation des menus.

**Ce qui est remplacé** : `garden.plot` (supprimé), `garden.postprocess` (fusionné dans les opérations), `garden.action` (renommé `garden.operation`, voir § 8), l'écran Chart.js (remplacé par les vues pivot et graphique), les champs `quantity_harvested` et `value_harvested` saisis (deviennent calculés).

### Positionnement

Les outils dédiés au maraîchage (Elzeard, Qrop, farmOS, LiteFarm…) couvrent bien la planification et le suivi au champ. Ils restent cependant séparés de la gestion commerciale et comptable. L'argument du module : **la planification maraîchère branchée nativement sur le stock, les ventes et la paie d'Odoo**, donc une rentabilité calculée sur les vraies ventes et les vrais coûts, sans double saisie.

---

## 3. Modèle de données cible

```
res.company
└── garden.farm (Ferme)
    └── garden.site (Site)
        └── garden.garden (Îlot — secteur d'irrigation)
            └── garden.bed (Planche)
                └── garden.crop (Culture) ── garden.crop.template (Itinéraire) ── garden.variety ── garden.species
                    ├── garden.operation.allocation ── garden.operation ── garden.operation.type
                    │                                       └── garden.operation.input (intrants → stock.move)
                    ├── stock.lot / stock.move (récoltes)
                    └── garden.loss
garden.season (Plan de culture annuel) ── garden.crop
garden.crop.profitability (rapport SQL, _auto = False)
```

### 3.1 Structure

**`garden.farm`** : `name`, `company_id`, `site_ids`, `active`.

**`garden.site`** : `name`, `farm_id`, `company_id` (lié), `partner_id` (adresse), `latitude`, `longitude`, `garden_ids`, `active`.

**`garden.garden`** (libellé « Îlot ») :
- `name`, `code`, `site_id`, `bed_ids`, `active`
- `culture_type` : plein air / sous abri (serre, tunnel)
- `irrigation_type` : goutte-à-goutte / aspersion / manuel / aucun
- `irrigation_flow` (L/h), pour calculer le volume d'eau d'un arrosage
- `area` : calculée, somme des surfaces des planches

**`garden.bed`** :
- `name`, `code` (unique par site, imprimé en QR code), `garden_id`
- `length` (m), `width` (m), `area` (m², calculée et stockée)
- `soil_type`, `notes`, `active`
- `crop_ids`, `current_crop_ids` (calculé : cultures en place à la date du jour)

### 3.2 Catalogue

**`garden.species`** (espèce) :
- `name` (Tomate), `family` (sélection : solanacées, brassicacées, cucurbitacées, apiacées, astéracées, fabacées, amaryllidacées, chénopodiacées, poacées, autre)
- `rotation_years` : délai minimal de retour de la famille sur une même planche (défaut 3)

**`garden.variety`** (variété) :
- `name`, `species_id`, `supplier_id` (`res.partner`)
- `seed_product_id` (semence achetée, `product.product`)
- `harvest_product_id` (produit vendu : « Tomate cœur de bœuf (kg) »)
- `seeds_per_gram`, `germination_rate` (%)
- `organic_status` : bio / non traitée / conventionnelle avec dérogation

Sur `product.template`, ajouter `garden_variety_ids` et un filtre « Produits maraîchers ».

**`garden.crop.template`** (itinéraire technique, remplace `garden.crop.catalog`) :
- `name`, `variety_id`, `culture_type` (plein air / sous abri)
- `propagation` : semis direct / plants autoproduits / plants achetés (+ `plant_product_id`)
- `row_count`, `row_spacing` (cm), `plant_spacing` (cm) → `density` (plants/m², calculée)
- `days_to_transplant`, `days_to_maturity`, `harvest_window_days`
- `expected_yield` (kg/m²), `expected_price` (€/kg, défaut = prix de vente du produit)
- `step_ids` : `garden.crop.template.step` (`operation_type_id`, `day_offset` depuis le semis, `expected_duration` en h/m², `sequence`)

**`garden.culture.mode`** : supprimé, ses champs passent sur l'itinéraire.

### 3.3 Plan de culture et cultures

**`garden.season`** : `name` (Saison 2027), `date_start`, `date_end`, `company_id`, `crop_ids`, `state` (brouillon / validé / clôturé).

**`garden.crop`** (culture sur planche) :
- `name` (calculé : `T-2027-P12-01`, aussi utilisé comme nom de lot), `season_id`, `template_id`, `variety_id`, `species_id` (liés)
- `bed_id`, `bed_share` (% de la planche occupée, défaut 100), `area` (calculée)
- Dates prévues : `planned_sowing_date`, `planned_transplant_date`, `planned_harvest_start`, `planned_harvest_end`
- Dates réelles : `date_start`, `date_end` (alimentées par les opérations réalisées)
- `state` : planifiée / semée / en place / en récolte / terminée / annulée
- Prévisionnel : `planned_plant_qty`, `planned_seed_qty` (g), `expected_yield_qty` (kg), `expected_revenue`
- Réalisé, calculé :
  - `harvested_qty` (somme des mouvements de stock de récolte)
  - `revenue` (§ 5.3)
  - `labour_hours`, `labour_cost`, `input_cost`, `margin`, `margin_per_hour`, `margin_per_m2`
- `lot_ids`, `operation_allocation_ids`, `loss_ids`, `notes`, `mail.thread` (photos, historique)

**Rétro-planning** : la date de récolte visée et l'itinéraire donnent les autres dates (`semis = récolte − days_to_maturity`, `repiquage = semis + days_to_transplant`). Un assistant (`garden.season.plan.wizard`) crée en série des cultures sur une liste de planches.

**Contrôles** (avertissements, pas des blocages) :
- **Chevauchement** : la somme des `bed_share` des cultures dont les périodes se recoupent dépasse 100 % de la planche.
- **Rotation** : la même famille a été cultivée sur la planche depuis moins de `rotation_years` ans.

**Génération des opérations** : à la validation de la saison, ou par un bouton sur la culture, une `garden.operation` planifiée est créée pour chaque étape de l'itinéraire, à la date `planned_sowing_date + day_offset`.

**Besoins en semences** : un rapport par variété calcule `plants = area × density`, puis `graines = plants / germination_rate × (1 + marge)` et `grammes = graines / seeds_per_gram`. Un bouton crée une demande de prix (module `purchase`, pont optionnel).

### 3.4 Opérations (travail)

**`garden.operation.type`** :
- `name`, `category` : préparation du sol / semis / repiquage / plantation / irrigation / désherbage / fertilisation / traitement / paillage / récolte / après récolte (lavage, conditionnement) / autre
- `default_scope` (culture / planche / îlot), `requires_quantity` (récolte), `icon`

**`garden.operation`** (remplace `garden.action`) :
- `name`, `type_id`, `category` (liée), `state` (planifiée / en cours / faite / annulée)
- `planned_date`, `date`, `company_id`
- Périmètre :
  - `scope` (culture / planche / îlot)
  - selon le périmètre, `crop_ids` (m2m), `bed_ids` (m2m) ou `garden_id`
- `employee_ids` (`hr.employee`), `duration` (heures, widget `float_time`)
  - Le temps total vaut durée × nombre d'employés, sauf saisie détaillée en lignes par employé (`garden.operation.worker` : `employee_id`, `duration`).
- Chronomètre : `timer_start`, boutons Démarrer / Arrêter
- `labour_cost` (calculé) : somme de durée × taux horaire de l'employé (`hourly_cost`, sinon taux par défaut de la configuration)
- `input_ids` : `garden.operation.input` (`product_id`, `quantity`, `uom_id`, `lot_id`, `move_id`)
- Récolte : `harvest_product_id`, `harvest_qty`, `harvest_uom_id`
- Irrigation : `water_volume` (= durée × débit de l'îlot)
- Traitement : `weather_notes`, `target` (ravageur, maladie)
- `allocation_ids`, `description`, `mail.thread`

**Répartition** (`garden.operation.allocation` : `operation_id`, `crop_id`, `share`, `hours`, `labour_cost`, `input_cost`) :
- Calculée quand l'opération passe à « faite ».
- Une opération sur un îlot ou sur plusieurs planches est répartie entre les cultures en place à cette date, **au prorata de leur surface occupée**.
- Le rapport de rentabilité lit uniquement les allocations.

**Validation d'une opération « faite »** :
1. Crée les mouvements de consommation des intrants : stock → emplacement virtuel « Consommation maraîchage » (usage `production`), valorisés au coût du produit.
2. Pour une récolte, crée un mouvement de l'emplacement virtuel « Production maraîchage » vers le stock pour `harvest_product_id`, avec le lot nommé d'après la culture (si le produit est suivi par lots).
3. Met à jour les dates réelles et l'état de la culture : le premier semis la passe en « semée », la première récolte en « en récolte ».

### 3.5 Pertes

**`garden.loss`** :
- `crop_id`, `date`, `stage` (avant récolte / après récolte), `quantity`, `uom_id`
- `cause` (maladie, ravageur, météo, invendu, autre), `notes`
- Après récolte, crée un `stock.scrap` sur le lot de la culture.

Indicateur associé : taux de perte = pertes / (récolte + pertes).

### 3.6 Conformité (France)

Sur `product.template` :
- `garden_input_type` : semence / plant / engrais / amendement / phytosanitaire / substrat / autre
- Pour les produits phytosanitaires : `amm_number`, `pre_harvest_interval_days` (DAR), `is_organic_allowed`
- Pour les engrais : `nitrogen_content` (%)

Fonctionnalités :
- **Registre phytosanitaire** (rapport PDF + export XLSX) : date, culture, surface traitée, produit, n° AMM, dose, quantité, opérateur, conditions.
- **DAR** : une récolte enregistrée avant la fin du délai avant récolte du dernier traitement affiche un avertissement bloquant, que le gérant peut lever.
- **Registre de fertilisation** : unités d'azote par planche et par saison.
- **Export certification bio** : origine et statut des semences, intrants utilisés.

---

## 4. Intégrations Odoo

| Application | Usage |
|---|---|
| `product`, `uom` | Variétés liées aux produits ; unités kg / botte / pièce / plant |
| `stock` | Récoltes (entrées), consommations d'intrants, rebuts, lots de traçabilité, emplacements virtuels créés à l'installation |
| `sale_management`, `account` | Chiffre d'affaires par culture (via lots ou au prorata, § 5.3) |
| `hr` | Employés, coût horaire |
| `mail` | Fil de discussion et pièces jointes (photos) sur cultures, planches et opérations |
| `purchase` (pont optionnel `odoo_garden_purchase`) | Demandes de prix de semences depuis les besoins du plan |
| `point_of_sale` (pont optionnel `odoo_garden_pos`) | Ventes des marchés intégrées au chiffre d'affaires |

Le module doit rester **compatible Community** : aucune dépendance à `web_gantt`, `sale_subscription` ou à un autre module Enterprise.

---

## 5. Rentabilité

### 5.1 Modèle de reporting

`garden.crop.profitability` est un modèle SQL (`_auto = False`, `init()` crée la vue). Il a une ligne par culture avec : saison, site, îlot, planche, espèce, famille, variété, surface, durée d'occupation, heures, coût main-d'œuvre, coût intrants, quantité récoltée, chiffre d'affaires, marge, et le prévu correspondant.

Vues : pivot, graphique, liste. Les indicateurs par heure et par m² sont calculés dans la vue SQL ou affichés comme mesures de ratio.

### 5.2 Indicateurs

- **Chiffre d'affaires** (§ 5.3)
- **Coût main-d'œuvre** = Σ heures allouées × taux horaire
- **Coût intrants** = Σ valeur des mouvements de consommation alloués
- **Charges fixes** (option) = coût annuel par m² (configuration) × surface × jours d'occupation / 365
- **Marge brute** = CA − main-d'œuvre − intrants − charges fixes
- **Marge par heure de travail**, **marge par m²**, **rendement** (kg/m²), **taux de perte**
- **Écart prévu / réalisé** sur le rendement, le chiffre d'affaires et les heures

Un tableau de bord (action client OWL ou `board`) affiche : marge par espèce, heures par catégorie d'opération, chiffre d'affaires mensuel, les 10 cultures les plus et les moins rentables à l'heure.

### 5.3 Attribution du chiffre d'affaires

Méthode choisie dans la configuration :
1. **Par lot** (exacte) : somme du montant HT des lignes de factures clients (et commandes PdV) dont les mouvements de livraison portent un lot de la culture. Nécessite des produits suivis par lots.
2. **Au prorata** (par défaut, adaptée aux marchés sans lots) : pour chaque produit et chaque mois, le CA facturé est réparti entre les cultures au prorata des quantités récoltées ce mois-là.

---

## 6. Ergonomie et rôles

### Groupes

| Groupe | Droits |
|---|---|
| Maraîchage / Ouvrier | Voir le plan, saisir et chronométrer ses opérations, enregistrer récoltes et pertes. Pas d'accès aux coûts. |
| Maraîchage / Chef de culture | Gérer catalogue, itinéraires, saisons, cultures et toutes les opérations |
| Maraîchage / Gérant | Rentabilité, configuration, levée des blocages DAR |

S'ajoutent des règles multi-société sur tous les modèles qui portent `company_id`.

### Écrans

- **Ma journée** (kanban mobile) : opérations planifiées du jour et en retard, regroupées par îlot, avec boutons Démarrer / Terminer.
- **QR code par planche** (étiquette PDF imprimable) : ouvre la planche, avec un raccourci « Nouvelle opération » et les cultures en place.
- **Plan de culture** : le Gantt OWL actuel, amélioré avec filtre par saison et site, regroupement par îlot, couleur par famille, barres prévues (hachurées) et réalisées, clic vers la culture.
- **Calendrier** des opérations planifiées.
- **Fiche culture** : boutons intelligents (opérations, récoltes, ventes, pertes, marge) et onglets Planification / Travail / Récoltes / Rentabilité.

### Configuration (`res.config.settings`)

- Taux horaire par défaut
- Charges fixes annuelles par m²
- Méthode d'attribution du CA
- Délai de rotation par défaut
- Marge de semis (%)
- Traçabilité par lots activée ou non

---

## 7. Phases de développement

Chaque phase se termine par : module installable sur une base vierge, mise à jour sans erreur depuis la phase précédente, tests verts, README mis à jour.

### Phase 0 — Assainissement
- Corriger les bugs listés dans `README.md` :
  - référence `odoo_garden.action_garden_farm` dans le contrôleur
  - droits manquants sur `garden.culture.mode` et `garden.plot`
  - le Gantt doit recevoir un domaine et non le contexte
  - `view_mode` `list`
- Supprimer la méthode dupliquée et `views/garden_traceability_views.xml`.
- Ajouter un `.gitignore` (`__pycache__/`, `.venv/`, `*.pyc`).
- Mettre en place `tests/` avec un premier test d'installation.

### Phase 1 — Structure et catalogue
- Dépendances : `product`, `uom`, `mail`.
- Surfaces sur planches et îlots, champs d'irrigation, `company_id`, `active`.
- Créer `garden.species`, `garden.variety`, `garden.crop.template` et ses étapes.
- Supprimer `garden.plot`, `garden.culture.mode`, `garden.crop.catalog`.
- Groupes de sécurité et règles multi-société.
- Données de démo : 1 ferme, 2 sites, 4 îlots, 20 planches, 10 espèces, 15 variétés, itinéraires.

### Phase 2 — Planification
- `garden.season`, refonte de `garden.crop` (états, prévu, surface).
- Rétro-planning, assistant de création en série, contrôles de chevauchement et de rotation.
- Génération des opérations planifiées, rapport des besoins en semences.
- Gantt OWL amélioré, calendrier.

### Phase 3 — Opérations et main-d'œuvre
- Dépendance : `hr`.
- `garden.operation` (remplace `garden.action` et `garden.postprocess`), travailleurs, chronomètre, coût.
- Périmètre culture / planche / îlot et répartition au prorata de la surface.
- Vue « Ma journée », étiquettes QR des planches.

### Phase 4 — Stock : intrants, récoltes, pertes, traçabilité
- Dépendance : `stock`.
- Emplacements virtuels de production et de consommation (données XML).
- Lignes d'intrants → mouvements de consommation ; récolte → entrée en stock avec lot de culture.
- `garden.loss` relié au rebut, traçabilité amont (lot de semence) et aval.

### Phase 5 — Ventes et rentabilité
- Dépendances : `sale_management`, `account`.
- Attribution du CA (par lot / au prorata).
- `garden.crop.profitability` avec vues pivot et graphique, champs calculés sur la culture.
- Tableau de bord. Supprimer les anciennes actions client « Statistiques » et « Production » (Chart.js).

### Phase 6 — Conformité
- Champs réglementaires sur les produits.
- Registre phytosanitaire (PDF + XLSX), contrôle DAR, registre de fertilisation, export bio.

### Phase 7 — Ponts optionnels et publication
- `odoo_garden_purchase` (demandes de prix de semences), `odoo_garden_pos` (CA des marchés), en `auto_install`.
- Traductions : `i18n/fr.pot` et `fr.po` (les libellés sources passent en anglais, voir § 8).
- Publication sur l'Apps Store :
  - licence `OPL-1`, `price` et `currency` dans le manifeste
  - `static/description/index.html`, `icon.png`, captures d'écran
  - aucune ressource externe (pas de CDN)

---

## 8. Consignes techniques pour le développement

- **Répertoire de travail** : ce dossier. Après chaque modification, recopier le module dans `odoo/custom_addons/odoo_garden` (voir `COPILOT.md`).
- **Conventions Odoo 19** : vérifier dans le code source d'Odoo 19 avant d'utiliser une API dont la forme a changé.
  - vues `list` (et non `tree`) ; attributs `invisible` / `readonly` / `required` en expressions (pas de `attrs` ni de `states`)
  - `<chatter/>` dans les formulaires
  - `models.Constraint` à la place de `_sql_constraints`
  - `@api.model_create_multi`
  - structure des groupes (`res.groups` / privilèges)
- **Renommage `garden.action` → `garden.operation`** : on suppose qu'aucune base de production ne contient de données. Si ce n'est pas le cas, écrire des scripts `migrations/` à chaque changement de modèle.
- **Libellés** : écrire les chaînes en anglais dans le code et fournir la traduction française dans `i18n/fr.po` (exigence de l'Apps Store et des clients non francophones). Les libellés métier restent français dans ce document.
- **Pas de SQL brut** hors des modèles de reporting `_auto = False`. Utiliser l'ORM (`_read_group`) pour les agrégations dans le reste du code.
- **Pas de librairie externe** chargée par CDN. Préférer les vues natives pivot et graphique, et `@web/core/assets` (`loadJS`) si une librairie est indispensable.
- **Tests** (`tests/`, `TransactionCase` et `tagged('post_install', '-at_install')`), au minimum :
  - rétro-planning
  - contrôles de chevauchement et de rotation
  - répartition d'une opération d'îlot
  - mouvements de stock de récolte et de consommation
  - attribution du CA par lot et au prorata
  - contrôle DAR
  - droits d'accès de l'ouvrier (pas d'accès aux coûts)
- **Commande de test** : `odoo-bin -d <base> -i odoo_garden --test-enable --stop-after-init` (à adapter à l'environnement local).
- **Un commit par phase** (ou par sous-étape significative), message en français.

---

## 9. Hypothèses à valider avec le porteur du projet

1. Aucune donnée de production à migrer (renommages et suppressions de modèles autorisés).
2. Cible : Odoo 19 Community **et** Enterprise, marché francophone en priorité (registres français).
3. Une ferme = une société Odoo ; plusieurs fermes possibles en multi-société.
4. Monnaie et unités par défaut : EUR, kg, m².
5. Prix de vente, nom commercial et éditeur (`author`, `website`) à définir avant la phase 7.
