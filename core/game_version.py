# -*- coding: utf-8 -*-
"""游戏版本校验：只放行 1.5.78 的《空洞骑士》。

为什么用 Assembly-CSharp.dll 的哈希，而不是读版本号：
  - hollow_knight.exe 里写的版本其实是 **Unity 引擎版本**（实测 2020.2.2.426360），
    不是游戏版本；
  - 游戏目录名（Hollow.Knight.v1.5.78.11833）用户能随便改，不可信；
  - Steam 的 appmanifest 只有 Steam 版才有，覆盖不到 GOG 版和手动解压的副本；
  - 而 Assembly-CSharp.dll 的内容由游戏版本唯一决定，换版本它必变。拿原版 dll
    的 SHA256 当指纹，Steam / GOG / 解压版一视同仁。

装上 Modding API 后这个 dll 会被"注入版"替换，所以校验必须看**原版**那份：
优先用 .v 备份（就是未注入的原版），没有 .v 时才看当前 dll 是否仍是原版。
"""
import hashlib
import os

from core.installer import _api_paths, _is_modded_dll
from utils.common import get_managed_dir

# 已知的原版 dll 指纹：{SHA256 -> 版本名}。只有命中这个表才允许装 API / 启动游戏。
# 采集自 1.5.78.11833（Windows Steam 版）。托管 dll 是平台无关的 IL，GOG 版和
# 手动解压的副本只要来自同一 build，内容就一致、哈希也一致。
# 以后若遇到"确属 1.5.78 但哈希不同"的发行版，把它的哈希加进这张表即可。
KNOWN_VANILLA_DLL = {
    "fcc01e0df1b841a8faf6b5e39f27030f63204ad02f430b3defa262134ae4e8a0": "1.5.78.11833",
}

# 对外展示时说的目标版本（含构建号，提示文案里要写全）
REQUIRED_VERSION = "1.5.78.11833"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 512), b""):
            h.update(chunk)
    return h.hexdigest()


def _vanilla_dll_for_check(game_path):
    """找出用于校验版本的那份「原版 dll」，返回 (路径, 找不到的原因)。

    顺序很重要：**当前 dll 优先，备份只作兜底**。反过来的话，「装了 API 之后
    游戏又被 Steam 升级」就会误判——那时当前 dll 已经换成新版原版，而 .v 里还
    留着旧的 1.5.78，优先看 .v 会把升级后的游戏放行。
    """
    cur, van, mod = _api_paths(get_managed_dir(game_path))

    # ① 当前 dll 没被注入 → 它如实反映游戏此刻的版本
    if os.path.isfile(cur) and not _is_modded_dll(cur):
        return cur, ""

    # ② 当前是模组版（装过 API）→ 原版已被替换，只能靠 .v 备份判断
    if os.path.isfile(van) and not _is_modded_dll(van):
        return van, ""

    if not os.path.isfile(cur):
        return None, "未找到 Assembly-CSharp.dll，请检查游戏路径是否正确。"

    # 当前是模组版又没有原版备份，无从判断它原本是哪个版本
    return None, ("当前已注入 Modding API 且缺少原版备份，无法判断游戏版本，"
                  "请先点「还原原版」。")


def check_game_version(game_path):
    """校验游戏版本。

    返回 dict：
        ok       是否放行（True = 确认是 1.5.78）
        version  识别出的版本名，未知时为空串
        sha256   参与校验的那份 dll 的哈希
        message  给用户的说明（不通过时说明原因，方便排查/上报新指纹）
    """
    path, reason = _vanilla_dll_for_check(game_path)
    if path is None:
        return {"ok": False, "version": "", "sha256": "", "message": reason}

    sha = _sha256(path)
    version = KNOWN_VANILLA_DLL.get(sha, "")
    if version:
        return {"ok": True, "version": version, "sha256": sha,
                "message": f"游戏版本校验通过，当前是{version}版本"}

    return {
        "ok": False,
        "version": "",
        "sha256": sha,
        "message": f"游戏版本校验不通过：当前游戏版本不是{REQUIRED_VERSION}。",
    }
