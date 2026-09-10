# M1c: izolacja kontekstu rol

To jest nowy glowny kierunek M1. Wczesniejszy eksperyment z ACL Windows pozostaje
diagnostyka historyczna i nie jest warunkiem przejscia do M2.

## Granica

Prefect/Python sklada jawny packet roli i przekazuje go nowemu `codex exec` przez
stdin. Model nie dostaje ogolnego interfejsu do lokalnego systemu plikow. Kazda
rola ma nowy proces i nowa sesje; nie uzywamy resume/fork ani podagenta autora.

Autor, sedzia i arbiter moga poznac tylko material, ktory orkiestrator jawnie
umiescil w ich packet. Raporty i artefakty przechodza przez kontrolowany handoff,
a nie przez wspolny katalog przegladany przez model.

Dla pierwszych przeplywow tekstowych wylaczamy shell/unified exec, multi-agent,
web search, MCP, skills, memories, apps/collaboration instructions i automatyczny
project context. Produkcyjny `codex exec` uzywa `--ignore-user-config`,
`--ignore-rules`, `--ephemeral`, read-only i stdin.

Wersja Codex 0.153.4 laduje globalne `$CODEX_HOME/AGENTS.override.md` lub
`$CODEX_HOME/AGENTS.md` przez osobny provider instrukcji. Dlatego preflight jawnie
blokuje odbior M1, jesli taki plik istnieje. Nie czytamy ani nie kopiujemy auth.json.

## Co sprawdza audit

`codex debug prompt-input` buduje lokalnie model-visible input. Audit tworzy pusty
tymczasowy CODEX_HOME oraz trzy osobne katalogi i packety z losowymi markerami:
author, judge_content, arbiter. Dla kazdej roli wymaga:

- widocznosci wlasnego markera;
- braku markerow pozostalych rol;
- braku charakterystycznych instrukcji z repozytorium webinar;
- zgodnosci statycznego kontraktu przyszlego `codex exec`.

Audit nie wywoluje modelu i nie zuzywa ElevenLabs. Surowe wyniki zawieraja tylko
syntetyczne dane i trafiaja do ignorowanego `runs/context-isolation/`.

PASS tego auditu oznacza, ze testowany mechanizm model-visible context nie miesza
packetow rol i ze kontrakt uruchomienia nie uzywa historii sesji. Nie dowodzi to
jeszcze jakosci sedziego ani izolacji przyszlych narzedzi sieciowych. Jezeli
pozniej damy roli shell, filesystem, browser lub MCP, ta nowa powierzchnia wymaga
osobnego testu granic (najpewniej kontener/VM albo bardzo waski broker narzedzi).

## Uruchomienie - Windows / Git Bash

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_context_isolation.py' -v
export PREFECT_API_URL="http://127.0.0.1:4200/api"
./.venv/Scripts/python.exe flows/context_isolation.py
```

Oczekiwany wynik koncowy:

```json
{
  "context_isolation_audit": "PASS",
  "model_request_sent": false,
  "llm_called": false
}
```

Flow w Prefect: `video-production-context-isolation`.

## Podstawa sprawdzona dla codex-cli 0.153.4

- `codex exec --ignore-user-config`: config.toml jest pomijany, auth nadal uzywa
  CODEX_HOME (`codex-rs/exec/src/cli.rs`).
- `debug prompt-input`: wypisuje model-visible prompt input
  (`codex-rs/cli/src/main.rs`).
- globalny AGENTS w CODEX_HOME jest ladowany niezaleznie przez
  `CodexHomeUserInstructionsProvider` (`codex-rs/codex-home/src/instructions/mod.rs`).

Po PASS nastepny etap to pierwszy minimalny przeplyw M2:
`source-pack -> author -> judge_content`, nadal bez audio i Remotion.
