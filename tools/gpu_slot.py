#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GPU 卡槽调度器 —— YJ-Agent 组合台训练并发管理。

取代旧「全局单锁」（任何卡都互斥，一个训练阻断全部）。改为**按卡记账**：
  - local = 1 卡（RTX 4070 Laptop 8GB），实际单槽
  - hpc   = 4 卡（gpu4090 分区 / QOS 4gpus）
多任务可共存，只要某 host 空闲卡 >= 申请卡数；**绝不挤正在跑的**。
卡满 -> 排队（queue）；有卡 release 后，按 FIFO 取出第一个放得下的排队任务交主线起。

真源 = .portfolio/locks/training.lock（schema v2）。training_lock.js hook 读同一文件放行/阻断。

用法（主线启训前后调用，不要手改 JSON）：
  python tools/gpu_slot.py request <project> <host> <gpus> [note]
      申请卡槽。够 -> 写 starting 条目 + 打印 "GO <id>"；不够 -> 入队 + 打印 "QUEUED <id> ..."
  python tools/gpu_slot.py release <id|project>
      任务结束清账。打印释放结果 + 每个现在放得下的排队任务 "NEXT <id> <project> <host> <gpus> :: <note>"
  python tools/gpu_slot.py status
      人读视图：每 host 占用/空闲 + active + queue
  python tools/gpu_slot.py list
      原始 JSON
  python tools/gpu_slot.py reap
      清理 active 中 pid 已死的 local 条目（陈旧锁），打印清掉了哪些

host 取值：local | hpc
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta

LOCK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.portfolio', 'locks', 'training.lock'))
CAP = {"local": 1, "hpc": 4}
CN_TZ = timezone(timedelta(hours=8))


def now():
    return datetime.now(CN_TZ).isoformat(timespec='seconds')


def load():
    try:
        with open(LOCK, encoding='utf-8') as f:
            d = json.load(f)
        if not isinstance(d, dict):
            d = {}
    except Exception:
        d = {}
    d.setdefault("schema_version", 2)
    d.setdefault("capacity", dict(CAP))
    d.setdefault("active", [])
    d.setdefault("queue", [])
    return d


def save(d):
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    with open(LOCK, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def used(d, host):
    return sum(int(j.get("gpus", 1)) for j in d["active"]
               if j.get("host") == host and j.get("status") in ("running", "starting"))


def free(d, host):
    return int(d["capacity"].get(host, 0)) - used(d, host)


def cmd_request(project, host, gpus, note=""):
    if host not in CAP:
        print(f"ERR unknown host '{host}' (need local|hpc)")
        return 2
    gpus = int(gpus)
    d = load()
    jid = uuid.uuid4().hex[:8]
    f = free(d, host)
    if f >= gpus:
        d["active"].append({
            "id": jid, "project": project, "host": host, "gpus": gpus,
            "status": "starting", "note": note,
            "window_id": os.environ.get("YJ_WINDOW_ID", ""),
            "start_ts": now(),
        })
        save(d)
        print(f"GO {jid}  ({host} 申请 {gpus} 卡，空闲 {f}->{f-gpus})  —— 可启动；启动后 hook 自动翻 running")
        return 0
    else:
        d["queue"].append({
            "id": jid, "project": project, "host": host, "gpus": gpus,
            "note": note, "window_id": os.environ.get("YJ_WINDOW_ID", ""),
            "enqueued_ts": now(),
        })
        save(d)
        print(f"QUEUED {jid}  ({host} 申请 {gpus} 卡，仅空闲 {f}) —— 卡满已排队；有卡 release 后自动取出")
        return 0


def _fits_and_promote(d):
    """FIFO 扫 queue，把第一个放得下的移入 active starting，返回被起的条目列表。"""
    started = []
    remaining = []
    for q in d["queue"]:
        host = q.get("host")
        g = int(q.get("gpus", 1))
        if free(d, host) >= g:
            q2 = dict(q)
            q2["status"] = "starting"
            q2["start_ts"] = now()
            d["active"].append(q2)
            started.append(q2)
        else:
            remaining.append(q)
    d["queue"] = remaining
    return started


def cmd_release(key):
    d = load()
    before = len(d["active"])
    dropped = [j for j in d["active"] if j.get("id") == key or j.get("project") == key]
    d["active"] = [j for j in d["active"] if not (j.get("id") == key or j.get("project") == key)]
    if before == len(d["active"]):
        print(f"WARN 无匹配 active 条目 '{key}'（可能已清）")
    else:
        for j in dropped:
            print(f"RELEASED {j.get('id')} {j.get('project')} {j.get('host')} {j.get('gpus')}卡")
    started = _fits_and_promote(d)
    save(d)
    for s in started:
        print(f"NEXT {s.get('id')} {s.get('project')} {s.get('host')} {s.get('gpus')} :: {s.get('note','')}")
    if not started and d["queue"]:
        print(f"（队列仍有 {len(d['queue'])} 个等待，当前卡仍不够）")
    return 0


def cmd_status():
    d = load()
    print(f"== GPU 卡槽 (schema v{d['schema_version']}) ==")
    for host, cap in d["capacity"].items():
        print(f"  {host}: {used(d, host)}/{cap} 占用，空闲 {free(d, host)}")
    print(f"-- active ({len(d['active'])}) --")
    for j in d["active"]:
        print(f"  [{j.get('status')}] {j.get('id')} {j.get('project')} {j.get('host')} {j.get('gpus')}卡 "
              f"since={j.get('running_since') or j.get('start_ts')} note={j.get('note','')}")
    print(f"-- queue ({len(d['queue'])}) --")
    for q in d["queue"]:
        print(f"  {q.get('id')} {q.get('project')} {q.get('host')} {q.get('gpus')}卡 "
              f"enq={q.get('enqueued_ts')} note={q.get('note','')}")
    return 0


def cmd_reap():
    """清 local active 中 pid 已死的陈旧条目（hpc 不在本机无法验 pid，跳过）。"""
    d = load()
    killed = []
    keep = []
    for j in d["active"]:
        pid = j.get("pid")
        if j.get("host") == "local" and pid:
            try:
                os.kill(int(pid), 0)
                keep.append(j)
            except (OSError, ValueError):
                killed.append(j)
        else:
            keep.append(j)
    d["active"] = keep
    started = _fits_and_promote(d)
    save(d)
    for k in killed:
        print(f"REAPED {k.get('id')} {k.get('project')} (pid {k.get('pid')} 已死)")
    for s in started:
        print(f"NEXT {s.get('id')} {s.get('project')} {s.get('host')} {s.get('gpus')} :: {s.get('note','')}")
    if not killed:
        print("无陈旧 local 条目")
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    c = argv[1]
    if c == "request":
        if len(argv) < 5:
            print("用法: gpu_slot.py request <project> <host> <gpus> [note]")
            return 1
        return cmd_request(argv[2], argv[3], argv[4], " ".join(argv[5:]))
    if c == "release":
        if len(argv) < 3:
            print("用法: gpu_slot.py release <id|project>")
            return 1
        return cmd_release(argv[2])
    if c == "status":
        return cmd_status()
    if c == "list":
        print(json.dumps(load(), ensure_ascii=False, indent=2))
        return 0
    if c == "reap":
        return cmd_reap()
    print(f"未知子命令 '{c}'")
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
