from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestGardenStockSetup(TransactionCase):

    def test_main_company_locations(self):
        company = self.env.ref('base.main_company')
        production = company.garden_production_location_id
        consumption = company.garden_consumption_location_id
        self.assertEqual(production, self.env.ref('odoo_garden.stock_location_garden_production'))
        self.assertEqual(consumption, self.env.ref('odoo_garden.stock_location_garden_consumption'))
        self.assertEqual((production.usage, consumption.usage), ('production', 'production'))
        self.assertEqual(production.company_id, company)
        self.assertNotEqual(production, consumption)

    def test_new_company_gets_its_own_locations(self):
        company = self.env['res.company'].create({'name': 'Ferme bis'})
        self.assertEqual(company.garden_production_location_id.company_id, company)
        self.assertEqual(company.garden_consumption_location_id.company_id, company)
        self.assertEqual(company.garden_production_location_id.usage, 'production')
        self.assertNotEqual(
            company.garden_production_location_id, self.env.company.garden_production_location_id,
        )

    def test_stock_location_defaults_to_warehouse_stock(self):
        company = self.env.ref('base.main_company')
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', company.id)], limit=1)
        self.assertFalse(company.garden_stock_location_id)
        self.assertEqual(company._get_garden_stock_location(), warehouse.lot_stock_id)
        other = self.env['stock.location'].create({
            'name': 'Chambre froide', 'usage': 'internal', 'company_id': company.id,
        })
        company.garden_stock_location_id = other
        self.assertEqual(company._get_garden_stock_location(), other)

    def test_settings_fields(self):
        settings = self.env['res.config.settings'].create({})
        self.assertEqual(
            settings.garden_production_location_id, self.env.company.garden_production_location_id,
        )
