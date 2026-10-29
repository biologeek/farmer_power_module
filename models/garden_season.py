from odoo import api, fields, models
from odoo.exceptions import ValidationError


class GardenSeason(models.Model):
    _name = 'garden.season'
    _description = 'Season (annual crop plan)'
    _inherit = ['mail.thread']
    _order = 'date_start desc, id desc'

    # Une saison regroupe le plan de culture d'une année (ou d'une campagne) : ses cultures, leurs
    # planches et leurs dates prévues. Les contrôles et les besoins en semences s'y rapportent.

    name = fields.Char('Name', required=True, tracking=True, help='Season label, for example "Season 2027". Unique per company.')
    date_start = fields.Date('Start Date', required=True, tracking=True, help='First day of the season.')
    date_end = fields.Date('End Date', required=True, tracking=True, help='Last day of the season; cannot precede the start.')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, default=lambda self: self.env.company, index=True,
        help='Company owning the crop plan.',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('validated', 'Validated'), ('closed', 'Closed')],
        string='Status', required=True, default='draft', tracking=True, copy=False,
        help='Draft: plan being prepared. Validated: plan frozen. Closed: season over.',
    )
    crop_ids = fields.One2many('garden.crop', 'season_id', string='Crops', help='Crops planned during this season.')
    crop_count = fields.Integer('Number of Crops', compute='_compute_crop_count', help='Number of crops attached to the season.')
    notes = fields.Text('Notes')

    _name_company_uniq = models.Constraint(
        'UNIQUE (name, company_id)', 'A season with this name already exists for this company.',
    )

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for season in self:
            if season.date_start and season.date_end and season.date_end < season.date_start:
                raise ValidationError(self.env._('The end of the season cannot precede its start.'))

    @api.depends('crop_ids')
    def _compute_crop_count(self):
        counts = dict(self.env['garden.crop']._read_group(
            [('season_id', 'in', self.ids)], ['season_id'], ['__count'],
        ))
        for season in self:
            season.crop_count = counts.get(season, 0)

    def action_validate(self):
        self.state = 'validated'
        self.action_generate_operations()

    def action_generate_operations(self):
        """Crée les opérations planifiées manquantes des cultures de la saison (idempotent)."""
        self.crop_ids._generate_operations()

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
