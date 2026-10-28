from psycopg2 import IntegrityError

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestGardenStructure(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.farm = cls.env['garden.farm'].create({'name': 'Ferme'})
        cls.site = cls.env['garden.site'].create({'name': 'Site', 'farm_id': cls.farm.id})
        cls.garden = cls.env['garden.garden'].create({
            'name': 'Îlot A', 'code': 'A', 'site_id': cls.site.id,
            'irrigation_type': 'drip', 'irrigation_flow': 500,
        })

    def _bed(self, **vals):
        vals.setdefault('name', 'Planche')
        vals.setdefault('garden_id', self.garden.id)
        return self.env['garden.bed'].create(vals)

    def test_company_inherited(self):
        self.assertEqual(self.farm.company_id, self.env.company)
        bed = self._bed()
        self.assertEqual(self.site.company_id, self.farm.company_id)
        self.assertEqual(self.garden.company_id, self.farm.company_id)
        self.assertEqual(bed.company_id, self.farm.company_id)
        self.assertEqual(bed.site_id, self.site)

    def test_areas(self):
        bed1 = self._bed(name='P1', length=30, width=1.2)
        self._bed(name='P2', length=10, width=1)
        self.assertAlmostEqual(bed1.area, 36.0)
        self.assertAlmostEqual(self.garden.area, 46.0)
        bed1.width = 1.0
        self.assertAlmostEqual(self.garden.area, 40.0)

    def test_bed_code_unique_per_site(self):
        self._bed(code='P01')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self._bed(name='Doublon', code='P01')
        # même code sur un autre site : autorisé
        site2 = self.env['garden.site'].create({'name': 'Site 2', 'farm_id': self.farm.id})
        garden2 = self.env['garden.garden'].create({'name': 'Îlot B', 'site_id': site2.id})
        self.assertTrue(self._bed(name='Autre', code='P01', garden_id=garden2.id))
        # plusieurs planches sans code : autorisé
        self._bed(name='Sans code 1')
        self._bed(name='Sans code 2')

    def test_archive(self):
        bed = self._bed()
        bed.active = False
        self.assertFalse(self.env['garden.bed'].search([('id', '=', bed.id)]))
        self.assertTrue(self.env['garden.bed'].with_context(active_test=False).search([('id', '=', bed.id)]))

    def test_current_crops(self):
        species = self.env['garden.species'].create({'name': 'Test espèce'})
        variety = self.env['garden.variety'].create({'name': 'V', 'species_id': species.id})
        template = self.env['garden.crop.template'].create({'name': 'T', 'variety_id': variety.id})
        bed = self._bed()
        Crop = self.env['garden.crop']
        past = Crop.create({'template_id': template.id, 'bed_id': bed.id,
                            'date_start': '2000-01-01', 'date_end': '2000-06-01'})
        current = Crop.create({'template_id': template.id, 'bed_id': bed.id,
                               'date_start': '2000-01-01', 'date_end': '2999-01-01'})
        open_ended = Crop.create({'template_id': template.id, 'bed_id': bed.id, 'date_start': '2000-01-01'})
        future = Crop.create({'template_id': template.id, 'bed_id': bed.id, 'date_start': '2999-01-01'})
        self.assertEqual(bed.crop_ids, past | current | open_ended | future)
        self.assertEqual(bed.current_crop_ids, current | open_ended)
        self.assertEqual(current.company_id, bed.company_id)
        self.assertEqual(current.variety_id, variety)
        self.assertEqual(current.species_id, species)

    def test_multi_company_rule(self):
        company2 = self.env['res.company'].create({'name': 'Autre société'})
        farm2 = self.env['garden.farm'].create({'name': 'Ferme 2', 'company_id': company2.id})
        site2 = self.env['garden.site'].create({'name': 'S2', 'farm_id': farm2.id})
        garden2 = self.env['garden.garden'].create({'name': 'G2', 'site_id': site2.id})
        bed2 = self._bed(name='B2', garden_id=garden2.id)
        self.assertEqual(bed2.company_id, company2)
        user = self.env['res.users'].create({
            'name': 'Chef', 'login': 'chef_multi', 'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'group_ids': [(6, 0, [self.env.ref('odoo_garden.group_garden_chef').id])],
        })
        for record in (farm2, site2, garden2, bed2):
            self.assertFalse(record.with_user(user).search([('id', '=', record.id)]), record._name)
        self.assertTrue(self.farm.with_user(user).search([('id', '=', self.farm.id)]))
