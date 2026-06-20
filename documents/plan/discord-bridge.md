# แผน: branch สำหรับ Discord bot

สรุปการต่อ bridge กับ Discord แทน Telegram — ทำอะไรได้มากกว่า/น้อยกว่า, แนวทาง refactor ให้ต่างจาก `main` ให้น้อยที่สุด, และ security risk.

---

## 1. สถาปัตยกรรมปัจจุบัน (Telegram ผูกอยู่ตรงไหน)

โค้ดส่วนใหญ่ **transport-agnostic อยู่แล้ว** — ไม่รู้จัก Telegram เลย:

| ไม่ต้องแตะ | หน้าที่ |
|---|---|
| `bridge/iterm.py`, `proc.py` | คุย iTerm2 / process |
| `bridge/store.py` | session state (ไฟล์ json) |
| `bridge/gate.py` | permission/question gate |
| `bridge/cswap.py`, `usage.py` | quota + สลับ account |
| `bridge/stream.py`, `transcript.py`, `activity.py`, `busy.py` | อ่าน transcript / สถานะ |

Telegram ผูกแค่ **3 จุด**:

| ผูก Telegram | รายละเอียด |
|---|---|
| `bridge/telegram.py` (101 บรรทัด) | IO ล้วน — `send_message`, `get_updates` (long-poll), inline keyboard, edit, typing, callback |
| `bridge/config.py` | `bot_token`, `allowed_chat_id` |
| `listener.py` | orchestrate + พึ่ง **รูปทรง update dict** ของ Telegram (`{"message":{...},"callback_query":{...}}`) |
| `bridge/commands.py`, `recap.py` | string เป็น **MarkdownV2** + `escape_md_v2` |

> กุญแจ: `listener.py` (`resolve_target`, `handle_callback`, `handle_bridge_command`) อ่าน update dict แบบ Telegram. ถ้าทำให้ Discord ป้อน dict **รูปทรงเดียวกัน** ได้ → `listener.py` แทบไม่ต้องแก้ → rebase จาก `main` ง่าย.

---

## 2. Discord ทำได้ "มากกว่า" Telegram

| ความสามารถ | Telegram ตอนนี้ | Discord |
|---|---|---|
| **Threads ต่อ session** | ต้องใช้ forum topic ของ supergroup (`telegram-group` branch, ซับซ้อน) | thread เป็น native — สร้าง/อ่าน/route ง่ายกว่า |
| **Realtime** | long-poll (`getUpdates`, จัดการ offset เอง) | Gateway WebSocket push — ไม่มี polling latency, ไม่ต้องเก็บ offset |
| **Dropdown เลือก session/account** | ทำไม่ได้ — เรียงปุ่มเป็นแถวๆ | Select menu (dropdown) — เลือก session/account ในเมนูเดียว |
| **Modal (ฟอร์ม popup)** | ไม่มี | กรอกข้อความยาว/หลายช่องผ่าน popup ได้ |
| **Ephemeral message** | ไม่มี — screen snapshot ต้อง `deleteMessage` เอง | ส่งแบบ "เห็นคนเดียว" — gate/screen ไม่ต้องลบ ไม่รก |
| **Embed สวยๆ** | text + MarkdownV2 escaping เจ็บปวด | embed มีสี/field/title — dashboard `/status` สวยกว่า |
| **Syntax highlight** | code block ธรรมดา | ` ```python ` ไฮไลต์ตามภาษา |
| **แนบไฟล์** | ทำได้แต่ไม่ได้ใช้ | ส่งรูป screenshot จริง / log ยาวเป็นไฟล์ได้ง่าย (ทะลุ limit ตัวอักษร) |
| **Slash command มี argument** | `/cmd` เปล่าๆ | typed args + autocomplete native |

---

## 3. Discord ทำได้ "น้อยกว่า" / ยากกว่า

| ข้อจำกัด | ผลกระทบ |
|---|---|
| **ไม่มี persistent reply keyboard** | Telegram มีแถวปุ่มลัดล่างจอตลอด (`command_keyboard`) — Discord ไม่มี. ต้องแทนด้วย slash command หรือ pinned message ที่มีปุ่ม |
| **Event loop ชนกัน** | `discord.py` กับ `iterm2.run_until_complete` ต่างก็อยากเป็นเจ้าของ asyncio loop → **ความเสี่ยง refactor ใหญ่สุด** (ดู §4) |
| **ต้องมี gateway connection ค้างไว้** | Telegram long-poll เรียบง่ายกว่า. discord.py reconnect อัตโนมัติให้ แต่ moving part เยอะกว่า |
| **Setup ยุ่งกว่า** | ต้องสร้าง server (guild) + invite bot + เปิด **MESSAGE_CONTENT intent** (privileged) ใน dev portal |
| **เริ่ม DM หาคนก่อนไม่ได้** | bot DM ได้เฉพาะคนที่อยู่ guild ร่วมกัน → ใช้งานจริงควรเป็น private guild ไม่ใช่ DM ล้วน |
| **2000 ตัวอักษร/ข้อความ** | สั้นกว่า Telegram (4096). แก้ด้วย embed (4096) หรือแนบไฟล์ |
| **dep ใหญ่ขึ้น** | ตอนนี้พึ่งแค่ `httpx`. `discord.py` เป็น dep หนักกว่า + supply-chain surface ใหญ่ขึ้น |

---

## 4. แนวทาง refactor (ให้ต่างจาก main น้อยสุด)

**เลือก Adapter pattern** — เลียนแบบ "หน้าตา interface" ของ Telegram ทับ discord.py:

### โครงสร้าง
```
bridge/discord_io.py   # ใหม่ — mirror ทุก signature ใน telegram.py
                       #   send_message(cfg, text, ...) -> id
                       #   edit_message_text / edit_reply_markup / delete_message
                       #   answer_callback / send_chat_action / set_my_commands
                       #   get_updates(cfg, offset) -> list[update_dict]   ← กุญแจ
```

### กุญแจ: แปลง gateway push → update dict แบบ Telegram
discord.py เป็น push (event) แต่ `listener.py` คาดหวัง pull (`get_updates`). เชื่อมด้วย **`asyncio.Queue`**:

```
on_message / on_interaction (discord)
        │  normalize → {"message": {...}} / {"callback_query": {...}}
        ▼
   asyncio.Queue  ──► get_updates(cfg, offset) ดึงออกมา
```
- `on_message` → `{"update_id":n, "message":{"from":{"id":..}, "chat":{"id":..}, "text":.., "reply_to_message":..}}`
- `on_interaction` (กดปุ่ม) → `{"update_id":n, "callback_query":{"id":.., "from":{"id":..}, "data":.., "message":{"message_id":..}}}`

ทำแบบนี้แล้ว `resolve_target`, `handle_callback`, `handle_gate_reply`, `handle_bridge_command` ใน `listener.py` **ไม่ต้องแก้เลย**.

### เลือก transport ด้วย config
```python
# config.py — เพิ่ม field, ไม่ลบของเดิม
transport: str = "telegram"   # หรือ "discord"
discord_token / discord_channel_id / allowed_user_id
```
```python
# listener.py — บรรทัด import เดียวที่เปลี่ยน
if cfg.transport == "discord":
    from bridge import discord_io as io
else:
    from bridge import telegram as io
```
บน branch `discord`: ตั้ง `TRANSPORT=discord` ใน `.env` → Telegram **ปิดเอง** (ไม่ถูก import/start). ไม่ต้องลบโค้ด Telegram → merge `main` กลับมาได้สบาย.

### เรื่อง event loop (จุดเสี่ยง)
ต้องรัน iTerm2 connection + discord client ใน loop เดียว. ทางที่สะอาดสุด:
- ให้ **discord.py เป็นเจ้าของ loop** (`async with client`), แล้วเปิด iTerm2 connection ด้วย `iterm2.Connection.async_create()` ภายใน loop นั้น (ไม่ใช้ `run_until_complete`).
- `_amain(connection)` เดิมแทบใช้ซ้ำได้ — แค่เปลี่ยนคนเปิด connection.

### MarkdownV2
- Telegram escape โหด, Discord markdown ง่ายกว่า. ให้ transport ถือ `escape()` ของตัวเอง (Discord = แทบ no-op). แก้ `commands.py`/`recap.py` ให้เรียก `io.escape` แทน `escape_md_v2` ตรงๆ — diff เล็ก.

### สิ่งที่ลดลงต้องชดเชย
- `command_keyboard` (reply keyboard) → ใช้ Discord slash command + pinned message ที่มีปุ่ม.

---

## 5. Security risks

| ความเสี่ยง | มาตรการ |
|---|---|
| **MESSAGE_CONTENT เป็น privileged intent** — bot อ่านทุกข้อความในห้องที่เห็น | จำกัด bot ไว้ **private guild ที่เราเป็นเจ้าของคนเดียว** + ล็อก permission ของห้อง |
| **ใครก็ได้ในห้อง = สั่ง terminal เราได้** (inject text = ใกล้ RCE) | **allowlist ที่ author user-id** ไม่ใช่แค่ channel — ขยาย `is_allowed` ให้เช็ค `guild_id + channel_id + author_id` ครบ |
| **คนอื่นในห้องเห็น output ของ Claude / screen snapshot** อาจหลุด code/secret บนจอ | private guild + ใช้ **ephemeral message** กับ gate/screen |
| **Discord token หลุด = ยึด bot ได้เต็ม** | เก็บใน `.env` (gitignored) เหมือน `BOT_TOKEN` เดิม, อย่า hardcode |
| **discord.py = dep ใหญ่ขึ้น (supply chain)** | pin version ใน requirements, ตรวจก่อน bump |
| **request intent เกินจำเป็น** | ขอเฉพาะ `guilds`, `guild_messages`, `message_content` เท่าที่ใช้ |
| **screen/transcript egress ไป Discord** (เหมือนเดิมกับ Telegram) | private channel + ephemeral, อย่าโพสต์ snapshot ที่มี secret |

> ข้อต่างสำคัญจาก Telegram: Telegram ใช้ `allowed_chat_id` เดียวก็พอ (DM 1:1). Discord ห้องมีหลายคนได้ → **ห้ามเชื่อแค่ channel ต้อง allowlist author** มิฉะนั้นใครเข้าห้องก็สั่ง terminal เราได้.

---

## 6. ลำดับงานที่เสนอ

1. `git checkout -b discord` จาก `main`
2. เพิ่ม field ใน `config.py` (`transport`, discord_*) — ไม่ลบของเดิม
3. เขียน `bridge/discord_io.py` (mirror signature + Queue + normalizer) — เขียน test ก่อนด้วย fake update dict (เลียน test เดิม)
4. แก้ import switch + เจ้าของ event loop ใน `listener.py`/`_amain`
5. แทน `escape_md_v2` ตรงๆ ด้วย `io.escape`
6. ชดเชย reply keyboard ด้วย slash command + pinned buttons
7. ทดสอบ end-to-end ใน private guild, ตรวจ allowlist author

> ของที่ใช้ซ้ำได้ทั้งดุ้น: `iterm`, `store`, `gate`, `cswap`, `stream`, `commands` (logic), `listener` (logic). งานจริงกองที่ `discord_io.py` + event loop เท่านั้น.
