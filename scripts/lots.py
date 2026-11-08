import json, re, sys
from datetime import date
d = json.load(open(sys.argv[1]))
docs = {x['id']: x for x in d['documents']}
pat = re.compile(r"([XM]\d+) (.+?) ([\d.]+) sh acquired (\d{4}-\d{2}-\d{2}) sold (\d{4}-\d{2}-\d{2}) proceeds ([\d,]+\.\d\d) basis ([\d,]+\.\d\d) wash sale loss disallowed ([\d,]+\.\d\d) (short|long)-term (covered|noncovered)")
num = lambda s: float(s.replace(',', ''))
lots = {}
for did in ['D74', 'D31']:
    for p in docs[did]['pages']:
        for m in pat.finditer(p['printed_content']):
            i, name, sh, acq, sold, pr, bs, ws, term, cov = m.groups()
            lots[i] = dict(doc=did, page=p['page'], name=name, acq=acq, sold=sold, pr=num(pr), bs=num(bs), ws=num(ws), term=term, cov=cov)
print('lots parsed', len(lots), sum(1 for l in lots.values() if l['doc']=='D74'), 'brightpath')
V = d['return_versions'][2]
ret = {}
lp = re.compile(r"acquired (\S+), sold (\S+); proceeds ([\d,]+\.\d\d), basis ([\d,]+\.\d\d)(?:, adjustment W ([\d,]+\.\d\d))?")
for l in V['lines']:
    k = l['key']
    if k.startswith('F8949.') and k.split('.')[2][0] in 'XM' and k.split('.')[2][1:].isdigit():
        m = lp.search(l['label'])
        ret[k.split('.')[2]] = dict(box=k.split('.')[1], acq=m.group(1), sold=m.group(2), pr=num(m.group(3)), bs=num(m.group(4)), w=num(m.group(5) or '0'), val=l['value'])
issues = []
for i, L in lots.items():
    R = ret.get(i)
    if not R: issues.append((i, 'MISSING from return', L)); continue
    a = date.fromisoformat(L['acq']); s = date.fromisoformat(L['sold'])
    lt = (s.year - a.year, s.month, s.day) > (1, a.month, a.day)
    true_term = 'long' if lt else 'short'
    box_term = 'long' if R['box'] in 'DEF' else 'short'
    if true_term != L['term']: issues.append((i, f'broker says {L["term"]} but dates say {true_term}', L['acq'], L['sold']))
    if box_term != L['term']: issues.append((i, f'return box {R["box"]} vs broker {L["term"]}'))
    for f in ['pr', 'bs']:
        if abs(R[f] - L[f]) > 0.005: issues.append((i, f'{f} return {R[f]} vs doc {L[f]}'))
    if abs(R['w'] - L['ws']) > 0.005: issues.append((i, f'wash return {R["w"]} vs doc {L["ws"]}'))
    if R['acq'] != L['acq'] or R['sold'] != L['sold']: issues.append((i, 'dates differ', R['acq'], L['acq'], R['sold'], L['sold']))
    exp = round(L['pr'] - L['bs'] + L['ws'], 2)
    if abs(exp - R['val']) > 0.01: issues.append((i, f'gain return {R["val"]} vs computed {exp}'))
for i in ret:
    if i not in lots: issues.append((i, 'in return but not in documents', ret[i]))
for x in issues: print(x)
for did, summ in [('D74', None)]:
    st = [l for l in lots.values() if l['doc']=='D74' and l['term']=='short']; lt = [l for l in lots.values() if l['doc']=='D74' and l['term']=='long']
    print('D74 ST proceeds %.2f basis %.2f wash %.2f n=%d' % (sum(l['pr'] for l in st), sum(l['bs'] for l in st), sum(l['ws'] for l in st), len(st)))
    print('D74 LT proceeds %.2f basis %.2f wash %.2f n=%d' % (sum(l['pr'] for l in lt), sum(l['bs'] for l in lt), sum(l['ws'] for l in lt), len(lt)))
m = [l for l in lots.values() if l['doc']=='D31']
print('D31 proceeds total %.2f n=%d' % (sum(l['pr'] for l in m), len(m)))
