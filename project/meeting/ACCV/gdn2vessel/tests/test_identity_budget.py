"""
test_identity_budget.py — 手画拓扑小图验三粒度计数正确性

防计数 bug 命门：覆盖 junction 删除逻辑边界（相邻 junction 像素、端点、孤立像素）。

三粒度定义：
  cc     = scipy.ndimage.label 8-连通分量数（背景 label=0 排除）
  branch = skeletonize → 删 junction(8邻居≥3) → 剩余连通分量数
  bifur  = junction 像素的 8-连通分量数

测试用例：
  T1: 两条不相连水平线 → cc=2, branch=2, bifur=0
  T2: Y 形（1主干分2支）→ cc=1, branch=3, bifur=1
  T3: 十字（+形）→ cc=1, branch=4, bifur=1
  T4: 单像素点（最小骨架） → cc=1, branch=1, bifur=0
  T5: 空 mask → 三粒度均=0
  T6: 两条相邻但不相交的线 → cc=2
  T7: L 形（折角，无分叉）→ cc=1, bifur=0
"""

from __future__ import annotations

import numpy as np
import pytest

# 被测模块路径：src/benchmark/identity_budget.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "benchmark"))

from identity_budget import count_identities


# ─────────────────────────────────────────────────────────────────────────────
#  辅助：画骨架图（直接作为 mask，无需 skeletonize 再处理）
# ─────────────────────────────────────────────────────────────────────────────

def _make_mask(shape, coords):
    """coords = list of (row, col) 坐标，返回 bool (H,W) mask。"""
    m = np.zeros(shape, dtype=bool)
    for r, c in coords:
        m[r, c] = True
    return m


# ─────────────────────────────────────────────────────────────────────────────
#  T1：两条不相连水平线
#
#  row 2: . . X X X X . .
#  row 5: . . X X X X . .
#
#  期望：cc=2, branch=2, bifur=0
#  理由：两条独立直线，各自 1 连通分量，各自 1 分支段，无分叉点
# ─────────────────────────────────────────────────────────────────────────────

def test_two_unconnected_lines_cc():
    m = _make_mask((10, 10), [(2, 2), (2, 3), (2, 4), (2, 5), (5, 2), (5, 3), (5, 4), (5, 5)])
    assert count_identities(m, "cc") == 2

def test_two_unconnected_lines_branch():
    m = _make_mask((10, 10), [(2, 2), (2, 3), (2, 4), (2, 5), (5, 2), (5, 3), (5, 4), (5, 5)])
    assert count_identities(m, "branch") == 2

def test_two_unconnected_lines_bifur():
    m = _make_mask((10, 10), [(2, 2), (2, 3), (2, 4), (2, 5), (5, 2), (5, 3), (5, 4), (5, 5)])
    assert count_identities(m, "bifur") == 0


# ─────────────────────────────────────────────────────────────────────────────
#  T2：Y 形（1 主干 + 2 分支，1 个分叉点）
#
#  布局（11×9 canvas）：
#    col:    1 2 3 4 5 6 7
#    row 1:          X           ← 左支端点
#    row 2:        X             ← 左支中
#    row 3:      X               ← 左支中  (合并点上方)
#    row 4:    X                 ← junction（左支+右支+主干交汇）
#    row 5:      X               ← 右支中
#    row 6:        X             ← 右支中
#    row 7:          X           ← 右支端点
#    row 8:    X                 ← 主干中
#    row 9:    X                 ← 主干端点
#
#  用斜线（对角连续像素），skeletonize 后仍为骨架
#  简化：直接用厚一像素的 Y，skeletonize 会把它变成细线
#
#  更简单的方案：直接给 skeletonize 前的厚 mask，让它自己骨架化，再验。
#  但为精确控制拓扑，用 "稀疏骨架" 直接给 count_identities。
#
#  注意：count_identities 内部调用 skeletonize(mask)，若 mask 本身已是骨架，
#  skeletonize 应保持不变（对单像素宽结构幂等）。
#
#  Y 形骨架（用细线 + 明确交叉点）：
#    col:  1 2 3 4 5
#    row1: X . . . .   ← 左支端点
#    row2: . X . . .
#    row3: . . X . .   ← junction
#    row4: . . . X .   ← 右支中
#    row5: . . . . X   ← 右支端点
#    row3: . . X . .   ← junction（重复，即 row3,col2 为交汇点）
#    row4_main: . . X . .  主干向下
#    row5_main: . . X . .
#    row6_main: . . X . .  主干端点
#
#  最终设计（10×10）：
#    junction 在 (5,5)
#    左支：(3,3)-(4,4)-(5,5)（对角 → skeletonize 保留）
#    右支：(3,7)-(4,6)-(5,5)
#    主干：(5,5)-(6,5)-(7,5)-(8,5)
#
#  验证：branch=3（左支/右支/主干），bifur=1，cc=1
# ─────────────────────────────────────────────────────────────────────────────

def _make_y_mask():
    """
    直接构造一个厚 Y 形 mask（非单像素骨架），让 skeletonize 处理。
    主干竖向，两支斜向，共用一个交汇区域。
    """
    m = np.zeros((20, 20), dtype=bool)
    # 主干：col=10, row=10..17
    for r in range(10, 18):
        m[r, 10] = True
    # 左支：从 (10,10) 向左上 (5,5)
    for i in range(6):
        m[10 - i, 10 - i] = True
    # 右支：从 (10,10) 向右上 (5,15)
    for i in range(6):
        m[10 - i, 10 + i] = True
    return m

def test_y_shape_cc():
    m = _make_y_mask()
    assert count_identities(m, "cc") == 1

def test_y_shape_branch():
    """Y 形骨架应有 3 分支段（左/右/主干各一段）。"""
    m = _make_y_mask()
    n = count_identities(m, "branch")
    assert n == 3, f"Y 形 branch 期望 3，得 {n}"

def test_y_shape_bifur():
    """Y 形有且仅有 1 个分叉点。"""
    m = _make_y_mask()
    n = count_identities(m, "bifur")
    assert n == 1, f"Y 形 bifur 期望 1，得 {n}"


# ─────────────────────────────────────────────────────────────────────────────
#  T3：十字（+ 形）→ cc=1, branch=4, bifur=1
#
#  中心 (5,5)，四臂各延伸 3 像素
#  十字 junction 点在中心（8 邻居中有 ≥3 个骨架像素）
# ─────────────────────────────────────────────────────────────────────────────

def _make_cross_mask():
    m = np.zeros((13, 13), dtype=bool)
    # 水平臂：row=6, col=2..10
    m[6, 2:11] = True
    # 垂直臂：col=6, row=2..10
    m[2:11, 6] = True
    return m

def test_cross_cc():
    m = _make_cross_mask()
    assert count_identities(m, "cc") == 1

def test_cross_branch():
    """十字 → 4 分支段（上/下/左/右臂）。"""
    m = _make_cross_mask()
    n = count_identities(m, "branch")
    assert n == 4, f"十字 branch 期望 4，得 {n}"

def test_cross_bifur():
    """十字中心 1 个分叉点。"""
    m = _make_cross_mask()
    n = count_identities(m, "bifur")
    assert n == 1, f"十字 bifur 期望 1，得 {n}"


# ─────────────────────────────────────────────────────────────────────────────
#  T4：单像素点 → cc=1, branch=1, bifur=0
# ─────────────────────────────────────────────────────────────────────────────

def test_single_pixel_cc():
    m = _make_mask((5, 5), [(2, 2)])
    assert count_identities(m, "cc") == 1

def test_single_pixel_branch():
    m = _make_mask((5, 5), [(2, 2)])
    # 单像素骨架，无邻居 → 非 junction → 1 branch
    assert count_identities(m, "branch") == 1

def test_single_pixel_bifur():
    m = _make_mask((5, 5), [(2, 2)])
    assert count_identities(m, "bifur") == 0


# ─────────────────────────────────────────────────────────────────────────────
#  T5：空 mask → 三粒度均 = 0
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_mask_cc():
    m = np.zeros((10, 10), dtype=bool)
    assert count_identities(m, "cc") == 0

def test_empty_mask_branch():
    m = np.zeros((10, 10), dtype=bool)
    assert count_identities(m, "branch") == 0

def test_empty_mask_bifur():
    m = np.zeros((10, 10), dtype=bool)
    assert count_identities(m, "bifur") == 0


# ─────────────────────────────────────────────────────────────────────────────
#  T6：两条相邻（8-连通）直线 → cc=1（8-连通下合并）
#
#  row3: X X X X
#  row4: X X X X   ← 紧邻，8-连通下为 1 个分量
# ─────────────────────────────────────────────────────────────────────────────

def test_adjacent_lines_cc():
    coords = [(3, c) for c in range(4)] + [(4, c) for c in range(4)]
    m = _make_mask((8, 8), coords)
    # 8-连通 → 紧邻两行视为 1 个分量
    assert count_identities(m, "cc") == 1


# ─────────────────────────────────────────────────────────────────────────────
#  T7：L 形（折角，无分叉点）→ cc=1, bifur=0, branch=1
# ─────────────────────────────────────────────────────────────────────────────

def _make_l_mask():
    """L 形：水平段 row=5,col=2..8 + 垂直段 col=2,row=5..10"""
    m = np.zeros((14, 12), dtype=bool)
    m[5, 2:9] = True    # 水平段
    m[5:11, 2] = True   # 垂直段（与水平段共享 (5,2)）
    return m

def test_l_shape_cc():
    m = _make_l_mask()
    assert count_identities(m, "cc") == 1

def test_l_shape_bifur():
    """L 形折角处邻居数 = 2（水平+垂直），不足 3，无 junction → bifur=0。"""
    m = _make_l_mask()
    n = count_identities(m, "bifur")
    assert n == 0, f"L 形 bifur 期望 0，得 {n}"

def test_l_shape_branch():
    """L 形无 junction，整条骨架为 1 分支段。"""
    m = _make_l_mask()
    n = count_identities(m, "branch")
    assert n == 1, f"L 形 branch 期望 1，得 {n}"


# ─────────────────────────────────────────────────────────────────────────────
#  T8：相邻 junction 像素（防两个紧邻 junction 被算成 2 个 bifur）
#
#  双十字（两个 + 紧邻，共享一条公共边）→ bifur 应视相邻像素而定
#  简单用例：直接做两个紧邻 junction 像素，验其合并为 1 个 bifur
# ─────────────────────────────────────────────────────────────────────────────

def test_adjacent_junctions_merge():
    """
    相邻的 junction 像素（8-连通相邻）应合并为同一个分叉点，而非多计。

    构造 H 形：左竖（col=2）+ 右竖（col=6）+ 横杠（row=5, col=2..6）
    骨架化后，左侧连接处产生多个紧邻 junction 像素（cluster）→ 合并为 1 个 bifur；
    右侧同理 → 合并为 1 个 bifur；共 bifur=2。

    这验证了相邻 junction 不会被多计（4 个紧邻像素 → 1 个分叉点）。
    H 形同时也验证 branch=4（上左/下左/上右/下右 + 横杠共 5 段，但横杠两端各有
    junction 截断 → 上4段 + 横杠中段 = 5，实际视骨架形态而定，故只断言 bifur=2）。
    """
    m = np.zeros((12, 10), dtype=bool)
    m[2:9, 2] = True    # 左竖
    m[2:9, 6] = True    # 右竖
    m[5, 2:7] = True    # 横杠
    n = count_identities(m, "bifur")
    assert n == 2, f"H 形 bifur 期望 2（左右各一 junction cluster），得 {n}"


# ─────────────────────────────────────────────────────────────────────────────
#  T9：端点不被算作 junction（邻居=1 的骨架像素）
# ─────────────────────────────────────────────────────────────────────────────

def test_endpoint_not_junction():
    """
    直线端点邻居数=1，不应被算作 junction。
    一条直线 5 像素 → bifur=0，branch=1。
    """
    m = _make_mask((8, 8), [(4, 1), (4, 2), (4, 3), (4, 4), (4, 5)])
    assert count_identities(m, "bifur") == 0
    assert count_identities(m, "branch") == 1


# ─────────────────────────────────────────────────────────────────────────────
#  T10：非法 granularity 应 raise ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_granularity():
    m = _make_mask((5, 5), [(2, 2)])
    with pytest.raises(ValueError):
        count_identities(m, "invalid_gran")
