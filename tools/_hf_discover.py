import sys; sys.path.insert(0, "tools")
from _hf_hpc import conn, run
c = conn()
cmds = [
    ("conda/mamba", "which conda mamba 2>/dev/null; echo ---; conda env list 2>/dev/null | head -30"),
    ("cuda module", "module avail 2>&1 | tr ' ' '\\n' | grep -i cuda | head -15"),
    ("abide缓存", "find /gpfs/work/bio -maxdepth 3 -iname '*abide*' 2>/dev/null | head; ls /gpfs/work/bio/shared 2>/dev/null | head"),
    ("gpu/disk", "nvidia-smi -L 2>/dev/null | head -2; df -h /gpfs/work/bio/jiayu2403 2>/dev/null | tail -1"),
    ("现有env复用候选", "ls /gpfs/work/bio/jiayu2403/gdn2venv 2>/dev/null | head; ls /gpfs/work/bio/jiayu2403/*/bin/python 2>/dev/null | head"),
    ("python版本", "python --version 2>&1; python3 --version 2>&1"),
]
for name, cmd in cmds:
    print(f"\n===== {name} =====")
    print(run(c, cmd, timeout=90))
c.close()
print("DONE")
