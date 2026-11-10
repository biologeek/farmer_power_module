import time
from odoo import api
env = api.Environment(env.cr, 2, {})  # noqa: F821
Rev = env['garden.revenue']
crops = env['garden.crop'].search([('state', '!=', 'cancelled')])
for method in ('prorata', 'lot'):
    for label, sample in (('1000 cultures', crops[:1000]), ('toutes', crops)):
        env.invalidate_all()
        t = time.time(); totals = Rev.get_extra_totals(sample, method); t_new = time.time() - t
        if label == 'toutes':
            print('%s %s : totaux en %.1fs' % (method, label, t_new)); continue
        t = time.time(); entries = Rev.get_extra_entries(sample, method); t_old = time.time() - t
        bad = 0
        for cid in sample.ids:
            a, c = totals.get(cid, (0.0, 0)); es = entries.get(cid, [])
            if c != len(es) or abs(a - sum(e['amount'] for e in es)) > 1e-6:
                bad += 1
        print('%s %s : totaux %.2fs / entrées %.2fs, divergences=%d, cultures avec PdV=%d' % (method, label, t_new, t_old, bad, sum(1 for v in totals.values() if v[1])))
