import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(filename)s:%(lineno)d | "
    "%(message)s"
)




def get_logger(
    name: str,
    log_level=logging.INFO,
    log_file="logs/app.log",
):
    """
    Retourne un logger configuré.

    Parameters
    ----------
    name : str
        Nom du logger (généralement __name__)
    log_level : int
        logging.INFO, DEBUG...
    log_file : str
        Fichier de log

    Returns
    -------
    logging.Logger
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(log_level)

    # Création du dossier logs
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)

    # Console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Fichier
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
        
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.propagate = False

    return logger






def reset_logger(log_file="logs/app.log"):
    """
    Vide le fichier de log principal et ferme proprement les handlers
    de tous les loggers associés à ce fichier.
    """
    log_path = Path(log_file)
    if not log_path.exists():
        return

    # Fermer temporairement le fichier sur tous les FileHandlers actifs
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            for handler in logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    if Path(handler.baseFilename).resolve() == log_path.resolve():
                        handler.close()

    # Vider le contenu du fichier
    with open(log_path, "w", encoding="utf-8") as f:
        f.truncate(0)