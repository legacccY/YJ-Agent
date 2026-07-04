#!/usr/bin/env bash
set -e
B=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_official/coverage_fix
mkdir -p "$B/deephlapan_out_SNV110"
docker run --rm -v "$B":/data biopharm/deephlapan:v1.1 \
    deephlapan -F /data/deephlapan_input_SNV110.csv -O /data/deephlapan_out_SNV110/
ls -la "$B/deephlapan_out_SNV110/"
