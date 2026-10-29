from odoo import api, fields, models
from odoo.exceptions import UserError


class GardenLoss(models.Model):
    _name = 'garden.loss'
    _description = 'Loss on a Crop'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'
    # Une perte avant récolte (maladie, ravageur, météo...) n'a aucun effet sur le stock. Une perte après
    # récolte (invendu, abîmé...) crée un rebut (`stock.scrap`) sur le lot de la culture.

    crop_id = fields.Many2one(
        'garden.crop', string='Crop', required=True, index=True, ondelete='cascade', tracking=True,
        help='Crop concerned by the loss.',
    )
    bed_id = fields.Many2one('garden.bed', string='Bed', related='crop_id.bed_id', store=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Company', related='crop_id.company_id', store=True, index=True,
    )
    date = fields.Date(
        'Date', required=True, default=fields.Date.context_today, index=True, tracking=True,
        help='Day the loss was noticed.',
    )
    stage = fields.Selection(
        [('pre_harvest', 'Pre-Harvest'), ('post_harvest', 'Post-Harvest')],
        string='Step', required=True, default='pre_harvest', tracking=True,
        help='Pre-harvest: loss in the field, no effect on stock. Post-harvest: a stock scrap is created on '
             'the crop lot.',
    )
    product_id = fields.Many2one(
        'product.product', string='Product', compute='_compute_product_id', store=True, readonly=False,
        precompute=True,
        help='Lost product (suggested from the variety of the crop); it determines the post-harvest scrap.',
    )
    quantity = fields.Float(
        'Lost Quantity', digits='Product Unit', required=True, tracking=True,
        help='Lost quantity, in the chosen unit.',
    )
    uom_id = fields.Many2one(
        'uom.uom', string='Unit', compute='_compute_uom_id', store=True, readonly=False, required=True,
        precompute=True, help='Unit of the quantity (suggested from the product, otherwise kg).',
    )
    quantity_ref = fields.Float(
        'Quantity (product unit)', compute='_compute_quantity_ref', store=True, digits='Product Unit',
        help='Quantity converted into the unit of the harvested product, used for the loss rate.',
    )
    cause = fields.Selection(
        [
            ('disease', 'Disease'),
            ('pest', 'Pest'),
            ('weather', 'Weather'),
            ('unsold', 'Unsold'),
            ('other', 'Other'),
        ],
        string='Cause', required=True, default='other', tracking=True,
        help='Main cause of the loss.',
    )
    notes = fields.Text('Notes', help='Details about the loss.')
    scrap_id = fields.Many2one(
        'stock.scrap', string='Stock Scrap', readonly=True, copy=False, index='btree_not_null', ondelete='restrict',
        help='Scrap created for a post-harvest loss.',
    )
    lot_id = fields.Many2one(
        'stock.lot', string='Lot', related='scrap_id.lot_id',
        help='Crop lot the scrap was made on.',
    )

    _quantity_positive = models.Constraint(
        'CHECK (quantity > 0)', 'The lost quantity must be strictly positive.',
    )

    @api.depends('crop_id')
    def _compute_product_id(self):
        for loss in self:
            loss.product_id = loss.crop_id.variety_id.harvest_product_id

    @api.depends('product_id')
    def _compute_uom_id(self):
        default_uom = self.env.ref('uom.product_uom_kgm', raise_if_not_found=False)
        for loss in self:
            loss.uom_id = loss.product_id.uom_id or loss.uom_id or default_uom

    @api.depends('quantity', 'uom_id', 'product_id.uom_id')
    def _compute_quantity_ref(self):
        for loss in self:
            target = loss.product_id.uom_id or loss.uom_id
            loss.quantity_ref = loss.uom_id._compute_quantity(loss.quantity, target, round=False) if target else loss.quantity

    # ------------------------------------------------------------------
    # Rebut de stock (après récolte)
    # ------------------------------------------------------------------
    _LOCKED_FIELDS = {'crop_id', 'stage', 'product_id', 'quantity', 'uom_id', 'date'}

    def _get_scrap_lot(self):
        """Lot de récolte de la culture pour le produit perdu (vide si le produit n'est pas suivi par lots)."""
        self.ensure_one()
        product = self.product_id.sudo()
        if product.tracking == 'none':
            return self.env['stock.lot']
        lot = self.env['stock.lot'].sudo().search([
            ('garden_crop_id', '=', self.crop_id.id), ('product_id', '=', product.id),
        ], limit=1)
        if not lot:
            raise UserError(self.env._(
                'No harvest lot of crop "%(crop)s" for "%(product)s": record a harvest first before declaring a '
                'post-harvest loss.',
                crop=self.crop_id.name, product=product.display_name,
            ))
        return lot

    def _get_scrap_location(self, lot):
        """Emplacement du lot (le plus fourni), à défaut l'emplacement de stockage maraîchage."""
        self.ensure_one()
        company = self.company_id
        if lot:
            quants = self.env['stock.quant'].sudo().search([
                ('lot_id', '=', lot.id), ('location_id.usage', '=', 'internal'),
                ('company_id', '=', company.id), ('quantity', '>', 0),
            ], order='quantity desc', limit=1)
            if quants:
                return quants.location_id
        return company._get_garden_stock_location()

    def _create_scrap(self):
        """Crée et valide le rebut de stock des pertes après récolte qui n'en ont pas encore."""
        for loss in self.filtered(lambda l: l.stage == 'post_harvest' and not l.scrap_id):
            if not loss.product_id:
                raise UserError(self.env._(
                    'Choose the lost product: the variety of crop "%s" has no harvest product.',
                    loss.crop_id.name,
                ))
            lot = loss._get_scrap_lot()
            location = loss._get_scrap_location(lot)
            if not location:
                raise UserError(self.env._(
                    'Configure the storage location of company "%s".', loss.company_id.name,
                ))
            scrap = self.env['stock.scrap'].sudo().with_company(loss.company_id).create({
                'product_id': loss.product_id.id,
                'product_uom_id': loss.uom_id.id,
                'scrap_qty': loss.quantity,
                'lot_id': lot.id or False,
                'location_id': location.id,
                'company_id': loss.company_id.id,
                'origin': self.env._('Loss: %s', loss.crop_id.name),
            })
            if scrap.product_id.is_storable and not scrap.check_available_qty():
                raise UserError(self.env._(
                    'Insufficient stock to scrap %(qty)s %(uom)s of "%(product)s"%(lot)s.',
                    qty=loss.quantity, uom=loss.uom_id.name, product=loss.product_id.display_name,
                    lot=lot and self.env._(" (lot %s)", lot.name) or "",
                ))
            scrap.do_scrap()
            moment = fields.Datetime.to_datetime(loss.date).replace(hour=12)
            scrap.move_ids.write({'date': moment})
            scrap.move_ids.move_line_ids.write({'date': moment})
            loss.scrap_id = scrap

    @api.model_create_multi
    def create(self, vals_list):
        losses = super().create(vals_list)
        losses._create_scrap()
        return losses

    def write(self, vals):
        if self._LOCKED_FIELDS & vals.keys() and any(loss.scrap_id for loss in self):
            raise UserError(self.env._(
                'This loss already scrapped stock: it can no longer be modified (only the cause and the notes can).',
            ))
        result = super().write(vals)
        if self._LOCKED_FIELDS & vals.keys():
            self._create_scrap()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_scrapped(self):
        if any(loss.scrap_id for loss in self):
            raise UserError(self.env._(
                'A loss that scrapped stock cannot be deleted: correct the stock with an inventory adjustment.',
            ))

    def action_view_scrap(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.scrap',
            'res_id': self.scrap_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
