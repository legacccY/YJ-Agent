# 阶段三：VisiScore-Net 模型训练

## 目标

训练一个轻量级多维图像质量评估网络，输入一张皮肤照片，输出 5 个维度的质量评分（清晰度/光照/完整度/色温/对比度）以及对应的文字改进建议。**该评分向量 $\mathbf{q} \in [0,1]^5$ 将作为阶段四 Q-VIB 编码器的条件输入和质量自适应先验的调控信号。**

---

## 前置条件

- 阶段二完成：`paired_dataset/` 和 `quality_labels.csv` 已就绪
- DataLoader 验证通过

---

## 本阶段工具

| 工具 | 用途 |
|------|------|
| timm | 加载 MobileNetV3 / EfficientNet / tinyViT 预训练权重 |
| torch.cuda.amp | FP16 混合精度训练（内置，无需额外安装） |
| wandb | 记录每次 run 的 loss 曲线、5 维评分分布、超参，支持多 run 对比 |
| scipy | 计算 PLCC / SRCC 相关系数（评估指标） |

---

## 关键技术决策点

1. **Backbone 选择**：
   - MobileNetV3-Small（最轻量，~1.5M 参数，最省显存）
   - EfficientNet-B0（精度更好，~5.3M 参数）
   - tinyViT-5M（Transformer 架构，~5M 参数，可能泛化更好）
   - 决策标准：在 RTX 4070 上 Batch 128 FP16 显存 ≤ 4GB

2. **人工标注规模**：0 张（纯弱监督）/ 500 张 / 1000 张。影响标签质量和额外标注工作量

3. **降质档位**：3 档 / 5 档 / 连续值。与阶段二决策保持一致

---

## 交付物清单

| 文件 | 用途 |
|------|------|
| `models/visiscore.py` | 模型定义：Backbone + 5 个回归头。**`forward()` 只返回 `q_vector`（shape `(batch, 5)`），不改变推理接口；另实现 `forward_features()` 返回 `(features, q_vector)` 元组，其中 `features` 为 Backbone 末端池化向量，专供阶段四 Q-VIB 编码器复用** |
| `models/losses.py` | 多任务损失：MSE + Ranking Loss + Consistency Loss |
| `train_visiscore.py` | 训练脚本，支持 `--resume`、FP16 混合精度、wandb 日志 |
| `eval_visiscore.py` | 评估脚本，与 BRISQUE / NIMA 对比实验 |
| `checkpoints/best_visiscore.pth` | 最佳模型权重 |
| `results/eval_report_visiscore.md` | 评估报告，含指标表格和分析 |

---

## 工作步骤

1. **模型定义**：选定 Backbone，接 5 个独立回归头，每头输出 [0, 1] 范围评分（Sigmoid 激活）。`forward()` 只返回 `q_vector`（shape `(batch, 5)`）；另实现 `forward_features()` 返回 `(features, q_vector)` 元组，`features` 为 Backbone 末端池化向量，供阶段四 Q-VIB 编码器复用
2. **损失函数设计**：MSE 回归损失 + 排序一致性损失（确保退化程度与评分负相关）
3. **训练**：FP16 混合精度，Batch 128，约 20 epoch，~40h，全程支持断点续训
4. **评估**：与 BRISQUE（无参考 IQA）和 NIMA（神经网络 IQA）对比，统计 PLCC/SRCC 相关系数
5. **模型导出**：保存权重，验证推理速度（单张 <100ms）。**导出时确保 `torch.jit.script` 或 `torch.onnx.export` 可选，方便阶段五 Agent 系统低开销调用**

---

## 验收标准

- 在测试集上 PLCC/SRCC ≥ 0.7（至少一个维度显著优于 BRISQUE baseline）
- 单张图片推理时间 <100ms（RTX 4070）
- 评估报告中有完整的维度对比表格
- **$\mathbf{q}$ 输出值域 [0,1]，5 个维度之间有合理区分度（非高度共线），均值 $\bar{q}$ 在退化/原始样本间有明显分离**

---

## 硬件/资源约束

- **显存**：Batch 128 FP16 ≈ 3.5GB，留有余量，不应超过 6GB
- **训练时间**：~2h/epoch × 20 epoch ≈ 40h，建议分多天训练
- **必须支持** `--resume checkpoint_path` 断点续训，防止意外中断丢失进度

---

## 注意事项

- 5 个回归头共享 Backbone 特征提取，降低参数量和计算量
- Ranking Loss 的采样策略：同一原图的不同退化程度应有明确的评分排序
- 模型推理时需要处理不同分辨率的输入，统一 resize 到固定尺寸（如 224×224）
- wandb 自动保存训练曲线，每次 run 取名有意义（如 `mobilev3-batch128-lr1e3`），方便后续论文截图
- 如果弱标注质量差，可能需要回到阶段二补充人工标注，预留迭代余地
- **与 Q-VIB 的接口约定**：VisiScore-Net 输出的 $\mathbf{q}$ 向量是 Q-VIB 编码器的条件输入——两者通过 $\mathbf{q}$ 解耦。VisiScore-Net 不需要知道 Q-VIB 的存在，但输出格式（`torch.Tensor`，shape `(batch, 5)` 训练时 / `(5,)` 推理时，值域 `[0,1]`）必须在代码注释中明确约定，避免阶段四集成时出现类型/形状 mismatch。阶段四对 $\mathbf{q}$ 有两种用法：质量自适应先验侧使用 `q.mean()`（标量 $\bar{q}$），质量分词器侧使用完整 `q`（shape `(5,)`）——两路均从同一个 `q_vector` 派生，VisiScore-Net 无需区分输出
