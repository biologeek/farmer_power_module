from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class GardenOperationInput(models.Model):
    _name = 'garden.operation.input'
    _description = 'Input Consumed by an Operation'
    _order = 'operation_id, sequence, id'
    # Une ligne par produit consommé (semence, plant, engrais, traitement...). Quand l'opération passe à
    # « faite », un mouvement de stock part de l'emplacement de stockage vers « Consommation maraîchage ».

    sequence = fields.Integer('Sequence', default=10)
    operation_id = fields.Many2one(
        'garden.operation', string='Operation', required=True, index=True, ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Company', related='operation_id.company_id', store=True, index=True,
    )
    operation_state = fields.Selection(related='operation_id.state', string='Operation Status')
    product_id = fields.Many2one(
        'product.product', string='Product', required=True, index=True, ondelete='restrict',
        domain="[('garden_input_type', '!=', False)]",
        help='Consumed product. Only products with a "market gardening input type" are suggested.',
    )
    garden_input_type = fields.Selection(related='product_id.garden_input_type', string='Input Type', store=True)
    tracking = fields.Selection(related='product_id.tracking', string='Tracking')
    quantity = fields.Float(
        'Quantity', digits='Product Unit', default=1.0, required=True,
        help='Quantity consumed, in the unit of the line.',
    )
    uom_id = fields.Many2one(
        'uom.uom', string='Unit', compute='_compute_uom_id', store=True, readonly=False, precompute=True,
        required=True, help='Unit of the quantity (suggested from the product).',
    )
    treated_area = fields.Float(
        'Treated Area (m²)', compute='_compute_treated_area', store=True, readonly=False, digits=(16, 2),
        help='Area on which the product is applied (plant protection register). Suggested from the target of '
             'the operation (occupied area of the crops, beds or block); editable if only a part is treated. '
             'Frozen once the operation is done.',
    )
    dose = fields.Float(
        'Dose (per ha)', compute='_compute_dose', store=True, digits=(16, 3),
        help='Quantity applied per hectare, in the unit of the line (e.g. kg/ha, L/ha): quantity × 10,000 / '
             'treated area.',
    )
    lot_id = fields.Many2one(
        'stock.lot', string='Lot', domain="[('product_id', '=', product_id)]", ondelete='restrict',
        help='Lot of the consumed product, required for a product tracked by lots (e.g. seed lot).',
    )
    move_id = fields.Many2one(
        'stock.move', string='Stock Move', copy=False, readonly=True, index='btree_not_null',
        ondelete='set null',
        help='Last consumption move created when the operation was validated.',
    )
    consumed = fields.Boolean(
        'Consumed', compute='_compute_consumed',
        help='True if a consumption move is in force (not cancelled by a reverse move).',
    )
    unit_cost = fields.Float(
        'Unit Cost', compute='_compute_unit_cost', store=True, readonly=False, digits=(16, 5),
        groups='odoo_garden.group_garden_chef',
        help='Cost of the product per unit of the line. Suggested from the product cost; frozen when the '
             'operation is done.',
    )
    cost = fields.Float(
        'Cost', compute='_compute_cost', store=True, digits='Product Price',
        groups='odoo_garden.group_garden_chef',
        help='Quantity × unit cost.',
    )

    _quantity_positive = models.Constraint(
        'CHECK (quantity > 0)', 'The quantity of an input must be strictly positive.',
    )

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id

    @api.depends(
        'operation_id.scope', 'operation_id.crop_ids.area', 'operation_id.bed_ids.area', 'operation_id.garden_id.area',
    )
    def _compute_treated_area(self):
        for line in self:
            operation = line.operation_id
            if operation.state == 'done' and line.treated_area:
                continue  # la surface d'une application faite ne bouge plus (registre)
            line.treated_area = operation._get_target_area() if operation.scope else 0.0

    @api.depends('quantity', 'treated_area')
    def _compute_dose(self):
        for line in self:
            line.dose = line.quantity * 10000.0 / line.treated_area if line.treated_area > 0 else 0.0

    @api.constrains('treated_area')
    def _check_treated_area(self):
        if any(line.treated_area < 0 for line in self):
            raise ValidationError(self.env._('The treated area cannot be negative.'))

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
                raise ValidationError(self.env._('Lot "%(lot)s" is not a lot of product "%(product)s".',
                                                 lot=line.lot_id.name, product=line.product_id.display_name))

    # ------------------------------------------------------------------
    # Verrou : les lignes d'une opération faite ne se modifient plus
    # ------------------------------------------------------------------
    _LOCKED_FIELDS = {'product_id', 'quantity', 'uom_id', 'lot_id', 'operation_id', 'treated_area'}

    def _check_operation_open(self, operations=None):
        if self.env.context.get('garden_creating_operation'):
            return
        for operation in (operations or self.operation_id):
            if operation.state == 'done':
                raise UserError(self.env._(
                    'Operation "%s" is done: set it back to planned to modify its inputs.',
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
                    'Configure the storage location and the "Market Gardening Consumption" location of company "%s".',
                    company.name,
                ))
            product = line.product_id
            if product.tracking != 'none' and not line.lot_id:
                raise UserError(self.env._(
                    'Enter the lot of "%(product)s" (operation "%(operation)s").',
                    product=product.display_name, operation=operation.name,
                ))
            if product.tracking == 'serial' and line.uom_id._compute_quantity(line.quantity, product.uom_id) != 1:
                raise UserError(self.env._(
                    'A product tracked by serial number is consumed one unit at a time ("%s").',
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
