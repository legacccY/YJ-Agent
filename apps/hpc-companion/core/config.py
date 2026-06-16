"""应用级路径、常量与内置集群预设。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "HPC Companion"
APP_VERSION = "0.1.0"
ORG = "YJ-Agent"

# keyring 服务名（密码加密存于系统凭据库）
KEYRING_SERVICE = "hpc-companion"


def app_data_dir() -> Path:
    """跨平台用户配置目录。Windows: %APPDATA%\\HPC Companion。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def profiles_path() -> Path:
    return app_data_dir() / "profiles.json"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def load_settings() -> dict:
    import json
    p = settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_settings(data: dict) -> None:
    import json
    settings_path().write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resource_path(rel: str) -> Path:
    """打包(PyInstaller)后资源定位。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent.parent / rel


# 内置预设：用户新建连接时可一键套用，凭证仍需自己填。
CLUSTER_PRESETS = {
    "XJTLU HPC (gpu4090)": {
        "host": "dtn.hpc.xjtlu.edu.cn",
        "port": 22,
        "username": "",
        "slurm_account": "shuihuawang",
        "partition": "gpu4090",
        "qos": "4gpus",
        "default_remote_dir": "/gpfs/work/bio/",
        "vpn_note": "校外必须先连 XJTLU VPN 才能访问该主机。",
        "python_path": "",
    },
    "自定义 / 通用 SLURM 集群": {
        "host": "",
        "port": 22,
        "username": "",
        "slurm_account": "",
        "partition": "",
        "qos": "",
        "default_remote_dir": "",
        "vpn_note": "",
        "python_path": "",
    },
}
