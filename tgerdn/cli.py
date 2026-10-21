"""Interfejs wiersza polecen.

    tgerdn fetch      - pobiera ceny i zapisuje pliki dla Home Assistant
    tgerdn show       - wypisuje plan ladowania z ostatniego zapisu
    tgerdn simulate   - symuluje cala dobe ladowania na prawdziwych szablonach
    tgerdn doctor     - szybka diagnostyka konfiguracji i danych
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path

from .config import Settings, Tariff
from .model import DayPrices
from .planner import build_day_prices, build_plan, merge_plan, now_iso
from .publisher import build_payload, empty_payload, read_payload, write_payload
from .tge import FetchError, fetch, parse_fixings, url_for

logger = logging.getLogger('tgerdn')

FILES = {
    'today': 'today.json',
    'tomorrow': 'tomorrow.json',
}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s %(levelname)-7s %(message)s',
        datefmt='%H:%M:%S',
    )


def _target_days(names: list[str] | None, today: date) -> list[tuple[str, date]]:
    """Zamienia nazwy ('today', 'tomorrow', YYYY-MM-DD) na pary (etykieta, data)."""
    out: list[tuple[str, date]] = []
    for name in names or ['today', 'tomorrow']:
        if name == 'today':
            out.append(('today', today))
        elif name == 'tomorrow':
            out.append(('tomorrow', date.fromordinal(today.toordinal() + 1)))
        else:
            out.append(('today', date.fromisoformat(name)))
    return out


def _fetch_day(day: date, settings: Settings) -> tuple[str, list, str]:
    """Pobiera strone dla doby. Zwraca (status, fixings, url)."""
    url = url_for(settings.base_url, day)
    try:
        payload = fetch(url, timeout=settings.timeout, retries=settings.retries)
    except FetchError as error:
        logger.error('%s', error)
        return 'error', [], url

    fixings = parse_fixings(payload)
    days = {fixing.day for fixing in fixings}
    if days:
        logger.info('Pobrano %s (%s), wiersze dla: %s',
                    url, len(fixings), ', '.join(sorted(days)))
    else:
        logger.warning('Pobrano %s, ale nie ma tabeli Fixing I', url)
    return 'ok', fixings, url


def _settings_from_args(args: argparse.Namespace) -> Settings:
    """Zlacza ustawienia ze srodowiska z opcjami z wiersza polecen."""
    settings = Settings.from_env()
    return settings.with_overrides(
        output_dir=getattr(args, 'output_dir', None),
        tariff=Tariff.from_env().with_overrides(
            charging_hours=getattr(args, 'charging_hours', None),
            window_margin=getattr(args, 'window_margin', None),
            day_margin=getattr(args, 'day_margin', None),
        ),
    )


def _fetch_all(settings: Settings, days: list[str] | None) -> int:
    """Pobiera ceny i zapisuje pliki. Zwraca liczbe zapisanych plikow."""
    output_dir: Path = settings.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today()
    targets = _target_days(days, today)
    written = 0
    failed = 0

    for label, delivery in targets:
        status, fixings, url = _fetch_day(delivery, settings)

        if status == 'error':
            failed += 1
            continue

        day_str = delivery.isoformat()
        day_prices = build_day_prices(
            day_str,
            fixings,
            settings.tariff,
            fetched_at=now_iso(),
            source_url=url,
        )

        path = output_dir / FILES.get(label, FILES['today'])
        previous = read_payload(path)

        if not day_prices.hours:
            # TGE nie opublikowal jeszcze tej doby - zapisujemy pusty payload,
            # zeby karta w HA pokazala "Brak danych" zamiast cudzych danych.
            payload = empty_payload(day_str, settings.tariff, label=label, source=url)
            write_payload(path, payload)
            continue

        plan = build_plan(day_prices, settings.tariff)
        if previous and previous.get('day') == day_str:
            plan = merge_plan(previous.get('plan'), plan)

        payload = build_payload(day_prices, plan, settings.tariff, label=label)
        if write_payload(path, payload):
            written += 1
            _log_plan(day_prices, plan)

    if written:
        logger.info('Gotowe: zapisano %d plikow w %s', written, output_dir)
    else:
        logger.error('Nie udalo sie pobrac zadnych danych (blad: %d)', failed)
    return written


def cmd_fetch(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    return 0 if _fetch_all(settings, getattr(args, 'day', None)) else 1


def _parse_run_times(value: str) -> list[time]:
    """'00:01,12:01' -> [(0, 1), (12, 1)]."""
    times: list[time] = []
    for part in (value or '').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            times.append(datetime.strptime(part, '%H:%M').time())
        except ValueError:
            logger.error('Nieprawidlowa godzina pobierania: %r (oczekiwano HH:MM)', part)
    if not times:
        times = [time(0, 1), time(12, 1)]
        logger.warning('Brak poprawnych godzin - uzywam domyslnych: 00:01, 12:01')
    return sorted(times)


def _next_run(now: datetime, times: list[time]) -> datetime:
    """Najblizsza nastepna godzina pobierania (po teraz)."""
    candidates = []
    for run_time in times:
        candidate = now.replace(hour=run_time.hour, minute=run_time.minute,
                                second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        candidates.append(candidate)
    return min(candidates)


def cmd_serve(args: argparse.Namespace) -> int:
    """Tryb dodatku HA - pobiera cyklicznie i czeka do kolejnej godziny."""
    settings = _settings_from_args(args)
    times = _parse_run_times(args.hour)
    stop = threading.Event()

    def _stop(signum, frame):  # pragma: no cover - sygnal z kontenera
        logger.info('Otrzymano sygnal %s - koncze...', signum)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _stop)
        except ValueError:  # pragma: no cover - nie glowny watek
            pass

    logger.info('tgerdn serve: katalog %s, pobieranie o %s',
                settings.output_dir, ', '.join(t.strftime('%H:%M') for t in times))

    while not stop.is_set():
        _fetch_all(settings, getattr(args, 'day', None))

        target = _next_run(datetime.now(), times)
        logger.info('Nastepne pobieranie: %s', target.strftime('%Y-%m-%d %H:%M'))

        while not stop.is_set():
            remaining = (target - datetime.now()).total_seconds()
            if remaining <= 0:
                break
            stop.wait(min(remaining, 30.0))

    logger.info('tgerdn serve: zatrzymano')
    return 0


def _format_window(hours: list[int]) -> str:
    """Zamienia godziny TGE na czytelne przedzialy, np. '02:00-05:00, 13:00-15:00'."""
    if not hours:
        return '-'
    blocks: list[list[int]] = []
    for hour in sorted(hours):
        if blocks and hour == blocks[-1][-1] + 1:
            blocks[-1].append(hour)
        else:
            blocks.append([hour])
    parts = []
    for block in blocks:
        start = block[0] - 1
        end = block[-1]
        parts.append(f'{start:02d}:00-{end:02d}:00')
    return ', '.join(parts)


def _log_plan(day_prices: DayPrices, plan) -> None:
    logger.info(
        'Plan %s: okno %s (%d h) | najtansza %02d:00 = %.4f | najdroższa %02d:00 = %.4f | srednia %.4f',
        day_prices.day,
        _format_window(list(plan.hours)),
        len(plan.hours),
        plan.cheapest_hour - 1,
        plan.cheapest_price,
        plan.dearest_hour - 1,
        plan.dearest_price,
        plan.day_avg,
    )


def cmd_show(args: argparse.Namespace) -> int:
    settings = Settings.from_env().with_overrides(output_dir=args.output_dir)
    label = args.which
    path = settings.output_dir / FILES[label]
    payload = read_payload(path)

    if payload is None:
        logger.error('Brak pliku %s - uruchom najpierw "tgerdn fetch"', path)
        return 1

    print(f'\nTGE RDN - {payload.get("day")} ({label})')
    print('-' * 62)
    print(f'  pobrano:      {payload.get("fetched_at") or "-"}')
    print(f'  zrodlo:       {payload.get("source") or "-"}')
    print(f'  godziny:      {payload.get("data_points")}')

    plan = payload.get('plan')
    if not plan:
        print('  plan:         brak danych')
        return 0

    print(f'  okno lad. ({plan["count"]} h): {_format_window(list(plan["hours"]))}')
    print(f'  najtansza:    {plan["cheapest_hour"] - 1:02d}:00 -> {plan["cheapest_price"]:.4f} PLN/kWh')
    print(f'  najdrozsza:   {plan["dearest_hour"] - 1:02d}:00 -> {plan["dearest_price"]:.4f} PLN/kWh')
    print(f'  srednia doby: {plan["day_avg"]:.4f} PLN/kWh')
    print(f'  w oknie:      {plan["cost_avg"]:.4f} PLN/kWh  vs  najdrozsze: {plan["cost_worst"]:.4f}')
    print(f'  oszczednosc:  {plan["saving"]:.4f} PLN/kWh')
    for kwh in (10, 20, 50):
        cost_window = plan['cost_avg'] * kwh
        cost_worst = plan['cost_worst'] * kwh
        print(f'    {kwh:>3} kWh: {cost_window:>6.2f} zl w oknie  '
              f'(vs {cost_worst:>6.2f} zl w najdrozszych godzinach, '
              f'oszczednosc {cost_worst - cost_window:.2f} zl)')
    print()
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    from .simulate import run_scenarios

    return run_scenarios(verbose=not args.quiet)


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = Settings.from_env().with_overrides(output_dir=args.output_dir)
    output_dir: Path = settings.output_dir
    print('\nTGE RDN - diagnostyka')
    print(f'  katalog:      {output_dir} '
          f'({"istnieje" if output_dir.is_dir() else "BRAK - utworze go przy pierwszym fetch"})')
    print(f'  taryfa:       okno {settings.tariff.window_margin} / dzien {settings.tariff.day_margin} '
          f'PLN/kWh, {settings.tariff.charging_hours} h, progi '
          f'{settings.tariff.charge_below}/{settings.tariff.stop_above}')

    problems = 0
    for label, name in FILES.items():
        path = output_dir / name
        payload = read_payload(path)
        if payload is None:
            print(f'  {name:<14} BRAK')
            problems += 1
            continue
        fetched = payload.get('fetched_at')
        age = '-'
        if fetched:
            try:
                moment = datetime.fromisoformat(fetched)
                hours = (datetime.now().astimezone() - moment).total_seconds() / 3600
                age = f'{hours:.1f} h temu'
            except ValueError:
                age = '?'
        ok = 'OK  ' if payload.get('data_fetched') else 'PUSTE'
        print(f'  {name:<14} {ok}  {payload.get("data_points")} godzin, '
              f'day={payload.get("day")}, pobrano {age}')
        if payload.get('plan'):
            print(f'  {"":<14} okno: {_format_window(list(payload["plan"]["hours"]))}')

    print()
    if problems:
        print(f'  Znaleziono {problems} problem(y) - uruchom "tgerdn fetch".')
        return 1
    print('  Wszystko w porzadku.')
    return 0


def build_parser() -> argparse.ArgumentParser:
    # `-v` moze wystapic przed albo po nazwie podkomendy.
    verbose = argparse.ArgumentParser(add_help=False)
    verbose.add_argument('-v', '--verbose', action='store_true', default=argparse.SUPPRESS,
                          help='wiecej szczegolow')

    parser = argparse.ArgumentParser(
        prog='tgerdn',
        parents=[verbose],
        description='Ceny energii TGE RDN dla Home Assistant.',
    )
    sub = parser.add_subparsers(dest='command')

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument('--output-dir', default=None,
                        help='katalog na pliki JSON (domyslnie ~/.local/share/tgerdn)')

    fetch = sub.add_parser('fetch', parents=[verbose], help='pobierz ceny i zapisz pliki dla HA')
    add_common(fetch)
    fetch.add_argument('--day', action='append',
                        choices=['today', 'tomorrow'],
                        help='ktora dobe pobrac (mozna powtorzyc, domyslnie obie)')
    fetch.add_argument('--charging-hours', type=int, default=None,
                        help='ile godzin dziennie ladujemy w najtanszym oknie')
    fetch.add_argument('--window-margin', type=float, default=None,
                        help='margines dostawy w godzinach okienkowych')
    fetch.add_argument('--day-margin', type=float, default=None,
                        help='margines dostawy w godzinach dziennych')
    fetch.set_defaults(func=cmd_fetch)

    serve = sub.add_parser('serve', parents=[verbose],
                            help='pobieraj cyklicznie (tryb dodatku HA)')
    add_common(serve)
    serve.add_argument('--hour', default='00:01,12:01',
                        help='godziny pobierania po przecinku (domyslnie 00:01,12:01)')
    serve.add_argument('--charging-hours', type=int, default=None,
                       help='ile godzin dziennie ladujemy w najtanszym oknie')
    serve.add_argument('--window-margin', type=float, default=None,
                       help='margines dostawy w godzinach okienkowych')
    serve.add_argument('--day-margin', type=float, default=None,
                       help='margines dostawy w godzinach dziennych')
    serve.set_defaults(func=cmd_serve)

    show = sub.add_parser('show', parents=[verbose], help='wypisz plan z ostatniego zapisu')
    add_common(show)
    show.add_argument('which', nargs='?', default='today', choices=['today', 'tomorrow'])
    show.set_defaults(func=cmd_show)

    simulate = sub.add_parser('simulate', parents=[verbose],
                              help='symuluj dobe ladowania')
    simulate.add_argument('-q', '--quiet', action='store_true', help='tylko podsumowanie')
    simulate.set_defaults(func=cmd_simulate)

    doctor = sub.add_parser('doctor', parents=[verbose], help='diagnostyka konfiguracji i danych')
    add_common(doctor)
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(getattr(args, 'verbose', False))

    if not getattr(args, 'command', None):
        args = parser.parse_args(['fetch', *(argv or [])])

    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        logger.info('Przerwano')
        return 130
    except Exception as error:  # noqa: BLE001 - CLI ma nie dumpowac tracebackow
        logger.error('Blad: %s', error)
        if args.verbose:
            raise
        return 1


if __name__ == '__main__':
    sys.exit(main())
