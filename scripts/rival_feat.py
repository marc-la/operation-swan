import json, datetime as dt, statistics as st, math, re, collections, random
from scipy import stats
T=lambda s: dt.datetime.fromisoformat(s.replace('Z','+00:00'))
SP='data/rival_census'
ours={a for v in json.load(open(SP+'/ours_all.json')).values() for a,u in v}
C={}
for l in open(SP+'/census.jsonl'):
    a=json.loads(l); C[a['account_id']]=a
now=dt.datetime.now(dt.timezone.utc)
recs={}
for f in ('pilot','rest'):
    for l in open(f'{SP}/{f}.jsonl'):
        r=json.loads(l)
        if r['account_id'] in ours or r['err'] or not r['posts']: continue
        recs[r['account_id']]=r
YES=re.compile(r'\b(vote yes|voting yes|support(ing)? (the )?(proof|requirement)|back the proof)\b',re.I)
NO=re.compile(r'\b(vote no|voting no|oppose|against (the )?(proof|requirement))\b',re.I)
rows=[]
for r in recs.values():
    P=r['posts']; ts=sorted(T(p['t']) for p in P)
    if len(P)<30: continue
    tx=[p['b'] or '' for p in P if p['k']!='repost']
    if len(tx)<15: continue
    gaps=[(b-a).total_seconds()/3600 for a,b in zip(ts,ts[1:])]
    span=(ts[-1]-ts[0]).total_seconds()/3600
    hrs=collections.Counter(t.hour for t in ts); tot=len(ts)
    ent=-sum(c/tot*math.log(c/tot) for c in hrs.values())/math.log(24)
    cr=T(C[r['account_id']]['created_at'])
    rows.append(dict(i=r['account_id'],n=len(P),trunc=bool(r['truncated']),idle=(now-ts[-1]).total_seconds()/3600,
      age=(now-cr).total_seconds()/3600,span=span,pace=len(P)/max(span,1),
      reply=sum(p['k']=='reply' for p in P)/len(P),repost=sum(p['k']=='repost' for p in P)/len(P),top=sum(p['k']=='post' for p in P)/len(P),
      chars=st.mean(len(t) for t in tx),q=sum('?' in t for t in tx)/len(tx),at=sum('@' in t for t in tx)/len(tx),
      hashtag=sum('#' in t for t in tx)/len(tx),giphy=sum(1 for p in P if p['e'])/len(P),
      emdash=sum('—' in t for t in tx)/len(tx),
      gapcv=(st.pstdev(gaps)/st.mean(gaps)) if gaps and st.mean(gaps)>0 else 0,hour_ent=ent,
      yes=sum(bool(YES.search(t)) for t in tx)/len(tx),no=sum(bool(NO.search(t)) for t in tx)/len(tx),
      uniq=len(set(tx))/len(tx)))
dead=[r for r in rows if r['idle']>=24]; alive=[r for r in rows if r['idle']<6]
print('accounts >=30 posts',len(rows),'dead',len(dead),'alive',len(alive))
print('feature | dead median | alive median | MWU p')
for k in ('n','pace','age','span','reply','repost','top','chars','q','at','hashtag','giphy','emdash','gapcv','hour_ent','yes','no','uniq'):
    a=[r[k] for r in dead]; b=[r[k] for r in alive]
    p=stats.mannwhitneyu(a,b).pvalue
    print(f'{k:8s} {st.median(a):8.3f} {st.median(b):8.3f}  p={p:.3g}')
# pace-matched: within pace tertiles
allp=sorted(r['pace'] for r in dead+alive); cuts=[allp[len(allp)//3],allp[2*len(allp)//3]]
print('\ndead share by pace tertile (posts/h):',[round(c,1) for c in cuts])
for lo,hi in ((0,cuts[0]),(cuts[0],cuts[1]),(cuts[1],1e9)):
    d=sum(lo<=r['pace']<hi for r in dead); a=sum(lo<=r['pace']<hi for r in alive); print(f'  {lo:.1f}-{hi:.1f}: dead {d} alive {a} dead share {d/(d+a):.2f}')
# logistic with pace control
import numpy as np
X=[];y=[]
keys=['pace','chars','reply','repost','q','at','hashtag','giphy','gapcv','hour_ent','yes','no','uniq']
for r in dead+alive:
    X.append([math.log(r['pace']+0.1)]+[r[k] for k in keys[1:]]); y.append(1 if r in dead else 0)
X=np.array(X); y=np.array(y); mu=X.mean(0); sd=X.std(0)+1e-9; Z=(X-mu)/sd
from scipy.optimize import minimize
def nll(w):
    z=Z@w[1:]+w[0]; return np.sum(np.log1p(np.exp(z))-y*z)+0.5*np.sum(w[1:]**2)
w=minimize(nll,np.zeros(Z.shape[1]+1)).x
print('\nridge logistic, death ~ standardized features (positive = more dead):')
for k,c in sorted(zip(['logpace']+keys[1:],w[1:]),key=lambda t:-abs(t[1])): print(f'  {k:9s} {c:+.2f}')
json.dump(rows,open(SP+'/feat_rows.json','w'),default=str)
