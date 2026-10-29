from odoo import api, fields, models


class GardenCropSale(models.TransientModel):
    _name = 'garden.crop.sale'
    _description = "Ligne de vente attribuée à une culture"
    _order = 'date desc, id'
    # Lignes temporaires créées à l'ouverture du bouton « Ventes » de la culture : elles exposent au chef de
    # culture le détail du chiffre d'affaires attribué (facture, client, produit, montant) sans lui donner
    # accès aux factures ni à la comptabilité. Les factures sont lues en ``sudo`` à la création uniquement.

    crop_id = fields.Many2one('garden.crop', string='Culture', required=True, ondelete='cascade', index=True)
    date = fields.Date('Date')
    invoice_name = fields.Char('Facture')
    is_refund = fields.Boolean('Avoir')
    partner_id = fields.Many2one('res.partner', string='Client')
    product_id = fields.Many2one('product.product', string='Produit')
    quantity = fields.Float('Quantité', digits='Product Unit')
    line_amount = fields.Float('Montant HT de la ligne', digits='Product Price')
    amount = fields.Float('Montant attribué', digits='Product Price')
    share = fields.Float('Part attribuée (%)')

    @api.model
    def _open_for(self, crop):
        """Crée les lignes de vente de la culture et retourne l'action qui les liste."""
        crop = crop.sudo()
        attribution = self.env['garden.revenue'].get_attribution(crop).get(crop.id, {})
        lines = self.env['account.move.line'].sudo().browse(list(attribution))
        self.sudo().search([('crop_id', '=', crop.id), ('create_uid', '=', self.env.uid)]).unlink()
        extra_entries = self.env['garden.revenue'].get_extra_entries(crop).get(crop.id, [])
        self.sudo().create([{
            'crop_id': crop.id,
            'date': entry['date'],
            'invoice_name': entry['document'],
            'is_refund': entry['is_refund'],
            'partner_id': entry['partner_id'],
            'product_id': entry['product_id'],
            'quantity': entry['quantity'],
            'line_amount': entry['line_amount'],
            'amount': entry['amount'],
            'share': (entry['amount'] / entry['line_amount'] * 100.0) if entry['line_amount'] else 0.0,
        } for entry in extra_entries])
        self.sudo().create([{
            'crop_id': crop.id,
            'date': line.date,
            'invoice_name': line.move_id.name,
            'is_refund': line.move_id.move_type == 'out_refund',
            'partner_id': line.partner_id.id,
            'product_id': line.product_id.id,
            'quantity': line.quantity * (-1 if line.move_id.move_type == 'out_refund' else 1),
            'line_amount': -line.balance,
            'amount': attribution[line.id],
            'share': (attribution[line.id] / -line.balance * 100.0) if line.balance else 0.0,
        } for line in lines])
        action = self.env['ir.actions.act_window']._for_xml_id('odoo_garden.action_garden_crop_sale')
        action['domain'] = [('crop_id', '=', crop.id), ('create_uid', '=', self.env.uid)]
        action['name'] = self.env._("Ventes : %s", crop.name)
        return action
