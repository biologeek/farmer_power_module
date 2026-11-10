from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class GardenSeasonPlanWizard(models.TransientModel):
    """Crée en série des cultures d'une saison sur une liste de planches, éventuellement échelonnées."""
    _name = 'garden.season.plan.wizard'
    _description = 'Batch Planning Wizard'

    season_id = fields.Many2one('garden.season', string='Season', required=True, help='Season that will receive the crops created.')
    template_id = fields.Many2one(
        'garden.crop.template', string='Crop Template', required=True,
        help='Template applied to all the crops created.',
    )
    bed_ids = fields.Many2many(
        'garden.bed', string='Beds', required=True,
        help='A crop is created on each of these beds.',
    )
    target = fields.Selection(
        [('harvest', 'Targeted Harvest Start'), ('sowing', 'Sowing Date')],
        string='Target Date', required=True, default='harvest',
        help='Indicates whether the date entered is the harvest start (backward planning) or the sowing.',
    )
    target_date = fields.Date('Date', required=True, help='Target date for the first bed.')
    stagger_days = fields.Integer(
        'Offset between Beds (days)', default=0,
        help='Number of days added to the target date for each successive bed, to stagger the crops (0 = all '
             'beds on the same date).',
    )
    bed_share = fields.Float('Bed Share (%)', default=100.0, help='Share of each bed occupied by the crop.')
    preview = fields.Text('Preview', compute='_compute_preview', help='Dates computed for each bed before creation.')

    def _get_dates_per_bed(self):
        """Liste de (planche, dates prévues) ; la planche n°i est décalée de i × ``stagger_days``."""
        self.ensure_one()
        result = []
        for index, bed in enumerate(self.bed_ids):
            target = self.target_date + timedelta(days=index * self.stagger_days)
            if self.target == 'sowing':
                dates = self.template_id._plan_dates(sowing_date=target)
            else:
                dates = self.template_id._plan_dates(harvest_start=target)
            result.append((bed, dates))
        return result

    @api.depends('template_id', 'bed_ids', 'target', 'target_date', 'stagger_days')
    def _compute_preview(self):
        for wizard in self:
            if not (wizard.template_id and wizard.bed_ids and wizard.target_date):
                wizard.preview = False
                continue
            lines = [
                wizard.env._(
                    "%(bed)s: sowing %(sowing)s, harvest %(start)s → %(end)s",
                    bed=bed.display_name, sowing=dates['planned_sowing_date'], start=dates['planned_harvest_start'],
                    end=dates['planned_harvest_end'],
                )
                for bed, dates in wizard._get_dates_per_bed()
            ]
            wizard.preview = "\n".join(lines)

    def action_create_crops(self):
        self.ensure_one()
        if not self.bed_ids:
            raise UserError(self.env._('Select at least one bed.'))
        vals_list = [
            {
                'season_id': self.season_id.id,
                'template_id': self.template_id.id,
                'bed_id': bed.id,
                'bed_share': self.bed_share,
                **dates,
            }
            for bed, dates in self._get_dates_per_bed()
        ]
        crops = self.env['garden.crop'].create(vals_list)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Crops Created'),
            'res_model': 'garden.crop',
            'view_mode': 'list,form',
            'domain': [('id', 'in', crops.ids)],
        }
