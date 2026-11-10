"""Générateur de données de charge pour Farmer Power (farmer_power).

Usage (depuis le dossier qui contient odoo/ et odoo.conf) :

    LOAD_SCALE=0.02 ./odoo-venv/bin/python odoo/odoo-bin shell -c odoo.conf -d farmer_power_load \
        --no-http < custom_addons/farmer_power/loadtest/generate_load_data.py

LOAD_SCALE : 1.0 = « grosse exploitation » (~1 200 planches, ~10 000 cultures, ~100 000 opérations,
~6 000 factures, ~40 000 commandes PdV). 0.02 = test de fumée. LOAD_STEPS limite les étapes
(ex. « structure,catalog,crops »). Les données sont cohérentes entre applications : récoltes en stock avec
lot par culture -> factures clients (prorata) + commandes de vente livrées par lot + commandes PdV payées.
"""
import logging
import os
import random
import time
from datetime import date, timedelta

from odoo import Command, fields

_logger = logging.getLogger('loadtest')
logging.getLogger('loadtest').setLevel(logging.INFO)

SCALE = float(os.environ.get('LOAD_SCALE', '0.02'))
STEPS = set((os.environ.get('LOAD_STEPS') or 'structure,catalog,crops,operations,losses,invoices,orders,pos').split(','))
YEARS = [2023, 2024, 2025, 2026, 2027]
rnd = random.Random(42)
T0 = time.time()


def n(base, minimum=1):
    return max(minimum, int(base * SCALE))


def log(msg, *args):
    print('[%6.0fs] %s' % (time.time() - T0, msg % args if args else msg), flush=True)


# Pas de suivi de messagerie ni de notifications pendant la génération (le coût du chatter se mesure à part).
env = env(context=dict(env.context, tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
                       mail_create_nosubscribe=True))  # noqa: F821
Env = env  # noqa
ref = env.ref
company = env.company


def commit():
    env.cr.commit()
    env.invalidate_all()


def batches(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ---------------------------------------------------------------------------------------------------------
# Structure : ferme, sites, îlots, planches
# ---------------------------------------------------------------------------------------------------------
if 'structure' in STEPS and not env['garden.farm'].search([('name', '=', 'LOAD Farm')]):
    farm = env['garden.farm'].create({'name': 'LOAD Farm'})
    sites = env['garden.site'].create([
        {'name': 'Site %d' % i, 'farm_id': farm.id, 'latitude': 48 + rnd.random(), 'longitude': -1.7 + rnd.random()}
        for i in range(1, n(4, 2) + 1)
    ])
    gardens = env['garden.garden'].create([
        {
            'name': 'Block %s%02d' % (site.name[-1], k), 'code': '%s%02d' % (site.name[-1], k), 'site_id': site.id,
            'culture_type': rnd.choice(['open_air'] * 3 + ['sheltered']),
            'irrigation_type': rnd.choice(['drip', 'sprinkler', 'manual', 'none']),
            'irrigation_flow': rnd.choice([0, 800, 1200, 2500]),
        }
        for site in sites for k in range(1, n(30, 4) // len(sites) + 1)
    ])
    beds_per = max(5, n(1200, 20) // len(gardens))
    soils = ['sandy', 'silty', 'clayey', 'loamy', 'humus']
    bed_vals = [
        {
            'name': 'Bed %s-%03d' % (g.code, i), 'code': '%s%03d' % (g.code, i), 'garden_id': g.id,
            'length': rnd.choice([20, 25, 30, 40, 50]), 'width': rnd.choice([0.8, 1.0, 1.2]),
            'soil_type': rnd.choice(soils),
        }
        for g in gardens for i in range(1, beds_per + 1)
    ]
    for chunk in batches(bed_vals, 500):
        env['garden.bed'].create(chunk)
    commit()
    log('structure : %d sites, %d îlots, %d planches', len(sites), len(gardens), len(bed_vals))

# ---------------------------------------------------------------------------------------------------------
# Catalogue : variétés, produits récoltés, intrants, itinéraires techniques, employés, clients
# ---------------------------------------------------------------------------------------------------------
if 'catalog' in STEPS and not env['garden.variety'].search([('name', 'like', 'LOAD %')], limit=1):
    species = env['garden.species'].search([])
    uom_kg = ref('uom.product_uom_kgm')
    varieties, harvest_products = env['garden.variety'], env['product.product']
    for sp in species[: n(45, 8)]:
        for k in range(1, 4):
            hp = env['product.product'].create({
                'name': 'LOAD %s %d (kg)' % (sp.name, k), 'type': 'consu', 'is_storable': True, 'tracking': 'lot',
                'uom_id': uom_kg.id, 'list_price': round(rnd.uniform(2, 9), 2), 'sale_ok': True,
                'available_in_pos': True,
            })
            varieties |= env['garden.variety'].create({
                'name': 'LOAD %s %d' % (sp.name, k), 'species_id': sp.id, 'harvest_product_id': hp.id,
                'germination_rate': rnd.choice([80, 90, 95]),
            })
    steps_cat = [(ref('farmer_power.operation_type_%s' % c).id, o, h) for c, o, h in [
        ('sowing', 0, 0.02), ('weeding', 25, 0.01), ('fertilization', 20, 0.005), ('harvest', 70, 0.03)]]
    templates = env['garden.crop.template']
    for v in varieties:
        templates |= env['garden.crop.template'].create({
            'name': '%s - route' % v.name, 'variety_id': v.id, 'culture_type': rnd.choice(['open_air', 'sheltered']),
            'propagation': 'direct_sowing', 'row_count': 3, 'row_spacing': 30, 'plant_spacing': 20,
            'days_to_maturity': rnd.choice([50, 70, 90, 120]), 'harvest_window_days': rnd.choice([21, 42, 70]),
            'expected_yield': round(rnd.uniform(1.5, 8), 1), 'expected_price': round(rnd.uniform(2, 9), 2),
            'step_ids': [Command.create({'operation_type_id': t, 'day_offset': o, 'expected_duration': h})
                         for t, o, h in steps_cat],
        })
    inputs = {}
    mk = lambda name, typ, **kw: env['product.product'].create(dict({  # noqa: E731
        'name': 'LOAD ' + name, 'type': 'consu', 'is_storable': True, 'garden_input_type': typ,
        'uom_id': uom_kg.id, 'list_price': 0, 'sale_ok': False, 'standard_price': round(rnd.uniform(1, 12), 2),
    }, **kw))
    inputs['fertilizer'] = env['product.product'].concat(*[mk('Fertilizer %d' % i, 'fertilizer', nitrogen_content=rnd.choice([3, 5, 8, 12]), is_organic_allowed=i % 2 == 0) for i in range(8)])
    inputs['phytosanitary'] = env['product.product'].concat(*[mk('Treatment %d' % i, 'phytosanitary', amm_number='AMM-LOAD-%07d (dummy number)' % (1000 + i), pre_harvest_interval_days=rnd.choice([3, 7, 14, 21]), is_organic_allowed=i % 3 == 0) for i in range(8)])
    inputs['seed'] = env['product.product'].concat(*[mk('Seed %d' % i, 'seed') for i in range(6)])
    inputs['substrate'] = env['product.product'].concat(*[mk('Potting soil %d' % i, 'substrate') for i in range(3)])
    emps = env['hr.employee'].create([
        {'name': 'LOAD Worker %02d' % i, 'garden_hourly_cost': rnd.choice([14, 16, 18, 22])} for i in range(1, n(40, 6) + 1)
    ])
    env['res.partner'].create([
        {'name': 'LOAD Customer %04d' % i, 'customer_rank': 1, 'is_company': rnd.random() < 0.5}
        for i in range(1, n(300, 8) + 1)
    ])
    commit()
    log('catalogue : %d variétés, %d itinéraires, %d employés, %d intrants', len(varieties), len(templates), len(emps),
        sum(len(v) for v in inputs.values()))

# Objets partagés par les étapes suivantes
varieties = env['garden.variety'].search([('name', 'like', 'LOAD %')])
templates = env['garden.crop.template'].search([('name', 'like', 'LOAD %')])
beds = env['garden.bed'].search([('name', 'like', 'Bed %')]).filtered(lambda b: b.garden_id.site_id.farm_id.name == 'LOAD Farm')
employees = env['hr.employee'].search([('name', 'like', 'LOAD Worker%')])
customers = env['res.partner'].search([('name', 'like', 'LOAD Customer%')])
fert = env['product.product'].search([('name', 'like', 'LOAD Fertilizer%')])
phyto = env['product.product'].search([('name', 'like', 'LOAD Treatment%')])
seeds = env['product.product'].search([('name', 'like', 'LOAD Seed%')])
OP = lambda c: ref('farmer_power.operation_type_%s' % c)  # noqa: E731
kg = ref('uom.product_uom_kgm')

# ---------------------------------------------------------------------------------------------------------
# Saisons et cultures
# ---------------------------------------------------------------------------------------------------------
if 'crops' in STEPS and not env['garden.season'].search([('name', 'like', 'LOAD %')], limit=1):
    seasons = env['garden.season'].create([
        {'name': 'LOAD Season %d' % y, 'date_start': date(y, 1, 1), 'date_end': date(y, 12, 31),
         'state': 'closed' if y < 2027 else 'validated'} for y in YEARS
    ])
    count = 0
    for season in seasons:
        y = season.date_start.year
        vals = []
        for bed in beds:
            cursor = date(y, 3, 1) + timedelta(days=rnd.randint(0, 30))
            for _ in range(rnd.choice([1, 2, 2])):
                tpl = rnd.choice(templates)
                sowing = cursor
                harvest_start = sowing + timedelta(days=tpl.days_to_maturity or 70)
                harvest_end = harvest_start + timedelta(days=tpl.harvest_window_days or 30)
                if harvest_end.year > y or harvest_end > date(y, 12, 15):
                    break
                vals.append({
                    'name': '%d-%s-%02d' % (y % 100, bed.code, len(vals) % 97),
                    'season_id': season.id, 'template_id': tpl.id, 'bed_id': bed.id, 'bed_share': 100,
                    'state': 'done' if y < 2027 else rnd.choice(['planned', 'sown', 'harvesting', 'done']),
                    'planned_sowing_date': sowing, 'planned_harvest_start': harvest_start,
                    'planned_harvest_end': harvest_end, 'date_start': sowing,
                    'date_end': harvest_end if y < 2027 else False,
                    'sowing_quantity': 300, 'planted_quantity': 280,
                })
                cursor = harvest_end + timedelta(days=rnd.randint(3, 15))
        # noms uniques (le préfixe ci-dessus évite le coût de _assign_names, mesuré à part)
        seen = {}
        for v in vals:
            key = v['name'][:-3]
            seen[key] = seen.get(key, 0) + 1
            v['name'] = '%s-%02d' % (key, seen[key])
        for chunk in batches(vals, 500):
            env['garden.crop'].create(chunk)
        commit()
        count += len(vals)
        log('cultures %d : %d (total %d)', y, len(vals), count)

crops = env['garden.crop'].search([('season_id.name', 'like', 'LOAD %')])

# ---------------------------------------------------------------------------------------------------------
# Opérations : travaux, intrants, traitements, récoltes (entrées en stock avec lot par culture)
# ---------------------------------------------------------------------------------------------------------
if 'operations' in STEPS and crops and not env['garden.operation'].search([('description', '=', 'LOAD')], limit=1):
    total_ops = 0
    work_types = [OP('weeding'), OP('irrigation'), OP('hoeing'), OP('mulching'), OP('fertilization'), OP('treatment')]
    for chunk in batches(list(crops), 200):
        vals = []
        for crop in chunk:
            tpl = crop.template_id
            sow = crop.date_start or crop.planned_sowing_date
            hs = crop.planned_harvest_start
            he = crop.planned_harvest_end or hs
            workers = rnd.sample(list(employees), rnd.choice([1, 1, 2, 3]))
            common = {'scope': 'crop', 'crop_ids': [Command.set([crop.id])], 'description': 'LOAD', 'state': 'done'}
            # semis avec intrant de semence
            vals.append(dict(common, type_id=OP('sowing').id, planned_date=sow, date=sow,
                             employee_ids=[Command.set([w.id for w in workers])], duration=round(rnd.uniform(0.5, 3), 2),
                             input_ids=[Command.create({'product_id': rnd.choice(seeds).id, 'quantity': round(rnd.uniform(0.1, 1), 2), 'uom_id': kg.id})]))
            # travaux d'entretien, certains avec intrants (engrais) ou traitement
            for k in range(rnd.randint(3, 6)):
                t = rnd.choice(work_types)
                d = sow + timedelta(days=rnd.randint(7, max(8, (hs - sow).days - 10)))
                v = dict(common, type_id=t.id, planned_date=d, date=d,
                         employee_ids=[Command.set([w.id for w in rnd.sample(workers, 1)])],
                         duration=round(rnd.uniform(0.25, 2.5), 2))
                if t == OP('fertilization'):
                    v['input_ids'] = [Command.create({'product_id': rnd.choice(fert).id, 'quantity': round(rnd.uniform(1, 20), 1), 'uom_id': kg.id})]
                elif t == OP('treatment'):
                    product = rnd.choice(phyto)
                    # DAR respecté : traitement au moins 25 jours avant la première récolte
                    d = min(d, hs - timedelta(days=25))
                    v.update(planned_date=d, date=d, target=rnd.choice(['Mildew', 'Aphids', 'Rust']),
                             weather_notes='Dry, 18 °C, no wind',
                             input_ids=[Command.create({'product_id': product.id, 'quantity': round(rnd.uniform(0.1, 2), 2), 'uom_id': kg.id})])
                if rnd.random() < 0.3:  # saisie détaillée du temps par employé
                    v['worker_ids'] = [Command.create({'employee_id': w.id, 'duration': round(rnd.uniform(0.25, 2.5), 2)}) for w in workers]
                vals.append(v)
            # récoltes réparties sur la fenêtre de récolte
            product = tpl.variety_id.harvest_product_id
            for k in range(rnd.randint(4, 8)):
                d = hs + timedelta(days=int((he - hs).days * k / 8))
                vals.append(dict(common, type_id=OP('harvest').id, planned_date=d, date=d,
                                 employee_ids=[Command.set([w.id for w in rnd.sample(workers, 1)])],
                                 duration=round(rnd.uniform(0.5, 3), 2), harvest_product_id=product.id,
                                 harvest_qty=round(crop.area * rnd.uniform(0.2, 1.2), 1) or 5.0, harvest_uom_id=kg.id))
        try:
            env['garden.operation'].create(vals)
        except Exception as exc:  # noqa
            env.cr.rollback()
            log('ERREUR lot d\'opérations : %s', str(exc)[:300])
            continue
        commit()
        total_ops += len(vals)
        if total_ops % 2000 < len(vals):
            log('opérations : %d', total_ops)
    # quelques opérations à portée « îlot » (arrosage, travail du sol) : allocation sur de nombreuses cultures
    gardens = env['garden.garden'].search([('code', '!=', False)]).filtered(lambda g: g.site_id.farm_id.name == 'LOAD Farm')
    big_vals = []
    for g in gardens[: n(20, 3)]:
        for y in (2026, 2027):
            for m in range(4, 10):
                d = date(y, m, rnd.randint(1, 28))
                big_vals.append({'type_id': OP('irrigation').id, 'scope': 'garden', 'garden_id': g.id, 'planned_date': d, 'date': d,
                                 'employee_ids': [Command.set([rnd.choice(employees).id])], 'duration': 2.0, 'description': 'LOAD', 'state': 'done'})
    for chunk in batches(big_vals, 20):
        env['garden.operation'].create(chunk)
        commit()
    log('opérations : %d + %d à portée îlot', total_ops, len(big_vals))

# ---------------------------------------------------------------------------------------------------------
# Pertes
# ---------------------------------------------------------------------------------------------------------
if 'losses' in STEPS and crops and not env['garden.loss'].search([], limit=1):
    sample = rnd.sample(list(crops), int(len(crops) * 0.15))
    loss_vals = [{
        'crop_id': c.id, 'date': (c.planned_harvest_start or c.date_start) - timedelta(days=rnd.randint(1, 20)),
        'stage': 'pre_harvest', 'cause': rnd.choice(['disease', 'weather', 'pest', 'other']),
        'quantity': round(rnd.uniform(1, 15), 1), 'uom_id': kg.id,
    } for c in sample]
    for chunk in batches(loss_vals, 500):
        env['garden.loss'].create(chunk)
    commit()
    log('pertes : %d', len(loss_vals))

# ---------------------------------------------------------------------------------------------------------
# Factures clients (prorata des récoltes du mois) et commandes de vente livrées par lot
# ---------------------------------------------------------------------------------------------------------
hp_all = varieties.harvest_product_id
if 'invoices' in STEPS and customers and hp_all and not env['account.move'].search([('ref', '=', 'LOAD')], limit=1):
    months = [(y, m) for y in YEARS for m in range(4, 12)]
    inv_vals = []
    for (y, m) in months:
        for _ in range(n(150, 5)):
            d = date(y, m, 28)
            inv_vals.append({
                'move_type': 'out_invoice', 'partner_id': rnd.choice(customers).id, 'invoice_date': d, 'date': d, 'ref': 'LOAD',
                'invoice_line_ids': [Command.create({
                    'product_id': p.id, 'quantity': round(rnd.uniform(5, 80), 1), 'price_unit': p.list_price,
                    'tax_ids': [Command.clear()],
                }) for p in rnd.sample(list(hp_all), rnd.randint(1, 5))],
            })
    done = 0
    for chunk in batches(inv_vals, 100):
        moves = env['account.move'].create(chunk)
        moves.action_post()
        commit()
        done += len(chunk)
        if done % 1000 < 100:
            log('factures : %d / %d', done, len(inv_vals))
    log('factures : %d', done)

if 'orders' in STEPS and customers and not env['sale.order'].search([('client_order_ref', '=', 'LOAD')], limit=1):
    lots = env['stock.lot'].search([('garden_crop_id', 'in', crops.ids)], limit=n(2000, 20))
    done = 0
    for lot in lots:
        stock = env['stock.quant']._get_available_quantity(lot.product_id, company._get_garden_stock_location(), lot_id=lot)
        if stock < 2:
            continue
        qty = round(min(stock, rnd.uniform(2, 20)), 1)
        try:
            order = env['sale.order'].create({
                'partner_id': rnd.choice(customers).id, 'client_order_ref': 'LOAD',
                'date_order': fields.Datetime.to_datetime(lot.garden_crop_id.planned_harvest_end or date.today()),
                'order_line': [Command.create({'product_id': lot.product_id.id, 'product_uom_qty': qty, 'price_unit': lot.product_id.list_price, 'tax_ids': [Command.clear()]})],
            })
            order.action_confirm()
            picking = order.picking_ids
            picking.action_assign()
            move = picking.move_ids
            move.move_line_ids.unlink()
            env['stock.move.line'].create({
                'move_id': move.id, 'picking_id': picking.id, 'product_id': lot.product_id.id,
                'product_uom_id': lot.product_id.uom_id.id, 'quantity': qty, 'lot_id': lot.id,
                'location_id': picking.location_id.id, 'location_dest_id': picking.location_dest_id.id, 'picked': True,
            })
            move.picked = True
            picking.with_context(skip_backorder=True).button_validate()
            inv = order._create_invoices()
            inv.invoice_date = order.date_order.date()
            inv.action_post()
            done += 1
            if done % 25 == 0:
                commit()
        except Exception as exc:  # noqa
            env.cr.rollback()
            log('ERREUR commande lot %s : %s', lot.name, str(exc)[:200])
    commit()
    log('commandes de vente livrées par lot : %d', done)

# ---------------------------------------------------------------------------------------------------------
# Point de vente : commandes de marché payées (états forcés comme dans les tests du pont)
# ---------------------------------------------------------------------------------------------------------
if 'pos' in STEPS and 'pos.order' in env and hp_all and not env['pos.order'].search([('internal_note', '=', 'LOAD')], limit=1):
    config = env['pos.config'].search([('name', '=', 'LOAD Market')]) or env['pos.config'].create({'name': 'LOAD Market'})
    session = env['pos.session'].search([('config_id', '=', config.id), ('state', '=', 'opened')], limit=1)
    if not session:
        session = env['pos.session'].create({'config_id': config.id})
        session.action_pos_session_open()
    prods = list(hp_all)
    total = 0
    n_orders = n(40000, 40)
    for chunk in batches(list(range(n_orders)), 500):
        vals = []
        for _ in chunk:
            d = date(rnd.choice(YEARS), rnd.randint(4, 11), rnd.randint(1, 28))
            lines, amount = [], 0.0
            for p in rnd.sample(prods, rnd.randint(1, 4)):
                q = round(rnd.uniform(0.3, 4), 1)
                sub = round(q * p.list_price, 2)
                amount += sub
                lines.append(Command.create({
                    'name': p.name, 'product_id': p.id, 'qty': q, 'price_unit': p.list_price,
                    'price_subtotal': sub, 'price_subtotal_incl': sub,
                }))
            vals.append({
                'session_id': session.id, 'config_id': config.id, 'company_id': company.id, 'date_order': '%s 09:30:00' % d,
                'amount_tax': 0.0, 'amount_total': round(amount, 2), 'amount_paid': round(amount, 2), 'amount_return': 0.0,
                'lines': lines, 'internal_note': 'LOAD', 'state': 'paid',
            })
        env['pos.order'].create(vals)
        commit()
        total += len(vals)
        if total % 5000 < 500:
            log('commandes PdV : %d / %d', total, n_orders)
    log('commandes PdV : %d', total)

# ---------------------------------------------------------------------------------------------------------
# Bilan
# ---------------------------------------------------------------------------------------------------------
for model in ['garden.bed', 'garden.crop', 'garden.operation', 'garden.operation.input', 'garden.operation.worker',
              'garden.operation.allocation', 'garden.loss', 'stock.move', 'stock.lot', 'account.move', 'account.move.line',
              'sale.order', 'pos.order', 'pos.order.line']:
    if model in env:
        env.cr.execute('SELECT count(*) FROM %s' % env[model]._table)
        log('%-30s %d', model, env.cr.fetchone()[0])
env.cr.commit()
