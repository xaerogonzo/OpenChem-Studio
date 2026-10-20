"""Diagnostics of a finished quality run (`PREREGISTRATION.md`): what the stored results say beyond the four claims. REPORTED, DECIDING NOTHING: the verdict is `run_quality.py report`'s and is never moved by these numbers.

    python diagnostics.py --paroutes DIR [--artifacts DIR]

Uses the same matching (`route_match.py`) as the verdict; the relaxed measures (best leaf overlap, fraction of the reference's reactions found) are credit the strict rule does not give.
"""
import argparse, json, sys, statistics
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import route_match as m
ap = argparse.ArgumentParser(description='Diagnostics of a finished quality run (reported, deciding nothing).')
ap.add_argument('--paroutes', required=True)
ap.add_argument('--artifacts', default=str(HERE / 'artifacts'))
args = ap.parse_args()
A = Path(args.artifacts)
ref=json.load(open(r'D:\_scratch\aizynth\paroutes\ref_routes_n1.json'))
rows=[json.loads(l) for l in open(A / 'results_r1.jsonl', encoding='utf-8')]
n=len(rows)
solved=[r for r in rows if r['statistics']['is_solved']]
cnt=[r['route_count'] for r in rows]
print('targets',n,'solved',len(solved))
print('routes returned: median',statistics.median(cnt),'min',min(cnt),'max',max(cnt),'share with >=10:',sum(1 for c in cnt if c>=10)/n)
rec10=[m.recovered_at(r['routes'],ref[r['id']],10) for r in rows]
print('recovered@10 overall',sum(rec10)/n,'| among solved',sum(1 for r,x in zip(rows,rec10) if x and r['statistics']['is_solved'])/len(solved))
# relaxed diagnostics on the first 10 routes
def best(r, f):
    return max((f(rt, ref[r['id']]) for rt in r['routes'][:10]), default=0.0)
def reaction_frac(p, q):
    a,b=m.reactions_of(p), m.reactions_of(q); return len(a&b)/len(b) if b else 0.0
lo=[best(r,m.leaf_overlap) for r in rows]; rf=[best(r,reaction_frac) for r in rows]
print('any of first 10 has leaf overlap 1.0 (same starting materials):', sum(1 for x in lo if x>=0.999)/n)
print('mean best leaf overlap in first 10:', round(sum(lo)/n,3), '| mean best fraction of reference reactions found in first 10:', round(sum(rf)/n,3))
print('any of first 10 contains >=50% of the reference reactions:', sum(1 for x in rf if x>=0.5)/n, '; >=75%:', sum(1 for x in rf if x>=0.75)/n)
# by reference depth
def depth(nd):
    ch=nd.get('children') or []
    return max([depth(c) for c in ch],default=0) if nd['type']=='mol' else 1+max([depth(c) for c in ch],default=0)
import collections
by=collections.defaultdict(lambda:[0,0,0])
for r,x in zip(rows,rec10):
    d=min(depth(ref[r['id']]),6); by[d][0]+=1; by[d][1]+=x; by[d][2]+=r['statistics']['is_solved']
print('by reference depth (6 = 6 or more): depth: targets, recovered@10, solved'); 
for d in sorted(by): print('  ',d,by[d][0],round(by[d][1]/by[d][0],2),round(by[d][2]/by[d][0],2))
# one-step reference routes depth>=2 always (set min is 2)
# stability noise floor
r2={json.loads(l)['id']:json.loads(l) for l in open(A / 'results_r2.jsonl', encoding='utf-8')}
r3={json.loads(l)['id']:json.loads(l) for l in open(A / 'results_r3.jsonl', encoding='utf-8')}
r1={r['id']:r for r in rows}
spread=[]; 
for i in r2:
    rc=[x[i]['route_count'] for x in (r1,r2,r3)]; nd=[x[i]['statistics']['number_of_nodes'] for x in (r1,r2,r3)]; t=[x[i]['seconds'] for x in (r1,r2,r3)]
    rec=[m.recovered_at(x[i]['routes'],ref[i],10) for x in (r1,r2,r3)]
    spread.append((rc,nd,t,rec))
print('stability: recovered@10 identical across 3 runs on',sum(1 for s in spread if len(set(s[3]))==1),'of 20; route counts differ on',sum(1 for s in spread if len(set(s[0]))>1),'of 20; node counts differ on',sum(1 for s in spread if len(set(s[1]))>1),'of 20')
print('median relative spread of seconds across the 3 runs:', round(statistics.median([(max(s[2])-min(s[2]))/statistics.mean(s[2]) for s in spread]),2))
print('unsolved targets:',[ (r['id'],depth(ref[r['id']])) for r in rows if not r['statistics']['is_solved']])
print('time s: median',statistics.median([r['seconds'] for r in rows]),'mean',round(statistics.mean([r['seconds'] for r in rows]),1),'max',max(r['seconds'] for r in rows),'; peak MB',max(r['peak_working_set_mb'] for r in rows))
print('first-solution iteration median (solved):',statistics.median([r['statistics']['first_solution_iteration'] for r in solved]))
