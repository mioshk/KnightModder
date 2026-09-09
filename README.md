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

## 项目结构与模块职责

面向开发者 / AI 的代码导航：

| 路径 | 职责 | 关键导出 |
| --- | --- | --- |
| `main.py` | 程序入口：崩溃日志、DPI/字体、创建主窗口、延迟检查更新 | `main()` |
| `config.py` | 全局常量：版本、Steam、网络 URL（CDN+Raw 双源）、API 夸克链接、配色 | `APP_VERSION`, `API_QUARK_LINKS`, `API_ZIP_MAP` |
| `core/installer.py` | 核心引擎：API 安装/还原（`.v`/`.m` 三份 dll 互换）、Mod 安装、夸克包解析 | `install_api`, `restore_vanilla`, `install_mods`, `_resolve_api_package` |
| `core/online_install.py` | 在线模组：抓取 ModLinks、Cookie 校验 | `verify_cookie` |
| `core/install_manager.py` | 安装编排：串联 UI → installer 的业务流程 | — |
| `core/quark.py` | 夸克网盘客户端：登录态、分享下载、断点续传 | `QuarkClient`, `QuarkError` |
| `utils/common.py` | 工具：路径解析、配置读写、Cookie 存取、远程内容抓取 | `get_managed_dir`, `load_saved_path`, `save_quark_cookie`, `fetch_remote_content` |
| `ui/main_window.py` | 主窗口与整体布局 | `MainWindow` |
| `ui/mod_page.py` | 在线/本地 Mod 列表与安装页 | `ModPage`, `OnlineModPage` |
| `ui/settings_page.py` | 设置页（夸克登录入口等） | `SettingsPage` |
| `ui/quark_login_dialog.py` | 夸克内嵌登录（缺 QtWebEngine 时回退手动粘贴 Cookie） | `show_quark_login_dialog` |
| `ui/dialogs.py` | 通用对话框（关于、路径选择、手动 Cookie 粘贴等） | `show_about_dialog`, `show_quark_cookie_dialog` |
| `ui/update_checker.py` | 启动后静默检查版本更新 | `auto_check_for_updates` |
| `ui/styles.py` | 深色主题样式表 | `DARK_STYLE_SHEET` |

### 关键数据流
- **安装 API**：`MainWindow` → `install_api()` → 本地 `downloads/` 缓存命中则直接用，否则 `QuarkClient.download_share()` 从夸克下载 → 解压覆盖 `Managed/` → 维护 `.v`(原版)/`.m`(模组版) 备份。
- **在线 Mod**：`ModPage` → `fetch_remote_content(ModLinksCN.xml)` → 列表展示 → 用户复制/下载。
- **登录**：`SettingsPage` → `show_quark_login_dialog()` → QtWebEngine 内嵌页扫码（无 QtWebEngine 则手动粘贴 Cookie）→ `save_quark_cookie()`。

> 打包配置：Windows 用 `main.spec`（含 `EXCLUDES` 排除未用 Qt 模块），macOS/Linux 由 CI（`build.yml`）以等价的 `--exclude-module` 列表构建；三端同步排除可显著减小体积。

## 致谢

感谢所有 Mod 作者与 Hollow Knight 社区。
