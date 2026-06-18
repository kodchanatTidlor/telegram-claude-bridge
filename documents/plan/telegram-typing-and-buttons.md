# Plan: Typing indicator + inline keyboard buttons

## Feature 1 — typing while working (replaces "waiting for input")
- typing เด้งขณะ Claude ทำงาน; หาย = ตาผู้ใช้ → เลิกส่งข้อความ "⏸ waiting for input"
- busy-flag (`.busy`, mtime = ts) + listener ส่ง `sendChatAction typing` ทุก ~4s ขณะ busy
- ลบ `notify_hook.py` (Notification → แค่ clear busy)
- `busy_hook.py` (ใหม่) อ่าน `hook_event_name`:
  - SET: UserPromptSubmit, PostToolUse
  - CLEAR: Stop, SubagentStop, Notification
  - gate ใต้ wait: clear busy เอง (ตาผู้ใช้ตอบ permission → typing ดับ)
- staleness guard: is_busy = flag fresh < 15 นาที (กัน crash ค้าง); PostToolUse touch ต่ออายุ
- listener: asyncio task แยก ping typing ขนาน poll loop

## Feature 2 — inline keyboard
- gate ส่งข้อความพร้อมปุ่ม:
  - permission: ✅ Allow (cb `y`) / ❌ Deny (cb `n`)
  - question: ปุ่มต่อ option, cb = เลข 1-based
- callback_data วิ่งผ่าน `interpret_permission`/`interpret_question` เดิม (เลข/y/n) → ไม่ต้องแก้ตีความ
- text reply ยังตอบได้คู่กัน
- listener: `handle_callback` รับ `callback_query` → resolve_pending(message_id, data) → answerCallbackQuery (เคลียร์ spinner) → editMessageReplyMarkup ล้างปุ่มกันกดซ้ำ; เช็ก allowlist
- telegram.py: send_message รับ `reply_markup`; เพิ่ม `send_chat_action`, `answer_callback`, `edit_reply_markup`

## ไฟล์
- bridge/telegram.py — reply_markup + 3 method
- bridge/busy.py (ใหม่) — set/clear/is_busy + staleness
- bridge/gate.py — permission_keyboard, question_keyboard
- bridge/config.py — busy_path
- gate_hook.py — ส่งพร้อม keyboard + clear busy ก่อน wait
- listener.py — handle_callback + typing task
- busy_hook.py (ใหม่); ลบ notify_hook.py + test
- settings.json — busy_hook wired to 5 events; Notification เลิกเรียก notify_hook
- tests: busy, gate keyboards, telegram methods, listener callback

## Fallback/safety
- listener down → ไม่มี typing (เหมือนเดิม), busy_hook skip
- callback allowlist เช็ก; ปุ่มถูกกด→ล้าง กันกดซ้ำ
- text + button = ทางตอบคู่ ทั้งคู่ลง answer file เดียวกัน
