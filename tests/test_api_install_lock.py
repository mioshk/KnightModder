# -*- coding: utf-8 -*-
"""API 安装/还原的并发保护测试。

背景（真实事故）：用户点了「安装 API」后几秒内界面没有任何输出，以为没生效又
点了两下 —— 于是三个线程同时跑 install_api，抢同一个 .part 临时文件，报
[WinError 5] 拒绝访问，最后还弹出一个"安装失败"。核心层必须自己挡住并发，
不能只依赖 UI 禁按钮。
"""
import threading
import unittest
from unittest import mock


class ApiInstallLockTests(unittest.TestCase):
    def tearDown(self):
        # 万一某个用例没释放干净，别污染后面的用例
        from core import installer
        if installer._API_LOCK.locked():
            installer._API_LOCK.release()

    def test_second_concurrent_call_is_rejected(self):
        from core import installer
        started = threading.Event()
        release = threading.Event()

        def slow(*_a, **_kw):
            started.set()
            release.wait(5)
            return {}

        with mock.patch.object(installer, "_install_api_locked", side_effect=slow):
            t = threading.Thread(target=lambda: installer.install_api("dummy"))
            t.start()
            self.assertTrue(started.wait(5), "首个任务没能启动")
            with self.assertRaises(RuntimeError) as ctx:
                installer.install_api("dummy")
            self.assertIn("进行中", str(ctx.exception))
            release.set()
            t.join(5)

    def test_lock_released_after_success(self):
        """成功后锁必须还回来，否则这台机器上再也装不了 API"""
        from core import installer
        with mock.patch.object(installer, "_install_api_locked", return_value={}):
            installer.install_api("dummy")
            installer.install_api("dummy")  # 不应报错

    def test_lock_released_after_failure(self):
        from core import installer
        with mock.patch.object(installer, "_install_api_locked",
                               side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                installer.install_api("dummy")
        with mock.patch.object(installer, "_install_api_locked", return_value={}):
            installer.install_api("dummy")  # 失败后仍能再来一次

    def test_install_and_restore_share_the_lock(self):
        """安装与还原动的是同一批 dll，不能同时跑"""
        from core import installer
        started = threading.Event()
        release = threading.Event()

        def slow(*_a, **_kw):
            started.set()
            release.wait(5)
            return {}

        with mock.patch.object(installer, "_install_api_locked", side_effect=slow):
            t = threading.Thread(target=lambda: installer.install_api("dummy"))
            t.start()
            self.assertTrue(started.wait(5))
            with self.assertRaises(RuntimeError):
                installer.restore_vanilla("dummy")
            release.set()
            t.join(5)


if __name__ == "__main__":
    unittest.main()
