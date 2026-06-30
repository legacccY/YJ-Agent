# Phase1 implement 接口契约（多块并行防缝）

> 两 coder 块照此造，不各编各的。集成烟测(integrate 棒)按此核缝。

## 文件领地（不重叠）
- **块A 预训练+烟测**（coder1）：新建 `code/pretrain/`（各范式 launch 脚本 + 配置 + 中间 ckpt hook + state.json 心跳）+ `code/smoke_monitor.py` + `code/submit_pretrain.sh`。**只读** backbones.py/paths.py/datasets.py，不改。
- **块B 评估扩展**（coder2）：改 `code/probes.py`（加 attentive 头 + knn）+ 新建 `code/vindr_loader.py`（跨域 + 3 放射师聚合）+ `code/ckpt_probe_driver.py`（中间 ckpt probe@10% 驱动）+ 改 `code/eval_collect.py`（汇全网格）。**只读** backbones.py/extract_features.py，不改 backbones.py。

## 共享契约（两块都遵守）
1. **路径走真源**：数据/权重路径**只从 `code/paths.py` 取**（已 HPC 自动 pick），禁硬编码。数据集真源 `.portfolio/datasets.json`。
2. **预训练产物 = ckpt**：块A 输出 `results/pretrain/<method>_s<seed>_ep<E>.pth`（中间 ckpt E∈{25,50,100}）。ckpt 内含 `model_state_dict`(ViT-B backbone) + `meta`(method/seed/images_seen/eff_bs/steps)。
3. **块B 消费 ckpt**：块B 从 `results/pretrain/*.pth` 读 backbone 权重做 probe → 输出 `results/eval_grid.csv`，列对齐现有 pilot_hpc.csv schema：`backbone,probe_type,label_frac,domain,split,mAUC,per_class_auc,seed,n_train,n_test,seconds,timestamp` + 新列 `pretrain_seed,pretrain_ep,images_seen`。
4. **state.json 心跳**（防 context 断链）：块A 预训练/烟测每 50-100 步写 `results/state_<run>.json`（step/loss/监控量/timestamp），主线监控读它不读 stdout。
5. **VinDr 标签**：`data/external/vindr_cxr/labels/image_labels_{train,test}.csv`（28 类，train 45001 行需按 image_id 聚合 3 放射师=并集或多数）。NIH∩VinDr 共享类终表见 TODO-E（重训前主线冻结，块B 留参数位）。
6. **NPZ/特征 key**：沿用 extract_features.py 现有 schema（pooled 特征 key=`feats`，标签 key=`labels`，id key=`ids`）——块B 扩 attentive 需 token 级特征，新增 key=`tokens` 不破坏现有。

## 复现零偏离铁律（R4，块A 核心）
- **禁从头重写 SSL 预训练算法**。块A = **包装官方 repo**：MAE(facebookresearch/mae)/DINO(facebookresearch/dino)/MoCo-v3(facebookresearch/moco-v3) 联网 clone；CheXWorld 用本地 `project/meeting/复现/CheXWorld/repo/`(train_jepa.py)。
- 写 thin launch 脚本调官方训练码，注入 `SSL_RECIPES.md` 冻结超参 + NIH 单库 + images-seen 步数控制 + 中间 ckpt 存盘 hook。**超参一字不改官方值**（查不到的标 TODO 不臆想）。
- coder **不启训练**（写完交主线经 gpu_slot 跑）。
