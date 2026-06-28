#!/bin/bash
PROJ=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench
# 找一个有 pandas 的 python
PY=/root/miniconda3/envs/improve/bin/python
[ -x "$PY" ] || PY=/root/miniconda3/bin/python
MODE="${1:-smoke}"
cd $PROJ
if [ "$MODE" = "smoke" ]; then
  sudo $PY scripts/phaseB/run_netmhcpan_ba_101102.py --smoke 2 2>&1 | tail -16
else
  sudo $PY scripts/phaseB/run_netmhcpan_ba_101102.py 2>&1 | tail -14
fi
