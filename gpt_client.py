import os

from openai import OpenAI, APIError, RateLimitError

from config import OPENAI_API_KEY

def get_gpt_response(history, user_message, system_prompt, proxy_host, proxy_port, proxy_user, proxy_password):
    """
    Аргументы:
      history (list of dict) — список предыдущих сообщений в формате:
            [{"role": "user"|"assistant", "content": "..."} ...]
      user_message (str) — новое сообщение от пользователя.

    Возвращает кортеж (assistant_content, assistant_entry), где:
      assistant_content (str) — текст ответа GPT,
      assistant_entry (dict) — {"role": "assistant", "content": assistant_content}
    """
    print("щас будет запрос к гпт")
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    print(messages)
    # Формируем URL прокси
    proxy_url = f"http://{proxy_user}:{proxy_password}@{proxy_host}:{proxy_port}"

    # Сохраняем старые значения переменных окружения (если были)
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")

    # Устанавливаем прокси только для этого блока
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=100,
            temperature=0.3
        )

        assistant_content = response.choices[0].message.content.strip()
        print("запрос закончен")
        if "ПОЗОВИ МЕНЕДЖЕРА" in assistant_content:
            assistant_content = "Отлично, я Вас понял! Скоро подключится менеджер и продолжит консультацию."
            assistant_entry = {"role": "MANAGER", "content": assistant_content}
        else:
            assistant_entry = {"role": "assistant", "content": assistant_content}

        return assistant_content, assistant_entry

    except RateLimitError:
        warning = "Сервис временно недоступен (превышена квота). Попробуйте позже."
        return warning, {"role": "assistant", "content": warning}

    except APIError:
        warning = "Ошибка при обращении к GPT. Попробуйте позже."
        return warning, {"role": "assistant", "content": warning}
    finally:
        # Восстанавливаем старые значения переменных окружения
        if old_http is not None:
            os.environ["HTTP_PROXY"] = old_http
        else:
            os.environ.pop("HTTP_PROXY", None)

        if old_https is not None:
            os.environ["HTTPS_PROXY"] = old_https
        else:
            os.environ.pop("HTTPS_PROXY", None)