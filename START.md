# Start na Windows

## 1. Nowe repozytorium

Utwórz najlepiej prywatne repozytorium, np. `webinar-production`.
Przekaż adres asystentowi do dodania plików przez GitHub albo rozpakuj pakiet
w katalogu głównym lokalnej kopii i wykonaj commit samodzielnie.
Nie kopiuj całych starych repozytoriów.

Poniższe polecenia wykonuj w PowerShell, w katalogu głównym nowego repozytorium.

## 2. Narzędzia: tylko brakujące

- [Git for Windows](https://git-scm.com/downloads/win).
- [Python 3.13](https://www.python.org/downloads/windows/) do procesu produkcyjnego.
  Wersja nauczana w kursie będzie miała osobne środowisko.
- [Node.js LTS](https://nodejs.org/en/download).

Nie instalujemy teraz Dockera, Claude Code ani SDK OpenAI. Mechanizm izolacji
zostanie dobrany i przetestowany w M1; ten start go nie implementuje.

```powershell
git --version
py -3.13 --version
node --version
npm.cmd --version
```

## 3. Codex i abonament

```powershell
npm.cmd install -g @openai/codex
codex.cmd --version
codex.cmd login
codex.cmd login status
```

Wybierz ChatGPT, nie klucz API. Jeśli masz już Codex z innego instalatora,
nie instaluj drugiej kopii: użyj istniejącego polecenia `codex`.
Nie kopiuj tokenów ani auth.json do repo/czatu. Nie włączaj automatycznych dopłat.

Podstawy: [CLI](https://developers.openai.com/codex/cli),
[logowanie](https://developers.openai.com/codex/auth),
[automatyzacja](https://developers.openai.com/codex/noninteractive).

## 4. Osobne środowisko Prefect

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\prefect.exe version
.\.venv\Scripts\python.exe scripts/check_starter.py
```

Nie trzeba aktywować venv ani zmieniać ExecutionPolicy. Prefect jest instalowany
w osobnym środowisku; stare repozytoria pozostają bez zmian.
Po udanym teście zapisz dokładne wersje (lock dla tego komputera):

```powershell
.\.venv\Scripts\python.exe -c "import pathlib,subprocess,sys; pathlib.Path('requirements.lock.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True),encoding='utf-8')"
```

## 5. Serwer: pierwsze okno PowerShell

```powershell
.\.venv\Scripts\prefect.exe server start --host 127.0.0.1
```

Panel: `http://127.0.0.1:4200`. Pozostaw okno uruchomione. Nie wystawiaj serwera
publicznie. Na początek wystarcza lokalny SQLite.

## 6. Test: drugie okno, ten sam katalog repozytorium

```powershell
$env:PREFECT_API_URL = "http://127.0.0.1:4200/api"
.\.venv\Scripts\python.exe flows/smoke.py
```

W panelu pojawi się `video-production-startup`. To test infrastruktury, nie
produkcji ani izolacji. Nie wywołuje LLM, renderowania ani ElevenLabs.

Podstawy: [instalacja Prefect](https://docs.prefect.io/v3/get-started/install),
[serwer lokalny](https://docs.prefect.io/v3/how-to-guides/self-hosted/server-cli).

## 7. Dalsza praca

Adres repozytorium i wyniki kontroli wersji/logowania wystarczą do następnego
etapu M1. Nie przekazuj poświadczeń. Nie zlecaj jeszcze produkcji całego kursu.
