# Installation et `addons_path`

Le dépôt contient **trois modules Odoo**, chacun dans un dossier à la racine :

| Module | Dossier | Rôle |
|---|---|---|
| `farmer_power` | `farmer_power/` | application principale |
| `farmer_power_purchase` | `farmer_power_purchase/` | pont Achats (`auto_install` avec `purchase`) |
| `farmer_power_pos` | `farmer_power_pos/` | pont Point de vente (`auto_install` avec `point_of_sale`) |

Il suffit d'ajouter **le dossier du dépôt** à l'`addons_path` (`--addons-path=<addons d'Odoo>,<dépôt>` ou `addons_path = ...` dans `odoo.conf`) : Odoo y trouve les trois modules. Les ponts s'installent d'eux-mêmes quand Achats / Point de vente sont installés ; ne pas les installer sans le module principal (ils en dépendent), qui fonctionne seul.

## Environnement de développement

Dans cet environnement, `custom_addons/` (hors dépôt) contient des liens symboliques vers les trois dossiers :

```
custom_addons/farmer_power           -> ../module/farmer_power
custom_addons/farmer_power_purchase  -> ../module/farmer_power_purchase
custom_addons/farmer_power_pos       -> ../module/farmer_power_pos
```

Redémarrer Odoo et mettre à jour la liste des applications.

## Test

```
./run.sh -d garden_test -i farmer_power,farmer_power_purchase,farmer_power_pos --test-enable \
  --test-tags /farmer_power,/farmer_power_purchase,/farmer_power_pos --stop-after-init
```
