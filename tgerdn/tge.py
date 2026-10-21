"""Pobieranie i parsowanie ceny Fixing I ze strony TGE.

Dwie niezalezne rzeczy:
  - `fetch()`          - HTTP (urllib, standardowa biblioteka),
  - `parse_fixings()`  - czysta funkcja na HTML-u, testowalna bez sieci.

Strona TGE oznacza sekcje Fixing I komentarzami HTML
(`<!-- Fixing I start -->` / `<!-- Fixing I end -->`), wiec kolumne z kursem
rozpoznajemy po tych znacznikach, a nie po numerze kolumny. Awaryjnie
uzywamy naglowka ("Kurs [PLN/MWh]").

Konwencja TGE: doba handlowa to H01..H24, gdzie H01 = 00:00-01:00.
Ceny na dobe `D` sa publikowane na stronie z data `D-1`.
"""

from __future__ import annotations

import gzip
import logging
import re
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0 Safari/537.36'
)
DATE_FORMAT = '%d-%m-%Y'
ROW_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_H(\d{1,2})$')
PRICE_RE = re.compile(r'^-?\d+(?:[.,]\d+)?$')
PRICE_COLUMN_MARKER = 'kurs [pln/mwh]'
DATE_COLUMN_MARKER = 'data dostawy'
# Rozsadny widełek kursu (PLN/MWh) - poza nim to nie cena.
PRICE_LIMITS = (-100_000.0, 100_000.0)


class FetchError(RuntimeError):
    """Pobranie strony nie powiodlo sie."""


@dataclass(frozen=True)
class RawFixing:
    """Wiersz tabeli Fixing I - jeszcze surowy, w PLN/MWh."""

    day: str
    hour: int
    price_pln_mwh: float


class _Cell:
    """Pojedyncza komorka tabeli."""

    __slots__ = ('text', 'is_header', 'in_fixing')

    def __init__(self, text: str = '', is_header: bool = False, in_fixing: bool = False):
        self.text = text
        self.is_header = is_header
        self.in_fixing = in_fixing

    def __repr__(self) -> str:  # pragma: no cover - tylko do debugowania
        return f'_Cell({self.text!r}, in_fixing={self.in_fixing})'


class _TableParser(HTMLParser):
    """Zbiera wiersze tabel z HTML-a i pamieta, gdzie zaczyna sie sekcja Fixing I."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_Cell]] = []
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None
        self._in_fixing = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == 'tr':
            self._row = []
        elif tag in ('td', 'th'):
            self._cell = _Cell(text='', is_header=tag == 'th', in_fixing=self._in_fixing)
        elif tag == 'br' and self._cell is not None:
            self._cell.text += ' '

    def handle_endtag(self, tag: str) -> None:
        if tag in ('td', 'th') and self._cell is not None:
            if self._row is not None:
                self._row.append(self._cell)
            self._cell = None
        elif tag == 'tr' and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.text += data

    def handle_comment(self, data: str) -> None:
        low = data.lower()
        if 'fixing i start' in low:
            self._in_fixing = True
        elif 'fixing i end' in low:
            self._in_fixing = False


def _to_price(text: str) -> float | None:
    """Zamienia tekst komorki na liczbe (albo None, gdy to nie cena)."""
    cleaned = re.sub(r'\s+', '', text or '').replace('\xa0', '')
    if not cleaned or cleaned in {'-', '--', 'n/a'}:
        return None
    if not PRICE_RE.match(cleaned):
        return None
    try:
        value = float(cleaned.replace(',', '.'))
    except ValueError:
        return None
    low, high = PRICE_LIMITS
    if not low <= value <= high:
        return None
    return value


def _price_column_index(rows: list[list[_Cell]]) -> int | None:
    """Indeks kolumny z kursem Fixing I (z naglowka)."""
    for row in rows:
        texts = [cell.text.strip() for cell in row]
        if not any(DATE_COLUMN_MARKER in text.lower() for text in texts):
            continue
        for index, cell in enumerate(row):
            if cell.in_fixing:
                return index
        for index, text in enumerate(texts):
            if PRICE_COLUMN_MARKER in text.lower():
                return index
    return None


def parse_fixings(html: str | bytes) -> list[RawFixing]:
    """Parsuje wszystkie wiersze Fixing I ze strony TGE.

    Args:
        html: zawartosc strony (str lub bytes).

    Returns:
        Lista `RawFixing` posortowana po dacie i godzinie.
        Pusta lista, gdy na stronie nie ma tabeli Fixing I.
    """
    if isinstance(html, bytes):
        html = html.decode('utf-8', errors='replace')

    parser = _TableParser()
    parser.feed(html)
    parser.close()

    price_index = _price_column_index(parser.rows)
    found: dict[tuple[str, int], float] = {}

    for row in parser.rows:
        if not row:
            continue
        match = ROW_RE.match(row[0].text.strip())
        if not match:
            continue

        day, hour = match.group(1), int(match.group(2))
        if not 1 <= hour <= 24:
            continue

        price = None
        for cell in row[1:]:
            if cell.in_fixing:
                # Pierwsza komorka w sekcji Fixing I to kurs - kolejna to wolumen.
                price = _to_price(cell.text)
                break
        if price is None and price_index is not None and price_index < len(row):
            price = _to_price(row[price_index].text)
        if price is None:
            continue

        found.setdefault((day, hour), price)

    return [RawFixing(day, hour, price) for (day, hour), price in sorted(found.items())]


def page_date_for(delivery: date) -> date:
    """TGE publikuje ceny na dobe `delivery` na stronie z data `delivery - 1 dzien`."""
    return delivery - timedelta(days=1)


def url_for(base_url: str, delivery: date) -> str:
    """Adres strony TGE z cunami na wskazana dobe dostawy."""
    return f'{base_url}?dateShow={page_date_for(delivery).strftime(DATE_FORMAT)}&type=1'


def fetch(url: str, *, timeout: float = 30.0, retries: int = 3, backoff: float = 2.0) -> bytes:
    """Pobiera strone z obsluga gzip i ponawianiem po bledach.

    Raises:
        FetchError: gdy po wszystkich probach pobranie sie nie powiodlo.
    """
    last_error: Exception | None = None

    for attempt in range(1, max(1, retries) + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': USER_AGENT,
                    'Accept': 'text/html,application/xhtml+xml',
                    'Accept-Language': 'pl-PL,pl;q=0.9',
                    'Accept-Encoding': 'gzip, deflate',
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                encoding = (response.headers.get('Content-Encoding') or '').lower()

            if encoding == 'gzip':
                payload = gzip.decompress(payload)
            elif encoding == 'deflate':
                payload = zlib.decompress(payload, -zlib.MAX_WBITS)
            return payload
        except (urllib.error.URLError, OSError, ValueError) as error:
            last_error = error
            if attempt < retries:
                wait = backoff * attempt
                logger.warning('Pobieranie nieudane (%s/%s): %s - ponawiam za %.0fs',
                               attempt, retries, error, wait)
                time.sleep(wait)

    raise FetchError(f'Nie udalo sie pobrac {url}: {last_error}') from last_error
