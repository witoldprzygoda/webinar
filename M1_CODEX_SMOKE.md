# M1a: Prefect -> Codex, dwa nowe procesy i sesje

To test techniczny, nie produkcja ani odbior izolacji M1.
PRODUCTION_WORKFLOW.md, QUALITY_RUBRIC.md i wymagania M1 pozostaja bez zmian.

## Uruchomienie (Windows, Git Bash)

W katalogu repozytorium:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -v
export PREFECT_API_URL="http://127.0.0.1:4200/api"
./.venv/Scripts/python.exe flows/codex_smoke.py
```

Serwer Prefect musi pozostac uruchomiony. Brak nowych zaleznosci: potrzebne sa
istniejacy Prefect, Python oraz zalogowany Codex CLI. Domyslny model
`gpt-6-astra` pochodzi z potwierdzonego lokalnego testu operatora; mozna wybrac
inny dostepny model przez `--model NAZWA`.

Live smoke zuzywa limit abonamentowy: sa dwa krotkie wywolania, wykonywane
kolejno. Testy unittest nie wywoluja prawdziwego modelu ani uslug zewnetrznych.

Oczekiwany wynik:

```text
CODEX PROCESS/SESSION CHECK PASSED. ISOLATION NOT VERIFIED.
```

Flow w panelu: `video-production-codex-smoke`.
Raport: `runs/codex-smoke/<run-id>/summary.json`.
Pole `separate_sessions` ma wartosc true, natomiast `isolation_verified`
i `production_implemented` pozostaja false. To zamierzone.
Nie przesylaj auth.json, konfiguracji konta ani pelnych prywatnych logow.
Do diagnostyki wystarcza summary.json i ewentualny komunikat bledu.

## Co robi adapter

- Weryfikuje `codex login status` i wymagane opcje `exec --help` przed wywolaniem.
- Uzywa oficjalnego CLI, nie SDK ani klucza API.
- Nie przekazuje zmiennych API keys/custom endpoints i wymusza login ChatGPT
  oraz provider openai. Nie kupuje kredytow ani nie zmienia providera przy bledzie.
- Nie kopiuje ani nie otwiera auth.json; zachowuje lokalizacje istniejacego
  logowania (HOME/USERPROFILE/CODEX_HOME).
- Na Windows wywoluje npm entry point przez node zamiast shell=True i .cmd.
- Uruchamia dwa oddzielne procesy w nowych katalogach tymczasowych poza repo.
- Nie uzywa resume/fork; przekazuje jedynie syntetyczny prompt przez stdin.
- Zada read-only, ephemeral, brak wczytywania user config/AGENTS i wylaczenie
  pamieci oraz narzedzi. Raport odrzuca zarejestrowane uzycie narzedzia.
- Odbiera JSONL i `thread_id` od klienta Codex, nie od deklaracji modelu.
- Zapisuje receipt, PID, hash wejscia/wyjscia, statystyki i lokalne logi w runs/.
- Brak cache i ponowien zlecenia modelu w Prefect. Limit -> BLOCKED_LIMIT;
  timeout -> TIMEOUT_NO_RETRY. Wewnetrzne zachowanie klienta pozostaje po jego stronie.

Ustawienia CLI sa zadanym profilem testu, nie dowodem efektywnej izolacji.
`--ignore-user-config` celowo pomija osobiste ustawienia; model podajemy jawnie.
Nie stosujemy `--ignore-rules` ani `danger-full-access`.
Katalog runs/ jest juz wykluczony z Gita przez istniejacy .gitignore.

## Czego ten test NIE dowodzi

- Nie dowodzi braku dostepu do plikow innych rol ani sekretow konta OS.
- Nie weryfikuje wszystkich zrodel automatycznych instrukcji/pluginow/pamieci.
- Nie jest kalibracja sedziego: odpowiedzi to proste znaczniki polaczenia.
- Nie daje gwarancji niezaleznych bledow tego samego modelu.
- Nie odczytuje rozliczen konta i nie potwierdza wylaczenia juz zakupionych kredytow.
- Nie uruchamia lekcji, wykonywania jej przykladow, arbitra, Remotion lub ElevenLabs.

Przed M2 konieczna jest dalsza czesc M1: wymuszana granica dostepu do plikow,
negatywne testy odczytu autora przez sedziego oraz zapisu rubric i zgod,
a takze testy efektywnego zestawu instrukcji. Nie dopuszczamy produkcji
na podstawie samego PASS tego smoke testu.

## Testy wykonane podczas przygotowania

16 testow unittest PASS w kontenerze Linux; kompilacja skladni obu modulow PASS.
Test subprocess uruchamia lokalny FAKE Codex: sprawdza transport/receipts,
nie model. Sciezka Windows launcher ma test jednostkowy, nie test na Windows.
Prefect oraz rzeczywisty Codex nie byly uruchamiane w tym kontenerze.
Integracja z zalogowanym kontem i serwerem jest testem operatora opisanym wyzej.

## Dokumentacja referencyjna

Sprawdzona 2026-09-10:

- https://developers.openai.com/codex/noninteractive/
- https://developers.openai.com/codex/config-reference/
- https://developers.openai.com/codex/auth/

Odczyt statystyk tokenow nie jest sam w sobie dowodem rozliczenia przez API.
