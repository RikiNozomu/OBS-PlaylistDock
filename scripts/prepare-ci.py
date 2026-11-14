"""Prepare OBS and its matching Qt SDK on a clean CI runner.

OBS_VERSION and DEPS_VERSION must match: DEPS_VERSION is the obs-deps release
that OBS_VERSION was built with (CMakePresets.json "prebuilt" version in the
OBS source). The plugin only loads on OBS releases shipping the same Qt minor.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".deps"
OBS_VERSION = "32.2.2"
DEPS_VERSION = "2026-07-15"
WORK.mkdir(exist_ok=True)


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def download(url, name):
    path = WORK / name
    if not path.exists():
        partial = path.with_name(path.name + ".part")
        for attempt in range(3):
            try:
                urllib.request.urlretrieve(url, partial)
                partial.replace(path)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
    return path


source_archive = download(f"https://github.com/obsproject/obs-studio/archive/refs/tags/{OBS_VERSION}.zip", "obs-source.zip")
with zipfile.ZipFile(source_archive) as archive:
    archive.extractall(WORK)
source = WORK / f"obs-studio-{OBS_VERSION}"
qt = WORK / "qt"
qt.mkdir(exist_ok=True)
sdk = WORK / "sdk"
sdk.mkdir(exist_ok=True)
deps_url = f"https://github.com/obsproject/obs-deps/releases/download/{DEPS_VERSION}/"

if sys.platform == "win32":
    with zipfile.ZipFile(download(deps_url + f"windows-deps-qt6-{DEPS_VERSION}-x64.zip", "qt.zip")) as archive:
        archive.extractall(qt)
    obs = WORK / "obs"
    with zipfile.ZipFile(download(f"https://github.com/obsproject/obs-studio/releases/download/{OBS_VERSION}/OBS-Studio-{OBS_VERSION}-Windows-x64.zip", "obs.zip")) as archive:
        archive.extractall(obs)
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft Visual Studio/Installer/vswhere.exe"
    visual_studio = Path(subprocess.check_output([str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"], text=True).strip())
    lib_tool = sorted((visual_studio / "VC/Tools/MSVC").glob("*/bin/Hostx64/x64/lib.exe"))[-1]
    run(sys.executable, ROOT / "scripts/prepare-windows-sdk.py", "--obs-source", source, "--obs-bin", obs / "bin/64bit", "--lib-tool", lib_tool, "--out", sdk)
    vlc = WORK / "vlc"
    vlc.mkdir(exist_ok=True)
    with zipfile.ZipFile(download("https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.zip", "vlc.zip")) as archive:
        archive.extractall(vlc)
    import winreg
    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC") as key:
        winreg.SetValueEx(key, "InstallDir", 0, winreg.REG_SZ, str(vlc / "vlc-3.0.21"))
else:
    dependencies = WORK / "dependencies"
    dependencies.mkdir(exist_ok=True)
    with tarfile.open(download(deps_url + f"macos-deps-{DEPS_VERSION}-arm64.tar.xz", "dependencies.tar.xz")) as archive:
        archive.extractall(dependencies, filter="data")
    with tarfile.open(download(deps_url + f"macos-deps-qt6-{DEPS_VERSION}-arm64.tar.xz", "qt.tar.xz")) as archive:
        archive.extractall(qt, filter="data")
    image = download(f"https://github.com/obsproject/obs-studio/releases/download/{OBS_VERSION}/OBS-Studio-{OBS_VERSION}-macOS-Apple.dmg", "obs-arm64.dmg")
    mount = WORK / "mount"
    run("hdiutil", "attach", image, "-readonly", "-nobrowse", "-mountpoint", mount)
    obs = WORK / "OBS.app"
    try:
        run("ditto", mount / "OBS.app", obs)
    finally:
        run("hdiutil", "detach", mount)
    includes = sdk / "include"
    includes.mkdir(exist_ok=True)
    (includes / "obsconfig.h").write_text("#pragma once\n#define OBS_RELEASE_CANDIDATE 0\n#define OBS_BETA 0\n")
    config = sdk / "cmake"
    config.mkdir(exist_ok=True)
    for target in ("libobs", "obs-frontend-api"):
        frameworks = obs / "Contents/Frameworks"
        binary = frameworks / "libobs.framework/Versions/A/libobs" if target == "libobs" else next(frameworks.glob("*obs-frontend-api*.dylib"))
        paths = [source / "libobs", includes, dependencies / "include"]
        if target == "obs-frontend-api":
            paths.append(source / "frontend/api")
        (config / f"{target}Config.cmake").write_text(
            f"if(NOT TARGET OBS::{target})\n  add_library(OBS::{target} SHARED IMPORTED GLOBAL)\n"
            f"  set_target_properties(OBS::{target} PROPERTIES IMPORTED_LOCATION \"{binary}\" "
            f"INTERFACE_INCLUDE_DIRECTORIES \"{';'.join(map(str, paths))}\")\nendif()\nset({target}_FOUND TRUE)\n")
    run("brew", "install", "--cask", "vlc")

(WORK / "environment.json").write_text(json.dumps({"obs": str(obs), "qt": str(qt), "sdk": str(sdk / "cmake")}))
