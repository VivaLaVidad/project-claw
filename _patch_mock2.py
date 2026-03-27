path='d:/桌面/Project Claw/mock_client.html'
with open(path,encoding='utf-8') as f:
    c=f.read()

c=c.replace('demoMode=false,','demoMode=__LIVE__,',1) # placeholder
c=c.replace('demoMode=true,','demoMode=false,',1)
c=c.replace('demoMode=__LIVE__,','demoMode=false,',1)

# swap active class between mock/live buttons
old_mock = 'class="chip-btn active" id="modeMock"'
new_mock = 'class="chip-btn" id="modeMock"'
old_live = 'class="chip-btn" id="modeLive"'
new_live = 'class="chip-btn active" id="modeLive"'
if old_mock in c:
    c=c.replace(old_mock, new_mock, 1)
    c=c.replace(old_live, new_live, 1)
    print('OK: buttons swapped')
else:
    print('SKIP: buttons not found (may already be correct)')

with open(path,'w',encoding='utf-8') as f:
    f.write(c)
print('OK: mock_client.html patched - default real mode')
