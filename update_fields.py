with open(r'd:\桌面\Project Claw\lobster_mvp.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 修改多维表格字段名为正确的
old_payload = '''        payload = {
            "records": [
                {
                    "fields": {
                        "用户输入": user_input,
                        "龙虾回复": assistant_reply
                    }
                }
            ]
        }'''

new_payload = '''        payload = {
            "records": [
                {
                    "fields": {
                        "用户消息 / User": user_input,
                        "龙虾回复 / Assistant": assistant_reply,
                        "场景分类": "点单接单",
                        "处理状态": "待清洗"
                    }
                }
            ]
        }'''

content = content.replace(old_payload, new_payload)

with open(r'd:\桌面\Project Claw\lobster_mvp.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 多维表格字段已更新为:")
print("  - 用户消息 / User")
print("  - 龙虾回复 / Assistant")
print("  - 场景分类")
print("  - 处理状态")
