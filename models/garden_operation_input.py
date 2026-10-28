from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class GardenOperationInput(models.Model):
    _name = 'garden.operation.input'
    _description = "Intrant consommé par une opération"
    _order = 'operation_id, sequence, id'
    # Une ligne par produit consommé (semence, plant, engrais, traitement...). Quand l'opération passe à
    # « faite », un mouvement de stock part de l'emplacement de stockage vers « Consommation maraîchage ».

    sequence = fields.Integer('Séquence', default=10)
    operation_id = fields.Many2one(
        'garden.operation', string='Opération', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Société', related='operation_id.company_id', store=True, index=True,
    )
    operation_state = fields.Selection(related='operation_id.state', string="État de l'opération")
    product_id = fields.Many2one(
        'product.product', string='Produit', required=True, index=True, ondelete='restrict',
        domain="[('garden_input_type', '!=', False)]",
        help="Produit consommé. Seuls les produits dont le « type d'intrant maraîcher » est renseigné sont proposés.",
    )
    garden_input_type = fields.Selection(related='product_id.garden_input_type', string="Type d'intrant", store=True)
    tracking = fields.Selection(related='product_id.tracking', string='Suivi')
    quantity = fields.Float(
        'Quantité', digits='Product Unit', default=1.0, required=True,
        help="Quantité consommée, dans l'unité de la ligne.",
    )
    uom_id = fields.Many2one(
        'uom.uom', string='Unité', compute='_compute_uom_id', store=True, readonly=False, precompute=True,
        required=True, help="Unité de la quantité (proposée d'après le produit).",
    )
    lot_id = fields.Many2one(
        'stock.lot', string='Lot', domain="[('product_id', '=', product_id)]", ondelete='restrict',
        help="Lot du produit consommé, obligatoire pour un produit suivi par lots (ex. lot de semences).",
    )
    move_id = fields.Many2one(
        'stock.move', string='Mouvement de stock', copy=False, readonly=True, index='btree_not_null',
        ondelete='set null',
        help="Dernier mouvement de consommation créé à la validation de l'opération.",
    )
    consumed = fields.Boolean(
        'Consommé', compute='_compute_consumed',
        help="Vrai si un mouvement de consommation est en vigueur (non annulé par un mouvement inverse).",
    )
    unit_cost = fields.Float(
        'Coût unitaire', compute='_compute_unit_cost', store=True, readonly=False, digits=(16, 5),
        groups='odoo_garden.group_garden_chef',
        help="Coût du produit par unité de la ligne. Proposé d'après le coût du produit ; "
             "figé au moment où l'opération est faite.",
    )
    cost = fields.Float(
        'Coût', compute='_compute_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help="Quantité × coût unitaire.",
    )

    _quantity_positive = models.Constraint(
        'CHECK (quantity > 0)', "La quantité d'un intrant doit être strictement positive.",
    )

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id

    @api.depends('move_id.garden_reversal_ids')
    def _compute_consumed(self):
        for line in self:
            line.consumed = bool(line.move_id and not line.move_id.garden_reversal_ids)

    def _get_product_cost(self):
        """Coût du produit par unité de la ligne (coût standard de la société de l'opération)."""
        self.ensure_one()
        product = self.product_id.sudo().with_company(self.operation_id.company_id or self.env.company)
        return product.uom_id._compute_price(product.standard_price, self.uom_id or product.uom_id)

    @api.depends('product_id', 'uom_id')
    def _compute_unit_cost(self):
        # volontairement sans dépendance au coût du produit : il est figé quand l'opération est faite
        for line in self:
            line.unit_cost = line._get_product_cost() if line.product_id else 0.0

    @api.depends('quantity', 'unit_cost')
    def _compute_cost(self):
        for line in self:
            line.cost = line.quantity * line.unit_cost

    @api.constrains('product_id', 'lot_id')
    def _check_lot_product(self):
        for line in self:
            if line.lot_id and line.lot_id.product_id != line.product_id:
                raise ValidationError(self.env._("Le lot « %(lot)s » n'est pas un lot du produit « %(product)s ».",
                                                 lot=line.lot_id.name, product=line.product_id.display_name))

    # ------------------------------------------------------------------
    # Verrou : les lignes d'une opération faite ne se modifient plus
    # ------------------------------------------------------------------
    _LOCKED_FIELDS = {'product_id', 'quantity', 'uom_id', 'lot_id', 'operation_id'}

    def _check_operation_open(self, operations=None):
        for operation in (operations or self.operation_id):
            if operation.state == 'done':
                raise UserError(self.env._(
                    "L'opération « %s » est faite : remettez-la en planifiée pour modifier ses intrants.",
                    operation.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        operations = self.env['garden.operation'].browse([v['operation_id'] for v in vals_list if v.get('operation_id')])
        self._check_operation_open(operations)
        return super().create(vals_list)

    def write(self, vals):
        if self._LOCKED_FIELDS & vals.keys():
            self._check_operation_open()
        return super().write(vals)

    def unlink(self):
        if not self.env.context.get('garden_force_unlink'):
            self._check_operation_open()
        return super().unlink()

    # ------------------------------------------------------------------
    # Mouvements de stock
    # ------------------------------------------------------------------
    def _consume(self):
        """Crée les mouvements de consommation (stock -> « Consommation maraîchage ») des lignes non consommées."""
        Move = self.env['stock.move'].sudo()
        for line in self.sudo().filtered(lambda l: not l.consumed):
            operation = line.operation_id
            company = operation.company_id
            source = company._get_garden_stock_location()
            destination = company.garden_consumption_location_id
            if not source or not destination:
                raise UserError(self.env._(
                    "Configurez l'emplacement de stockage et l'emplacement « Consommation maraîchage » de la société « %s ».",
                    company.name,
                ))
            product = line.product_id
            if product.tracking != 'none' and not line.lot_id:
                raise UserError(self.env._(
                    "Renseignez le lot de « %(product)s » (opération « %(operation)s »).",
                    product=product.display_name, operation=operation.name,
                ))
            if product.tracking == 'serial' and line.uom_id._compute_quantity(line.quantity, product.uom_id) != 1:
                raise UserError(self.env._(
                    "Un produit suivi par numéro de série se consomme une unité à la fois (« %s »).",
                    product.display_name,
                ))
            line.unit_cost = line._get_product_cost()
            move = Move.with_company(company).create(operation._prepare_stock_move_vals(
                product, line.quantity, line.uom_id, source, destination, line.lot_id,
                kind='input',
            ))
            move._action_done()
            operation._set_move_date(move)
            line.move_id = move

    def _unconsume(self):
        """Annule la consommation des lignes consommées par un mouvement inverse."""
        for line in self.sudo().filtered('consumed'):
            line.operation_id._reverse_stock_move(line.move_id, 'input_return')
