"""Compile ConcertTicket.sol / Helper.sol with solc 0.8.20 (Standard JSON).

成员 2、3 交付的合约使用 Remix 风格 import:
    import "@openzeppelin/contracts@5.0.2/token/ERC721/ERC721.sol";
solc 不认识 "@5.0.2" 这个后缀，因此这里用 remapping 把它映射到
contracts/lib/@openzeppelin/contracts/（由 backend/fetch_deps.py 下载）。

输出:
    contracts/build/ConcertTicket.json  { abi, bytecode, deployedBytecode, ... }
    contracts/build/Helper.json
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
BUILD = CONTRACTS / "build"
BIN = CONTRACTS / "bin"
SOLC_VERSION = "0.8.20"
EVM_VERSION = "paris"  # 不用 PUSH0，保证在伦敦规则的老私有链上也能跑

SOLC_HOST_MAP = {
    ("Darwin", "x86_64"): "macosx-amd64",
    ("Darwin", "arm64"): "macosx-amd64",  # 通过 Rosetta 运行 x86_64 版本
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "aarch64"): "linux-aarch64",
}


# binaries.soliditylang.org 前面挂着 Cloudflare，会把 Python-urllib 的默认 UA
# 当爬虫拦成 403 Forbidden，因此下载时必须自带一个普通 UA。
SOLC_UA = "Mozilla/5.0 (X11; Linux x86_64) ftec5520-build/1.0"


def _urlopen(url: str, timeout: int):
    """带 User-Agent 的 urlopen（裸 urlopen 会被 403）。"""
    request = urllib.request.Request(url, headers={"User-Agent": SOLC_UA})
    return urllib.request.urlopen(request, timeout=timeout)


def solc_path() -> Path:
    """返回本地 solc 二进制路径，不存在则从 binaries.soliditylang.org 下载。"""
    local = BIN / "solc"
    if local.exists():
        return local

    host = SOLC_HOST_MAP.get((platform.system(), platform.machine()))
    if host is None:
        sys.exit(f"没有为 {platform.system()}/{platform.machine()} 准备 solc 下载地址")

    BIN.mkdir(parents=True, exist_ok=True)
    base = f"https://binaries.soliditylang.org/{host}"
    with _urlopen(f"{base}/list.json", 30) as r:
        listing = json.load(r)
    key = next((k for k in listing["releases"] if k == SOLC_VERSION or k.startswith(SOLC_VERSION + "+")), None)
    if key is None:
        sys.exit(f"list.json 里找不到 solc {SOLC_VERSION} 的构建")
    url = f"{base}/{listing['releases'][key]}"
    print(f"[compile] 下载 solc {key}: {url}")
    with _urlopen(url, 180) as r, open(local, "wb") as f:
        shutil.copyfileobj(r, f)
    local.chmod(0o755)
    return local


def build_standard_json() -> dict:
    oz = CONTRACTS / "lib" / "@openzeppelin" / "contracts"
    if not (oz / "token" / "ERC721" / "ERC721.sol").exists():
        sys.exit("缺少 OpenZeppelin 依赖，请先运行: python backend/fetch_deps.py")

    sources = {
        "contracts/ConcertTicket.sol": {"content": (CONTRACTS / "ConcertTicket.sol").read_text("utf-8")},
        "contracts/Helper.sol": {"content": (CONTRACTS / "Helper.sol").read_text("utf-8")},
    }
    return {
        "language": "Solidity",
        "sources": sources,
        "settings": {
            # 相对 base-path 的 remapping，--standard-json 下绝对路径不可用
            "remappings": ["@openzeppelin/contracts@5.0.2/=contracts/lib/@openzeppelin/contracts/"],
            "optimizer": {"enabled": True, "runs": 200},
            "evmVersion": EVM_VERSION,
            "outputSelection": {
                "*": {
                    "*": [
                        "abi",
                        "evm.bytecode.object",
                        "evm.deployedBytecode.object",
                        "metadata",
                    ]
                }
            },
        },
    }


def compile_contracts() -> dict:
    """编译并返回 {合约名: artifact}，同时写入 contracts/build/*.json。"""
    solc = solc_path()
    payload = build_standard_json()
    proc = subprocess.run(
        [str(solc), "--standard-json", "--base-path", str(ROOT), "--allow-paths", str(ROOT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"solc 退出码 {proc.returncode}\n{proc.stderr[:4000]}")

    out = json.loads(proc.stdout)
    errors = [e for e in out.get("errors", []) if e.get("severity") == "error"]
    if errors:
        for e in errors:
            print(f"[solc error] {e['formattedMessage']}", file=sys.stderr)
        sys.exit("编译失败")

    warnings = [e for e in out.get("errors", []) if e.get("severity") == "warning"]
    for w in warnings[:5]:
        print(f"[solc warn] {w['message']}")

    artifacts: dict[str, dict] = {}
    BUILD.mkdir(parents=True, exist_ok=True)
    for name in ("ConcertTicket", "Helper"):
        c = out["contracts"][f"contracts/{name}.sol"][name]
        artifact = {
            "contractName": name,
            "compiler": {"version": SOLC_VERSION, "evmVersion": EVM_VERSION, "optimizer": True},
            "source_sha256": {
                "ConcertTicket.sol": _sha256(CONTRACTS / "ConcertTicket.sol"),
                "Helper.sol": _sha256(CONTRACTS / "Helper.sol"),
            },
            "abi": c["abi"],
            "bytecode": "0x" + c["evm"]["bytecode"]["object"],
            "deployedBytecode": "0x" + c["evm"]["deployedBytecode"]["object"],
        }
        (BUILD / f"{name}.json").write_text(json.dumps(artifact, indent=2, ensure_ascii=False), "utf-8")
        artifacts[name] = artifact
        size = (len(artifact["bytecode"]) - 2) // 2
        print(f"[compile] {name}: ABI {len(artifact['abi'])} 项, bytecode {size} bytes -> {BUILD / (name + '.json')}")
    return artifacts


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    os.chdir(ROOT)
    compile_contracts()
