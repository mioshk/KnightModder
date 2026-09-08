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

## 构建与打包

KnightModder 支持 Windows / macOS / Linux 三端，但 **PyInstaller 不能交叉编译**——每个平台的独立包必须在该平台（或对应 CI runner）上构建。

- 本地构建：安装依赖后运行 `python build.py`，产物在 `dist/`（`KnightModder.exe` / `.app` / 无后缀二进制）。`build.py` 已自动收集 QtWebEngine（夸克登录用 `QWebEngineView`）；macOS 构建会读取 `entitlements.plist` 以标准方式签名。
- 自动构建（推荐，无需自有 Mac/Linux 硬件）：推送 `v*` 标签或在 Actions 页手动触发，GitHub Actions 会在 `windows-latest` / `macos-latest` / `ubuntu-latest` 三个 runner 上自动出包并作为 artifact 提供下载（见 `.github/workflows/build.yml`）。
- 自动发布：推送 `v*` 标签时，CI 会在构建完成后自动创建 GitHub Release，并把三端产物命名为 `KnightModder-windows.exe` / `KnightModder-macos.app` / `KnightModder-linux` 上传（手动触发只产生 artifact、不建 Release）。
- 分发注意：macOS 上若要分发给他人，需用 Apple Developer ID 签名并 notarization；CI 里的签名是带 `entitlements.plist` 的 ad-hoc 重签 + 强化运行时，仅本机/信任设备可直接打开，其它 Mac 首次打开需右键「打开」或 `xattr -cr`。

## 致谢

感谢所有 Mod 作者与 Hollow Knight 社区。
