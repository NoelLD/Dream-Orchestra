import os
import sys

import dream
from dream.models import list_models


def main() -> int:
    api_key = os.environ.get("DREAM_API_KEY", "").strip()
    if not api_key:
        print("Bitte DREAM_API_KEY in .env neben compose.yaml eintragen.", file=sys.stderr)
        return 2

    try:
        models = list_models(api_key=api_key)
    except dream.DreamAuthError:
        print("Dream Labs hat den API-Key abgelehnt.", file=sys.stderr)
        return 1
    except dream.DreamConfigError:
        print("Ungültige Dream-Konfiguration. Prüft die Werte in .env.", file=sys.stderr)
        return 1
    except dream.DreamProtocolError:
        print(
            "Keine gültige Antwort von Dream Labs. Prüft HTTPS-Zugang, DREAM_API_URL und SDK-Version.",
            file=sys.stderr,
        )
        return 1
    except dream.DreamError as error:
        print(f"Dream-Labs-Anfrage fehlgeschlagen ({type(error).__name__}).", file=sys.stderr)
        return 1

    print(f"Dream-Labs-API erreichbar. SDK {dream.__version__}. Verfügbare Checkpoints: {len(models)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
