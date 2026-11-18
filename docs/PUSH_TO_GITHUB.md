# 推到 GitHub 的步骤

> 本目录已经是"可直接提交"的状态：`.gitignore` 已排除 `.env`、`blockchain/miner.key`、
> `tools/`、`contracts/bin/`、`contracts/lib/`、`.venv/`、链数据与日志。

## 1. 在 GitHub 上先建一个空仓库

浏览器打开 https://github.com/new ，填名字（例如 `FTEC5520_AntiScalping`），
**不要**勾选 "Add a README" / ".gitignore" / "license"，建一个空仓库。

## 2. 本地初始化并推送

```bash
cd FTEC5520_AntiScalping

git init
git add .
git status                 # ← 确认列表里没有 .env / miner.key / .venv / tools
git commit -m "FTEC5520 anti-scalping ticketing: private chain + Web3.py API + Streamlit app"

git branch -M main
git remote add origin https://github.com/<你的用户名>/FTEC5520_AntiScalping.git
git push -u origin main
```

如果提示要登录，用 GitHub 的 **Personal Access Token**（Settings → Developer settings →
Personal access tokens → Tokens (classic) → `repo` 权限）当密码，不要用账号密码。

## 3. 推送前的 30 秒自查

```bash
git ls-files | grep -E "\.env$|miner\.key|password\.txt|\.venv/" && echo "❌ 有敏感文件，先移除" || echo "✅ 干净"
```

如果误加了敏感文件：

```bash
git rm --cached .env
git commit -m "remove secrets"
```

> 已经被推上去过的私钥要视为泄露：本项目里这些只是本地测试链的钥匙，
> 但仍然建议 `python blockchain/init_chain.py --force` 重新生成一套。

## 4. 队友克隆后怎么跑

```bash
git clone https://github.com/<你的用户名>/FTEC5520_AntiScalping.git
cd FTEC5520_AntiScalping
./scripts/bootstrap.sh                 # 建 venv、下 Geth/OZ、建链、部署、造数据
.venv/bin/streamlit run app/app.py
```

## 5. 仓库大小

当前提交内容约 3 MB（主要是 `results/screenshots/` 的 6 张 PNG）。
GitHub 单文件上限 100 MB，无需 Git LFS。
