"""
run_scheduler.py — Entrypoint standalone do scheduler Sentinel-2
Mantém o asyncio event loop vivo enquanto o APScheduler processa os jobs.
"""
import asyncio
from loguru import logger
from app.pipeline.scheduler import start_scheduler


async def main() -> None:
    start_scheduler()
    logger.info("Scheduler rodando — aguardando jobs...")
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler encerrado.")


if __name__ == "__main__":
    asyncio.run(main())
