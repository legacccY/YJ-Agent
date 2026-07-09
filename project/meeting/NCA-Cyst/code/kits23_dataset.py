"""KiTS23 dataset subclass for official M3D-NCA.

服务 NCA-Cyst 项目 § Phase 1a/1b baseline，lever = 打通 M3D-NCA 在 KiTS23 囊肿分割的数据管线。

设计目标：**不扁平化复制 34GB 数据**。官方 `Dataset_NiiGz_3D` 假设 image / label 分放两个扁平
目录、同名对应；KiTS23 是 `dataset/case_XXXXX/{imaging,segmentation}.nii.gz` 的嵌套结构。
本子类通过 override `getFilesInPath`（改文件枚举）+ 复制 `__getitem__`（仅改路径拼接 & label 合并）
直接读原生 case 子目录，官方 `M3D-NCA-official/` 下文件一个都不改。

复现零偏离：除「路径拼接」「label_mode 选择」两处必要适配外，`__getitem__` 与官方逐行一致
（预处理 / torchio 归一化 / 缓存 / rescale 全部原样）。
"""
import os
import sys
from pathlib import Path

import numpy as np
import torchio

# 把官方 M3D-NCA repo 根加进 sys.path，才能 import 其 src.* 包。
# 目录关系：project/meeting/NCA-Cyst/code/  <->  project/meeting/Med-NCA/M3D-NCA-official/
# 环境变量 M3DNCA_OFFICIAL_ROOT 可覆盖（HPC 用 /gpfs/work/bio/jiayu2403/mednca/M3D-NCA-official）。
_OFFICIAL_ROOT = Path(os.environ.get(
    "M3DNCA_OFFICIAL_ROOT",
    str(Path(__file__).resolve().parents[2] / "Med-NCA" / "M3D-NCA-official")))
if str(_OFFICIAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_OFFICIAL_ROOT))

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D  # noqa: E402


class Dataset_KiTS23_3D(Dataset_NiiGz_3D):
    r"""KiTS23 3D 数据集，直接读 `dataset/case_XXXXX/` 原生嵌套结构。

    #Args
        cases_subset: 只加载子集（本地烟测用），支持三种取值：
            - None       → 全部 case（默认）。
            - int N      → 排序后前 N 个 case。
            - list[str]  → 指定 case id 列表（按给定顺序，用于控制 train/test split 落点）。
        label_mode: 目标类选择：
            - 'binary_all' (Phase 1a) → label>0 全前景=1（等价官方 `label[label>0]=1`）。
            - 'cyst'       (Phase 1b) → 囊肿(KiTS23 label==3)=1，其余=0。

    .. note:: `cases_subset` 必须在**构造时**传入——官方 `Experiment()` 在
        `dataset.set_experiment()` 之前就会调用 `getFilesInPath`，那时 `self.exp` 尚未挂上，
        无法从 config 读取。故 case 子集走构造参数而非 config。
    """

    def __init__(self, cases_subset=None, label_mode="binary_all", slice=None, resize=True):
        super().__init__(slice=slice, resize=resize)
        if slice is not None:
            # 官方 2D 切片模式与 KiTS23 嵌套结构未适配；本子类只支持 M3D-NCA 的 3D 模式。
            raise NotImplementedError("Dataset_KiTS23_3D 仅支持 3D（slice=None）。")
        if label_mode not in ("binary_all", "cyst"):
            raise ValueError(f"label_mode 只能是 'binary_all' 或 'cyst'，收到 {label_mode!r}")
        self.cases_subset = cases_subset
        self.label_mode = label_mode

    # ------------------------------------------------------------------
    #  文件枚举：override 官方（官方假设扁平一堆 .nii.gz）
    # ------------------------------------------------------------------
    def getFilesInPath(self, path):
        r"""枚举 `path` 下的 KiTS23 case 子目录。

        `path` 由 config 的 img_path / label_path 传入（本项目两者都设为 dataset 根）。
        对 image/label 两次调用返回**完全一致**的字典（同一份 case 列表、同序），
        保证官方 DataSplit 的 index 切分对 image 与 label 对齐。

        #Returns:
            dic (dict): {case_id: {0: (case_id, case_id, 0)}}
            —— 与官方 3D 分支同构；此处「文件名」= case 目录名，真实文件名在 __getitem__ 里拼。
        """
        if self.slice is not None:
            raise NotImplementedError("Dataset_KiTS23_3D 仅支持 3D（slice=None）。")

        # 只取存在 imaging.nii.gz 的 case 目录，排序保证 split 可复现。
        all_cases = sorted(
            d for d in os.listdir(path)
            if d.startswith("case_")
            and os.path.isdir(os.path.join(path, d))
            and os.path.exists(os.path.join(path, d, "imaging.nii.gz"))
        )

        # 应用 cases_subset
        if self.cases_subset is None:
            cases = all_cases
        elif isinstance(self.cases_subset, int):
            cases = all_cases[: self.cases_subset]
        else:  # list / tuple of case ids —— 保留给定顺序，过滤掉不存在的
            existing = set(all_cases)
            cases = [c for c in self.cases_subset if c in existing]
            missing = [c for c in self.cases_subset if c not in existing]
            if missing:
                print(f"[Dataset_KiTS23_3D] WARNING: cases_subset 中缺失/无 imaging 的 case 被跳过: {missing}")

        dic = {}
        for case_id in cases:
            # 3D 模式：id = case 目录名；元组 (name, p_id, slice_id) = (case_id, case_id, 0)
            dic[case_id] = {0: (case_id, case_id, 0)}
        return dic

    # ------------------------------------------------------------------
    #  取样：复制自官方 Nii_Gz_Dataset_3D.__getitem__
    #  仅改两处：(1) 路径拼接到 case 子目录固定文件名；(2) label 按 label_mode 选择类。
    #  其余（torchio rescale/znorm、缓存、rescale3d/preprocessing3d、expand_dims）逐行一致、零偏离。
    # ------------------------------------------------------------------
    def __getitem__(self, idx):
        r"""复制自官方 `Nii_Gz_Dataset_3D.__getitem__`（3D 路径），
        仅改「路径拼接」与「label 合并」两处，标注见行内。"""
        rescale = torchio.RescaleIntensity(out_min_max=(0, 1), percentiles=(0.5, 99.5))
        znormalisation = torchio.ZNormalization()

        img = self.data.get_data(key=self.images_list[idx])
        if not img:
            img_name, p_id, img_id = self.images_list[idx]
            label_name, _, _ = self.labels_list[idx]

            # --- KiTS23 适配 (1/2)：image 与 label 同在 case_XXXXX/ 子目录下、固定文件名。
            #     官方原句： img, label = self.load_item(os.path.join(self.images_path, img_name)),
            #                              self.load_item(os.path.join(self.labels_path, img_name))
            #     （官方假设两目录同名文件；KiTS23 是嵌套固定名。images_path/labels_path 均为 dataset 根，img_name=case_id）
            img = self.load_item(os.path.join(self.images_path, img_name, "imaging.nii.gz"))
            label = self.load_item(os.path.join(self.labels_path, img_name, "segmentation.nii.gz"))

            # 2D 分支：KiTS23 只用 3D，此分支保留但不会进入（slice 恒 None）。
            if self.slice is not None:
                if len(img.shape) == 4:
                    img = img[..., 0]
                if self.exp.get_from_config('rescale') is not None and self.exp.get_from_config('rescale') is True:
                    img, label = self.rescale3d(img), self.rescale3d(label, isLabel=True)
                if self.slice == 0:
                    img, label = img[img_id, :, :], label[img_id, :, :]
                elif self.slice == 1:
                    img, label = img[:, img_id, :], label[:, img_id, :]
                elif self.slice == 2:
                    img, label = img[:, :, img_id], label[:, :, img_id]
                if len(img.shape) == 4:
                    img = img[..., 0]
                img, label = self.preprocessing(img), self.preprocessing(label, isLabel=True)
            # 3D
            else:
                if len(img.shape) == 4:
                    img = img[..., 0]
                img = np.expand_dims(img, axis=0)
                img = rescale(img)
                img = np.squeeze(img)
                if self.exp.get_from_config('rescale') is not None and self.exp.get_from_config('rescale') is True:
                    img, label = self.rescale3d(img), self.rescale3d(label, isLabel=True)
                if self.exp.get_from_config('keep_original_scale') is not None and self.exp.get_from_config('keep_original_scale'):
                    img, label = self.preprocessing3d(img), self.preprocessing3d(label, isLabel=True)
                # Add dim to label
                if len(label.shape) == 3:
                    label = np.expand_dims(label, axis=-1)
            img_id = "_" + str(p_id) + "_" + str(img_id)

            # 缓存的是**原始多类 label**（合并前），跨 epoch 复用。
            self.data.set_data(key=self.images_list[idx], data=(img_id, img, label))
            img = self.data.get_data(key=self.images_list[idx])

        id, img, label = img

        size = self.size

        # Create patches from full resolution
        if self.exp.get_from_config('patchify') is not None and self.exp.get_from_config('patchify') is True and self.state == "train":
            img, label = self.patchify(img, label)

        if len(size) > 2:
            size = size[0:2]

        # Normalize image
        img = np.expand_dims(img, axis=0)
        if np.sum(img) > 0:
            img = znormalisation(img)
        img = rescale(img)
        img = img[0]

        # --- KiTS23 适配 (2/2)：按 label_mode 选目标类。
        #     官方原句： label[label > 0] = 1   （原地改，会污染缓存的原始 label）
        #     这里用**非原地**赋值，保住缓存里的多类原始 label 不被破坏——否则 'cyst' 模式
        #     第二个 epoch 会对已二值化的 label 再取 ==3 得全零（原地改的隐患）。
        if self.label_mode == "binary_all":
            label = (label > 0).astype(label.dtype)          # 等价官方全前景合并（肾区）
        elif self.label_mode == "cyst":
            label = (np.rint(label) == 3).astype(label.dtype)  # 囊肿 = KiTS23 label 3
        else:
            raise ValueError(f"未知 label_mode: {self.label_mode!r}")

        # Number of defined channels（2D 专用；3D size 长度=3 不进入）
        if len(self.size) == 2:
            img = img[..., :self.exp.get_from_config('input_channels')]
            label = label[..., :self.exp.get_from_config('output_channels')]

        return (id, img, label)
