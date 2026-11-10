# Farmer Power

Gestion d'une exploitation maraîchère pour Odoo 19. Le dépôt contient trois modules, chacun dans son dossier :

| Dossier | Rôle |
|---|---|
| [`farmer_power/`](farmer_power/README.md) | application principale |
| `farmer_power_purchase/` | pont Achats : demandes de prix de semences (`auto_install` avec `purchase`) |
| `farmer_power_pos/` | pont Point de vente : ventes de marché dans le chiffre d'affaires des cultures (`auto_install` avec `point_of_sale`) |

Ajouter le dossier du dépôt à l'`addons_path` d'Odoo ; voir `farmer_power/README.md` et `farmer_power/docs/INSTALLATION.md`.

`loadtest/` : scripts de test de charge (non inclus dans les archives). `tools/` : outils de migration.
