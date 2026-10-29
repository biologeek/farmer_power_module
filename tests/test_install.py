from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestGardenInstall(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.farm = cls.env['garden.farm'].create({'name': 'Ferme test'})
        cls.site = cls.env['garden.site'].create({'name': 'Site test', 'farm_id': cls.farm.id})
        cls.garden = cls.env['garden.garden'].create({'name': 'Îlot test', 'site_id': cls.site.id})
        cls.bed = cls.env['garden.bed'].create({'name': 'Planche test', 'garden_id': cls.garden.id})
        cls.species = cls.env['garden.species'].create({'name': 'Tomate (test)', 'family': 'solanaceae'})
        cls.variety = cls.env['garden.variety'].create({'name': 'Coeur de boeuf', 'species_id': cls.species.id})
        cls.template = cls.env['garden.crop.template'].create({'name': 'Tomate', 'variety_id': cls.variety.id})
        cls.crop = cls.env['garden.crop'].create({
            'template_id': cls.template.id,
            'bed_id': cls.bed.id,
            'date_start': '2026-03-01',
            'date_end': '2026-08-01',
        })
        cls.operation_type = cls.env['garden.operation.type'].create({'name': 'Arrosage (test)'})
        cls.operation = cls.env['garden.operation'].create({
            'type_id': cls.operation_type.id,
            'scope': 'crop',
            'crop_ids': [(6, 0, cls.crop.ids)],
            'planned_date': '2026-04-01',
            'date': '2026-04-01',
            'duration': 0.5,
        })

    def test_operation_links(self):
        self.assertEqual(self.operation.garden_main_id, self.garden)
        self.assertEqual(self.crop.operation_ids, self.operation)
        self.assertIn(self.crop.name, self.operation.name)

    def test_occupancy_data(self):
        data = self.env['garden.bed'].get_occupancy_data([])
        self.assertIn('beds', data)
        self.assertIn('start_date', data)
        self.assertIn('end_date', data)
        bed_data = next(b for b in data['beds'] if b['id'] == self.bed.id)
        self.assertEqual(len(bed_data['crops']), 1)
        self.assertEqual(bed_data['crops'][0]['id'], self.crop.id)
        # domain=None doit aussi fonctionner
        self.assertIn('beds', self.env['garden.bed'].get_occupancy_data(None))

    def test_old_statistics_screens_removed(self):
        tags = self.env['ir.actions.client'].search([('tag', 'like', 'garden_%')]).mapped('tag')
        self.assertCountEqual(tags, ['garden_analytics'] * 5 + ['garden_bed_occupancy', 'garden_dashboard'])
        for xmlid in (
            'action_garden_statistics', 'action_garden_statistics_charts', 'action_garden_production_statistics',
            'menu_garden_statistics_graphics', 'menu_garden_production_statistics',
        ):
            self.assertFalse(self.env.ref('odoo_garden.' + xmlid, raise_if_not_found=False), xmlid)
        self.assertFalse(hasattr(self.env['garden.crop'], 'get_production_statistics_data'))
        self.assertFalse(hasattr(self.env['garden.operation.allocation'], 'get_statistics_data'))
        self.assertTrue(self.env.ref('odoo_garden.menu_garden_time_statistics'))

    def test_farm_action_xmlid(self):
        self.assertTrue(self.env.ref('odoo_garden.action_garden_farm'))

    def test_action_method_removed_from_operation_model(self):
        self.assertFalse(hasattr(self.env['garden.operation'], 'get_production_statistics_data'))

    def test_removed_models(self):
        for model in (
            'garden.plot', 'garden.culture.mode', 'garden.crop.catalog',
            'garden.action', 'garden.action.type', 'garden.postprocess',
        ):
            self.assertNotIn(model, self.env)
