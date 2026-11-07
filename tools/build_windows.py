"""Build the Windows x64 resource distribution using pinned upstream releases."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
RELEASES = [
    ("MaaXYZ/MaaFramework", "v5.14.3", "MAA-win-x86_64-v5.14.3.zip",
     "4042fde31c583cc5125ec5b12257f8d1929672bb5cb64c9052c34fc8ff4bb8ff"),
    ("MaaXYZ/MFAAvalonia", "v2.16.4", "MFAAvalonia-v2.16.4-win-x64.zip",
     "e44c4e95d41d6566a38020550128726bfc91b96056602f8e320239671fab40fa"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New output directory; must not already exist")
    parser.add_argument("--cache", type=Path, default=ROOT / "build" / "downloads")
    parser.add_argument("--version", default="v1.7.6")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Output already exists: {output}")
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    extracted = []
    manifest = {"version": args.version, "components": []}
    for repo, tag, filename, expected in RELEASES:
        archive = cache / filename
        url = f"https://github.com/{repo}/releases/download/{tag}/{filename}"
        if not archive.exists():
            print(f"Downloading {filename}", flush=True)
            urllib.request.urlretrieve(url, archive)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Archive checksum mismatch: {archive}")
        target = cache / filename.removesuffix(".zip")
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (target / name).resolve().is_relative_to(target.resolve()):
                    raise ValueError(f"Unsafe archive path: {name}")
            z.extractall(target)
        extracted.append(target)
        manifest["components"].append({"repository": repo, "version": tag,
                                       "url": url, "sha256": actual})

    # Use MCCA's installer, with its destination and dependency root overridden.
    sys.path.insert(0, str(ROOT / "tools"))
    spec = importlib.util.spec_from_file_location("mcca_install", ROOT / "tools/install.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    output.mkdir(parents=True)
    installer.install_path = output
    installer.version = args.version
    # install_deps uses ROOT/deps; copying explicitly avoids changing that directory.
    shutil.copytree(extracted[0] / "bin", output, dirs_exist_ok=True)
    shutil.copytree(extracted[0] / "share/MaaAgentBinary", output / "MaaAgentBinary")
    installer.install_resource()
    installer.install_chores()
    # Keep the framework's flat plugin layout. The GUI archive's nested plugin
    # directory is not a DLL and causes the root native loader to report errors.
    shutil.copytree(extracted[1], output, dirs_exist_ok=True,
                    ignore=lambda directory, names: ["plugins"]
                    if Path(directory) == extracted[1] and "plugins" in names else [])
    native = output / "runtimes/win-x64/native/MaaFramework.dll"
    assert hashlib.sha256(native.read_bytes()).digest() == hashlib.sha256(
        (output / "MaaFramework.dll").read_bytes()).digest()
    manifest["resources"] = {
        str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((output / "resource").rglob("*")) if p.is_file()
    }
    manifest["interface_sha256"] = hashlib.sha256((output / "interface.json").read_bytes()).hexdigest()
    (output / "BUILD-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "START-HERE.txt").write_text(
        "MCCA v1.7.6 Windows x64 - JumpBack compatibility build\n\n"
        "Start MFAAvalonia.exe. Requires the x64 .NET 10 Runtime.\n"
        "Configure your emulator before running tasks.\n"
        "This build migrates is_sub/interrupt to JumpBack and includes tested\n"
        "repairs for daily gifts, time-limited trade, and weekly-stage paging.\n"
        "Do not accept the in-app v1.7.5 resource update: it is the older\n"
        "upstream resource and would replace these local repairs.\n"
        "No existing installation or user settings have been copied.\n\n"
        "Upstream source and licenses:\n"
        "MCCA (MIT): https://github.com/Airlient/MCCA\n"
        "MaaFramework (LGPL-3.0): https://github.com/MaaXYZ/MaaFramework/tree/v5.14.3\n"
        "MFAAvalonia (GPL-3.0): https://github.com/MaaXYZ/MFAAvalonia/tree/v2.16.4\n",
        encoding="utf-8")
    archive = shutil.make_archive(str(output), "zip", root_dir=output)
    print(f"Directory: {output}\nArchive: {archive}", flush=True)


if __name__ == "__main__":
    main()
