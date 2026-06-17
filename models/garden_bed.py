from odoo import api, fields, models

class GardenBed(models.Model):
    _name = 'garden.bed'
    _description = 'Planche de culture'

    name = fields.Char('Nom de la planche', required=True)
    garden_id = fields.Many2one('garden.garden', string='Jardin', required=True)
    action_ids = fields.One2many('garden.action', 'bed_id', string='Actions')

    @api.model
    def get_occupancy_data(self, domain=None):
        domain = domain or []
        beds = self.search(domain, order='name')
        crops = self.env['garden.crop'].search([('bed_id', 'in', beds.ids)])

        start_dates = crops.mapped('date_start')
        end_dates = crops.mapped('date_end')
        today = fields.Date.today()
        start = min(start_dates) if start_dates else today
        end = max([d or start for d in end_dates]) if end_dates else start

        bed_data = []
        for bed in beds:
            bed_crops = crops.filtered(lambda crop: crop.bed_id == bed).sorted(key=lambda crop: crop.date_start or "")
            bed_data.append({
                'id': bed.id,
                'name': bed.name,
                'crops': [
                    {
                        'id': crop.id,
                        'label': crop.catalog_id.name or crop.name or "",
                        'date_start': crop.date_start,
                        'date_end': crop.date_end or crop.date_start,
                    }
                    for crop in bed_crops
                ],
            })
        return {
            'beds': bed_data,
            'start_date': start,
            'end_date': end,
        }
