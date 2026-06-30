# -*- coding: utf-8 -*-
"""
apply_monitor_hook.py —— CXR-SSLBench Phase1 collapse 烟测 patch-applier（R4 合规：监控非算法改）。

职责（INTERFACE §4 + submit_pretrain.sh TODO-MONITOR-HOOK）：
  官方 facebookresearch/dino|moco-v3 训练 loop **不 emit** collapse 监控量（teacher 熵/特征 std/...）
  → 本脚本用**文本锚点匹配**在官方 main_<method>.py 的训练 loop 注入 ~1 行 hook 调用 +
    文件级一段 monitor helper，使训练时每 CXRSSL_LOG_EVERY(默认50) 步调
    smoke_monitor.MonitorWriter.log_step 灌入监控量到 results/smoke_<method>.csv。
  **绝不改官方超参/算法**——只在 loss 已算出后只读地 detach 特征/概率算监控量并 append csv（R4 零偏离）。

幂等：注入块带 `# [CXRSSL-MONITOR]` 标记；重复跑检测到标记即跳过，不重复插。
失败保护：任一锚点找不到 / 歧义 → 打印哪个锚点 + 非 0 退出（绝不静默没插）。
首次注入前备份原文件为 main_<method>.py.cxrssl_orig（便于回滚 / 重新生成）。

用法（主线在 HPC clone 完官方 repo 后、启训练前跑一次）：
  cd code
  python pretrain/apply_monitor_hook.py --repo_dir vendor/dino --method dino
  python pretrain/apply_monitor_hook.py --repo_dir vendor/moco --method moco

注入的 hook 运行时从**环境变量**取写盘参数（主线在 submit_pretrain.sh 启训前 export）：
  CXRSSL_RESULTS_DIR  (必填) = $RESULTS，smoke_<method>.csv / state_<run>.json 落处
  CXRSSL_CODE_DIR     (必填) = $CODE，hook 加进 sys.path 以 import smoke_monitor
  CXRSSL_RUN          (可选, 默认 'smk') = $RUN，state.json 心跳 run 名
  CXRSSL_SEED         (可选, 默认 '0')   = $SEED
  CXRSSL_LOG_EVERY    (可选, 默认 '50')  = emit 间隔（步）
  说明：仅 rank0 进程写 csv（dist.get_rank()/RANK env 判定），避免多进程并写 header 崩。

⚠️ Windows 注意：写回用 newline='\n'，防 CRLF 污染 HPC Linux 上的官方 py（与 HPC submit checklist 一致）。
"""
import argparse
import re
import sys
from pathlib import Path

MARKER = '# [CXRSSL-MONITOR]'

# ===========================================================================
# 注入到官方 main 文件的 monitor helper（module 级，插在训练函数 def 之前）
#   COMMON：env/sys.path 装载 + 单例 writer + rank0 判定 + numpy softmax
#   <METHOD>_FN：method 专属 log 函数（每 N 步算监控量调 log_step）
# ===========================================================================
_COMMON = '''{MARKER} >>> injected by apply_monitor_hook.py (R4: 监控非算法改, 只读 emit collapse 量)
import os as _cxrssl_os, sys as _cxrssl_sys
_CXRSSL_METHOD = '{METHOD}'
_cxrssl_code_dir = _cxrssl_os.environ.get('CXRSSL_CODE_DIR', '')
if _cxrssl_code_dir and _cxrssl_code_dir not in _cxrssl_sys.path:
    _cxrssl_sys.path.insert(0, _cxrssl_code_dir)
_CXRSSL_WRITER = None
_CXRSSL_STEP = 0
_CXRSSL_EVERY = int(_cxrssl_os.environ.get('CXRSSL_LOG_EVERY', '50'))


def _cxrssl_is_rank0():
    try:
        import torch.distributed as _d
        if _d.is_available() and _d.is_initialized():
            return _d.get_rank() == 0
    except Exception:
        pass
    return (_cxrssl_os.environ.get('RANK', '0') in ('0', '')
            and _cxrssl_os.environ.get('LOCAL_RANK', '0') in ('0', ''))


def _cxrssl_writer():
    global _CXRSSL_WRITER
    if _CXRSSL_WRITER is None:
        import smoke_monitor as _sm
        _CXRSSL_WRITER = _sm.MonitorWriter(
            _cxrssl_os.environ['CXRSSL_RESULTS_DIR'],
            _cxrssl_os.environ.get('CXRSSL_RUN', 'smk'),
            _CXRSSL_METHOD,
            _cxrssl_os.environ.get('CXRSSL_SEED', '0'))
    return _CXRSSL_WRITER


def _cxrssl_softmax_np(x):
    import numpy as _np
    x = x - x.max(axis=-1, keepdims=True)
    e = _np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)
'''

_DINO_FN = '''

def _cxrssl_log_dino(teacher_output, loss_val, epoch=None, total_steps=None):
    """每 CXRSSL_LOG_EVERY 步：teacher_output[2B,out_dim] logits -> softmax 熵/kl + 跨样本特征 std。"""
    global _CXRSSL_STEP
    _CXRSSL_STEP += 1
    if _CXRSSL_STEP % _CXRSSL_EVERY != 0 or not _cxrssl_is_rank0():
        return
    try:
        import torch as _t, smoke_monitor as _sm
        with _t.no_grad():
            logits = teacher_output.detach().float().cpu().numpy()
        probs = _cxrssl_softmax_np(logits)
        m = _sm.compute_dino_metrics(teacher_probs=probs, feats=logits,
                                     out_dim=logits.shape[-1])
        _cxrssl_writer().log_step(_CXRSSL_STEP, epoch=epoch, loss=loss_val,
                                  total_steps=total_steps, **m)
    except Exception as _e:
        _cxrssl_sys.stderr.write('[CXRSSL-MONITOR][warn] dino log skip: %r\\n' % (_e,))
{MARKER} <<< end injected helper


'''

_MOCO_FN = '''

def _cxrssl_log_moco(model, images0, loss_val, epoch=None, total_steps=None):
    """每 CXRSSL_LOG_EVERY 步：base_encoder(images0) 投影特征跨样本 std + ln(batch) 基线。
    临时 eval()+no_grad 只读 forward（ViT 用 LayerNorm 无 BN、dropout 默认关 -> 零 RNG 副作用），
    try/finally 保证恢复 train 模式（不破坏官方训练）。"""
    global _CXRSSL_STEP
    _CXRSSL_STEP += 1
    if _CXRSSL_STEP % _CXRSSL_EVERY != 0 or not _cxrssl_is_rank0():
        return
    try:
        import torch as _t, smoke_monitor as _sm
        bs = int(images0.size(0))
        enc = model.module.base_encoder if hasattr(model, 'module') else model.base_encoder
        was_training = model.training
        try:
            model.eval()
            with _t.no_grad():
                feats = enc(images0).detach().float().cpu().numpy()
        finally:
            if was_training:
                model.train()
        m = _sm.compute_moco_metrics(feats=feats, batch=bs)
        _cxrssl_writer().log_step(_CXRSSL_STEP, epoch=epoch, loss=loss_val,
                                  total_steps=total_steps, **m)
    except Exception as _e:
        _cxrssl_sys.stderr.write('[CXRSSL-MONITOR][warn] moco log skip: %r\\n' % (_e,))
{MARKER} <<< end injected helper


'''

# ---- method -> (entry 文件, 函数锚点, loop 调用锚点子串, 注入的调用语句, helper 块) ----
SPECS = {
    'dino': dict(
        entry='main_dino.py',
        def_anchor='def train_one_epoch(',
        call_anchor='metric_logger.update(loss=loss.item())',
        call_body='_cxrssl_log_dino(teacher_output, loss.item(), epoch=epoch)',
        fn=_DINO_FN,
    ),
    'moco': dict(
        entry='main_moco.py',
        def_anchor='def train(',
        call_anchor='losses.update(loss.item()',
        call_body='_cxrssl_log_moco(model, images[0], loss.item(), epoch=epoch)',
        fn=_MOCO_FN,
    ),
}


# ===========================================================================
# 文本注入（纯字符串操作，不 import/执行官方训练码）
# ===========================================================================
def _insert_header(text, def_anchor, helper):
    """在 module 级训练函数 def 之前插入 helper 块。唯一匹配，否则报错。"""
    key = '\n' + def_anchor
    cnt = text.count(key)
    if cnt == 0:
        if text.startswith(def_anchor):           # def 在文件首行（无前导换行）
            return helper + text
        raise RuntimeError(f'函数锚点未找到: {def_anchor!r}')
    if cnt > 1:
        raise RuntimeError(f'函数锚点歧义(匹配 {cnt} 处): {def_anchor!r}')
    return text.replace(key, '\n' + helper + def_anchor, 1)


def _insert_call_after(text, call_anchor, call_body):
    """在唯一含 call_anchor 子串的行之后，插入同缩进的 call_body。返回 (新文本, 行号)。"""
    pat = re.compile(r'(?m)^([ \t]*).*' + re.escape(call_anchor) + r'.*$')
    matches = list(pat.finditer(text))
    if not matches:
        raise RuntimeError(f'loop 调用锚点未找到: {call_anchor!r}')
    if len(matches) > 1:
        raise RuntimeError(f'loop 调用锚点歧义(匹配 {len(matches)} 处): {call_anchor!r}')
    m = matches[0]
    indent = m.group(1)
    line_no = text[:m.start()].count('\n') + 1
    insert = '\n' + indent + call_body
    return text[:m.end()] + insert + text[m.end():], line_no


def apply_hook(main_path, method):
    """对单个 main_<method>.py 注入 monitor hook。
    返回 dict(status, def_anchor, call_anchor, call_line)。锚点缺失/歧义 -> raise RuntimeError。"""
    method = method.lower()
    if method not in SPECS:
        raise RuntimeError(f'未知 method: {method}（仅 dino|moco）')
    spec = SPECS[method]
    main_path = Path(main_path)
    if not main_path.is_file():
        raise RuntimeError(f'官方 main 文件不存在: {main_path}')

    text = main_path.read_text(encoding='utf-8')
    if MARKER in text:
        return dict(status='already', def_anchor=spec['def_anchor'],
                    call_anchor=spec['call_anchor'], call_line=None)

    helper = (_COMMON + spec['fn']).format(MARKER=MARKER, METHOD=method)
    # 先插 loop 调用（拿行号报告），再插 header（header 在前、不影响已记录调用行内容）
    text2, call_line = _insert_call_after(text, spec['call_anchor'], spec['call_body'])
    text3 = _insert_header(text2, spec['def_anchor'], helper)

    # 备份原文件（首次）
    bak = main_path.with_name(main_path.name + '.cxrssl_orig')
    if not bak.exists():
        bak.write_text(text, encoding='utf-8', newline='\n')
    # 写回（newline='\n' 防 Windows CRLF 污染 HPC Linux）
    with open(main_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text3)
    return dict(status='inserted', def_anchor=spec['def_anchor'],
                call_anchor=spec['call_anchor'], call_line=call_line)


def main():
    p = argparse.ArgumentParser(
        description='CXR-SSLBench collapse 烟测 patch-applier（注入 monitor hook 到官方 main，不跑训练）')
    p.add_argument('--repo_dir', required=True, help='官方 repo clone 目录（如 vendor/dino）')
    p.add_argument('--method', required=True, choices=['dino', 'moco'])
    a = p.parse_args()

    spec = SPECS[a.method]
    main_path = Path(a.repo_dir) / spec['entry']
    try:
        r = apply_hook(main_path, a.method)
    except RuntimeError as e:
        sys.stderr.write(f'[apply_monitor_hook][FAIL] {e}\n')
        sys.stderr.write(f'  目标文件: {main_path}\n')
        sys.stderr.write(f'  期望锚点: def={spec["def_anchor"]!r} / call={spec["call_anchor"]!r}\n')
        sys.stderr.write('  -> 官方版本可能漂移，请核对 main 文件后调整 SPECS 锚点；未注入，退出非 0。\n')
        sys.exit(2)

    if r['status'] == 'already':
        print(f'[apply_monitor_hook][skip] {main_path} 已含 {MARKER}（幂等，不重复插）')
    else:
        print(f'[apply_monitor_hook][ok] {main_path}')
        print(f'  helper 插于函数 {r["def_anchor"]!r} 之前（module 级）')
        print(f'  log 调用插于锚点 {r["call_anchor"]!r}（约第 {r["call_line"]} 行）之后')
        print(f'  备份: {main_path.name}.cxrssl_orig')
    print('  运行时需 export: CXRSSL_RESULTS_DIR / CXRSSL_CODE_DIR [/ CXRSSL_RUN / CXRSSL_SEED / CXRSSL_LOG_EVERY]')
    sys.exit(0)


if __name__ == '__main__':
    main()
