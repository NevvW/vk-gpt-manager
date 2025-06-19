import hashlib
import os

import faiss
import numpy as np
import pandas as pd
from openai import OpenAI, APIError, RateLimitError

from config import OPENAI_API_KEY

# ---------- Configuration ----------
PRODUCT_CSV_PATH = 'products/products.csv'
METADATA_CSV_PATH = 'products/products_metadata.csv'
INDEX_PATH = 'products/products.index'
EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_BATCH_SIZE = 100
TOP_K = 5


# ---------- Proxy Helper ----------
def configure_proxy(host: str, port: str, user: str, password: str) -> tuple[str | None, str | None]:
    """
    Устанавливает HTTP_PROXY и HTTPS_PROXY и возвращает старые значения.
    """
    proxy_url = f"http://{user}:{password}@{host}:{port}"
    old_http = os.environ.get("HTTP_PROXY")
    old_https = os.environ.get("HTTPS_PROXY")
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url
    return old_http, old_https


# ---------- Embedding Helpers ----------

def hash_text(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def load_products() -> pd.DataFrame:
    # Читаем CSV с колонками name и price
    df = pd.read_csv(PRODUCT_CSV_PATH)
    df['id'] = df.index.astype(str)
    df['name_hash'] = df['name'].apply(hash_text)
    df['price_hash'] = df['price'].astype(str).apply(hash_text)
    df['description_hash'] = df['description'].astype(str).apply(hash_text)
    return df.set_index('id')


def load_metadata() -> pd.DataFrame:
    # Если файл с метаданными существует — читаем и ставим index по 'id'
    if os.path.exists(METADATA_CSV_PATH):
        md = pd.read_csv(METADATA_CSV_PATH, dtype={'id': str})
        md['name_hash'] = md['name_hash'].astype(str)
        md['price_hash'] = md['price_hash'].astype(str)
        md['description_hash'] = md['description_hash'].astype(str)
        return md.set_index('id')
    # Иначе создаём пустой DataFrame с индексом 'id'
    cols = ['name', 'description', 'price', 'name_hash', 'description_hash', 'price_hash']
    df = pd.DataFrame(columns=cols)
    df.index.name = 'id'
    return df


def get_embedding_batch(texts: list[str]) -> np.ndarray:
    """
    Возвращает эмбеддинги для списка текстов.
    Использует OpenAI клиент и корректно обрабатывает ответ.
    """
    resp = openai_client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
    embs = [datum.embedding for datum in resp.data]
    return np.array(embs, dtype=np.float32)


# ---------- Vectorization Initialization ----------

def initialize_vectorization(proxy_host, proxy_port, proxy_user, proxy_password) -> None:
    """
    Инициализирует OpenAI клиент, загружает данные, строит FAISS-индекс и обновляет метаданные.
    """
    global openai_client, _products, _metadata, index
    # Настраиваем клиента
    old_http, old_https = configure_proxy(host=proxy_host, port=proxy_port, user=proxy_user, password=proxy_password)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    # Загружаем продукты и метаданные
    _products = load_products()
    _metadata = load_metadata()

    # 3) проверяем, есть ли изменения
    rebuild_index = False
    changes = []
    for pid, row in _products.iterrows():
        if pid not in _metadata.index:
            changes.append((pid, 'new'))
        else:
            old = _metadata.loc[pid]
            if row['name_hash'] != old['name_hash']:
                changes.append((pid, 'name_changed'))
            if row['price_hash'] != old['price_hash']:
                changes.append((pid, 'price_changed'))
            if row['description_hash'] != old['description_hash']:
                changes.append((pid, 'description_changed'))

    if changes:
        rebuild_index = True
        for pid, change in changes:
            print(f"Product {pid}: {change}")
    else:
        print("No changes detected.")

    # 4) строим или загружаем FAISS-индекс
    #    — если файла индекса нет, или если надо пересоздать (rebuild_index=True), мы перебираем все данные
    if rebuild_index or not os.path.exists(INDEX_PATH):
        print("Rebuilding FAISS index from scratch...")
        embs_list, ids = [], []
        for i in range(0, len(_products), EMBEDDING_BATCH_SIZE):
            batch = _products.iloc[i:i + EMBEDDING_BATCH_SIZE]
            texts = (batch['name'].fillna('') + '. ' + batch['description'].fillna('')).tolist()
            embs_list.append(get_embedding_batch(texts))
            ids += batch.index.astype(int).tolist()
        embs_np = np.vstack(embs_list)

        faiss.normalize_L2(embs_np)
        dim = embs_np.shape[1]
        base_index = faiss.IndexFlatL2(dim)
        index = faiss.IndexIDMap(base_index)
        index.add_with_ids(embs_np, np.array(ids, dtype=np.int64))
        faiss.write_index(index, INDEX_PATH)
    else:
        print("Loading existing FAISS index...")
        index = faiss.read_index(INDEX_PATH)
    print("successful")
    # Сохраняем актуальные метаданные
    _products[['name', 'description', 'price', 'name_hash', 'description_hash', 'price_hash']].to_csv(METADATA_CSV_PATH)

    if old_http is not None:
        os.environ["HTTP_PROXY"] = old_http
    else:
        os.environ.pop("HTTP_PROXY", None)

    if old_https is not None:
        os.environ["HTTPS_PROXY"] = old_https
    else:
        os.environ.pop("HTTPS_PROXY", None)


# ---------- Retrieval ----------
def get_conversation_embedding(history: list[dict], user_message: str) -> np.ndarray:
    """
    Собирает все user-сообщения из истории + текущее в одну строку
    и возвращает единичный эмбеддинг.
    """
    # Берём только тексты сообщений, где роль — 'user'
    user_texts = [m['content'] for m in history if m['role'] == 'user']
    # Добавляем текущее сообщение
    full_text = " ".join(user_texts + [user_message])
    # Получаем эмбеддинг одной строкой
    emb = get_embedding_batch([full_text])[0]  # shape (dim,)
    return emb

def retrieve_products_with_history(history: list[dict], user_message: str, k: int = TOP_K) -> pd.DataFrame:
    """
    Делает поиск по FAISS на основе эмбеддинга всей беседы + последнего вопроса.
    """
    q_emb = get_conversation_embedding(history, user_message)
    # поиск возвращает (distances, indices)
    distances, idxs = index.search(q_emb.reshape(1, -1), k)
    # приводим к DataFrame
    df = _products.iloc[idxs[0]].reset_index(drop=True)
    df['distance'] = distances[0]
    return df

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
    retrieved = retrieve_products_with_history(history, user_message)
    context = "\n\n".join(
        f"Товар {i + 1}:\n"
        f"Название: {row['name']}\n"
        f"Описание: {row['description']}\n"
        f"Цена: {row['price']}\n"
        for i, row in retrieved.iterrows()
    )
    # объединяем базовый системный промпт и контекст товаров
    sales_prompt = f"{system_prompt}\n\nИнформация по релевантным товарам:\n{context}"

    print("щас будет запрос к гпт")
    messages = [{"role": "system", "content": sales_prompt}]
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
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=400,
            temperature=0.3
        )

        assistant_content = response.choices[0].message.content.strip()
        print("запрос закончен")
        if "bitrix" in assistant_content.lower():
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
