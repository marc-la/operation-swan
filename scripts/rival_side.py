import json, re, collections, statistics as st, datetime as dt, math
SP='data/rival_census'
T=lambda s: dt.datetime.fromisoformat(s.replace('Z','+00:00'))
rows={r['i']:r for r in json.load(open(SP+'/feat_rows.json'))}
recs={}
for f in ('pilot','rest'):
    for l in open(f'{SP}/{f}.jsonl'):
        r=json.loads(l)
        if r['account_id'] in rows: recs[r['account_id']]=r
YES=re.compile(r"(vote yes|voting yes|i('| a)?m (a )?yes|back(ing)? (the )?(proof|requirement)|support(ing)? (the )?(proof|vaccination proof|requirement)|in favou?r of (the )?(proof|requirement))",re.I)
NO=re.compile(r"(vote no|voting no|i('| a)?m (a )?no\b|oppose|against (the )?(proof|requirement|mandate)|keep kingstonia open|protect choice)",re.I)
for i,r in rows.items():
    tx=[(p['b'] or '') for p in recs[i]['posts'] if p['k']!='repost']
    y=sum(bool(YES.search(t)) for t in tx); n=sum(bool(NO.search(t)) for t in tx)
    r['ny'],r['nn']=y,n
    r['side']='YES' if y>=3 and y>2*n else 'NO' if n>=3 and n>2*y else 'mixed/none'
    r['state']='dead' if r['idle']>=24 else 'alive' if r['idle']<6 else 'unclear'
print('side classification of accounts with >=30 posts:',collections.Counter(r['side'] for r in rows.values()))
pc=sorted(r['pace'] for r in rows.values()); c1,c2=pc[len(pc)//3],pc[2*len(pc)//3]
print('\nside x state, and dead share among dead+alive, by pace tertile')
for side in ('YES','NO','mixed/none'):
    for name,lo,hi in (('slow',0,c1),('mid',c1,c2),('fast',c2,1e9),('all',0,1e9)):
        d=sum(1 for r in rows.values() if r['side']==side and r['state']=='dead' and lo<=r['pace']<hi)
        a=sum(1 for r in rows.values() if r['side']==side and r['state']=='alive' and lo<=r['pace']<hi)
        print(f'  {side:10s} {name:4s} dead {d:3d} alive {a:3d}  dead share {d/(d+a) if d+a else float("nan"):.2f}')
# how many explicit sayers
print('\nexplicit stance posts in sample: yes',sum(r['ny'] for r in rows.values()),'no',sum(r['nn'] for r in rows.values()))

print('\n===== explicit-statement rate, within side =====')
for r in rows.values():
    tx=[(p['b'] or '') for p in recs[r['i']]['posts'] if p['k']!='repost']
    r['expl']=(r['ny']+r['nn'])/max(len(tx),1)
    r['nn_rate']=r['nn']/max(len(tx),1); r['ny_rate']=r['ny']/max(len(tx),1)
for side in ('NO','YES'):
    for name,lo,hi in (('mid+fast',c1,1e9),):
        d=[r['expl'] for r in rows.values() if r['side']==side and r['state']=='dead' and lo<=r['pace']<hi]
        a=[r['expl'] for r in rows.values() if r['side']==side and r['state']=='alive' and lo<=r['pace']<hi]
        print(side,name,'explicit-stance share of posts: dead median',round(st.median(d),2),'(n',len(d),') alive median',round(st.median(a),2),'(n',len(a),')')
# age control: dead share among NO fast by account age tercile
import statistics
ages=sorted(r['age'] for r in rows.values()); a1,a2=ages[len(ages)//3],ages[2*len(ages)//3]
print('\nNO/YES, mid+fast pace, by account age tercile (h):',round(a1),round(a2))
for side in ('NO','YES'):
    for name,lo,hi in (('young',0,a1),('mid',a1,a2),('old',a2,1e9)):
        d=sum(1 for r in rows.values() if r['side']==side and r['state']=='dead' and r['pace']>=c1 and lo<=r['age']<hi)
        a=sum(1 for r in rows.values() if r['side']==side and r['state']=='alive' and r['pace']>=c1 and lo<=r['age']<hi)
        print(f'  {side} {name:5s} dead {d:3d} alive {a:3d} share {d/(d+a) if d+a else float("nan"):.2f}')
print('\nthe NO-side accounts that are fast and still alive:')
for r in rows.values():
    if r['side']=='NO' and r['state']=='alive' and r['pace']>=c2:
        print(' ',r['i'],'n',r['n'],'pace',round(r['pace'],1),'age',round(r['age']),'explicit',round(r['expl'],2),'reply',round(r['reply'],2),'repost',round(r['repost'],2),'chars',round(r['chars']))
# logistic: dead ~ log pace + NO + expl + age
import numpy as np
from scipy.optimize import minimize
D=[r for r in rows.values() if r['state'] in('dead','alive')]
X=np.array([[math.log(r['pace']+.1),1.0 if r['side']=='NO' else 0.0,1.0 if r['side']=='YES' else 0.0,r['expl'],r['age']/24,r['repost'],r['uniq']] for r in D]); y=np.array([1.0 if r['state']=='dead' else 0.0 for r in D])
mu=X.mean(0); sd=X.std(0)+1e-9; Z=(X-mu)/sd
nll=lambda w: np.sum(np.log1p(np.exp(Z@w[1:]+w[0]))-y*(Z@w[1:]+w[0]))+0.5*np.sum(w[1:]**2)
w=minimize(nll,np.zeros(Z.shape[1]+1)).x
print('\nridge logistic (standardised): ',dict(zip(['logpace','side_NO','side_YES','explicit','age_d','repost','uniq'],np.round(w[1:],2))))
