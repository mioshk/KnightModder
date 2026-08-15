# -*- coding: utf-8 -*-
"""检查更新 - 夸克网盘分发（防双弹窗版）"""
import io
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap, QFont, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QProgressBar, QWidget, QScrollArea,
)
from config import APP_VERSION, UPDATE_CHECK_URL
from utils.common import safe_requests_get, get_asset_path


# ==================== 全局状态 ====================
# True = 当前正在检查更新（防止自动 + 手动同时请求）
_update_lock = False


# ============================================================
# 后台线程：请求更新接口
# ============================================================
class UpdateChecker(QThread):
    finished = Signal(bool, dict, str)

    def __init__(self):
        super().__init__()
        self.url = UPDATE_CHECK_URL

    def run(self):
        import requests  # 延迟导入
        from packaging.version import parse as parse_version  # 延迟导入
        try:
            r = safe_requests_get(self.url, timeout=10)
            if r.status_code != 200:
                self.finished.emit(False, {}, f"HTTP {r.status_code}")
                return
            data = r.json()
            ver = data.get('version', '')
            if not ver:
                self.finished.emit(False, {}, "版本信息格式错误")
                return
            has = parse_version(ver) > parse_version(APP_VERSION)
            self.finished.emit(has, data, "")
        except Exception as e:
            self.finished.emit(False, {}, str(e))


# ============================================================
# 更新弹窗（你的原 UI，一字未改）
# ============================================================
class UpdateDialog(QDialog):
    def __init__(self, version_info, parent=None):
        super().__init__(parent)
        self.version_info = version_info
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("发现新版本")
        self.setWindowIcon(QIcon(get_asset_path("icon.ico")))
        self.setMinimumSize(420, 500)
        self.setStyleSheet("QDialog{background-color:#1a1a1a;}")

        main = QVBoxLayout(self)
        main.setContentsMargins(28, 24, 28, 24)
        main.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # 标题
        trow = QHBoxLayout()
        ic = QLabel("🎉")
        ic.setStyleSheet("font-size:30px;background:transparent;")
        trow.addWidget(ic)
        t = QLabel(f"发现新版本 v{self.version_info.get('version','')}")
        t.setFont(QFont("Microsoft YaHei", 17, QFont.Bold))
        t.setStyleSheet("color:#34c759;background:transparent;")
        trow.addWidget(t)
        trow.addStretch()
        layout.addLayout(trow)

        # 版本信息
        for lbl, val, clr in [
            ("当前版本：", f"v{APP_VERSION}", "#cccccc"),
            ("新版本：", f"v{self.version_info.get('version','')} ⭐", "#34c759"),
        ]:
            r = QHBoxLayout()
            a = QLabel(lbl)
            a.setStyleSheet("color:#888;font-size:13px;background:transparent;")
            b = QLabel(val)
            b.setStyleSheet(f"color:{clr};font-size:13px;font-weight:600;background:transparent;")
            r.addWidget(a)
            r.addWidget(b)
            r.addStretch()
            layout.addLayout(r)

        rd = self.version_info.get('release_date', '')
        if rd:
            r = QHBoxLayout()
            x = QLabel(f"📅 发布日期：{rd}")
            x.setStyleSheet("color:#888;font-size:12px;background:transparent;")
            r.addWidget(x)
            r.addStretch()
            layout.addLayout(r)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#333;max-height:1px;border:none;")
        layout.addWidget(sep)

        # 更新内容（不滚动）
        ct = QLabel("📋 更新内容")
        ct.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        ct.setStyleSheet("color:#aaa;background:transparent;margin-top:6px;")
        layout.addWidget(ct)

        text = self.version_info.get('changelog', '暂无更新日志')
        if '\n' in text and not text.startswith('-'):
            text = '\n'.join(f'- {l.strip()}' for l in text.split('\n') if l.strip())

        cl = QLabel(text)
        cl.setWordWrap(True)
        cl.setTextFormat(Qt.PlainText)
        cl.setStyleSheet("""
            QLabel{
                background:#1e1e1e;
                color:#ccc;
                border:1px solid #333;
                border-radius:8px;
                padding:12px 14px;
                font-size:13px;
                line-height:1.8;
            }
        """)
        layout.addWidget(cl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background:#333;max-height:1px;border:none;")
        layout.addWidget(sep2)

        # 下载提示
        dt = QLabel("📥 下载新版本")
        dt.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        dt.setStyleSheet("color:#aaa;background:transparent;")
        layout.addWidget(dt)

        dd = QLabel("请打开手机「夸克网盘」扫码，转存后用电脑下载")
        dd.setStyleSheet("color:#888;font-size:12px;background:transparent;")
        layout.addWidget(dd)

        # 二维码
        qw = QWidget()
        qw.setStyleSheet("QWidget{background:#fff;border-radius:12px;}")
        ql = QVBoxLayout(qw)
        ql.setContentsMargins(20, 20, 20, 20)
        qr_lbl = QLabel()
        qr_lbl.setAlignment(Qt.AlignCenter)
        pix = self._gen_qrcode()
        if pix:
            qr_lbl.setPixmap(pix.scaled(
                240, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        else:
            qr_lbl.setText("⚠️ 无法生成二维码")
        ql.addWidget(qr_lbl)
        layout.addWidget(qw)

        # 关闭按钮
        br = QHBoxLayout()
        br.addStretch()
        btn = QPushButton("关闭")
        btn.setObjectName("btnSecondary")
        btn.clicked.connect(self.reject)
        btn.setFixedHeight(32)
        br.addWidget(btn)
        br.addStretch()
        layout.addLayout(br)

        scroll.setWidget(content)
        main.addWidget(scroll)

    def _gen_qrcode(self):
        import qrcode  # 延迟导入
        try:
            link = self.version_info.get('quark_link', '')
            if not link:
                return None
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=6,
                border=2,
            )
            qr.add_data(link)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            p = QPixmap()
            p.loadFromData(buf.read())
            return p
        except Exception:
            return None


# ============================================================
# 手动检查更新（菜单 / 按钮）
# ============================================================
def check_for_updates(parent=None, show_no_update=False):
    global _update_lock
    if _update_lock:
        if show_no_update:
            QMessageBox.information(
                parent, "检查更新", "正在检查更新中，请稍候..."
            )
        return

    dlg = QDialog(parent)
    dlg.setWindowTitle("检查更新")
    dlg.setFixedSize(380, 120)
    dlg.setStyleSheet("""
        QDialog{background:#1a1a1a;}
        QLabel{color:#ccc;}
    """)

    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(30, 20, 30, 20)
    lay.setSpacing(12)

    lbl = QLabel("正在检查更新...")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFont(QFont("Microsoft YaHei", 13))
    lay.addWidget(lbl)

    pb = QProgressBar()
    pb.setRange(0, 0)
    pb.setStyleSheet("""
        QProgressBar{
            border:none;
            background:#333;
            border-radius:4px;
            height:4px;
        }
        QProgressBar::chunk{
            background:#34c759;
            border-radius:4px;
        }
    """)
    lay.addWidget(pb)

    chk = UpdateChecker()

    def done(has, info, err):
        global _update_lock
        _update_lock = False
        dlg.accept()
        if has:
            UpdateDialog(info, parent).exec()
        elif show_no_update:
            msg = f"✅ 已是最新版本！\nv{APP_VERSION}"
            if err:
                msg = f"⚠️ {err}"
            QMessageBox.information(parent, "检查更新", msg)

    chk.finished.connect(done)
    chk.start()
    _update_lock = True
    dlg.exec()


# ============================================================
# ✅ 启动自动检测更新（main.py 调用）
# ============================================================
def auto_check_for_updates(parent=None):
    global _update_lock
    if _update_lock:
        return  # 正在检查中，自动检查直接放弃

    _update_lock = True
    chk = UpdateChecker()

    def done(has, info, err):
        global _update_lock
        _update_lock = False
        if has:
            UpdateDialog(info, parent).exec()

    chk.finished.connect(done)
    chk.start()
    setattr(auto_check_for_updates, '_ref', chk)


def schedule_auto_check(parent=None, delay_ms=3000):
    """延迟启动，避免阻塞主界面初始化"""
    QTimer.singleShot(delay_ms, lambda: auto_check_for_updates(parent))