# Installation et `addons_path`

Le dépôt contient **trois modules Odoo** :

| Module | Dossier | Rôle |
|---|---|---|
| `odoo_garden` | racine du dépôt | application principale |
| `odoo_garden_purchase` | `bridges/odoo_garden_purchase` | pont Achats (`auto_install` avec `purchase`) |
| `odoo_garden_pos` | `bridges/odoo_garden_pos` | pont Point de vente (`auto_install` avec `point_of_sale`) |

Odoo ne découvre que les modules situés **directement** dans un répertoire de l'`addons_path` : les ponts, rangés sous `bridges/`, doivent être rendus visibles.

## Environnement de développement

`custom_addons/` (hors dépôt, déjà dans l'`addons_path` de `odoo.conf`) contient des liens symboliques :

```
custom_addons/odoo_garden           -> ../module
custom_addons/odoo_garden_purchase  -> ../module/bridges/odoo_garden_purchase
custom_addons/odoo_garden_pos       -> ../module/bridges/odoo_garden_pos
```

Créer les liens manquants :

```
cd custom_addons
ln -s ../module/bridges/odoo_garden_purchase odoo_garden_purchase
ln -s ../module/bridges/odoo_garden_pos      odoo_garden_pos
```

Redémarrer Odoo, mettre à jour la liste des applications ; les ponts s'installent d'eux-mêmes quand Achats / Point de vente sont installés.

## Autre installation

- soit copier ou lier les trois dossiers côte à côte dans un répertoire déjà présent dans l'`addons_path` (le dossier du module principal doit s'appeler `odoo_garden`) ;
- soit ajouter le dossier des ponts à l'`addons_path` : `--addons-path=<addons d'Odoo>,<dossier parent du dépôt>,<dépôt>/bridges` (ou `addons_path = ...` dans `odoo.conf`).

Ne pas installer les ponts sans le module principal (ils en dépendent) ; le module principal fonctionne seul.

## Test

```
./run.sh -d garden_test -i odoo_garden,odoo_garden_purchase,odoo_garden_pos --test-enable \
  --test-tags /odoo_garden,/odoo_garden_purchase,/odoo_garden_pos --stop-after-init
```
