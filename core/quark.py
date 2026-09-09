# -*- coding: utf-8 -*-
"""
夸克网盘下载内核

复用 QuarkPanTool(https://github.com/...) 逆向出的夸克 Web 接口，用
requests 同步实现，供"软件内一键下载并安装 Mod"使用。

核心链路（夸克限制：download 接口只允许下载自己网盘内的文件）：
    分享链接 -> 解析 pwd_id/passcode -> 取 stoken -> 列出分享文件树
    -> 转存到自己网盘的目录(save) -> 轮询转存任务完成
    -> 在自己网盘定位文件(sort) -> 拿下载地址(file/download) -> 流式下载

转存目录策略：所有转存都放在用户网盘根目录的「KnightModder」文件夹下，
每次下载建一个独立子目录；下载完成后【不删除】，保留在网盘里由用户自行清理。

调用示例（供 CLI 自测 / M2 安装管理器调用）：
    from core.quark import QuarkClient
    client = QuarkClient(cookie_str="__pus=xxx; __puus=yyy; ...")
    client.download_share(
        url="https://pan.quark.cn/s/f69929220293",
        local_dir=r"D:/mods_tmp",
        progress_callback=lambda done, total, name: print(name, done, total),
    )
"""
import ast
import json
import os
import random
import re
import time

import requests

# ---------------- cookie 存取 ----------------

def _timestamp13() -> int:
    return int(time.time() * 1000)


def _random_dt() -> int:
    return random.randint(100, 9999)


class QuarkError(Exception):
    """夸克接口/网络异常（错误消息已经过友好化处理）。"""


class QuarkClient:
    """夸克网盘客户端：负责 cookie 管理、分享解析、转存与下载。"""

    # 主业务 UA（与 QuarkPanTool 保持一致）
    PC_UA = ("Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/94.0.4606.71 Safari/537.36 "
             "Core/1.94.225.400 QQBrowser/12.2.5544.400")
    # 客户端 UA：file/download 返回 23018（需客户端 UA）时切换
    CLIENT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) quark-cloud-drive/2.5.56 "
                 "Chrome/100.0.4896.160 Electron/18.3.5.12-a038f7b798 "
                 "Safari/537.36 Channel/pckk_other_ch")
    # 下载文件时使用的 UA
    DL_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0")

    def __init__(self, cookie_str: str = "", cookie_path: str = "",
                 progress_callback=None, status_callback=None,
                 timeout: int = 60, verify_login: bool = True):
        """
        :param cookie_str: 夸克 Cookie 头字符串（如 "k=v; k2=v2"）
        :param cookie_path: Cookie 文件路径（json 或 QuarkPanTool cookies.txt 格式）
        :param progress_callback: 下载进度回调(done_bytes, total_bytes, file_name)
        :param status_callback: 状态/日志回调(message, level)，level: info/warn/error/success
        :param verify_login: 构造时是否立即调 account/info 探测登录态。
            并行下载时每路一个客户端实例，但只需主客户端探测一次，其余传
            verify_login=False 以省去重复请求（前提是 cookie 已被外部验证有效）。
        """
        self.progress_callback = progress_callback or (lambda *a: None)
        self.status_callback = status_callback or (lambda *a: None)
        self.timeout = timeout
        self.session = requests.Session()

        cookie = cookie_str or self._read_cookie_file(cookie_path) if cookie_path else cookie_str
        self.cookies = self._normalize_cookie_str(cookie)
        self.base_headers = {
            "user-agent": self.PC_UA,
            "origin": "https://pan.quark.cn",
            "referer": "https://pan.quark.cn/",
            "accept-language": "zh-CN,zh;q=0.9",
            "cookie": self.cookies,
        }
        self.is_logged_in = self.check_login() if verify_login else True
        # 云端管理根目录（KnightModder）fid 缓存：整个客户端生命周期只创建一次
        self._cloud_root_cache: dict = {}

    # ---------------- cookie 工具 ----------------

    @staticmethod
    def _read_cookie_file(cookie_path: str) -> str:
        """读取 cookie 文件：支持 json list/dict、QuarkPanTool cookies.txt、header 串"""
        if not cookie_path or not os.path.isfile(cookie_path):
            return ""
        with open(cookie_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        if not content:
            return ""
        # JSON list [{name,value,domain,...}] / dict {name:value}
        try:
            data = json.loads(content)
            return QuarkClient._cookie_data_to_str(data)
        except (ValueError, TypeError):
            pass
        # QuarkPanTool cookies.txt: Python repr 的 list —— 用 ast.literal_eval 安全解析
        try:
            data = ast.literal_eval(content)
            return QuarkClient._cookie_data_to_str(data)
        except (ValueError, SyntaxError):
            pass
        # 其余直接当 header 串
        return content

    @staticmethod
    def _cookie_data_to_str(data) -> str:
        pairs = []
        if isinstance(data, dict):
            pairs = [(str(k), str(v)) for k, v in data.items()]
        elif isinstance(data, list):
            for c in data:
                if isinstance(c, dict):
                    domain = str(c.get("domain", ""))
                    if "quark" not in domain and domain not in ("pan.quark.cn",):
                        continue
                    name, value = c.get("name"), c.get("value")
                    if name and value is not None:
                        pairs.append((str(name), str(value)))
        return "; ".join(f"{k}={v}" for k, v in pairs)

    @staticmethod
    def _normalize_cookie_str(cookie: str) -> str:
        if not cookie:
            return ""
        cookie = cookie.strip()
        # 若用户误传 list/dict 结构，转成 header 串
        if cookie.startswith("["):
            try:
                return QuarkClient._cookie_data_to_str(json.loads(cookie))
            except (ValueError, TypeError):
                pass
        if cookie.startswith("{"):
            try:
                return QuarkClient._cookie_data_to_str(json.loads(cookie))
            except (ValueError, TypeError):
                pass
        return cookie

    # ---------------- 登录态检查 ----------------

    def check_login(self) -> bool:
        """调 account/info 验证 cookie 是否有效"""
        if not self.cookies:
            return False
        try:
            r = self.session.get(
                "https://pan.quark.cn/account/info",
                params={"fr": "pc", "platform": "pc"},
                headers=self.base_headers,
                timeout=self.timeout,
            )
            return bool(r.json().get("data"))
        except Exception:
            return False

    def get_nickname(self) -> str:
        try:
            r = self.session.get(
                "https://pan.quark.cn/account/info",
                params={"fr": "pc", "platform": "pc"},
                headers=self.base_headers,
                timeout=self.timeout,
            )
            data = r.json().get("data") or {}
            return data.get("nickname", "")
        except Exception:
            return ""

    # ---------------- 分享链接解析 ----------------

    @staticmethod
    def parse_share_url(url: str):
        """
        解析分享链接，返回 (pwd_id, passcode)
        兼容 https://pan.quark.cn/s/abcde?pwd=123 等格式
        """
        text = (url or "").strip()
        match = re.search(r"/s/([0-9a-zA-Z]+)", text)
        if not match:
            raise QuarkError("无效的夸克分享链接")
        pwd_id = match.group(1)
        passcode = ""
        m = re.search(r"pwd=([0-9a-zA-Z]+)", text)
        if m:
            passcode = m.group(1)
        return pwd_id, passcode

    # ---------------- 分享页：stoken / detail ----------------

    def get_stoken(self, pwd_id: str, passcode: str = "") -> str:
        api = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token"
        params = {
            "pr": "ucpro", "fr": "pc", "uc_param_str": "",
            "__dt": _random_dt(), "__t": _timestamp13(),
        }
        try:
            r = self.session.post(api, json={"pwd_id": pwd_id, "passcode": passcode},
                                  params=params, headers=self.base_headers,
                                  timeout=self.timeout)
            data = r.json()
        except Exception as e:
            raise QuarkError(f"网络请求失败：{e}") from e
        if data.get("status") == 200 and data.get("data"):
            return data["data"]["stoken"]
        raise QuarkError(f"链接解析失败：{data.get('message', '未知错误')}")

    def get_detail(self, pwd_id: str, stoken: str, pdir_fid: str = "0"):
        """
        列出分享目录某层文件。返回 (is_owner, [file dicts])
        file dict 字段: fid/file_name/file_type/dir/pdir_fid/share_fid_token/include_items/status
        """
        api = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        page = 1
        file_list = []
        is_owner = 0
        while True:
            params = {
                "pr": "ucpro", "fr": "pc", "uc_param_str": "",
                "pwd_id": pwd_id, "stoken": stoken,
                "pdir_fid": pdir_fid, "force": "0",
                "_page": str(page), "_size": "50",
                "_sort": "file_type:asc,updated_at:desc",
                "__dt": _random_dt(), "__t": _timestamp13(),
            }
            try:
                r = self.session.get(api, params=params, headers=self.base_headers,
                                     timeout=self.timeout)
                data = r.json()
            except Exception as e:
                raise QuarkError(f"网络请求失败：{e}") from e
            payload = data.get("data") or {}
            meta = data.get("metadata") or {}
            is_owner = payload.get("is_owner", 0)
            total = int(meta.get("_total") or 0)
            if total < 1:
                return is_owner, file_list
            size = int(meta.get("_size") or 50)
            count = int(meta.get("_count") or 0)
            for f in payload.get("list") or []:
                file_list.append({
                    "fid": f.get("fid"),
                    "file_name": f.get("file_name"),
                    "file_type": f.get("file_type"),
                    "dir": f.get("dir"),
                    "pdir_fid": f.get("pdir_fid"),
                    "include_items": f.get("include_items", ""),
                    "share_fid_token": f.get("share_fid_token"),
                    "status": f.get("status"),
                    "size": f.get("size", 0),
                })
            if total <= size or count < size:
                return is_owner, file_list
            page += 1

    def walk_share(self, pwd_id: str, stoken: str, pdir_fid: str = "0", rel_path: str = "",
                   is_owner: int = 0):
        """
        递归遍历分享文件树。
        返回 (files, folders_map, is_owner)
        files: [{fid, file_name, size, rel_path, share_fid_token, pdir_fid}]
        folders_map: {fid: {file_name, pdir_fid}} 用于还原目录结构
        is_owner: 该分享是否为当前登录账号自己所创建（夸克禁止转存自己的分享）
        """
        files, folders_map = [], {}
        is_owner, item_list = self.get_detail(pwd_id, stoken, pdir_fid=pdir_fid)
        for item in item_list:
            name = item["file_name"]
            if item.get("dir"):
                folders_map[item["fid"]] = {
                    "file_name": name,
                    "pdir_fid": item["pdir_fid"],
                }
                sub_rel = os.path.join(rel_path, name) if rel_path else name
                sub_files, sub_map, _ = self.walk_share(pwd_id, stoken,
                                                     pdir_fid=item["fid"],
                                                     rel_path=sub_rel,
                                                     is_owner=is_owner)
                files.extend(sub_files)
                folders_map.update(sub_map)
            else:
                files.append({
                    "fid": item["fid"],
                    "file_name": name,
                    "size": item.get("size", 0),
                    "rel_path": rel_path,
                    "share_fid_token": item.get("share_fid_token"),
                    "pdir_fid": item.get("pdir_fid"),
                })
        return files, folders_map, is_owner

    # ---------------- 自己网盘：建目录 / 列表 / 转存 ----------------

    def create_dir(self, dir_name: str, pdir_fid: str = "0") -> str:
        """在自己网盘的 pdir_fid 下新建目录，返回新目录 fid"""
        api = "https://drive-pc.quark.cn/1/clouddrive/file"
        params = {
            "pr": "ucpro", "fr": "pc", "uc_param_str": "",
            "__dt": _random_dt(), "__t": _timestamp13(),
        }
        body = {
            "pdir_fid": pdir_fid,
            "file_name": dir_name,
            "dir_path": "",
            "dir_init_lock": False,
        }
        r = self.session.post(api, params=params, json=body,
                              headers=self.base_headers, timeout=self.timeout)
        data = r.json()
        if data.get("code") == 0 and data.get("data"):
            return data["data"]["fid"]
        if data.get("code") == 23008:
            # 同名冲突：通过列表查找已有目录 fid
            for f in self.list_own_dir(pdir_fid):
                if f.get("dir") and f.get("file_name") == dir_name:
                    return f["fid"]
            raise QuarkError(f"创建目录失败：同名冲突且无法定位")
        raise QuarkError(f"创建目录失败：{data.get('message', '未知错误')}")

    def list_own_dir(self, pdir_fid: str = "0", page: int = 1, size: int = 100):
        """列出自己网盘目录下的文件（sort 接口，自动翻页返回全部）"""
        api = "https://drive-pc.quark.cn/1/clouddrive/file/sort"
        out = []
        while True:
            params = {
                "pr": "ucpro", "fr": "pc", "uc_param_str": "",
                "pdir_fid": pdir_fid,
                "_page": str(page), "_size": str(size),
                "_fetch_total": "false", "_fetch_sub_dirs": "1",
                "_sort": "",
                "__dt": _random_dt(), "__t": _timestamp13(),
            }
            r = self.session.get(api, params=params, headers=self.base_headers,
                                 timeout=self.timeout)
            data = r.json()
            items = (data.get("data") or {}).get("list") or []
            for f in items:
                out.append({
                    "fid": f.get("fid"),
                    "file_name": f.get("file_name"),
                    "dir": f.get("dir"),
                    "pdir_fid": f.get("pdir_fid"),
                    "size": f.get("size", 0),
                })
            if len(items) < size:
                break
            page += 1
        return out

    # ---------------- 云端管理目录 / 临时转存清理 ----------------

    # 统一的云端管理根目录名：所有在线下载的转存文件都放在这一个目录里，
    # 避免在用户网盘根目录反复创建一堆 "KnightModder_xxx" 文件夹。
    # 下载完成后不会自动删除，用户可到网盘里自行清理。
    CLOUD_ROOT_NAME = "KnightModder"

    @staticmethod
    def _sanitize_part(name: str) -> str:
        """把目录名片段清洗成网盘友好的文件名片段"""
        cleaned = re.sub(r"[^\w\u4e00-\u9fa5-]+", "-", str(name or "")).strip("-")
        return cleaned or "mod"

    def _find_child_dir(self, parent_fid: str, name: str):
        """在 parent_fid 下找同名目录，返回其 fid；没有则返回 None"""
        for f in self.list_own_dir(parent_fid):
            if f.get("dir") and f.get("file_name") == name:
                return f["fid"]
        return None

    def _ensure_cloud_root(self) -> str:
        """确保云端管理根目录存在（同一客户端只向 API 查询一次）并返回其 fid"""
        cached = self._cloud_root_cache.get(self.CLOUD_ROOT_NAME)
        if cached:
            return cached
        fid = self._find_child_dir("0", self.CLOUD_ROOT_NAME)
        if not fid:
            fid = self.create_dir(self.CLOUD_ROOT_NAME, pdir_fid="0")
        self._cloud_root_cache[self.CLOUD_ROOT_NAME] = fid
        return fid

    def _find_own_file(self, filename: str, size: int):
        """在自己网盘里按文件名+大小查找文件；命中返回真实 cloud fid，未命中返回 None。

        用于"分享链接本身就是自己网盘里的文件"的场景：检测到后直接拿真实 fid
        下载，跳过转存（省一次云端复制，也避免重复堆积文件）。
        """
        api = "https://drive-pc.quark.cn/1/clouddrive/file/search"
        params = {
            "pr": "ucpro", "fr": "pc", "uc_param_str": "",
            "pdir_fid": "0", "filename": filename, "type": "0",
            "_page": "1", "_size": "50",
            "__dt": _random_dt(), "__t": _timestamp13(),
        }
        try:
            r = self.session.get(api, params=params, headers=self.base_headers,
                                 timeout=self.timeout)
            data = r.json()
        except Exception:
            return None
        for f in (data.get("data") or {}).get("list") or []:
            if f.get("file_name") == filename and int(f.get("size") or 0) == size:
                return f.get("fid")
        return None

    def _list_file_index(self, dir_fid: str):
        """
        列出目录内文件的索引：{file_name: [{"fid":..., "size":...}, ...]}

        同一个文件名可能出现多次（重复转存/网盘自动改名），所以值是列表。
        用于转存前后做差集，精确定位"本次新转存进来的文件"。
        """
        index = {}
        for item in self.list_own_dir(dir_fid):
            if item.get("dir"):
                continue
            index.setdefault(item.get("file_name"), []).append({
                "fid": item.get("fid"),
                "size": int(item.get("size") or 0),
            })
        return index

    def _best_effort_remove(self, fid: str):
        """
        尽力删除自己创建的云端目录（连同转存内容，删除是异步任务）。

        注意：正常下载流程【不再自动调用】本方法——转存文件会保留在网盘的
        「KnightModder」目录中，由用户自行决定是否清理。此方法保留下来，
        仅供将来做「手动清理云端转存」功能时使用。
        """
        if not fid:
            return
        try:
            r = self.session.post(
                "https://drive-pc.quark.cn/1/clouddrive/file/delete",
                params={
                    "pr": "ucpro", "fr": "pc", "uc_param_str": "",
                    "__dt": _random_dt(), "__t": _timestamp13(),
                },
                json={"action_type": 2, "filelist": [fid], "exclude_fids": []},
                headers=self.base_headers,
                timeout=self.timeout,
            )
            data = r.json()
            tid = (data.get("data") or {}).get("task_id")
            if tid:
                # 删除任务通常几秒内完成：短间隔轮询确认即可，
                # 无需按「转存」的长上限等待，超时就留给后台处理并降级为告警。
                self.poll_task(tid, delay=0.6, max_retry=20)
            self.status_callback("云端临时转存目录已自动清理", "info")
        except Exception as e:  # noqa: BLE001
            self.status_callback(f"云端临时目录清理失败（不影响下载结果）：{e}", "warn")

    def save_share(self, pwd_id: str, stoken: str, fid_list, token_list,
                   to_pdir_fid: str = "0") -> str:
        """把分享文件转存到自己网盘目录，返回任务 task_id"""
        api = "https://drive.quark.cn/1/clouddrive/share/sharepage/save"
        params = {
            "pr": "ucpro", "fr": "pc", "uc_param_str": "",
            "__dt": _random_dt(), "__t": _timestamp13(),
        }
        body = {
            "fid_list": fid_list,
            "fid_token_list": token_list,
            "to_pdir_fid": to_pdir_fid,
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": "0",
            "scene": "link",
        }
        r = self.session.post(api, params=params, json=body,
                              headers=self.base_headers, timeout=self.timeout)
        data = r.json()
        if data.get("status") == 200 and data.get("data"):
            return data["data"]["task_id"]
        raise QuarkError(f"转存失败：{data.get('message', '未知错误')}")

    def poll_task(self, task_id: str, max_retry: int = 60, delay: float = 0.8,
                  on_wait=None):
        """轮询异步任务直至完成；成功返回 json，超时抛异常。
        :param on_wait: 可选回调(第几次, 总上限)，约每 4 次轮询回调一次，
            用于界面实时提示「转存中/等待服务器处理」，避免长时间无反馈。
        """
        for i in range(max_retry):
            time.sleep(delay + random.uniform(0, 0.3))
            if on_wait and i % 4 == 0:
                try:
                    on_wait(i + 1, max_retry)
                except Exception:  # noqa: BLE001
                    pass
            url = ("https://drive-pc.quark.cn/1/clouddrive/task"
                   f"?pr=ucpro&fr=pc&uc_param_str=&task_id={task_id}"
                   f"&retry_index={i}&__dt=21192&__t={_timestamp13()}")
            r = self.session.get(url, headers=self.base_headers, timeout=self.timeout)
            data = r.json()
            if data.get("message") == "ok" and data.get("data", {}).get("status") == 2:
                return data
            msg = data.get("message", "")
            if "capacity limit" in msg:
                raise QuarkError("转存失败：网盘容量不足")
        # 文案保持通用：此函数不只轮询「转存」，也用于清理阶段的「删除」任务，
        # 若写死「转存任务超时」会在清理失败时误导用户（实际转存早已成功）。
        raise QuarkError("云端任务处理超时，请稍后重试")

    # ---------------- 下载 ----------------

    def get_download_urls(self, fids) -> list:
        """对自己网盘内的文件批量获取下载地址，返回 [{fid,file_name,download_url,size,pdir_fid}]"""
        api = "https://drive-pc.quark.cn/1/clouddrive/file/download"
        params = {
            "pr": "ucpro", "fr": "pc", "sys": "win32",
            "ve": "2.5.56", "ut": "", "guid": "",
        }
        headers = {
            "user-agent": self.DL_UA,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "accept-language": "zh-CN",
            "origin": "https://pan.quark.cn",
            "referer": "https://pan.quark.cn/",
            "cookie": self.cookies,
        }
        last_err = ""
        for attempt in range(2):
            r = self.session.post(api, params=params, json={"fids": fids},
                                  headers=headers, timeout=self.timeout)
            data = r.json()
            if data.get("code") == 23018 and attempt == 0:
                headers["user-agent"] = self.CLIENT_UA
                continue
            if data.get("status") != 200 or not data.get("data"):
                last_err = data.get("message", "未知错误")
                continue
            out = []
            for i in data["data"]:
                out.append({
                    "fid": i.get("fid"),
                    "file_name": i.get("file_name"),
                    "download_url": i.get("download_url"),
                    "size": i.get("size", 0),
                    "pdir_fid": i.get("pdir_fid"),
                })
            return out
        raise QuarkError(f"获取下载地址失败：{last_err or '未知错误'}")

    def download_file(self, url: str, save_path: str, expect_size: int = 0) -> str:
        """流式下载单个文件，支持断点续传。返回最终文件路径

        :param expect_size: 期望的文件大小（来自分享信息）。用于防止把「上一次
            中断下载的旧版本残留 .part」当成断点续传的起点拼进新版本里。
        """
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        part_path = save_path + ".part"
        resumed = os.path.getsize(part_path) if os.path.isfile(part_path) else 0
        if resumed and expect_size and resumed > expect_size:
            # 残留分片比新版本还大（旧版本残留）：丢弃重下
            try:
                os.remove(part_path)
            except OSError:
                pass
            resumed = 0

        headers = {
            "user-agent": self.DL_UA,
            "origin": "https://pan.quark.cn",
            "referer": "https://pan.quark.cn/",
            "cookie": self.cookies,
        }
        if resumed:
            headers["range"] = f"bytes={resumed}-"

        r = self.session.get(url, headers=headers, stream=True, timeout=self.timeout)
        if r.status_code not in (200, 206):
            raise QuarkError(f"下载失败（HTTP {r.status_code}）")
        if resumed and r.status_code == 200:
            # 服务器忽略了 Range 请求（返回完整内容）：不能追加，必须从头写
            resumed = 0

        total = None
        if "content-length" in r.headers:
            total = int(r.headers.get("content-length") or 0) + resumed

        mode = "ab" if resumed else "wb"
        done = resumed
        with open(part_path, mode) as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self.progress_callback(done, total,
                                               os.path.basename(save_path))
        if total is None:
            self.progress_callback(done, done, os.path.basename(save_path))
        os.replace(part_path, save_path)
        return save_path

    # ---------------- 组合流程 ----------------

    def download_share(self, url: str, local_dir: str,
                       remote_dir_name: str = "", passcode: str = "",
                       select_file=None, return_files: bool = False,
                       force_transfer: bool = False):
        """
        高级入口：解析分享 -> 转存到自己的云盘目录 -> 下载全部/选定文件到 local_dir。

        :param url: 夸克分享链接
        :param local_dir: 下载到本地哪个目录
        :param remote_dir_name: Mod 名（用于判断云端同名文件是否属于本 Mod；缺省用分享码）。
            所有转存文件平铺在用户网盘统一的「KnightModder」目录中（不建子目录），
            已存在且大小一致、且文件名属于本 Mod 的文件直接复用不再重复转存；
            下载完成后【保留不删除】，用户可到网盘里自行清理。
        :param passcode: 提取码
        :param force_transfer: True 时跳过"云端已有同名同大小文件就复用"的优化，
            强制重新转存一份再下载（用于 sha 校验不通过时自愈重试）
        :param select_file: 可选过滤器 lambda(file dict) -> bool，默认下载所有文件
        :param return_files: 为 True 时额外返回本次下载的文件绝对路径列表
        :return: 仅下载目录（str）；return_files=True 时返回 (下载目录, [文件绝对路径])
        """
        if not self.is_logged_in:
            raise QuarkError("夸克未登录或登录已过期，请先登录夸克账号")

        pwd_id, auto_pwd = self.parse_share_url(url)
        passcode = passcode or auto_pwd

        self.status_callback("正在解析分享链接...", "info")
        stoken = self.get_stoken(pwd_id, passcode)
        files, _, is_owner = self.walk_share(pwd_id, stoken)
        if not files:
            raise QuarkError("分享内容为空或无法读取")

        # 需要下载的文件
        targets = [f for f in files if (select_file is None or select_file(f))]
        if not targets:
            raise QuarkError("分享内容中没有找到可下载的文件")
        total_size = sum(int(t.get("size") or 0) for t in targets)
        self.status_callback(
            f"分享内容共 {len(files)} 个文件，本次需下载 {len(targets)} 个"
            f"（{self._fmt_size(total_size)}）", "info")

        # ---------- 自己的分享：跳过"转存"，直接下载网盘原文件 ----------
        # 夸克限制：禁止"转存自己的分享"（报错"用户禁止转存自己的分享"）。
        # 但分享里的文件本来就在你自己的网盘里——get_detail 返回的 fid 就是这些文件
        # 在你网盘中的真实 fid，直接拿它去 /file/download 取下载地址即可，既不触发被禁
        # 止的转存，也不会在你的网盘里产生重复副本。非本人的分享无法直下（fid 指向
        # 分享者网盘、不在你网盘内），仍按下方原有逻辑转存后再下载。
        if is_owner:
            self.status_callback(
                "检测到这是您自己的分享，已跳过转存，直接下载网盘中的原文件",
                "success")
            need_fids = [t["fid"] for t in targets]
            try:
                url_map = {i["fid"]: i for i in self.get_download_urls(need_fids)}
            except QuarkError as e:
                raise QuarkError(
                    f"获取下载地址失败（请确认分享文件仍在您网盘中）：{e}") from e
            downloaded = []
            for t, fid in zip(targets, need_fids):
                info = url_map.get(fid)
                if not info or not info.get("download_url"):
                    raise QuarkError(
                        f"获取下载地址失败：{t['file_name']}"
                        f"（请确认该文件仍在您网盘中）")
                rel = t.get("rel_path") or ""
                dest_dir = os.path.join(local_dir, rel) if rel else local_dir
                self.status_callback(f"开始下载：{t['file_name']}", "info")
                final_path = self.download_file(
                    info["download_url"], os.path.join(dest_dir, t["file_name"]),
                    expect_size=int(info.get("size") or t.get("size") or 0))
                downloaded.append(final_path)
            self.status_callback(
                "全部文件下载完成（您自己的分享，未产生任何云端副本）", "success")
            result_dir = (os.path.join(local_dir, targets[0]["rel_path"])
                          if targets[0].get("rel_path") else local_dir)
            if return_files:
                return result_dir, downloaded
            return result_dir

        # ---------- 自己的网盘文件：跳过转存，直接下载 ----------
        # 若分享链接指向的就是用户自己网盘里的文件，按"文件名+大小"在网盘里定位真实
        # fid，命中则无需转存（省一次云端复制、也避免重复堆积文件），直接下载。
        own_fid = {}
        for t in targets:
            name = t["file_name"]
            size = int(t.get("size") or 0)
            if size:
                fid = self._find_own_file(name, size)
                if fid:
                    own_fid[name] = fid
        if own_fid:
            self.status_callback(
                f"检测到 {len(own_fid)} 个文件已在您网盘中，跳过转存直接下载",
                "success")

        # ---------- 云盘转存：直接放进「KnightModder」，不套子目录 ----------
        # 全部文件平铺在网盘 KnightModder/ 下；更新时先清掉该 Mod 的旧文件，
        # 避免重复转存导致 (1)(2)(3) 自动改名堆积。
        target_fid = self._ensure_cloud_root()
        owner_key = re.sub(r"[\s\-_]+", "", self._sanitize_part(
            remote_dir_name or pwd_id or "")).lower()

        # 转存前清理：删掉云端属于该 Mod 的旧文件（防止 (1)(2)(3) 堆积）
        if owner_key:
            before_index = self._list_file_index(target_fid)
            old_fids = []
            for fname, items in before_index.items():
                if fname in own_fid:
                    # 自己网盘里已有的文件（本次要直接下载的）不清理，避免误删
                    continue
                stem = os.path.splitext(fname)[0]
                fkey = re.sub(r"[\s\-_]+", "", stem).lower()
                if owner_key and (fkey.startswith(owner_key) or owner_key in fkey):
                    old_fids.extend(i["fid"] for i in items)
            if old_fids:
                self.status_callback(f"正在清理云端旧文件（{len(old_fids)} 个）...", "info")
                try:
                    r = self.session.post(
                        "https://drive-pc.quark.cn/1/clouddrive/file/delete",
                        params={
                            "pr": "ucpro", "fr": "pc", "uc_param_str": "",
                            "__dt": _random_dt(), "__t": _timestamp13(),
                        },
                        json={"action_type": 2, "filelist": old_fids, "exclude_fids": []},
                        headers=self.base_headers,
                        timeout=self.timeout,
                    )
                    data = r.json()
                    tid = (data.get("data") or {}).get("task_id")
                    if tid:
                        self.poll_task(tid, delay=0.6, max_retry=20)
                    self.status_callback("云端旧文件已清理", "success")
                except Exception as e:  # noqa: BLE001
                    self.status_callback(f"云端旧文件清理失败（继续转存）：{e}", "warn")

        # 转存前快照：目录里已有的文件（清理后重新取，确保准确）
        before_index = self._list_file_index(target_fid)
        before_fids = {i["fid"] for items in before_index.values() for i in items}

        # 已存在且大小一致的同名文件可复用，不再重复转存（省时间也不堆重复文件）。
        # 安全前提：文件名必须"看起来属于本次这个 Mod"（平铺后目录里是各 Mod 混放，
        # 否则同名文件可能来自别的 Mod）。对不上就老老实实重新转存。
        def _belongs_to_this_mod(fname: str) -> bool:
            stem = os.path.splitext(fname)[0]
            key = re.sub(r"[\s\-_]+", "", stem).lower()
            return bool(owner_key) and (key.startswith(owner_key) or owner_key in key)

        to_save = []
        reused_fid = {}
        for t in targets:
            name = t["file_name"]
            size = int(t.get("size") or 0)
            if size and name in own_fid:
                # 网盘里已有该文件（自己的分享）：直接复用真实 fid，跳过转存
                reused_fid[name] = own_fid[name]
                continue
            hit = None
            # force_transfer：不做复用，全部重新转存（sha 校验失败后的自愈重试）
            if size and not force_transfer and _belongs_to_this_mod(name):
                for item in before_index.get(name, []):
                    if item["size"] == size:
                        hit = item["fid"]
                        break
            if hit:
                reused_fid[name] = hit
            else:
                to_save.append(t)

        if to_save:
            self.status_callback(
                f"正在转存到您的网盘「{self.CLOUD_ROOT_NAME}」（下载后保留）...",
                "info")
            task_id = self.save_share(
                pwd_id, stoken,
                [f["fid"] for f in to_save],
                [f["share_fid_token"] for f in to_save],
                to_pdir_fid=target_fid,
            )

            def _wait_tick(_n, _max):
                self.status_callback(
                    "正在转存到网盘…服务器仍在同步处理，请耐心等待", "info")
            self.poll_task(task_id, on_wait=_wait_tick)
            self.status_callback("转存完成，正在获取下载地址...", "success")
        else:
            self.status_callback("云端已存在相同文件，直接复用，无需重复转存", "success")

        # 定位本次要下载的文件：优先取"本次新转存进来"的 fid，避免取到旧的同名文件
        after_index = self._list_file_index(target_fid) if to_save else before_index
        save_names = {t["file_name"] for t in to_save}
        need_fids = []
        used_fids = set()      # 避免同一批里多个同名文件取到同一个 fid
        for t in targets:
            name = t["file_name"]
            fid = reused_fid.get(name)

            if fid is None:
                for item in after_index.get(name, []):
                    if (item["fid"] not in before_fids
                            and item["fid"] not in used_fids):
                        fid = item["fid"]
                        break

            if fid is None:
                # 兼容网盘对重复文件自动改名的情况（如 "X (1).zip"）：
                # 在本次新增的 fid 里找同后缀的同名派生文件
                stem, ext = os.path.splitext(name)
                for fname, items in after_index.items():
                    if fname == name or not fname.startswith(stem + " "):
                        continue
                    if ext and not fname.endswith(ext):
                        continue
                    for item in items:
                        if (item["fid"] not in before_fids
                                and item["fid"] not in used_fids):
                            fid = item["fid"]
                            break
                    if fid:
                        break

            if fid is None and name in save_names:
                # 我们确实发起了转存却没找到"新增"文件：
                # 可能是网盘"原地覆盖"——旧 fid 的大小已变成新文件的大小，
                # 这种情况内容就是新的，可以用；否则必须报错，绝不能静默用旧文件。
                size = int(t.get("size") or 0)
                if size:
                    for item in after_index.get(name, []):
                        if item["size"] == size:
                            fid = item["fid"]
                            break

            if fid is None and name not in save_names:
                # 未发起转存（走复用分支）时的兜底：目录里存在同名文件即可
                items = after_index.get(name) or []
                if items:
                    fid = items[0]["fid"]

            if not fid:
                if name in save_names:
                    raise QuarkError(
                        f"转存后未在网盘中找到新文件：{name}"
                        f"（云端未生成新条目，为避免装到旧版本已中止）")
                raise QuarkError(f"转存后未能在网盘目录中找到：{name}")
            used_fids.add(fid)
            need_fids.append(fid)

        url_map = {i["fid"]: i for i in self.get_download_urls(need_fids)}
        downloaded = []
        for t, fid in zip(targets, need_fids):
            info = url_map.get(fid)
            if not info or not info.get("download_url"):
                raise QuarkError(f"获取下载地址失败：{t['file_name']}")
            rel = t.get("rel_path") or ""
            dest_dir = os.path.join(local_dir, rel) if rel else local_dir
            self.status_callback(f"开始下载：{t['file_name']}", "info")
            # 用分享里的原始文件名保存（云端若被自动改名也不影响本地文件名）
            final_path = self.download_file(
                info["download_url"], os.path.join(dest_dir, t["file_name"]),
                expect_size=int(info.get("size") or t.get("size") or 0))
            downloaded.append(final_path)

        # 不再删除云端文件：平铺保留在「KnightModder」目录下，由用户自行清理
        self.status_callback(
            f"全部文件下载完成，云端文件已保留在网盘「{self.CLOUD_ROOT_NAME}」，"
            f"可自行清理", "success")
        result_dir = (os.path.join(local_dir, targets[0]["rel_path"])
                      if targets[0].get("rel_path") else local_dir)
        if return_files:
            return result_dir, downloaded
        return result_dir

    @staticmethod
    def _fmt_size(num):
        for unit in ("B", "KB", "MB", "GB"):
            if num < 1024:
                return f"{num:.0f}{unit}" if unit == "B" else f"{num:.1f}{unit}"
            num /= 1024
        return f"{num:.1f}TB"
