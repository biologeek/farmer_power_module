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
            'quantity_harvested': 12.5,
            'value_harvested': 50.0,
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

    def test_operation_statistics(self):
        self.operation.action_done()
        data = self.env['garden.operation.allocation'].get_statistics_data()
        self.assertIn('pie', data)
        self.assertIn('stacked', data)
        self.assertIn('categories', data['stacked'])
        self.assertIn('series', data['stacked'])
        self.assertIn('Arrosage (test)', [p.get('label') or p.get('name') for p in data['pie']])

    def test_production_statistics(self):
        data = self.env['garden.crop'].get_production_statistics_data()
        for key in ('month_totals', 'bed_totals', 'crop_totals'):
            self.assertIn(key, data)
        self.assertIn('Planche test', [b['bed'] for b in data['bed_totals']])
        self.assertIn('Tomate', [c['crop'] for c in data['crop_totals']])

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
