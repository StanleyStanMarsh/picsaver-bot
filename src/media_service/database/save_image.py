import uuid
from pathlib import Path
import json
import requests
import os

from tenacity import retry, retry_if_exception, wait_exponential, stop_after_attempt

from bot_service.config import BOT_TOKEN, PROXY_FULL_ADDRESS

ROOT_DIR = Path(__file__).parent.parent.parent.parent  # media_service/workers/save_worker.py -> на 3 уровня вверх
IMAGES_DIR = ROOT_DIR / "images"


@retry(
        retry=retry_if_exception(requests.exceptions.Timeout),
        wait=wait_exponential(max=5),
        stop=stop_after_attempt(5),
        reraise=True
)
def download_image_by_file_path(bot_token: str, file_path: str, save_path: str, proxy: str = None):
    """
    Скачивает изображение по file_path используя requests (один запрос)
    """
    proxies = None
    if proxy:
        proxies = {
            'http': proxy,
            'https': proxy,
        }
    
    # Формируем URL для скачивания (один запрос)
    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    
    # Скачиваем файл
    response = requests.get(
        download_url, 
        proxies=proxies, 
        stream=True,
        timeout=(10, 120)  # (connect timeout, read timeout)
    )
    response.raise_for_status()
    
    # Сохраняем файл
    with open(save_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def add_image(user_id: int, file_path: str, file_id: str):
    """
    Сохраняет изображение на диск и обновляет мета-информацию
    file_path: путь к файлу, полученный от Telegram API (например, "photos/file_123.jpg")
    """
    # Создаем директорию пользователя
    user_dir = IMAGES_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    
    # Генерируем уникальное имя файла
    file_name = f"{uuid.uuid4()}.jpg"
    save_path = user_dir / file_name
    
    # Скачиваем изображение (один HTTP запрос)
    try:
        download_image_by_file_path(
            bot_token=BOT_TOKEN,
            file_path=file_path,
            save_path=str(save_path),
            proxy=PROXY_FULL_ADDRESS
        )
    except Exception as e:
        raise Exception(f"Failed downloading picture with file_path: {file_path}, due to this exception {e}")
    
    # Работа с мета-файлом
    meta_file = user_dir / "meta.json"
    data = []
    
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding='utf-8') as f:
                content = f.read()
                if content:
                    data = json.loads(content)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Ошибка чтения meta.json: {e}")
            data = []
    
    # Добавляем новую запись
    data.append({
        "file_id": file_id,  # сохраняем оригинальный file_path от Telegram
        "local_path": file_name  # сохраняем локальное имя файла
    })
    
    # Сохраняем мета-файл
    with open(meta_file, "w", encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return True
