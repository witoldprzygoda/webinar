# M2: kalibracja poziomu odbiorcy

Pierwszy Gate A dla `python-console-calculator` został odrzucony przez człowieka
mimo PASS obu sędziów. Powód: narracja była formalnie poprawna, lecz zbyt nisko
ustawiała zakładany poziom kompetencji odbiorcy (m.in. objaśnianie oczywistych
symboli i promptu). To jest wada systemowa, nie pojedyncza korekta stylistyczna.

Od rubric 0.2 każda lekcja musi jawnie wskazać `audience_profile`. Domyślny profil
pierwszego kursu to `cs_year3`: studenci III roku informatyki / technicznie biegli
odbiorcy. Profil rozdziela wiedzę zakładaną od treści, które należy wyjaśniać.

Nowe kryterium L4 wymaga, aby poziom przekazu odpowiadał temu profilowi. Tekst
może być poprawny faktograficznie i językowo, a mimo to otrzymać REVISE za
infantylizację, tłumaczenie wiedzy bazowej lub narracyjne opisywanie oczywistego
interfejsu zamiast istotnej semantyki.

Profil jest kontrolowanym wejściem autora, judge-content i judge-language. Gate A
odrzuca wyniki oparte na starszej rubric albo bez profilu odbiorcy. Stary artefakt
`b97a51508cce4bbac219b842669c5e12770ec07f828d4b4c8def35647a16a7ed`
pozostaje historycznym przypadkiem kalibracyjnym i nie może być zatwierdzony pod
rubric 0.2.

Następny przebieg zaczyna się ponownie od M2a. Nie należy ręcznie poprawiać starego
artefaktu ani pomijać nowych sędziów.
