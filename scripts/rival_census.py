# Read-only census of all Legit Social accounts (id, username, created_at, verified, private). ~1 read per 100 accounts.
import capturethenarrative as ctn, json, sys, time
out=sys.argv[1]
s=ctn.LegitSocial(max_retries=0)
n=0; cursor=None; t0=time.time()
with open(out,'w') as f:
    while True:
        try:
            pg=s.accounts(limit=100,cursor=cursor)
        except ctn.RateLimited as e:
            time.sleep(e.retry_after+1); continue
        for a in pg: f.write(json.dumps({k:a.get(k) for k in('account_id','username','display_name','verified','private','created_at')})+'\n'); n+=1
        cursor=pg.next_cursor
        rl=s.rate_limit
        if rl and rl.remaining<150: time.sleep(5)
        time.sleep(0.4)
        if not cursor or not len(pg): break
print('accounts',n,'secs',round(time.time()-t0))
