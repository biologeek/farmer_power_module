"""Mesures de charge de Farmer Power sur la base farmer_power_load.

    ./odoo-venv/bin/python odoo/odoo-bin shell -c odoo.conf -d farmer_power_load --db-filter=^farmer_power_load$ \
        --no-http < custom_addons/farmer_power/loadtest/benchmark.py

Chaque mesure : temps réel, nombre de requêtes SQL, nombre de lignes. Exécuté en administrateur (droits gérant).
Les écritures de mesure sont annulées (rollback) : la base n'est pas modifiée.
"""
import json
import os
import resource
import time
from datetime import date

from odoo import Command, api

REPEAT = int(os.environ.get('BENCH_REPEAT', '1'))
results = []

env = api.Environment(env.cr, 2, dict(env.context, tracking_disable=True))  # noqa: F821 (admin)
admin = env.user
mgr = env.ref('farmer_power.group_garden_manager')
if mgr not in admin.group_ids:
    admin.write({'group_ids': [Command.link(mgr.id)]})
env.cr.commit()


def measure(label, func, repeat=REPEAT, rollback=True):
    best = None
    for _ in range(repeat):
        env.invalidate_all()
        q0, t0 = env.cr.sql_log_count if hasattr(env.cr, 'sql_log_count') else 0, time.perf_counter()
        out = func()
        dt = time.perf_counter() - t0
        q1 = env.cr.sql_log_count if hasattr(env.cr, 'sql_log_count') else 0
        if rollback:
            env.cr.rollback()
        if best is None or dt < best[0]:
            best = (dt, q1 - q0, out)
    dt, q, out = best
    size = out if isinstance(out, int) else ''
    results.append({'label': label, 'seconds': round(dt, 3), 'queries': q, 'size': size})
    print('%-62s %8.2fs %7d req  %s' % (label, dt, q, size), flush=True)


Crop, Op, Bed = env['garden.crop'], env['garden.operation'], env['garden.bed']
n_crops = Crop.search_count([])
print('Base : %d cultures, %d opérations, %d planches\n' % (n_crops, Op.search_count([]), Bed.search_count([])))

# --- Tableaux de bord thématiques ------------------------------------------------------------------------
A = env['garden.analytics']
for theme in ('occupation', 'crops', 'work', 'finance', 'years'):
    for year in (2027, 2025):
        if theme == 'years' and year == 2025:
            continue
        measure('dashboard %s %d' % (theme, year), lambda t=theme, y=year: len(A.get_data(t, y)['charts']))

# --- Rentabilité -----------------------------------------------------------------------------------------
P = env['garden.crop.profitability']
measure('rentabilité : refresh() complet (création initiale)', lambda: P.refresh() and P.search_count([]), rollback=False)
env.cr.commit()  # conserve les lignes pour les mesures suivantes
measure('rentabilité : refresh() sans changement', lambda: P.refresh() and P.search_count([]))
measure('rentabilité : get_dashboard_data()', lambda: len(P.get_dashboard_data()))
measure('rentabilité : liste (80 premières lignes)', lambda: len(P.search_read([], limit=80)))
measure('rentabilité : groupement par saison', lambda: len(P._read_group([], ['crop_id.season_id'], ['revenue:sum'])))

# --- Chiffre d'affaires attribué (les deux méthodes + pont PdV) -------------------------------------------
Rev = env['garden.revenue']
crops_all = Crop.search([('state', '!=', 'cancelled')])
for method in ('prorata', 'lot'):
    measure('chiffre d\'affaires, méthode %s, %d cultures' % (method, len(crops_all)),
            lambda m=method: len(Rev.get_revenue(crops_all, m)))
crop_sample = crops_all[:1]
measure('chiffre d\'affaires, 1 culture (prorata)', lambda: len(Rev.get_revenue(crop_sample, 'prorata')))

# --- Gantt d'occupation ----------------------------------------------------------------------------------
season_2027 = env['garden.season'].search([('name', 'like', '%2027')], limit=1)
site = env['garden.site'].search([], limit=1)
measure('Gantt occupation : toutes les planches/saisons', lambda: len(Bed.get_occupancy_data()['beds']))
measure('Gantt occupation : saison 2027', lambda: len(Bed.get_occupancy_data(season_id=season_2027.id)['beds']))
measure('Gantt occupation : saison 2027 + 1 site', lambda: len(Bed.get_occupancy_data(season_id=season_2027.id, site_id=site.id)['beds']))

# --- Besoins en semences ---------------------------------------------------------------------------------
measure('besoins en semences : toutes cultures', lambda: len(Crop.get_seed_needs()))
measure('besoins en semences : saison 2027', lambda: len(Crop.get_seed_needs([('season_id', '=', season_2027.id)])))

# --- Registres de conformité -----------------------------------------------------------------------------
W = env['garden.compliance.wizard']
for register in ('phyto', 'fertilization', 'organic'):
    for label, vals in (('2027', {'date_from': '2027-01-01', 'date_to': '2027-12-31'}), ('2023-2027', {'date_from': '2023-01-01', 'date_to': '2027-12-31'})):
        def run(register=register, vals=vals):
            w = W.create(dict(vals, register=register))
            w._compute_lines()
            return w.line_count if hasattr(w, 'line_count') else len(w.line_ids)
        measure('registre %s %s : calcul' % (register, label), run)

    def run_xlsx(register=register):
        w = W.create({'register': register, 'date_from': '2023-01-01', 'date_to': '2027-12-31'})
        w._compute_lines()
        t = time.perf_counter()
        name, content = w._get_xlsx()
        return len(content)
    measure('registre %s 2023-2027 : calcul + export XLSX (octets)' % register, run_xlsx)

# --- Listes, formulaires, « Ma journée » ----------------------------------------------------------------
crop_fields = ['name', 'season_id', 'template_id', 'bed_id', 'state', 'area', 'planned_harvest_start',
               'harvested_qty', 'margin', 'revenue', 'labour_cost', 'input_cost', 'has_overlap', 'has_rotation_conflict']
measure('liste cultures : 80 lignes (champs stockés + calculés)', lambda: len(Crop.search_read([], crop_fields, limit=80, order='id desc')))
measure('liste cultures : recherche texte « 27- »', lambda: len(Crop.search_read([('name', 'ilike', '27-')], ['name'], limit=80)))
measure('liste cultures : regroupement par saison/état', lambda: len(Crop._read_group([], ['season_id', 'state'], ['__count'])))
measure('liste opérations : 80 lignes', lambda: len(Op.search_read([], ['name', 'type_id', 'state', 'date', 'total_hours', 'labour_cost', 'input_cost'], limit=80, order='date desc')))
measure('liste opérations : regroupement par type', lambda: len(Op._read_group([], ['type_id'], ['total_hours:sum'])))
measure('« Ma journée » : opérations planifiées d\'un employé', lambda: len(Op.search_read(
    [('employee_ids', 'in', env['hr.employee'].search([('name', 'like', 'LOAD Worker%')], limit=1).ids), ('state', 'in', ('planned', 'in_progress'))],
    ['name', 'type_id', 'planned_date'], limit=80)))
measure('formulaire d\'une culture récoltée (champs calculés)', lambda: len(Crop.search([('state', '=', 'done')], limit=1).read(list(Crop._fields))[0]))
measure('traçabilité d\'un lot', lambda: len(env['garden.traceability']._open(crop=Crop.search([('lot_ids', '!=', False)], limit=1)) or {}))

# --- Écritures -------------------------------------------------------------------------------------------
bed = Bed.search([], limit=1)
tpl = env['garden.crop.template'].search([], limit=1)
season = season_2027
measure('création d\'une culture sans nom (calcul automatique du nom)', lambda: Crop.create({'season_id': season.id, 'template_id': tpl.id, 'bed_id': bed.id, 'planned_sowing_date': '2027-04-01'}).id and 1)
garden = env['garden.garden'].search([], limit=1)
n_in_garden = Crop.search_count([('bed_id.garden_id', '=', garden.id), ('state', '!=', 'cancelled')])
measure('opération « îlot » faite (%d cultures dans l\'îlot)' % n_in_garden, lambda: Op.create({
    'type_id': env.ref('farmer_power.operation_type_irrigation').id, 'scope': 'garden', 'garden_id': garden.id,
    'planned_date': '2027-06-01', 'date': '2027-06-01', 'state': 'done', 'duration': 2.0}).id and 1)
crop_h = Crop.search([('state', '=', 'harvesting')], limit=1) or Crop.search([], limit=1)
measure('récolte faite sur une culture (mouvement de stock + lot)', lambda: Op.create({
    'type_id': env.ref('farmer_power.operation_type_harvest').id, 'scope': 'crop', 'crop_ids': [Command.set(crop_h.ids)],
    'planned_date': '2027-07-01', 'date': '2027-07-01', 'state': 'done', 'duration': 1.0, 'harvest_qty': 12.0,
    'harvest_product_id': crop_h.template_id.variety_id.harvest_product_id.id, 'harvest_uom_id': env.ref('uom.product_uom_kgm').id}).id and 1)
measure('changement du taux horaire par défaut (recalcul de tous les coûts)', lambda: Op.search([])._recompute_labour_cost() or 1, repeat=1)

# --- Bilan -----------------------------------------------------------------------------------------------
print('\nMémoire max du processus : %.0f Mo' % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024))
out = os.environ.get('BENCH_OUT')
if out:
    with open(out, 'w') as f:
        json.dump(results, f, indent=1)
print('\nLentes (> 1 s) :')
for r in sorted(results, key=lambda r: -r['seconds']):
    if r['seconds'] > 1:
        print('  %7.2fs  %6d req  %s' % (r['seconds'], r['queries'], r['label']))
