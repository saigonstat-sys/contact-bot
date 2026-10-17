import os
import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, Update
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship

# === НАСТРОЙКИ (ЗАМЕНИ НА СВОИ!) ===
BOT_TOKEN ="8754559240:AAEso4mE8roM7G42YYP4P15JbF_oeiyz4zA"
MY_TELEGRAM_ID = 8709539653
# ====================================

BASE_DIR = Path("/home/Status101")
UPLOADS_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "contacts.db"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# === База данных ===
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Subscriber(Base):
    __tablename__ = "subscribers"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    last_name: Mapped[str] = mapped_column(default="")
    first_name: Mapped[str] = mapped_column(default="")
    middle_name: Mapped[str | None] = mapped_column(default=None)
    birth_day: Mapped[int | None] = mapped_column(default=None)
    birth_month: Mapped[int | None] = mapped_column(default=None)
    birth_year: Mapped[int | None] = mapped_column(default=None)
    avatar_path: Mapped[str | None] = mapped_column(default=None)

    phones: Mapped[list["Phone"]] = relationship(back_populates="subscriber", cascade="all, delete-orphan")
    emails: Mapped[list["Email"]] = relationship(back_populates="subscriber", cascade="all, delete-orphan")
    files: Mapped[list["File"]] = relationship(back_populates="subscriber", cascade="all, delete-orphan")

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name]
        if self.middle_name and self.middle_name != "-":
            parts.append(self.middle_name)
        return " ".join(parts)

    @property
    def birth_date_str(self):
        if self.birth_day and self.birth_month and self.birth_year:
            return f"{self.birth_day:02d}.{self.birth_month:02d}.{self.birth_year}"
        return "Не указана"

class Phone(Base):
    __tablename__ = "phones"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column()
    number: Mapped[str] = mapped_column()
    subscriber: Mapped["Subscriber"] = relationship(back_populates="phones")

class Email(Base):
    __tablename__ = "emails"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column()
    address: Mapped[str] = mapped_column()
    subscriber: Mapped["Subscriber"] = relationship(back_populates="emails")

class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column()
    file_type: Mapped[str] = mapped_column()
    file_path: Mapped[str] = mapped_column()
    file_name: Mapped[str] = mapped_column()
    subscriber: Mapped["Subscriber"] = relationship(back_populates="files")

# === Состояния ===
class SearchState(StatesGroup):
    fio = State()
    phone = State()
    email = State()

class AddState(StatesGroup):
    last_name = State()
    first_name = State()
    middle_name = State()
    birth_date = State()
    phones = State()
    emails = State()
    avatar = State()
    files = State()

class EditState(StatesGroup):
    field = State()
    value = State()

# === Клавиатуры ===
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск по ФИО", callback_data="srch_fio")],
        [InlineKeyboardButton(text="📱 Поиск по телефону", callback_data="srch_ph")],
        [InlineKeyboardButton(text="📧 Поиск по email", callback_data="srch_em")],
        [InlineKeyboardButton(text="📋 Все контакты", callback_data="all_list_1")],
        [InlineKeyboardButton(text="➕ Добавить контакт", callback_data="add_new")],
    ])

def contact_kb(sub_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Фото", callback_data=f"ph_{sub_id}")],
        [InlineKeyboardButton(text="🎥 Видео", callback_data=f"vd_{sub_id}")],
        [InlineKeyboardButton(text="📄 Файлы", callback_data=f"fl_{sub_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"ed_{sub_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_{sub_id}")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")],
    ])

def files_kb(files_list, sub_id, back_cb):
    btns = []
    for f in files_list:
        e = {"document":"📄","photo":"🖼","video":"🎥"}.get(f.file_type,"📎")
        btns.append([InlineKeyboardButton(text=f"{e} {f.file_name}", callback_data=f"sf_{f.id}")])
    btns.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def edit_kb(sub_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ФИО", callback_data=f"ed_fio_{sub_id}")],
        [InlineKeyboardButton(text="🎂 Дата рождения", callback_data=f"ed_bd_{sub_id}")],
        [InlineKeyboardButton(text="📱 Телефоны", callback_data=f"ed_ph_{sub_id}")],
        [InlineKeyboardButton(text="📧 Email", callback_data=f"ed_em_{sub_id}")],
        [InlineKeyboardButton(text="🖼 Аватар", callback_data=f"ed_av_{sub_id}")],
        [InlineKeyboardButton(text="➕ Добавить файлы", callback_data=f"ed_af_{sub_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"ct_{sub_id}")],
    ])

# === Проверка доступа ===
class AccessCheck(BaseMiddleware):
    async def __call__(self, handler, event, data):
        uid = event.from_user.id if hasattr(event,"from_user") and event.from_user else None
        if uid == MY_TELEGRAM_ID:
            return await handler(event, data)
        if hasattr(event,"message") and event.message:
            await event.message.answer("⛔ Доступ запрещён.")
        elif hasattr(event,"answer"):
            await event.answer("⛔ Доступ запрещён.", show_alert=True)
        return None

# === Функции БД ===
async def search(q, mode):
    async with async_session_factory() as s:
        if mode=="fio":
            stmt = select(Subscriber).where(or_(
                Subscriber.first_name.ilike(f"%{q}%"),
                Subscriber.last_name.ilike(f"%{q}%"),
                Subscriber.middle_name.ilike(f"%{q}%")
            ))
        elif mode=="ph":
            stmt = select(Subscriber).join(Phone).where(Phone.number.ilike(f"%{q}%"))
        elif mode=="em":
            stmt = select(Subscriber).join(Email).where(Email.address.ilike(f"%{q}%"))
        else: return []
        r = await s.execute(stmt)
        return r.scalars().all()

async def get_sub(sid):
    async with async_session_factory() as s:
        r = await s.execute(select(Subscriber).where(Subscriber.id==sid))
        return r.scalars().first()

async def get_file(fid):
    async with async_session_factory() as s:
        r = await s.execute(select(File).where(File.id==fid))
        return r.scalars().first()

async def delete_sub(sid):
    async with async_session_factory() as s:
        sub = await s.get(Subscriber, sid)
        if sub:
            await s.delete(sub)
            await s.commit()
            return True
        return False

async def save_contact(fn, ln, mn, bd, bm, by, phones, emails, avatar, files_data):
    async with async_session_factory() as s:
        sub = Subscriber(first_name=fn, last_name=ln, middle_name=mn if mn!="-" else None,
                        birth_day=bd, birth_month=bm, birth_year=by, avatar_path=avatar)
        sub.phones = [Phone(number=p) for p in phones]
        sub.emails = [Email(address=e) for e in emails]
        sub.files = [File(file_type=f['type'], file_path=f['path'], file_name=f['name']) for f in files_data]
        s.add(sub)
        await s.commit()
        await s.refresh(sub)
        return sub

async def update_fio(sid, ln, fn, mn):
    async with async_session_factory() as s:
        sub = await s.get(Subscriber, sid)
        if sub:
            sub.last_name, sub.first_name = ln, fn
            sub.middle_name = mn if mn!="-" else None
            await s.commit()

async def update_birth(sid, d, m, y):
    async with async_session_factory() as s:
        sub = await s.get(Subscriber, sid)
        if sub:
            sub.birth_day, sub.birth_month, sub.birth_year = d, m, y
            await s.commit()

async def update_phones(sid, phones):
    async with async_session_factory() as s:
        sub = await s.get(Subscriber, sid)
        if sub:
            sub.phones = [Phone(number=p) for p in phones]
            await s.commit()

async def update_emails(sid, emails):
    async with async_session_factory() as s:
        sub = await s.get(Subscriber, sid)
        if sub:
            sub.emails = [Email(address=e) for e in emails]
            await s.commit()

async def update_avatar(sid, path):
    async with async_session_factory() as s:
        sub = await s.get(Subscriber, sid)
        if sub:
            sub.avatar_path = path
            await s.commit()

async def get_all_contacts(limit=10, offset=0):
    async with async_session_factory() as s:
        stmt = select(Subscriber).order_by(Subscriber.last_name, Subscriber.first_name).limit(limit).offset(offset)
        r = await s.execute(stmt)
        return r.scalars().all()

async def count_contacts():
    async with async_session_factory() as s:
        stmt = select(func.count(Subscriber.id))
        r = await s.execute(stmt)
        return r.scalar()

def card_text(sub):
    t = f"👤 <b>{sub.full_name}</b>\n\n"
    t += f"📅 Дата рождения: {sub.birth_date_str}\n\n"
    if sub.phones:
        t += "<b> Телефоны:</b>\n" + "\n".join(f"  • {p.number}" for p in sub.phones) + "\n\n"
    if sub.emails:
        t += "<b>📧 Email:</b>\n" + "\n".join(f"  • {e.address}" for e in sub.emails) + "\n\n"
    t += f"📎 Файлов: {len(sub.files)}"
    return t

# === Хендлеры ===
router = Router()

@router.message(CommandStart())
async def cmd_start(m: Message):
    await m.answer(" Привет! Я бот для управления контактами.", reply_markup=main_kb())

@router.callback_query(F.data=="menu")
async def cb_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("🏠 Главное меню:", reply_markup=main_kb())
    await cb.answer()

@router.callback_query(F.data=="srch_fio")
async def cb_search_fio(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("🔍 Введи ФИО (часть):")
    await state.set_state(SearchState.fio)
    await cb.answer()

@router.callback_query(F.data=="srch_ph")
async def cb_search_ph(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("📱 Введи телефон:")
    await state.set_state(SearchState.phone)
    await cb.answer()

@router.callback_query(F.data=="srch_em")
async def cb_search_em(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("📧 Введи email:")
    await state.set_state(SearchState.email)
    await cb.answer()

@router.message(SearchState.fio)
async def proc_fio(m: Message, state: FSMContext):
    results = await search(m.text.strip(), "fio")
    await state.clear()
    if not results:
        await m.answer("❌ Ничего не найдено.", reply_markup=main_kb())
    elif len(results)==1:
        await show_contact(m, results[0], is_new=True)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"👤 {s.full_name}", callback_data=f"ct_{s.id}")] for s in results[:10]
        ] + [[InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]])
        await m.answer(f" Найдено {len(results)}:", reply_markup=kb)

@router.message(SearchState.phone)
async def proc_phone(m: Message, state: FSMContext):
    results = await search(m.text.strip(), "ph")
    await state.clear()
    if not results:
        await m.answer("❌ Ничего не найдено.", reply_markup=main_kb())
    elif len(results)==1:
        await show_contact(m, results[0], is_new=True)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f" {s.full_name}", callback_data=f"ct_{s.id}")] for s in results[:10]
        ] + [[InlineKeyboardButton(text=" Меню", callback_data="menu")]])
        await m.answer(f"🔍 Найдено {len(results)}:", reply_markup=kb)

@router.message(SearchState.email)
async def proc_email(m: Message, state: FSMContext):
    results = await search(m.text.strip(), "em")
    await state.clear()
    if not results:
        await m.answer("❌ Ничего не найдено.", reply_markup=main_kb())
    elif len(results)==1:
        await show_contact(m, results[0], is_new=True)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"👤 {s.full_name}", callback_data=f"ct_{s.id}")] for s in results[:10]
        ] + [[InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]])
        await m.answer(f" Найдено {len(results)}:", reply_markup=kb)

@router.callback_query(F.data.startswith("all_list_"))
async def cb_all_list(cb: CallbackQuery):
    page = int(cb.data.split("_")[2])
    per_page = 10
    offset = (page - 1) * per_page
    total = await count_contacts()
    contacts = await get_all_contacts(limit=per_page, offset=offset)
    if not contacts:
        await cb.message.answer("📋 Список контактов пуст.", reply_markup=main_kb())
        await cb.answer()
        return
    buttons = []
    for c in contacts:
        name = c.full_name
        if len(name) > 30:
            name = name[:27] + "..."
        buttons.append([InlineKeyboardButton(text=f"👤 {name}", callback_data=f"ct_{c.id}")])
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"all_list_{page-1}"))
    if len(contacts) == per_page and (page * per_page) < total:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"all_list_{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    start_num = offset + 1
    end_num = offset + len(contacts)
    text = f"📋 Контакты ({start_num}-{end_num} из {total}):"
    await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

async def show_contact(target, sub, is_new=True):
    text = card_text(sub)
    kb = contact_kb(sub.id)
    has_avatar = sub.avatar_path and os.path.exists(sub.avatar_path)
    if has_avatar:
        try:
            photo = FSInputFile(sub.avatar_path)
            if is_new and hasattr(target, "answer_photo"):
                await target.answer_photo(photo, caption=text, parse_mode="HTML", reply_markup=kb)
                return
            elif not is_new and hasattr(target, "message") and hasattr(target.message, "answer_photo"):
                await target.message.answer_photo(photo, caption=text, parse_mode="HTML", reply_markup=kb)
                return
        except Exception as e:
            print(f"⚠️ Не удалось отправить фото: {e}")
    if is_new and hasattr(target, "answer"):
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
    elif not is_new and hasattr(target, "message") and hasattr(target.message, "answer"):
        await target.message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("ct_"))
async def cb_contact(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    sub = await get_sub(sid)
    if not sub:
        await cb.answer("❌ Не найден", show_alert=True)
        return
    await show_contact(cb, sub, is_new=False)
    await cb.answer()

@router.callback_query(F.data.startswith("ph_"))
async def cb_photos(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    sub = await get_sub(sid)
    photos = [f for f in sub.files if f.file_type=="photo"] if sub else []
    if not photos:
        await cb.answer("📷 Фото нет", show_alert=True)
        return
    await cb.message.answer(f"🖼 Фото ({len(photos)}):", reply_markup=files_kb(photos, sid, f"ct_{sid}"))
    await cb.answer()

@router.callback_query(F.data.startswith("vd_"))
async def cb_videos(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    sub = await get_sub(sid)
    videos = [f for f in sub.files if f.file_type=="video"] if sub else []
    if not videos:
        await cb.answer("🎥 Видео нет", show_alert=True)
        return
    await cb.message.answer(f"🎥 Видео ({len(videos)}):", reply_markup=files_kb(videos, sid, f"ct_{sid}"))
    await cb.answer()

@router.callback_query(F.data.startswith("fl_"))
async def cb_files(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    sub = await get_sub(sid)
    docs = [f for f in sub.files if f.file_type=="document"] if sub else []
    if not docs:
        await cb.answer("📄 Файлов нет", show_alert=True)
        return
    await cb.message.answer(f"📄 Файлы ({len(docs)}):", reply_markup=files_kb(docs, sid, f"ct_{sid}"))
    await cb.answer()

@router.callback_query(F.data.startswith("sf_"))
async def cb_send_file(cb: CallbackQuery):
    fid = int(cb.data.split("_")[1])
    f = await get_file(fid)
    if not f:
        await cb.answer("❌ Файл не найден", show_alert=True)
        return
    try:
        inp = FSInputFile(f.file_path, filename=f.file_name)
        if f.file_type=="document":
            await cb.message.answer_document(inp)
        elif f.file_type=="photo":
            await cb.message.answer_photo(inp)
        elif f.file_type=="video":
            await cb.message.answer_video(inp)
        await cb.answer("✅ Отправлено!")
    except Exception as e:
        await cb.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.callback_query(F.data.startswith("del_"))
async def cb_del_confirm(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    sub = await get_sub(sid)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delyes_{sid}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"ct_{sid}")]
    ])
    await cb.message.answer(f"️ Удалить {sub.full_name}?", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("delyes_"))
async def cb_del_yes(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    ok = await delete_sub(sid)
    await cb.message.answer("✅ Удалено." if ok else "❌ Ошибка.", reply_markup=main_kb())
    await cb.answer()

@router.callback_query(F.data.startswith("ed_") & ~F.data.startswith("ed_fio_") & ~F.data.startswith("ed_bd_") & ~F.data.startswith("ed_ph_") & ~F.data.startswith("ed_em_") & ~F.data.startswith("ed_av_") & ~F.data.startswith("ed_af_"))
async def cb_edit_menu(cb: CallbackQuery):
    sid = int(cb.data.split("_")[1])
    await cb.message.answer("✏️ Что изменить?", reply_markup=edit_kb(sid))
    await cb.answer()

@router.callback_query(F.data.startswith("ed_fio_"))
async def cb_ed_fio(cb: CallbackQuery, state: FSMContext):
    sid = int(cb.data.split("_")[2])
    await state.update_data(eid=sid, efield="fio")
    await cb.message.answer("✏️ Введи ФИО: Фамилия Имя Отчество\n(Отчество можно '-')")
    await state.set_state(EditState.value)
    await cb.answer()

@router.callback_query(F.data.startswith("ed_bd_"))
async def cb_ed_bd(cb: CallbackQuery, state: FSMContext):
    sid = int(cb.data.split("_")[2])
    await state.update_data(eid=sid, efield="bd")
    await cb.message.answer("Введи дату рождения: ДД.ММ.ГГГГ")
# Создаём таблицы при первом запуске
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Таблицы базы данных готовы")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccessCheck())
    dp.callback_query.middleware(AccessCheck())
    dp.include_router(router)
    
    await init_db()
    print("🤖 Бот запущен в режиме long polling!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
