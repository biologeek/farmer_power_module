# Tests de charge

Scripts de développement (non livrés : `loadtest/` est exclu de `git archive`, voir `.gitattributes`) pour générer
un jeu de données volumineux et cohérent, puis mesurer les écrans et calculs coûteux de Farmer Power.

Tous les scripts se lancent depuis le dossier qui contient `odoo/` et `odoo.conf`, avec `odoo-bin shell` :

```
createdb farmer_power_load
./odoo-venv/bin/python odoo/odoo-bin -c odoo.conf -d farmer_power_load --db-filter=^farmer_power_load$ \
    -i farmer_power,farmer_power_purchase,farmer_power_pos,point_of_sale,purchase --without-demo=all --stop-after-init

LOAD_SCALE=1.0 ./odoo-venv/bin/python odoo/odoo-bin shell -c odoo.conf -d farmer_power_load \
    --db-filter=^farmer_power_load$ --no-http < custom_addons/farmer_power/loadtest/generate_load_data.py
```

| Script | Rôle |
|---|---|
| `generate_load_data.py` | Génère ferme, catalogue, cultures, opérations, pertes, factures, ventes livrées par lot et commandes PdV. `LOAD_SCALE` (1.0 ≈ 1 200 planches, 8 300 cultures, 96 000 opérations, 8 000 factures, 2 000 ventes, 40 000 commandes PdV ; 0.02 = test de fumée), `LOAD_STEPS` pour limiter les étapes. Durée à l'échelle 1 : environ 35 minutes. Idempotent par étape. |
| `benchmark.py` | Mesure temps réel et requêtes SQL des tableaux de bord, de la rentabilité, du chiffre d'affaires, du Gantt, des registres et exports, des listes et des écritures (`BENCH_REPEAT`, `BENCH_OUT` pour un JSON). Les écritures sont annulées. |
| `profile_prorata.py`, `profile_gantt.py`, `profile_profit.py`, `profile_dash.py` | Profils cProfile des points qui ont posé problème. |
| `check_revenue.py` | Vérifie que les totaux agrégés du pont PdV égalent la somme des entrées détaillées (prorata et lot). |
| `time_refresh.py` | Temps de `refresh()` et du tableau de bord de rentabilité, et cohérence des lignes avec le recalcul de l'ORM. |

`results/benchmark_before.out` et `results/benchmark_after.out` donnent les mesures avant et après les corrections de
performance (8 309 cultures, 95 964 opérations ; machine de développement partagée, mesures uniques, cache vidé à
chaque mesure : ordres de grandeur du premier affichage).

Limites du jeu de données : suivi des messages coupé pendant la génération ; toutes les commandes PdV sont rattachées
à une seule session ouverte ; les ventes par lot ne portent que sur les lots ayant du stock.
