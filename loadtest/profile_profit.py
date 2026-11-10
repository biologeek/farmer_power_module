import cProfile, pstats, io, time
from odoo import api
env = api.Environment(env.cr, 2, {})  # noqa: F821
P = env['garden.crop.profitability']
for label, fn in (('refresh', P.refresh), ('get_dashboard_data', P.get_dashboard_data)):
    env.invalidate_all(); t = time.time()
    pr = cProfile.Profile(); pr.enable(); fn(); pr.disable()
    print('== %s : %.1fs' % (label, time.time() - t))
    st = io.StringIO(); pstats.Stats(pr, stream=st).sort_stats('cumulative').print_stats(22); print(st.getvalue()[300:4200])
env.cr.rollback()
