import json, sys
d = json.load(open(sys.argv[1]))
def desc(x, depth=0, maxd=2):
    pad = "  " * depth
    if isinstance(x, dict):
        for k, v in list(x.items())[:60]:
            t = type(v).__name__
            n = len(v) if isinstance(v, (list, dict, str)) else ""
            print(f"{pad}{k}: {t} {n}")
            if depth < maxd and isinstance(v, (dict,)) : desc(v, depth+1, maxd)
            if depth < maxd and isinstance(v, list) and v and isinstance(v[0], dict):
                print(f"{pad}  [0] keys: {list(v[0].keys())}")
desc(d)
