# Produkcja webinarów

Warsztat: Python + Prefect, abonamentowy Codex jako wykonawca,
opcjonalnie Claude Code, Remotion i ElevenLabs.

**Stan 0.1: dokumentacja i test startowy.** Adapter LLM, izolacja agentów,
resolver materiałów i produkcja filmów nie są jeszcze zaimplementowane.

1. Instalacja: [START.md](START.md).
2. Nadrzędna procedura: [PRODUCTION_WORKFLOW.md](PRODUCTION_WORKFLOW.md).
3. Kryteria niezależnej oceny: [QUALITY_RUBRIC.md](QUALITY_RUBRIC.md).
4. Etapy implementacji: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
5. Rozszerzalny rejestr materiałów: [config/sources.json](config/sources.json).

`AGENTS.md` określa pracę programisty nad repozytorium.
Instrukcje oddzielnych ról produkcyjnych znajdują się w `prompts/`.

Pierwszy docelowy rezultat: zweryfikowany scenariusz merytoryczny jednego
podrozdziału, z niezależnymi recenzjami i akceptacją człowieka. Bez audio.

## Testy pakietu

`python scripts/check_starter.py` sprawdza pliki, JSON, polityki i składnię Pythona.
`python flows/smoke.py` sprawdza uruchomienie flow na lokalnym Prefect.
Źaden z tych testów nie wywołuje LLM ani ElevenLabs i nie dowodzi izolacji agentów.

Przy przygotowaniu sprawdzono pliki i składnię. Nie wykonano testu z serwerem
Prefect ani kontem Codex: środowisko przygotowania nie miało dostępu sieciowego
potrzebnego do instalacji Prefect. Weryfikacja integracji pozostaje zadaniem lokalnym.
