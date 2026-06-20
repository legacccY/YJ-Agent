#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conductor —— YJ-Agent 通用阶段编排引擎（持久任务 DAG）。

解决什么：单项目多阶段工作有先后依赖，要 Claude 自己当指挥按序推进、跑完一棒
自动解锁下一棒、到拍板点停——但 context 压缩会断链。仿 gpu_slot.py / state.json：
**任务图写文件不靠记忆**，任何窗口任何时候 `/conductor <project>` 都能读图续跑。

与 gpu_slot.py 正交：pipeline.py 管「干哪些棒、谁依赖谁、现在该派谁」（编排层）；
gpu_slot.py 管「训练有没有空卡」（资源层）。训练那一棒由 conductor 走 gpu_slot.py。

真源 = .portfolio/pipelines/<project>.json
节点 schema：
  {"id","stage","agent","deps":[...],"status","gate":bool,"group","desc","out","ts"}
status：pending（未起）| running（已派）| done（完成）| blocked（卡住待修）| skipped
gate=true 的节点 = 拍板点（训练/HPC上传/投稿/立项…），conductor 到此停下报，
  放行后才 `done` 推进。

用法（conductor skill 调用，不要手改 JSON）：
  python tools/pipeline.py init <project> [--template paper|experiment|scout|writing] [--from <phase关键词>]
      建/重置该项目 DAG。无 --template 默认 experiment。已存在则报错（用 --force 覆盖）。
  python tools/pipeline.py ready <project> [--free]
      ⭐核心：打印**现在可派**的节点（status=pending 且所有 deps 已 done）。
      同 group 的多个就绪节点 = 可并行扇出。遇 gate 节点单独标 "GATE"。
      已被某窗认领的标 "@窗名"。--free = 只看没被认领的（新窗找活）。
  python tools/pipeline.py claim <project> <node_id> <window>
      节点级认领（一篇多窗：各窗领不同节点并行，不撞同块）。标 running。
  python tools/pipeline.py mine <project> <window>
      看某窗认领了哪些节点。
  python tools/pipeline.py next <project>
      一行人读：现在该干啥（就绪节点 / 卡在哪个 gate / 全完成）。
  python tools/pipeline.py start <project> <node_id>
      标记某节点已派出（running）。
  python tools/pipeline.py done <project> <node_id> [--out "结果指针/csv路径/结论"]
      标记完成，自动解锁依赖它的下游节点。
  python tools/pipeline.py block <project> <node_id> --reason "..."
      标记卡住（如 skeptic 抓到致命伤 / 训练发散），下游不解锁。
  python tools/pipeline.py skip <project> <node_id> [--reason "..."]
      跳过某棒（如设计已红队过、本轮不写作）。视同 done 解锁下游。
  python tools/pipeline.py reset <project> <node_id|--stale>
      把某节点退回 pending 重跑（修 blocked 后重派 / 分析说要回炉重设计）。
      --stale = 把所有 running 退回 pending（窗口中途死了恢复用，仿 gpu_slot reap）。
  python tools/pipeline.py add <project> <node_id> --agent X --stage S [--deps a,b]
                              [--gate] [--group g] [--desc "..."]
      自定义加节点（custom 图 / 临时插棒）。
  python tools/pipeline.py status <project>
      人读全图：每节点状态字形 + 依赖 + 当前波次。
  python tools/pipeline.py list [<project>]
      原始 JSON（无 project = 列所有 pipeline）。
  python tools/pipeline.py rm <project>
      删除该项目 DAG（归档到 .archive）。

退出码：ready/next 有就绪节点=0；卡在 gate=10；全完成=20；空图/不存在=2。
"""
import json
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

# Windows GBK 控制台编码不了字形/emoji → 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PDIR = os.path.join(ROOT, '.portfolio', 'pipelines')
ADIR = os.path.join(PDIR, '.archive')
CN_TZ = timezone(timedelta(hours=8))

GLYPH = {
    'pending': '·', 'running': '▶', 'done': '✓',
    'blocked': '✗', 'skipped': '⊘',
}


def now():
    return datetime.now(CN_TZ).isoformat(timespec='seconds')


def ppath(project):
    return os.path.join(PDIR, f'{project}.json')


def load(project):
    p = ppath(project)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def save(dag):
    os.makedirs(PDIR, exist_ok=True)
    p = ppath(dag['project'])
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(dag, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def find(dag, node_id):
    for n in dag['nodes']:
        if n['id'] == node_id:
            return n
    return None


# ---------------------------------------------------------------- templates
# 节点：(id, stage, agent, deps, gate, group, desc)
# agent 对应 .claude/agents/ 角色；"主线" = 主线亲自串行（训练/HPC/投稿等）。
TEMPLATES = {
    # 完整论文闭环：调研→设计→红队→写码→🔬集成烟测→🛑跑→分析→核数→写→审
    'paper': [
        ('scout', '调研', 'researcher', [], False, 'scout', '文献/竞品/官方超参/SOTA 并行探路'),
        ('design', '设计', 'planner', ['scout'], False, '', '出实验矩阵，对齐 ACCEPTANCE 判据'),
        ('redteam', '红队', 'skeptic', ['design'], False, '', '攻设计致命伤（0 致命即过）'),
        ('implement', '写码', 'coder', ['redteam'], False, '', '实现各 run 脚本/config，自测 pytest'),
        ('integrate', '集成烟测', '主线', ['implement'], False, '', '🔬真·端到端最小跑(1图1step本地<5min)踩缝:数据格式/依赖/路径/eval喂的对不对。pytest≠真验,缝在这暴露不留给HPC'),
        ('train', '跑', '主线', ['integrate'], True, '', '🛑拍板：gpu_slot 申卡→/loop /run-experiment'),
        ('analyze', '分析', 'analyst', ['train'], False, '', '读 csv/state.json 趋势/图/对判据'),
        ('verify', '核数', 'verifier', ['analyze'], False, '', '关键数字三方对账'),
        ('write', '写作', 'writer', ['verify'], False, '', '写章节（数字过 verifier）'),
        ('review', '审稿', 'reviewer', ['write'], False, '', '对抗审稿 + 反跑偏审计'),
    ],
    # 实验中段闭环（= experiment-cycle 的 DAG 版 + 集成烟测闸）
    'experiment': [
        ('design', '设计', 'planner', [], False, '', '出实验矩阵，对齐判据'),
        ('redteam', '红队', 'skeptic', ['design'], False, '', '攻设计致命伤（0 致命即过）'),
        ('implement', '写码', 'coder', ['redteam'], False, '', '实现各 run 脚本/config，自测 pytest'),
        ('integrate', '集成烟测', '主线', ['implement'], False, '', '🔬真·端到端最小跑(1图1step本地<5min)踩缝:数据格式/依赖/路径/eval喂的对不对。pytest≠真验,缝在这暴露不留给HPC'),
        ('train', '跑', '主线', ['integrate'], True, '', '🛑拍板：gpu_slot 申卡→/loop /run-experiment'),
        ('analyze', '分析', 'analyst', ['train'], False, '', '读结果出趋势/图/对判据'),
        ('verify', '核数', 'verifier', ['analyze'], False, '', '关键数字三方对账 + 写 LOG'),
    ],
    # 探路调研（= paper-scout）：4 researcher 并行 → reviewer 收口
    'scout': [
        ('lit', '调研', 'researcher', [], False, 'scout', '查既有文献/方法'),
        ('rivals', '调研', 'researcher', [], False, 'scout', '查竞品/撞车'),
        ('hyper', '调研', 'researcher', [], False, 'scout', '查官方超参/实现'),
        ('sota', '调研', 'researcher', [], False, 'scout', '查 SOTA 设置/榜单'),
        ('synth', '收口', 'reviewer', ['lit', 'rivals', 'hyper', 'sota'], False, '', '汇总找漏洞/盲区'),
    ],
    # 写作冲刺
    'writing': [
        ('verify', '核数', 'verifier', [], False, '', '数字三方对账'),
        ('write', '写作', 'writer', ['verify'], False, '', '写/改章节'),
        ('review', '审稿', 'reviewer', ['write'], False, '', '对抗审稿'),
    ],
}


def cmd_init(args):
    project = args.project
    if load(project) is not None and not args.force:
        print(f'ERR pipeline 已存在：{ppath(project)}。--force 覆盖（旧图归档）。')
        return 2
    if load(project) is not None and args.force:
        _archive(project)
    tmpl = args.template or 'experiment'
    if tmpl not in TEMPLATES:
        print(f'ERR 未知模板 {tmpl}，可选：{", ".join(TEMPLATES)}')
        return 2
    nodes = []
    for (nid, stage, agent, deps, gate, group, desc) in TEMPLATES[tmpl]:
        nodes.append({
            'id': nid, 'stage': stage, 'agent': agent, 'deps': list(deps),
            'status': 'pending', 'gate': gate, 'group': group,
            'desc': desc, 'out': '', 'owner': '', 'ts': '',
        })
    dag = {
        'schema_version': 1, 'project': project, 'template': tmpl,
        'created': now(), 'updated': now(),
        'from_phase': args.from_phase or '', 'nodes': nodes,
    }
    save(dag)
    print(f'OK init {project} [{tmpl}] {len(nodes)} 棒。')
    return cmd_next(args)


def _archive(project):
    dag = load(project)
    if dag is None:
        return
    os.makedirs(ADIR, exist_ok=True)
    stamp = datetime.now(CN_TZ).strftime('%Y%m%d_%H%M%S')
    with open(os.path.join(ADIR, f'{project}_{stamp}.json'), 'w', encoding='utf-8') as f:
        json.dump(dag, f, ensure_ascii=False, indent=2)
    os.remove(ppath(project))


def _ready_nodes(dag):
    done_ids = {n['id'] for n in dag['nodes'] if n['status'] in ('done', 'skipped')}
    ready = []
    for n in dag['nodes']:
        if n['status'] != 'pending':
            continue
        if all(d in done_ids for d in n['deps']):
            ready.append(n)
    return ready


def cmd_ready(args):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}（先 init）')
        return 2
    ready = _ready_nodes(dag)
    if not ready:
        running = [n for n in dag['nodes'] if n['status'] == 'running']
        blocked = [n for n in dag['nodes'] if n['status'] == 'blocked']
        if running:
            print('WAIT 在跑：' + ', '.join(f"{n['id']}({n['agent']})" for n in running))
            return 0
        if blocked:
            print('BLOCKED 卡住：' + ', '.join(f"{n['id']}::{n['out']}" for n in blocked))
            # 被 blocked 上游堵死的下游（孤儿）
            bids = {n['id'] for n in blocked}
            orphan = [n['id'] for n in dag['nodes'] if n['status'] == 'pending'
                      and any(d in bids for d in n['deps'])]
            if orphan:
                print('  ↳ 被堵下游（修上游 reset 后才解）：' + ', '.join(orphan))
            return 10
        pend = [n for n in dag['nodes'] if n['status'] == 'pending']
        if pend:
            print('DEADLOCK 有 pending 但无可派（依赖环/孤儿）：'
                  + ', '.join(f"{n['id']}←{','.join(n['deps'])}" for n in pend))
            return 10
        print('DONE 全部完成。')
        return 20
    gates = [n for n in ready if n['gate']]
    if gates:
        for g in gates:
            print(f"GATE {g['id']} [{g['stage']}] {g['desc']} —— 🛑拍板点，停下报，放行后 done")
        return 10
    # --free：只看没被任何窗认领的就绪节点（新窗找活干）
    if getattr(args, 'free', False):
        ready = [n for n in ready if not n['owner']]
        if not ready:
            print('（无空闲可领的就绪节点——都被认领了，或等上游）')
            return 0
    # 同 group 的就绪节点可并行扇出
    groups = {}
    for n in ready:
        groups.setdefault(n['group'] or n['id'], []).append(n)
    for gname, ns in groups.items():
        tag = f'PARALLEL[{gname}]' if len(ns) > 1 else 'READY'
        for n in ns:
            own = f" @{n['owner']}" if n['owner'] else ''
            print(f"{tag} {n['id']} [{n['stage']}] agent={n['agent']}{own} :: {n['desc']}")
    return 0


def cmd_next(args):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    ready = _ready_nodes(dag)
    total = len(dag['nodes'])
    done = sum(1 for n in dag['nodes'] if n['status'] in ('done', 'skipped'))
    prefix = f'[{args.project} {done}/{total}]'
    if not ready:
        running = [n['id'] for n in dag['nodes'] if n['status'] == 'running']
        blocked = [n for n in dag['nodes'] if n['status'] == 'blocked']
        if running:
            print(f'{prefix} 等在跑：{", ".join(running)}')
            return 0
        if blocked:
            print(f'{prefix} 卡住待修：' + '; '.join(f"{n['id']}={n['out']}" for n in blocked))
            return 10
        print(f'{prefix} ✓ 全部完成')
        return 20
    gates = [n for n in ready if n['gate']]
    if gates:
        g = gates[0]
        print(f"{prefix} 🛑拍板点：{g['id']} [{g['stage']}] {g['desc']}")
        return 10
    names = ', '.join(f"{n['id']}({n['agent']})" for n in ready)
    par = ' [可并行扇出]' if len(ready) > 1 else ''
    print(f'{prefix} 下一棒：{names}{par}')
    return 0


def _set(args, status, out=None):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    n = find(dag, args.node_id)
    if n is None:
        print(f"ERR 无此节点：{args.node_id}（有：{', '.join(x['id'] for x in dag['nodes'])}）")
        return 2
    n['status'] = status
    n['ts'] = now()
    if out is not None:
        n['out'] = out
    if status in ('done', 'skipped', 'pending'):
        n['owner'] = ''  # 完成/重置 → 释放认领，别的窗可接
    dag['updated'] = now()
    save(dag)
    return n, dag


def cmd_start(args):
    r = _set(args, 'running')
    if isinstance(r, int):
        return r
    n, _ = r
    print(f"OK start {n['id']} ({n['agent']}) ▶")
    return 0


def cmd_done(args):
    r = _set(args, 'done', out=args.out or '')
    if isinstance(r, int):
        return r
    n, dag = r
    print(f"OK done {n['id']} ✓")
    # 解锁信息
    newly = _ready_nodes(dag)
    if newly:
        gates = [x for x in newly if x['gate']]
        if gates:
            print(f"→ 解锁拍板点：{gates[0]['id']} [{gates[0]['stage']}] 🛑 {gates[0]['desc']}")
        else:
            print('→ 解锁：' + ', '.join(f"{x['id']}({x['agent']})" for x in newly)
                  + (' [可并行]' if len(newly) > 1 else ''))
    else:
        remain = [x for x in dag['nodes'] if x['status'] == 'pending']
        running = [x for x in dag['nodes'] if x['status'] == 'running']
        if not remain and not running:
            print('→ ✓ 全部完成')
        elif running:
            print('→ 等在跑：' + ', '.join(x['id'] for x in running))
    return 0


def cmd_block(args):
    r = _set(args, 'blocked', out=args.reason or '')
    if isinstance(r, int):
        return r
    n, _ = r
    print(f"OK block {n['id']} ✗ :: {n['out']}")
    return 0


def cmd_skip(args):
    r = _set(args, 'skipped', out=args.reason or 'skipped')
    if isinstance(r, int):
        return r
    n, dag = r
    print(f"OK skip {n['id']} ⊘")
    newly = _ready_nodes(dag)
    if newly:
        print('→ 解锁：' + ', '.join(x['id'] for x in newly))
    return 0


def cmd_reset(args):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    if getattr(args, 'stale', False) or args.node_id == '--stale':
        hit = [n for n in dag['nodes'] if n['status'] == 'running']
        for n in hit:
            n['status'] = 'pending'
            n['ts'] = now()
        dag['updated'] = now()
        save(dag)
        if hit:
            print('OK reset --stale 退回 pending：' + ', '.join(n['id'] for n in hit))
        else:
            print('（无 running 节点，无需恢复）')
        return cmd_next(args)
    n = find(dag, args.node_id)
    if n is None:
        print(f"ERR 无此节点：{args.node_id}")
        return 2
    n['status'] = 'pending'
    n['out'] = ''
    n['ts'] = now()
    dag['updated'] = now()
    save(dag)
    print(f"OK reset {n['id']} → pending（可重派）")
    return cmd_next(args)


def cmd_add(args):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}（先 init，或 init --template custom 后 add）')
        return 2
    if find(dag, args.node_id):
        print(f'ERR 节点已存在：{args.node_id}')
        return 2
    deps = [d.strip() for d in (args.deps or '').split(',') if d.strip()]
    for d in deps:
        if not find(dag, d):
            print(f'ERR 依赖不存在：{d}')
            return 2
    dag['nodes'].append({
        'id': args.node_id, 'stage': args.stage or '自定义',
        'agent': args.agent or '主线', 'deps': deps, 'status': 'pending',
        'gate': bool(args.gate), 'group': args.group or '', 'desc': args.desc or '',
        'out': '', 'owner': '', 'ts': '',
    })
    dag['updated'] = now()
    save(dag)
    print(f'OK add {args.node_id} (deps={deps or "—"}{", GATE" if args.gate else ""})')
    return 0


def cmd_claim(args):
    """节点级认领（一篇多窗：各窗领不同节点并行，不撞）。"""
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    n = find(dag, args.node_id)
    if n is None:
        print(f"ERR 无此节点：{args.node_id}")
        return 2
    if n['owner'] and n['owner'] != args.window and n['status'] == 'running':
        print(f"ERR {n['id']} 已被 {n['owner']} 窗认领且在跑——别双做（换个 ready --free 的节点）")
        return 2
    n['owner'] = args.window
    n['status'] = 'running'
    n['ts'] = now()
    dag['updated'] = now()
    save(dag)
    print(f"OK claim {n['id']} → {args.window} 窗 ▶（其余窗 ready --free 看还剩哪些可领）")
    return 0


def cmd_mine(args):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    mine = [n for n in dag['nodes'] if n['owner'] == args.window]
    if not mine:
        print(f'（{args.window} 窗未认领任何节点）')
        return 2
    for n in mine:
        print(f"  {GLYPH.get(n['status'],'?')} {n['id']} [{n['stage']}] {n['agent']} ::{n['out'] or n['desc']}")
    return 0


def cmd_dep(args):
    """改依赖边（拆块后让 integrate/下游指向新块）。"""
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    n = find(dag, args.node_id)
    if n is None:
        print(f"ERR 无此节点：{args.node_id}")
        return 2
    if args.add:
        for d in [x.strip() for x in args.add.split(',') if x.strip()]:
            if not find(dag, d):
                print(f'ERR 依赖不存在：{d}')
                return 2
            if d == args.node_id:
                print('ERR 不能依赖自己')
                return 2
            if d not in n['deps']:
                n['deps'].append(d)
    if args.rm:
        for d in [x.strip() for x in args.rm.split(',') if x.strip()]:
            if d in n['deps']:
                n['deps'].remove(d)
    dag['updated'] = now()
    save(dag)
    print(f"OK {n['id']} deps = {n['deps'] or '—'}")
    return 0


def cmd_status(args):
    dag = load(args.project)
    if dag is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    done = sum(1 for n in dag['nodes'] if n['status'] in ('done', 'skipped'))
    total = len(dag['nodes'])
    print(f"== {dag['project']} [{dag.get('template','?')}] {done}/{total} == (更新 {dag['updated']})")
    done_ids = {n['id'] for n in dag['nodes'] if n['status'] in ('done', 'skipped')}
    for n in dag['nodes']:
        g = GLYPH.get(n['status'], '?')
        gate = ' 🛑' if n['gate'] else ''
        dep = ''
        if n['deps']:
            unmet = [d for d in n['deps'] if d not in done_ids]
            dep = f"  ←{','.join(n['deps'])}" + (f" (待 {','.join(unmet)})" if unmet else '')
        out = f"  ::{n['out']}" if n['out'] else ''
        print(f"  {g} {n['id']:<11}[{n['stage']}] {n['agent']:<10}{gate}{dep}{out}")
    print('  ' + '-' * 40)
    cmd_next(args)
    return 0


def cmd_list(args):
    if args.project:
        dag = load(args.project)
        if dag is None:
            print(f'ERR 无 pipeline：{args.project}')
            return 2
        print(json.dumps(dag, ensure_ascii=False, indent=2))
        return 0
    if not os.path.isdir(PDIR):
        print('（无 pipeline）')
        return 2
    files = [f[:-5] for f in os.listdir(PDIR) if f.endswith('.json')]
    if not files:
        print('（无 pipeline）')
        return 2
    for proj in sorted(files):
        dag = load(proj)
        done = sum(1 for n in dag['nodes'] if n['status'] in ('done', 'skipped'))
        print(f"{proj:<16} [{dag.get('template','?')}] {done}/{len(dag['nodes'])}  更新 {dag['updated']}")
    return 0


def cmd_rm(args):
    if load(args.project) is None:
        print(f'ERR 无 pipeline：{args.project}')
        return 2
    _archive(args.project)
    print(f'OK 已删除 {args.project}（归档到 .archive）')
    return 0


def build_parser():
    p = argparse.ArgumentParser(description='Conductor 阶段编排引擎')
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('init'); s.add_argument('project')
    s.add_argument('--template', '-t'); s.add_argument('--from', dest='from_phase')
    s.add_argument('--force', action='store_true'); s.set_defaults(fn=cmd_init)

    for name, fn in [('next', cmd_next), ('status', cmd_status)]:
        s = sub.add_parser(name); s.add_argument('project'); s.set_defaults(fn=fn)

    s = sub.add_parser('ready'); s.add_argument('project')
    s.add_argument('--free', action='store_true'); s.set_defaults(fn=cmd_ready)

    s = sub.add_parser('claim'); s.add_argument('project'); s.add_argument('node_id')
    s.add_argument('window'); s.set_defaults(fn=cmd_claim)

    s = sub.add_parser('mine'); s.add_argument('project'); s.add_argument('window')
    s.set_defaults(fn=cmd_mine)

    s = sub.add_parser('dep'); s.add_argument('project'); s.add_argument('node_id')
    s.add_argument('--add'); s.add_argument('--rm'); s.set_defaults(fn=cmd_dep)

    s = sub.add_parser('start'); s.add_argument('project'); s.add_argument('node_id')
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser('done'); s.add_argument('project'); s.add_argument('node_id')
    s.add_argument('--out', default=''); s.set_defaults(fn=cmd_done)

    s = sub.add_parser('block'); s.add_argument('project'); s.add_argument('node_id')
    s.add_argument('--reason', default=''); s.set_defaults(fn=cmd_block)

    s = sub.add_parser('skip'); s.add_argument('project'); s.add_argument('node_id')
    s.add_argument('--reason', default=''); s.set_defaults(fn=cmd_skip)

    s = sub.add_parser('reset'); s.add_argument('project')
    s.add_argument('node_id', nargs='?', default=''); s.add_argument('--stale', action='store_true')
    s.set_defaults(fn=cmd_reset)

    s = sub.add_parser('add'); s.add_argument('project'); s.add_argument('node_id')
    s.add_argument('--agent'); s.add_argument('--stage'); s.add_argument('--deps')
    s.add_argument('--gate', action='store_true'); s.add_argument('--group')
    s.add_argument('--desc'); s.set_defaults(fn=cmd_add)

    s = sub.add_parser('list'); s.add_argument('project', nargs='?'); s.set_defaults(fn=cmd_list)
    s = sub.add_parser('rm'); s.add_argument('project'); s.set_defaults(fn=cmd_rm)
    return p


def main():
    args = build_parser().parse_args()
    sys.exit(args.fn(args))


if __name__ == '__main__':
    main()
