import os
import sys
import threading
import time
from datetime import datetime, timedelta

import django
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

from config import VK_TOKEN, GROUP_ID
from gpt_client import get_gpt_response
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


def main():
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    longpoll = VkBotLongPoll(vk_session, group_id=GROUP_ID)
    vk = vk_session.get_api()
    history_manager = HistoryManager(max_history_length=10)
    print("Бот запущен... Ожидание сообщений.")
    threading.Thread(target=reminder_worker, args=(vk, history_manager), daemon=True).start()

    try:
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                print("поймал сообщение")
                obj = event.obj.message or event.obj

                peer_id = obj.get("peer_id")
                text = obj.get("text", "").strip()

                if peer_id is None or text == "" or history_manager.in_blacklist(peer_id):
                    continue

                history_manager.set_stage(peer_id, 0)

                settings = get_bot_settings()

                ban_list = [w.strip() for w in settings.ban_word.split(",") if w.strip()]
                if any(bw in text for bw in ban_list):
                    history_manager.put_in_blacklist(peer_id, "ban_word")
                    continue

                history = history_manager.get_history(peer_id)

                user_entry = {"role": "user", "content": text}
                history_manager.add_message(peer_id, user_entry)


                assistant_content, assistant_entry = get_gpt_response(
                    history,
                    text,
                    settings.agent_promt + settings.key_word + settings.promt,
                    settings.proxy_host,
                    settings.proxy_port,
                    settings.proxy_user,
                    settings.proxy_password
                )
                if assistant_entry["role"] == "MANAGER":
                    history_manager.put_in_blacklist(peer_id, "manager")
                    user_id = obj.get("from_id")
                    user = vk.users.get(user_ids=user_id)[0]
                    create_bitrix_request(f"{user['first_name']} {user['last_name']} | VK")
                else:
                    history_manager.add_message(peer_id, assistant_entry)

                vk.messages.send(
                    peer_id=peer_id,
                    message=assistant_content,
                    random_id=0
                )
    except KeyboardInterrupt:
        print("Остановка бота... Закрываем соединение с БД.")
    finally:
        history_manager.close()


if __name__ == "__main__":
    main()
