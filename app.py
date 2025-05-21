# ...весь твой импорт и инициализация как было

print("🟢 Шуви запущена и слушает ВКонтакте…")

try:
    print("Перед longpoll.listen()")  # <--- Дебаг: доходим до запуска longpoll
    for event in longpoll.listen():
        print("Что-то пришло!")        # <--- Дебаг: пришло хоть одно событие

        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            print(f"Новое сообщение от {event.user_id}: {event.text}")  # <--- Дебаг сообщения
            user_id  = event.user_id
            user_msg = event.text.strip()

            now, last = time.time(), user_last_message_time.get(user_id, 0)
            if now - last < RESPONSE_COOLDOWN:
                continue
            user_last_message_time[user_id] = now

            if any(phrase in user_msg.lower() for phrase in PING_PHRASES):
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
                if user_msg.lower() in ["стоп", "пока", "отключиться"]:
                    del active_users[user_id]
                    send_vk_message(user_id, "Сессия завершена. Чтобы снова начать, напиши 'Шуви'.")
                    continue
                else:
                    active_users[user_id] = now
            else:
                if "Шуви" in user_msg.lower():
                    active_users[user_id] = now
                    send_vk_message(user_id, "Шуви активирован! Теперь отвечаю на любые сообщения. Чтобы завершить — напиши 'Стоп' или 'Пока'.")
                else:
                    continue

            try:
                thread_id = user_threads.setdefault(
                    user_id, client.beta.threads.create().id
                )
                client.beta.threads.messages.create(
                    thread_id=thread_id, role="user", content=user_msg
                )
                run = client.beta.threads.runs.create(
                    thread_id=thread_id, assistant_id=assistant_id
                )
                while client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=run.id
                ).status != "completed":
                    time.sleep(1)
                reply = client.beta.threads.messages.list(
                    thread_id=thread_id
                ).data[0].content[0].text.value
                send_vk_message(user_id, reply)
            except Exception as e:
                send_vk_message(user_id, "Произошла ошибка. Попробуйте позже.")
                print("❌ Ошибка (внутри обработки сообщения):", e)
    print("Цикл завершился")  # <--- Если увидишь это, значит longpoll оборвался

except Exception as global_e:
    print("!!! GLOBAL ERROR:", global_e)
