# HLAthena 部署 NOTES

---

## ⚠️⚠️ 重要：HLAthena 仅作 PRESENTATION PROXY BASELINE

**HLAthena 预测 MHC-I 提呈（presentation），不预测免疫原性。**

论文原文（Sarkizova et al. 2020 Nat Biotech）明确：
> "We did not model whether HLA-presented peptides can engage the T cell receptor,
>  as this problem remains unsolved."

独立 benchmark 实测：ELISpot AUC **~0.6**，PPV **0.3063**（近随机水平）。

**进 QuantImmuBench 的定位**：
- 只能作为 "MHC-I presentation → immunogenicity" 假设的 proxy baseline 对比
- 绝不与 PRIME / deepHLApan / ImmuneApp / DeepImmuno 等免疫原性工具在同一列
- 图表/结果表里需明确标注 `HLAthena (presentation proxy, not immunogenicity)`
- 预期 AUC 低于所有真正免疫原性工具，这不是部署问题而是任务定义不同

---

## 部署路线（决策 + 理由）

### 主路：WSL2 docker pull → docker save → SCP → singularity build

**理由**：
- HPC 无 docker，且 Docker Hub 出网不通（HPC 防火墙）
- HPC 有 Singularity 3.11.3，可读 docker-archive
- WSL2 本机有 docker daemon（Docker Desktop），代理可通 Docker Hub
- 镜像 `ssarkizova/hlathena-external:dev`（~909MB），可接受一次性传输

**命令序列见** `build_hlathena_sif.sh`（分 A/B/C/D 四阶段注释清楚）。

### 备选：web server 手动跑小批

如 docker save 镜像 + SCP + singularity build 整链出问题（如 HPC 磁盘不足、网络阻断），改用：
1. 访问 http://hlathena.tools （免费 web server，上限 10000 肽/批）
2. 手动上传 TSV，下载输出 TSV
3. 截图记录参数界面 + 输出列
4. 将结果文件存 `scripts/out/hlathena_webserver_smoke.tsv`

**备选触发条件**：
- SIF 构建失败（singularity build 报错无法解决）
- HPC /gpfs 磁盘不足（SIF ~600-900MB + 存档 ~909MB = ~1.8GB 额外占用）
- 镜像再分发合规问题（见"风险"节）

---

## 部署步骤（主路线总结）

### 前提检查
- [ ] WSL2 docker daemon 运行中：`docker info`
- [ ] Docker Hub 可访问（走代理）：`docker pull hello-world`
- [ ] HPC 登录节点可达：`ssh jiayu2403@dtn.hpc.xjtlu.edu.cn`
- [ ] HPC /gpfs 剩余空间 ≥ 3GB：`df -h /gpfs/work/bio/jiayu2403/`

### 步骤
1. **本机 WSL2** 运行 `build_hlathena_sif.sh`（阶段 A+B+C 全包）
   - A: docker pull + docker save (~909MB tar)
   - B: SCP 传 HPC（⚠️ 主线拍板确认后执行上传）
   - C: HPC singularity build（~5-15 分钟）
   - D: singularity inspect 验证

2. **HPC 登录节点** 运行 `smoke_hlathena.sh`
   - 自动 inspect entrypoint（确认真实命令行参数）
   - 跑 8 条 8-11mer 测试肽，输出 MSi 分
   - QC 检查 MSi 列存在 + 数值合理

3. 烟测通过后回填 `TOOLS/HLAthena.md`（实测输入/输出样例、真实命令行）

---

## 风险与 TODO

### TODO（运行前必须解决）

**[TODO-1] HLA 格式字符串** — 优先级: 🔴 高
- 当前 `smoke_hlathena.sh` 占位 `"HLA-A*02:01"`（netMHCpan 标准格式）
- 实际 Docker 内部期待格式未确认
- **查法**: 访问 hlathena.tools → Predict → "How to use" 看 HLA allele 字段说明
- 常见变体: `HLA-A*02:01` / `HLA-A0201` / `A*02:01` / `A0201`
- 格式错误后果: singularity run 报 "unknown allele" 或输出全 NaN

**[TODO-2] Docker 命令行参数** — 优先级: 🔴 高
- `smoke_hlathena.sh` 步骤 4 用的 `--input_file / --output_file / --model MSi` 是推断占位
- **查法（步骤 3 自动跑）**:
  ```
  singularity inspect --runscript hlathena.sif
  singularity exec hlathena.sif python /run_hlathena.py --help
  ```
- 若入口不是 `/run_hlathena.py`，步骤 3 的 `ls /` 输出会显示实际脚本名

**[TODO-3] MSi 阈值** — 优先级: 🟡 中
- 已知参考：MSiC ≥0.95 (strong) / ≥0.90 (normal) / ≥0.80 (weak)
- 需在 hlathena.tools 文档或论文 Supplementary 确认是否适用 MSi（非 MSiC）
- **查法**: hlathena.tools → Documentation 或 Sarkizova 2020 Supp Table

**[TODO-4] MSiC/MSiCE 烟测** — 优先级: 🟢 低（MSi 主路通后再做）
- MSiC 需额外列 `ctex_up` / `ctex_dn`（上下游 30aa）
- MSiCE 需 RNA 表达量（TPM）
- benchmark 若只跑 MSi，MSiC/MSiCE 可选做

### 风险

**[风险-1] 镜像 6 年未更新**
- `ssarkizova/hlathena-external:dev` 最后更新 ~2018-2019
- Python/依赖版本非常旧，容器化隔离是唯一可行部署方式
- 在 Singularity 3.11.3 下兼容性未经测试 → 可能遇到 glibc/lib 问题
- 缓解：singularity inspect 后用 exec 最小验证

**[风险-2] 镜像再分发合规**
- Docker Hub 页面无显式 license（research purposes only）
- 将 Docker 镜像转 Singularity SIF 并存在 HPC 属于研究内部使用
- 论文 benchmark 引用数字前建议联系 Broad Institute / Sarkizova 确认
- 不向第三方发布 SIF 或 benchmark 原始数字

**[风险-3] HPC 磁盘占用**
- docker-archive tar: ~909MB（传后可删）
- hlathena.sif: ~600-900MB（Singularity 压缩后）
- 确认 /gpfs 剩余空间后再启传输；传完后删 tar 释放：
  ```
  rm /gpfs/work/bio/jiayu2403/quantimmu/sif/hlathena-external.tar
  ```

**[风险-4] 无公开 GitHub，无法查源码**
- 仅有论文 Supplementary Code + Docker 镜像
- 出 bug 无法对照源码 debug，只能靠 Docker logs + inspect

---

## 实测后回填（主线跑 smoke 后更新）

> 烟测通过后由主线填写，然后同步到 TOOLS/HLAthena.md

- 实测命令: `TODO`
- 实测 HLA 格式: `TODO`
- 实测输入样例 (前 3 行): `TODO`
- 实测输出列: `TODO`
- 实测 MSi 分数范围: `TODO`
- singularity inspect runscript 输出: `TODO`
- 阈值确认: `TODO`
- 烟测 job_id / 路径: `TODO`
- 状态更新: `TODO` → 更新 DEPLOY_TRACKER.md 第二批表

---

## 参考

- 论文: Sarkizova et al. 2020 Nat Biotech 38:199-209, DOI 10.1038/s41587-019-0322-9
- Docker: `ssarkizova/hlathena-external:dev` (~909MB)
- Web server: http://hlathena.tools (10000 肽/批上限)
- HPC SIF 路径 (建后): `/gpfs/work/bio/jiayu2403/quantimmu/sif/hlathena.sif`
- 本地 WSL2 存档: `~/quantimmu/docker_archives/hlathena-external.tar`
