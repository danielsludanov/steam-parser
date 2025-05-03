import json
import re
import time
import uuid
from datetime import datetime

import requests
from bs4 import BeautifulSoup as bs


# Function to remove HTML tags from text
def strip_html(html_text):
    if not html_text:
        return ""
    soup = bs(html_text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def Top_Games():
    url = "https://steamspy.com/api.php?request=top100in2weeks"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Ошибка при получении данных: {e}")
        return {}


def get_game_data(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=russian"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if not data[str(appid)]["success"]:
            return None
        return data[str(appid)]["data"]
    except requests.RequestException as e:
        print(f"Ошибка при запросе данных для appid {appid}: {e}")
        return None


def get_avg_playtime(appid):
    url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        avg_playtime_minutes = data.get("average_forever", None)
        # Конвертация в часы, округление до двух знаков после запятой
        return (
            round(avg_playtime_minutes / 60, 2)
            if avg_playtime_minutes is not None
            else None
        )
    except requests.RequestException as e:
        print(f"Ошибка при получении avg_playtime для appid {appid}: {e}")
        return None


import re

from bs4 import BeautifulSoup

# Константы
WINDOWS_CONTAINER_CLASSES = ["game_area_sys_req", "sysreq_content", "active"]
WINDOWS_DATA_OS = "win"
SYS_REQ_BLOCK_CLASS = "game_area_sys_req"
MIN_REQ_CLASS = "game_area_sys_req_leftCol"
REC_REQ_CLASS = "game_area_sys_req_rightCol"
FULL_REQ_CLASS = "game_area_sys_req_full"
LIST_CLASS = "bb_ul"
NOT_SPECIFIED = "не указано"


def parse_system_requirements(soup):
    """Парсинг системных требований только для Windows с учётом разных структур."""
    # Инициализация словаря с "не указано" для всех полей
    sys_req = {
        "os_name": "Windows",
        "min_ram_gb": NOT_SPECIFIED,
        "min_cpu": NOT_SPECIFIED,
        "min_gpu": NOT_SPECIFIED,
        "min_storage_gb": NOT_SPECIFIED,
        "min_directx": NOT_SPECIFIED,
        "rec_ram_gb": NOT_SPECIFIED,
        "rec_cpu": NOT_SPECIFIED,
        "rec_gpu": NOT_SPECIFIED,
        "rec_storage_gb": NOT_SPECIFIED,
        "rec_directx": NOT_SPECIFIED,
    }

    try:
        print("1. Поиск блока системных требований...")
        # Найти блок системных требований
        sys_req_block = soup.find("div", class_=SYS_REQ_BLOCK_CLASS)
        if not sys_req_block:
            print(f"Блок с классом '{SYS_REQ_BLOCK_CLASS}' не найден.")
            return sys_req
        print(f"Блок '{SYS_REQ_BLOCK_CLASS}' найден.")
        print("Содержимое game_area_sys_req:", sys_req_block.prettify()[:1000])

        print("2. Поиск контейнера для Windows...")
        # Найти контейнер Windows
        windows_req = soup.find(
            "div",
            attrs={"data-os": WINDOWS_DATA_OS},
            class_=lambda x: x and "sysreq_content" in x.split(),
        )
        if not windows_req:
            print(
                f"Контейнер с data-os='{WINDOWS_DATA_OS}' и классом 'sysreq_content' не найден."
            )
            all_contents = soup.find_all("div", class_="sysreq_content")
            print(f"Найдено {len(all_contents)} sysreq_content контейнеров:")
            for i, content in enumerate(all_contents, 1):
                print(
                    f"Контейнер {i}: class={content.get('class', [])}, data-os={content.get('data-os', 'нет')}"
                )
            return sys_req
        print(
            f"Контейнер Windows найден: class={windows_req.get('class')}, data-os={windows_req.get('data-os')}"
        )

        print("3. Определение структуры требований...")
        # Проверяем, есть ли минимальные и рекомендуемые или только минимальные
        min_req = windows_req.find("div", class_=MIN_REQ_CLASS)
        rec_req = windows_req.find("div", class_=REC_REQ_CLASS)
        full_req = windows_req.find("div", class_=FULL_REQ_CLASS)

        if not min_req and not full_req:
            print("Не найдены блоки минимальных требований.")
            return sys_req

        def parse_req(req_block, prefix):
            if not req_block:
                print(f"Блок {prefix} требований не найден.")
                return
            items = req_block.find("ul", class_=LIST_CLASS)
            if not items:
                print(f"Список с классом '{LIST_CLASS}' ({prefix}) не найден.")
                return
            print(f"Обработка элементов {prefix} требований...")
            for item in items.find_all("li"):
                text = item.get_text(strip=True)
                if not text:
                    continue
                print(f"Элемент: {text}")

                if any(
                    keyword in text.lower()
                    for keyword in ["os:", "операционная система:"]
                ):
                    sys_req["os_name"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
                elif any(
                    keyword in text.lower() for keyword in ["processor:", "процессор:"]
                ):
                    sys_req[f"{prefix}_cpu"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
                elif any(
                    keyword in text.lower()
                    for keyword in ["memory:", "оперативная память:"]
                ):
                    match = re.search(r"(\d+\.?\d*)\s*(ГБ|GB)", text, re.IGNORECASE)
                    if match:
                        sys_req[f"{prefix}_ram_gb"] = float(match.group(1))
                        print(f"RAM ({prefix}): {sys_req[f'{prefix}_ram_gb']} GB")
                    else:
                        sys_req[f"{prefix}_ram_gb"] = (
                            text.split(":", 1)[1].strip() if ":" in text else text
                        )
                elif any(
                    keyword in text.lower() for keyword in ["graphics:", "видеокарта:"]
                ):
                    sys_req[f"{prefix}_gpu"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
                elif any(
                    keyword in text.lower()
                    for keyword in ["hard drive:", "storage:", "место на диске:"]
                ):
                    match = re.search(r"(\d+\.?\d*)\s*(ГБ|GB)", text, re.IGNORECASE)
                    if match:
                        sys_req[f"{prefix}_storage_gb"] = float(match.group(1))
                        print(
                            f"Storage ({prefix}): {sys_req[f'{prefix}_storage_gb']} GB"
                        )
                    else:
                        sys_req[f"{prefix}_storage_gb"] = (
                            text.split(":", 1)[1].strip() if ":" in text else text
                        )
                elif "directx:" in text.lower():
                    match = re.search(r"DirectX[^\d]*(\d+)", text, re.IGNORECASE)
                    if match:
                        sys_req[f"{prefix}_directx"] = f"Version {match.group(1)}"
                        print(f"DirectX ({prefix}): {sys_req[f'{prefix}_directx']}")
                    else:
                        sys_req[f"{prefix}_directx"] = (
                            text.split(":", 1)[1].strip() if ":" in text else text
                        )

        # Если есть full_req (только минимальные)
        if full_req:
            print("Обнаружена структура с game_area_sys_req_full (только минимальные).")
            parse_req(full_req, "min")
        else:
            # Если есть min_req и rec_req
            print("Обнаружена структура с минимальными и рекомендуемыми требованиями.")
            parse_req(min_req, "min")
            parse_req(rec_req, "rec")

        print("Результат парсинга:", sys_req)
        return sys_req
    except AttributeError as e:
        print(f"Ошибка при парсинге системных требований: {e}")
        return sys_req


def parse_steam_page(appid, game_data):
    url = f"https://store.steampowered.com/app/{appid}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = bs(response.text, "html.parser")

        franchise = None
        franchise_rows = soup.find_all("div", class_="dev_row")
        for row in franchise_rows:
            label = row.find("b")
            if (
                label
                and label.text.strip() == "Franchise"
                or label
                and label.text.strip() == "Франшиза"
            ):
                franchise_links = row.find_all("a")
                franchise_names = [link.text.strip() for link in franchise_links]
                if franchise_names:
                    franchise_name = franchise_names[-1]
                    franchise = {
                        "franchise_id": None,
                        "franchise_name": franchise_name,
                        "franchise_description": f"Серия игр, включающая {franchise_name}",
                    }
                break
        if not franchise:
            franchise = {
                "franchise_id": None,
                "franchise_name": "Не найдено",
                "franchise_description": "Франшиза не указана",
            }

        awards = []
        awards_table = soup.find("div", id="awardsTable")
        if awards_table:
            award_entries = awards_table.find_all(
                "a", class_=re.compile(r"steamawards\d+_app_square_ctn")
            )
            for entry in award_entries:
                award_title = entry.find(
                    "div", class_=re.compile(r"steamawards\d+_app_banner_header")
                )
                award_name = (
                    award_title.text.strip() if award_title else "Неизвестная награда"
                )

                image = entry.find("img")
                image_url = image["src"] if image and image.get("src") else None

                website_url = entry["href"] if entry.get("href") else url

                awards.append(
                    {
                        "award_id": None,
                        "award_name": award_name,
                        "image_url": image_url,
                        "website_url": website_url,
                    }
                )

        # Парсинг системных требований
        system_requirements = parse_system_requirements(soup)

        return {
            "franchise": franchise,
            "awards": awards,
            "system_requirements": system_requirements,
        }
    except (requests.RequestException, AttributeError) as e:
        print(f"Ошибка при парсинге страницы для appid {appid}: {e}")
        return {
            "franchise": {
                "franchise_id": None,
                "franchise_name": "Не найдено",
                "franchise_description": "Франшиза не указана",
            },
            "awards": [],
            "system_requirements": None,
        }


def parse_age_rating(appid, game_data):
    required_age = game_data.get("required_age", 0)
    if required_age and isinstance(required_age, (int, str)) and int(required_age) > 0:
        return f"{required_age}+", int(required_age)

    url = f"https://store.steampowered.com/app/{appid}/"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = bs(response.text, "html.parser")
        age_rating = soup.find("div", class_="game_rating_icon")
        if age_rating and age_rating.img:
            rating = age_rating.img["alt"]
            match = re.search(r"(\d+)\+", rating)
            if match:
                return match.group(0), int(match.group(1))
    except (requests.RequestException, AttributeError):
        pass
    return "0+", 0


def map_game_to_db(game_data, appid):
    """Маппинг данных игры на структуру базы данных без автоинкрементных ID."""
    current_time = datetime.now().isoformat()

    # Возрастной рейтинг
    age_rating_code, min_age = parse_age_rating(appid, game_data)

    # Парсинг страницы Steam для франшизы, наград и системных требований
    steam_page_data = parse_steam_page(appid, game_data)

    # Выбор header_image_url из галереи (первый скриншот, если есть)
    screenshots = game_data.get("screenshots", [])
    header_image_url = (
        screenshots[0]["path_full"]
        if screenshots
        else game_data.get("header_image", "")
    )

    # Получение среднего времени игры в часах
    avg_playtime_hours = get_avg_playtime(appid)

    # Основная информация об игре
    game = {
        "game_title": game_data.get("name", ""),
        "cover_image_url": game_data.get("header_image", ""),
        "header_image_url": header_image_url,
        "age_rating_code": age_rating_code,
        "min_age": min_age,
        "release_date": game_data.get("release_date", {}).get("date", ""),
        "average_rating": None,
        "total_ratings": 0,
        "favorites_count": 0,
        "description": strip_html(game_data.get("detailed_description", "")),
        "franchise_name": steam_page_data["franchise"]["franchise_name"],
        "franchise_description": steam_page_data["franchise"]["franchise_description"],
        "publisher_name": (
            game_data.get("publishers", [])[0] if game_data.get("publishers") else None
        ),
        "avg_playtime": avg_playtime_hours,
        "created_at": current_time,
        "updated_at": current_time,
    }

    # Разработчики (список названий)
    developers = game_data.get("developers", [])

    # Жанры (список названий)
    genres = [genre["description"] for genre in game_data.get("genres", [])]

    # Теги (список названий)
    tags = [cat["description"] for cat in game_data.get("categories", [])]

    # Платформы (список названий)
    platforms = [
        plat.capitalize()
        for plat in game_data.get("platforms", [])
        if game_data["platforms"].get(plat)
    ]

    # Языки с удалением HTML тегов и лишних символов
    supported_languages = game_data.get("supported_languages", "")
    languages = []
    if supported_languages:
        # Парсим HTML, чтобы обработать <strong> и другие теги
        lang_soup = bs(supported_languages, "html.parser")
        # Разделяем текст по запятым, игнорируя пустые элементы
        lang_items = [
            item.strip()
            for item in lang_soup.get_text(separator=",").split(",")
            if item.strip()
        ]
        for lang in lang_items:
            # Очищаем язык от лишних символов (*, пробелы)
            clean_lang = re.sub(r"[*]+", "", lang).strip()
            if not clean_lang:
                continue
            # Проверяем наличие <strong> в оригинальном HTML для аудио
            has_audio = any(
                tag.name == "strong" and clean_lang in tag.get_text(strip=True)
                for tag in lang_soup.find_all()
            )
            languages.append(
                {
                    "language": clean_lang,
                    "interface": True,
                    "audio": has_audio,
                    "subtitles": True,
                }
            )

    # Режимы игры (список названий)
    play_modes = [
        cat["description"]
        for cat in game_data.get("categories", [])
        if cat["description"] in ["Одиночная игра", "Мультиплеер", "Кооператив"]
    ]
    # Если режимы не найдены, устанавливаем значение по умолчанию
    if not play_modes:
        play_modes = ["Не указано"]

    # Подключение (список названий)
    connectivity = []
    if any(
        cat["description"] in ["Мультиплеер", "Кооператив", "Онлайн кооператив"]
        for cat in game_data.get("categories", [])
    ):
        connectivity.append("Онлайн")
    if any(
        cat["description"] == "Одиночная игра"
        for cat in game_data.get("categories", [])
    ):
        connectivity.append("Оффлайн")
    # Если подключение не определено, устанавливаем значение по умолчанию
    if not connectivity:
        connectivity = ["Оффлайн" if game_data.get("categories") else "Не указано"]

    # Контроллеры
    controllers = [
        {"controller_name": "Gamepad", "notes": cat["description"]}
        for cat in game_data.get("categories", [])
        if cat["description"]
        in ["Поддержка контроллера (полная)", "Поддержка контроллера (частичная)"]
    ]

    # Добавление клавиатуры как устройства ввода по умолчанию, если нет других контроллеров
    if not controllers:
        controllers.append(
            {
                "controller_name": "Клавиатура",
                "notes": "Поддержка клавиатуры и мыши по умолчанию",
            }
        )

    # Награды
    awards = [
        {
            "award_name": award["award_name"],
            "image_url": award["image_url"],
            "website_url": award["website_url"],
        }
        for award in steam_page_data["awards"]
    ]

    # Системные требования
    system_requirements = steam_page_data["system_requirements"]

    return {
        "game": game,
        "developers": developers,
        "genres": genres,
        "tags": tags,
        "platforms": platforms,
        "languages": languages,
        "gallery": [
            {"media_url": img["path_full"], "media_type": "image"}
            for img in game_data.get("screenshots", [])
        ],
        "trailers": [
            {"trailer_url": movie["mp4"]["max"], "preview_image": movie["thumbnail"]}
            for movie in game_data.get("movies", [])
        ],
        "play_modes": play_modes,
        "connectivity": connectivity,
        "controllers": controllers,
        "awards": awards,
        "system_requirements": system_requirements,
    }


def main():
    # Получаем топ-100 игр
    top_games = Top_Games()
    if not top_games:
        print("Не удалось получить список топ-100 игр")
        return

    results = []
    for appid, game_info in list(top_games.items())[:20]:
        print(f"Обрабатываем игру с appid {appid}")
        game_data = get_game_data(appid)
        if game_data:
            mapped_data = map_game_to_db(game_data, appid)
            results.append(mapped_data)
        time.sleep(0.2)  # Задержка для Steam Store API и парсинга страниц

    # Сохраняем результат в JSON
    with open("top_100_games.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Данные сохранены в top_100_games.json")


if __name__ == "__main__":
    main()
