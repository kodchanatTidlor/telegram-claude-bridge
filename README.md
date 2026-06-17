# Telegram ↔ Claude Code Bridge

เมื่อ Claude Code ทำงานเสร็จใน iTerm2 จะส่งสรุป (recap) เข้า Telegram ให้
แล้วถ้าคุณ reply ข้อความนั้นกลับมา ข้อความจะถูกพิมพ์เข้า Claude session ที่กำลังรันอยู่
(พิมพ์ + กด Enter ให้อัตโนมัติ) เหมือนคุณนั่งพิมพ์เองที่ terminal

ใช้ตอน AFK — สั่งงาน Claude ต่อจากมือถือได้

---

## TL;DR — ก็อป prompt นี้ไปวางใน Claude Code แล้วมันจะ setup ให้จนจบ

> ช่วย setup telegram-claude-bridge ที่ `~/telegram-claude-bridge` ให้ใช้งานได้จนจบ ตามขั้นตอนนี้ ทำทีละขั้นและถามผมเมื่อต้องการข้อมูล:
>
> 1. Clone repo ไปที่ `~/telegram-claude-bridge` (ถ้ายังไม่มี): `git clone https://github.com/kodchanatTidlor/telegram-claude-bridge.git ~/telegram-claude-bridge`
> 2. เช็กว่ามี Python 3.9+ ในเครื่องหรือยัง (`python3 --version`) ถ้าไม่มี ให้ติดตั้งด้วย `brew install python` (ต้องมี Homebrew ก่อน — https://brew.sh)
> 3. เช็กว่ามี iTerm2 ติดตั้งหรือยัง (`ls /Applications/iTerm.app` หรือ `brew list --cask iterm2`) ถ้าไม่มี ให้ติดตั้งด้วย `brew install --cask iterm2`
> 4. เข้าโฟลเดอร์ `~/telegram-claude-bridge` สร้าง venv และลง dependency: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
> 5. ถามผมขอ **Telegram Bot Token** กับ **Chat ID** (บอกวิธีหาให้ผมด้วย ถ้าผมยังไม่มี) แล้วสร้างไฟล์ `.env` จาก `.env.example` ใส่ค่า `BOT_TOKEN` และ `ALLOWED_CHAT_ID` (ห้าม commit ไฟล์นี้)
> 6. ลง Stop hook แบบ user scope ใน `~/.claude/settings.json` ให้ยิง `recap_hook.py` ด้วย venv python (merge เข้า hooks เดิม อย่าทับ) — command คือ `$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/recap_hook.py`
> 7. บอกผมให้เปิด iTerm2 Python API เอง (Settings → General → Magic → Enable Python API) เพราะต้องกดใน GUI
> 8. รัน `python3 ~/telegram-claude-bridge/bridgectl.py status` เช็กความพร้อม แล้วบอกผมว่าต้องรัน `python3 ~/telegram-claude-bridge/bridgectl.py serve` ใน iTerm2 เพื่อเริ่มใช้งาน
>
> ทำตามทีละขั้น เช็กผลแต่ละขั้นก่อนไปต่อ

---

## ติดตั้งแบบ manual (ถ้าไม่ใช้ TL;DR)

### 1. ติดตั้ง iTerm2 (ถ้ายังไม่มี)
bridge นี้พิมพ์ข้อความเข้า Claude ผ่าน iTerm2 Python API — ต้องใช้ iTerm2 (Terminal.app ปกติใช้ไม่ได้)

```bash
# เช็กว่ามีหรือยัง
ls /Applications/iTerm.app 2>/dev/null && echo "มีแล้ว" || echo "ยังไม่มี"

# ถ้ายังไม่มี (ต้องมี Homebrew ก่อน — https://brew.sh)
brew install --cask iterm2
```

### 2. เปิด iTerm2 Python API
เปิด iTerm2 → **Settings** (⌘,) → **General** → แท็บ **Magic** → ติ๊ก **Enable Python API**
(ทำครั้งเดียว ต้องกดใน GUI เอง)

### 3. ติดตั้ง bridge
```bash
cd ~/telegram-claude-bridge
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 4. สร้าง Telegram Bot เพื่อเอา Token
1. เปิด Telegram คุยกับ **@BotFather**
2. พิมพ์ `/newbot`
3. ตั้งชื่อ bot และ username (ลงท้าย `bot`)
4. BotFather จะส่ง **token** กลับมา หน้าตาเช่น `123456789:ABCdef...` → เก็บไว้
5. (แนะนำ) พิมพ์ `/setprivacy` → เลือก bot → **Enable** เพื่อให้ bot อ่านเฉพาะข้อความที่ส่งถึงมันโดยตรง

### 5. หา Chat ID ของตัวเอง
1. เปิดแชตกับ bot ที่เพิ่งสร้าง กด **Start** แล้วพิมพ์อะไรก็ได้ส่งไปหามัน 1 ข้อความ
2. หา chat id ด้วยวิธีใดวิธีหนึ่ง:

   **วิธี A — ใช้ @userinfobot**
   คุยกับ **@userinfobot** ใน Telegram → มันบอก `Id` ของคุณ (ตัวเลขล้วน)

   **วิธี B — ผ่าน API** (แทน `<TOKEN>` ด้วย token จากขั้น 4)
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | grep -o '"id":[0-9]*' | head -1
   ```
   เลขในผลลัพธ์คือ chat id ของคุณ

### 6. สร้างไฟล์ .env
```bash
cd ~/telegram-claude-bridge
cp .env.example .env
```
แก้ `.env` ใส่ค่า:
```
BOT_TOKEN=<token จากขั้น 4>
ALLOWED_CHAT_ID=<chat id จากขั้น 5>
POLL_TIMEOUT=50
```
> `.env` อยู่ใน `.gitignore` แล้ว — จะไม่ถูก commit

### 7. ลง Claude Code Stop hook (user scope)
ให้ Claude ยิง recap ทุกครั้งที่ทำงานเสร็จ ทุกโปรเจกต์ — ใส่ใน `~/.claude/settings.json`
(merge เข้า `hooks` เดิม อย่าทับของเก่า; ถ้ามี `Stop` อยู่แล้วให้ append เข้า array)

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [
        { "type": "command",
          "command": "$HOME/telegram-claude-bridge/.venv/bin/python $HOME/telegram-claude-bridge/recap_hook.py" }
      ] }
    ]
  }
}
```
หลังแก้ settings.json ให้เปิดเมนู `/hooks` ใน Claude Code 1 ครั้ง (หรือ restart) เพื่อให้โหลด hook ใหม่

---

## วิธีใช้งาน (foreground)

bridge รันแบบ foreground อย่างเดียว — เปิดทิ้งไว้ใน iTerm2 tab นึง เห็น log สดๆ

```bash
python3 ~/telegram-claude-bridge/bridgectl.py serve     # เริ่มทำงาน เห็น log ในจอนี้ — Ctrl+C เพื่อหยุด
python3 ~/telegram-claude-bridge/bridgectl.py status    # เช็กสถานะ: listener RUNNING/STOPPED | recap ON/OFF
```

ปิด terminal หรือ Ctrl+C = bridge หยุด และ recap ปิดอัตโนมัติ
(Stop hook จะส่ง recap เฉพาะตอน listener ทำงานอยู่)

### flow การใช้งาน
1. `python3 ~/telegram-claude-bridge/bridgectl.py serve` ใน iTerm2 (เปิดทิ้งไว้)
2. สั่งงาน Claude ใน iTerm2 อีก tab — พองานเสร็จ recap เด้งเข้า Telegram (มี quote prompt + คำตอบ)
3. **ส่งข้อความเฉยๆ** → เข้า session ล่าสุด (active)
4. **reply ที่ recap อันใดอันหนึ่ง** → เข้า session ที่ recap นั้นมาจาก (เจาะ session เก่า / หลาย session)
5. ข้อความถูกพิมพ์ + Enter ให้อัตโนมัติ Claude ทำงานต่อ → recap ใหม่เด้งมา (วนไป)

---

## ความปลอดภัย
- รับคำสั่งเฉพาะจาก `ALLOWED_CHAT_ID` ของคุณเท่านั้น — id อื่นถูกทิ้งเงียบ
- `BOT_TOKEN` เป็นความลับสูงสุด — ถ้ารั่ว คนอื่นพิมพ์เข้า terminal คุณได้ และอ่าน recap เก่าได้ เก็บ `.env` ให้พ้น git
- inject เข้าเฉพาะ session ที่ Claude ยังรันอยู่ — ถ้า session กลายเป็น shell เปล่า (Claude ออกแล้ว) จะไม่พิมพ์เข้าไป
- recap วิ่งผ่าน Telegram (ไม่ใช่ E2E encryption) — เหมาะกับงานส่วนตัวที่ไม่มีข้อมูลอ่อนไหว/PII

---

## คำสั่งทั้งหมด
| คำสั่ง | ทำอะไร |
|--------|--------|
| `python3 ~/telegram-claude-bridge/bridgectl.py serve` | เริ่ม bridge (foreground, เห็น log, Ctrl+C หยุด) |
| `python3 ~/telegram-claude-bridge/bridgectl.py status` | เช็กสถานะ listener + recap |
| `python3 ~/telegram-claude-bridge/bridgectl.py update` | ดึงโค้ดล่าสุดจาก GitHub (git pull) + อัปเดต deps (restart serve หลังอัปเดต) |

## แก้ปัญหา
- **recap ไม่เด้งเข้า Telegram** → เช็ก `status` ว่า listener RUNNING; เช็กว่าลง Stop hook แล้ว (เปิด `/hooks` 1 ครั้ง)
- **reply แล้วขึ้น "claude not running"** → session นั้น Claude ออกไปแล้ว (เหลือ shell) — reply recap ของ session ที่ยังรันอยู่แทน
- **เปิด serve แล้ว error 409 Conflict** → มี listener ค้างอยู่; `serve` จะ kill ตัวเก่าให้เองก่อนเริ่ม
- **ดู error** → log แสดงในจอที่รัน `serve` โดยตรง
