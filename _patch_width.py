import re
path = 'd:/桌面/Project Claw/god_mode_dashboard.py'
with open(path, encoding='utf-8') as f:
    c = f.read()

before = c.count('use_container_width')
c = c.replace('use_container_width=True', "width='stretch'")
c = c.replace('use_container_width=False', "width='content'")
after = c.count('use_container_width')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print(f'OK: replaced {before - after} occurrences, {after} remaining')
