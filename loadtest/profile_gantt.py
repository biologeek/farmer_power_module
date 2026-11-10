import cProfile, pstats, io, time
from odoo import api
env = api.Environment(env.cr, 2, {})  # noqa: F821
Bed = env['garden.bed']
s = env['garden.season'].search([('name', 'like', '%2027')], limit=1)
for label, kw in (('toutes saisons', {}), ('saison 2027', {'season_id': s.id})):
    env.invalidate_all(); env.cr.sql_log_count if False else None
    q0 = env.cr.sql_log_count; t = time.time()
    pr = cProfile.Profile(); pr.enable(); Bed.get_occupancy_data(**kw); pr.disable()
    print('%s : %.1fs, %d req' % (label, time.time() - t, env.cr.sql_log_count - q0))
    if label == 'toutes saisons':
        st = io.StringIO(); pstats.Stats(pr, stream=st).sort_stats('cumulative').print_stats(14); print(st.getvalue()[:3800])
