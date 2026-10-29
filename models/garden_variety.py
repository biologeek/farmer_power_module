from odoo import fields, models


class GardenVariety(models.Model):
    _name = 'garden.variety'
    _description = 'Variety'
    _order = 'species_id, name'

    name = fields.Char('Variety', required=True)
    species_id = fields.Many2one('garden.species', string='Species', required=True, index=True)
    family = fields.Selection(related='species_id.family', string='Botanical Family', store=True)
    supplier_id = fields.Many2one('res.partner', string='Supplier')
    seed_product_id = fields.Many2one('product.product', string='Seed Product')
    harvest_product_id = fields.Many2one('product.product', string='Harvested Product')
    seeds_per_gram = fields.Float('Seeds per Gram')
    germination_rate = fields.Float('Germination Rate (%)', default=100.0)
    organic_status = fields.Selection(
        [
            ('organic', 'Organic'),
            ('untreated', 'Untreated'),
            ('derogation', 'Conventional with Derogation'),
        ],
        string='Organic Status',
    )
    template_ids = fields.One2many('garden.crop.template', 'variety_id', string='Templates')
    notes = fields.Text('Notes')
    active = fields.Boolean('Active', default=True)

    _name_species_uniq = models.Constraint(
        'UNIQUE (name, species_id)', 'This variety already exists for this species.',
    )
    _germination_rate_range = models.Constraint(
        'CHECK (germination_rate >= 0 AND germination_rate <= 100)',
        'The germination rate must be between 0 and 100 %.',
    )
