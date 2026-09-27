# -*- coding: utf-8 -*-
"""游戏版本校验：只放行 1.5.78 的《空洞骑士》。

为什么用 globalgamemanagers，而不是 Assembly-CSharp.dll 的哈希：
  - hollow_knight.exe 里写的版本其实是 **Unity 引擎版本**，不是游戏版本；
  - 游戏目录名（Hollow.Knight.v1.5.78.11833）用户能随便改，不可信；
  - Steam 的 appmanifest 只有 Steam 版才有，覆盖不到 GOG 版和手动解压的副本；
  - **最关键**：Modding API 注入**只改** Assembly-CSharp.dll，绝不碰
    globalgamemanagers —— 所以后者是「随游戏版本变化、又不被任何 Mod 改动」的最稳
    指纹。装了 API 之后当前 dll 变成模组版、拿不到原版哈希，但只要
    globalgamemanagers 命中 1.5.78 即可确信版本，无需再在 Managed 里写 .v/.m 备份。

这个门禁**只判断一件事：游戏本体是不是 1.5.78**。装 Mod（包括本工具自己装的
Modding API）只是往 Assembly-CSharp.dll 里注入代码，**不会改变游戏版本**，所以一个
装了 Mod 的 1.5.78 游戏必须照常放行。门禁要拦的只有一种情况：游戏本体不是 1.5.78
（如 Steam 升到别的版本、或路径指错了游戏）。
"""
import hashlib
import os

from utils.common import get_managed_dir

# 第二判定文件：Unity 的全局构建元数据 globalgamemanagers（位于 hollow_knight_Data/ 下）。
# 它和「游戏内容」(sharedassets*/resources.assets/level*) 是两码事——资源替换类 Mod
# 只改内容包、绝不碰它；Modding API 注入也**只改** Assembly-CSharp.dll、不碰它。
# 因此它是「随游戏版本变化、又不被任何 Mod 改动」的最稳版本指纹，也是唯一的权威来源。
SECONDARY_FILE = "globalgamemanagers"
KNOWN_SECONDARY_SHA256 = {
    "57ebbd860f452878d82000ed7caa9d40f22436ffcc1e56088eec28683c486efa": "1.5.78.11833",
}

# 已知的原版 dll 指纹：{SHA256 -> 版本名}。只用于**校验内置原版 dll 是否货真价实**
# （还原 API 时把内置原版复制到游戏目录前先核对），不再参与版本门禁判定。
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


def _secondary_check(game_path):
    """核对 globalgamemanagers 是否为 1.5.78。

    globalgamemanagers 是 Unity 的全局构建元数据，**只随游戏版本变化、且不被任何 Mod
    或 Modding API 改动**，所以它是判断游戏版本的唯一权威来源。返回 (state, version, sha256)：
        "ok"      命中已知 1.5.78 资源包
        "absent"  文件不存在（异常安装 / 路径指错）
        "mismatch"文件存在但哈希不符（很可能不是 1.5.78）
    """
    data_dir = os.path.dirname(get_managed_dir(game_path))
    path = os.path.join(data_dir, SECONDARY_FILE)
    if not os.path.isfile(path):
        return "absent", "", ""
    sha = _sha256(path)
    version = KNOWN_SECONDARY_SHA256.get(sha, "")
    if version:
        return "ok", version, sha
    return "mismatch", "", sha


def check_game_version(game_path):
    """校验游戏版本（只认 globalgamemanagers）。

    唯一权威信号就是 globalgamemanagers 的哈希：命中 1.5.78 即放行，缺失或不匹配
    即拒绝。不再依赖 Assembly-CSharp.dll（它被 Modding API 注入后不再是原版哈希），
    也不在 Managed 里写任何备份。

    返回 dict：
        ok        是否放行（True = 确认是 1.5.78）
        version   识别出的版本名，未知时为空串
        sha256    参与校验的文件哈希
        message   给用户的短结论（状态胶囊，只放关键字）
        detail    更完整的说明（用于 tooltip / 弹窗 / 日志）
    """
    state, version, sha = _secondary_check(game_path)

    if state == "ok":
        return {"ok": True, "version": version, "sha256": sha,
                "message": f"版本校验通过（{version}）",
                "detail": "可以安装 API 与启动游戏"}

    if state == "absent":
        reason = ("未找到 hollow_knight_Data/globalgamemanagers，无法确认游戏版本。"
                  "请确认游戏路径指向完整的《空洞骑士》安装目录。")
        return {"ok": False, "version": "", "sha256": "",
                "message": "无法确认游戏版本", "detail": reason}

    # mismatch：文件在，但哈希不在已知表里
    return {
        "ok": False, "version": "", "sha256": sha,
        "message": f"版本校验不通过（当前不是{REQUIRED_VERSION}）",
        "detail": ("游戏版本校验不通过：当前游戏版本不是 "
                   f"{REQUIRED_VERSION}。Steam 库右键游戏 → 属性 → 游戏版本及测试版"
                   f" → 选择 {REQUIRED_VERSION}。"),
    }
