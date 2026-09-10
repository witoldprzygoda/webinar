# Procedura produkcji webinarów

Wersja 0.1. Jest to kontrakt docelowy. Stan implementacji opisuje
IMPLEMENTATION_PLAN.md; wymagania nie są deklaracją już działających funkcji.

## 1. Cel i zasady nadrzędne

Z jasno wskazanego materiału powstaje profesjonalny, precyzyjny tekst do
wygłoszenia, potem zaakceptowana realizacja wizualna, a dopiero następnie audio
ElevenLabs i film Remotion. System obsługuje wiele kursów; Python jest pierwszym.

Prefect odpowiada za kolejność, stan, limity i bramki. Modele wykonują wydzielone
zadania. Nie ma nadrzędnego agenta LLM, który zmienia warunki odbioru.
Wytwórca przedstawia propozycję; niezależna ocena i człowiek decydują o odbiorze.

## 2. Materiały i know-how z dowolnych dostępnych źródeł

config/sources.json jest rozszerzalnym rejestrem: repozytorium, lokalny plik,
PDF, witryna, dokumentacja, wzorzec wizualny, opis doświadczenia. Nie ograniczamy
wiedzy do dwóch pierwszych repozytoriów. Dostęp respektuje uprawnienia operatora.

Rozróżniamy: material (zakres kursu), evidence (dowód), knowhow (doświadczenie
warsztatowe) oraz reference (jawnie zaakceptowany wzorzec konkretnej cechy).
Samo zarejestrowanie starego filmu nie nadaje mu statusu poprawnego wzorca.

Resolver dla każdego przebiegu zapisuje pochodzenie, dokładną ścieżkę/strony,
commit lub datę pobrania, hash treści i cel wykorzystania. Branch/URL to punkt
wejścia; produkcja używa utrwalonego snapshotu. Ekstrakcję kodu z PDF trzeba
sprawdzić. Dla repozytorium preferujemy Markdown, nie pośredni PDF.

Autor, projektant i sędzia mogą wnioskować o dodatkowe źródła.
Sędzia ma niezależny dostęp do dowodów, nie tylko listę wybraną przez autora.
Rozszerzenie dostępu jest jawne i zapisane. Zewnętrzne instrukcje nie przejmują
kontroli nad zadaniem, uprawnieniami ani kryteriami.

Know-how dla sędziego obejmuje neutralne fakty i zatwierdzone referencje, nie
historię autora ani wcześniejszy werdykt o aktualnym artefakcie. Etykiety
kalibracyjnych przypadków testowych nie są ujawniane podczas ślepego testu.

## 3. Niezależność sędziego i arbitra: wymóg techniczny

Każda ocena oraz arbitraż otrzymują nowy proces CLI, nową sesję bez resume/fork
sesji autora i osobny katalog zadania. Wywołuje je Prefect, nie autor jako podagentów.

Wejście jest wyliczone jawnie: artefakt, brief, rubric, przykłady, wykonania,
dowody oraz neutralne referencje potrzebne dla roli. Recenzent języka dostaje
tekst i profil odbiorcy; merytoryczny także kod i dowody. Arbiter dodatkowo
otrzymuje zanonimizowane zgłoszenia i materiał potrzebny do rozstrzygnięcia.

Zabroniony jest dostęp do rozmów autora, samoocen, poprzednich pochwał,
prywatnych logów, historii Git z negocjacjami i wspólnej pamięci sesji.
Kontrolujemy automatycznie ładowane instrukcje, pluginy i konfigurację klienta.
Sędzia nie może dostać polecenia typu: "zalicz, bo to już piąta runda".

Sam katalog roboczy, tryb read-only ani --ephemeral NIE dowodzą izolacji od
odczytu innych plików. Implementacja stosuje sprawdzone ograniczenia systemowe,
np. odpowiednio ograniczony sandbox, osobne konta OS lub kontenery/VM.
Dobór mechanizmu i testy negatywnego dostępu należą do M1.
Nie wyłączamy zabezpieczeń, by ułatwić uruchomienie.

Autor zapisuje propozycję, lecz nie rubric, cudze raporty ani zgody człowieka.
Sędzia zapisuje raport, nie edytuje ocenianej wersji. Arbiter rozstrzyga,
nie poprawia tekstu i nie publikuje. Hashe wejść są sprawdzane po zadaniu.

Wymagana jest niezależność procesu i kontekstu. Wspólne błędy tego samego
modelu nadal są możliwe; niezależność wykonania nie gwarantuje bezbłędnej oceny.
Sędziów kalibrujemy na znanych wadach oraz poprawnych przykładach.

## 4. Zlecenie i punkt odniesienia

Brief określa: course_id, lesson_id, materiał, odbiorcę, wymagania wstępne,
tematy wymagane/wyłączone, język, zakres aktualizacji, środowisko i budżet.
Powstaje source-pack konkretnej lekcji, nie cały kurs w kontekście każdego agenta.

Wersje Pythona/bibliotek, system operacyjny i data weryfikacji są jawne.
Python uruchamiający Prefect jest niezależny od Pythona nauczanego w kursie.
Test na innym systemie nie potwierdza instrukcji specyficznej dla Windows.
Niedostępne środowisko oznacza brak weryfikacji, nie domniemany wynik.

## 5. Etap A: scenariusz merytoryczny

Autor tworzy profesjonalny tekst mówiony: najpierw wprowadzenie pojęcia,
potem mechanizm, uzasadnienie i przykład. Bez potoczności, pustych zdań,
zastępowania wyjaśnień metaforami i mylących skrótów myślowych.
Nie narzucamy uniwersalnej liczby scen ani długości całego filmu.

Artefakty: script.md, examples/, execution-results.json, evidence.json,
coverage.json. Tekst i przykłady mają trwałe identyfikatory. Tekst kanoniczny
zachowuje normalną pisownię nazw, bez fonetycznych zamienników dla TTS.
Przykłady są już powiązane z wyjaśnieniami, ale bez reżyserowania animacji.

Twierdzenia zależne od wersji sprawdzamy w aktualnych źródłach pierwotnych.
Executor naprawdę uruchamia kod bez sekretów, z limitami czasu/pamięci/uprawnień.
Zapisuje stdin, stdout, stderr, exit_code, wersje i OS. Celowy błąd jest oznaczony.

Następnie osobno pracują judge-content oraz judge-language według rubric.
Uwagi mają cytat, kryterium, wagę, dowód i zakres pewności.
Arbiter ocenia sporne lub istotne uwagi: trafność obserwacji OSOBNO od
poprawności proponowanej zmiany. Zła poprawka nie unieważnia trafnej obserwacji.

Poprawkę wykonuje autor/rewriter w następnym zadaniu. Powstaje nowy hash i nowa,
niezależna ocena. Domyślnie najwyżej trzy cykle naprawy; nierozstrzygnięte
kwestie trafiają do człowieka, nie do automatycznej akceptacji.

GATE A: człowiek zatwierdza konkretną wersję treści i przykładów.

## 6. Etap B: plan scen i warianty

Projektant otrzymuje zatwierdzony tekst i przykłady. Proponuje 2-3 warianty
krótkiego fragmentu, różniące się sposobem objaśnienia, nie samym kolorem.
Po wyborze powstaje scene-plan.json całej lekcji. Każda kwestia narracji jest
powiązana z widocznym kodem, wynikiem, diagramem lub innym elementem.

Korzystamy ze sprawdzonych komponentów Remotion. Nowa forma wizualna może
powstać kreatywnie, ale przechodzi osobne zadanie programistyczne i odbiór.
Zmiana treści/przykładu wymuszona sceną wraca do etapu A.

## 7. Etap C: animowany podgląd bez głosu

Z planu powstaje preview-timing.json i podgląd Remotion. Aktualna kwestia
lektora jest widoczna poza kadrem lub w osobnej warstwie roboczego eksportu,
aby nie zasłaniać kodu. ElevenLabs pozostaje wyłączony.

Wskazanie jest związane z identyfikatorem fragmentu narracji i celem
(example_id + anchor_id), nie z bezwzględną sekundą ani pikselem.
Kompilator wyznacza panel/linie, renderer geometrię. Jest jeden tor wskaźnika.
Szacunkowe czasy są jawnie tymczasowe; nie zatwierdzamy ich jako czasu audio.

Kontrola techniczna obejmuje m.in. cele, widoczne panele, zakresy linii,
niepożądane nakładanie elementów, konflikty ruchu i czytelność.
Niezależny sędzia ogląda rzeczywiste klatki/sekwencje/klipy.
Sama klatka nie dowodzi płynności, a transkrypcja nie dowodzi poprawnej wymowy.
Brak odpowiednich możliwości narzędzia oznacza NOT_VERIFIED i ocenę człowieka.

GATE B: człowiek zatwierdza projekt realizacji, jeszcze nie rytm prawdziwego głosu.

## 8. Etap D: audio i rzeczywisty czas

Tekst TTS powstaje z tekstu kanonicznego i słownika wymowy. Zachowujemy mapowanie
również po normalizacji tekstu przez dostawcę. Najpierw próbka trudnych nazw
w pełnych zdaniach i jej akceptacja; dopiero potem pozostałe nagrania.
Synteza wymaga jawnej zgody na wykorzystanie kredytów ElevenLabs.

Przechowujemy oryginał audio, wynik obróbki, ustawienia, tekst TTS,
identyfikator żądania i wyrównanie tekst/czas. Po cięciu ciszy odpowiednio
przesuwamy oś czasu i kontrolujemy końcówki wypowiedzi.

Rzeczywisty timing zastępuje roboczy. Z tych samych semantycznych identyfikatorów
kompilujemy ruch ponownie. Powtarzamy testy czasu wskazania, widoczności treści
i pomieszczenia całej wypowiedzi w scenie.

## 9. Etap E: render i odbiór

Powstaje finalny film i raport kontroli. Sędzia końcowy jest nowym procesem,
nie projektantem scen. Ocenia rzeczywisty wynik, nie deklarowany zamiar.
GATE C: człowiek akceptuje wymowę, tempo, obraz i synchronizację.
Publikacja wymaga osobnej jawnej decyzji; nie jest skutkiem ubocznym renderu.

## 10. Sukces, stan i koszty

Exit code 0 i istnienie pliku oznaczają tylko wykonanie zadania.
Sukces to przejście QUALITY_RUBRIC.md, testów i odpowiednich bramek człowieka.
Nie stosujemy średniej, która kompensuje błąd rzeczowy dobrym wyglądem.
Autor nie zmienia kryteriów; ich nowa wersja wymaga zgody człowieka.

Stan biznesowy (WAITING_HUMAN, REVISION_REQUIRED, BLOCKED_LIMIT) jest niezależny
od stanu technicznego Prefect. Poprawnie zakończone flow może dostarczyć raport
odrzucenia; nie oznacza to zaakceptowanej lekcji.

LLM: oficjalny Codex CLI z logowaniem ChatGPT, opcjonalnie Claude Code po teście
uprawnień i rozliczenia. Brak automatycznego fallbacku do płatnego API i zakupów
kredytów. Limity zatrzymują kolejkę; nie obchodzimy ich i nie dzielimy konta
z osobami trzecimi. Mechanizm logowania musi być potwierdzony na koncie operatora.

Cache odpowiada zależnościom: ruch wskaźnika nie zmienia audio; zmiana zdania
zmienia jego nagranie i zależną synchronizację. Jeśli TTS używa sąsiednich zdań,
ten kontekst także należy do klucza cache. Uwzględniamy konfigurację, prompt,
rubric i wersje narzędzi. Review jest ważne tylko dla wskazanego hasha.

Timeout kosztownego wywołania nie oznacza bezpiecznego retry. Nieznany wynik
wymaga wyjaśnienia po identyfikatorze, nie ślepego ponowienia.
Zgoda człowieka zawiera hash, osobę, datę i decyzję. Zmiana danych unieważnia
zależne zgody. Autor nie ma uprawnień do ich zapisu.

## 11. Adaptacja doświadczeń python-webinar

Po przypięciu wersji badamy potrzebne elementy:

| Referencja | Przedmiot adaptacji |
| --- | --- |
| AGENTS.md | Recenzja, obserwacja vs poprawka, kalibracja |
| wideo/RECEPTURA.md | Precyzja, wprowadzenie, zgodność obrazu z narracją |
| scripts/uruchom-przyklady.py | Rzeczywiste wyniki kodu |
| scripts/buduj-scenariusz.py | Kompilacja i walidacja |
| scripts/narracja.mjs | Cache, wyrównanie i kontrola nagrań |
| wideo/render/src/duration-source.ts | Roboczy i rzeczywisty czas |
| wideo/render/src/spotlight-timeline.ts | Pojedynczy tor uwagi |
| wideo/out/wyrazenia-warunkowe-v6/ | Materiał porównawczy, nie automatyczny wzorzec sukcesu |

Nie przenosimy ograniczeń jednego rozdziału jako reguł dla wszystkich kursów.
Nie kopiujemy starych instrukcji do sędziego. Zidentyfikowane sprzeczności
rozstrzygamy przez nową procedurę i dowody, nie przez dawną deklarację sukcesu.

## 12. Podstawy techniczne

Procedura powyżej jest projektem tego repozytorium. Dokumentacja sprawdzona 10.09.2026:

- [Lokalny Prefect](https://docs.prefect.io/v3/how-to-guides/self-hosted/server-cli).
- [Bramki człowieka w Prefect](https://docs.prefect.io/v3/advanced/interactive).
- [Codex: logowanie](https://developers.openai.com/codex/auth).
- [Codex: tryb nieinteraktywny](https://developers.openai.com/codex/noninteractive).
- [Doświadczenia recenzji](https://github.com/witoldprzygoda/python-webinar/blob/master/AGENTS.md).
- [Narzędzia produkcyjne](https://github.com/witoldprzygoda/python-webinar/blob/master/scripts/README.md).

Odsyłacze do branchy służą odkrywaniu źródeł. Rzeczywisty przebieg utrwala
konkretne wersje. Wpis w procedurze nie zastępuje testu implementacji.
