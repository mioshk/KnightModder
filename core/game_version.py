# -*- coding: utf-8 -*-
"""游戏版本校验：只放行 1.5.78 的《空洞骑士》。

为什么用 Assembly-CSharp.dll 的哈希，而不是读版本号：
  - hollow_knight.exe 里写的版本其实是 **Unity 引擎版本**（实测 2020.2.2.426360），
    不是游戏版本；
  - 游戏目录名（Hollow.Knight.v1.5.78.11833）用户能随便改，不可信；
  - Steam 的 appmanifest 只有 Steam 版才有，覆盖不到 GOG 版和手动解压的副本；
  - 而 Assembly-CSharp.dll 的内容由游戏版本唯一决定，换版本它必变。拿原版 dll
    的 SHA256 当指纹，Steam / GOG / 解压版一视同仁。

这个门禁**只判断一件事：游戏本体是不是 1.5.78**。它和「用户装了什么 Mod」毫无关系——
装 Mod（包括本工具自己装的 Modding API）只是往 Assembly-CSharp.dll 里注入代码，
**不会改变游戏版本**，所以一个装了 Mod 的 1.5.78 游戏必须照常放行。门禁要拦的只有
一种情况：游戏本体不是 1.5.78（比如 Steam 升到了别的版本、或路径指错了游戏）。

由于 Modding API 会改写 Assembly-CSharp.dll，原本那份「原版 dll 哈希」就取不到了，
于是另用一份**第二判定文件**来交叉确认版本：Unity 的全局构建元数据
`hollow_knight_Data/globalgamemanagers`。它和「游戏内容」(sharedassets*/resources.assets/
level*) 是两码事——资源替换类 Mod 只改内容包、绝不碰它，Modding API 注入也只改
Assembly-CSharp.dll、不碰它，所以它是「随版本变化、又不被任何 Mod 改动」的最稳确认源。
它只是「确认」信号——命中 1.5.78 指纹即可确信版本，缺失或不匹配都**不会**因此拦截，
只是少了一层确认，退回 dll 自身的判断。详见 _secondary_check 与 check_game_version。
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

# 第二判定文件：Unity 的全局构建元数据 globalgamemanagers（位于 hollow_knight_Data/ 下）。
# 选它的理由：它和「游戏内容」(sharedassets*/resources.assets/level*) 是两码事——资源替换
# 类 Mod 只改内容包、绝不碰它；Modding API 注入也**只改** Assembly-CSharp.dll、不碰它。
# 因此它是「随游戏版本变化、又不被任何 Mod 改动」的最稳交叉确认源。它只用来**确认**版本：
# 命中 1.5.78 即可确信，缺失/不匹配都**不会**拦截，只是退回 dll 自身的判断。
# 路径相对于 hollow_knight_Data 目录。
SECONDARY_FILE = "globalgamemanagers"
KNOWN_SECONDARY_SHA256 = {
    "57ebbd860f452878d82000ed7caa9d40f22436ffcc1e56088eec28683c486efa": "1.5.78.11833",
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
    """找出用于校验版本的那份 dll，返回 (路径, 原因, 缺原版备份)。

    顺序很重要：**当前 dll 优先，备份只作兜底**。反过来的话，「装了 API 之后
    游戏又被 Steam 升级」就会误判——那时当前 dll 已经换成新版原版，而 .v 里还
    留着旧的 1.5.78，优先看 .v 会把升级后的游戏放行。

    返回 路径=None 表示无法校验，原因写在 原因 里（此时 缺原版备份 恒为 False）。
    缺原版备份 为 True 时，路径指向「已被注入的模组版 dll」：靠它无法精确比对
    原版哈希，但能反推游戏版本（由 check_game_version 据此放行，见下文）。
    """
    cur, van, mod = _api_paths(get_managed_dir(game_path))

    # ① 当前 dll 没被注入 → 它如实反映游戏此刻的版本
    if os.path.isfile(cur) and not _is_modded_dll(cur):
        return cur, "", False

    # ② 当前是模组版（装过 API）→ 原版已被替换，只能靠 .v 备份判断
    if os.path.isfile(van) and not _is_modded_dll(van):
        return van, "", False

    if not os.path.isfile(cur):
        return None, "未找到 Assembly-CSharp.dll，请检查游戏路径是否正确。", False

    # ③ 当前是模组版、又没有原版备份：手动覆盖安装 API（没用本工具）的用户会
    #    走到这里。能跑到这步说明当前 dll 已被注入 Modding API —— 而 HK 的
    #    Modding API 只针对 1.5.78 一个版本发布，一个被注入的 dll 即可反推游戏
    #    是 1.5.78，故放行；但标记「缺原版备份」：离线还原需要它，没有就只能走
    #    Steam「验证游戏完整性」恢复官方原版。
    return cur, "", True


def _secondary_check(game_path):
    """核对第二判定文件（游戏资源包）是否为 1.5.78。

    《空洞骑士》的 Modding API 注入**只改** Assembly-CSharp.dll，绝不碰资源包，所以
    资源包的哈希可以独立交叉验证游戏版本：它只随游戏版本变化、且不会被装 Mod 改动。
    返回 (state, version, sha256)，state 取值：
        "ok"      命中已知 1.5.78 资源包
        "absent"  文件根本不存在（异常安装，无法靠它校验，退回 dll 推断兜底）
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


def _missing_vanilla_backup(van):
    """当前是否缺原版备份 .v（缺则无法离线还原）。"""
    return not (os.path.isfile(van) and not _is_modded_dll(van))


def check_game_version(game_path):
    """校验游戏版本。

    这个门禁**只判断一件事：游戏本体是不是《空洞骑士》1.5.78**。它和「用户装了什么
    Mod」毫无关系——装 Mod（包括本工具自己装的 Modding API）只是往 Assembly-CSharp.dll
    里注入代码，**不会改变游戏版本**，所以一个装了 Mod 的 1.5.78 游戏必须照常放行。
    门禁要拦的只有一种情况：游戏本体不是 1.5.78（如 Steam 升到别的版本、路径指错游戏）。

    判定顺序（任一命中即放行，只有「原版 dll 也不认识」才拒绝）：

        ① 当前 dll 是原版且命中已知指纹表 → 最稳，确认 1.5.78。
        ② 第二判定文件（资源包）命中 1.5.78 → 交叉确认版本；与 dll 是否被 Mod
           改动无关（装了 Mod 也照常确认）。资源包只是「确认」信号，缺失/不匹配
           都**不会**因此拦截，只是退回下面的 dll 判断。
        ③ 当前 dll 已被注入 Modding API → 可反推游戏是 1.5.78（API 只针对这一版
           发布），放行。装 Mod 不改版本，绝不会因「装了 Mod」而拦截。
        ④ 当前 dll 是原版但不在已知表（如 Steam 升到别的版本）→ 拒绝；缺失 → 拒绝。

    返回 dict：
        ok                是否放行（True = 确认是 1.5.78）
        version           识别出的版本名，未知时为空串
        sha256            参与校验的那份文件的哈希（dll 或资源包）
        message           给用户的短结论（用于状态胶囊，只放关键字）
        detail            更完整的说明（用于 tooltip / 弹窗 / 日志）
        no_vanilla_backup 当前是否缺原版备份 .v（缺则无法离线还原）
    """
    cur, van, mod = _api_paths(get_managed_dir(game_path))
    sec_state, sec_ver, sec_sha = _secondary_check(game_path)
    no_vanilla = _missing_vanilla_backup(van)

    # ① 当前 dll 是原版且命中已知指纹表：最稳，直接确认 1.5.78
    if os.path.isfile(cur) and not _is_modded_dll(cur):
        sha = _sha256(cur)
        v = KNOWN_VANILLA_DLL.get(sha)
        if v:
            return {"ok": True, "version": v, "sha256": sha,
                    "message": f"版本校验通过（{v}）",
                    "detail": "可以安装 API 与启动游戏",
                    "no_vanilla_backup": no_vanilla}

    # ② 第二判定文件（资源包）命中 1.5.78：交叉确认游戏版本（与 dll 是否被 Mod 改动无关）
    if sec_state == "ok":
        if not os.path.isfile(cur):
            return {"ok": False, "version": "", "sha256": sec_sha,
                    "message": "未找到 Assembly-CSharp.dll，请检查游戏路径是否正确。",
                    "detail": "未找到 Assembly-CSharp.dll，请检查游戏路径是否正确。",
                    "no_vanilla_backup": False}
        if _is_modded_dll(cur):
            # dll 已是注入版（装了 API 的用户）：资源包确认是 1.5.78，标记缺原版备份
            return {
                "ok": True, "version": sec_ver, "sha256": sec_sha,
                "message": f"已注入 Modding API（{sec_ver}）",
                "detail": ("游戏版本校验通过：资源包确认是 " + sec_ver + "，且当前 dll 已注入 "
                           "Modding API，可确认是 " + sec_ver + "。但缺少原版备份 .v，无法离线还原，"
                           "可用 Steam「验证游戏完整性」恢复官方原版后再重新安装 API。"),
                "no_vanilla_backup": True,
            }
        return {"ok": True, "version": sec_ver, "sha256": sec_sha,
                "message": f"版本校验通过（{sec_ver}）",
                "detail": "资源包确认是 " + sec_ver + "，可以安装 API 与启动游戏。",
                "no_vanilla_backup": no_vanilla}

    # ③ dll 已被注入 Modding API：可反推游戏是 1.5.78（API 只针对这一版发布），
    #    放行。装 Mod 不改游戏版本，绝不会因「装了 Mod」而拦截。
    if os.path.isfile(cur) and _is_modded_dll(cur):
        return {
            "ok": True,
            "version": REQUIRED_VERSION,
            "sha256": _sha256(cur),
            "message": f"已注入 Modding API（{REQUIRED_VERSION}）",
            "detail": ("游戏版本校验通过：当前 dll 已注入 Modding API，可确认是 "
                       f"{REQUIRED_VERSION}。但缺少原版备份 .v，无法离线还原，"
                       "可用 Steam「验证游戏完整性」恢复官方原版后再重新安装 API。"),
            "no_vanilla_backup": no_vanilla,
        }

    # ④ 兜底：当前 dll 是原版但不在已知表（如 Steam 升到别的版本），或缺失 → 拒绝
    path, reason, _ = _vanilla_dll_for_check(game_path)
    if path is None:
        return {"ok": False, "version": "", "sha256": "", "message": reason,
                "detail": reason, "no_vanilla_backup": False}
    sha = _sha256(path)
    version = KNOWN_VANILLA_DLL.get(sha, "")
    if version:
        return {"ok": True, "version": version, "sha256": sha,
                "message": f"版本校验通过（{version}）",
                "detail": "可以安装 API 与启动游戏",
                "no_vanilla_backup": _missing_vanilla_backup(van)}
    # 原版 dll 但哈希不在已知表内：版本不符（如 Steam 升级到其它版本）
    return {
        "ok": False,
        "version": "",
        "sha256": sha,
        "message": f"版本校验不通过（当前不是{REQUIRED_VERSION}）",
        "detail": ("游戏版本校验不通过：当前游戏版本不是 "
                   f"{REQUIRED_VERSION}。Steam 库右键游戏 → 属性 → 游戏版本及测试版"
                   f" → 选择 {REQUIRED_VERSION}。"),
        "no_vanilla_backup": False,
    }
