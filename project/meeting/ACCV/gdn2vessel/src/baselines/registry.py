"""
registry.py — Baseline adapter registry for gdn2vessel harness.

使用方式：
    # 注册（在各 adapter 文件顶层执行）
    from baselines.registry import register

    @register
    class FRUNetAdapter(BaselineAdapter):
        name = 'fr_unet'
        ...

    # 使用
    from baselines.registry import get_adapter
    adapter = get_adapter('fr_unet')
    model = adapter.build_model(cfg)

设计要点：
  - dict 真源 MODEL_REGISTRY，key = adapter.name（str），value = adapter class。
  - register 装饰器自动调 validate_attrs()，注册时报错而非运行时才崩。
  - 支持 list_adapters() 供 CLI 打印已注册的全部 adapter 名。
  - Windows 安全：无 multiprocessing；无 scipy.stats。
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Dict, List, Type

from .base_adapter import BaselineAdapter


# --------------------------------------------------------------------------- #
#  Global registry
# --------------------------------------------------------------------------- #

MODEL_REGISTRY: Dict[str, Type[BaselineAdapter]] = {}
"""
key  : adapter.name (str)，例如 'ours_gdn2', 'backbone_unet', 'fr_unet', ...
value: BaselineAdapter 子类（未实例化的 class）
"""


# --------------------------------------------------------------------------- #
#  register decorator
# --------------------------------------------------------------------------- #

def register(cls: Type[BaselineAdapter]) -> Type[BaselineAdapter]:
    """
    Class decorator：将 BaselineAdapter 子类注册进 MODEL_REGISTRY。

    使用方式::

        @register
        class MyAdapter(BaselineAdapter):
            name = 'my_baseline'
            ...

    注册时会调用 cls().validate_attrs() 检查必填属性。
    若 name 已存在且指向不同 class，抛 ValueError（防覆写）。

    Args:
        cls: BaselineAdapter 子类（未实例化）。

    Returns:
        cls（原样返回，方便 decorator 链）。

    Raises:
        TypeError:  cls 不是 BaselineAdapter 子类。
        ValueError: name 为空、属性校验失败或 name 重复注册。
    """
    if not (isinstance(cls, type) and issubclass(cls, BaselineAdapter)):
        raise TypeError(
            f"@register expects a BaselineAdapter subclass, got {cls!r}"
        )

    # 实例化一次用于属性校验（不保留实例，只检查）
    instance = cls.__new__(cls)
    # 手动初始化类属性（不调 __init__ 避免副作用）
    instance.validate_attrs()  # 已在 base_adapter 定义

    name = cls.name
    if name in MODEL_REGISTRY and MODEL_REGISTRY[name] is not cls:
        raise ValueError(
            f"Adapter name {name!r} is already registered by "
            f"{MODEL_REGISTRY[name].__name__}. Cannot overwrite with {cls.__name__}."
        )

    MODEL_REGISTRY[name] = cls
    return cls


# --------------------------------------------------------------------------- #
#  get_adapter factory
# --------------------------------------------------------------------------- #

def get_adapter(name: str) -> BaselineAdapter:
    """
    通过 name 取 adapter **实例**（每次调用都 new 一个，adapter 无状态）。

    Args:
        name: adapter.name 字符串，例如 'ours_gdn2'。

    Returns:
        BaselineAdapter 子类的新实例。

    Raises:
        KeyError: name 未注册，附带已注册名列表方便诊断。
    """
    if name not in MODEL_REGISTRY:
        registered = sorted(MODEL_REGISTRY.keys())
        raise KeyError(
            f"Adapter {name!r} not found in MODEL_REGISTRY.\n"
            f"Registered adapters: {registered}\n"
            "Make sure the adapter module has been imported "
            "(e.g., via baselines/__init__.py or explicit import)."
        )
    return MODEL_REGISTRY[name]()


# --------------------------------------------------------------------------- #
#  list_adapters
# --------------------------------------------------------------------------- #

def list_adapters() -> List[str]:
    """
    返回已注册 adapter 的 name 列表（排序）。
    CLI 用::

        python -c "from baselines.registry import list_adapters; print(list_adapters())"
    """
    return sorted(MODEL_REGISTRY.keys())


# --------------------------------------------------------------------------- #
#  auto_discover: 扫描 adapters/ 子目录并 import 所有 .py
# --------------------------------------------------------------------------- #

def auto_discover(adapters_dir: str | Path | None = None) -> None:
    """
    自动 import adapters/ 目录下所有 Python 模块，触发 @register 装饰器。
    在 __init__.py 或 evaluate.py 的顶部调用一次即可。

    Args:
        adapters_dir: adapters 目录路径，默认为 baselines/adapters/（相对当前文件）。
    """
    if adapters_dir is None:
        adapters_dir = Path(__file__).parent / "adapters"
    else:
        adapters_dir = Path(adapters_dir)

    if not adapters_dir.exists():
        return  # 目录不存在时静默跳过（CI 空目录场景）

    for py_file in sorted(adapters_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue  # 跳过 __init__.py 等
        module_name = f"baselines.adapters.{py_file.stem}"
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            # 部分 adapter 有可选依赖（mamba 等）；import 失败时警告不崩溃
            import warnings
            warnings.warn(
                f"[registry] Could not import {module_name}: {e}. "
                "This adapter will not be registered.",
                ImportWarning,
                stacklevel=2,
            )
