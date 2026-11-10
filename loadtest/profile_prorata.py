import cProfile, pstats, io, time
from odoo import api
env = api.Environment(env.cr, 2, {})  # noqa: F821
crops = env['garden.crop'].search([('state', '!=', 'cancelled')], limit=int(__import__('os').environ.get('N', '8309')))
Rev = env['garden.revenue']
env.invalidate_all()
pr = cProfile.Profile()
t = time.time()
pr.enable()
Rev.get_revenue(crops, 'prorata')
pr.disable()
print('TOTAL %.1fs for %d crops' % (time.time() - t, len(crops)))
for sort in ('cumulative', 'tottime'):
    s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats(sort).print_stats(18); print(s.getvalue()[:4500])
