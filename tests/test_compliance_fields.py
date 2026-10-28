from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .test_stock_inputs import GardenStockCase


class GardenComplianceCase(GardenStockCase):
    """Fixtures de conformité (phase 6) : produits phytosanitaire et engrais réglementés, cultures, utilisateurs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_treatment = cls.env.ref('odoo_garden.operation_type_treatment')
        cls.type_fertilization = cls.env.ref('odoo_garden.operation_type_fertilization')
        cls.manager = new_test_user(cls.env, login='garden_comp_manager', groups='odoo_garden.group_garden_manager')
        cls.phyto = cls._storable(
            'Phyto test', garden_input_type='phytosanitary', standard_price=10.0,
            amm_number='AMM-TEST-0001', pre_harvest_interval_days=7,
        )
        cls._set_stock(cls.phyto, 100)
        cls.nitro = cls._storable(
            'Engrais azoté test', garden_input_type='fertilizer', standard_price=1.0, nitrogen_content=10.0,
            is_organic_allowed=True, uom_id=cls.env.ref('uom.product_uom_kgm').id,
        )
        cls._set_stock(cls.nitro, 1000)
        cls.harvest_product = cls._storable('Tomate test')
        cls.variety.harvest_product_id = cls.harvest_product

    def setUp(self):
        super().setUp()
        self.crop = self._crop(planned_sowing_date='2031-03-01')  # 36 m² (planche P12 : 30 x 1,2)

    def _treatment(self, date='2031-06-10', quantity=0.5, crop=None, product=None, **vals):
        """Traitement fait le ``date`` avec un intrant phytosanitaire."""
        crop = crop or self.crop
        operation = self._operation(
            type_id=self.type_treatment.id, crop_ids=[(6, 0, crop.ids)], date=date,
            input_ids=[(0, 0, {'product_id': (product or self.phyto).id, 'quantity': quantity})],
            **vals,
        )
        operation.action_done()
        return operation

    def _harvest(self, date, crop=None, qty=10.0, **vals):
        crop = crop or self.crop
        return self._operation(
            type_id=self.type_harvest.id, crop_ids=[(6, 0, crop.ids)], date=date,
            harvest_product_id=self.harvest_product.id, harvest_qty=qty, **vals,
        )


@tagged('post_install', '-at_install')
class TestGardenComplianceFields(GardenComplianceCase):

    def test_product_fields(self):
        template = self.phyto.product_tmpl_id
        self.assertEqual(template.amm_number, 'AMM-TEST-0001')
        self.assertEqual(template.pre_harvest_interval_days, 7)
        with self.assertRaises(ValidationError):
            self.nitro.product_tmpl_id.nitrogen_content = 120
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.env.cr.savepoint():
            template.pre_harvest_interval_days = -1

    def test_chef_edits_regulatory_fields_only(self):
        template = self.phyto.product_tmpl_id.with_user(self.chef)
        self.assertFalse(template.has_access('write'))
        template.write({'pre_harvest_interval_days': 14, 'amm_number': 'AMM-X'})
        self.assertEqual(template.sudo().pre_harvest_interval_days, 14)
        with self.assertRaises(AccessError):
            template.write({'name': 'Renommé'})
        with self.assertRaises(AccessError):
            template.write({'pre_harvest_interval_days': 3, 'name': 'Renommé'})
        worker_template = self.phyto.product_tmpl_id.with_user(self.worker)
        with self.assertRaises(AccessError):
            worker_template.write({'pre_harvest_interval_days': 1})

    def test_worker_cannot_read_regulatory_fields_in_views(self):
        arch = self.env['product.template'].with_user(self.worker).get_views([(False, 'form')])['views']['form']['arch']
        self.assertNotIn('amm_number', arch)
        arch = self.env['product.template'].with_user(self.chef).get_views([(False, 'form')])['views']['form']['arch']
        self.assertIn('amm_number', arch)

    def test_treated_area_and_dose(self):
        operation = self._operation(
            type_id=self.type_treatment.id, crop_ids=[(6, 0, self.crop.ids)],
            input_ids=[(0, 0, {'product_id': self.phyto.id, 'quantity': 0.36})],
        )
        line = operation.input_ids
        self.assertAlmostEqual(line.treated_area, 36.0)
        self.assertAlmostEqual(line.dose, 100.0)  # 0,36 par 36 m² = 100 par ha
        line.treated_area = 18.0
        self.assertAlmostEqual(line.dose, 200.0)
        bed_operation = self._operation(
            type_id=self.type_treatment.id, scope='bed', bed_ids=[(6, 0, (self.bed | self.bed2).ids)],
            input_ids=[(0, 0, {'product_id': self.phyto.id, 'quantity': 1})],
        )
        self.assertAlmostEqual(bed_operation.input_ids.treated_area, 46.0)
        garden_operation = self._operation(
            type_id=self.type_treatment.id, scope='garden', garden_id=self.garden.id,
            input_ids=[(0, 0, {'product_id': self.phyto.id, 'quantity': 1})],
        )
        self.assertAlmostEqual(garden_operation.input_ids.treated_area, self.garden.area)

    def test_treated_area_frozen_when_done(self):
        operation = self._treatment()
        line = operation.input_ids
        self.assertAlmostEqual(line.treated_area, 36.0)
        self.crop.bed_share = 50
        self.assertAlmostEqual(line.treated_area, 36.0)
        with self.assertRaises(UserError):
            line.treated_area = 10
        operation.action_reset_planned()
        with self.assertRaises(ValidationError):
            line.treated_area = -5
