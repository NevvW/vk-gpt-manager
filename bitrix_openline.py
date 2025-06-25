import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from functools import wraps

import django
import requests
from flask import Flask, request, jsonify, current_app

from config import INCOMING_WEBHOOK_URL, CLIENT_ID, BOT_ID
from gpt_client import initialize_vectorization, get_gpt_response
from utils import HistoryManager

app = Flask(__name__)

# Инициализация логирования
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'bot.log')

file_handler = logging.FileHandler(
    filename=LOG_FILE,
    encoding='utf-8'
)

# Создаём хендлер для консоли
console_handler = logging.StreamHandler()

# Общий форматтер
formatter = logging.Formatter(
    fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Настраиваем basicConfig через аргумент handlers
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

logger = logging.getLogger(__name__)

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


# HTTP-вызов методов Bitrix24 через Webhook
def bitrix_call(method, params):
    url = f"{INCOMING_WEBHOOK_URL}/{method}"
    logger.debug(f"Calling {url} with {params}")
    resp = requests.post(url, data=params)
    print(params)
    print(url)
    if resp.status_code != 200:
        current_app.logger.error(f"HTTP {resp.status_code}: {resp.text}")
    else:
        result = resp.json()
        if result.get('error'):
            current_app.logger.error(f"Bitrix24 error: {result}")
    return resp


def is_text_only(form):
    """
    Возвращает True, если в форме только текстовое сообщение,
    без файлов, репостов, превью и системных уведомлений.
    """
    data = form.to_dict()
    dialog_id = data.get('data[PARAMS][DIALOG_ID]')
    logger.debug(f"{dialog_id} Проверяем текст сообщения")

    # 2) Проверка наличия текста
    text = data.get('data[PARAMS][MESSAGE]', '').strip()
    if not text:
        logger.info(f"{dialog_id} Текста нет")
        return False

    # 3) Проверка файлов (FILE_ID и FILES)
    if form.getlist('data[PARAMS][PARAMS][FILE_ID]') or \
            any(key.startswith('data[PARAMS][FILES]') for key in data):
        send_manager(dialog_id)
        logger.info(f"{dialog_id} Загрузили файл")
        return False

    # 5) Проверка rich previews и URL-репортов (ATTACH и URL_ATTACH)
    if any(key.startswith('data[PARAMS][PARAMS][ATTACH]') for key in data) or \
            any(key.startswith('data[PARAMS][URL_ATTACH]') for key in data):
        send_manager(dialog_id)
        logger.info(f"{dialog_id} Ссылка")
        return False

    lower_text = text.lower()
    if "url" in lower_text or "http" in lower_text:
        send_manager(dialog_id)
        logger.info(f"{dialog_id} Ссылка прям ссылка")
        return False

    # 6) Служебные сообщения (SYSTEM)
    if data.get('data[PARAMS][SYSTEM]') == 'Y':
        logger.info(f"{dialog_id} Служебное сообщение")
        return False

    logger.debug(f"{dialog_id} Текст отличный")

    return True


def always_ok(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        f(*args, **kwargs)
        return jsonify({'ERROR': 0, 'RESULT': 'ok'})

    return wrapper


@app.route('/', methods=['POST'])
@always_ok
def webhook_handler():
    logger.info("Запрос от Bitrix24")
    data_from_form = request.form.to_dict()
    logger.info(request.form)
    logger.info('------------------')
    event = data_from_form.get('event')
    logger.info(f"Событие: {event}")

    # Общие переменные
    dialog_id = data_from_form.get('data[PARAMS][DIALOG_ID]')
    text = data_from_form.get('data[PARAMS][MESSAGE]')

    if event == 'ONIMBOTMESSAGEADD':
        if dialog_id is None:
            logger.error("dialog_id не удалось получить из сообщения")
            return

        if history_manager.in_blacklist(dialog_id):
            logger.info("Пользователь в чёрном списке")
            return

        if not is_text_only(request.form):
            return

        logger.info(f"TEXT: {text}")

        global last_excel_change
        settings = get_bot_settings()

        if settings.last_change != last_excel_change:
            send_manager(dialog_id,
                         "Прямо сейчас мы обновляем наш каталог товаров. Вам ответит первый освободившийся менеджер!")
            initialize_vectorization(
                proxy_host=settings.proxy_host,
                proxy_port=settings.proxy_port,
                proxy_user=settings.proxy_user,
                proxy_password=settings.proxy_password
            )
            last_excel_change = settings.last_change
            return

        history_manager.set_stage(dialog_id, 0)

        ban_list = [w.strip() for w in settings.ban_word.split(",") if w.strip()]
        if any(bw in text for bw in ban_list):
            history_manager.put_in_blacklist(dialog_id, "ban_word")
            return

        history = history_manager.get_history(dialog_id)
        history_manager.add_message(dialog_id, {"role": "user", "content": text})

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
            logger.warning("нужно позвать менеджера")
            send_manager(dialog_id)
            return
        else:
            history_manager.add_message(dialog_id, assistant_entry)

        thread = threading.Timer(
            function=send_delayed_message,
            interval=30,
            args=(dialog_id, assistant_content),
        )
        thread.daemon = True
        thread.start()

    return jsonify({'ERROR': 0, 'RESULT': 'ok'})


def send_manager(dialog_id: str,
                 message: str = "Отлично, я Вас поняла! Скоро подключится менеджер и продолжит консультацию."):
    history_manager.put_in_blacklist(dialog_id, "manager")
    send_delayed_message(dialog_id, message)
    create_bitrix_request(dialog_id.replace("chat", ""))


def send_delayed_message(dialog_id, message):
    bitrix_call('imbot.message.add', {
        'BOT_ID': BOT_ID,
        'DIALOG_ID': dialog_id,
        'MESSAGE': message,
        'CLIENT_ID': CLIENT_ID,
    })


def reminder_worker(history_manager: HistoryManager):
    logger.info("Reminder worker started")
    while True:
        try:
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
            for dialog_id in peer_ids:
                try:
                    stage = history_manager.get_stage(dialog_id)
                    if stage >= 2:
                        continue

                    last_user_ts = history_manager.get_last_user_timestamp(dialog_id)
                    if not last_user_ts:
                        continue

                    elapsed = now - last_user_ts

                    if stage == 0 and elapsed >= timedelta(seconds=REMINDER1_DELAY):
                        send_delayed_message(dialog_id, reminder_text)
                        # vk.messages.send(peer_id=peer_id, message=reminder_text, random_id=0)
                        history_manager.set_stage(dialog_id, 1)

                    elif stage == 1 and elapsed >= timedelta(seconds=REMINDER2_DELAY):
                        send_delayed_message(dialog_id, final_text)

                        # vk.messages.send(peer_id=peer_id, message=final_text, random_id=0)
                        history_manager.set_stage(dialog_id, 2)
                except Exception as e:
                    logger.error(f"Error in reminder_worker for {dialog_id}: {e}")
        except Exception as e:
            logger.error(f"Error in reminder_worker: {e}")

        time.sleep(10)


def create_bitrix_request(chat_id):
    bitrix_call("imopenlines.bot.session.operator", {
        "CHAT_ID": chat_id,
        "CLIENT_ID": CLIENT_ID,
    })


if __name__ == '__main__':
    global history_manager
    history_manager = HistoryManager(max_history_length=10)
    logger.info("Бот запущен... Ожидание сообщений.")

    threading.Thread(target=reminder_worker,
                     args=(history_manager,),
                     daemon=True).start()

    settings = get_bot_settings()
    initialize_vectorization(
        proxy_host=settings.proxy_host,
        proxy_port=settings.proxy_port,
        proxy_user=settings.proxy_user,
        proxy_password=settings.proxy_password
    )

    global last_excel_change
    last_excel_change = settings.last_change

    app.run(host='0.0.0.0', port=5000, threaded=True)
