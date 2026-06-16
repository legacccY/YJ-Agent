# HOWTO：GitHub 日常协同备忘

> 个人速查。最后更新：2026-06-16。配套计划见 `~/.claude/plans/github-lexical-kurzweil.md`。

## 0. 仓库地图（别搞混）

| 仓库 | 可见性 | 干什么 | 本地路径 |
|---|---|---|---|
| `legacccY/YJ-Agent` | 🔒 **private** | LifeOS + 未发表论文（绝不公开，护双盲） | `D:\YJ-Agent` |
| `legacccy/legacccy.github.io` | 🌐 public | 学术个人主页（只放脱敏内容） | `D:\sites\legacccy.github.io` |

**红线**：未发表论文的方法名/数据集/数字/结果，永远只待在 private 仓，不进任何公开仓。

---

## 1. gh CLI（已装 v2.94.0）

首次要登录一次（浏览器授权）：

```powershell
gh auth login          # 选 GitHub.com → HTTPS → Login with a web browser，照提示贴 code
gh auth status         # 看到 "Logged in to github.com as legacccy" 即成功
```

登录后 gh 能直接管仓库 / PR，不用每次开网页。

---

## 2. 日常改东西的标准流（branch → PR → merge）

**为什么不直接在 main 上改**：main 是「干净的成品线」。在分支上改，做错了随时丢掉分支，不污染主线；将来加合作者也是一人一分支互不踩。

```powershell
# ① 从最新 main 开一条工作分支
git switch main
git pull                          # 先拉最新，避免落后
git switch -c feat/写啥就叫啥      # 例：feat/homepage、fix/typo

# ② 改文件……改完看一眼动了啥
git status
git add -A
git commit -m "说清楚改了什么"

# ③ 推到远程 + 开 PR
git push -u origin feat/写啥就叫啥
gh pr create --fill               # 自动用 commit 信息填 PR 标题/正文

# ④ 合并（自己审完）并删掉分支
gh pr merge --squash --delete-branch
git switch main && git pull       # 回到 main 拉下刚合并的
```

> 一个人也建议走这套：养成习惯，且 PR 页能完整看到 diff，比直接 push 安全。
> 嫌麻烦的小改也可直接在 main 上 commit + push，但重要改动走 PR。

---

## 3. 常见卡点

**push 被拒（rejected / behind）**：远程比本地新，先拉再推
```powershell
git pull --rebase                 # 把你的提交叠到远程最新之上
# 若有冲突：编辑器里改掉 <<<<<<< ======= >>>>>>> 标记的冲突段，然后
git add <冲突文件> && git rebase --continue
git push
```

**改错想撤**：
```powershell
git restore <文件>                # 丢掉某文件未提交的改动
git switch - && git branch -D 分支名   # 整条分支不要了
```

**看历史 / 当前状态**：
```powershell
git status          # 现在动了哪些文件
git log --oneline -10   # 近 10 条提交
gh pr list          # 有哪些待处理 PR
```

---

## 4. 将来加导师/合作者

```powershell
gh repo add-collaborator <仓库> <对方用户名>
# 或网页：仓库 Settings → Collaborators → Add people
```

⚠️ **开权限前先想清楚**：该仓有没有未发表 / 双盲敏感内容。YJ-Agent 整仓不要随便加人；要共享某篇论文，单独建一个只含该论文脱敏材料的仓再加。
