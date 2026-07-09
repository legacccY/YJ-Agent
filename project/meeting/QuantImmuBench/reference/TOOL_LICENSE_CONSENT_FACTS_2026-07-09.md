# 工具许可 / 书面同意 事实核查 + NeoaPred 缺席脚注（给老师 §8⑤⑥ + 报告脚注）

> researcher 2026-07-09 联网查证 + 主线 Bash 核出处。服务老师 §8⑥「请提供更多信息，这个要求非常奇怪」+ NeoaPred 新切缺席脚注。条款引原文 + URL，未取干净快照的标 TODO。

## NeoaPred 新切缺席脚注（可直接入报告）
新切重跑工具数 30→**29**：NeoaPred 于 **2026-07-07 由用户拍板从工具集移除**（唯一结构-物理呈递工具、跑最慢、GPU 曾 HPC TIMEOUT，旧版仅在严格 9mer 得 244 个有效值），rerun 不再产出其结果；旧产物留存 `out_official/` 仅供参考、不进重跑收口。
出处：`TOOL_RERUN_STATUS.md:40`（Bash 核实）。

## ⑥ 书面同意要求 —— 事实核查

**报告那句话的来源**：项目自建 PPT 注记（读 DTU 许可后**自设的合规红线**，非外部强加）→ `ppt/gen_ppt_5tools.js:619`；验收档 G8 → `02_ACCEPTANCE.md:28,184-189`（Bash 核实：DTU 工具数字 pending consent = 投稿前拍板点；**`netmhcpan_ba` 是 G1/G4 关键工具，consent 不到位其 headline 数字须撤/替**）。

**逐工具**（条款原文 + URL）：
| 工具 | 许可 | 发表相关条款 | 用其分数发 benchmark 是否真需书面同意 |
|---|---|---|---|
| netMHCpan BA/EL、NetMHCstabpan、NetTepi、ICERFIRE | DTU Health Tech 学术许可（非商业/单机构） | 条款 (v):「publish any results of benchmark tests run on the Product to a third party without HEALTH's prior written consent」；「agree to not give the program to third parties」；「…commercialization is not allowed」 — URL: https://services.healthtech.dtu.dk/cgi-bin/sw_request?software=netMHCpan&version=4.1 | **是**，但仅限"benchmark 测试结果"这一类；单纯用工具发论文 + 引用是允许的（DTU 官网主动给引用格式） |
| andy90 / Seq2Neo / pTuneos / IMPROVE | 各异（Seq2Neo=AFL-3.0 等），但内部调用 DTU 二进制 | 继承 DTU benchmark 条款 | 间接受限：benchmark 呈现其分数=呈现 DTU 结果 → 同落 (v) |
| TSCAPE | CC BY-NC-ND 4.0 | 署名 + 非商业 + 禁演绎；对"发表结果"无限制 | **否**（引用即可）。⚠️**与项目档冲突**：`02_ACCEPTANCE.md:189` 把 TSCAPE 列为 DTU pending，researcher 查为 CC BY-NC-ND — **存疑，投稿前厘清** |
| DeepNetBim | 无明示 license | 记「发表前邮件 Li-Lab-SJTU」 | 需先邮件确认 |
| BigMHC / Repitope(MIT) / MHCflurry / DeepImmuno / PRIME 等 | 开源宽松 / 学术非商用 | 无发表限制 | 否 |

**给老师的中文客观小结（可直接转述）**：
> 关于"个别工具需发布方书面同意才能发表结果"：核查后，这一要求只针对 DTU Health Tech 的几个工具（netMHCpan BA/EL、NetMHCstabpan、NetTepi、ICERFIRE，及内部调用它们的 andy90/Seq2Neo/pTuneos/IMPROVE），来源是 DTU 学术许可里一条 benchmark 条款，大意为"未经 DTU 事先书面同意，不得向第三方发布在其软件上跑出的 benchmark 测试结果"。需澄清两点：① 用这些工具跑结果、论文里引用发表本身完全允许——DTU 官网甚至主动给"发表结果时请引用以下文献"的格式；真正受限的只是"系统性 benchmark 对比/排名"这一特定情形，而我们这篇恰是 benchmark 对比论文，才触发。② 这类"benchmark 结果需事先书面同意"条款在软件业界很常见（称 DeWitt 条款，Oracle/Google/微软都有，https://cube.dev/blog/dewitt-clause-or-can-you-benchmark-a-database ），并非 DTU 独有的怪规定。实务处理简单：投稿前给 DTU 发一封邮件取书面同意即可。其余非 DTU 工具均无发表限制。

**TODO（诚实）**：DTU 许可协议**逐字原始快照未取到**（正文藏在需勾选同意的交互下载页后）；条款枚举号 (v) 经两次独立读取一致、置信中高，但建议正式取同意时走一次学术下载 / 邮件 health-software@dtu.dk 拿全文逐字核对。TSCAPE 许可归属（DTU vs CC BY-NC-ND）存疑待厘清。
