"""Entrada do serviço com proteção também durante a inicialização."""
from app.core.logging import install_safe_logging

install_safe_logging()


def main():
    import logging
    import uvicorn

    try:
        uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
    except Exception as exc:
        logging.getLogger(__name__).error(
            "Falha ao iniciar o serviço: classe=%s", type(exc).__name__,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
