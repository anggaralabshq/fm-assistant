import json, sys, time
from fmspike import FmClient
c = FmClient(timeout=10)
deadline = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 60)
while True:
    p = c.call('panels')
    if p or time.time() > deadline:
        break
    time.sleep(3)
print(json.dumps(p, ensure_ascii=False))
print(json.dumps([r['text'] for r in c.call('ui_find', text='', max=80)], ensure_ascii=False))
print(json.dumps(c.call('ping'), ensure_ascii=False))
