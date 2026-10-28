from odoo import fields, models


class GardenVariety(models.Model):
    _name = 'garden.variety'
    _description = 'Variété'
    _order = 'species_id, name'

    name = fields.Char('Variété', required=True)
    species_id = fields.Many2one('garden.species', string='Espèce', required=True, index=True)
    family = fields.Selection(related='species_id.family', string='Famille botanique', store=True)
    supplier_id = fields.Many2one('res.partner', string='Fournisseur')
    seed_product_id = fields.Many2one('product.product', string='Produit semence')
    harvest_product_id = fields.Many2one('product.product', string='Produit récolté')
    seeds_per_gram = fields.Float('Graines par gramme')
    germination_rate = fields.Float('Taux de germination (%)', default=100.0)
    organic_status = fields.Selection(
        [
            ('organic', 'Bio'),
            ('untreated', 'Non traitée'),
            ('derogation', 'Conventionnelle avec dérogation'),
        ],
        string='Statut bio',
    )
    template_ids = fields.One2many('garden.crop.template', 'variety_id', string='Itinéraires')
    notes = fields.Text('Notes')
    active = fields.Boolean('Actif', default=True)

    _name_species_uniq = models.Constraint(
        'UNIQUE (name, species_id)', 'Cette variété existe déjà pour cette espèce.',
    )
    _germination_rate_range = models.Constraint(
        'CHECK (germination_rate >= 0 AND germination_rate <= 100)',
        'Le taux de germination doit être compris entre 0 et 100 %.',
    )
