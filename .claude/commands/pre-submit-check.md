# pre-submit-check

论文投稿前数字一致性检查。提交前必须运行。

## 触发场景

用户说"准备投稿"、"提交之前检查一下"、"pre-submit check"、"投稿前"。

## 执行步骤

### Step 1：定位论文文件

询问或从 `submission_state.json` 推断：
- 主 tex 文件路径（如 `papers/sub_bmvc/main.tex`）
- 对应的 registry 文件（`experiments/registry.json` 或子论文的独立注册表）
- OVERVIEW.md 的 Critical Numbers 表

### Step 2：提取论文中的关键数字

读取 .tex 文件，提取以下模式的数字：
- 数值指标（如 `PSNR 28.12`、`AUC 0.707`、`ECE 0.098`）
- 百分比（如 `59\%`、`15.5\%`、`68\%`）
- 统计量（如 `$\rho=-0.192$`、`$p<0.05$`）
- Table 中的数字

将提取结果整理为清单：

```
提取到的关键数字：
1. Section 4.1: AUC = 0.707
2. Section 4.2: ECE = 0.098
3. Table 1, Row 3: PSNR = 28.12
4. Figure 3 caption: ρ = -0.192
...
```

### Step 3：与 registry.json 对比

对每个数字，在 registry.json 中查找对应 run_id：

```
检查结果：
✅ AUC 0.707 → run_id: 20250515_143022_qvib_full (paper_reference: "Table 1, row F")
✅ ECE 0.098 → run_id: 20250515_143022_qvib_full
❌ PSNR 28.12 → 未找到对应 run_id！请确认数据来源。
⚠️ ρ = -0.192 → run_id: 20250516_080000_ham10000_zero_shot（paper_reference 为空，建议补录）
```

所有 ❌ 项必须在投稿前解决。⚠️ 项建议解决。

### Step 4：与 OVERVIEW.md 的 Critical Numbers 对比

对每个在 OVERVIEW.md 中登记的数字，检查是否与论文引用一致：

```
Critical Numbers 对比：
✅ Q-VIB AUC: OVERVIEW 0.707 = 论文 0.707
✅ VisiScore PLCC: OVERVIEW 0.924 = 论文 0.924
❌ ECE baseline: OVERVIEW 0.146 ≠ 论文 0.149（差异：0.003，请确认使用哪个数字）
```

### Step 5：检查图表验证标记

检查 `figures/` 目录下是否所有图表都有 `.verified` 标记文件：

```
图表验证状态：
✅ fig_1.pdf → fig_1.verified 存在（2025-05-17）
✅ fig_2.pdf → fig_2.verified 存在（2025-05-17）
❌ fig_3.pdf → 未找到 fig_3.verified，请运行 /validate-figures
⚠️ fig_4.pdf → fig_4.verified 存在，但日期较旧（2025-05-10），图表是否在此之后修改过？
```

### Step 6：检查匿名化

读取 .tex 文件，搜索以下模式（可能暴露身份）：
- 邮箱地址
- 机构全名（在方法章节中）
- 代码仓库链接（非匿名链接）
- 自我引用（`anonymous202*` 等）
- 致谢章节

输出：
```
匿名化检查：
❌ 发现机构名：Section 1, Line 23 "Xi'an Jiaotong-Liverpool University"
⚠️ 发现代码链接：Figure 5 caption（请确认是否为匿名链接）
✅ 无邮箱地址
✅ 致谢章节：已注释/删除
```

### Step 7：格式检查

- 页数是否超出限制（从 `submission_state.json` 读取 `page_limit`）
- 参考文献格式（bibtex 编译无警告）
- 图表文件是否为 PDF（非 PNG，确保矢量质量）
- DPI（PNG 备用图 >= 300 DPI）

### Step 8：输出汇总报告

```
投稿前检查汇总
==============
数字溯源：  ✅ 12/13 已溯源，❌ 1 待处理
OVERVIEW 一致性：✅ 全部一致
图表验证：  ✅ 3/4 已验证，❌ 1 待运行 /validate-figures
匿名化：    ❌ 2 处问题，需修复
格式：      ✅ 页数 11/12，参考文献无警告

⛔ 状态：不建议提交。请先解决所有 ❌ 项。

必须修复：
1. PSNR 28.12 — 补录 run_id 到 registry.json
2. fig_3.pdf — 运行 /validate-figures 完成验证
3. 匿名化 — 删除 Section 1 中的机构名
```

## 注意事项

- 数字差异在 0.001 以内可能是四舍五入，但必须确认
- 如果某个数字是"已知近似值"（如 claim "约 59%"），在 INFO.md 中注明
- rebuttal 阶段新增的实验数字，必须同样走 registry.json 注册流程
