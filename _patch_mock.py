path = 'd:/桌面/Project Claw/mock_client.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 默认切换为真实模式（先尝试真实，失败自动降级演示）
changes = 0

# 把 demoMode 默认值改为 false（真实模式优先）
if 'let demoMode    = true;' in content:
    content = content.replace('let demoMode    = true;', 'let demoMode    = false; // 默认真实模式，离线自动降级', 1)
    changes += 1
    print('OK: demoMode default -> false')
elif "let demoMode=true;" in content:
    content = content.replace('let demoMode=true;', 'let demoMode=false;', 1)
    changes += 1
    print('OK: demoMode default -> false (compact)')
else:
    print('SKIP: demoMode pattern not found')

# 把 modeMock active -> modeLive active
if "'modeMock'" in content or '"modeMock"' in content:
    # chip button initial active state
    old = "class=\"chip-btn active\" id=\"modeMock\""
    new = "class=\"chip-btn\" id=\"modeMock\""
    old2 = "class=\"chip-btn\" id=\"modeLive\""
    new2 = "class=\"chip-btn active\" id=\"modeLive\""
    if old in content:
        content = content.replace(old, new, 1)
        content = content.replace(old2, new2, 1)
        changes += 1
        print('OK: modeLive set as default active')
    else:
        print('SKIP: chip button pattern not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Done. {changes} changes.')
