from ast import literal_eval

from odoo import Command
from odoo.tests import tagged

from .test_stock_harvest import GardenHarvestCase


@tagged('post_install', '-at_install')
class TestGardenTraceability(GardenHarvestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_planting = cls.env.ref('odoo_garden.operation_type_planting')
        cls.customer = cls.env['res.partner'].create({'name': 'Client traçabilité'})
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        # la semence est reçue d'un fournisseur sur le lot SEM-001 (lot créé par la fixture)
        cls.receipt = cls.env['stock.move'].create({
            'origin': 'Réception test', 'product_id': cls.seed.id, 'product_uom': cls.seed.uom_id.id,
            'product_uom_qty': 20, 'location_id': cls.supplier_location.id, 'location_dest_id': cls.stock_location.id,
            'picked': True,
            'move_line_ids': [Command.create({
                'product_id': cls.seed.id, 'product_uom_id': cls.seed.uom_id.id, 'quantity': 20,
                'location_id': cls.supplier_location.id, 'location_dest_id': cls.stock_location.id,
                'lot_id': cls.seed_lot.id, 'picked': True,
            })],
        })
        cls.receipt._action_done()

    def _deliver(self, lot, quantity):
        picking = self.env['stock.picking'].create({
            'partner_id': self.customer.id,
            'picking_type_id': self.warehouse.out_type_id.id,
            'location_id': self.stock_location.id,
            'location_dest_id': self.customer_location.id,
            'move_ids': [Command.create({
                'product_id': self.tomato.id, 'product_uom': self.tomato.uom_id.id, 'product_uom_qty': quantity,
                'location_id': self.stock_location.id, 'location_dest_id': self.customer_location.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.move_line_ids.write({'lot_id': lot.id, 'quantity': quantity})
        picking.move_ids.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        return picking

    def _scenario(self):
        crop = self._crop(planned_sowing_date='2027-03-01')
        sowing = self._done_operation(
            type_id=self.type_sowing.id, crop_ids=[(6, 0, crop.ids)], date='2027-03-01',
            input_ids=[(0, 0, {'product_id': self.seed.id, 'quantity': 4, 'lot_id': self.seed_lot.id})],
        )
        weeding = self._done_operation(
            crop_ids=[(6, 0, crop.ids)], date='2027-04-10',
            input_ids=[(0, 0, {'product_id': self.fertilizer.id, 'quantity': 2})],
        )
        planned = self._operation(crop_ids=[(6, 0, crop.ids)])  # pas faite : absente de la traçabilité
        self._harvest(crop, 20.0, date='2027-06-20')
        lot = crop.lot_ids
        picking = self._deliver(lot, 8.0)
        loss = self.env['garden.loss'].create({
            'crop_id': crop.id, 'stage': 'post_harvest', 'quantity': 2.0, 'cause': 'unsold',
        })
        return crop, lot, sowing, weeding, planned, picking, loss

    def test_lot_traceability_upstream_and_downstream(self):
        crop, lot, sowing, weeding, planned, picking, loss = self._scenario()
        action = lot.action_garden_traceability()
        self.assertEqual(action['res_model'], 'garden.traceability')
        trace = self.env['garden.traceability'].browse(action['res_id'])
        self.assertEqual(trace.lot_id, lot)
        self.assertEqual(trace.crop_id, crop)
        self.assertEqual(trace.product_id, self.tomato)
        self.assertAlmostEqual(trace.on_hand_qty, 10.0)  # 20 récoltés - 8 livrés - 2 rebutés
        # amont
        self.assertEqual(trace.operation_ids, sowing | weeding | self.env['garden.operation'].search([
            ('crop_ids', 'in', crop.id), ('type_id', '=', self.type_harvest.id),
        ]))
        self.assertNotIn(planned, trace.operation_ids)
        self.assertEqual(trace.input_ids.product_id, self.seed | self.fertilizer)
        self.assertEqual(trace.seed_input_ids.product_id, self.seed)
        self.assertEqual(trace.seed_lot_ids, self.seed_lot)
        self.assertEqual(trace.seed_receipt_line_ids.move_id, self.receipt)
        self.assertEqual(len(trace.harvest_line_ids), 1)
        self.assertAlmostEqual(trace.harvest_line_ids.quantity, 20.0)
        # aval : la livraison et le rebut sortent le lot du stock
        out = trace.out_line_ids
        self.assertEqual(len(out), 2)
        delivery_line = out.filtered(lambda l: l.picking_id == picking)
        self.assertAlmostEqual(delivery_line.quantity, 8.0)
        self.assertEqual(delivery_line.picking_partner_id, self.customer)
        self.assertEqual(delivery_line.location_dest_id, self.customer_location)
        scrap_line = out - delivery_line
        self.assertEqual(scrap_line.move_id, loss.scrap_id.move_ids)
        self.assertAlmostEqual(scrap_line.quantity, 2.0)

    def test_crop_traceability_with_several_lots(self):
        crop, lot, *_rest = self._scenario()
        # un second produit récolté sur la même culture : deux lots
        other_product = self._storable('Tomate déclassée (kg)', tracking='lot')
        move = self.env['stock.move'].create({
            'origin': 'Récolte test', 'product_id': other_product.id, 'product_uom': other_product.uom_id.id,
            'product_uom_qty': 3, 'location_id': self.production_location.id,
            'location_dest_id': self.stock_location.id, 'picked': True,
            'garden_crop_id': crop.id, 'garden_kind': 'harvest',
            'move_line_ids': [Command.create({
                'product_id': other_product.id, 'product_uom_id': other_product.uom_id.id, 'quantity': 3,
                'location_id': self.production_location.id, 'location_dest_id': self.stock_location.id,
                'lot_id': self.env['stock.lot'].create({
                    'name': crop.name, 'product_id': other_product.id, 'garden_crop_id': crop.id,
                }).id, 'picked': True,
            })],
        })
        move._action_done()
        self.assertEqual(len(crop.lot_ids), 2)
        action = crop.action_garden_traceability()
        trace = self.env['garden.traceability'].browse(action['res_id'])
        self.assertFalse(trace.lot_id)
        self.assertEqual(trace.lot_ids, crop.lot_ids)
        self.assertEqual(len(trace.harvest_line_ids), 2)
        self.assertEqual(trace.crop_id, crop)

    def test_seed_lot_usage(self):
        crop, *_rest = self._scenario()
        trace = self.env['garden.traceability'].browse(self.seed_lot.action_garden_traceability()['res_id'])
        self.assertFalse(trace.crop_id)
        self.assertEqual(trace.usage_input_ids.operation_id.crop_ids, crop)
        self.assertEqual(trace.usage_input_ids.lot_id, self.seed_lot)
        self.assertEqual(len(trace.out_line_ids), 1)  # sortie vers « Consommation maraîchage »
        self.assertEqual(trace.out_line_ids.location_dest_id, self.consumption_location)

    def test_reopened_operation_leaves_traceability(self):
        crop, lot, sowing, *_rest = self._scenario()
        sowing.action_reset_planned()
        trace = self.env['garden.traceability'].browse(lot.action_garden_traceability()['res_id'])
        self.assertNotIn(sowing, trace.operation_ids)
        self.assertFalse(trace.seed_lot_ids)

    def test_screen_readable_by_garden_users(self):
        crop, lot, *_rest = self._scenario()
        spec = {
            'crop_id': {}, 'lot_id': {}, 'operation_ids': {'fields': {'name': {}}},
            'input_ids': {'fields': {'product_id': {}, 'quantity': {}}},
            'seed_lot_ids': {'fields': {'name': {}}},
            'out_line_ids': {'fields': {'quantity': {}, 'reference': {}, 'picking_partner_id': {}}},
            'usage_input_ids': {'fields': {'product_id': {}}},
        }
        for user in (self.chef, self.worker):
            trace = self.env['garden.traceability'].browse(
                lot.with_user(user).action_garden_traceability()['res_id']).with_user(user)
            data = trace.web_read(spec)[0]
            self.assertTrue(data['out_line_ids'])
            self.assertEqual(data['lot_id'], lot.id)
            # aucun coût dans l'écran
            self.assertFalse({'cost', 'unit_cost', 'labour_cost'} & set(trace.fields_get()))

    def test_buttons_and_menu(self):
        crop, lot, *_rest = self._scenario()
        lot_arch = lot.get_view(self.env.ref('stock.view_production_lot_form').id)['arch']
        self.assertIn('action_garden_traceability', lot_arch)
        crop_arch = crop.get_view(self.env.ref('odoo_garden.view_garden_crop_form').id)['arch']
        for method in ('action_garden_traceability', 'action_view_harvests', 'action_view_lots', 'action_view_losses'):
            self.assertIn(method, crop_arch)
        action = crop.action_view_lots()
        self.assertEqual(self.env['stock.lot'].search(action['domain']), lot)
        harvests = crop.action_view_harvests()
        lines = self.env['stock.move.line'].search(harvests['domain'])
        self.assertEqual(lines.move_id.garden_kind, 'harvest')
        self.assertTrue(self.env.ref('odoo_garden.menu_garden_lots'))
        self.assertIn(lot, self.env['stock.lot'].search(literal_eval(self.env.ref('odoo_garden.action_garden_lots').domain)))
        # le lot affiche sa culture
        self.assertEqual(lot.garden_crop_id, crop)
