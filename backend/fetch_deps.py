"""下载合约编译依赖 OpenZeppelin Contracts 5.0.2 到 contracts/lib/。

成员 2、3 在 Remix 里 import 的是 "@openzeppelin/contracts@5.0.2/..."，
即 Remix 自带 npm 解析。本地用 solc 编译需要自己准备同一版本源码。
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "contracts" / "lib" / "@openzeppelin" / "contracts"
VERSION = "5.0.2"
URL = f"https://registry.npmjs.org/@openzeppelin/contracts/-/contracts-{VERSION}.tgz"


def main() -> None:
    if (LIB / "token" / "ERC721" / "ERC721.sol").exists():
        print(f"[deps] OpenZeppelin Contracts {VERSION} 已存在: {LIB}")
        return

    print(f"[deps] 下载 {URL}")
    with tempfile.TemporaryDirectory() as tmp:
        tgz = Path(tmp) / "oz.tgz"
        with urllib.request.urlopen(URL, timeout=120) as r, open(tgz, "wb") as f:
            shutil.copyfileobj(r, f)
        with tarfile.open(tgz) as tar:
            tar.extractall(tmp, filter="data")
        src = Path(tmp) / "package"
        if not src.exists():
            sys.exit("npm 包结构异常，未找到 package/ 目录")
        LIB.parent.mkdir(parents=True, exist_ok=True)
        if LIB.exists():
            shutil.rmtree(LIB)
        shutil.copytree(src, LIB)

    print(f"[deps] 解压完成 -> {LIB}")


if __name__ == "__main__":
    main()
