"""
baselines/__init__.py — gdn2vessel baseline harness 包入口。

导入此包时自动：
  1. 暴露 BaselineAdapter ABC。
  2. 暴露 registry 工厂函数（register / get_adapter / list_adapters）。
  3. 调用 auto_discover 自动 import adapters/ 下所有 adapter 模块，
     触发 @register 装饰器完成注册。
     （失败的 adapter 只 warn 不崩，保证 mamba 未装时其他 adapter 仍可用）
"""

from .base_adapter import (
    BaselineAdapter,
    KIND_ARCHITECTURE,
    KIND_LOSS,
    ENV_MAIN,
    ENV_MAMBA,
)
from .registry import (
    MODEL_REGISTRY,
    auto_discover,
    get_adapter,
    list_adapters,
    register,
)

# 自动扫描并注册 adapters/ 下所有 adapter
auto_discover()

__all__ = [
    "BaselineAdapter",
    "KIND_ARCHITECTURE",
    "KIND_LOSS",
    "ENV_MAIN",
    "ENV_MAMBA",
    "MODEL_REGISTRY",
    "register",
    "get_adapter",
    "list_adapters",
    "auto_discover",
]
