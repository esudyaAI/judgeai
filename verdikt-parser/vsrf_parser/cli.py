"""CLI-интерфейс парсера судебных актов ВС РФ."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .browser import BrowserTransport
from .client import VSRFClient
from .crawler import Crawler
from .dataset import build_dataset, parse_article_filter, save_dataset
from .http_client import HttpClient
from .sudact import SudActClient

log = logging.getLogger("vsrf_parser.cli")


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--delay", type=float, default=0.8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--browser", action="store_true",
                        help="использовать nodriver (Chrome) вместо прямого HTTP")
    parser.add_argument("--sqlite", action="store_true",
                        help="дополнительно писать метаданные в acts.db")
    parser.add_argument("--insecure", action="store_true",
                        help="отключить проверку TLS-сертификата (по умолчанию включена)")


def _make_transport(args: argparse.Namespace):
    if args.browser:
        print("[*] Транспорт: nodriver (Chrome browser-fallback)")
        return BrowserTransport(delay=max(args.delay, 1.5))
    workers = getattr(args, "workers", 1) or 1
    return HttpClient(
        delay=args.delay,
        timeout=args.timeout,
        pool_size=max(8, workers * 2),
        verify=not getattr(args, "insecure", False),
    )


def cmd_buildid(args: argparse.Namespace) -> int:
    transport = _make_transport(args)
    client = VSRFClient(transport)
    build_id = client.resolve_build_id()
    print(f"buildId: {build_id}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    transport = _make_transport(args)
    client = VSRFClient(transport)
    client.resolve_build_id()
    for case_type in VSRFClient.CASE_TYPES:
        try:
            page = client.fetch_acts_page(page=1, case_type=case_type)
        except Exception as exc:
            print(f"{case_type}: ошибка — {exc}")
            continue
        print(f"{case_type}: {page.total} производств")
    return 0


def cmd_crawl(args: argparse.Namespace) -> int:
    transport = _make_transport(args)
    client = VSRFClient(transport)
    if not args.browser:
        client.resolve_build_id()
    crawler = Crawler(
        client,
        out_dir=args.out,
        case_type=args.case_type,
        instance=args.instance,
        workers=args.workers,
    )
    crawler.open_stores(sqlite=args.sqlite)
    try:
        total_new = 0
        for page in crawler.iter_act_pages(
            start_page=args.start_page, max_pages=args.limit_pages
        ):
            if not page.items:
                log.info("Страница %d пуста — конец выборки", page.page)
                break
            new = crawler.collect_claims(
                page.items,
                max_claims=args.max_claims - total_new if args.max_claims else None,
            )
            total_new += new
            print(
                f"[+] Страница {page.page}: {len(page.items)} дел, "
                f"новых карточек: {new} (всего новых: {total_new})",
                flush=True,
            )
            if args.max_claims and total_new >= args.max_claims:
                break
        print(f"[=] Метаданные: +{total_new} записей в {args.out / 'metadata.jsonl'}")

        if not args.no_pdf:
            pdf_ids = crawler.collect_pdf_ids()
            limit = args.pdf_limit if args.pdf_limit else None
            downloaded = crawler.download_pdfs(
                pdf_ids, limit=limit, pdf_delay=args.pdf_delay
            )
            print(f"[=] PDF: скачано {downloaded} (доступно по метаданным: {len(pdf_ids)})")

        if not args.no_text:
            extracted = crawler.extract_texts(ocr=not args.no_ocr)
            print(f"[=] Тексты: извлечено {extracted} файлов в {args.out / 'texts'}")

        if not args.no_parse:
            parsed = crawler.parse_texts()
            print(f"[=] Разбор: +{parsed} записей в {args.out / 'parsed.jsonl'}")
    finally:
        crawler.close()
    return 0


def cmd_pdf(args: argparse.Namespace) -> int:
    transport = _make_transport(args)
    client = VSRFClient(transport)
    crawler = Crawler(client, out_dir=args.out, workers=args.workers)
    pdf_ids = (
        [args.pdf_id] if args.pdf_id else crawler.collect_pdf_ids()
    )
    downloaded = crawler.download_pdfs(
        pdf_ids, limit=args.limit, pdf_delay=args.pdf_delay
    )
    print(f"Скачано PDF: {downloaded} из {len(pdf_ids)} доступных")
    return 0


def cmd_text(args: argparse.Namespace) -> int:
    from .pdf import extract_text, save_text

    crawler = _make_crawler_for_local(args)
    if args.pdf_path:
        result = extract_text(Path(args.pdf_path), ocr=not args.no_ocr)
        out = Path(args.pdf_path).with_suffix(".txt")
        save_text(out, result.text)
        print(
            f"Текст: {out} ({result.pages} стр., text_layer={result.has_text_layer}, "
            f"ocr={result.ocr_used})"
        )
        return 0
    extracted = crawler.extract_texts(ocr=not args.no_ocr, limit=args.limit)
    print(f"Извлечено текстов: {extracted}")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    from .text_parser import parse_act_file

    if args.text_file:
        parsed = parse_act_file(Path(args.text_file))
        print(_format_parsed(parsed))
        return 0
    crawler = _make_crawler_for_local(args)
    count = crawler.parse_texts(limit=args.limit)
    print(f"Разобрано текстов: {count} -> {args.out / 'parsed.jsonl'}")
    return 0


def _make_crawler_for_local(args: argparse.Namespace) -> Crawler:
    workers = getattr(args, "workers", 1) or 1
    client = VSRFClient(HttpClient(delay=args.delay, pool_size=max(8, workers * 2)))
    return Crawler(client, out_dir=args.out, workers=workers)


def cmd_show(args: argparse.Namespace) -> int:
    transport = _make_transport(args)
    client = VSRFClient(transport)
    client.resolve_build_id()
    details = client.fetch_claim(args.claim_id)
    print(_format_details(details))
    return 0


def _format_details(details) -> str:
    lines = [
        f"ID производства:  {details.claim_id}",
        f"Номер дела:       {details.sdd_id}",
        f"Тип:              {details.claim_type}",
        f"Вид:              {details.case_type}",
        f"Инстанция:        {details.instance_label}",
        f"Коллегия:         {details.department}",
        f"Регистрация:      {details.register_date}",
        f"Поступило:        {details.incoming_method}",
        "--- Первая инстанция (firstAct) ---",
        f"  Тип акта:       {details.first_act.act_type_name}",
        f"  Суд:            {details.first_act.court_name}",
        f"  Номер дела:     {details.first_act.full_case_number}",
        f"  Судья:          {details.first_act.judge_name}",
        f"  Дата:           {details.first_act.create_date}",
        "--- Итоговый акт ВС РФ (finalAct) ---",
        f"  Тип акта:       {details.final_act.act_type_name}",
        f"  Дата:           {details.final_act.create_date}",
        f"  Результат:      {details.final_act.judgement_type_name}",
        f"  Докладчик:      {details.final_act.reporter_name}",
        f"  PDF:            {details.final_act.download_link}",
        "--- Лица ---",
    ]
    for group in details.personalities:
        for person in group.persons:
            lines.append(f"  [{group.status_label}] {person.short_name} — {person.article}")
    lines.append("--- События ---")
    for event in details.events:
        lines.append(f"  {event.event_datetime}: {event.type_name}")
    return "\n".join(lines)


def _format_parsed(parsed) -> str:
    lines = [
        f"Вид акта:         {parsed.act_kind}",
        f"Номер дела:       {parsed.case_number}",
        f"Дата:             {parsed.act_date}",
        f"Город:            {parsed.city}",
        f"Коллегия:         {parsed.collegium}",
        f"Председательств.: {parsed.presiding_judge}",
        f"Судьи:            {', '.join(parsed.judges) or '—'}",
        f"Секретарь:        {parsed.secretary}",
        f"Прокурор:         {parsed.prosecutor}",
        f"Осуждённые:       {', '.join(parsed.convicted) or '—'}",
        f"Суд 1-й инст.:    {parsed.lower_court}",
        f"Дата приговора:   {parsed.lower_court_date}",
        f"Статьи УК:        {'; '.join(parsed.articles) or '—'}",
        f"Итог:             {parsed.outcome}",
        f"Глаголы итога:    {', '.join(parsed.outcome_verbs) or '—'}",
        f"Наказание:        {parsed.sentence or '—'}",
        f"Оперативная часть: {(parsed.operative_part or '—')[:300]}",
    ]
    return "\n".join(lines)


def cmd_sudact(args: argparse.Namespace) -> int:
    sud = SudActClient(delay=args.delay)
    try:
        payload = sud.search(args.query)
        results = sud.parse_search_results(payload)
        print(f"Найдено: {payload.get('total_found', '')}".strip())
        for item in results[: args.top]:
            print(f"  - {item['title']}  [{item['url']}]")
        if args.fetch:
            docs = sud.search_and_fetch(args.query, fetch_docs=args.fetch)
            out_dir = args.out / "sudact"
            out_dir.mkdir(parents=True, exist_ok=True)

            path = out_dir / "sudact_results.json"
            path.write_text(
                json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Документы ({len(docs['documents'])}) сохранены: {path}")
    finally:
        sud.close()
    return 0


def cmd_dataset(args: argparse.Namespace) -> int:
    from .dataset import load_jsonl, record_matches

    out_dir: Path = args.out
    filters = parse_article_filter(args.article) if args.article else []
    if args.article:
        print(f"[*] Фильтр по статьям: {args.article}")

    metadata = load_jsonl(out_dir / "metadata.jsonl")
    if not metadata:
        print(f"[!] Нет метаданных: {out_dir / 'metadata.jsonl'} — сначала запустите crawl")
        return 1

    matched = [
        rec for rec in metadata if not filters or record_matches(rec, filters)
    ]
    pdf_ids = [rec["pdf_id"] for rec in matched if rec.get("pdf_id")]
    print(
        f"[=] Метаданных: {len(metadata)}, по фильтру: {len(matched)}, "
        f"с PDF-ссылками: {len(pdf_ids)}"
    )

    if args.download:
        transport = _make_transport(args)
        client = VSRFClient(transport)
        crawler = Crawler(client, out_dir=out_dir, workers=args.workers)
        downloaded = crawler.download_pdfs(
            pdf_ids, limit=args.download, pdf_delay=args.pdf_delay
        )
        extracted = crawler.extract_texts(ocr=not args.no_ocr)
        parsed = crawler.parse_texts()
        print(f"[=] Докачано PDF: {downloaded}, текстов: {extracted}, разобрано: {parsed}")

    result = build_dataset(
        out_dir,
        article_spec=args.article,
        text_field=args.text_field,
        include_full_text=not args.no_full_text,
    )
    out_path = out_dir / "dataset.jsonl"
    save_dataset(result["items"], out_path)
    print(f"[=] ML-датасет: {result['in_dataset']} примеров -> {out_path}")
    print("[=] Распределение меток (label = что вынес ВС РФ):")
    for label, count in sorted(
        result["labels"].items(), key=lambda kv: -kv[1]
    ):
        print(f"    {label}: {count}")
    if result["in_dataset"] < len(matched):
        pending = len(matched) - result["in_dataset"]
        print(
            f"[*] Ещё {pending} отфильтрованных дел без текста — "
            f"докачайте: dataset --article ... --download N (или больше N)"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vsrf_parser",
        description="Парсер приговоров и судебных актов Верховного Суда РФ",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_buildid = sub.add_parser("buildid", help="показать актуальный Next.js buildId")
    _add_common(p_buildid)
    p_buildid.set_defaults(func=cmd_buildid)

    p_stats = sub.add_parser("stats", help="число производств по типам дел")
    _add_common(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    p_crawl = sub.add_parser("crawl", help="полный пайплайн сбора и разбора")
    _add_common(p_crawl)
    p_crawl.add_argument("--case-type", default="CRIMINAL",
                         choices=VSRFClient.CASE_TYPES)
    p_crawl.add_argument("--instance", choices=VSRFClient.INSTANCES)
    p_crawl.add_argument("--workers", type=int, default=1,
                         help="параллельных потоков для карточек/PDF/текстов")
    p_crawl.add_argument("--start-page", type=int, default=1)
    p_crawl.add_argument("--limit-pages", type=int)
    p_crawl.add_argument("--max-claims", type=int)
    p_crawl.add_argument("--no-pdf", action="store_true")
    p_crawl.add_argument("--pdf-limit", type=int)
    p_crawl.add_argument("--pdf-delay", type=float, default=1.0,
                         help="мин. интервал между запросами PDF, сек "
                              "(хранилище троттлится: 429 + ~1 Мбит/с на IP)")
    p_crawl.add_argument("--no-text", action="store_true")
    p_crawl.add_argument("--no-ocr", action="store_true")
    p_crawl.add_argument("--no-parse", action="store_true")
    p_crawl.set_defaults(func=cmd_crawl)

    p_pdf = sub.add_parser("pdf", help="докачать PDF по метаданным")
    _add_common(p_pdf)
    p_pdf.add_argument("--pdf-id", help="скачать конкретный stor_pdf/{id}")
    p_pdf.add_argument("--workers", type=int, default=1)
    p_pdf.add_argument("--pdf-delay", type=float, default=1.0)
    p_pdf.add_argument("--limit", type=int)
    p_pdf.set_defaults(func=cmd_pdf)

    p_text = sub.add_parser("text", help="извлечь текст из PDF")
    _add_common(p_text)
    p_text.add_argument("--pdf-path", help="конкретный PDF-файл")
    p_text.add_argument("--workers", type=int, default=1)
    p_text.add_argument("--limit", type=int)
    p_text.add_argument("--no-ocr", action="store_true")
    p_text.set_defaults(func=cmd_text)

    p_parse = sub.add_parser("parse", help="разобрать тексты актов")
    _add_common(p_parse)
    p_parse.add_argument("--text-file", help="разобрать конкретный текстовый файл")
    p_parse.add_argument("--limit", type=int)
    p_parse.set_defaults(func=cmd_parse)

    p_show = sub.add_parser("show", help="карточка производства по claim_id")
    _add_common(p_show)
    p_show.add_argument("claim_id")
    p_show.set_defaults(func=cmd_show)

    p_dataset = sub.add_parser(
        "dataset",
        help="ML-датасет: фильтр по статьям УК + метка исхода",
    )
    _add_common(p_dataset)
    p_dataset.add_argument("--article", default=None,
                           help='фильтр: "105", "105.2", "105 ч.2,111"')
    p_dataset.add_argument("--download", type=int, default=0,
                           help="докачать N PDF по фильтру перед сборкой датасета")
    p_dataset.add_argument("--workers", type=int, default=4)
    p_dataset.add_argument("--pdf-delay", type=float, default=1.0)
    p_dataset.add_argument("--no-ocr", action="store_true")
    p_dataset.add_argument("--text-field", choices=["full", "operative"],
                           default="full",
                           help="что положить в поле text: весь акт или резолютивную часть")
    p_dataset.add_argument("--no-full-text", action="store_true",
                           help="не включать поле text (только метаданные + метка)")
    p_dataset.set_defaults(func=cmd_dataset)

    p_sudact = sub.add_parser("sudact", help="поиск в СудАкт (резервный источник)")
    p_sudact.add_argument("query")
    p_sudact.add_argument("--top", type=int, default=10)
    p_sudact.add_argument("--fetch", type=int, default=0,
                          help="число документов для выгрузки текста")
    p_sudact.add_argument("--out", type=Path, default=Path("data"))
    p_sudact.add_argument("--delay", type=float, default=1.5)
    p_sudact.set_defaults(func=cmd_sudact)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n[!] Прервано пользователем; прогресс сохранён", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
