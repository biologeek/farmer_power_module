from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .test_operations import GardenOperationCase


class GardenStockCase(GardenOperationCase):
    """Fixtures de stock communes (phase 4) : intrants avec stock initial, utilisateurs, emplacements."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.consumption_location = cls.company.garden_consumption_location_id
        cls.production_location = cls.company.garden_production_location_id
        cls.fertilizer = cls._storable('Engrais test', garden_input_type='fertilizer', standard_price=2.0)
        cls.seed = cls._storable('Semence test', garden_input_type='seed', tracking='lot', standard_price=0.5)
        cls._set_stock(cls.fertilizer, 100)
        cls.seed_lot = cls.env['stock.lot'].create({'name': 'SEM-001', 'product_id': cls.seed.id})
        cls._set_stock(cls.seed, 50, cls.seed_lot)
        cls.worker = new_test_user(cls.env, login='garden_stock_worker', groups='odoo_garden.group_garden_worker')
        cls.chef = new_test_user(cls.env, login='garden_stock_chef', groups='odoo_garden.group_garden_chef')

    @classmethod
    def _storable(cls, name, **vals):
        vals.setdefault('tracking', 'none')
        return cls.env['product.product'].create(dict({'name': name, 'type': 'consu', 'is_storable': True}, **vals))

    @classmethod
    def _set_stock(cls, product, quantity, lot=None, location=None):
        quant = cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': product.id, 'location_id': (location or cls.stock_location).id,
            'inventory_quantity': quantity, 'lot_id': lot.id if lot else False,
        })
        quant.action_apply_inventory()

    def _qty(self, product, lot=None, location=None):
        domain = [('product_id', '=', product.id), ('location_id', '=', (location or self.stock_location).id)]
        if lot:
            domain.append(('lot_id', '=', lot.id))
        return sum(self.env['stock.quant'].search(domain).mapped('quantity'))

    def _done_operation(self, **vals):
        vals.setdefault('date', '2027-04-15')
        operation = self._operation(**vals)
        operation.action_done()
        return operation


@tagged('post_install', '-at_install')
class TestGardenInputs(GardenStockCase):

    def test_input_product_domain_and_type(self):
        template = self.fertilizer.product_tmpl_id
        self.assertEqual(template.garden_input_type, 'fertilizer')
        self.assertTrue(template.is_garden_product)
        found = self.env['product.template'].search([('is_garden_product', '=', True)])
        self.assertIn(template, found)
        plain = self._storable('Produit sans type')
        self.assertNotIn(plain.product_tmpl_id, self.env['product.template'].search([('is_garden_product', '=', True)]))
        self.assertIn(plain.product_tmpl_id, self.env['product.template'].search([('is_garden_product', '=', False)]))

    def test_consumption_creates_move_and_cost(self):
        operation = self._operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 5})])
        line = operation.input_ids
        self.assertEqual(line.uom_id, self.fertilizer.uom_id)
        self.assertAlmostEqual(line.unit_cost, 2.0)
        self.assertAlmostEqual(operation.input_cost, 10.0)
        self.assertFalse(line.move_id)
        self.assertEqual(self._qty(self.fertilizer), 100)  # rien tant que l'opération n'est pas faite
        operation.date = '2027-04-15'
        operation.action_done()
        move = line.move_id
        self.assertEqual(move.state, 'done')
        self.assertEqual(move.location_id, self.stock_location)
        self.assertEqual(move.location_dest_id, self.consumption_location)
        self.assertEqual(move.quantity, 5)
        self.assertEqual(move.garden_kind, 'input')
        self.assertEqual(move.garden_operation_id, operation)
        self.assertEqual(str(move.date.date()), '2027-04-15')
        self.assertTrue(line.consumed)
        self.assertEqual(self._qty(self.fertilizer), 95)
        self.assertEqual(self._qty(self.fertilizer, location=self.consumption_location), 5)
        # le coût est figé à la consommation
        self.fertilizer.standard_price = 9.0
        self.assertAlmostEqual(line.cost, 10.0)
        # idempotent : une nouvelle écriture d'état ne consomme pas deux fois
        operation.write({'state': 'done'})
        self.assertEqual(self._qty(self.fertilizer), 95)
        self.assertEqual(len(operation.move_ids), 1)

    def test_unit_cost_converted_to_line_uom(self):
        gram = self.env['uom.uom'].create({
            'name': 'g test', 'relative_uom_id': self.fertilizer.uom_id.id, 'relative_factor': 0.001,
        })
        operation = self._operation(input_ids=[(0, 0, {
            'product_id': self.fertilizer.id, 'quantity': 500, 'uom_id': gram.id,
        })])
        self.assertAlmostEqual(operation.input_ids.unit_cost, 0.002)
        self.assertAlmostEqual(operation.input_cost, 1.0)
        operation.date = '2027-04-15'
        operation.action_done()
        self.assertEqual(self._qty(self.fertilizer), 99.5)

    def test_reopen_reverses_and_redo_consumes_again(self):
        operation = self._done_operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 4})])
        first = operation.input_ids.move_id
        self.assertEqual(self._qty(self.fertilizer), 96)
        operation.action_reset_planned()
        self.assertEqual(self._qty(self.fertilizer), 100)
        self.assertFalse(operation.input_ids.consumed)
        reverse = first.garden_reversal_ids
        self.assertEqual(len(reverse), 1)
        self.assertEqual(reverse.garden_kind, 'input_return')
        self.assertEqual((reverse.location_id, reverse.location_dest_id), (self.consumption_location, self.stock_location))
        self.assertEqual(first.state, 'done')  # l'historique n'est pas supprimé
        operation.action_reset_planned()  # idempotent
        self.assertEqual(self._qty(self.fertilizer), 100)
        operation.action_done()
        self.assertEqual(self._qty(self.fertilizer), 96)
        self.assertNotEqual(operation.input_ids.move_id, first)
        self.assertTrue(operation.input_ids.consumed)

    def test_cancel_planned_operation_touches_no_stock(self):
        operation = self._operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 4})])
        operation.action_cancel()
        self.assertFalse(operation.move_ids)
        self.assertEqual(self._qty(self.fertilizer), 100)

    def test_lot_tracked_input(self):
        operation = self._operation(input_ids=[(0, 0, {'product_id': self.seed.id, 'quantity': 3})])
        with self.assertRaises(UserError):
            operation.action_done()  # lot obligatoire
        self.assertEqual(operation.state, 'planned')
        operation.input_ids.lot_id = self.seed_lot
        operation.action_done()
        self.assertEqual(operation.input_ids.move_id.move_line_ids.lot_id, self.seed_lot)
        self.assertEqual(self._qty(self.seed, self.seed_lot), 47)
        # le lot doit être celui du produit
        other_lot = self.env['stock.lot'].create({
            'name': 'AUTRE', 'product_id': self._storable('Autre semence', tracking='lot').id,
        })
        with self.assertRaises(ValidationError):
            operation.action_reset_planned()
            operation.input_ids.lot_id = other_lot

    def test_input_quantity_must_be_positive(self):
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.cr.savepoint():
            self._operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 0})])

    def test_done_operation_inputs_are_locked(self):
        operation = self._done_operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 1})])
        with self.assertRaises(UserError):
            operation.input_ids.quantity = 2
        with self.assertRaises(UserError):
            operation.write({'input_ids': [(0, 0, {'product_id': self.fertilizer.id, 'quantity': 1})]})
        with self.assertRaises(UserError):
            operation.input_ids.unlink()
        operation.action_reset_planned()
        operation.input_ids.quantity = 2  # de nouveau modifiable
        operation.action_done()
        self.assertEqual(self._qty(self.fertilizer), 98)

    def test_deleting_done_operation_reverses_stock(self):
        operation = self._done_operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 6})])
        self.assertEqual(self._qty(self.fertilizer), 94)
        moves = operation.move_ids
        operation.sudo().unlink()
        self.assertEqual(self._qty(self.fertilizer), 100)
        self.assertEqual(len(moves.exists()), 1)

    def test_input_cost_allocated_to_crops(self):
        big = self._crop(planned_sowing_date='2027-03-01')  # 36 m²
        small = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')  # 10 m²
        operation = self._done_operation(
            crop_ids=[(6, 0, (big | small).ids)],
            input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 23})],
        )
        self.assertAlmostEqual(operation.input_cost, 46.0)
        by_crop = {a.crop_id: a for a in operation.allocation_ids}
        self.assertAlmostEqual(by_crop[big].input_cost, 46.0 * 36 / 46)
        self.assertAlmostEqual(by_crop[small].input_cost, 10.0)
        self.assertAlmostEqual(big.input_cost, 36.0)
        self.assertAlmostEqual(small.input_cost, 10.0)
        operation.action_reset_planned()
        self.assertAlmostEqual(big.input_cost, 0.0)

    def test_missing_locations_raise(self):
        operation = self._operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 1})])
        self.company.sudo().garden_consumption_location_id = False
        with self.assertRaises(UserError):
            operation.action_done()

    def test_custom_stock_location(self):
        cold = self.env['stock.location'].create({
            'name': 'Local intrants', 'usage': 'internal', 'company_id': self.company.id,
        })
        self._set_stock(self.fertilizer, 10, location=cold)
        self.company.garden_stock_location_id = cold
        self._done_operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 4})])
        self.assertEqual(self._qty(self.fertilizer, location=cold), 6)
        self.assertEqual(self._qty(self.fertilizer), 100)

    def test_worker_records_inputs_without_stock_access(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        worker_op = self.env['garden.operation'].with_user(self.worker).create({
            'type_id': self.type_weeding.id, 'crop_ids': [(6, 0, crop.ids)], 'date': '2027-04-15',
            'input_ids': [(0, 0, {'product_id': self.fertilizer.id, 'quantity': 2})],
        })
        worker_op.action_done()
        self.assertEqual(worker_op.sudo().input_ids.move_id.state, 'done')
        self.assertEqual(self._qty(self.fertilizer), 98)
        worker_op.action_reset_planned()
        self.assertEqual(self._qty(self.fertilizer), 100)
        # mais aucun droit direct sur les mouvements, les lots ou le stock
        Move = self.env['stock.move'].with_user(self.worker)
        with self.assertRaises(AccessError):
            Move.search([])
        with self.assertRaises(AccessError):
            Move.create({
                'name': 'x', 'product_id': self.fertilizer.id, 'product_uom': self.fertilizer.uom_id.id,
                'product_uom_qty': 1, 'location_id': self.stock_location.id,
                'location_dest_id': self.consumption_location.id,
            })
        with self.assertRaises(AccessError):
            self.env['stock.scrap'].with_user(self.worker).create({'product_id': self.fertilizer.id, 'scrap_qty': 1})
        with self.assertRaises(AccessError):
            self.env['stock.quant'].with_user(self.worker).create({
                'product_id': self.fertilizer.id, 'location_id': self.stock_location.id, 'quantity': 5,
            })
        with self.assertRaises(AccessError):
            self.seed_lot.with_user(self.worker).write({'ref': 'x'})
        with self.assertRaises(AccessError):
            self.env['stock.lot'].with_user(self.worker).create({'name': 'X', 'product_id': self.seed.id})
        # lecture seule des lots (choix du lot d'un intrant)
        self.assertTrue(self.seed_lot.with_user(self.worker).read(['name']))

    def test_input_costs_hidden_from_worker(self):
        operation = self._operation(input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 2})])
        as_worker = operation.with_user(self.worker)
        for record, fname in (
            (as_worker, 'input_cost'), (as_worker.input_ids, 'cost'), (as_worker.input_ids, 'unit_cost'),
        ):
            with self.assertRaises(AccessError, msg=fname):
                record.read([fname])
        self.assertTrue(as_worker.input_ids.read(['quantity', 'product_id']))
        for model in ('garden.operation', 'garden.operation.input', 'garden.operation.allocation', 'garden.crop'):
            self.assertFalse({'input_cost', 'cost', 'unit_cost'} & set(self.env[model].with_user(self.worker).fields_get()))
        arch = as_worker.get_view(as_worker.env.ref('odoo_garden.view_garden_operation_form').id)['arch']
        self.assertNotIn('input_cost', arch)
        self.assertNotIn('unit_cost', arch)
        as_chef = operation.with_user(self.chef)
        self.assertAlmostEqual(as_chef.read(['input_cost'])[0]['input_cost'], 4.0)
        self.assertAlmostEqual(as_chef.input_ids.read(['cost'])[0]['cost'], 4.0)
