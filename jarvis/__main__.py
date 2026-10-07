"""Start Jarvis.

    python -m jarvis              stemme + ikon i proceslinjen
    python -m jarvis --console    skriv i stedet for at tale
    python -m jarvis --test-stt   mål hvor hurtigt tale til tekst er
    python -m jarvis --test-tts   test oplæsningen
"""

import argparse

from . import app


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis", description="Lokal stemmeassistent")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--console", action="store_true", help="skriv i stedet for at tale")
    mode.add_argument("--test-stt", action="store_true", help="mål tale til tekst på denne maskine")
    mode.add_argument("--test-tts", action="store_true", help="test oplæsningen")
    args = parser.parse_args()

    if args.console:
        app.run_console()
    elif args.test_stt:
        app.run_stt_test()
    elif args.test_tts:
        app.run_tts_test()
    else:
        app.run_voice()


if __name__ == "__main__":
    main()
