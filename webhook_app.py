from aiohttp import web
from aiogram import Bot, Dispatcher, Update
from aiogram.fsm.storage.memory import MemoryStorage
from bot import BOT_TOKEN, init_db, router, AccessCheck

async def on_startup(app):
    await init_db()
    webhook_url = f"https://contact-bot-hzjf.onrender.com/{BOT_TOKEN.split(':')[1]}/"
    await app['bot'].set_webhook(webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")
    print("🤖 Бот запущен и работает!")

async def on_shutdown(app):
    await app['bot'].delete_webhook()
    await app['bot'].session.close()

async def webhook_handler(request):
    data = await request.json()
    update = Update(**data)
    await request.app['dp'].feed_update(request.app['bot'], update)
    return web.Response()

def application():
    app = web.Application()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.message.middleware(AccessCheck())
    dp.callback_query.middleware(AccessCheck())
    dp.include_router(router)
    
    app['bot'] = bot
    app['dp'] = dp
    
    app.router.add_post(f'/{BOT_TOKEN.split(":")[1]}/', webhook_handler)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    return app
