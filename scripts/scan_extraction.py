import json, re, sys
d = json.load(open(sys.argv[1]))
docs = {x['id']: x for x in d['documents']}
def page_text(did, p):
    for pg in docs[did]['pages']:
        if pg['page'] == p: return pg['printed_content']
    return None
def norm(s): return re.sub(r'\s+', ' ', str(s)).strip()
def num(s):
    s = str(s).replace(',', '').replace('$', '').strip()
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try: v = float(s)
    except: return None
    return -v if neg else v
issues = []
for e in d['extracted_values']:
    t = page_text(e['document_id'], e['page'])
    tar = e['text_as_read']
    if t is None:
        issues.append(('NO_PAGE', e)); continue
    if tar and norm(tar) not in norm(t):
        issues.append(('TEXT_NOT_ON_PAGE', e))
    if e['value_type'] in ('money', 'integer', 'quantity', 'percent') and tar:
        n = num(tar)
        if n is not None and e['value'] is not None and abs(n - float(e['value'])) > 0.005:
            issues.append(('VALUE_NE_TEXT', e))
    if not tar and e['value'] not in (None, '', 0, 0.0, False):
        issues.append(('VALUE_BUT_NOTHING_READ', e))
from collections import Counter
print(Counter(k for k, _ in issues))
for k, e in issues:
    if e['document_id'] in ('D74',) and k == 'TEXT_NOT_ON_PAGE': continue
    print(k, e['id'], e['document_id'], 'p', e['page'], e['field'], '| value=', e['value'], '| read=', repr(e['text_as_read']), '| conf', e['confidence'])
