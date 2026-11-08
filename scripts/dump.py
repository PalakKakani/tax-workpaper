import json, sys
d = json.load(open(sys.argv[1]))
docs = {x['id']: x for x in d['documents']}
ev = {e['id']: e for e in d['extracted_values']}
def doc(i, values=True):
    x = docs[i]
    print(f"##### {i} {x['title']} | {x['document_type']} | belongs {x['belongs_to']} | recv {x['received_at']} | corrected {x.get('marked_corrected')} | extr {x['extraction']}")
    for p in x['pages']:
        print(f"  p{p['page']}: {p['printed_content']}")
    if values:
        for e in d['extracted_values']:
            if e['document_id'] == i:
                print(f"    {e['id']} p{e['page']} {e['field']} = {e['value']!r} (read {e['text_as_read']!r}, conf {e['confidence']})")
def lines(prefixes, v=2):
    V = d['return_versions'][v]
    for l in V['lines']:
        if any(l['key'].startswith(p) for p in prefixes):
            print(f"  {l['key']} [{l['jurisdiction']}] {l['label']} = {l['value']!r} | rule {l.get('rule')} | in {l.get('inputs')} | src {l.get('sources')} | {l.get('note') or ''}")
if __name__ == '__main__':
    mode = sys.argv[2]
    if mode == 'doc':
        for i in sys.argv[3:]: doc(i)
    elif mode == 'lines':
        lines(sys.argv[3:])
