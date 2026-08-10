from pathlib import Path
p = Path('ui/mod_page.py')
t = p.read_text(encoding='utf-8')
old = '''    # ---------- 右下角提示相关 ----------
    def eventFilter(self, obj, event):
        if obj == self.detail_scroll.parent() and event.type() == event.Type.Resize:
            self._reposition_copy_tip()
            return True
        if obj == self.mod_list.viewport() and event.type() == QEvent.MouseButtonPress:
            item = self.mod_list.itemAt(event.pos())
            if item is None:
                self._clear_selection()
                return True
        return super().eventFilter(obj, event)
'''
new = '''    # ---------- 右下角提示相关 ----------
    def eventFilter(self, obj, event):
        if hasattr(self, 'detail_scroll') and obj == self.detail_scroll.parent() and event.type() == event.Type.Resize:
            self._reposition_copy_tip()
            return True
        if obj == self.mod_list.viewport() and event.type() == QEvent.MouseButtonPress:
            item = self.mod_list.itemAt(event.pos())
            if item is None:
                self._clear_selection()
                return True
        return super().eventFilter(obj, event)
'''
cnt = t.count(old)
print('occurrences =', cnt)
if cnt == 0:
    raise SystemExit('old block not found')
if cnt > 2:
    raise SystemExit('unexpected occurrences count: {}'.format(cnt))
t = t.replace(old, new, 2)
p.write_text(t, encoding='utf-8')
print('patched', cnt, 'occurrences')
