#!/usr/bin/env python
"""HPC 训练监控 — 用法: python hpc_monitor.py [job_id]"""
import paramiko, warnings, sys, argparse
warnings.filterwarnings('ignore')

HOST = 'dtn.hpc.xjtlu.edu.cn'
USER = 'jiayu2403'
PASSWD = 'pxXd3VGhbB'
LOG_DIR = '/gpfs/work/bio/jiayu2403/mambavision/logs'

def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWD, timeout=15)
    return c

def run(c, cmd):
    _, o, e = c.exec_command(cmd)
    out = o.read().decode('utf-8', errors='replace').strip()
    err = e.read().decode('utf-8', errors='replace').strip()
    return out, err

def monitor(job_id=None):
    c = connect()

    print("=" * 60)
    print("=== GPU 队列状态 ===")
    out, _ = run(c, "sinfo -p gpu4090 --format='%P %a %T %N' 2>&1")
    print(out)

    print("\n=== 我的任务 ===")
    out, _ = run(c, "squeue -u jiayu2403 --format='%.10i %.12j %.8T %.10M %.6D %R' 2>&1")
    print(out if out else "（无运行中的任务）")

    if job_id:
        print(f"\n=== Job {job_id} 详情 ===")
        out, _ = run(c, f"scontrol show job {job_id} 2>&1 | grep -E 'JobState|StartTime|RunTime|NodeList|Reason'")
        print(out)

        log_file = f"{LOG_DIR}/{job_id}.out"
        err_file = f"{LOG_DIR}/{job_id}.err"

        print(f"\n=== 日志末尾 ({log_file}) ===")
        out, _ = run(c, f"tail -30 {log_file} 2>&1")
        print(out if out else "（日志未生成，任务可能还在排队）")

        out2, _ = run(c, f"tail -10 {err_file} 2>&1")
        if out2 and 'No such file' not in out2:
            print(f"\n=== 错误日志末尾 ===")
            print(out2)

    print("=" * 60)
    c.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('job_id', nargs='?', default='1433437', help='SLURM Job ID')
    args = parser.parse_args()
    monitor(args.job_id)
