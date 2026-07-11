"""M3D-NCA × KiTS23 训练入口。

服务 NCA-Cyst 项目 § Phase 1a/1b baseline，lever = 打通 M3D-NCA 在 KiTS23 囊肿分割管线。

仿官方 src/examples/train_M3D_NCA.py 搭骨架（模型/agent/loss/Experiment 全用官方原类，零改），
换成本项目 Dataset_KiTS23_3D + config_kits23。额外加：
  - state.json 实时状态（epoch/loss/dice/status）——loop 监控 context 压缩后会断链，
    脚本自写 state.json 才可靠（见 CLAUDE.md 训练监控经验）。
  - 静默发散检测：ep>=10 后 train loss>3 且 test dice<0.05 → state.json 标 status='diverged'，
    主线据此 scancel（NCA 发散 signature：loss 死平 + Dice 0）。

⚠️ 训练步骤**零偏离**：不加梯度裁剪 / 不加 lr warmup / 不改官方任何超参逻辑。
   下方 run_training() 的循环体逐行复制自官方 BaseAgent.train，**仅插入 state.json 写入与
   发散判定**，训练调用（batch_step / intermediate_results / save_state / increase_epoch）零改。

⚠️ NCA seed 说明：本脚本显式设 np/random/torch/cuda seed，但**seed 锁不住 NCA 训练命运**——
   生死很大程度由 epoch-1 的 GPU 随机激活掷定（BatchNorm track_running_stats=False + 随机 fire_rate），
   同 seed 也可能一次收敛一次发散（见 reference_nca_divergence_signature）。故须跑多 seed 报收敛率。

用法（由主线跑；本文件绝不自跑）：
    本地烟测：  python train_kits23.py --config smoke --label_mode binary_all --seed 0
    HPC 全量：  python train_kits23.py --config full  --label_mode binary_all --seed 0
    Phase 1b：  python train_kits23.py --config full  --label_mode cyst        --seed 0
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

# 官方 M3D-NCA repo 根加进 sys.path（与 kits23_dataset 同法，双保险）。
# 环境变量 M3DNCA_OFFICIAL_ROOT 可覆盖（HPC）；缺省=本地相对路径。
_OFFICIAL_ROOT = Path(os.environ.get(
    "M3DNCA_OFFICIAL_ROOT",
    str(Path(__file__).resolve().parents[2] / "Med-NCA" / "M3D-NCA-official")))
if str(_OFFICIAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_OFFICIAL_ROOT))

# 本项目 code/ 目录也加进去，保证 import 同目录模块。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.Model_BasicNCA3D import BasicNCA3D          # noqa: E402
from src.losses.LossFunctions import DiceFocalLoss, DiceLoss  # noqa: E402
from src.utils.Experiment import Experiment                  # noqa: E402
from src.agents.Agent_M3D_NCA import Agent_M3D_NCA           # noqa: E402

from kits23_dataset import Dataset_KiTS23_3D                 # noqa: E402
from config_kits23 import get_config                          # noqa: E402

# Phase2 类平衡(CB)组件（本项目新写，不改官方）——仅 --class_balance on 时启用。
from agent_m3d_nca_cb import Agent_M3D_NCA_CB                 # noqa: E402
from losses_cb import DiceTverskyLoss                          # noqa: E402


def set_seed(seed):
    """设 seed（见文件头：对 NCA 只是尽力而为，锁不住 epoch-1 GPU RNG）。"""
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
      - ep>=10 后发散判定（loss>3 且 dice<0.05 → status='diverged'）。
    训练调用（initialize_epoch / batch_step / intermediate_results / intermediate_evaluation /
    save_state / conclude_epoch / increase_epoch）与官方**完全一致，零改**。
    """
    dice_last = None  # 最近一次 test Dice（评估间隔才更新）

    write_state(state_path, status="starting", config=config_name, label_mode=label_mode,
                seed=seed, epoch=int(exp.currentStep), avg_loss=None, dice=None,
                max_steps=int(exp.get_max_steps()))

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
            # 同时**捕获 Dice 数值**供 state.json / 发散判定（官方 intermediate_evaluation 不返回值）。
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

        # --- 监控插入：发散判定 + 写 state.json ---
        status = "running"
        if epoch >= 10 and avg_loss is not None and avg_loss > 3 and dice_last is not None and dice_last < 0.05:
            status = "diverged"  # NCA 发散 signature：loss 死平>3 + Dice≈0，主线可据此 scancel
        write_state(state_path, status=status, config=config_name, label_mode=label_mode,
                    seed=seed, epoch=int(epoch), avg_loss=avg_loss, dice=dice_last,
                    max_steps=int(exp.get_max_steps()))

        agent.conclude_epoch()
        exp.increase_epoch()

    write_state(state_path, status="done", config=config_name, label_mode=label_mode,
                seed=seed, epoch=int(exp.get_max_steps()), avg_loss=avg_loss, dice=dice_last,
                max_steps=int(exp.get_max_steps()))


def main():
    parser = argparse.ArgumentParser(description="M3D-NCA × KiTS23 训练入口")
    parser.add_argument("--config", choices=["smoke", "full"], default="smoke",
                        help="smoke=本地8GB烟测 / full=HPC 24GB 正式")
    parser.add_argument("--label_mode", choices=["binary_all", "cyst"], default=None,
                        help="binary_all=全前景(Phase1a) / cyst=囊肿label3(Phase1b)；缺省用 config 默认")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model_path", default=None, help="覆盖 config 的 model_path")
    parser.add_argument("--n_epoch", type=int, default=None, help="覆盖 config 的 n_epoch（更快烟测）")
    parser.add_argument("--state_path", default=None,
                        help="state.json 路径（缺省=<model_path>/state.json）")
    # --- Phase2 kill-shot 开关（关键格 b = −global_view, +class_balance） ---
    parser.add_argument("--class_balance", choices=["off", "on"], default="off",
                        help="off=零偏离官方(格a/baseline) / on=前景优先采样+DiceTversky(格b)")
    parser.add_argument("--global_view", choices=["off", "on"], default="off",
                        help="全局视野模块占位；本 Stage 只支持 off（GV 模块后置未实现）")
    parser.add_argument("--tversky_gamma", type=float, default=1.0,
                        help="Focal Tversky γ；1.0=纯 Tversky（默认）。仅 class_balance=on 生效")
    parser.add_argument("--tversky_wfn", type=float, default=0.9,
                        help="Tversky FN 惩罚系数（CB-max 默认 0.9，极端重罚 FN）；w_fp 派生=1-wfn。仅 on 生效")
    parser.add_argument("--cb_copy_paste_frac", type=float, default=0.02,
                        help="copy-paste 增广目标前景占比（默认 0.02=2%）。仅 on 生效")
    args = parser.parse_args()

    # global_view 本 Stage 未实现，on 直接报错（避免静默当 off 跑造成误读）。
    if args.global_view == "on":
        raise NotImplementedError(
            "--global_view on 未实现（GV 模块本 Stage 后置）；关键格 b 需 --global_view off。")

    cfg = get_config(args.config)
    if args.label_mode is not None:
        cfg['label_mode'] = args.label_mode
    if args.model_path is not None:
        cfg['model_path'] = args.model_path
    if args.n_epoch is not None:
        cfg['n_epoch'] = args.n_epoch
    # CB 开关写入 config（供 agent 读 + state.json 存档溯源）。
    cfg['class_balance'] = args.class_balance
    cfg['global_view'] = args.global_view
    cfg['tversky_gamma'] = args.tversky_gamma
    cfg['tversky_wfn'] = args.tversky_wfn
    cfg['cb_copy_paste_target_frac'] = args.cb_copy_paste_frac
    cfg.setdefault('cb_max_retries', 20)         # 组件① 无前景 case 回退用（中心采样已不 retry）
    cfg.setdefault('cb_copy_paste_cap', 8)       # 组件② 粘贴份数硬上限

    label_mode = cfg['label_mode']
    cases_subset = cfg.get('cases_subset', None)

    set_seed(args.seed)

    # state.json 路径
    os.makedirs(cfg['model_path'], exist_ok=True)
    state_path = args.state_path or os.path.join(cfg['model_path'], "state.json")
    print(f"[train_kits23] config={args.config} label_mode={label_mode} seed={args.seed}")
    print(f"[train_kits23] model_path={cfg['model_path']}")
    print(f"[train_kits23] state.json -> {state_path}")

    # --- 数据集（cases_subset/label_mode 必须构造时传，getFilesInPath 早于 set_experiment） ---
    dataset = Dataset_KiTS23_3D(cases_subset=cases_subset, label_mode=label_mode)

    device = torch.device(cfg['device'])
    # 两级 NCA：与官方 train_M3D_NCA.py 一致（kernel 7 → kernel 3）。
    ca1 = BasicNCA3D(cfg['channel_n'], cfg['cell_fire_rate'], device,
                     hidden_size=cfg['hidden_size'], kernel_size=7, input_channels=cfg['input_channels']).to(device)
    ca2 = BasicNCA3D(cfg['channel_n'], cfg['cell_fire_rate'], device,
                     hidden_size=cfg['hidden_size'], kernel_size=3, input_channels=cfg['input_channels']).to(device)
    ca = [ca1, ca2]
    # class_balance=on → 用前景优先采样子类（组件①）；off → 官方原类（零偏离）。
    if args.class_balance == "on":
        agent = Agent_M3D_NCA_CB(ca)
    else:
        agent = Agent_M3D_NCA(ca)

    exp = Experiment([cfg], dataset, ca, agent)
    dataset.set_experiment(exp)
    exp.set_model_state('train')

    # Windows: num_workers=0（避免 spawn 复杂度；>0 时官方 Dataset 不保证 spawn 安全）。
    # pin_memory=False（spawn worker 不支持）。
    data_loader = torch.utils.data.DataLoader(
        dataset, shuffle=True, batch_size=exp.get_from_config('batch_size'),
        num_workers=0, pin_memory=False)

    # class_balance=on → DiceTversky（组件③，极端重罚 FN）；off → 官方 DiceFocalLoss（零偏离）。
    if args.class_balance == "on":
        w_fn = args.tversky_wfn
        loss_function = DiceTverskyLoss(w_fn=w_fn, w_fp=1.0 - w_fn, gamma=args.tversky_gamma)
        print("[train_kits23] class_balance=ON (CB-max 三组件): "
              "①囊肿中心采样 + ②copy-paste增广(frac=%.3f) + ③DiceTversky(w_fn=%.2f,w_fp=%.2f,gamma=%.3f)"
              % (args.cb_copy_paste_frac, w_fn, 1.0 - w_fn, args.tversky_gamma))
    else:
        loss_function = DiceFocalLoss()

    t0 = time.time()
    try:
        run_training(agent, exp, data_loader, loss_function, state_path,
                     args.config, label_mode, args.seed)
    except Exception as e:
        # 崩溃也落一笔 state.json，便于主线判因
        write_state(state_path, status="crashed", config=args.config, label_mode=label_mode,
                    seed=args.seed, error=repr(e))
        raise
    print(f"[train_kits23] 训练结束，用时 {time.time()-t0:.1f}s")

    # 官方收尾：测试集平均 Dice
    print("[train_kits23] 最终测试集 Dice：")
    agent.getAverageDiceScore()


if __name__ == "__main__":
    # Windows spawn 守卫（DataLoader 多进程 & CUDA 必需）。
    main()
