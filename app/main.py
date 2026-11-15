from __future__ import annotations

import argparse
import logging
import time

from app.config import settings
from app.database.schema import initialize_database
from app.services.free_games_service import run_epic_crawler
from app.services.steam_deals_service import run_steam_crawler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawler de jogos grátis da Epic e promoções da Steam")
    parser.add_argument("--crawler", choices=("epic", "steam", "all"), default="all")
    parser.add_argument("--once", action="store_true", help="Executa uma vez (padrão)")
    parser.add_argument("--watch", action="store_true", help="Repete a coleta no intervalo configurado")
    parser.add_argument("--interval", type=int, default=settings.crawler_interval,
                        help="Intervalo em segundos para --watch")
    parser.add_argument("--max-items", type=int, default=None,
                        help="Limita itens para testes; não desativa promoções ausentes")
    parser.add_argument("--log-level", default=settings.log_level,
                        choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def run_selected(crawler: str, max_items: int | None) -> None:
    if crawler in ("epic", "all") and settings.epic_enabled:
        logging.info("Iniciando crawler Epic Games")
        logging.info("Epic Games: %s", run_epic_crawler(max_items=max_items))
    if crawler in ("steam", "all") and settings.steam_enabled:
        logging.info("Iniciando crawler Steam")
        logging.info("Steam: %s", run_steam_crawler(max_items=max_items))


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    initialize_database()
    if args.watch:
        if args.interval < 60:
            raise SystemExit("O intervalo mínimo de --watch é 60 segundos.")
        while True:
            try:
                run_selected(args.crawler, args.max_items)
            except Exception:
                logging.exception("Falha durante a execução do crawler")
            logging.info("Próxima execução em %s segundos", args.interval)
            time.sleep(args.interval)
    else:
        run_selected(args.crawler, args.max_items)


if __name__ == "__main__":
    main()
