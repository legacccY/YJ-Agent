# -*- coding: utf-8 -*-
"""
test_apply_monitor_hook.py —— 验 patch-applier 文本注入：插入/幂等/锚点匹配/缺锚点报错/歧义报错。
纯文本操作，不 import/执行官方训练码（mock main 只是字符串片段）。

主线跑：cd code && python -m pytest pretrain/test_apply_monitor_hook.py -x -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_monitor_hook as amh  # noqa: E402

# ---- mock 官方 main 片段（含真锚点，缩进仿官方 loop）----
MOCK_DINO = '''import torch

def train_one_epoch(student, teacher, teacher_without_ddp, dino_loss, data_loader,
                    optimizer, lr_schedule, wd_schedule, momentum_schedule, epoch, args):
    metric_logger = MetricLogger(delimiter="  ")
    for it, (images, _) in enumerate(metric_logger.log_every(data_loader, 10)):
        teacher_output = teacher(images[:2])
        student_output = student(images)
        loss = dino_loss(student_output, teacher_output, epoch)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        metric_logger.update(loss=loss.item())
        metric_logger.update(lr=optimizer.param_groups[0]["lr"])
    return {k: meter.global_avg for k, meter in metric_logger.meters.items()}
'''

MOCK_MOCO = '''import torch

def train(train_loader, model, optimizer, scaler, summary_writer, epoch, args):
    losses = AverageMeter('Loss', ':.4e')
    for i, (images, _) in enumerate(train_loader):
        moco_m = args.moco_m
        images[0] = images[0].cuda(args.gpu, non_blocking=True)
        images[1] = images[1].cuda(args.gpu, non_blocking=True)
        with torch.cuda.amp.autocast(True):
            loss = model(images[0], images[1], moco_m)
        losses.update(loss.item(), images[0].size(0))
        optimizer.zero_grad()
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
'''


def _write(tmp_path, method, text):
    entry = amh.SPECS[method]['entry']
    p = tmp_path / entry
    p.write_text(text, encoding='utf-8')
    return p


@pytest.mark.parametrize('method,mock,call_body', [
    ('dino', MOCK_DINO, '_cxrssl_log_dino(teacher_output, loss.item(), epoch=epoch)'),
    ('moco', MOCK_MOCO, '_cxrssl_log_moco(model, images[0], loss.item(), epoch=epoch)'),
])
def test_insert_then_idempotent(tmp_path, method, mock, call_body):
    p = _write(tmp_path, method, mock)

    r1 = amh.apply_hook(p, method)
    assert r1['status'] == 'inserted'
    out = p.read_text(encoding='utf-8')
    # 标记 + helper + 调用都已注入
    assert amh.MARKER in out
    assert call_body in out
    assert '_sm.MonitorWriter' in out  # helper 用惰性 _sm.MonitorWriter（含子串，原 'not in' 断言写错）
    assert 'from smoke_monitor import' not in out  # 不裸 top-level import（惰性避免拉 torch）
    assert '_cxrssl_writer' in out
    # 备份生成且 = 原文
    bak = p.with_name(p.name + '.cxrssl_orig')
    assert bak.exists() and bak.read_text(encoding='utf-8') == mock
    # 写回为 LF（无 CRLF）
    assert b'\r\n' not in p.read_bytes()  # read_text(newline=) 是 py3.13+；用 bytes 查 CRLF
    # call 行号合理
    assert isinstance(r1['call_line'], int) and r1['call_line'] > 0

    # 幂等：再跑不重复插
    r2 = amh.apply_hook(p, method)
    assert r2['status'] == 'already'
    out2 = p.read_text(encoding='utf-8')
    assert out2 == out                       # 文件未变
    assert out2.count(amh.MARKER) == 2        # 仅首尾两个标记，没翻倍


@pytest.mark.parametrize('method', ['dino', 'moco'])
def test_missing_call_anchor_raises(tmp_path, method):
    # 删掉 loop 调用锚点行 -> 必须报错退出（不静默没插）
    mock = MOCK_DINO if method == 'dino' else MOCK_MOCO
    anchor = amh.SPECS[method]['call_anchor']
    broken = '\n'.join(l for l in mock.splitlines() if anchor not in l) + '\n'
    p = _write(tmp_path, method, broken)
    with pytest.raises(RuntimeError, match='锚点未找到'):
        amh.apply_hook(p, method)


@pytest.mark.parametrize('method', ['dino', 'moco'])
def test_missing_def_anchor_raises(tmp_path, method):
    mock = MOCK_DINO if method == 'dino' else MOCK_MOCO
    def_anchor = amh.SPECS[method]['def_anchor']
    broken = mock.replace(def_anchor, 'def _renamed_loop(')
    p = _write(tmp_path, method, broken)
    with pytest.raises(RuntimeError, match='函数锚点未找到'):
        amh.apply_hook(p, method)


def test_call_anchor_ambiguous_raises(tmp_path):
    # 两处 metric_logger.update(loss=loss.item()) -> 歧义须报错，不乱插
    dup = MOCK_DINO.replace(
        '        metric_logger.update(loss=loss.item())\n',
        '        metric_logger.update(loss=loss.item())\n'
        '        metric_logger.update(loss=loss.item())\n', 1)
    p = _write(tmp_path, 'dino', dup)
    with pytest.raises(RuntimeError, match='歧义'):
        amh.apply_hook(p, 'dino')


def test_missing_file_raises(tmp_path):
    with pytest.raises(RuntimeError, match='不存在'):
        amh.apply_hook(tmp_path / 'nope_main.py', 'dino')


def test_unknown_method_raises(tmp_path):
    p = _write(tmp_path, 'dino', MOCK_DINO)
    with pytest.raises(RuntimeError, match='未知 method'):
        amh.apply_hook(p, 'mae')
