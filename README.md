# ⚔️ KnightModder

**空洞骑士·骑士模组师** —— 让每一位骑士都能轻松享受 Mod 的乐趣。

- 作者：[MioSs-](https://space.bilibili.com/538844794) ｜ [联系我](https://docs.qq.com/aio/DU2VHWGF0R2NtUWRI)

## 为什么会有这个工具？

想装 Mod 却总卡在第一步：打不开 GitHub、找不到链接、不会解压、报错不会排查。KnightModder 一键解决。

## 功能一览

- **一键安装 API**：选路径 → 安装，自动从夸克网盘下载 API 包并完成注入（本地 `downloads/` 已有则直接用，免重复下载）
- **原版 / 模组一键互换**：「安装 API / 还原原版」两个按钮在 原版↔模组版 间切换，自动备份、还原均无需重新下载
- **在线模组仓库**：Mod 链接集中展示，一键复制「本体 + 前置」批量下载
- **依赖检查**：自动扫描缺失前置，避免漏装崩溃
- **错误检测**：检查 Mod 结构，定位报错

## 注意事项

- 仅支持 **1.5.78 版本**，更高版本需先退回（步骤见 USAGE.md）
- 下载 Mod 与 API 均使用 **夸克网盘**，首次需登录夸克账号（弹窗扫码/授权）
- 还原原版依赖首次安装时自动生成的原版备份（`.v`）；若备份丢失，会提示用 Steam「验证游戏完整性」恢复，不自动下载原版

## 各平台游戏 / Mod 路径对照

KnightModder 已支持 Windows / macOS / Linux 自动识别游戏目录，Mod 安装位置按平台不同：

| 平台 | 游戏根目录示例 | Mods 目录（相对根目录） |
| --- | --- | --- |
| Windows (Steam) | `…\steamapps\common\Hollow Knight` | `hollow_knight_Data\Managed\Mods` |
| Linux (Steam) | `~/.steam/steam/steamapps/common/Hollow Knight` | `hollow_knight_Data/Managed/Mods` |
| macOS (Steam) | `~/Library/Application Support/Steam/steamapps/common/Hollow Knight` | `Hollow Knight.app/Contents/Resources/Data/Managed/Mods` |

说明：
- **macOS 游戏在 `.app` 包内**，没有 `hollow_knight_Data` 文件夹，Mods 实际位于 `Hollow Knight.app/Contents/Resources/Data/Managed/Mods`。
- API 注入目标（Managed 目录）同理按平台分支。
- 启动方式：Steam 官方版走 `steam://rungameid/367520`；macOS 自定义副本用 `open` 拉起 `.app`，Linux 直接运行 `hollow_knight.x86_64`。
- 进程探测 / 单实例锁（Mutex）检测为 Windows 专属机制；macOS / Linux 上进程检测改用 psutil，单实例锁检测自动跳过。

## 致谢

感谢所有 Mod 作者与 Hollow Knight 社区。
