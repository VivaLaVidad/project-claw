from pathlib import Path

path = Path(r'd:\桌面\Project Claw\lobster_mvp.py')
text = path.read_text(encoding='utf-8')

old = '''    logger.info(f"📱 屏幕分辨率: {w}x{h}")
    logger.info("👁️ 开始监听消息（已启用气泡识别）...")

    while True:
        try:
            img_path = "current_screen.png"
            d.screenshot(img_path)
            img = cv2.imread(img_path)
            results = reader.readtext(img_path, detail=1)

            chat_msg = ""
            for (bbox, text, prob) in reversed(results):
                if len(text.strip()) < 1:
                    continue
                if any(bad in text for bad in ["发送", "表情", "语音", "微信", "限制", "下午", "上午"]):
                    continue
                if not bubble_detector.is_user_message(bbox, img):
                    logger.debug(f"🚫 过滤龙虾回复: {text}")
                    stats["filtered"] += 1
                    continue
                chat_msg = text.strip()
                break

            if chat_msg:
                if dedup.is_duplicate(chat_msg):'''

new = '''    logger.info(f"📱 屏幕分辨率: {w}x{h}")
    logger.info("👁️ 开始监听消息（已启用气泡识别）...")

    # OCR 只识别聊天主体区域，减少全屏识别延迟
    crop_top = int(h * 0.15)
    crop_bottom = int(h * 0.82)
    crop_left = int(w * 0.05)
    crop_right = int(w * 0.95)

    while True:
        try:
            img_path = "current_screen.png"
            crop_path = "chat_crop.png"
            d.screenshot(img_path)
            img = cv2.imread(img_path)
            crop_img = img[crop_top:crop_bottom, crop_left:crop_right]
            cv2.imwrite(crop_path, crop_img)
            results = reader.readtext(crop_path, detail=1)

            chat_msg = ""
            for (bbox, text, prob) in reversed(results):
                if len(text.strip()) < 1:
                    continue
                if any(bad in text for bad in ["发送", "表情", "语音", "微信", "限制", "下午", "上午"]):
                    continue
                mapped_bbox = [[p[0] + crop_left, p[1] + crop_top] for p in bbox]
                if not bubble_detector.is_user_message(mapped_bbox, img):
                    logger.debug(f"🚫 过滤龙虾回复: {text}")
                    stats["filtered"] += 1
                    continue
                chat_msg = text.strip()
                break

            if chat_msg:
                if dedup.is_duplicate(chat_msg):'''

if old not in text:
    raise SystemExit('target block not found')

text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('localized OCR updated')
