"""High-volume directory discovery: crawl Tabelog for comprehensive
ramen/izakaya candidate lists.

Uses Scrapling (HTTP + TLS fingerprint impersonation) to bypass
Tabelog's anti-bot protection. RamenDB was removed because it returns
403 on all endpoints regardless of fetcher type.

Key discoveries from live validation:
- Tabelog listing pages: /{city}/A{area}/A{subarea}/rstLst/{page}/
  Returns 20 results per page, paginates up to ~50 pages per area.
- Genre codes in URLs are ignored server-side; Tabelog serves generic
  top picks. Genre filtering must happen client-side from detail pages.
- Detail page info (official URL, address, phone) is on the /dtlmenu/
  subpage, not the main detail URL.
"""

from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any

from scrapling import Fetcher

from .contact_crawler import normalize_website_url

TABELOG_BASE = "https://tabelog.com"

# Aggregator hosts to filter out of official URL extraction
AGGREGATOR_HOSTS: tuple[str, ...] = (
    "tabelog.com", "hotpepper.jp", "gnavi.co.jp", "gurunavi.com",
    "retty.me", "hitosara.com", "yahoo.co.jp", "google.com",
    "instagram.com", "facebook.com", "twitter.com", "x.com",
    "line.me", "lin.ee", "tripadvisor.", "yelp.", "mixi.jp",
    "ramendb.supleks.jp", "supleks.jp", "apple.com", "play.google",
    "maps.google", "k-img.com", "kakaku.com", "doubleclick.net",
    "logly.co.jp", "facebook.net", "googlesyndication.com",
)

# Genre keywords for categorization (not filtering — all genres accepted)
RAMEN_GENRE_KEYWORDS = ("ラーメン", "つけ麺", "中華そば", "担々麺", "油そば", "そば", "うどん")
IZAKAYA_GENRE_KEYWORDS = (
    "居酒屋", "ダイニングバー", "バー", "日本酒バー", "酒場",
    "焼鳥", "焼き鳥", "やきとり", "ホルモン", "おでん",
)

# Known chain/franchise name patterns — these are excluded at discovery.
# Substring-matched against the restaurant name from Tabelog listings.
CHAIN_NAME_PATTERNS: tuple[str, ...] = (
    # Ramen chains
    "一蘭", "一風堂", "天下一品", "幸楽苑", "山岡家", "来来亭",
    "ラーメン二郎", "二郎系", "六厘舎", "麺屋武蔵", "とみ田",
    "フジミ", "ぼっけ志", "蒙古タンメン",
    # Izakaya/dining chains
    "鳥貴族", "白木屋", "魚民", "和民", "笑兵", "甘太郎",
    "塩串屋", "世界の山ちゃん", "山ちゃん", "はなの舞",
    # Yakiniku chains
    "牛角", "安安", "焼肉きんぐ", "焼肉ホルモン満腹",
    "成城石井", "ktan",
    # Family restaurant / fast food chains
    "ガスト", "ジョナサン", "バーミヤン", "夢庵", "しゃぶ葉",
    "すき家", "吉野家", "松屋", "はなまるうどん", "丸亀製麺",
    "サイゼリヤ", "大戸屋", "デニーズ", "サガミ", "ココス",
    "マクドナルド", "ロッテリア", "モスバーガー", "ケンタッキー",
    "ドミノ", "ピザハット", "ピザーラ", "日高屋", "まいどおおきに",
    # Hotel/department store restaurants
    "ホテル", "旅館",
)

# Tabelog area sub-areas per city.
# Each entry maps a city to a list of (area_code, sub_area_code) tuples.
# These are Tabelog's internal area hierarchy codes.
TABELOG_CITY_AREAS: dict[str, str] = {
    "Tokyo": "tokyo",
    "Osaka": "osaka",
    "Kyoto": "kyoto",
    "Fukuoka": "fukuoka",
    "Sapporo": "hokkaido",
    "Nagoya": "aichi",
    "Yokohama": "kanagawa",
    "Kobe": "hyogo",
    "Hiroshima": "hiroshima",
    "Nara": "nara",
    "Kanazawa": "ishikawa",
    "Hakone": "kanagawa",
    "Kamakura": "kanagawa",
    "Sendai": "miyagi",
}

# Sub-areas within cities for comprehensive coverage.
# Key: city slug used in Tabelog URL, Value: list of sub-area paths.
TABELOG_SUB_AREAS: dict[str, list[str]] = {
    "tokyo": [
        "A1301/A130101",  # Ginza
        "A1301/A130102",  # Yurakucho/Hibiya
        "A1302/A130201",  # Tokyo/Nihombashi
        "A1302/A130202",  # Otemachi/Marunouchi
        "A1303/A130301",  # Shibuya
        "A1303/A130302",  # Ebisu
        "A1303/A130303",  # Daikanyama/Nakameguro
        "A1304/A130401",  # Shinjuku
        "A1304/A130402",  # Yoyogi/Hatagaya
        "A1305/A130501",  # Ikebukuro
        "A1305/A130503",  # Takadanobaba
        "A1306/A130601",  # Akasaka/Nagatacho
        "A1307/A130701",  # Roppongi
        "A1307/A130702",  # Azabu/Hiroo
        "A1308/A130801",  # Akasaka
        "A1309/A130905",  # Kanda/Jimbocho
        "A1311/A131101",  # Akihabara
        "A1312/A131201",  # Ueno
        "A1313/A131301",  # Asakusa
        "A1316/A131601",  # Nakano
        "A1316/A131602",  # Koenji/Asagaya
        "A1317/A131701",  # Shimokitazawa
        "A1319/A131901",  # Kichijoji
        "A1320/A132001",  # Kagurazaka
        "A1321/A132101",  # Monzen-Nakacho/Kiyosumi
    ],
    "osaka": [
        "A2701/A270101",  # Umeda
        "A2701/A270102",  # Namba
        "A2702/A270201",  # Shinsaibashi
        "A2703/A270301",  # Tenma
        "A2704/A270401",  # Kyobashi
        "A2710/A271001",  # Tennoji
    ],
    "kyoto": [
        "A2601/A260101",  # Kawaramachi
        "A2602/A260201",  # Kyoto Station
        "A2603/A260301",  # Gion
        "A2604/A260401",  # Kiyamachi
    ],
    "fukuoka": [
        "A4001/A400101",  # Tenjin
        "A4001/A400102",  # Hakata
        "A4002/A400201",  # Nakasu
    ],
    "kanagawa": [
        "A1401/A140101",  # Yokohama Station
        "A1401/A140102",  # Minatomirai
        "A1402/A140201",  # Kamakura
        "A1406/A140601",  # Hakone
    ],
    "hokkaido": [
        "A0101/A010101",  # Sapporo Susukino
        "A0101/A010102",  # Sapporo Odori
        "A0101/A010103",  # Sapporo Tanukikoji
        "A0102/A010201",  # Sapporo Station
        "A0103/A010301",  # Shiroishi/Atsubetsu
        "A0104/A010401",  # Toyohira
    ],
    "aichi": [
        "A2301/A230101",  # Nagoya Station
        "A2301/A230102",  # Sakae
        "A2302/A230201",  # Nishiki/Yaba-cho
        "A2304/A230401",  # Kanayama
    ],
}

TABELOG_CATEGORY_PATHS: dict[str, list[str]] = {
    "all": ["ramen", "izakaya"],
    "ramen": ["ramen"],
    "izakaya": ["izakaya"],
}

# Shared fetcher instance (reuses connection pool and TLS config)
_fetcher: Fetcher | None = None


def _get_fetcher() -> Fetcher:
    """Return a shared Fetcher instance."""
    global _fetcher
    if _fetcher is None:
        _fetcher = Fetcher()
    return _fetcher


@dataclass
class DirectoryCandidate:
    name: str
    website: str
    address: str = ""
    phone: str = ""
    rating: float | None = None
    review_count: int | None = None
    source: str = ""
    source_url: str = ""
    category: str = ""
    city: str = ""


@dataclass
class TabelogPageResult:
    city: str
    category: str
    page: int
    listing_url: str
    listing_count: int
    detail_fetches: int
    exhausted: bool
    candidates: list[DirectoryCandidate]
    area_path: str = ""


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _is_official_url(url: str) -> bool:
    """Check if a URL is an official restaurant website (not aggregator/social)."""
    host = urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")
    if not host:
        return False
    return not any(token in host for token in AGGREGATOR_HOSTS)


def _is_chain(name: str) -> bool:
    """Check if a restaurant name matches a known chain pattern."""
    return any(chain in name for chain in CHAIN_NAME_PATTERNS)


def _extract_detail_links(html: str) -> list[dict[str, str]]:
    """Extract restaurant detail page links from a Tabelog listing page.

    Detail URLs match pattern: tabelog.com/{city}/A{area}/A{subarea}/{id}/
    """
    listings: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    pattern = re.compile(
        r'<a[^>]*href="(https://tabelog\.com/[a-z]+/A\d+/A\d+/\d+/)"[^>]*>([^<]{2,120})</a>'
    )
    for match in pattern.finditer(html):
        url = match.group(1)
        name = _clean_text(match.group(2))
        if url in seen_urls or not name:
            continue
        seen_urls.add(url)
        listings.append({"url": url, "name": name})
    return listings


def _extract_official_url_from_dtlmenu(html: str) -> str:
    """Extract official website URL from Tabelog /dtlmenu/ page.

    The pattern is: <th>ホームページ</th> ... <p class="homepage"><a href="...">
    """
    hp_match = re.search(
        r'<th>ホームページ</th>\s*<td>\s*<p[^>]*class="homepage"[^>]*>\s*<a[^>]*href="([^"]+)"',
        html,
        re.DOTALL,
    )
    if hp_match:
        url = normalize_website_url(hp_match.group(1))
        if url and _is_official_url(url):
            return url
    return ""


def _extract_address_from_dtlmenu(html: str) -> str:
    """Extract address from Tabelog /dtlmenu/ page."""
    match = re.search(r'<th>住所</th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL)
    if match:
        return _clean_text(re.sub(r'<[^>]+>', '', match.group(1)))
    return ""


def _extract_phone_from_dtlmenu(html: str) -> str:
    """Extract phone number from Tabelog /dtlmenu/ page."""
    match = re.search(r'<th>電話番号</th>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL)
    if match:
        return _clean_text(re.sub(r'<[^>]+>', '', match.group(1)))
    return ""


def _extract_genres_from_dtlmenu(html: str) -> list[str]:
    """Extract genre/category tags from Tabelog detail page for client-side filtering."""
    # Genre text in the header subinfo section
    genres: list[str] = []
    for match in re.finditer(
        r'class="[^"]*rdheader-subinfo__genre-text[^"]*"[^>]*>([^<]+)', html
    ):
        text = match.group(1).strip()
        if text:
            genres.append(text)
    # Also try catching genre from the breadcrumb/link patterns
    if not genres:
        for match in re.finditer(
            r'<span[^>]*class="[^"]*linktree__parent-target-text[^"]*"[^>]*>([^<]+)', html
        ):
            text = match.group(1).strip()
            if text and text not in genres:
                genres.append(text)
    return genres


def _classify_genre(genres: list[str], *, category: str) -> str:
    """Return 'ramen', 'izakaya', or 'restaurant' based on genre tags.

    Never returns None — all restaurants are accepted. The category
    parameter is used to prefer a specific label when both match.
    """
    genre_text = " ".join(genres)
    is_ramen = any(kw in genre_text for kw in RAMEN_GENRE_KEYWORDS)
    is_izakaya = any(kw in genre_text for kw in IZAKAYA_GENRE_KEYWORDS)

    if is_ramen:
        return "ramen"
    if is_izakaya:
        return "izakaya"
    return "restaurant"


def _extract_rating_from_dtlmenu(html: str) -> tuple[float | None, int | None]:
    """Extract rating and review count from Tabelog /dtlmenu/ page."""
    rating = None
    review_count = None
    # Rating: look for <b class="...ratingval...">X.XX</b>
    rating_match = re.search(r'<b[^>]*class="[^"]*ratingval[^"]*"[^>]*>([0-3]\.\d{2})</b>', html)
    if not rating_match:
        rating_match = re.search(r'([0-3]\.\d{2})</b>', html)
    if rating_match:
        try:
            rating = float(rating_match.group(1))
        except ValueError:
            pass
    # Review count
    review_match = re.search(r'([0-9,]+)\s*件', html)
    if review_match:
        try:
            review_count = int(review_match.group(1).replace(",", ""))
        except ValueError:
            pass
    return rating, review_count


def _get_sub_areas_for_city(city: str) -> list[str]:
    """Return Tabelog sub-area paths for a city."""
    city_slug = TABELOG_CITY_AREAS.get(city, city.lower())
    return TABELOG_SUB_AREAS.get(city_slug, [])


def tabelog_sub_area_paths_for_city(city: str) -> list[str]:
    """Return configured Tabelog sub-area paths for a city."""
    return list(_get_sub_areas_for_city(city))


def crawl_tabelog_area(
    *,
    city: str,
    category: str = "ramen",
    max_pages: int = 50,
    max_detail_fetches: int = 500,
    delay_seconds: float = 0.5,
    timeout: int = 10,
) -> list[DirectoryCandidate]:
    """Crawl Tabelog for ramen/izakaya candidates in a city.

    Paginates through area-specific listing pages, then fetches each
    restaurant's /dtlmenu/ page to extract official URL, address, phone,
    and genre tags. Filters by genre client-side since Tabelog ignores
    genre codes in listing URLs.
    """
    fetcher = _get_fetcher()
    city_slug = TABELOG_CITY_AREAS.get(city, city.lower())
    sub_areas = _get_sub_areas_for_city(city)

    candidates: list[DirectoryCandidate] = []
    seen_websites: set[str] = set()
    seen_detail_urls: set[str] = set()
    detail_fetches = 0

    # City-wide category pages avoid multiplying generic area listings while
    # still paginating through the target city/category result set.
    area_paths: list[str | None] = [None]
    category_paths = TABELOG_CATEGORY_PATHS.get(category, TABELOG_CATEGORY_PATHS["all"])

    for area_path in area_paths:
        if detail_fetches >= max_detail_fetches:
            break

        for category_path in category_paths:
            if detail_fetches >= max_detail_fetches:
                break

            for page in range(1, max_pages + 1):
                if detail_fetches >= max_detail_fetches:
                    break

                url = _tabelog_listing_url(
                    city_slug=city_slug,
                    category_path=category_path,
                    page=page,
                    area_path=area_path,
                )

                try:
                    resp = fetcher.get(url, timeout=timeout)
                    if resp.status != 200:
                        break
                    html = resp.html_content
                except Exception:
                    break

                listings = _extract_detail_links(html)
                if not listings:
                    break  # No more results for this area/category.

                for listing in listings:
                    if detail_fetches >= max_detail_fetches:
                        break

                    detail_url = listing["url"]

                    # Skip already-seen detail URLs (same restaurant can appear
                    # on multiple area/category listing pages).
                    if detail_url in seen_detail_urls:
                        continue
                    seen_detail_urls.add(detail_url)

                    name = listing["name"]

                    # Skip known chains — no point emailing them.
                    if _is_chain(name):
                        continue

                    # Fetch the /dtlmenu/ subpage for structured data.
                    dtlmenu_url = detail_url.rstrip("/") + "/dtlmenu/"
                    try:
                        detail_resp = fetcher.get(dtlmenu_url, timeout=timeout)
                        if detail_resp.status != 200:
                            # Some pages don't have /dtlmenu/; skip.
                            continue
                        detail_html = detail_resp.html_content
                        detail_fetches += 1
                    except Exception:
                        continue

                    if delay_seconds > 0:
                        time.sleep(delay_seconds)

                    genres = _extract_genres_from_dtlmenu(detail_html)
                    matched_category = _classify_genre(genres, category=category)
                    if matched_category == "restaurant" and category in {"ramen", "izakaya"}:
                        matched_category = category

                    # Extract official URL.
                    official_url = _extract_official_url_from_dtlmenu(detail_html)
                    if not official_url:
                        continue

                    # Dedup by website host.
                    website_host = urllib.parse.urlparse(official_url).netloc.lower().removeprefix("www.")
                    if website_host in seen_websites:
                        continue
                    seen_websites.add(website_host)

                    address = _extract_address_from_dtlmenu(detail_html)
                    phone = _extract_phone_from_dtlmenu(detail_html)
                    rating, review_count = _extract_rating_from_dtlmenu(detail_html)

                    candidates.append(DirectoryCandidate(
                        name=name,
                        website=official_url,
                        address=address,
                        phone=phone,
                        rating=rating,
                        review_count=review_count,
                        source="tabelog",
                        source_url=detail_url,
                        category=matched_category,
                        city=city,
                    ))

    return candidates


def crawl_tabelog_listing_page(
    *,
    city: str,
    category: str,
    page: int,
    area_path: str | None = None,
    timeout: int = 10,
    delay_seconds: float = 0.0,
) -> TabelogPageResult:
    """Fetch one city/category Tabelog listing page for checkpointed crawls."""
    fetcher = _get_fetcher()
    city_slug = TABELOG_CITY_AREAS.get(city, city.lower())
    category_paths = TABELOG_CATEGORY_PATHS.get(category, [category])
    category_path = category_paths[0]
    listing_url = _tabelog_listing_url(
        city_slug=city_slug,
        category_path=category_path,
        page=page,
        area_path=area_path,
    )

    try:
        resp = fetcher.get(listing_url, timeout=timeout)
        if resp.status != 200:
            return TabelogPageResult(city, category, page, listing_url, 0, 0, True, [], area_path or "")
        html = resp.html_content
    except Exception:
        return TabelogPageResult(city, category, page, listing_url, 0, 0, True, [], area_path or "")

    listings = _extract_detail_links(html)
    if not listings:
        return TabelogPageResult(city, category, page, listing_url, 0, 0, True, [], area_path or "")

    candidates: list[DirectoryCandidate] = []
    seen_websites: set[str] = set()
    detail_fetches = 0
    for listing in listings:
        name = listing["name"]
        if _is_chain(name):
            continue
        detail_url = listing["url"]
        dtlmenu_url = detail_url.rstrip("/") + "/dtlmenu/"
        try:
            detail_resp = fetcher.get(dtlmenu_url, timeout=timeout)
            if detail_resp.status != 200:
                continue
            detail_html = detail_resp.html_content
            detail_fetches += 1
        except Exception:
            continue
        if delay_seconds > 0:
            time.sleep(delay_seconds)

        official_url = _extract_official_url_from_dtlmenu(detail_html)
        if not official_url:
            continue
        website_host = urllib.parse.urlparse(official_url).netloc.lower().removeprefix("www.")
        if website_host in seen_websites:
            continue
        seen_websites.add(website_host)

        genres = _extract_genres_from_dtlmenu(detail_html)
        matched_category = _classify_genre(genres, category=category)
        if matched_category == "restaurant" and category in {"ramen", "izakaya"}:
            matched_category = category
        candidates.append(DirectoryCandidate(
            name=name,
            website=official_url,
            address=_extract_address_from_dtlmenu(detail_html),
            phone=_extract_phone_from_dtlmenu(detail_html),
            rating=_extract_rating_from_dtlmenu(detail_html)[0],
            review_count=_extract_rating_from_dtlmenu(detail_html)[1],
            source="tabelog",
            source_url=detail_url,
            category=matched_category,
            city=city,
        ))

    return TabelogPageResult(city, category, page, listing_url, len(listings), detail_fetches, False, candidates, area_path or "")


def _tabelog_listing_url(*, city_slug: str, category_path: str, page: int, area_path: str | None = None) -> str:
    page_suffix = "" if page == 1 else f"{page}/"
    if area_path:
        return f"{TABELOG_BASE}/{city_slug}/{area_path}/rstLst/{category_path}/{page_suffix}"
    return f"{TABELOG_BASE}/{city_slug}/rstLst/{category_path}/{page_suffix}"


def discover_area_candidates(
    *,
    city: str,
    category: str = "all",
    max_pages: int = 50,
    max_detail_fetches: int = 500,
    delay_seconds: float = 0.5,
    timeout: int = 10,
    sources: tuple[str, ...] = ("tabelog",),
) -> list[DirectoryCandidate]:
    """High-volume directory discovery for a city.

    Crawls Tabelog for comprehensive ramen/izakaya lists with official
    website URLs. Genre filtering is done client-side from detail pages.

    Args:
        city: City name (e.g. "Tokyo", "Osaka")
        category: "ramen", "izakaya", or "all"
        max_pages: Max listing pages to crawl per sub-area
        max_detail_fetches: Max detail page fetches total
        delay_seconds: Delay between detail page requests (rate limiting)
        timeout: HTTP timeout per request (unused by Scrapling but kept for API compat)
        sources: Which directory sources to use (only "tabelog" supported)

    Returns:
        List of DirectoryCandidate with official website URLs.
    """
    all_candidates: list[DirectoryCandidate] = []
    seen_websites: set[str] = set()

    for source in sources:
        if source == "tabelog":
            source_candidates = crawl_tabelog_area(
                city=city,
                category=category,
                max_pages=max_pages,
                max_detail_fetches=max_detail_fetches,
                delay_seconds=delay_seconds,
                timeout=timeout,
            )
        else:
            continue

        # Dedup across sources
        for candidate in source_candidates:
            host = urllib.parse.urlparse(candidate.website).netloc.lower().removeprefix("www.")
            if host and host not in seen_websites:
                seen_websites.add(host)
                all_candidates.append(candidate)

    return all_candidates
