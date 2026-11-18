"""Download the OpenZeppelin Contracts 5.0.2 dependency needed for compilation.

The sources land in contracts/lib/. Members 2 and 3 import
"@openzeppelin/contracts@5.0.2/..." in Remix, which resolves it through the npm support
bundled with Remix. Compiling locally with solc requires preparing the same version of
the sources yourself.
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
        print(f"[deps] OpenZeppelin Contracts {VERSION} already present: {LIB}")
        return

    print(f"[deps] Downloading {URL}")
    with tempfile.TemporaryDirectory() as tmp:
        tgz = Path(tmp) / "oz.tgz"
        with urllib.request.urlopen(URL, timeout=120) as r, open(tgz, "wb") as f:
            shutil.copyfileobj(r, f)
        with tarfile.open(tgz) as tar:
            tar.extractall(tmp, filter="data")
        src = Path(tmp) / "package"
        if not src.exists():
            sys.exit("Unexpected npm package layout: package/ directory not found")
        LIB.parent.mkdir(parents=True, exist_ok=True)
        if LIB.exists():
            shutil.rmtree(LIB)
        shutil.copytree(src, LIB)

    print(f"[deps] Extraction complete -> {LIB}")


if __name__ == "__main__":
    main()
