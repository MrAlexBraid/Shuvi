import os
import time
import asyncio
from openai import OpenAI
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
from telegram import Bot

client = OpenAI()
vk_token     = os.getenv("VK_API_TOKEN")
assistant_id = os.getenv("OPENAI_ASSISTANT_ID")

# Telegram
tg_bot_token = os.getenv("TG_BOT_TOKEN")
shuvi_chat_id = os.getenv("SHUVI_CHAT_ID")
tg_bot = Bot(token=tg_bot_token)

if not vk_token or not assistant_id:
    raise ValueError("❌ Нет VK_API_TOKEN или OPENAI_ASSISTANT_ID в переменных Railway")
if not tg_bot_token or not shuvi_chat_id:
    raise ValueError("❌ Нет TG_BOT_TOKEN или SHUVI_CHAT_ID в переменных Railway")

vk_session = vk_api.VkApi(token=vk_token)
vk         = vk_session.get_api()
longpoll   = VkLongPoll(vk_session)

user_last_message_time = {}
user_threads           = {}
active_users           = {}
RESPONSE_COOLDOWN      = 5
SESSION_TIMEOUT        = 30 * 60

def send_vk_message(user_id: int, text: str):
    try:
        vk.messages.send(user_id=user_id,
                         message=text,
                         random_id=int(time.time() * 1_000_000))
        print(f"[VK] Сообщение отправлено {user_id}: {text[:30]}")
    except Exception as e:
        print(f"[VK] Ошибка отправки сообщения {user_id}: {e}")

def send_telegram_message(chat_id, text):
    async def _send():
        await tg_bot.send_message(chat_id=chat_id, text=text)
    try:
        asyncio.get_running_loop().create_task(_send())
    except RuntimeError:
        asyncio.run(_send())

def is_active(user_id):
    if user_id in active_users:
        if time.time() - active_users[user_id] < SESSION_TIMEOUT:
            return True
        else:
            del active_users[user_id]
    return False

PING_PHRASES = [
    "позови алекса", "позвать алекса", "зовите алекса", "человек", "кожанный мешок", "Позови человека",
    "позвать владельца", "позвать директора"
]

print("🟢 Шуви запущена и слушает ВКонтакте…")

try:
    print("Перед longpoll.listen()")
    for event in longpoll.listen():
        print("Что-то пришло!")
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            print(f"Новое сообщение от {event.user_id}: {event.text}")
            user_id  = event.user_id
            user_msg = event.text.strip()

            now, last = time.time(), user_last_message_time.get(user_id, 0)
            if now - last < RESPONSE_COOLDOWN:
                print(f"[COOLDOWN] Пропуск ответа для {user_id}")
                continue
            user_last_message_time[user_id] = now

            if any(phrase in user_msg.lower() for phrase in PING_PHRASES):
                print("[PING] Пинг админа!")
                send_telegram_message(
                    shuvi_chat_id,
                    f"Вас зовут в чатике VK!\nUser: vk.com/id{user_id}\nСообщение: {user_msg}"
                )
                send_vk_message(
                    user_id,
                    "Алексу отправлено уведомление, он скоро напишет Вам. Сессия завершена. Чтобы снова начать, напиши 'Шуви'"
                )
                if user_id in active_users:
                    del active_users[user_id]
                continue

            if is_active(user_id):
                print("[STATE] Пользователь активен, отвечаю")
                if user_msg.lower() in ["стоп", "пока", "отключиться"]:
                    del active_users[user_id]
                    send_vk_message(user_id, "Сессия завершена. Чтобы снова начать, напиши 'Шуви'.")
                    continue
                else:
                    active_users[user_id] = now
            else:
                if "шуви" in user_msg.lower():
                    print("[ACTIVATE] Активация Шуви для пользователя")
                    active_users[user_id] = now
                    send_vk_message(user_id, "Шуви активирован! Теперь отвечаю на любые сообщения. Чтобы завершить — напиши 'Стоп' или 'Пока'.")
                else:
                    print("[NO ACTIVATE] Сообщение вне активации Шуви")
                    continue

            try:
                print("[OPENAI] Пробую создать thread для OpenAI")
                thread_id = user_threads.setdefault(
                    user_id, client.beta.threads.create().id
                )
                print("[OPENAI] Отправляю сообщение в thread")
                client.beta.threads.messages.create(
                    thread_id=thread_id, role="user", content=user_msg
                )
                print("[OPENAI] Запускаю run")
                run = client.beta.threads.runs.create(
                    thread_id=thread_id, assistant_id=assistant_id
                )
                while client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=run.id
                ).status != "completed":
                    print("[OPENAI] Ожидание завершения run...")
                    time.sleep(1)
                reply = client.beta.threads.messages.list(
                    thread_id=thread_id
                ).data[0].content[0].text.value
                print(f"[OPENAI] Получен ответ: {reply[:40]}... Отправляю в VK")
                send_vk_message(user_id, reply)
            except Exception as e:
                send_vk_message(user_id, "Произошла ошибка. Попробуйте позже.")
                print("❌ Ошибка (внутри обработки сообщения):", e)
    print("Цикл завершился")
except Exception as global_e:
    print("!!! GLOBAL ERROR:", global_e)
