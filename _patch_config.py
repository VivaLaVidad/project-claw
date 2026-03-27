"""patch_config.py - 修复 config.py 的 signaling_ws_base_url 优先读 A2A_SIGNALING_URL"""
path = 'd:/桌面/Project Claw/config.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# 修复 signaling_ws_base_url: 若 A2A_SIGNALING_URL 有值，提取其 base 部分
old = '''    @property
    def signaling_ws_base_url(self) -> str:
        return f"{self.SIGNALING_WS_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"
'''
new = '''    @property
    def signaling_ws_base_url(self) -> str:
        # 若直接设置了 A2A_SIGNALING_URL，提取 base（scheme+host+port）
        if self.A2A_SIGNALING_URL:
            import re
            m = re.match(r"(wss?://[^/]+)", self.A2A_SIGNALING_URL)
            if m:
                return m.group(1)
        return f"{self.SIGNALING_WS_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"
'''
if old.strip() in c:
    c = c.replace(old, new, 1)
    print('OK: signaling_ws_base_url patched')
else:
    print('SKIP: pattern not found')

# 同样修复 signaling_http_base_url
old2 = '''    @property
    def signaling_http_base_url(self) -> str:
        return f"{self.SIGNALING_HTTP_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"
'''
new2 = '''    @property
    def signaling_http_base_url(self) -> str:
        # 若直接设置了 A2A_SIGNALING_URL，转换为 http base
        if self.A2A_SIGNALING_URL:
            import re
            m = re.match(r"(wss?://[^/]+)", self.A2A_SIGNALING_URL)
            if m:
                base = m.group(1).replace("wss://", "https://").replace("ws://", "http://")
                return base
        return f"{self.SIGNALING_HTTP_SCHEME}://{self.SIGNALING_HOST}:{self.SIGNALING_PORT}"
'''
if old2.strip() in c:
    c = c.replace(old2, new2, 1)
    print('OK: signaling_http_base_url patched')
else:
    print('SKIP: http base pattern not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print('Done: config.py patched')
