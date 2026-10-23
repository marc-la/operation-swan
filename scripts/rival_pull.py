# Read-only pull of account_posts histories for a list of account ids. Paced; backs off on the shared 300/min bucket.
# usage: pull.py ids.txt out.jsonl [max_per_min] [max_pages]
import capturethenarrative as ctn, json, sys, time, os
ids=[int(x) for x in open(sys.argv[1]).read().split()]
out=sys.argv[2]; per_min=float(sys.argv[3]) if len(sys.argv)>3 else 60; max_pages=int(sys.argv[4]) if len(sys.argv)>4 else 40
done=set()
if os.path.exists(out):
    for l in open(out):
        try: done.add(json.loads(l)['account_id'])
        except Exception: pass
s=ctn.LegitSocial(max_retries=0)
gap=60.0/per_min; reads=0
def call(*a,**k):
    global reads
    while True:
        try:
            r=s.account_posts(*a,**k); reads+=1; time.sleep(gap)
            rl=s.rate_limit
            if rl and rl.remaining<120: time.sleep(10)
            return r
        except ctn.RateLimited as e: time.sleep(e.retry_after+2)
with open(out,'a') as f:
    for n,i in enumerate(ids):
        if i in done: continue
        posts=[]; cur=None; err=None; pages=0
        try:
            while pages<max_pages:
                pg=call(i,limit=100,cursor=cur); pages+=1
                for p in pg: posts.append({'id':p['post_id'],'k':p['kind'],'t':p['created_at'],'rt':p.get('reply_to_post_id'),'rp':p.get('repost_of_post_id'),'b':p['body'],'e':(p.get('embed') or {}).get('kind') if p.get('embed') else None})
                cur=pg.next_cursor
                if not cur or not len(pg): break
        except ctn.APIError as e: err=f'{e.status}'
        f.write(json.dumps({'account_id':i,'err':err,'pages':pages,'truncated':bool(cur) and pages>=max_pages,'posts':posts})+'\n'); f.flush()
        if n%25==0: print(n,len(ids),'reads',reads,flush=True)
print('done reads',reads)
