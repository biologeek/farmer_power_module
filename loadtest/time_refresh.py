import time
from odoo import api
env = api.Environment(env.cr, 2, {})  # noqa: F821
P = env['garden.crop.profitability']
for i in range(2):
    env.invalidate_all(); t = time.time(); P.refresh(); print('refresh #%d : %.1fs' % (i + 1, time.time() - t))
env.invalidate_all(); t = time.time(); P.get_dashboard_data(); print('get_dashboard_data : %.1fs' % (time.time() - t))
# cohérence : revenue/margin des lignes = valeurs recalculées par l'ORM, culture par culture
import random
env.invalidate_all()
lines = P.search([]).filtered(lambda l: l.revenue)
sample = random.Random(1).sample(list(lines), 300)
bad = 0
for l in sample:
    c = l.crop_id
    c.invalidate_recordset(['revenue', 'margin', 'sale_line_count'])
    if abs(c.revenue - l.revenue) > 0.01 or abs(c.margin - l.margin) > 0.01:
        bad += 1
print('échantillon de %d lignes avec chiffre d\'affaires : incohérences=%d' % (len(sample), bad))
env.cr.rollback()
