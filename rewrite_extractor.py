from pathlib import Path

path = Path(r'd:\桌面\Project Claw\lobster_mvp.py')
text = path.read_text(encoding='utf-8')

if 'import re' not in text:
    text = text.replace('import hashlib\nimport threading', 'import hashlib\nimport threading\nimport re')

marker = 'class FeishuSync:'
insert_block = '''class MessageExtractor:\n    \"\"\"工业级最新用户消息提取器\"\"\"\n\n    UI_KEYWORDS = {\"发送\", \"表情\", \"语音\", \"微信\", \"限制\", \"下午\", \"上午\", \"拍摄\", \"相册\", \"位置\", \"视频通话\", \"通话\"}\n\n    def clean_text(self, text: str) -> str:\n        text = text.replace(\"\\n\", \" \').replace(\"\\r\", \" \').strip()\n        text = re.sub(r\"\\s+\", \" \", text)\n        return text\n\n    def is_noise_text(self, text: str) -> bool:\n        if not text:\n            return True\n        if text in self.UI_KEYWORDS:\n            return True\n        if any(k in text for k in self.UI_KEYWORDS):\n            return True\n        if re.fullmatch(r\"\\d{1,2}[:：.]\\d{2}\", text):\n            return True\n        if len(text) == 1 and not re.search(r\"[\\u4e00-\\u9fffA-Za-z0-9]\", text):\n            return True\n        if re.fullmatch(r\"[^\\u4e00-\\u9fffA-Za-z0-9]+\", text):\n            return True\n        if len(text) <= 2 and text.isdigit():\n            return True\n        return False\n\n    def bbox_bottom(self, bbox):\n        ys = [p[1] for p in bbox]\n        return max(ys)\n\n    def extract_latest_user_message(self, results, crop_left, crop_top, full_img, bubble_detector):\n        candidates = []\n        for (bbox, text, prob) in results:\n            text = self.clean_text(text)\n            if self.is_noise_text(text):\n                continue\n            mapped_bbox = [[p[0] + crop_left, p[1] + crop_top] for p in bbox]\n            if not bubble_detector.is_user_message(mapped_bbox, full_img):\n                continue\n            candidates.append({\n                \"text\": text,\n                \"bbox\": mapped_bbox,\n                \"bottom\": self.bbox_bottom(mapped_bbox),\n                \"prob\": prob,\n            })\n\n        if not candidates:\n            return \"\"\n\n        candidates.sort(key=lambda x: (x[\"bottom\"], x[\"prob\"]), reverse=True)\n        return candidates[0][\"text\"]\n\n\n'''

if 'class MessageExtractor:' not in text:
    text = text.replace(marker, insert_block + marker)

text = text.replace('    dedup = MessageDedup(window_size=30, time_window_sec=60)\n    bubble_detector = BubbleDetector()', '    dedup = MessageDedup(window_size=30, time_window_sec=60)\n    bubble_detector = BubbleDetector()\n    message_extractor = MessageExtractor()')

old_block = '''            chat_msg = ""\n            for (bbox, text, prob) in reversed(results):\n                if len(text.strip()) < 1:\n                    continue\n                if any(bad in text for bad in ["发送", "表情", "语音", "微信", "限制", "下午", "上午"]):\n                    continue\n                mapped_bbox = [[p[0] + crop_left, p[1] + crop_top] for p in bbox]\n                if not bubble_detector.is_user_message(mapped_bbox, img):\n                    logger.debug(f"🚫 过滤龙虾回复: {text}")\n                    stats["filtered"] += 1\n                    continue\n                chat_msg = text.strip()\n                break'''

new_block = '''            try:\n                chat_msg = message_extractor.extract_latest_user_message(\n                    results=results,\n                    crop_left=crop_left,\n                    crop_top=crop_top,\n                    full_img=img,\n                    bubble_detector=bubble_detector\n                )\n            except Exception as e:\n                logger.error(f"❌ 消息提取异常: {e}")\n                chat_msg = \"\"'''

text = text.replace(old_block, new_block)
path.write_text(text, encoding='utf-8')
print('industrial extraction updated')
