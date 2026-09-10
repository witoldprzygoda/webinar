# M2a: pierwszy rzeczywisty pion treści

M2a uruchamia rzeczywisty, ale celowo mały przepływ:

`pinned source-pack -> fresh author Codex -> artifact -> fresh judge_content Codex`

Bez executora kodu, arbitra, pętli rewizji, audio i Remotion.

## Zakres pierwszej próby

Temat: interaktywna konsola Pythona jako kalkulator.

Materiał dydaktyczny jest przypięty do:

- `witoldprzygoda/python-notatki`
- commit `0bccb67f308b82b9e14833b3baffa56bcad16222`
- `docs/02-konsola/konsola-w-praktyce.md`
- sekcja od `## Konsola jako kalkulator` do następnego podrozdziału.

Dowód pierwotny dla Python 3.14 jest przypięty do aktualnego w dniu 2026-09-10
commitu gałęzi CPython 3.14:

- `python/cpython`
- commit `da5ed621a1c0ea495094aa727bbb0b90fb568c7e`
- `Doc/tutorial/introduction.rst`
- sekcja `Using Python as a Calculator`.

Resolver pobiera wyłącznie tekst z `raw.githubusercontent.com`, wymaga pełnego
40-znakowego SHA, zachowuje URL oraz SHA-256 pełnego pliku i wybranej sekcji.
Zewnętrzna treść jest przekazywana modelowi jako dane, nie instrukcja.

## Izolacja ról

M2a korzysta z mechanizmu zaliczonego w M1c. Autor i sędzia są osobnymi
`codex exec`, bez resume/fork. Sędzia dostaje artefakt autora i jawny source-pack,
ale nie dostaje prompt history, logów, reasoning ani samooceny autora. Każda rola
ma tool-free context packet; brak shell/filesystem/web/MCP/skills/memories.

Uruchamiaj z osobnym `CODEX_HOME` używanym dla webinaru, np. `.codex-webinar`,
który przeszedł M1c i nie zawiera globalnego AGENTS.md.

## Artefakt autora

Autor zwraca ustrukturyzowany JSON:

- `title`;
- `narration[]` z trwałymi `fragment_id`;
- `claims[]` z `claim_id`, tekstem i identyfikatorami źródeł;
- `coverage[]`;
- `open_questions[]`.

To nadal tekst semantyczny, bez planowania scen i bez zapisu wymowy TTS.

## Sędzia

Sędzia ocenia F1, F2, E1, E2, L1, L2, L3, D1 i P1. JSON Schema wiąże raport z
konkretnym `artifact_sha256` i rubric 0.1. Każde kryterium musi wystąpić dokładnie
raz. Brak wykonania kodu jest jawny; sędzia nie może uznać E1/E2 za PASS tylko
na podstawie wiarygodnie wyglądającego outputu.

Werdykt PASS/REVISE/BLOCKED nie jest automatycznym Gate A. M2a kończy się przed
bramką człowieka i przed automatyczną rewizją.

## Uruchomienie

Windows / Git Bash, po ustawieniu osobnego CODEX_HOME i przy działającym Prefect:

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_m2a_content.py' -v
export PREFECT_API_URL="http://127.0.0.1:4200/api"
./.venv/Scripts/python.exe flows/m2a_content.py
```

To uruchomienie wykonuje dwa rzeczywiste wywołania modelu w abonamencie ChatGPT:
najpierw autora, potem niezależnego sędziego. Brak automatycznych retry i brak
API fallbacku. Limit ma zatrzymać przebieg jako BLOCKED_LIMIT.

Wyniki znajdują się w `runs/m2a-content/<run-id>/`:

- `source-pack.json`
- `artifact.json`
- `author/receipt.json`
- `judge-report.json`
- `judge_content/receipt.json`
- `summary.json`

Do pierwszej analizy wystarczy wkleić `summary.json` i `judge-report.json`.
