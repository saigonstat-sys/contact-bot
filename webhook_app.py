import sys
import os
import asyncio
import json

path = "/home/Status101"
if path not in sys.path:
    sys.path.insert(0, path)

import bot as bot_module

BOT_TOKEN = bot_module.BOT_TOKEN
MY_TELEGRAM_ID = bot_module.MY_TELEGRAM_ID

bot = bot_module.Bot(token=BOT_TOKEN)
dp = bot_module.Dispatcher(storage=bot_module.MemoryStorage())

dp.message.middleware(bot_module.AccessCheck())
dp.callback_query.middleware(bot_module.AccessCheck())
dp.include_router(bot_module.router)

db_initialized = False

async def ensure_db():
    global db_initialized
    if not db_initialized:
        await bot_module.init_db()
        webhook_path = "/" + BOT_TOKEN.split(":")[1] + "/"
        webhook_url = "https://contact-bot-hzjf.onrender.com" + webhook_path
        await bot.set_webhook(webhook_url)
        print("Webhook set: " + webhook_url)
        db_initialized = True

def application(environ, start_response):
    if environ["REQUEST_METHOD"] == "POST":
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            body = environ["wsgi.input"].read(content_length)
            data = json.loads(body)
            update = bot_module.Update(**data)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(ensure_db())
            loop.run_until_complete(dp.feed_update(bot, update))
            loop.close()
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"OK"]
        except Exception as e:
            start_response("500 Error", [("Content-Type", "text/plain")])
            return [str(e).encode()]
    else:
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"Bot is running"]
