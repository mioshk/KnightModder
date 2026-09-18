# -*- coding: utf-8 -*-
"""UI 部件必须带父控件创建的回归测试。

背景（用户反馈的真实现象）：切换导航页时会闪过一个空白小方块。查下来是行内的
「待更新」按钮用 `QPushButton()`（无父控件）创建，紧接着 `_update_action_btn()`
里调了 `setVisible(True)` —— 那一刻它还没被 `addWidget`，Qt 就把它当成独立的顶层
窗口弹了出来。所以规则是：**无父控件创建 + addWidget 之前 setVisible(True) = 顶层
窗口闪现**。
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_FILES = ("ui/mod_page.py", "ui/main_window.py", "ui/settings_page.py",
            "ui/dialogs.py", "ui/update_checker.py")
PARENTLESS = re.compile(r"=\s*(QPushButton|QLabel|QFrame|QWidget)\(\)")


class WidgetParentTests(unittest.TestCase):
    @staticmethod
    def _src(rel):
        with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
            return f.read()

    def test_row_action_widgets_have_parent(self):
        """行内的「待更新」按钮与动作图标必须带 parent 创建"""
        src = self._src("ui/mod_page.py")
        self.assertNotIn("self.action_btn = QPushButton()", src,
                         "action_btn 无父控件创建，setVisible(True) 时会闪现顶层窗口")
        self.assertIn("self.action_btn = QPushButton(self)", src)
        self.assertIn("lbl = QLabel(self)", src)

    def test_no_setvisible_before_parenting(self):
        """无父控件创建的部件，在 addWidget 之前不能 setVisible(True)"""
        problems = []
        for rel in UI_FILES:
            lines = self._src(rel).splitlines()
            for i, line in enumerate(lines):
                m = PARENTLESS.search(line)
                if not m:
                    continue
                var = line.split("=")[0].strip()
                # 看创建之后的若干行里，addWidget 之前有没有 setVisible(True)
                after = "\n".join(lines[i + 1:i + 41])
                before_add = after.split("addWidget", 1)[0]
                if f"{var}.setVisible(True)" in before_add:
                    problems.append(f"{rel}:{i + 1} 变量 {var}")
        self.assertEqual([], problems,
                         "这些部件无父控件就被 setVisible(True)，会闪现成顶层窗口："
                         + "；".join(problems))


if __name__ == "__main__":
    unittest.main()
