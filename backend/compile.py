"""Compile ConcertTicket.sol / Helper.sol with solc 0.8.20 (Standard JSON).

The contracts delivered by Members 2 and 3 use Remix-style imports:
    import "@openzeppelin/contracts@5.0.2/token/ERC721/ERC721.sol";
solc does not understand the "@5.0.2" suffix, so a remapping maps it to
contracts/lib/@openzeppelin/contracts/ (downloaded by backend/fetch_deps.py).

Output:
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
EVM_VERSION = "paris"  # no PUSH0, so it also runs on the old London-rule private chain

SOLC_HOST_MAP = {
    ("Darwin", "x86_64"): "macosx-amd64",
    ("Darwin", "arm64"): "macosx-amd64",  # run the x86_64 build through Rosetta
    ("Linux", "x86_64"): "linux-amd64",
    ("Linux", "aarch64"): "linux-aarch64",
}


# Cloudflare fronts binaries.soliditylang.org and answers the default Python-urllib
# UA with 403 Forbidden, treating it as a crawler, so downloads must send a normal UA.
SOLC_UA = "Mozilla/5.0 (X11; Linux x86_64) ftec5520-build/1.0"


def _urlopen(url: str, timeout: int):
    """urlopen with a User-Agent header (a bare urlopen is rejected with 403)."""
    request = urllib.request.Request(url, headers={"User-Agent": SOLC_UA})
    return urllib.request.urlopen(request, timeout=timeout)


def solc_path() -> Path:
    """Return the path of the local solc binary, downloading it if it is missing."""
    local = BIN / "solc"
    if local.exists():
        return local

    host = SOLC_HOST_MAP.get((platform.system(), platform.machine()))
    if host is None:
        sys.exit(f"No solc download URL available for {platform.system()}/{platform.machine()}")

    BIN.mkdir(parents=True, exist_ok=True)
    base = f"https://binaries.soliditylang.org/{host}"
    with _urlopen(f"{base}/list.json", 30) as r:
        listing = json.load(r)
    key = next((k for k in listing["releases"] if k == SOLC_VERSION or k.startswith(SOLC_VERSION + "+")), None)
    if key is None:
        sys.exit(f"No solc {SOLC_VERSION} build found in list.json")
    url = f"{base}/{listing['releases'][key]}"
    print(f"[compile] Downloading solc {key}: {url}")
    with _urlopen(url, 180) as r, open(local, "wb") as f:
        shutil.copyfileobj(r, f)
    local.chmod(0o755)
    return local


def build_standard_json() -> dict:
    oz = CONTRACTS / "lib" / "@openzeppelin" / "contracts"
    if not (oz / "token" / "ERC721" / "ERC721.sol").exists():
        sys.exit("OpenZeppelin dependency missing, please run: python backend/fetch_deps.py")

    sources = {
        "contracts/ConcertTicket.sol": {"content": (CONTRACTS / "ConcertTicket.sol").read_text("utf-8")},
        "contracts/Helper.sol": {"content": (CONTRACTS / "Helper.sol").read_text("utf-8")},
    }
    return {
        "language": "Solidity",
        "sources": sources,
        "settings": {
            # remapping relative to base-path; absolute paths do not work in --standard-json
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
    """Compile and return {contract name: artifact}, also writing contracts/build/*.json."""
    solc = solc_path()
    payload = build_standard_json()
    proc = subprocess.run(
        [str(solc), "--standard-json", "--base-path", str(ROOT), "--allow-paths", str(ROOT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"solc exited with code {proc.returncode}\n{proc.stderr[:4000]}")

    out = json.loads(proc.stdout)
    errors = [e for e in out.get("errors", []) if e.get("severity") == "error"]
    if errors:
        for e in errors:
            print(f"[solc error] {e['formattedMessage']}", file=sys.stderr)
        sys.exit("Compilation failed")

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
        print(f"[compile] {name}: ABI {len(artifact['abi'])} items, bytecode {size} bytes -> {BUILD / (name + '.json')}")
    return artifacts


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    os.chdir(ROOT)
    compile_contracts()
