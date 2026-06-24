import sys, os, glob; sys.path.insert(0, "tools")
from _hf_hpc import conn, run, put
c = conn()
ROOT = "/gpfs/work/bio/jiayu2403/hyperfid"
LOCAL = "project/meeting/HyperFidBench"

print("=== 1. HPC 克隆 vendor repo ===")
print(run(c, f"mkdir -p {ROOT}/vendor && cd {ROOT}/vendor && "
            f"(test -d BrainGB || git clone --depth 1 https://github.com/HennyJie/BrainGB.git 2>&1 | tail -1) && "
            f"(test -d HyperGALE || git clone --depth 1 https://github.com/mehular0ra/HyperGALE.git 2>&1 | tail -1) && "
            f"ls", timeout=180))

print("=== 2. 上传 src 代码 ===")
for lane in ["braingb_lane", "hypergale_lane"]:
    run(c, f"mkdir -p {ROOT}/src/{lane}")
    for f in glob.glob(f"{LOCAL}/src/{lane}/*.py"):
        name = os.path.basename(f)
        put(c, f, f"{ROOT}/src/{lane}/{name}")
    print(f"  {lane}: uploaded {len(glob.glob(f'{LOCAL}/src/{lane}/*.py'))} py")

print("=== 3. 上传 abide.npy + split ===")
run(c, f"mkdir -p {ROOT}/vendor/BrainGB/examples/datasets/ABIDE {ROOT}/data/external/abide1")
put(c, f"{LOCAL}/vendor/BrainGB/examples/datasets/ABIDE/abide.npy", f"{ROOT}/vendor/BrainGB/examples/datasets/ABIDE/abide.npy")
put(c, f"{LOCAL}/vendor/BrainGB/examples/datasets/ABIDE/split_phenotypic.csv", f"{ROOT}/vendor/BrainGB/examples/datasets/ABIDE/split_phenotypic.csv")
put(c, f"{LOCAL}/data/external/abide1/split_indices.csv", f"{ROOT}/data/external/abide1/split_indices.csv")
print(run(c, f"ls -la {ROOT}/vendor/BrainGB/examples/datasets/ABIDE/ && du -sh {ROOT}/vendor/BrainGB/examples/datasets/ABIDE/abide.npy"))
# 去 CRLF for uploaded py
run(c, f"cd {ROOT}/src && find . -name '*.py' -exec sed -i 's/\\r$//' {{}} +")
c.close()
print("UPLOAD DONE")
