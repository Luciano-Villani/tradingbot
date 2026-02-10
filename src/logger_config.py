import sys
from pathlib import Path
from loguru import logger
from datetime import datetime
import json

def setup_logger(config_path=None):
    """Configura logging estructurado para Windows"""
    
    settings = {}
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            settings = json.load(f).get('logging', {})
    
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger.remove()
    
    if settings.get('console_output', True):
        logger.add(
            sys.stdout,
            level=settings.get('level', 'INFO'),
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            colorize=True
        )
    
    logger.add(
        log_dir / f"debug_{datetime.now().strftime('%Y%m%d')}.log",
        rotation=f"{settings.get('file_rotation_mb', 10)} MB",
        retention=f"{settings.get('retention_days', 7)} days",
        level="DEBUG",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"
    )
    
    logger.add(
        log_dir / "trades.csv",
        rotation="1 MB",
        retention="30 days",
        level="INFO",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss},{message}",
        filter=lambda record: record["message"].startswith("TRADE,")
    )
    
    logger.add(
        log_dir / "errors.log",
        rotation="5 MB",
        retention="30 days",
        level="ERROR",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}\n{exception}"
    )
    
    return logger

