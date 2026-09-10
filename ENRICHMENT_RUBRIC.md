# Enrichment rubric

Wersja 0.1. Ta rubric dotyczy wyłącznie fakultatywnego wzbogacania poprawnego
rdzenia lekcji. Nie jest częścią obowiązkowej QUALITY_RUBRIC i nie może obniżyć
oceny lekcji tylko dlatego, że nie znaleziono dobrego enrichmentu.

## Zasada nadrzędna

Brak enrichmentu jest poprawnym wynikiem. Nie ma wymaganej liczby kandydatów ani
KEEP. Słaby enrichment jest gorszy niż jego brak.

Profil `technical_competent` oznacza sprawnego technicznie odbiorcę, ale NIE
specjalistę od wszystkich idiomów, pułapek i zachowań Pythona. Nie wolno
odrzucać wartościowej pułapki tylko dlatego, że „dobry informatyk powinien to
wiedzieć”. Szczególnie cenne są krótkie ostrzeżenia przed błędami, które są
składniowo poprawne, wykonują się bez wyjątku i dają wiarygodnie wyglądający,
ale inny wynik niż zamierzony.

## Wymiary oceny kandydata

Każdy wymiar korzyści oceniany jest 0-2:

- R1 relevance: bezpośrednie dopasowanie do aktualnego tematu i miejsca wpięcia.
- R2 novelty_for_audience: niebanalność dla jawnego profilu odbiorcy. To wymiar
  pomocniczy, NIE warunek KEEP. Kandydat o novelty=0 lub 1 może zasługiwać na
  KEEP, jeżeli dobrze zapobiega realnej pomyłce albo daje praktyczny skrót.
- R3 practical_transfer_value: użyteczność praktyczna, prewencja realnego błędu
  albo transfer do innych sytuacji, narzędzi lub języków.
- R4 clarity_gain: czy kandydat poprawia rozumienie mechanizmu, granic lub pułapki.

Każdy koszt również oceniany jest 0-2, gdzie więcej oznacza gorzej:

- C1 digression_risk: ryzyko odejścia od osi lekcji. Samo nazwanie operatora lub
  mechanizmu potrzebnego do wyjaśnienia pułapki nie jest jeszcze dygresją.
- C2 prerequisite_burden: ilość nowej wiedzy potrzebnej tylko po to, by zrozumieć
  enrichment.

Dodatkowo podawany jest szacowany koszt w sekundach narracji.

## Szczególnie wartościowe klasy enrichmentu

Preferuj kandydatów, którzy przy małym koszcie czasowym spełniają co najmniej
jeden z warunków:

- ostrzegają przed cichą pomyłką, która nie kończy się SyntaxError/TypeError;
- pokazują Python-specyficzną semantykę, której nie wynika z ogólnej znajomości
  programowania;
- pokazują inny praktyczny tryb uruchomienia tego samego kodu lub narzędzia;
- łączą dwa właśnie omawiane mechanizmy w użyteczny idiom;
- ujawniają granicę prostej reguły lub zmianę typu/zachowania w nieoczywistym
  przypadku.

## Decyzje

- KEEP: prawdziwy, dobrze udokumentowany i wart czasu w tej konkretnej lekcji.
- MAYBE: ma potencjał, ale wymaga arbitrażu z powodu niepewnego dopasowania,
  kosztu, dowodu lub kompromisu dydaktycznego.
- DROP: banalny bez wartości prewencyjnej/praktycznej, dygresyjny, zbyt kosztowny,
  niedopasowany do odbiorcy albo niewystarczająco udokumentowany.

Nie stosujemy automatycznej sumy punktów jako decyzji. Oceny wymiarów pomagają
uzasadnić decyzję, ale KEEP/MAYBE/DROP pozostaje oceną jakościową. Niska
`novelty_for_audience` sama w sobie nie uzasadnia DROP.

## Weryfikowalność

Każdy kandydat musi wskazać jawne source_support_ids. Jeżeli późniejsze dodanie
kandydata wprowadza kod, wynik, zachowanie CLI lub inne twierdzenie możliwe do
sprawdzenia wykonaniem, integrator musi dodać odpowiedni plan weryfikacji. Po
integracji powstaje nowy hash artefaktu i ponownie obowiązuje pełna QUALITY_RUBRIC.
