import json, datetime as dt, statistics as st, collections, sys, glob
T=lambda s: dt.datetime.fromisoformat(s.replace('Z','+00:00'))
ours={a for v in json.load(open('data/rival_census/ours_all.json')).values() for a,u in v}
C={}
for l in open('data/rival_census/census.jsonl'):
    a=json.loads(l); C[a['account_id']]=a
now=dt.datetime.now(dt.timezone.utc)
recs={}
for f in ('data/rival_census/pilot.jsonl','data/rival_census/rest.jsonl'):
    for l in open(f):
        r=json.loads(l)
        if r['account_id'] in ours or r['err']: continue
        recs[r['account_id']]=r
rows=[]
for r in recs.values():
    P=r['posts']
    if not P: rows.append(dict(i=r['account_id'],n=0)); continue
    ts=sorted(T(p['t']) for p in P)
    gaps=[(b-a).total_seconds()/3600 for a,b in zip(ts,ts[1:])]
    age=(now-T(C[r['account_id']]['created_at'])).total_seconds()/3600
    trunc = r['truncated'] or len(P)>=100
    span=(ts[-1]-ts[0]).total_seconds()/3600
    rows.append(dict(i=r['account_id'],n=len(P),trunc=trunc,idle=(now-ts[-1]).total_seconds()/3600,age=age,span=span,
        med_gap=st.median(gaps) if gaps else None,pace=len(P)/max(span,1.0),
        reply=sum(p['k']=='reply' for p in P)/len(P),rep=sum(p['k']=='repost' for p in P)/len(P),
        first_lag=(ts[0]-T(C[r['account_id']]['created_at'])).total_seconds()/3600))
print('accounts sampled',len(rows))
z=[r for r in rows if r['n']==0]; print('never posted',len(z),f'({len(z)/len(rows):.0%})')
act=[r for r in rows if r['n']>=10]
print('with >=10 posts',len(act))
# death: idle >= 24h (and >=10 posts)
dead=[r for r in act if r['idle']>=24]; alive=[r for r in act if r['idle']<6]; mid=[r for r in act if 6<=r['idle']<24]
print('dead(idle>=24h)',len(dead),'alive(idle<6h)',len(alive),'unclear',len(mid))
# KM on posts-to-death, censored at 100 when truncated
ev=[]
for r in act:
    w=r['n']; d=(r['idle']>=24)
    if r['trunc']: ev.append((100,False))   # >=100: censor at 100 (first page only)
    else: ev.append((w,d))
ev.sort()
S=1.0; atrisk=len(ev); out=[]
i=0
while i<len(ev):
    w=ev[i][0]; dd=sum(1 for e in ev[i:] if e[0]==w and e[1]); cc=sum(1 for e in ev[i:] if e[0]==w)
    if dd: S*=1-dd/atrisk; out.append((w,round(S,3),atrisk))
    atrisk-=cc; i+=cc
for q in (10,20,30,50,75,99):
    s=[x for x in out if x[0]<=q]; print(f'S({q} posts) ~', s[-1][1] if s else 1.0)
print('share of >=10-post accounts reaching 100 posts:',sum(r['trunc'] for r in act)/len(act))
print('of those reaching 100: idle<6h',sum(1 for r in act if r['trunc'] and r['idle']<6),' idle>=24h',sum(1 for r in act if r['trunc'] and r['idle']>=24))
