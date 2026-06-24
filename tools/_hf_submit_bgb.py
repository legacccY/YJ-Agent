import sys; sys.path.insert(0, "tools")
from _hf_hpc import conn, run, put
c = conn()
ROOT = "/gpfs/work/bio/jiayu2403/hyperfid"
for f in ["sbatch_braingb.sh", "hpc_setup_braingb.sh"]:
    put(c, f"project/meeting/HyperFidBench/{f}", f"{ROOT}/{f}")
    run(c, f"cd {ROOT} && sed -i 's/\\r$//' {f}")
# 清残缺 venv（dtn 半装的）
print(run(c, f"rm -rf {ROOT}/hf_braingb_venv && echo cleaned_venv"))
out = run(c, f"cd {ROOT} && sbatch sbatch_braingb.sh 2>&1")
print("SBATCH:", out.strip())
print(run(c, "squeue -u jiayu2403 -o '%.10i %.9P %.10j %.8T %.10M %R' 2>&1 | grep -iE 'hf_bgb|JOBID'"))
c.close()
