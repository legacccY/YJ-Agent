import sys; sys.path.insert(0, "tools")
from _hf_hpc import conn, run, put
which = sys.argv[1] if len(sys.argv) > 1 else "braingb"
c = conn()
ROOT = "/gpfs/work/bio/jiayu2403/hyperfid"
for f in ["sbatch_buildenv.sh", "hpc_setup_braingb.sh", "hpc_setup_hypergale.sh"]:
    put(c, f"project/meeting/HyperFidBench/{f}", f"{ROOT}/{f}")
    run(c, f"cd {ROOT} && sed -i 's/\\r$//' {f}")
out = run(c, f"cd {ROOT} && sbatch sbatch_buildenv.sh {which} 2>&1")
print(f"SBATCH({which}):", out.strip())
print(run(c, "squeue -u jiayu2403 -o '%.10i %.9P %.12j %.8T %.10M %R' 2>&1 | grep -iE 'buildenv|JOBID'"))
c.close()
