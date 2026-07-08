"""slice_dtu HPC 编排（用户 2026-07-07 授权连 HPC 跑 stabpan/NetTepi/ICERFIRE）。
step=assess: 只读评估 3 工具部署状态 + rerun 目录是否已上传。
step=upload: sftp 上传 dtu_netmhcpan_inputs(.pep) + icerfire_inputs 到 HPC rerun 区。
不改数据、不删。CPU 工具走 cpudebug，不占 GPU 卡槽。"""
import sys, re, pathlib, paramiko, warnings
warnings.filterwarnings('ignore')
ROOT = pathlib.Path("D:/YJ-Agent")
t = (ROOT/"project/HPC_WORKFLOW.md").read_text(encoding="utf-8")
HOST = re.search(r'`([\w.]+\.xjtlu\.edu\.cn)`', t).group(1)
USER = re.search(r'用户名.*?`([^`]+)`', t).group(1)
PWD  = re.search(r'密码.*?`([^`]+)`', t).group(1)
QD = '/gpfs/work/bio/jiayu2403/quantimmu'
RERUN = f'{QD}/rerun'
STEP = sys.argv[1] if len(sys.argv) > 1 else 'assess'
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PWD, timeout=30)
def run(cmd, tt=120):
    _,o,e = c.exec_command(cmd, timeout=tt)
    return (o.read().decode('utf-8','replace')+e.read().decode('utf-8','replace')).strip()
print(f"[HPC] {HOST} connected  step={STEP}")

if STEP == 'assess':
    print("=== rerun 目录 (别窗上传?) ===")
    print(run(f'ls -d {RERUN} {QD}/scripts/out_rerun 2>/dev/null || echo NO_RERUN_DIR'))
    print("=== netMHCstabpan-1.0 binary + netMHCpan-2.8 后端 ===")
    print(run(f'ls {QD}/ext_tools/netMHCstabpan-1.0/netMHCstabpan {QD}/ext_tools/netMHCpan-2.8/netMHCpan 2>&1'))
    print("=== netMHCstabpan 真机烟测(等长9mer,核输出肽=输入肽) ===")
    print(run(f'cd /tmp && printf "RDPLSEITK\\n" > s9.pep && export NMHOME={QD}/ext_tools/netMHCstabpan-1.0 && {QD}/ext_tools/netMHCstabpan-1.0/netMHCstabpan -a HLA-A02:01 -l 9 -p /tmp/s9.pep 2>/dev/null | grep PEPLIST | head -2'))
    print("=== ICERFIRE dir + bashscripts + qib_icerfire env ===")
    print(run(f'ls -d {QD}/ext_tools/ICERFIRE 2>/dev/null && echo IC_DIR_OK || echo IC_DIR_MISS; ls {QD}/ext_tools/ICERFIRE/bashscripts/ICERFIRE.sh 2>/dev/null; ls -d {QD}/envs/qib_icerfire 2>/dev/null && echo ICENV_OK || echo ICENV_MISS'))
    print("=== NetTepi bin + qib_py27/qib_perl ===")
    print(run(f'find {QD} -maxdepth 4 -iname "netTepi*" 2>/dev/null | head; ls -d {QD}/envs/qib_py27 {QD}/envs/qib_perl 2>/dev/null; echo "--- old nettepi_out ---"; ls {QD}/nettepi_run 2>/dev/null | head -3'))
    print("=== 旧 official DTU 跑法参考(nettepi/icerfire run 目录) ===")
    print(run(f'ls -d {QD}/icerfire_run {QD}/nettepi_run 2>/dev/null'))
    print("=== cpudebug 队列 ===")
    print(run('sinfo -s 2>/dev/null | grep -iE "cpudebug|debug" | head'))

elif STEP == 'submit':
    # 先核 netMHCcons(NetTepi 依赖)
    print("=== netMHCcons-1.1 (NetTepi dep) ===")
    print(run(f'ls {QD}/ext_tools/netMHCcons-1.1/netMHCcons 2>/dev/null && echo CONS_OK || echo CONS_MISS'))
    sftp = c.open_sftp()
    run(f'mkdir -p {RERUN}/logs {RERUN}/stab_out {RERUN}/nettepi_out')
    local_sh = ROOT/"project/meeting/QuantImmuBench/scripts/out_rerun/_hpc_run_all.sh"
    sftp.put(str(local_sh), f'{RERUN}/run_all.sh')
    print(run(f'sed -i "s/\\r$//" {RERUN}/run_all.sh; echo SH_OK'))
    # setsid 后台跑，防 channel 关闭中断
    print(run(f'cd {RERUN} && setsid bash run_all.sh </dev/null >{RERUN}/logs/run_all.log 2>&1 & echo LAUNCHED pid=$!'))
    sftp.close()

elif STEP == 'poll':
    print(run(f'echo "=== run_all.log tail ==="; tail -15 {RERUN}/logs/run_all.log 2>/dev/null; echo "=== outputs ==="; echo "stab xls: $(ls {RERUN}/stab_out/*_stab.xls 2>/dev/null | wc -l)"; echo "nettepi txt: $(ls {RERUN}/nettepi_out/*_nettepi.txt 2>/dev/null | wc -l)"; echo "icerfire scored: $(find {QD}/ext_tools/ICERFIRE/bashscripts {RERUN}/icerfire_inputs -name "icerfire_input_scored_output*" 2>/dev/null | head)"; echo "=== stabpan proc alive? ==="; pgrep -af "netMHCstabpan|netTepi|ICERFIRE|run_all" | head -4'))

elif STEP == 'dlic':
    src = run(f'find {QD}/ext_tools/ICERFIRE/output -name "ICERFIRE_predictions.csv" -newermt "2026-07-07 18:40" 2>/dev/null | head -1').strip()
    print("src:", src)
    print("rows:", run(f'wc -l "{src}"'))
    print("head:", run(f'head -2 "{src}"'))
    sftp = c.open_sftp()
    dst = ROOT/"project/meeting/QuantImmuBench/scripts/out_rerun/icerfire_inputs/ICERFIRE_predictions.csv"
    sftp.get(src, str(dst)); sftp.close()
    print("[dlic] downloaded →", dst)

elif STEP == 'findic':
    print("=== 搜 ICERFIRE_predictions.csv (今天改动) ===")
    print(run(f'find {QD}/ext_tools/ICERFIRE {RERUN} -iname "*prediction*" -newermt "2026-07-07 18:40" 2>/dev/null | head'))
    print("=== ICERFIRE.sh 里输出文件名/output 目录约定 ===")
    print(run(f'grep -nE "predictions|scored|output|OUTFILE|OUTPUT|\\.csv" {QD}/ext_tools/ICERFIRE/bashscripts/ICERFIRE.sh 2>/dev/null | head -20'))
    print("=== ICERFIRE 目录下今天新文件 ===")
    print(run(f'find {QD}/ext_tools/ICERFIRE -newermt "2026-07-07 18:40" -type f 2>/dev/null | grep -avE "/tmp/|__pycache__" | head -20'))

elif STEP == 'iclog':
    print("=== icerfire.log 全 tail(去进度条) ===")
    print(run(f'grep -avE "it/s|Eval Folds|\\[A" {RERUN}/logs/icerfire.log 2>/dev/null | tail -40'))
    print("=== 任何 Traceback/Error ===")
    print(run(f'grep -aiE "error|traceback|exception|killed|no such|cannot|fail|memoryerror|segmentation" {RERUN}/logs/icerfire.log 2>/dev/null | tail -20'))
    print("=== run_all.log tail ===")
    print(run(f'tail -12 {RERUN}/logs/run_all.log 2>/dev/null'))
    print("=== tmp 中间产物 ===")
    print(run(f'ls -la {QD}/ext_tools/ICERFIRE/tmp/N4q8C/ 2>/dev/null | tail -15; echo "---bashscripts scored?---"; ls {QD}/ext_tools/ICERFIRE/bashscripts/*scored* 2>/dev/null'))

elif STEP == 'wait_icerfire':
    # HPC 端循环等 scored_output 出现（或进程结束），单 SSH 命令内轮询防 channel 反复建连
    cmd = (f'for i in $(seq 1 90); do '
           f'f=$(find {QD}/ext_tools/ICERFIRE/bashscripts {RERUN}/icerfire_inputs -name "icerfire_input_scored_output*" 2>/dev/null | head -1); '
           f'if [ -n "$f" ]; then echo "SCORED_READY $f"; wc -l "$f"; break; fi; '
           f'if ! pgrep -f "ICERFIRE.sh|netmhcpan_pipeline|pep_kernel_dist" >/dev/null; then echo "PROC_GONE_NO_OUTPUT"; tail -8 {RERUN}/logs/icerfire.log; break; fi; '
           f'sleep 40; done; echo POLL_END')
    print(run(cmd, tt=4000))

elif STEP == 'nettepi':
    sftp = c.open_sftp()
    local_sh = ROOT/"project/meeting/QuantImmuBench/scripts/out_rerun/_hpc_nettepi_only.sh"
    sftp.put(str(local_sh), f'{RERUN}/nettepi_only.sh')
    sftp.close()
    print(run(f'sed -i "s/\\r$//" {RERUN}/nettepi_only.sh; echo SH_OK'))
    print(run(f'cd {RERUN} && bash nettepi_only.sh 2>&1 | tail -20', tt=600))

elif STEP == 'diag':
    print("=== nettepi 支持等位 (alleles.lst) ===")
    print(run(f'cat {QD}/ext_tools/netTepi-1.0/alleles.lst 2>/dev/null | tr "\\n" " "'))
    print("=== nettepi txt/err 文件 ===")
    print(run(f'ls -la {RERUN}/nettepi_out/ 2>/dev/null | head'))
    print("=== 一个 nettepi .err 内容 ===")
    print(run(f'for e in {RERUN}/nettepi_out/*_nettepi.err; do echo "--- $e ---"; tail -8 "$e"; break; done'))
    print("=== 一个 nettepi .txt 内容 ===")
    print(run(f'for t in {RERUN}/nettepi_out/*_nettepi.txt; do echo "--- $t ---"; head -6 "$t"; break; done'))
    print("=== ICERFIRE 进度 ===")
    print(run(f'tail -6 {RERUN}/logs/icerfire.log 2>/dev/null; echo "scored?"; find {QD}/ext_tools/ICERFIRE/bashscripts {RERUN}/icerfire_inputs -name "icerfire_input_scored_output*" 2>/dev/null; pgrep -af "ICERFIRE|pep_kernel|netmhcpan_pipeline" | head -3'))

elif STEP == 'download':
    sftp = c.open_sftp()
    outdir = ROOT/"project/meeting/QuantImmuBench/scripts/out_rerun"
    (outdir/"stab_out").mkdir(exist_ok=True); (outdir/"nettepi_out").mkdir(exist_ok=True)
    # stab xls
    for fn in run(f'ls {RERUN}/stab_out/*_stab.xls 2>/dev/null').split():
        sftp.get(fn, str(outdir/"stab_out"/pathlib.Path(fn).name))
    # nettepi txt
    for fn in run(f'ls {RERUN}/nettepi_out/*_nettepi.txt 2>/dev/null').split():
        sftp.get(fn, str(outdir/"nettepi_out"/pathlib.Path(fn).name))
    # icerfire scored
    ic = run(f'find {QD}/ext_tools/ICERFIRE/bashscripts {RERUN}/icerfire_inputs -name "icerfire_input_scored_output*" 2>/dev/null | head -1')
    if ic.strip():
        sftp.get(ic.strip(), str(outdir/"icerfire_inputs"/"icerfire_input_scored_output"))
        print(f"[download] icerfire scored ← {ic.strip()}")
    print(f"[download] stab={len(list((outdir/'stab_out').glob('*_stab.xls')))} nettepi={len(list((outdir/'nettepi_out').glob('*_nettepi.txt')))}")
    sftp.close()

elif STEP == 'upload':
    sftp = c.open_sftp()
    run(f'mkdir -p {RERUN}/dtu_netmhcpan_inputs {RERUN}/icerfire_inputs {RERUN}/logs')
    # 上传 dtu_netmhcpan_inputs: 所有 .pep + allele_map.tsv + pep_index.csv
    base = ROOT/"project/meeting/QuantImmuBench/scripts/out_rerun"
    dtu = base/"dtu_netmhcpan_inputs"
    n = 0
    for f in sorted(dtu.glob("*.pep")) + [dtu/"allele_map.tsv", dtu/"pep_index.csv"]:
        sftp.put(str(f), f'{RERUN}/dtu_netmhcpan_inputs/{f.name}'); n += 1
    print(f"[upload] dtu_netmhcpan_inputs: {n} files")
    ic = base/"icerfire_inputs"
    for f in [ic/"icerfire_input.csv", ic/"icerfire_index.csv"]:
        sftp.put(str(f), f'{RERUN}/icerfire_inputs/{f.name}')
    print("[upload] icerfire_inputs: 2 files")
    # CRLF strip on HPC
    print(run(f'cd {RERUN}/dtu_netmhcpan_inputs && sed -i "s/\\r$//" *.pep allele_map.tsv 2>/dev/null; cd {RERUN}/icerfire_inputs && sed -i "s/\\r$//" *.csv 2>/dev/null; echo STRIP_DONE'))
    print(run(f'echo "pep files:"; ls {RERUN}/dtu_netmhcpan_inputs/*.pep | wc -l; echo "icerfire rows:"; wc -l {RERUN}/icerfire_inputs/icerfire_input.csv'))
    sftp.close()

c.close()
print("DONE")
