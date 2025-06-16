import os
import sys
import threading
import time
from datetime import datetime, timedelta

import django
import requests
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

from config import VK_TOKEN, GROUP_ID
from gpt_client import get_gpt_response, initialize_vectorization
from utils import HistoryManager, create_bitrix_request

project_root = os.path.dirname(os.path.abspath(__file__))

# 2) добавляем в PYTHONPATH папку с вашим Django-проектом
sys.path.insert(0, os.path.join(project_root, 'order'))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "order.settings")

django.setup()

from main.models import Bot  # импорт модели с настройками


def get_bot_settings() -> Bot:
    """
    Возвращает единственный объект Bot (pk=1) с текущими настройками.
    """

    return Bot.objects.get(pk=1)


def reminder_worker(vk, history_manager: HistoryManager):
    print("Reminder worker started")
    while True:
        history_manager.cursor.execute("""
            SELECT DISTINCT peer_id FROM dialog_history
        """)
        peer_ids = [row[0] for row in history_manager.cursor.fetchall()]

        now = datetime.utcnow()
        settings = get_bot_settings()

        REMINDER1_DELAY = settings.interval_first * 60 * 60
        REMINDER2_DELAY = settings.interval_second * 60 * 60
        reminder_text = settings.text_one_remember  # используем поле promt для первого напоминания
        final_text = settings.text_two_remember
        for peer_id in peer_ids:
            stage = history_manager.get_stage(peer_id)
            if stage >= 2:
                continue

            last_user_ts = history_manager.get_last_user_timestamp(peer_id)
            if not last_user_ts:
                continue

            elapsed = now - last_user_ts

            if stage == 0 and elapsed >= timedelta(seconds=REMINDER1_DELAY):
                vk.messages.send(peer_id=peer_id, message=reminder_text, random_id=0)
                history_manager.set_stage(peer_id, 1)

            elif stage == 1 and elapsed >= timedelta(seconds=REMINDER2_DELAY):
                vk.messages.send(peer_id=peer_id, message=final_text, random_id=0)
                history_manager.set_stage(peer_id, 2)

        time.sleep(10)


def send_delayed_message(vk, peer_id, message):
    # отправка ответа по истечении таймера
    print(f"Отправка сообщения {peer_id} с {message}")
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=0
    )


def keep_typing(vk, peer_id, duration, interval=4):
    """
    Каждые `interval` секунд шлём setActivity,
    чтобы индикатор «печатает…» держался пока duration.
    """
    end_time = time.time() + duration
    while time.time() < end_time:
        vk.messages.setActivity(peer_id=peer_id, type='typing')
        time.sleep(interval)


def handle_new_message(vk, history_manager, settings, obj):
    peer_id = obj.get("peer_id")
    text = obj.get("text", "").strip()
    print(obj)
    if peer_id is None or text == "" or history_manager.in_blacklist(peer_id):
        print("ПОльзователь в чёрном списке")
        return

    # 1) Помечаем как прочитанное
    vk.messages.markAsRead(
        peer_id=peer_id,
        start_message_id=obj.get("id")  # или message_ids=[obj["id"]]
    )

    # 2) запускаем «печатает…» в фоне на 30 сек (каждые 4 сек шлём новую aktivnost)
    threading.Thread(
        target=keep_typing,
        args=(vk, peer_id, 30),
        daemon=True
    ).start()

    # 3) Собираем историю и формируем ответ
    history_manager.set_stage(peer_id, 0)
    ban_list = [w.strip() for w in settings.ban_word.split(",") if w.strip()]
    if any(bw in text for bw in ban_list):
        history_manager.put_in_blacklist(peer_id, "ban_word")
        return

    history = history_manager.get_history(peer_id)
    history_manager.add_message(peer_id, {"role": "user", "content": text})

    assistant_content, assistant_entry = get_gpt_response(
        history,
        text,
        settings.agent_promt + settings.key_word,
        settings.proxy_host,
        settings.proxy_port,
        settings.proxy_user,
        settings.proxy_password
    )

    if assistant_entry["role"] == "MANAGER":
        print("нужно позвать менеджера")
        history_manager.put_in_blacklist(peer_id, "manager")
        user = vk.users.get(user_ids=obj.get("from_id"))[0]
        create_bitrix_request(f"{user['first_name']} {user['last_name']} | VK")
        send_delayed_message(vk, peer_id, "Отлично, я Вас понял! Скоро подключится менеджер и продолжит консультацию.")
        return
    else:
        history_manager.add_message(peer_id, assistant_entry)

    # 4) Через 30 сек отправляем сообщение в отдельном потоке
    timer = threading.Timer(
        interval=30,
        function=send_delayed_message,
        args=(vk, peer_id, assistant_content)
    )
    timer.daemon = True
    timer.start()


def main():
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)
    vk = vk_session.get_api()
    history_manager = HistoryManager(max_history_length=10)

    print("Бот запущен... Ожидание сообщений.")
    # (если у вас есть reminder_worker — оставляем его)
    threading.Thread(target=reminder_worker,
                     args=(vk, history_manager),
                     daemon=True).start()

    settings = get_bot_settings()
    initialize_vectorization(
        proxy_host=settings.proxy_host,
        proxy_port=settings.proxy_port,
        proxy_user=settings.proxy_user,
        proxy_password=settings.proxy_password
    )
    try:
        while True:
            try:
                for event in longpoll.listen():
                        if event.type == VkBotEventType.MESSAGE_NEW:
                            obj = event.obj.message or event.obj
                            # Обрабатываем каждое новое сообщение асинхронно
                            threading.Thread(
                                target=handle_new_message,
                                args=(vk, history_manager, get_bot_settings(), obj),
                                daemon=True
                            ).start()
            except requests.exceptions.ReadTimeout:
                print("🔁 Таймаут VK. Повторное подключение...")
                continue
            except Exception as e:
                print(f"❌ Ошибка longpoll: {e}")
                time.sleep(3)
    except KeyboardInterrupt:
        print("Остановка бота... Закрываем соединение с БД.")
    finally:
        history_manager.close()


if __name__ == "__main__":
    main()
