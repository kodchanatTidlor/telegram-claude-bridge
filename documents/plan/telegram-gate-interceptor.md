# Plan: Telegram Gate Interceptor

ควบคุม permission prompt + AskUserQuestion จาก Telegram (ข้ามเมนู TUI)

## ปัญหา
- permission prompt + AskUserQuestion เป็นเมนู TUI (ลูกศร/keypress) → inject text ตอบไม่ชัวร์
- Telegram ยอม getUpdates poller เดียว/บอท → hook โทร getUpdates เองไม่ได้ (409) → ต้อง IPC ผ่าน listener

## กลไก
`PreToolUse` hook (`gate_hook.py`) บล็อกรอคำตอบจาก Telegram แล้วคืน decision:
- **permission tools** (Bash/Write/Edit) → `permissionDecision: allow|deny` (official, สะอาด)
- **AskUserQuestion** → `deny` + reason ที่ยัดคำตอบ + สั่งไม่ถามซ้ำ**คำถามนี้** (hack เพราะไม่มี field ตอบคำถาม)

## Remote switch
gate ทำงานเฉพาะเมื่อ `.remote` flag เปิด (เพราะ listener รันตอนอยู่หน้าเครื่องด้วย). ปิด = local ปกติ ไม่ขวาง.
`bridgectl.py remote on|off|status` toggle.

## IPC (file-based, 1 ไฟล์/คำขอ กัน race)
- `.gate/pending/<message_id>.json` — hook เขียน, listener อ่าน+ลบ
- `.gate/answer/<message_id>.json`  — listener เขียน (raw reply text), hook อ่าน+ลบ
- correlation = message_id ของข้อความ gate ที่ส่งเข้า Telegram (user reply ถึงข้อความนั้น)
- pending เก่าเกิน max-age → listener/hook ล้างทิ้ง

## Flow
1. PreToolUse ยิง → ถ้า remote off / listener down / tool ไม่เข้าเงื่อนไข → passthrough (ไม่ output → เมนู local ปกติ)
2. hook ส่ง Telegram (sendMessage ไม่ใช่ poller ไม่ชน 409) ได้ message_id
3. hook `register_pending(mid, {kind})`
4. hook poll `answer/<mid>` จน timeout (~540s, < hook timeout 600s)
5. listener loop เห็น reply→pending mid → เขียน answer text + ลบ pending + ไม่ inject
6. hook อ่าน answer → ตีความ → คืน decision JSON; timeout → passthrough (fallback เมนู local)

## ตีความคำตอบ (hook ถือ tool_input, listener เก็บแค่ raw text)
- permission: y/yes/1/ok → allow; n/no/2/free-text → deny (free text → reason ป้อน Claude)
- question: เลข → option[n-1]; ตรง label → label นั้น; อื่น → custom ("Other")

## ไฟล์
- `bridge/config.py` — เพิ่ม `remote_path`, `gate_dir`
- `bridge/gate.py` (ใหม่) — pure: paths, register/resolve/take/clear pending+answer, is_remote, interpret_*, build_*
- `gate_hook.py` (ใหม่) — PreToolUse entry (orchestrate + คืน decision JSON)
- `listener.py` — route reply→pending ก่อน inject
- `bridgectl.py` — `remote` command
- settings.json — PreToolUse matcher `Bash|Write|Edit|AskUserQuestion` + `timeout: 600`; เลิกใช้ `ask_hook.py`
- ลบ `ask_hook.py` + test (gate_hook คุมแทน)
- tests: gate logic, gate_hook (mock send + wait), listener routing

## Fallback / safety
- timeout → passthrough → เมนู TUI local โผล่ตามปกติ (ไม่ค้าง)
- hook ทุกตัว gate ด้วย listener-alive + จับ exception → ไม่ block Claude
- default permission เมื่อกำกวม = deny (ปลอดภัย)
