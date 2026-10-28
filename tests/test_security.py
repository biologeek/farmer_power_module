from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install')
class TestGardenSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.worker = new_test_user(cls.env, login='garden_worker', groups='odoo_garden.group_garden_worker')
        cls.chef = new_test_user(cls.env, login='garden_chef', groups='odoo_garden.group_garden_chef')
        cls.manager = new_test_user(cls.env, login='garden_manager', groups='odoo_garden.group_garden_manager')
        cls.outsider = new_test_user(cls.env, login='garden_outsider', groups='base.group_user')
        farm = cls.env['garden.farm'].create({'name': 'Ferme'})
        site = cls.env['garden.site'].create({'name': 'Site', 'farm_id': farm.id})
        garden = cls.env['garden.garden'].create({'name': 'Îlot', 'site_id': site.id})
        cls.bed = cls.env['garden.bed'].create({'name': 'Planche', 'garden_id': garden.id})
        cls.species = cls.env['garden.species'].create({'name': 'Espèce sécurité'})
        variety = cls.env['garden.variety'].create({'name': 'V', 'species_id': cls.species.id})
        cls.template = cls.env['garden.crop.template'].create({'name': 'T', 'variety_id': variety.id})

    def test_group_hierarchy(self):
        worker_group = self.env.ref('odoo_garden.group_garden_worker')
        chef_group = self.env.ref('odoo_garden.group_garden_chef')
        manager_group = self.env.ref('odoo_garden.group_garden_manager')
        self.assertIn(worker_group, chef_group.implied_ids)
        self.assertIn(chef_group, manager_group.implied_ids)
        self.assertEqual(worker_group.privilege_id, manager_group.privilege_id)
        self.assertTrue(self.manager.has_group('odoo_garden.group_garden_worker'))
        self.assertFalse(self.worker.has_group('odoo_garden.group_garden_chef'))

    def test_worker_read_only_on_structure_and_catalog(self):
        for record in (self.bed, self.species, self.template):
            self.assertTrue(record.with_user(self.worker).read(['display_name']))
            with self.assertRaises(AccessError):
                record.with_user(self.worker).write({'name': 'X'})
            with self.assertRaises(AccessError):
                record.with_user(self.worker).unlink()
        with self.assertRaises(AccessError):
            self.env['garden.species'].with_user(self.worker).create({'name': 'Interdit'})
        with self.assertRaises(AccessError):
            self.env['garden.operation.type'].with_user(self.worker).create({'name': 'Interdit'})

    def test_worker_can_enter_work(self):
        crop = self.env['garden.crop'].with_user(self.worker).create({
            'template_id': self.template.id, 'bed_id': self.bed.id,
        })
        operation_type = self.env['garden.operation.type'].create({'name': 'Binage'})
        operation = self.env['garden.operation'].with_user(self.worker).create({
            'type_id': operation_type.id, 'crop_ids': [(6, 0, crop.ids)], 'duration': 0.25,
        })
        operation.write({'duration': 0.5})
        self.env['garden.loss'].with_user(self.worker).create({'crop_id': crop.id, 'quantity': 1})
        with self.assertRaises(AccessError):
            operation.unlink()

    def test_chef_manages_catalog_and_structure(self):
        species = self.env['garden.species'].with_user(self.chef).create({'name': 'Chef espèce'})
        species.write({'rotation_years': 2})
        species.unlink()
        self.bed.with_user(self.chef).write({'notes': 'ok'})
        with self.assertRaises(AccessError):
            self.bed.with_user(self.chef).unlink()
        self.bed.with_user(self.manager).unlink()

    def test_user_without_garden_group_has_no_access(self):
        with self.assertRaises(AccessError):
            self.env['garden.bed'].with_user(self.outsider).search([])
