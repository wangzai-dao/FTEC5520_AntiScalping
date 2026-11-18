# Steps to Push to GitHub

> This directory is already in a "ready to commit" state: `.gitignore` already excludes `.env`, `blockchain/miner.key`,
> `tools/`, `contracts/bin/`, `contracts/lib/`, `.venv/`, and the chain data and logs.

## 1. Create an Empty Repository on GitHub First

Open https://github.com/new in a browser, enter a name (for example `FTEC5520_AntiScalping`),
and **do not** check "Add a README" / ".gitignore" / "license"; create an empty repository.

## 2. Initialize Locally and Push

```bash
cd FTEC5520_AntiScalping

git init
git add .
git status                 # ← confirm the list contains no .env / miner.key / .venv / tools
git commit -m "FTEC5520 anti-scalping ticketing: private chain + Web3.py API + Streamlit app"

git branch -M main
git remote add origin https://github.com/<your-username>/FTEC5520_AntiScalping.git
git push -u origin main
```

If you are prompted to log in, use a GitHub **Personal Access Token** (Settings → Developer settings →
Personal access tokens → Tokens (classic) → `repo` scope) as the password, not your account password.

## 3. 30-Second Self-Check Before Pushing

```bash
git ls-files | grep -E "\.env$|miner\.key|password\.txt|\.venv/" && echo "❌ sensitive files present, remove them first" || echo "✅ clean"
```

If sensitive files were added by mistake:

```bash
git rm --cached .env
git commit -m "remove secrets"
```

> A private key that has already been pushed must be treated as leaked: in this project these are only keys for a local test chain,
> but it is still recommended to regenerate a new set with `python blockchain/init_chain.py --force`.

## 4. How Teammates Run It After Cloning

```bash
git clone https://github.com/<your-username>/FTEC5520_AntiScalping.git
cd FTEC5520_AntiScalping
./scripts/bootstrap.sh                 # create venv, download Geth/OZ, init the chain, deploy, seed data
.venv/bin/streamlit run app/app.py
```

## 5. Repository Size

The current committed content is about 3 MB (mainly the 6 PNG files in `results/screenshots/`).
GitHub's per-file limit is 100 MB, so Git LFS is not required.
