# One voice's life under the 3-ruled-hides rule (hide route only; i.i.d. hides): mean writes per account by write rate and stop policy.
# Offline model, no platform calls. See todo/40 and docs/06-strategy/hide-risk-analysis-2026-10-23.md. python scripts/life_sim.py
# Monte Carlo of one voice's life under the hide route only (3 ruled hides = banned).
# Model: each write hidden w.p. p; a hide becomes visible/ruled LAG h after the write; ban at the ruling of the 3rd hide.
# Optional account route: after the first RULED hide, ban after an extra Exp-distributed delay (mean ACC h) with prob PACC.
import random, statistics as st, sys
LAG=3.3
def life(R,p,policy,acc=None,rng=random):
    t=0.0; hides=[]  # times hides were written
    writes=0; pause_until=0.0; acc_ban=None
    while True:
        # ban check: the third hide ruled
        ruled=sorted(h+LAG for h in hides)
        if len(ruled)>=3 and t>=ruled[2]: return writes
        if acc_ban is not None and t>=acc_ban: return writes
        if acc is not None and acc_ban is None and ruled and t>=ruled[0]:
            if rng.random()<acc[1]: acc_ban=ruled[0]+rng.expovariate(1/acc[0])
            else: acc_ban=float('inf')
        vis=sum(1 for r in ruled if t>=r)
        if policy=='stop1' and vis>=1 and t<max(r for r in ruled if t>=r)+3.5:
            t+=0.1; continue
        gap=1.0/R
        t+=gap
        writes+=1
        if rng.random()<p: hides.append(t)
        if t>400: return writes
def run(R,p=0.014,policy='burn',acc=None,n=4000):
    random.seed(1)
    return st.mean(life(R,p,policy,acc) for _ in range(n))
print('hide route only, p=1.4%  (mean writes per account)')
print('R/h   burn  stop1')
for R in (2,4,8,15,25,40,80,180):
    print(f'{R:4d} {run(R):6.0f} {run(R,policy="stop1"):6.0f}')
print('\nwith account route: after first ruled hide, 50% chance a report lands, ban ~Exp(mean 6h) later')
print('R/h   burn  stop1')
for R in (2,4,8,15,25,40,80):
    print(f'{R:4d} {run(R,acc=(6,0.5)):6.0f} {run(R,policy="stop1",acc=(6,0.5)):6.0f}')
print('\np sensitivity at R=8, burn / R=25 burn')
for p in (0.003,0.006,0.01,0.014):
    print(p, round(run(8,p)), round(run(25,p)))
