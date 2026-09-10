# M2f — integracja enrichmentu i ponowny Gate A

M2f przyjmuje ukończony M2e z co najmniej jednym wybranym kandydatem.

Kolejność:

1. weryfikacja całego łańcucha M2b -> M2d -> M2e,
2. połączenie źródeł rdzenia i enrichmentu z zachowaniem provenance,
3. świeża sesja `enrichment_integrator`,
4. walidacja, że zaakceptowany rdzeń narracji i jego execution_plan nie zostały zmienione,
5. wykonanie oryginalnego execution_plan rdzenia,
6. wykonanie strukturalnego `enrichment.verification_plan`, w tym prawdziwych wywołań `python -c` przez `shell=False`,
7. świeży niezależny `judge_content` dla nowego hasha,
8. przy PASS — świeży niezależny `judge_language`,
9. przy dwóch PASS — nowy Gate A dla człowieka.

Integrator nie może przywracać kandydatów DROP ani wymyślać nowych enrichmentów.
Może redagować wyłącznie tekst wybranych dodatków, zachowując sens i źródła.
Kanoniczna narracja używa przenośnej składni `python -c`; dokładny CPython 3.14.7
jest wybierany przez executor i nie jest zakodowany w tekście wykładu.

Każdy nowy konkretny przykład musi być powiązany z nowym fragmentem przez
`candidate_id`, `fragment_ids` i strukturalny check. Executor nie uruchamia
modelowych stringów jako poleceń shella.

M2f tworzy nowy hash artefaktu. Poprzedni Gate A nie zatwierdza nowego artefaktu.
Audio i render pozostają wyłączone.
