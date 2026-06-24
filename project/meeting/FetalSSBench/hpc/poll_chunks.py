#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""管理 FetalSSBench 10 chunk(method x dataset)在 QOS 限额(8提交/4跑)下跑完 150 run。
每轮：算进度(各 results_<m>_<ds>.csv 满15行=done) + 补提未跑未排的 chunk(在提交额内) + RUN_FAIL 检查。
输出 STATUS: PROGRESS <done>/150 submitted=<n> / ALLDONE 150/150 / FAIL <combos>"""
import paramiko, os
R="/gpfs/work/bio/jiayu2403/fetalss"
SC=r"C:\Users\yj200\AppData\Local\Temp\claude\D--YJ-Agent\f4261f6b-bb70-4a57-bee4-68009ddb5d3f\scratchpad"
METHODS=["supervised","mean_teacher","cps","uamt","fixmatch"]
DATASETS=["psfhs","hc18"]
COMBOS=[(m,d) for m in METHODS for d in DATASETS]  # 10
SUBMIT_CAP=8
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("dtn.hpc.xjtlu.edu.cn",username="jiayu2403",password="pxXd3VGhbB",timeout=30)
def run(cmd):
    i,o,e=c.exec_command(cmd); return o.read().decode(errors="replace"), e.read().decode(errors="replace")

# 1) 每 combo 完成行数(100ep 去重)
done_rows={}
for m,d in COMBOS:
    o,_=run(f"tail -n +2 {R}/code/results/results_{m}_{d}.csv 2>/dev/null | awk -F',' '$13==100' | sort -u | wc -l")
    done_rows[(m,d)]=int(o.strip() or 0)
total_done=sum(min(15,v) for v in done_rows.values())  # 每 combo 满 15
done_combos={k for k,v in done_rows.items() if v>=15}

# 2) 在飞 combo(队列里的 fss_ job)
o,_=run("squeue -u jiayu2403 -h -o '%j'")
inflight_names=set(o.split())
inflight_combos={(m,d) for m,d in COMBOS if f"fss_{m}_{d}" in inflight_names}
njobs=len([n for n in o.split() if n.strip()])

# 3) RUN_FAIL 检查
fo,_=run(f"grep -h RUN_FAIL {R}/logs/chunk_*.out 2>/dev/null | sort -u | head")
fails=[l for l in fo.splitlines() if l.strip()]

# 4) 补提:既没done也没在飞的 combo,在提交额内
todo=[(m,d) for m,d in COMBOS if (m,d) not in done_combos and (m,d) not in inflight_combos]
submitted_now=[]
slots=SUBMIT_CAP-njobs
if slots>0 and todo:
    # 确保 sbatch_chunk.sh 在(已传过,跳过重传)
    for m,d in todo[:slots]:
        o2,e2=run(f"cd {R} && sbatch --job-name=fss_{m}_{d} --export=ALL,M={m},DS={d} sbatch_chunk.sh")
        if "Submitted" in o2: submitted_now.append(f"{m}_{d}")
        else: print(f"[submit fail {m}_{d}]", (o2+e2).strip()[:80])

print(f"[chunks] done_combos={len(done_combos)}/10 inflight={len(inflight_combos)} njobs={njobs} todo={len(todo)} submitted_now={submitted_now}")
print(f"[rows] " + " ".join(f"{m[:3]}_{d[:2]}={done_rows[(m,d)]}" for m,d in COMBOS))
if total_done>=150:
    print("STATUS: ALLDONE 150/150")
elif fails:
    print(f"STATUS: FAIL {len(fails)} (见 logs/chunk_*.out) PROGRESS {total_done}/150")
else:
    print(f"STATUS: PROGRESS {total_done}/150 submitted={len(submitted_now)} inflight={len(inflight_combos)}")
c.close()
