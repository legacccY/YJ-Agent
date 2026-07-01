# tidy

产物清洁工编排。派 `custodian` agent 扫散落物 → 产 pointer-aware 归档清单 → 主线串行执行可逆 move（Filesystem MCP）。管的是**文件产物整洁**，不碰论文内容/数字/实验逻辑（那些是 KEEP）。删除永远停下报拍板。

## 触发场景
用户说「整理一下产物」「太乱了扫一遍」「归档旧文件」「收工清扫」「/tidy」；或 Stop hook `custodian_sweep_reminder.js` 检测散落超阈值时提示。

## 三 mode

### `/tidy scan [zone]` — 只扫不动
1. 确定 zone（不给则默认 `root`；可 `all` 按 zone 并行扇出多个 custodian）。zone 列表：`root` / `_scratch` / `tools` / `meeting-root` / `git-ignore` / `<project-key>`。
2. 派 `custodian` agent（每 zone 一个，独立可并行）：冷启动给 zone 范围 + pointer-check 索引清单（registry / CLAUDE.md / PORTFOLIO / MEMORY / 项目 README/LOG）。
3. 主线汇总各 zone manifest → 报用户：可归档 N / 待删 J（拍板）/ KEEP K / DUP 提议。**只报不动。**

### `/tidy sweep <zone>` — 执行归档（需先 scan + 用户批准）
1. 对已批准 manifest 的 `ARCHIVE`/`SCRATCH` 项：**主线串行**用 `mcp__filesystem__move_file` 移到 `_archive/<YYYY-MM-DD>/<zone>/`（先 `date` 确认日期，`mcp__filesystem__create_directory` 建目标）。可逆。
2. `JUNK`/删除项：**不删**，列清单停下报用户拍板（CLAUDE.md 危险删除）。
3. 移动**逐个串行**，不与其他工具并批（CLAUDE.md 工具纪律：Filesystem MCP move，禁 rm，禁 PowerShell-via-Bash，防级联取消）。
4. 移完写 hygiene ledger：每条 append 一行到 `.portfolio/hygiene.jsonl`（`{ts,action:"archive",zone,from,to}`）。
5. **移后即验读档链**：抽查 registry/CLAUDE.md 读档链路径仍解析（没误移断链）。

### `/tidy gitignore` — 修 ignore 漂移
1. custodian 的 IGNORE-DRIFT 清单：`git rm --cached <files>`（**保留工作树**，只脱管）。
2. 补 `.gitignore` 模式（`_scratch/`、`_scratch_*.py`、`tmp_*.py`、`**/_scratch/`、`.trash_*` 等）。
3. `git status` 确认只剩预期改动，不误删工作树文件。

## 注意事项
- **pointer-aware 是命门**：custodian 动任何文件前先 grep 读档链，被引用的一律 KEEP。断链是本任务最大风险（用户明确关切）。
- **归档不删**：默认全部 move 到 `_archive/`（可逆）；删除全押后拍板。11GB `_scratch/` 数据 blob、`.trash_quantimmu/` 等大件删除单独报。
- **DUP 合并不自动做**：重复 tracker 合并涉及内容保真（写作任务），custodian 只提议，主线拍板后另派 writer，本命令不改内容。
- Filesystem MCP 高风险调用串行、不并批；改完不重复读回验证（Write/Edit 失败会直接报错）。
- 收工时 `.portfolio/hygiene.jsonl` 非空 = 本轮有清扫，git commit 摘要带一笔。
