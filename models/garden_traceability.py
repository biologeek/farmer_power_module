from odoo import api, fields, models

SEED_CATEGORIES = ('sowing', 'transplanting', 'planting')
SEED_TYPES = ('seed', 'plant')


class GardenTraceability(models.TransientModel):
    _name = 'garden.traceability'
    _description = "Traçabilité d'un lot ou d'une culture"
    # Écran de traçabilité en lecture seule, construit avec l'ORM (aucune vue SQL) :
    # - amont : culture, opérations faites, intrants, lots de semence ou de plant utilisés (et leur réception) ;
    # - aval : mouvements de sortie du lot (livraisons, ventes, rebuts...) lus dans `stock.move.line`,
    #   sans dépendre du module Ventes.
    # Les champs sont calculés en `sudo()` : l'écran s'ouvre depuis les boutons « Traçabilité » du lot et de la culture.

    lot_id = fields.Many2one('stock.lot', string='Lot', readonly=True, ondelete='cascade')
    crop_id = fields.Many2one(
        'garden.crop', string='Culture', compute='_compute_crop_id', store=True, readonly=False, ondelete='cascade',
        help="Culture d'origine du lot ; sans lot choisi, tous les lots de récolte de la culture sont tracés.",
    )
    product_id = fields.Many2one('product.product', string='Produit', compute='_compute_lots')
    lot_ids = fields.Many2many('stock.lot', string='Lots tracés', compute='_compute_lots')
    on_hand_qty = fields.Float('En stock', compute='_compute_lots', digits='Product Unit')
    operation_ids = fields.Many2many(
        'garden.operation', string='Opérations faites', compute='_compute_upstream',
        help="Opérations faites sur la culture (directement ou par la répartition d'une planche ou d'un îlot).",
    )
    input_ids = fields.Many2many(
        'garden.operation.input', string='Intrants consommés', compute='_compute_upstream',
        help="Intrants des opérations faites de la culture.",
    )
    seed_input_ids = fields.Many2many(
        'garden.operation.input', string='Semences et plants', compute='_compute_upstream',
        help="Intrants de type semence ou plant des opérations de semis, repiquage ou plantation.",
    )
    seed_lot_ids = fields.Many2many(
        'stock.lot', string='Lots de semence ou de plant', compute='_compute_upstream',
        help="Lots fournisseur des semences et plants utilisés (traçabilité amont).",
    )
    seed_receipt_line_ids = fields.Many2many(
        'stock.move.line', string='Réception des lots de semence', compute='_compute_upstream',
        help="Entrées de ces lots depuis un fournisseur.",
    )
    harvest_line_ids = fields.Many2many(
        'stock.move.line', string='Entrées en stock (récolte)', compute='_compute_upstream',
    )
    out_line_ids = fields.Many2many(
        'stock.move.line', string='Sorties du lot', compute='_compute_downstream',
        help="Mouvements terminés qui sortent le lot du stock (livraison, vente, rebut...).",
    )
    usage_input_ids = fields.Many2many(
        'garden.operation.input', string='Consommé par les opérations', compute='_compute_downstream',
        help="Opérations qui ont consommé ce lot comme intrant (lot de semence, d'engrais...).",
    )

    @api.depends('lot_id')
    def _compute_crop_id(self):
        for trace in self:
            trace.crop_id = trace.lot_id.garden_crop_id or trace.crop_id

    def _get_lots(self):
        self.ensure_one()
        return (self.lot_id or self.crop_id.lot_ids).sudo()

    @api.depends('lot_id', 'crop_id')
    def _compute_lots(self):
        for trace in self:
            lots = trace._get_lots()
            trace.lot_ids = lots
            trace.product_id = lots.product_id[:1]
            trace.on_hand_qty = sum(lots.mapped('product_qty'))

    @api.depends('lot_id', 'crop_id')
    def _compute_upstream(self):
        Operation = self.env['garden.operation'].sudo()
        Line = self.env['stock.move.line'].sudo()
        for trace in self:
            crop = trace.crop_id.sudo()
            operations = Operation.search(
                crop._get_operations_domain() + [('state', '=', 'done')], order='date, id',
            ) if crop else Operation
            inputs = operations.input_ids
            seed_inputs = inputs.filtered(
                lambda i: i.operation_id.category in SEED_CATEGORIES and i.garden_input_type in SEED_TYPES
            )
            seed_lots = seed_inputs.lot_id
            trace.operation_ids = operations
            trace.input_ids = inputs
            trace.seed_input_ids = seed_inputs
            trace.seed_lot_ids = seed_lots
            trace.seed_receipt_line_ids = Line.search([
                ('lot_id', 'in', seed_lots.ids), ('state', '=', 'done'), ('location_id.usage', '=', 'supplier'),
            ], order='date, id') if seed_lots else Line
            lots = trace._get_lots()
            trace.harvest_line_ids = Line.search([
                ('lot_id', 'in', lots.ids), ('state', '=', 'done'), ('move_id.garden_kind', '=', 'harvest'),
            ], order='date, id') if lots else Line

    @api.depends('lot_id', 'crop_id')
    def _compute_downstream(self):
        Line = self.env['stock.move.line'].sudo()
        Input = self.env['garden.operation.input'].sudo()
        for trace in self:
            lots = trace._get_lots()
            trace.out_line_ids = Line.search([
                ('lot_id', 'in', lots.ids), ('state', '=', 'done'),
                ('location_id.usage', '=', 'internal'), ('location_dest_id.usage', '!=', 'internal'),
            ], order='date, id') if lots else Line
            trace.usage_input_ids = Input.search([
                ('lot_id', 'in', lots.ids), ('operation_id.state', '=', 'done'),
            ]) if lots else Input

    # ------------------------------------------------------------------
    @api.model
    def _open(self, lot=None, crop=None):
        """Crée l'écran de traçabilité d'un lot (ou d'une culture) et retourne l'action qui l'ouvre."""
        vals = {}
        if lot:
            vals['lot_id'] = lot.id
        if crop:
            vals['crop_id'] = crop.id
            if not lot and len(crop.sudo().lot_ids) == 1:
                vals['lot_id'] = crop.sudo().lot_ids.id
        trace = self.create(vals)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Traçabilité"),
            'res_model': 'garden.traceability',
            'res_id': trace.id,
            'view_mode': 'form',
            'target': 'current',
        }


class StockLot(models.Model):
    _inherit = 'stock.lot'

    def action_garden_traceability(self):
        """Bouton « Traçabilité maraîchage » du lot."""
        self.ensure_one()
        return self.env['garden.traceability']._open(lot=self)
