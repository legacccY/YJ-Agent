#!/usr/bin/env python
"""HPC 实时监控 — Ctrl+C 退出
用法: python hpc_watch.py [job_id] [间隔秒数]
"""
import paramiko, warnings, sys, time, os, argparse
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

def run(c, cmd, timeout=15):
    try:
        _, o, e = c.exec_command(cmd, timeout=timeout)
        return o.read().decode('utf-8', errors='replace').strip()
    except Exception as ex:
        return f"[err: {ex}]"

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def parse_train_line(line):
    """从日志行提取 epoch/step/loss/speed"""
    if 'Train:' in line and 'Loss:' in line:
        return line
    if 'Test:' in line and 'Acc@1:' in line:
        return line
    return None

def watch(job_id, interval):
    print(f"连接 HPC... (刷新间隔 {interval}s，Ctrl+C 退出)")
    c = connect()
    refresh = 0

    while True:
        try:
            clear()
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            print(f"╔══ HPC 实时监控  [{now}]  刷新#{refresh} ══╗")

            # 任务状态
            sq = run(c, f"squeue -u {USER} --format='%.10i %.12j %.8T %.10M %R'")
            print(f"\n【任务状态】\n{sq if sq else '无运行任务'}")

            # GPU 分配
            gpu_info = run(c, f"scontrol show job {job_id} 2>/dev/null | grep -E 'RunTime|TresPerNode|NodeList'")
            print(f"\n【资源分配】\n{gpu_info}")

            # 尝试通过 srun 获取 GPU 利用率
            gpu_util = run(c,
                f"srun --overlap --jobid={job_id} --nodes=1 "
                f"nvidia-smi --query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu "
                f"--format=csv,noheader,nounits 2>&1",
                timeout=10
            )
            if gpu_util and 'error' not in gpu_util.lower() and 'denied' not in gpu_util.lower():
                lines = gpu_util.strip().split('\n')
                print(f"\n【GPU 实时利用率】")
                print(f"  {'GPU':>3}  {'利用率':>6}  {'显存已用':>8}  {'显存总量':>8}  {'温度':>4}")
                for ln in lines:
                    parts = [x.strip() for x in ln.split(',')]
                    if len(parts) >= 5:
                        print(f"  {parts[0]:>3}  {parts[1]:>5}%  {parts[2]:>6}MB  {parts[3]:>6}MB  {parts[4]:>3}°C")
            else:
                print(f"\n【GPU 利用率】无法直连计算节点（需 key auth）")

            # 最新训练日志（过滤有用行）
            raw_log = run(c, f"tail -60 {LOG_DIR}/{job_id}.err 2>/dev/null")
            useful = [l for l in raw_log.split('\n') if parse_train_line(l)]
            print(f"\n【训练进度 - 最近记录】")
            if useful:
                for l in useful[-8:]:
                    print(f"  {l}")
            else:
                print("  （等待训练输出...）")

            # 日志总行数 = 进度估算
            nlines = run(c, f"wc -l {LOG_DIR}/{job_id}.err 2>/dev/null | awk '{{print $1}}'")
            print(f"\n  err 日志共 {nlines} 行")

            print(f"\n╚══ 下次刷新: {interval}s 后 ══╝")
            refresh += 1

        except KeyboardInterrupt:
            print("\n退出监控。")
            break
        except Exception as ex:
            print(f"\n连接断开，重连中... ({ex})")
            try:
                c.close()
            except:
                pass
            time.sleep(5)
            try:
                c = connect()
            except:
                pass

        time.sleep(interval)

    try:
        c.close()
    except:
        pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('job_id', nargs='?', default='1433437')
    parser.add_argument('interval', nargs='?', type=int, default=30)
    args = parser.parse_args()
    watch(args.job_id, args.interval)
