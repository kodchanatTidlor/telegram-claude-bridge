# Telegram ↔ Claude Code Bridge

คุม Claude Code ที่รันใน iTerm2 จาก Telegram — เห็นสิ่งที่ Claude พูดสดๆ,
อนุมัติ permission / ตอบคำถาม ด้วยปุ่มกด, สั่งงานต่อ, เปิด session ใหม่
ทั้งหมดจากมือถือ

ใช้ตอน AFK — ไม่ต้องนั่งเฝ้า terminal

---

## ✨ What's New

อัปเดตใหญ่ จาก "recap ตอนจบ" → **คุม Claude แบบ interactive เต็มตัว**

- **Live mirror** — ข้อความที่ Claude พูดถูกส่งเข้า Telegram สดๆ ระหว่างทาง (ไม่ใช่แค่ตอนจบ) แสดงผลเป็น **markdown** สวยงาม (หัวข้อ/ตัวหนา/โค้ด/ลิสต์)
- **Typing indicator** — ขึ้น "typing…" ตอน Claude กำลังทำงาน; หายเมื่อถึงตาคุณ (แทนข้อความ "waiting for input")
- **Permission gate** — เวลา Claude ขอรัน Bash/แก้ไฟล์ → เด้งเข้า Telegram พร้อมปุ่ม **✅ Allow / ❌ Deny**
- **AskUserQuestion** — คำถามของ Claude เด้งมาพร้อม **ปุ่มเลือก** ตอบจากมือถือได้
- **`/status` dashboard** — ดู model, session ที่ active, prompt ค้าง + ปุ่ม refresh / สลับ session / **เปิด Claude session ใหม่**
- **`/cancel`** — หยุด Claude กลางคัน (ส่ง ESC)
- **Tool activity** — ขึ้นบรรทัดบอกว่ากำลัง editing/running/searching แล้วลบเมื่อเสร็จ (เงียบ ไม่ ping)
- **เสียงเฉพาะตอนสำคัญ** — ระหว่างทางเงียบ, ping เฉพาะคำตอบปิดเทิร์น
- **จัดการ session** — auto-follow session ล่าสุด, reply เจาะ session เก่าได้, prune session ที่ปิด/ออกไปแล้วอัตโนมัติ

> ⚠️ อัปเกรดจากเวอร์ชันเก่า: `recap_hook.py` ถูกแทนด้วยหลาย hook — ดูหัวข้อ
> "ลง Claude Code hooks" แล้วแทนที่ของเดิม

---

## เตรียมก่อนเริ่ม — Bot Token + Chat ID

ต้องมี 2 ค่านี้ก่อน (ทั้ง TL;DR และแบบ manual ใช้)

### 1. สร้าง Telegram Bot เพื่อเอา Token
1. เปิด Telegram คุยกับ **@BotFather**
<img width="434" height="86" alt="S__21749764_0" src="https://github.com/user-attachments/assets/17c48126-52de-4fb5-a25c-93cd95299164" />

2. พิมพ์ `/newbot`
3. ตั้งชื่อ bot และ username (ลงท้าย `bot`)
4. BotFather จะส่ง **token** กลับมา หน้าตาเช่น `123456789:ABCdef...` → เก็บไว้
5. (แนะนำ) พิมพ์ `/setprivacy` → เลือก bot → **Enable** เพื่อให้ bot อ่านเฉพาะข้อความที่ส่งถึงมันโดยตรง

### 2. หา Chat ID ของตัวเอง
คุยกับ **@userinfobot** ใน Telegram → มันบอก `Id` ของคุณ (ตัวเลขล้วน) = chat id

<img width="436" height="68" alt="S__21749765_0" src="https://github.com/user-attachments/assets/336a6d86-3eee-4ba4-8446-65903746fdba" />


### 3. กด Start บอทที่เพิ่งสร้าง (สำคัญ)
เปิดแชตกับ bot ของคุณ กด **Start** 1 ครั้ง — จำเป็น เพราะ Telegram ไม่ยอมให้ bot
ส่งข้อความหาคุณ ถ้าคุณยังไม่เคยเริ่มแชทกับมัน
> หมายเหตุ: ขั้นนี้คนละเรื่องกับการหา chat id — @userinfobot ในขั้น 2 ไม่ต้องยุ่งกับบอทที่สร้าง

---

## TL;DR — ก็อป prompt นี้ไปวางใน Claude Code แล้วมันจะ setup ให้จนจบ

> ช่วย setup telegram-claude-bridge ที่ `~/telegram-claude-bridge` ให้ใช้งานได้จนจบ ตามขั้นตอนนี้ ทำทีละขั้นและถามผมเมื่อต้องการข้อมูล:
>
> 1. Clone repo ไปที่ `~/telegram-claude-bridge` (ถ้ายังไม่มี): `git clone https://github.com/kodchanatTidlor/telegram-claude-bridge.git ~/telegram-claude-bridge`
> 2. เช็กว่ามี Python 3.9+ ในเครื่องหรือยัง (`python3 --version`) ถ้าไม่มี ให้ติดตั้งด้วย `brew install python` (ต้องมี Homebrew ก่อน — https://brew.sh)
> 3. เช็กว่ามี iTerm2 ติดตั้งหรือยัง (`ls /Applications/iTerm.app` หรือ `brew list --cask iterm2`) ถ้าไม่มี ให้ติดตั้งด้วย `brew install --cask iterm2`
> 4. เข้าโฟลเดอร์ `~/telegram-claude-bridge` สร้าง venv และลง dependency: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
> 5. ถามผมขอ **Telegram Bot Token** กับ **Chat ID** (วิธีหาอยู่ในหัวข้อ "เตรียมก่อนเริ่ม" ของ README) แล้วสร้างไฟล์ `.env` จาก `.env.example` ใส่ค่า `BOT_TOKEN` และ `ALLOWED_CHAT_ID` (ห้าม commit ไฟล์นี้)
> 6. ลง hooks แบบ user scope ใน `~/.claude/settings.json` ตามบล็อก JSON ในหัวข้อ "ลง Claude Code hooks" ของ README (merge เข้า `hooks` เดิม อย่าทับ; ถ้า event ไหนมีอยู่แล้วให้ append เข้า array). ทุก command ใช้ venv python: `$HOME/telegram-claude-bridge/.venv/bin/python`
> 7. บอกผมให้เปิด iTerm2 Python API เอง (Settings → General → Magic → Enable Python API) เพราะต้องกดใน GUI และให้กด Start บอทใน Telegram เอง
> 8. รัน `python3 ~/telegram-claude-bridge/bridgectl.py status` เช็กความพร้อม แล้วบอกผมว่าต้องรัน `python3 ~/telegram-claude-bridge/bridgectl.py serve` ใน iTerm2 เพื่อเริ่มใช้งาน (และ restart Claude Code ให้โหลด hooks ใหม่)
>
> ทำตามทีละขั้น เช็กผลแต่ละขั้นก่อนไปต่อ

---

## ติดตั้งแบบ manual (ถ้าไม่ใช้ TL;DR)

ทำหัวข้อ "เตรียมก่อนเริ่ม" ด้านบนให้เสร็จก่อน (Token + Chat ID + กด Start)

### 1. ติดตั้ง iTerm2 (ถ้ายังไม่มี)
bridge นี้พิมพ์ข้อความเข้า Claude ผ่าน iTerm2 Python API — ต้องใช้ iTerm2 (Terminal.app ปกติใช้ไม่ได้)

```bash
ls /Applications/iTerm.app 2>/dev/null && echo "มีแล้ว" || echo "ยังไม่มี"
# ถ้ายังไม่มี (ต้องมี Homebrew ก่อน — https://brew.sh)
brew install --cask iterm2
```

### 2. เปิด iTerm2 Python API
เปิด iTerm2 → **Settings** (⌘,) → **General** → แท็บ **Magic** → ติ๊ก **Enable Python API**
(ทำครั้งเดียว ต้องกดใน GUI เอง)

### 3. Clone + ติดตั้ง bridge
```bash
git clone https://github.com/kodchanatTidlor/telegram-claude-bridge.git ~/telegram-claude-bridge
cd ~/telegram-claude-bridge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 4. สร้างไฟล์ .env
```bash
cd ~/telegram-claude-bridge
cp .env.example .env
```
แก้ `.env` ใส่ค่า (Token + Chat ID จากหัวข้อ "เตรียมก่อนเริ่ม"):
```
BOT_TOKEN=<token>
ALLOWED_CHAT_ID=<chat id>
POLL_TIMEOUT=50
```
> `.env` อยู่ใน `.gitignore` แล้ว — จะไม่ถูก commit

### 5. ลง Claude Code hooks (user scope)
ใส่ใน `~/.claude/settings.json` — **merge เข้า `hooks` เดิม อย่าทับ** (ถ้า event ไหนมีอยู่แล้ว append เข้า `hooks` array ของมัน) ทุก path ใช้ venv python

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/busy_hook.py" }
      ] }
    ],
    "Stop": [
      { "hooks": [
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/stream_hook.py" },
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/busy_hook.py" },
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/activity_hook.py" }
      ] }
    ],
    "PostToolUse": [
      { "matcher": "", "hooks": [
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/stream_hook.py" },
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/busy_hook.py" },
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/activity_hook.py" }
      ] }
    ],
    "PreToolUse": [
      { "matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit|AskUserQuestion", "hooks": [
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/gate_hook.py", "timeout": 600 }
      ] },
      { "matcher": "", "hooks": [
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/activity_hook.py" }
      ] }
    ],
    "Notification": [
      { "hooks": [
        { "type": "command", "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/busy_hook.py" }
      ] }
    ]
  }
}
```

แต่ละ hook ทำอะไร:
| Hook | event | หน้าที่ |
|------|-------|--------|
| `stream_hook.py` | Stop, PostToolUse | mirror ข้อความ Claude เข้า Telegram (markdown) |
| `gate_hook.py` | PreToolUse | permission / AskUserQuestion → Telegram (บล็อกรอคำตอบ, ต้องตั้ง `timeout: 600`) |
| `activity_hook.py` | PreToolUse, PostToolUse, Stop | สถานะ tool กำลังทำ (ส่ง/ลบ) |
| `busy_hook.py` | UserPromptSubmit, PostToolUse, Stop, Notification | คุม typing indicator |

> hooks ทำงานเฉพาะตอน `serve` รันอยู่ — ถ้าไม่รัน ทุก hook จะข้ามทันที (ทำงาน local ปกติ)

หลังแก้ settings.json ให้ **restart Claude Code** (หรือเปิด `/hooks` 1 ครั้ง) เพื่อโหลด hooks ใหม่

---

## วิธีใช้งาน (foreground)

bridge รันแบบ foreground — เปิดทิ้งไว้ใน iTerm2 tab นึง เห็น log สดๆ

```bash
python3 ~/telegram-claude-bridge/bridgectl.py serve     # เริ่มทำงาน — Ctrl+C หยุด
python3 ~/telegram-claude-bridge/bridgectl.py status    # เช็กสถานะ
```

ปิด terminal หรือ Ctrl+C = bridge หยุด, hooks ทุกตัวข้ามอัตโนมัติ (กลับไปทำงาน local ล้วน)

### flow การใช้งาน
1. `bridgectl.py serve` ใน iTerm2 (เปิดทิ้งไว้)
2. สั่งงาน Claude ใน iTerm2 อีก tab — Telegram จะ:
   - ขึ้น **typing…** ตอนกำลังทำงาน
   - mirror สิ่งที่ Claude พูดเข้ามาสดๆ
   - ถ้า Claude ขอ permission / ถามคำถาม → เด้งปุ่มให้กด
3. **ตอบกลับ:**
   - **ส่งข้อความเฉยๆ** → เข้า session ล่าสุด (active auto-follow)
   - **reply ข้อความใดข้อความหนึ่ง** → เข้า session ที่ข้อความนั้นมาจาก (เจาะ session เก่า / หลาย session)
   - **กดปุ่ม** (permission/คำถาม) → ตอบตรงนั้น
4. ข้อความถูกพิมพ์ + Enter ให้อัตโนมัติ Claude ทำงานต่อ (วนไป)

### คำสั่งใน Telegram (bridge จัดการเอง ไม่ส่งต่อ Claude)
| คำสั่ง / ปุ่ม | ทำอะไร |
|--------------|--------|
| `/status` หรือ 📊 Status | dashboard: model, active session, prompt ค้าง + ปุ่ม refresh / สลับ session / เปิด session ใหม่ |
| `/cancel` หรือ 🛑 Stop | หยุด Claude กลางคัน (ส่ง ESC เข้า active session) |
| `/help` | รายการคำสั่ง |
| 🔄 Refresh (ใน dashboard) | อัปเดต + prune session ที่ปิด/ออกไปแล้ว |
| 📁 (ใน dashboard) | สลับ active session |
| ➕ New (ใน dashboard) | เปิดหน้าต่าง iTerm ใหม่ + รัน Claude ที่ cwd ที่เลือก |

---

## ความปลอดภัย
- รับคำสั่ง/กดปุ่มได้เฉพาะจาก `ALLOWED_CHAT_ID` ของคุณเท่านั้น — id อื่นถูกทิ้งเงียบ
- `BOT_TOKEN` เป็นความลับสูงสุด — ถ้ารั่ว คนอื่นพิมพ์เข้า terminal คุณได้ + อนุมัติ permission ได้ เก็บ `.env` ให้พ้น git
- **permission gate fail-safe** — error / timeout / ตอบกำกวม / listener ตาย → ไม่เคย auto-allow (default deny หรือเด้งเมนูในเครื่องตามปกติ)
- inject เข้าเฉพาะ session ที่ Claude ยังรันอยู่ — ถ้าเป็น shell เปล่า (Claude ออกแล้ว) จะไม่พิมพ์เข้าไป
- ทุกอย่างวิ่งผ่าน Telegram (ไม่ใช่ E2E encryption) — เหมาะงานส่วนตัว ไม่มีข้อมูลอ่อนไหว/PII

---

## คำสั่ง bridgectl
| คำสั่ง | ทำอะไร |
|--------|--------|
| `bridgectl.py serve` | เริ่ม bridge (foreground, เห็น log, Ctrl+C หยุด) |
| `bridgectl.py status` | เช็กสถานะ listener + mirror/gate |
| `bridgectl.py update` | ดึงโค้ดล่าสุด (git pull) + อัปเดต deps (restart serve หลังอัปเดต) |

## แก้ปัญหา
- **ไม่มีอะไรเด้งเข้า Telegram** → เช็ก `status` ว่า listener RUNNING; ลง hooks แล้ว + restart Claude Code; กด Start บอทแล้ว
- **🔐 permission ไม่เด้ง ทั้งที่ Claude ขอ** → gate ทำงานเฉพาะโหมด default; ถ้าอยู่ auto-accept (acceptEdits) จะข้ามไปไม่ถาม
- **reply แล้วขึ้น "claude not running"** → session นั้น Claude ออกไปแล้ว — reply ข้อความของ session ที่ยังรันอยู่
- **เปิด serve แล้ว error 409 Conflict** → มี listener ค้าง; `serve` จะ kill ตัวเก่าให้เองก่อนเริ่ม
- **markdown แสดงเพี้ยน / ตัวอักษรหลุด** → ลง dep ครบไหม (`telegramify-markdown` ใน requirements.txt)
- **ดู error** → log แสดงในจอที่รัน `serve` โดยตรง
