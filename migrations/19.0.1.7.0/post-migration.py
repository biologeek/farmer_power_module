"""Phase 7: the source labels became English.

Default records that live in ``noupdate`` data (operation types, virtual stock locations, record rules) keep
their former French names on a database created before this version, which Odoo does not rewrite on update.
Rename those that still carry the original French name (a record renamed by the user is left untouched).
The French name is kept as the ``fr_FR`` translation when the record is translatable and the language is active.
"""
from odoo import SUPERUSER_ID, api

# (xml id of the farmer_power module, model, former French name, new English name)
RENAMES = [
    ('operation_type_soil_preparation', 'garden.operation.type', 'Préparation du sol', 'Soil Preparation'),
    ('operation_type_sowing', 'garden.operation.type', 'Semis', 'Sowing'),
    ('operation_type_transplanting', 'garden.operation.type', 'Repiquage', 'Transplanting'),
    ('operation_type_planting', 'garden.operation.type', 'Plantation', 'Planting'),
    ('operation_type_irrigation', 'garden.operation.type', 'Arrosage', 'Watering'),
    ('operation_type_weeding', 'garden.operation.type', 'Désherbage', 'Weeding'),
    ('operation_type_fertilization', 'garden.operation.type', 'Fertilisation', 'Fertilization'),
    ('operation_type_treatment', 'garden.operation.type', 'Traitement', 'Treatment'),
    ('operation_type_mulching', 'garden.operation.type', 'Paillage', 'Mulching'),
    ('operation_type_harvest', 'garden.operation.type', 'Récolte', 'Harvest'),
    ('operation_type_washing', 'garden.operation.type', 'Lavage', 'Washing'),
    ('operation_type_packing', 'garden.operation.type', 'Conditionnement', 'Packing'),
    ('stock_location_garden_production', 'stock.location', 'Production maraîchage', 'Market Gardening Production'),
    ('stock_location_garden_consumption', 'stock.location', 'Consommation maraîchage', 'Market Gardening Consumption'),
    ('garden_farm_company_rule', 'ir.rule', 'Ferme : multi-société', 'Farm: multi-company'),
    ('garden_site_company_rule', 'ir.rule', 'Site : multi-société', 'Site: multi-company'),
    ('garden_garden_company_rule', 'ir.rule', 'Îlot : multi-société', 'Block: multi-company'),
    ('garden_bed_company_rule', 'ir.rule', 'Planche : multi-société', 'Bed: multi-company'),
    ('garden_crop_company_rule', 'ir.rule', 'Culture : multi-société', 'Crop: multi-company'),
    ('garden_operation_company_rule', 'ir.rule', 'Opération : multi-société', 'Operation: multi-company'),
    ('garden_operation_worker_rule', 'ir.rule', "Opération : l'ouvrier voit ses opérations et celles sans employé", 'Operation: the worker sees their own operations and those without employee'),
    ('garden_operation_chef_rule', 'ir.rule', 'Opération : le chef de culture voit tout', 'Operation: the crop manager sees everything'),
    ('garden_operation_worker_company_rule', 'ir.rule', 'Temps par employé : multi-société', 'Time per employee: multi-company'),
    ('garden_operation_allocation_company_rule', 'ir.rule', "Répartition d'opération : multi-société", 'Operation allocation: multi-company'),
    ('garden_operation_input_company_rule', 'ir.rule', "Intrant d'opération : multi-société", 'Operation input: multi-company'),
    ('garden_loss_company_rule', 'ir.rule', 'Perte : multi-société', 'Loss: multi-company'),
    ('garden_season_company_rule', 'ir.rule', 'Saison : multi-société', 'Season: multi-company'),
    ('garden_crop_profitability_company_rule', 'ir.rule', 'Rentabilité par culture : multi-société', 'Crop profitability: multi-company'),
]


def rename_defaults(env):
    french_active = bool(env['res.lang'].with_context(active_test=False).search([('code', '=', 'fr_FR'), ('active', '=', True)]))
    for xmlid, _model, old, new in RENAMES:
        record = env.ref('farmer_power.%s' % xmlid, raise_if_not_found=False)
        if not record:
            continue
        english = record.with_context(lang='en_US')
        if english.name != old:
            continue
        english.name = new
        if french_active and record._fields['name'].translate:
            record.update_field_translations('name', {'fr_FR': old})


def migrate(cr, version):
    rename_defaults(api.Environment(cr, SUPERUSER_ID, {}))
