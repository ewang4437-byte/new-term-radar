# 本地规则（这个 fork 专用）

这个仓库公开在 GitHub 上。**密钥和个人数据只留在本机，永远不提交、不推送。**

只在本机、不进 git 的东西：
- `.env`：所有 API key（AIsa、GoAnyAPI、TrustMRR、YouTube、AnyAPI……）
- `config.json`、`config-vn.json`、`server.json`：个人配置（自己的网站、关注的账号、站点地图）
- `state/`、`state-vn/`、`logs/`、`gsc_*.json`：运行记录、余额、Search Console 授权
- `report-*`、`traffic-*`、`keywords-*.txt`、`kw-*.txt`：每天的报告和词表

保护措施：
1. `.gitignore` 列出了上面这些文件。
2. `scripts/git-hooks/` 里的 pre-commit / pre-push 钩子：暂存或推送里出现这些文件，或者出现像 key 的字符串（`sk-…`、`AIza…`、`ghp_…`、`XXX_API_KEY=…`），就拒绝提交/推送。
   新克隆后运行一次：`sh scripts/git-hooks/install.sh`
3. 新配置项只写进 `config.example.json`（不含真实值），真实值写进本机的 `config.json`。

分支：`radar-mine` = 上游 + 本地改动（每天跑的就是它）；`local-2026-11-11` = 旧版备份。
同步上游：`git fetch upstream && git merge upstream/main`，合并后先跑 `PYTHONUTF8=1 python -m pytest -q`。
