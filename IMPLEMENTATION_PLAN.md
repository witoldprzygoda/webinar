# Plan budowy

## M0: start

Dostarczone: procedura, rubric, instrukcje ról, rejestr źródeł, kontrola plików
oraz test startowy Prefect. Lokalnie: instalacja, logowanie Codex, uruchomienie
serwera i flow. Odbiór: video-production-startup w panelu. Bez LLM/audio.

## M1: wykonawca i izolacja

Adapter Runner: role + immutable input packet + output contract -> artifact + receipt.
Pierwszy backend: codex exec. Nowy proces/sesja, brak resume i podagentów autora.
Testujemy faktyczne logowanie abonamentowe; brak zmiennej OPENAI_API_KEY nie
wyklucza zapisanego klucza/custom providera/dodatkowych kredytów.
Limity: BLOCKED_LIMIT, bez zakupu lub płatnego fallbacku.

Wymagane testy: brak odczytu danych autora przez sędziego, brak zapisu autora
do rubric i zgód, brak dziedziczenia pamięci/instrukcji, poprawny dostęp do
dozwolonych dowodów i zapis hashy. Sam rozdział PID/katalogów nie zalicza izolacji.

## M2: pierwszy kompletny przepływ merytoryczny

Resolver -> source-pack -> autor -> executor przykładów -> osobni sędziowie
-> arbiter w razie potrzeby -> poprawka -> nowa ocena -> GATE A człowieka.
Odbiór: poprawny tekst, dowody, pokrycie zakresu, restart bez utraty pracy.

## M3: wizualizacja bez głosu

Adaptacja potrzebnych elementów python-webinar. Dwa warianty fragmentu,
wybór, podgląd z napisami, semantyczne wskazanie, niezależna ocena i GATE B.

## M4: audio i final

Próbka wymowy, zgoda na koszt, ElevenLabs, cache, kontrola nagrań, mapowanie
tekstu/czasu, ponowna kompilacja, render, GATE C. Bez automatycznej publikacji.

## M5: przenośność i skala

Adapter Claude Code po aktualnej weryfikacji zasad, drugi kurs, limity kolejki,
magazyn artefaktów i koszt zaakceptowanej minuty. Nie budować przed testem M2/M3.
