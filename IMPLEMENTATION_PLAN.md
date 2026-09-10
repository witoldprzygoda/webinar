# Plan budowy

## M0: start

Dostarczone: procedura, rubric, instrukcje rol, rejestr zrodel, kontrola plikow
oraz test startowy Prefect. Lokalnie: instalacja, logowanie Codex, uruchomienie
serwera i flow. Odbior: video-production-startup w panelu. Bez LLM/audio.

## M1: wykonawca i izolacja kontekstu

M1a zalicza polaczenie Prefect -> Codex oraz nowe procesy/sesje bez resume/fork.

Glowna granica M1 to jawny context packet: Prefect/Python sklada dokladne wejscie
roli i przekazuje je nowemu `codex exec` przez stdin. Pierwsze role tekstowe nie
maja ogolnych narzedzi filesystem/shell. `--ignore-user-config`, `--ignore-rules`,
`--ephemeral`, wylaczone memories/skills/MCP/apps i czysty katalog ograniczaja
niejawny kontekst. `codex debug prompt-input` sluzy do testu model-visible input.
Globalny CODEX_HOME/AGENTS jest osobno wykrywany i blokuje odbior M1.

Wczesniejsza proba ACL Windows wykryla rzeczywiste problemy z dziedziczonymi
uprawnieniami i pozostaje testem diagnostycznym, ale nie jest juz architektura
handoffu rol. Jezeli pozniej damy agentowi shell/filesystem/browser/MCP, taka
powierzchnia wymaga nowego testu izolacji oraz odpowiedniego sandboxa/brokera.

Limity: BLOCKED_LIMIT, bez zakupu lub platnego fallbacku. Autor nie dostaje rubric
jako edytowalnego zasobu; sedzia nie dostaje historii autora. Hashe packetow i
artefaktow sa zapisywane.

Odbior M1c: syntetyczne markery rol nie przeciekaja do innych model-visible
promptow, brak repo/global instructions w niejawnej warstwie oraz zachowany
kontrakt swiezych sesji.

## M2: pierwszy kompletny przeplyw merytoryczny

Resolver -> source-pack -> autor -> executor przykladow -> osobni sedziowie
-> arbiter w razie potrzeby -> poprawka -> nowa ocena -> GATE A czlowieka.
Odbior: poprawny tekst, dowody, pokrycie zakresu, restart bez utraty pracy.

Pierwszy pionowy wycinek M2 bedzie mniejszy: source-pack -> author ->
judge_content, z jawnymi packetami M1 i bez audio/Remotion. Potem dolozymy
executor, judge_language, arbitra i petle rewizji.

## M3: wizualizacja bez glosu

Adaptacja potrzebnych elementow python-webinar. Dwa warianty fragmentu,
wybor, podglad z napisami, semantyczne wskazanie, niezalezna ocena i GATE B.

## M4: audio i final

Probka wymowy, zgoda na koszt, ElevenLabs, cache, kontrola nagran, mapowanie
tekstu/czasu, ponowna kompilacja, render, GATE C. Bez automatycznej publikacji.

## M5: przenosnosc i skala

Adapter Claude Code po aktualnej weryfikacji zasad, drugi kurs, limity kolejki,
magazyn artefaktow i koszt zaakceptowanej minuty. Nie budowac przed testem M2/M3.
