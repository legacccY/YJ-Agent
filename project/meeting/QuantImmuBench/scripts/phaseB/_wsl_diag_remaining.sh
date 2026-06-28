#!/bin/bash
echo "=== TSCAPE env ==="
ls /root/miniconda3/envs/tscape >/dev/null 2>&1 && echo "tscape env 在" || echo "无"
find /root /home -iname 'inference_csv.py' 2>/dev/null | head -2
echo "=== PRIME.x 二进制能跑? ==="
PD=/root/quantimmu/tools_repos/PRIME
ls $PD/PRIME 2>/dev/null && echo "PRIME 二进制在" || echo "无 PRIME 二进制"
ls $PD/lib/*.x 2>/dev/null | head -2
echo "=== MixMHCpred 二进制 ==="
ls /root/quantimmu/tools_repos/MixMHCpred/MixMHCpred 2>/dev/null && echo "MixMHCpred 在" || echo "无"
echo "=== ImmuneApp 任意位置 ==="
find /root /home -iname '*immuneapp*' -maxdepth 5 2>/dev/null | head -3 || echo "ImmuneApp 没找到"
echo "=== HLAthena docker 镜像 ==="
docker images 2>/dev/null | grep -i hlathena || echo "无 hlathena 镜像"
echo "=== netMHCpan 二进制(本地有没有) ==="
find /root /home -iname 'netMHCpan' -type f 2>/dev/null | head -2 || echo "本地无 netMHCpan"
echo "=== IMPROVE env improve ==="
ls /root/miniconda3/envs/improve >/dev/null 2>&1 && echo "improve env 在" || echo "无"
