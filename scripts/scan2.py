import json, re, sys
d = json.load(open(sys.argv[1]))
docs = {x['id']: x for x in d['documents']}
def page_text(did, p):
    for pg in docs[did]['pages']:
        if pg['page'] == p: return pg['printed_content']
def fmts(v):
    v = float(v); out = set()
    for x in (v, -v):
        out |= {f"{x:,.2f}", f"{x:,.0f}", f"{x:.2f}", f"{x:.0f}", f"{x:,}"}
    out.add(f"({abs(v):,.2f})")
    return out
bad = []
for e in d['extracted_values']:
    if e['value_type'] not in ('money',) or e['value'] is None: continue
    if e['document_id'] == 'D74': continue
    t = page_text(e['document_id'], e['page']) or ''
    tn = t.replace('$', '')
    if not any(f in tn for f in fmts(e['value'])):
        bad.append(e)
print(len(bad))
for e in bad:
    print(e['id'], e['document_id'], 'p', e['page'], e['field'], '| value=', e['value'], '| read=', repr(e['text_as_read']), '| conf', e['confidence'])
