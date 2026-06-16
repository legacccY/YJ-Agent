"""提交 GPU 任务：持续 matmul 占 GPU + 每 2s 写 experiment_state.json 心跳。
供 GUI 看「GPU 利用率」曲线 + 「训练心跳」曲线同时活。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.profiles import ProfileStore
from core.ssh_client import SSHClient
from core import slurm

s = ProfileStore(); p = s.get("XJTLU HPC (gpu4090)")
ssh = SSHClient(); ssh.connect(p, password=s.get_password(p), timeout=15)
WD = "/gpfs/work/bio/jiayu2403/test"
PY = "/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python"

# 确认 python 存在
chk = ssh.exec(f"test -x {PY} && echo Y || echo N").out.strip()
print("python exists:", chk, PY)

demo = '''import torch, time, json, os
sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "experiment_state.json")
os.makedirs(os.path.dirname(sp), exist_ok=True)
d = "cuda" if torch.cuda.is_available() else "cpu"
print("device", d, flush=True)
a = torch.randn(4096, 4096, device=d); b = torch.randn(4096, 4096, device=d)
for ep in range(1, 26):
    for _ in range(80):
        c = a @ b; a = c / (c.norm() + 1e-6)
    if d == "cuda": torch.cuda.synchronize()
    loss = 1.0 / ep; psnr = 20 + ep * 0.6
    json.dump({"status": "training", "epoch": ep, "train_loss": round(loss, 4),
               "val_psnr": round(psnr, 3), "device": d}, open(sp, "w"))
    print(f"epoch {ep} device={d} loss={loss:.4f} val_psnr={psnr:.3f}", flush=True)
    time.sleep(2)
print("DONE", flush=True)
'''
# 写 demo.py 到远端
ssh.exec(f"cat > {WD}/gpu_demo.py <<'PYEOF'\n{demo}\nPYEOF")
print("wrote gpu_demo.py")

spec = slurm.SbatchSpec(
    job_name="gpu_hb", account="shuihuawang", partition="gpudebug",
    qos="gpudebug", nodes=1, ntasks=1, cpus_per_task=4, gpus=1,
    time_limit="00:10:00", workdir=WD,
    command=f"{PY} gpu_demo.py")
r = slurm.submit_script(ssh, f"{WD}/submit_gpu.sh", slurm.build_sbatch(spec))
print("submit rc:", r.rc, "out:", r.out.strip(), "err:", r.err.strip())
print("jobid:", slurm.parse_submitted_job_id(r.out))
ssh.close()
