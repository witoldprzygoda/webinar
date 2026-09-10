# Kryteria niezależnego odbioru

Wersja 0.2. Zmiana wymaga zgody człowieka odpowiedzialnego za kurs.

| ID | Kryterium | Etap |
| --- | --- | --- |
| F1 | Poprawność faktów, brak nieuprawnionych uogólnień | Treść |
| F2 | Aktualność wersji, dowody i jawny punkt odniesienia | Treść |
| E1 | Zgodność narracji z kodem i rzeczywistym wynikiem | Treść |
| E2 | Wykonanie we właściwym środowisku, brak zgadywania outputu | Treść |
| L1 | Poprawna, precyzyjna terminologia i rozróżnienia pojęć | Treść |
| L2 | Profesjonalny, nie potoczny język; zdania zrozumiałe przy słuchaniu | Treść |
| L3 | Brak pustych zdań, mylących odniesień i zbędnych powtórzeń | Treść |
| L4 | Poziom przekazu adekwatny do jawnie wskazanej grupy odbiorców; brak infantylizacji i objaśniania wiedzy bazowej, którą profil odbiorcy zakłada jako opanowaną | Treść |
| D1 | Pokrycie briefu i zachowanie wymagań wstępnych | Treść |
| D2 | Czytelne wprowadzenie do nowego obrazu/listingu przed analizą | Plan/podgląd |
| V1 | Widoczność i czytelność omawianego elementu, brak zasłaniania | Podgląd |
| V2 | Poprawny cel, timing i czytelny ruch wskaźnika | Podgląd/final |
| A1 | Wymowa, pełne końcówki wypowiedzi, zrozumiałe tempo | Audio/final |
| A2 | Synchronizacja z rzeczywistym audio | Final |
| P1 | Niezależna ocena właściwego artefaktu i wersji rubric | Każda bramka |

Kryterium: PASS / FAIL / NOT_VERIFIED / NOT_APPLICABLE z uzasadnieniem.
Kryteriów przyszłego etapu nie oceniamy na wyrost. Brak dowodu nie oznacza PASS.

Werdykt: PASS (spełnione wymagania etapu), REVISE (uzasadniona wada wymagająca
zmiany), BLOCKED (brak danych, środowiska lub niezależności uniemożliwia ocenę).
Poważny błąd rzeczowy nie może być skompensowany atrakcyjnym wyglądem.
Drobne, jawne uwagi nie muszą blokować etapu, jeśli wymagania są spełnione.

L4 ocenia kalibrację poziomu, a nie trudność samego tematu. Autor może wprowadzić
prosty temat, ale nie powinien tłumaczyć oczywistych symboli, elementarnych operacji
ani interfejsu na poziomie niższym niż zadeklarowana wiedza wstępna odbiorcy.
Wyjaśnienie podstawy jest dopuszczalne tylko wtedy, gdy brief lub profil odbiorcy
wprost tego wymaga albo gdy dana różnica jest specyficzna dla omawianego języka,
środowiska lub stanowi realną pułapkę. Sędzia ma odróżniać krótkie pedagogiczne
wprowadzenie do przykładu od rozwlekłego opisywania tego, co kompetentny odbiorca
już rozpoznaje.

Raport zawiera artifact_sha256, rubric_version, role, run_id, verdict,
coverage_checks i findings. Uwaga: criterion_id, severity (high/medium/low),
cytat lub trwały identyfikator sceny, opis wady, dowód, pewność i ewentualna poprawka.
Arbiter osobno zapisuje observation_valid i proposed_fix_valid z uzasadnieniem.

Sędzia nie ma zadanej liczby błędów do znalezienia ani oczekiwanego werdyktu.
Przed użyciem produkcyjnym testujemy go na znanych wadach i poprawnych przykładach.
Mierzymy przeoczone błędy i fałszywe alarmy. Zmiana modelu, promptu lub kryteriów
wymaga ponownej kalibracji. Test nie dowodzi bezbłędności modelu.

## Zmiana 0.2

Dodano L4 po odrzuceniu przez człowieka artefaktu, który był formalnie poprawny,
ale zakładał zbyt niski poziom kompetencji odbiorcy. Profil odbiorcy staje się
obowiązkowym wejściem autora i sędziego narracji; "profesjonalny język" nie jest
już traktowany jako wystarczający substytut właściwego poziomu merytorycznego.
