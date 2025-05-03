import asyncio
import json
import re
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup as bs

# Константы
WINDOWS_CONTAINER_CLASSES = ["game_area_sys_req", "sysreq_content", "active"]
WINDOWS_DATA_OS = "win"
SYS_REQ_BLOCK_CLASS = "game_area_sys_req"
MIN_REQ_CLASS = "game_area_sys_req_leftCol"
REC_REQ_CLASS = "game_area_sys_req_rightCol"
FULL_REQ_CLASS = "game_area_sys_req_full"
LIST_CLASS = "bb_ul"
NOT_SPECIFIED = "не указано"
MAX_GAMES = 5000
BATCH_SIZE = 50


# Функция для удаления HTML-тегов
def strip_html(html_text):
    if not html_text:
        return ""
    soup = bs(html_text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


# Асинхронный HTTP-клиент
async def fetch_url(session, url, retries=5, delay=3):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }
    for attempt in range(retries):
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 429:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                response.raise_for_status()
                return await response.text()
        except aiohttp.ClientError:
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
    return None


async def Top_Games(session):
    all_games = {}
    page = 0
    while len(all_games) < MAX_GAMES:
        url = f"https://steamspy.com/api.php?request=all&page={page}"
        try:
            text = await fetch_url(session, url)
            if not text:
                break
            data = json.loads(text)
            if not data:
                break
            all_games.update(data)
            page += 1
            if len(data) < 1000:  # Если меньше 1000 игр на странице, это последняя
                break
            await asyncio.sleep(1)  # Задержка между запросами страниц
        except Exception:
            break
    return dict(list(all_games.items())[:MAX_GAMES])


async def get_game_data(session, appid):
    url = (
        f"https://store.steampowered.com/api/appdetails?appids={appid}&l=russian&cc=US"
    )
    try:
        text = await fetch_url(session, url)
        if not text:
            return None
        data = json.loads(text)
        if not data[str(appid)]["success"]:
            return None
        return data[str(appid)]["data"]
    except Exception:
        return None


async def get_avg_playtime(session, appid):
    url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
    try:
        text = await fetch_url(session, url)
        if not text:
            return None
        data = json.loads(text)
        avg_playtime_minutes = data.get("average_forever", None)
        return (
            round(avg_playtime_minutes / 60, 2)
            if avg_playtime_minutes is not None
            else None
        )
    except Exception:
        return None


async def parse_system_requirements(session, soup, appid, game_data):
    """Парсинг системных требований только для Windows с запасным вариантом из API."""
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

    def parse_req(req_block, prefix):
        if not req_block:
            return
        items = req_block.find("ul", class_=LIST_CLASS)
        if not items:
            return
        for item in items.find_all("li"):
            text = item.get_text(strip=True)
            if not text:
                continue
            if any(
                keyword in text.lower() for keyword in ["os:", "операционная система:"]
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
                else:
                    sys_req[f"{prefix}_storage_gb"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
            elif "directx:" in text.lower():
                match = re.search(r"DirectX[^\d]*(\d+)", text, re.IGNORECASE)
                if match:
                    sys_req[f"{prefix}_directx"] = f"Version {match.group(1)}"
                else:
                    sys_req[f"{prefix}_directx"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )

    try:
        sys_req_block = soup.find("div", class_=SYS_REQ_BLOCK_CLASS)
        if sys_req_block:
            windows_req = soup.find(
                "div",
                attrs={"data-os": WINDOWS_DATA_OS},
                class_=lambda x: x and "sysreq_content" in x.split(),
            )
            if windows_req:
                min_req = windows_req.find("div", class_=MIN_REQ_CLASS)
                rec_req = windows_req.find("div", class_=REC_REQ_CLASS)
                full_req = windows_req.find("div", class_=FULL_REQ_CLASS)
                if min_req or full_req:
                    if full_req:
                        parse_req(full_req, "min")
                    else:
                        parse_req(min_req, "min")
                        parse_req(rec_req, "rec")
                    return sys_req
    except AttributeError:
        pass

    # Запасной вариант: парсинг из Steam API
    pc_req = game_data.get("pc_requirements", {})
    min_req = pc_req.get("minimum", "")
    rec_req = pc_req.get("recommended", "")

    if min_req:
        soup_min = bs(min_req, "html.parser")
        for li in soup_min.find_all("li"):
            text = li.get_text(strip=True)
            if not text:
                continue
            if any(
                keyword in text.lower() for keyword in ["os:", "операционная система:"]
            ):
                sys_req["os_name"] = (
                    text.split(":", 1)[1].strip() if ":" in text else text
                )
            elif any(
                keyword in text.lower() for keyword in ["processor:", "процессор:"]
            ):
                sys_req["min_cpu"] = (
                    text.split(":", 1)[1].strip() if ":" in text else text
                )
            elif any(
                keyword in text.lower()
                for keyword in ["memory:", "оперативная память:"]
            ):
                match = re.search(r"(\d+\.?\d*)\s*(ГБ|GB)", text, re.IGNORECASE)
                if match:
                    sys_req["min_ram_gb"] = float(match.group(1))
                else:
                    sys_req["min_ram_gb"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
            elif any(
                keyword in text.lower() for keyword in ["graphics:", "видеокарта:"]
            ):
                sys_req["min_gpu"] = (
                    text.split(":", 1)[1].strip() if ":" in text else text
                )
            elif any(
                keyword in text.lower()
                for keyword in ["hard drive:", "storage:", "место на диске:"]
            ):
                match = re.search(r"(\d+\.?\d*)\s*(ГБ|GB)", text, re.IGNORECASE)
                if match:
                    sys_req["min_storage_gb"] = float(match.group(1))
                else:
                    sys_req["min_storage_gb"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
            elif "directx:" in text.lower():
                match = re.search(r"DirectX[^\d]*(\d+)", text, re.IGNORECASE)
                if match:
                    sys_req["min_directx"] = f"Version {match.group(1)}"
                else:
                    sys_req["min_directx"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )

    if rec_req:
        soup_rec = bs(rec_req, "html.parser")
        for li in soup_rec.find_all("li"):
            text = li.get_text(strip=True)
            if not text:
                continue
            if any(keyword in text.lower() for keyword in ["processor:", "процессор:"]):
                sys_req["rec_cpu"] = (
                    text.split(":", 1)[1].strip() if ":" in text else text
                )
            elif any(
                keyword in text.lower()
                for keyword in ["memory:", "оперативная память:"]
            ):
                match = re.search(r"(\d+\.?\d*)\s*(ГБ|GB)", text, re.IGNORECASE)
                if match:
                    sys_req["rec_ram_gb"] = float(match.group(1))
                else:
                    sys_req["rec_ram_gb"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
            elif any(
                keyword in text.lower() for keyword in ["graphics:", "видеокарта:"]
            ):
                sys_req["rec_gpu"] = (
                    text.split(":", 1)[1].strip() if ":" in text else text
                )
            elif any(
                keyword in text.lower()
                for keyword in ["hard drive:", "storage:", "место на диске:"]
            ):
                match = re.search(r"(\d+\.?\d*)\s*(ГБ|GB)", text, re.IGNORECASE)
                if match:
                    sys_req["rec_storage_gb"] = float(match.group(1))
                else:
                    sys_req["rec_storage_gb"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )
            elif "directx:" in text.lower():
                match = re.search(r"DirectX[^\d]*(\d+)", text, re.IGNORECASE)
                if match:
                    sys_req["rec_directx"] = f"Version {match.group(1)}"
                else:
                    sys_req["rec_directx"] = (
                        text.split(":", 1)[1].strip() if ":" in text else text
                    )

    return sys_req


async def parse_steam_page(session, appid, game_data):
    url = f"https://store.steampowered.com/app/{appid}/?cc=US"
    try:
        html = await fetch_url(session, url)
        if not html:
            return {
                "franchise": {
                    "franchise_id": None,
                    "franchise_name": "Не найдено",
                    "franchise_description": "Франшиза не указана",
                },
                "awards": [],
                "system_requirements": await parse_system_requirements(
                    session, None, appid, game_data
                ),
            }

        soup = bs(html, "html.parser")

        franchise = None
        franchise_rows = soup.find_all("div", class_="dev_row")
        for row in franchise_rows:
            label = row.find("b")
            if label and label.text.strip() in ["Franchise", "Франшиза"]:
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

        system_requirements = await parse_system_requirements(
            session, soup, appid, game_data
        )

        return {
            "franchise": franchise,
            "awards": awards,
            "system_requirements": system_requirements,
        }
    except Exception:
        return {
            "franchise": {
                "franchise_id": None,
                "franchise_name": "Не найдено",
                "franchise_description": "Франшиза не указана",
            },
            "awards": [],
            "system_requirements": await parse_system_requirements(
                session, None, appid, game_data
            ),
        }


async def parse_age_rating(session, appid, game_data):
    required_age = game_data.get("required_age", 0)
    if required_age and isinstance(required_age, (int, str)) and int(required_age) > 0:
        return f"{required_age}+", int(required_age)

    url = f"https://store.steampowered.com/app/{appid}/?cc=US"
    try:
        html = await fetch_url(session, url)
        if not html:
            return "0+", 0
        soup = bs(html, "html.parser")
        age_rating = soup.find("div", class_="game_rating_icon")
        if age_rating and age_rating.img:
            rating = age_rating.img["alt"]
            match = re.search(r"(\d+)\+", rating)
            if match:
                return match.group(0), int(match.group(1))
    except Exception:
        pass
    return "0+", 0


async def map_game_to_db(session, game_data, appid):
    try:
        current_time = datetime.now().isoformat()
        age_rating_code, min_age = await parse_age_rating(session, appid, game_data)
        steam_page_data = await parse_steam_page(session, appid, game_data)

        screenshots = game_data.get("screenshots", [])
        header_image_url = (
            screenshots[0]["path_full"]
            if screenshots
            else game_data.get("header_image", "")
        )
        avg_playtime_hours = await get_avg_playtime(session, appid)

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
            "franchise_description": steam_page_data["franchise"][
                "franchise_description"
            ],
            "publisher_name": (
                game_data.get("publishers", [])[0]
                if game_data.get("publishers")
                else None
            ),
            "avg_playtime": avg_playtime_hours,
            "created_at": current_time,
            "updated_at": current_time,
        }

        developers = game_data.get("developers", [])
        genres = [genre["description"] for genre in game_data.get("genres", [])]
        tags = [cat["description"] for cat in game_data.get("categories", [])]
        platforms = [
            plat.capitalize()
            for plat in game_data.get("platforms", [])
            if game_data["platforms"].get(plat)
        ]

        supported_languages = game_data.get("supported_languages", "")
        languages = []
        if supported_languages:
            lang_soup = bs(supported_languages, "html.parser")
            lang_items = [
                item.strip()
                for item in lang_soup.get_text(separator=",").split(",")
                if item.strip()
            ]
            for lang in lang_items:
                clean_lang = re.sub(r"[*]+", "", lang).strip()
                if not clean_lang:
                    continue
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

        play_modes = [
            cat["description"]
            for cat in game_data.get("categories", [])
            if cat["description"] in ["Одиночная игра", "Мультиплеер", "Кооператив"]
        ]
        if not play_modes:
            play_modes = ["Не указано"]

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
        if not connectivity:
            connectivity = ["Оффлайн" if game_data.get("categories") else "Не указано"]

        controllers = [
            {"controller_name": "Gamepad", "notes": cat["description"]}
            for cat in game_data.get("categories", [])
            if cat["description"]
            in ["Поддержка контроллера (полная)", "Поддержка контроллера (частичная)"]
        ]
        if not controllers:
            controllers.append(
                {
                    "controller_name": "Клавиатура",
                    "notes": "Поддержка клавиатуры и мыши по умолчанию",
                }
            )

        awards = [
            {
                "award_name": award["award_name"],
                "image_url": award["image_url"],
                "website_url": award["website_url"],
            }
            for award in steam_page_data["awards"]
        ]

        system_requirements = steam_page_data["system_requirements"]

        result = {
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
                {
                    "trailer_url": movie["mp4"]["max"],
                    "preview_image": movie["thumbnail"],
                }
                for movie in game_data.get("movies", [])
            ],
            "play_modes": play_modes,
            "connectivity": connectivity,
            "controllers": controllers,
            "awards": awards,
            "system_requirements": system_requirements,
        }
        return result
    except Exception:
        return None


async def process_game(session, appid, game_info):
    try:
        game_data = await get_game_data(session, appid)
        if game_data:
            result = await map_game_to_db(session, game_data, appid)
            if result:
                print(f"Успешно обработана игра с appid {appid}")
                return result
    except Exception:
        pass
    return None


async def main():
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        top_games = await Top_Games(session)
        if not top_games:
            return

        filtered_results = []
        game_items = list(top_games.items())
        for i in range(0, len(game_items), BATCH_SIZE):
            batch = game_items[i : i + BATCH_SIZE]
            tasks = [
                process_game(session, appid, game_info) for appid, game_info in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            batch_results = [
                r for r in results if not isinstance(r, Exception) and r is not None
            ]
            filtered_results.extend(batch_results)
            # Сохраняем промежуточные результаты
            with open("top_5000_games.json", "w", encoding="utf-8") as f:
                json.dump(filtered_results, f, ensure_ascii=False, indent=2)
            await asyncio.sleep(2)  # Задержка между партиями

        print(f"Собрано {len(filtered_results)} успешных результатов")


if __name__ == "__main__":
    asyncio.run(main())
