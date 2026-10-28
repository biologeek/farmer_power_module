from odoo import api, fields, models
from odoo.exceptions import ValidationError


class GardenSeason(models.Model):
    _name = 'garden.season'
    _description = 'Saison (plan de culture annuel)'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'

    # Une saison regroupe le plan de culture d'une année (ou d'une campagne) : ses cultures, leurs
    # planches et leurs dates prévues. Les contrôles et les besoins en semences s'y rapportent.

    name = fields.Char('Nom', required=True, tracking=True, help="Libellé de la saison, par exemple « Saison 2027 ». Unique par société.")
    date_start = fields.Date('Début', required=True, tracking=True, help="Premier jour de la saison.")
    date_end = fields.Date('Fin', required=True, tracking=True, help="Dernier jour de la saison ; ne peut pas précéder le début.")
    company_id = fields.Many2one(
        'res.company', string='Société', required=True, default=lambda self: self.env.company, index=True,
        help="Société propriétaire du plan de culture.",
    )
    state = fields.Selection(
        [('draft', 'Brouillon'), ('validated', 'Validé'), ('closed', 'Clôturé')],
        string='État', required=True, default='draft', tracking=True, copy=False,
        help="Brouillon : plan en préparation. Validé : plan arrêté. Clôturé : saison terminée.",
    )
    crop_ids = fields.One2many('garden.crop', 'season_id', string='Cultures', help="Cultures planifiées pendant cette saison.")
    crop_count = fields.Integer('Nombre de cultures', compute='_compute_crop_count', help="Nombre de cultures rattachées à la saison.")
    notes = fields.Text('Notes')

    _name_company_uniq = models.Constraint(
        'UNIQUE (name, company_id)', 'Une saison de ce nom existe déjà pour cette société.',
    )

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for season in self:
            if season.date_start and season.date_end and season.date_end < season.date_start:
                raise ValidationError(self.env._("La fin de la saison ne peut pas précéder son début."))

    @api.depends('crop_ids')
    def _compute_crop_count(self):
        counts = dict(self.env['garden.crop']._read_group(
            [('season_id', 'in', self.ids)], ['season_id'], ['__count'],
        ))
        for season in self:
            season.crop_count = counts.get(season, 0)

    def action_validate(self):
        self.state = 'validated'

    def action_close(self):
        self.state = 'closed'

    def action_reset_draft(self):
        self.state = 'draft'

    def action_view_crops(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('odoo_garden.action_garden_crop')
        action['domain'] = [('season_id', '=', self.id)]
        action['context'] = {'default_season_id': self.id}
        return action
