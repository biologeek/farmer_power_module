import cProfile, pstats, io, time
from odoo import api
env = api.Environment(env.cr, 2, {})  # noqa: F821
P = env['garden.crop.profitability']
P.refresh(); env.cr.commit(); env.invalidate_all()
type(P).refresh = lambda self: True
t = time.time(); pr = cProfile.Profile(); pr.enable(); P.get_dashboard_data(); pr.disable()
print('hors refresh : %.1fs' % (time.time() - t))
st = io.StringIO(); pstats.Stats(pr, stream=st).sort_stats('cumulative').print_stats(16); print(st.getvalue()[250:3600])
