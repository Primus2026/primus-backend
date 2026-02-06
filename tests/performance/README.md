# Testy Wydajnościowe (Locust)

Ten katalog zawiera skrypty do testowania wydajności API backendu Primus przy użyciu [Locust](https://locust.io/).

## Wymagania Wstępne

1. Backend musi być uruchomiony (`docker compose up`).
2. Zainstalowane zależności deweloperskie w `primus-backend`:

```bash
cd primus-backend
poetry install
```

## Uruchamianie Testów

Aby uruchomić pełny zestaw testów w trybie headless i wygenerować statystyki w konsoli:

```bash
cd primus-backend
poetry run locust -f scripts/locustfile.py --headless -u 10 -r 2 --run-time 5m --host https://localhost
```

### Parametry:
- `-f scripts/locustfile.py`: Ścieżka do pliku ze scenariuszami.
- `--headless`: Uruchomienie bez interfejsu webowego.
- `-u 10`: Liczba symulowanych użytkowników (10).
- `-r 2`: Tempo przyrostu użytkowników (2 na sekundę).
- `--run-time 5m`: Czas trwania testu (5 minut).
- `--host https://localhost`: Adres API.

## Scenariusze Testowe

Skrypt realizuje następujące zadania symulujące realne obciążenie systemu:

- **Import CSV**: Mierzy narzut masowego tworzenia produktów poprzez `/api/v1/product_definitions/import_csv`.
- **Wyszukiwanie Stanów**: Mierzy opóźnienie odczytu przy wyszukiwaniu konkretnych produktów przez `/api/v1/stock/`.
- **Generowanie Raportu Audytu**: Mierzy ciężką operację obliczeniową/IO (generowanie PDF) przez `/api/v1/reports/generate/audit`.
- **Alokacja Towaru**: Testuje złożony algorytm znajdowania najlepszego miejsca na regale (sprawdzanie temperatur, wymiarów) używając `/api/v1/stock/inbound/`.
- **Wydawanie Towaru (Outbound)**: Mierzy wydajność logiki FIFO przy wydawaniu towaru używając `/api/v1/stock/outbound/initiate/{barcode}`.
- **Rozpoznawanie AI**: Mierzy narzut kolejkowania zadań rozpoznawania obrazu przez `/api/v1/ai/recognize`.
- **Komendy Głosowe**: Mierzy opóźnienie przetwarzania intencji przez LLM używając `/api/v1/voice-command/`.

> **Uwaga**: Plik `locustfile.py` jest skonfigurowany tak, aby wyłączyć weryfikację SSL (`verify=False`), co pozwala na testowanie na lokalnych certyfikatach self-signed.
