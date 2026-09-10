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

Stan: pierwszy pionowy wycinek zakonczony Gate A dla lekcji
`python-console-calculator`.

Zaimplementowano:

- jawny profil odbiorcy `technical_competent` i kryterium L4;
- przypiete materialy/evidence oraz source-pack z hashem;
- autora z artifact-bound `execution_plan`;
- rzeczywiste wykonanie przykladow w CPython 3.14.7;
- niezaleznych judge-content i judge-language;
- normalny stan biznesowy `REVISION_REQUIRED` bez tracebacka;
- fakultatywny enrichment scout, niezalezna ocene kandydatow i arbitraz MAYBE;
- portfolio enrichmentu z osobna rubric 0.2, soft/hard budget i ocena wartosci
  marginalnej calego zestawu;
- integrator zachowujacy zaakceptowany rdzen oraz ponowne wykonanie i pelna
  rewalidacje wzbogaconego artefaktu;
- osobne evidence dla REPL i rzeczywistego `python -c`;
- human-readable Gate A review.

Artefakt `65202b7e279ddb983eb0ee7488919ec3f095ed2c5a4ba2891c6e702bb094a18c`
zostal jawnie zaakceptowany przez czlowieka w rozmowie 11.09.2026. Lokalny,
audytowalny receipt zapisuje `scripts/record_gate_a_approval.py`; kolejne etapy
nie moga ruszyc bez receipt dla dokladnie tego hasha.

Petla automatycznych rewizji do trzech cykli pozostaje elementem do dalszego
uogolnienia. Pierwszy wycinek wykazal poprawne stany PASS/REVISE i zaleznosci
hash/evidence bez audio i renderowania.

## M3: wizualizacja bez glosu

M3a zakonczone jako test projektowania scen po Gate A. Dla `frag-07` powstaly
trzy rozne mechaniki wizualne. Czlowiek wybral `v2`, czyli `state_model`: stala
nazwa `_` i jawnie zmieniana wartosc stanu, z rozdzieleniem odczytu od
aktualizacji. Wybor zapisuje append-only `scripts/record_m3a_selection.py`,
zwiazany z hashem calego zestawu wariantow i hashem wybranego wariantu.

Projektant dostaje tylko zaakceptowana narracje, powiazane rzeczywiste wyniki
wykonania i jawny, przypiety know-how pack. Pierwszy know-how snapshot uzywa
`python-webinar` commit `f9447818061a10b035ee8ad5cb84ef22a9c9deeb`,
`wideo/RECEPTURA.md`. Warianty i plan uzywaja semantycznych identyfikatorow, bez
pikseli, bez bezwzglednych sekund, bez audio i bez zmiany Gate A.

M3b jest zaimplementowane jako `flows/m3b_scene_plan.py`. Wymaga poprawnego
receipt wyboru M3a i tworzy `scene-plan.json` calej lekcji. Plan:

- zachowuje wszystkie fragmenty Gate A dokladnie raz i w tej samej kolejnosci;
- wiaze kazdy beat z `fragment_id` oraz dokladnym `anchor_text` z narracji;
- wiaze kod/output/state z konkretnym `example_id` albo `check_id`;
- nie dopuszcza wymyslonych wynikow wykonania;
- traktuje `v2` jako wiazaca mechanike dla `frag-07`, ale nie kopiuje jej
  automatycznie do pozostalych scen;
- jawnie zglasza nowe komponenty potrzebne przed preview.

`scripts/m3b_review.py` daje tekstowy przeglad calego planu przed implementacja
Remotion. M3b nadal nie renderuje i nie uruchamia audio.

Nastepne kroki M3:

1. implementacja/adaptacja potrzebnych komponentow Remotion z `scene-plan.json`;
2. roboczy timing i podglad bez glosu;
3. automatyczna kontrola techniczna oraz niezalezny judge-visual na rzeczywistym
   podgladzie;
4. GATE B czlowieka.

Zmiana tresci wymuszona wizualizacja zawsze wraca do Gate A zamiast byc
przemycona przez projektanta scen.

## M4: audio i final

Probka wymowy, zgoda na koszt, ElevenLabs, cache, kontrola nagran, mapowanie
tekstu/czasu, ponowna kompilacja, render, GATE C. Bez automatycznej publikacji.

## M5: przenosnosc i skala

Adapter Claude Code po aktualnej weryfikacji zasad, drugi kurs, limity kolejki,
magazyn artefaktow i koszt zaakceptowanej minuty. Nie budowac przed testem M2/M3.
