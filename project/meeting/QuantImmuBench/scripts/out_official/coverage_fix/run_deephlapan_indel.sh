#!/usr/bin/env bash
# deepHLApan indel 补跑 (context-free 单肽, MT-only). 在 WSL 内跑, 挂 /data 绕 Docker Desktop 路径转换.
set -e
B=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_official/coverage_fix
OUT="$B/deephlapan_out_INDEL"
mkdir -p "$OUT"
echo "[check] 容器内可见输入:"
docker run --rm -v "$B":/data biopharm/deephlapan:v1.1 ls -la /data/deephlapan_input_INDEL.csv
echo "[run] deephlapan context-free..."
docker run --rm -v "$B":/data biopharm/deephlapan:v1.1 \
    deephlapan -F /data/deephlapan_input_INDEL.csv -O /data/deephlapan_out_INDEL/
echo "[exit] $?"
echo "[out] 产出:"
ls -la "$OUT/"
