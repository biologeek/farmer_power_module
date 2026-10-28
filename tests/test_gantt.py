from odoo.tests import HttpCase, tagged

from .test_planning import GardenPlanningCase


@tagged('post_install', '-at_install')
class TestGardenGanttData(GardenPlanningCase):

    def test_gantt_data_structure(self):
        first = self._crop(planned_sowing_date='2027-03-01', date_start='2027-03-05', date_end='2027-07-01')
        second = self._crop(planned_sowing_date='2027-05-01')  # chevauche la première
        other_bed = self._crop(bed_id=self.bed2.id, planned_sowing_date='2027-03-01')
        data = self.env['garden.bed'].get_occupancy_data([('id', 'in', (self.bed | self.bed2).ids)])
        self.assertEqual(len(data['groups']), 1)
        group = data['groups'][0]
        self.assertIn('Îlot plan', group['name'])
        beds = {b['id']: b for b in group['beds']}
        crops = {c['id']: c for c in beds[self.bed.id]['crops']}
        self.assertEqual(set(crops), {first.id, second.id})
        self.assertEqual(crops[first.id]['planned_start'], '2027-03-01')
        self.assertEqual(crops[first.id]['real_start'], '2027-03-05')
        self.assertEqual(crops[first.id]['real_end'], '2027-07-01')
        self.assertEqual(crops[first.id]['family'], 'solanaceae')
        self.assertTrue(crops[second.id]['warnings'])
        # deux cultures simultanées sont sur deux lignes distinctes
        self.assertNotEqual(crops[first.id]['lane'], crops[second.id]['lane'])
        self.assertEqual(beds[self.bed.id]['lanes'], 2)
        self.assertEqual(beds[self.bed2.id]['lanes'], 1)
        self.assertEqual([c['id'] for c in beds[self.bed2.id]['crops']], [other_bed.id])
        self.assertEqual(data['start_date'], '2027-03-01')
        self.assertIn({'key': 'solanaceae', 'label': 'Solanacées'}, data['families'])
        self.assertIn(self.season.id, [s['id'] for s in data['seasons']])
        self.assertIn(self.site.id, [s['id'] for s in data['sites']])

    def test_gantt_filters(self):
        other_season = self.env['garden.season'].create({
            'name': 'Autre saison', 'date_start': '2028-01-01', 'date_end': '2028-12-31',
        })
        crop = self._crop(planned_sowing_date='2027-03-01')
        later = self._crop(planned_sowing_date='2028-03-01', season_id=other_season.id)
        domain = [('id', '=', self.bed.id)]
        bed_data = self.env['garden.bed'].get_occupancy_data(domain, season_id=self.season.id)['beds'][0]
        self.assertEqual([c['id'] for c in bed_data['crops']], [crop.id])
        bed_data = self.env['garden.bed'].get_occupancy_data(domain, season_id=other_season.id)['beds'][0]
        self.assertEqual([c['id'] for c in bed_data['crops']], [later.id])
        # filtre par site
        site2 = self.env['garden.site'].create({'name': 'Autre site', 'farm_id': self.farm.id})
        data = self.env['garden.bed'].get_occupancy_data(domain, site_id=site2.id)
        self.assertEqual(data['beds'], [])
        data = self.env['garden.bed'].get_occupancy_data(domain, site_id=self.site.id)
        self.assertEqual(len(data['beds']), 1)

    def test_empty_gantt(self):
        data = self.env['garden.bed'].get_occupancy_data([('id', '=', 0)])
        self.assertEqual(data['groups'], [])
        self.assertTrue(data['start_date'] <= data['end_date'])

    def test_calendar_view(self):
        view = self.env['garden.crop'].get_views([(False, 'calendar')])
        self.assertIn('calendar', view['views'])
        action = self.env.ref('odoo_garden.action_garden_crop_calendar')
        self.assertTrue(action.view_mode.startswith('calendar'))


@tagged('post_install', '-at_install')
class TestGardenGanttTour(HttpCase, GardenPlanningCase):

    def test_gantt_tour(self):
        self.bed.write({'code': 'GN01'})
        season = self.env['garden.season'].create({
            'name': 'Saison Gantt 2027', 'date_start': '2027-01-01', 'date_end': '2027-12-31',
        })
        species = self.env['garden.species'].create({'name': 'Tomate Gantt', 'family': 'solanaceae'})
        variety = self.env['garden.variety'].create({'name': 'Gantt', 'species_id': species.id})
        template = self.env['garden.crop.template'].create({
            'name': 'Tomate Gantt', 'variety_id': variety.id, 'days_to_maturity': 90, 'harvest_window_days': 30,
        })
        self.env['garden.crop'].create({
            'template_id': template.id, 'bed_id': self.bed.id, 'season_id': season.id,
            'planned_sowing_date': '2027-03-01', 'date_start': '2027-03-05', 'date_end': '2027-06-30',
        })
        self.start_tour('/odoo/action-odoo_garden.action_garden_bed_occupancy', 'garden_gantt_tour', login='admin')
