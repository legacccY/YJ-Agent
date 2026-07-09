"""UNet3D × KiTS23 训练入口（Phase 1c 同口径对照）。

服务 NCA-Cyst 项目 § Phase 1c，lever = UNet3D 同口径对照，亲手复现「主流模型囊肿近随机 vs NCA 能跑」。

仿 train_kits23.py 骨架（同一 Dataset_KiTS23_3D + 同 state.json 监控 + 同 env 路径覆盖 + 同 argparse），
把模型/agent/loss 换成官方 UNet3D 对照三件套（全用官方原类，零改）：
  - 模型： from unet import UNet3D   （官方 train_Unet3D.py：UNet3D(in_channels=1, padding=1, out_classes=1)）
  - agent：src.agents.Agent_UNet.Agent（官方，3D 分支 unsqueeze 加通道维）
  - loss： src.losses.LossFunctions.DiceBCELoss（官方 train_Unet3D.py 用它）
  - 评估：agent.test(DiceLoss) / getAverageDiceScore —— 与 M3D-NCA **同一套 Dice 口径**（同口径命门）。

⚠️ 依赖 `unet` pip 包（`from unet import UNet3D`）——不在官方已验证依赖里，HPC 可能没装。
   主线部署前须在 HPC DTN 上 `pip install unet`（见 README Phase 1c 段）。本脚本不装。

⚠️ 训练步骤零偏离：不加梯度裁剪 / 不加 lr warmup / 不改官方任何超参逻辑。run_training() 循环体
   逐行复制自官方 BaseAgent.train，**仅插入** state.json 写入与发散判定；训练调用零改。

⚠️ 发散检测钩子沿用 NCA 口径便于统一监控，但 **UNet 一般不静默发散**（有正常反传的稳定卷积网），
   此钩子对 UNet 非必需——保留只为让 state.json schema / 主线监控流程与 M3D-NCA 完全一致。
   且 UNet 用 DiceBCELoss，其量级通常 <2，几乎不会误触发 loss>3 的 diverged 判定。

用法（由主线跑；本文件绝不自跑）：
    本地烟测：  python train_unet_kits23.py --config smoke --label_mode binary_all --seed 0
    HPC 全量：  python train_unet_kits23.py --config full  --label_mode binary_all --seed 0
    Phase 1b 对照：python train_unet_kits23.py --config full --label_mode cyst --seed 0
"""
import os
import sys
import json
import time
import argparse
import random
import datetime
from pathlib import Path

import numpy as np
import torch

# 官方 M3D-NCA repo 根加进 sys.path（才能 import src.* 及 unet 所在环境）。
# 环境变量 M3DNCA_OFFICIAL_ROOT 可覆盖（HPC）；缺省=本地相对路径。
_OFFICIAL_ROOT = Path(os.environ.get(
    "M3DNCA_OFFICIAL_ROOT",
    str(Path(__file__).resolve().parents[2] / "Med-NCA" / "M3D-NCA-official")))
if str(_OFFICIAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_OFFICIAL_ROOT))

# 本项目 code/ 目录也加进去，保证 import 同目录模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from unet import UNet3D                                        # noqa: E402  ⚠️ 需 pip install unet
from src.losses.LossFunctions import DiceBCELoss, DiceLoss     # noqa: E402
from src.utils.Experiment import Experiment                    # noqa: E402
from src.agents.Agent_UNet import Agent as Agent_UNet          # noqa: E402

from kits23_dataset import Dataset_KiTS23_3D                   # noqa: E402
from config_unet_kits23 import get_unet_config                 # noqa: E402


def set_seed(seed):
    """设 seed（UNet 是稳定卷积网，seed 可比 NCA 更好地锁住结果，但仍尽力而为）。"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def write_state(state_path, **fields):
    """原子写 state.json（先写临时文件再 rename，避免监控读到半截）。"""
    fields['updated'] = datetime.datetime.now().isoformat(timespec='seconds')
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(fields, f, ensure_ascii=False, indent=2)
    os.replace(tmp, state_path)


def run_training(agent, exp, dataloader, loss_f, state_path, config_name, label_mode, seed):
    r"""训练循环。

    循环体逐行复制自官方 src/agents/Agent.py BaseAgent.train，**仅插入**：
      - 每 epoch 后写 state.json（epoch/avg_loss/status）；
      - evaluate_interval 时算 test Dice 记入 state.json；
      - ep>=10 后发散判定（loss>3 且 dice<0.05 → status='diverged'）——UNet 非必需，见文件头。
    训练调用（initialize_epoch / batch_step / intermediate_results / save_state /
    conclude_epoch / increase_epoch）与官方**完全一致，零改**。
    评估段复制自官方 intermediate_evaluation，仅额外**捕获 Dice 数值**供 state.json（官方不返回值）。
    """
    dice_last = None  # 最近一次 test Dice（评估间隔才更新）

    write_state(state_path, status="starting", model="UNet3D", config=config_name,
                label_mode=label_mode, seed=seed, epoch=int(exp.currentStep),
                avg_loss=None, dice=None, max_steps=int(exp.get_max_steps()))

    for epoch in range(exp.currentStep, exp.get_max_steps() + 1):
        print("Epoch: " + str(epoch))
        loss_log = {}
        for m in range(agent.output_channels):
            loss_log[m] = []
        agent.initialize_epoch()
        print('Dataset size: ' + str(len(dataloader)))
        for i, data in enumerate(dataloader):
            loss_item = agent.batch_step(data, loss_f)
            for key in loss_item.keys():
                loss_log[key].append(loss_item[key])
        agent.intermediate_results(epoch, loss_log)

        # --- 监控插入：本 epoch 平均训练 loss（key 0 = 唯一 output channel） ---
        vals = loss_log.get(0, [])
        avg_loss = (sum(vals) / len(vals)) if len(vals) > 0 else None

        if epoch % exp.get_from_config('evaluate_interval') == 0:
            print("Evaluate model")
            # 复制自官方 intermediate_evaluation：用 test Dice 评估 + 写 tensorboard 标量，
            # 同时捕获 Dice 数值供 state.json / 发散判定（官方 intermediate_evaluation 不返回值）。
            diceLoss = DiceLoss(useSigmoid=True)
            eval_log = agent.test(diceLoss)
            for key in eval_log.keys():
                img_plot = agent.plot_results_byPatient(eval_log[key])
                agent.exp.write_figure('Patient/dice/mask' + str(key), img_plot, epoch)
                if len(eval_log[key]) > 0:
                    mean_dice = sum(eval_log[key].values()) / len(eval_log[key])
                    agent.exp.write_scalar('Dice/test/mask' + str(key), mean_dice, epoch)
                    agent.exp.write_histogram('Dice/test/byPatient/mask' + str(key),
                                              np.fromiter(eval_log[key].values(), dtype=float), epoch)
                    if key == 0:
                        dice_last = float(mean_dice)

        if epoch % exp.get_from_config('save_interval') == 0:
            print("Model saved")
            agent.save_state(os.path.join(exp.get_from_config('model_path'), 'models',
                                          'epoch_' + str(exp.currentStep)))

        # --- 监控插入：发散判定 + 写 state.json（UNet 一般不触发，见文件头） ---
        status = "running"
        if epoch >= 10 and avg_loss is not None and avg_loss > 3 and dice_last is not None and dice_last < 0.05:
            status = "diverged"
        write_state(state_path, status=status, model="UNet3D", config=config_name,
                    label_mode=label_mode, seed=seed, epoch=int(epoch),
                    avg_loss=avg_loss, dice=dice_last, max_steps=int(exp.get_max_steps()))

        agent.conclude_epoch()
        exp.increase_epoch()

    write_state(state_path, status="done", model="UNet3D", config=config_name,
                label_mode=label_mode, seed=seed, epoch=int(exp.get_max_steps()),
                avg_loss=avg_loss, dice=dice_last, max_steps=int(exp.get_max_steps()))


def main():
    parser = argparse.ArgumentParser(description="UNet3D × KiTS23 训练入口（Phase 1c 同口径对照）")
    parser.add_argument("--config", choices=["smoke", "full"], default="smoke",
                        help="smoke=本地8GB烟测 / full=HPC 24GB 正式")
    parser.add_argument("--label_mode", choices=["binary_all", "cyst"], default=None,
                        help="binary_all=全前景(Phase1a) / cyst=囊肿label3(Phase1b)；缺省用 config 默认")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model_path", default=None, help="覆盖 config 的 model_path")
    parser.add_argument("--n_epoch", type=int, default=None, help="覆盖 config 的 n_epoch（更快烟测）")
    parser.add_argument("--state_path", default=None,
                        help="state.json 路径（缺省=<model_path>/state.json）")
    args = parser.parse_args()

    cfg = get_unet_config(args.config)
    if args.label_mode is not None:
        cfg['label_mode'] = args.label_mode
    if args.model_path is not None:
        cfg['model_path'] = args.model_path
    if args.n_epoch is not None:
        cfg['n_epoch'] = args.n_epoch

    label_mode = cfg['label_mode']
    cases_subset = cfg.get('cases_subset', None)

    set_seed(args.seed)

    # state.json 路径
    os.makedirs(cfg['model_path'], exist_ok=True)
    state_path = args.state_path or os.path.join(cfg['model_path'], "state.json")
    print(f"[train_unet_kits23] config={args.config} label_mode={label_mode} seed={args.seed}")
    print(f"[train_unet_kits23] model_path={cfg['model_path']}")
    print(f"[train_unet_kits23] state.json -> {state_path}")

    # --- 数据集：与 M3D-NCA 完全同源（同 Dataset_KiTS23_3D + 同 cases_subset/label_mode） ---
    #     cases_subset/label_mode 必须构造时传，getFilesInPath 早于 set_experiment（同 train_kits23 说明）。
    dataset = Dataset_KiTS23_3D(cases_subset=cases_subset, label_mode=label_mode)

    device = torch.device(cfg['device'])
    # 官方 UNet3D，零改：train_Unet3D.py 的 UNet3D(in_channels=1, padding=1, out_classes=1)。
    # out_classes=1 ↔ config output_channels=1（二分类），保证 train/test 循环 range(output_channels) 对齐。
    ca = UNet3D(in_channels=1, padding=1, out_classes=1).to(device)
    agent = Agent_UNet(ca)

    # Experiment 顺序与 train_kits23.py 一致：先构造 → set_experiment → set_model_state('train')。
    exp = Experiment([cfg], dataset, ca, agent)
    dataset.set_experiment(exp)
    exp.set_model_state('train')

    # 对比卖点用：UNet 参数量（NCA ~1.3e4 vs UNet 百万级）。
    n_params = sum(p.numel() for p in ca.parameters() if p.requires_grad)
    print(f"[train_unet_kits23] UNet3D 可训练参数量: {n_params}")

    # Windows: num_workers=0（避免 spawn 复杂度）；pin_memory=False（spawn worker 不支持）。
    data_loader = torch.utils.data.DataLoader(
        dataset, shuffle=True, batch_size=exp.get_from_config('batch_size'),
        num_workers=0, pin_memory=False)

    loss_function = DiceBCELoss()  # 官方 train_Unet3D.py 用 DiceBCELoss

    t0 = time.time()
    try:
        run_training(agent, exp, data_loader, loss_function, state_path,
                     args.config, label_mode, args.seed)
    except Exception as e:
        # 崩溃也落一笔 state.json，便于主线判因
        write_state(state_path, status="crashed", model="UNet3D", config=args.config,
                    label_mode=label_mode, seed=args.seed, error=repr(e))
        raise
    print(f"[train_unet_kits23] 训练结束，用时 {time.time()-t0:.1f}s")

    # 官方收尾：测试集平均 Dice（与 M3D-NCA 同一评估口径）。
    print("[train_unet_kits23] 最终测试集 Dice：")
    agent.getAverageDiceScore()


if __name__ == "__main__":
    # Windows spawn 守卫（DataLoader 多进程 & CUDA 必需）。
    main()
