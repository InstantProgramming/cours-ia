__version__ = "0.2.0"


def main() -> None:
    import os

    if os.environ.get("COURS_IA_NO_WINDOW"):
        from .server import main as serve

        serve()
    else:
        from .desktop import run

        run()
