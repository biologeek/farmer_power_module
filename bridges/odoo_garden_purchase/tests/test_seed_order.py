from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.odoo_garden.tests.test_planning import GardenPlanningCase


@tagged('post_install', '-at_install')
class TestGardenSeedOrder(GardenPlanningCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier = cls.env['res.partner'].create({'name': 'Seed Supplier A'})
        cls.supplier_b = cls.env['res.partner'].create({'name': 'Seed Supplier B'})
        cls.gram = cls.env.ref('uom.product_uom_gram')
        cls.kilogram = cls.env.ref('uom.product_uom_kgm')
        cls.unit = cls.env.ref('uom.product_uom_unit')
        cls.seed_tomato = cls._product('Tomato seed', cls.gram)
        cls.seed_cabbage = cls._product('Cabbage seed', cls.unit)
        cls.variety.write({'supplier_id': cls.supplier.id, 'seed_product_id': cls.seed_tomato.id})
        cls.variety_cabbage.write({'supplier_id': cls.supplier.id, 'seed_product_id': cls.seed_cabbage.id})
        cls.chef = new_test_user(cls.env, login='garden_purchase_chef', groups='odoo_garden.group_garden_chef')
        cls.manager = new_test_user(cls.env, login='garden_purchase_manager', groups='odoo_garden.group_garden_manager')
        # tomato: 36 m2 x 4 plants = 144 plants -> 216 seeds -> 0.72 g ; cabbage: 36 m2 x 5 = 180 -> 216 seeds
        base = {'season_id': cls.season.id, 'planned_sowing_date': '2027-03-01'}
        cls.crop_tomato = cls.env['garden.crop'].create(dict(base, template_id=cls.template.id, bed_id=cls.bed.id))
        cls.crop_cabbage = cls.env['garden.crop'].create(dict(base, template_id=cls.template_direct.id, bed_id=cls.bed2.id))

    @classmethod
    def _product(cls, name, uom):
        return cls.env['product.product'].create({'name': name, 'type': 'consu', 'uom_id': uom.id})

    def _wizard(self, user=None, **vals):
        vals.setdefault('season_id', self.season.id)
        return self.env['garden.seed.order.wizard'].with_user(user or self.env.user).create(vals)

    def _orders(self):
        return self.env['purchase.order'].search([('garden_season_id', '=', self.season.id)])

    def test_one_draft_order_per_supplier_one_line_per_variety(self):
        self.variety_cabbage.supplier_id = self.supplier_b
        self._wizard().action_create_rfq()
        orders = self._orders()
        self.assertEqual(len(orders), 2)
        self.assertEqual(set(orders.mapped('state')), {'draft'})
        self.assertEqual(orders.mapped('partner_id'), self.supplier | self.supplier_b)
        order_a = orders.filtered(lambda o: o.partner_id == self.supplier)
        self.assertEqual(len(order_a.order_line), 1)
        line = order_a.order_line
        self.assertEqual(line.product_id, self.seed_tomato)
        self.assertEqual(line.product_uom_id, self.gram)
        self.assertAlmostEqual(line.product_qty, 0.72)
        self.assertEqual(line.garden_variety_id, self.variety)
        self.assertEqual(line.garden_season_id, self.season)

    def test_same_supplier_gives_one_order_with_two_lines(self):
        self._wizard().action_create_rfq()
        orders = self._orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.order_line.product_id, self.seed_tomato | self.seed_cabbage)
        cabbage_line = orders.order_line.filtered(lambda l: l.product_id == self.seed_cabbage)
        self.assertEqual(cabbage_line.product_qty, 60.0)  # 10 m2 x 5 plants x 1.2 margin, in seeds

    def test_weight_unit_is_converted(self):
        self.seed_tomato.uom_id = self.kilogram
        self._wizard().action_create_rfq()
        line = self._orders().order_line.filtered(lambda l: l.product_id == self.seed_tomato)
        self.assertEqual(line.product_uom_id, self.kilogram)
        self.assertAlmostEqual(line.product_qty, 0.01)  # 0.00072 kg rounded up to the unit precision

    def test_missing_supplier_and_product_are_skipped_with_warning(self):
        self.variety_cabbage.supplier_id = False
        wizard = self._wizard()
        self.assertIn(self.variety_cabbage.display_name, wizard.preview)
        wizard.action_create_rfq()
        self.assertEqual(self._orders().order_line.product_id, self.seed_tomato)
        self.assertIn('no supplier', wizard.result)
        self.assertIn(self.variety_cabbage.display_name, wizard.result)
        self.variety.seed_product_id = False
        wizard2 = self._wizard(season_id=self.season.id)
        items, warnings = wizard2._get_requirements()
        self.assertTrue(any('no seed product' in w for w in warnings))
        self.assertFalse([i for i in items if i['variety'] == self.variety])

    def test_unsupported_unit_is_skipped(self):
        self.seed_cabbage.uom_id = self.env.ref('uom.product_uom_hour')
        items, warnings = self._wizard()._get_requirements()
        self.assertTrue(any('neither a weight nor a unit' in w for w in warnings))
        self.assertEqual([i['variety'] for i in items], [self.variety])

    def test_idempotent_and_only_missing_quantity(self):
        self._wizard().action_create_rfq()
        self.assertEqual(len(self._orders()), 1)
        again = self._wizard()
        again.action_create_rfq()
        self.assertEqual(len(self._orders()), 1)
        self.assertIn('0 request(s)', again.result)
        self.assertIn('Already requested', again.result)
        # a new crop increases the need of tomatoes only: only the difference is requested
        self._crop(bed_id=self.bed2.id, bed_share=50, planned_sowing_date='2027-04-01')  # 5 m2 -> 20 plants -> 30 seeds
        third = self._wizard()
        third.action_create_rfq()
        orders = self._orders()
        self.assertEqual(len(orders), 2)
        new_order = orders.sorted('id')[-1]
        self.assertEqual(len(new_order.order_line), 1)
        self.assertEqual(new_order.order_line.product_id, self.seed_tomato)
        self.assertAlmostEqual(new_order.order_line.product_qty, 0.10)

    def test_cancelled_order_does_not_count_as_ordered(self):
        self._wizard().action_create_rfq()
        self._orders().button_cancel()
        self._wizard().action_create_rfq()
        self.assertEqual(len(self._orders().filtered(lambda o: o.state == 'draft')), 1)

    def test_bought_plants(self):
        plant = self._product('Tomato plant', self.unit)
        self.template.write({'propagation': 'bought_plants', 'plant_product_id': plant.id})
        wizard = self._wizard()
        wizard.action_create_rfq()
        lines = self._orders().order_line
        self.assertIn(plant, lines.product_id)
        self.assertEqual(lines.filtered(lambda l: l.product_id == plant).product_qty, 144.0)
        self.assertNotIn(self.seed_tomato, lines.product_id)
        # without the option, plants are ignored
        self._orders().button_cancel()
        wizard = self._wizard(include_plants=False)
        wizard.action_create_rfq()
        self.assertNotIn(plant, self._orders().filtered(lambda o: o.state == 'draft').order_line.product_id)

    def test_other_season_is_not_mixed(self):
        other = self.env['garden.season'].create({'name': 'Other season', 'date_start': '2028-01-01', 'date_end': '2028-12-31'})
        self._crop(season_id=other.id, planned_sowing_date='2028-03-01')
        self._wizard().action_create_rfq()
        self.assertEqual(len(self.env['purchase.order'].search([('garden_season_id', '=', other.id)])), 0)

    def test_crop_manager_without_purchase_access(self):
        with self.assertRaises(AccessError):
            self.env['purchase.order'].with_user(self.chef).search([])
        wizard = self._wizard(user=self.chef)
        wizard.action_create_rfq()
        self.assertEqual(wizard.state, 'done')
        orders = self._orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.create_uid, self.chef)
        with self.assertRaises(AccessError):
            orders.with_user(self.chef).read(['name'])
        self.assertIn(orders.name, wizard.result)
        self.assertFalse(wizard.sudo().purchase_order_ids)

    def test_manager_and_worker_access(self):
        wizard = self._wizard(user=self.manager)
        wizard.action_create_rfq()
        self.assertEqual(wizard.state, 'done')
        worker = new_test_user(self.env, login='garden_purchase_worker', groups='odoo_garden.group_garden_worker')
        with self.assertRaises(AccessError):
            self.env['garden.seed.order.wizard'].with_user(worker).create({'season_id': self.season.id})
