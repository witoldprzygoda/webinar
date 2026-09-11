# M3c — silent preview

M3c zaczyna się dopiero po jawnym zaakceptowaniu konkretnego planu M3b do
budowy podglądu. Ta zgoda NIE jest Gate B. Gate B następuje dopiero po obejrzeniu
i ocenie rzeczywistego podglądu.

## 1. Receipt akceptacji M3b

Dla zaakceptowanego runu M3b:

```bash
./.venv/Scripts/python.exe scripts/record_m3b_preview_acceptance.py \
  runs/m3b-scene-plan/<RUN_ID> \
  --accepted-by "Witold Przygoda"
```

Receipt `m3b-preview-acceptance.json` jest append-only i wiąże exact:

- Gate A artifact;
- Gate A approval;
- M3a selection;
- visual fact catalog;
- `scene_plan_sha256`.

Nie twierdzi, że Gate B został osiągnięty.

## 2. Kompilacja roboczego timingu i propsów

```bash
./.venv/Scripts/python.exe flows/m3c_preview.py \
  runs/m3b-scene-plan/<RUN_ID>
```

Flow nie wywołuje LLM, ElevenLabs ani Remotion. Tworzy nowy katalog
`runs/m3c-preview/<RUN_ID>/` z:

- `preview-timing.json` — jawnie tymczasowy timing szacowany z długości narracji;
- `preview-props.json` — exact scene plan + zatwierdzona narracja + hashe wejść;
- `summary.json`.

Timing ma typ `TEMPORARY_ESTIMATE_FOR_SILENT_PREVIEW` i deklaruje
`replace_with_audio_alignment=true`. Nie wolno później traktować go jako czasu
finalnego audio.

## 3. Pierwsze uruchomienie Remotion

Projekt Remotion jest w `remotion/`. Instalacja zależności jest potrzebna tylko
po zmianie `package.json`/lockfile albo na nowym checkout:

```bash
cd remotion
npm install
npm run typecheck
```

Następnie Studio uruchamiamy z plikiem props wygenerowanym przez M3c. Oficjalny
Remotion CLI przyjmuje na Windows ścieżkę do pliku JSON przez `--props`, co
unika problemów z quotingiem inline JSON.

Przykład z repo root:

```bash
cd remotion
npm run studio -- --props ../runs/m3c-preview/<RUN_ID>/preview-props.json
```

Studio wypisze lokalny URL. Dostępne są dwie kompozycje:

- `WebinarSilentPreview` — czysty kadr 1920x1080;
- `WebinarSilentReview` — ten sam kadr oraz osobny pasek roboczy pod spodem z
  aktualnym fragmentem narracji i instrukcją beatu.

Audio jest wyłączone. Samo otwarcie Studio nie wykonuje renderu mp4.

## 4. Zakres pierwszego renderera

Renderer jest data-driven i używa strukturalnych `reveals` oraz jednego
`focus_target_id`. Plan M3b nie ma jeszcze osobnego strukturalnego pola `hides`.
Dlatego renderer nie parsuje polskiego pola `action`. Po przejściu do następnego
fragmentu narracji wcześniej odsłonięte elementy, które nie są używane przez
beaty aktualnego fragmentu, są mocno wygaszane zamiast arbitralnie usuwane.

To ograniczenie jest celowe i widoczne podczas odbioru M3c. Jeśli rzeczywisty
preview pokaże, że potrzebujemy pełnego modelu visibility transitions, należy
rozszerzyć kontrakt semantyczny zamiast dodawać parser tekstu `action`.

Wyjątkiem jest zaakceptowany wariant kalibracyjny `v2`: renderer ma osobny
reusable `underscore-state-slot` — stałą nazwę `_`, jedno gniazdo wartości i
kolejne aktualizacje dopiero po odsłonięciu odpowiednich outputów.

## 5. Co oceniamy przed Gate B

Najpierw odbieramy rzeczywisty preview, a nie deklarację planu. Sprawdzamy:

- czytelność i hierarchię typografii;
- czy kod/output nie nakładają się i mieszczą w kadrze;
- kolejność reveal/focus;
- czy jeden tor uwagi pozostaje jednoznaczny;
- sceny `s04`, `s05`, `s08` pod kątem nadmiaru informacji;
- mechanikę `_` w `s07`;
- czy robocze czasy nie powodują nienaturalnych skoków.

Dopiero potem dochodzi automatyczna kontrola techniczna i niezależny
`judge-visual`, a następnie human Gate B. ElevenLabs pozostaje wyłączony do
zaakceptowania Gate B.
