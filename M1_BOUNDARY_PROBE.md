# M1b: diagnostyka granicy dostepu do plikow

To ograniczony test sandboxowanych polecen Windows, nie gotowa izolacja
agenta ani odbior calego M1. Nie uruchamia modelu LLM lub ElevenLabs.

## Uruchomienie w Git Bash

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_codex_boundary.py' -v
./.venv/Scripts/python.exe scripts/check_codex_boundary.py
```

Prefect nie jest wymagany do tego testu i moze pozostac uruchomiony.
Nie trzeba niczego instalowac. Test jest przypiety do codex-cli 0.153.4,
ktore operator potwierdzil. Inna wersja zatrzymuje test zamiast zgadywania opcji.

## Co jest sprawdzane

Dla kazdej roli author / judge / arbiter powstaje oddzielne wywolanie
`codex sandbox -P webinar_boundary_probe ... -- <python.exe> ...`.
W tej wersji na Windows NIE ma dodatkowej podkomendy `windows`.
Profil uprawnien jest przekazywany jako argument, bez edycji config.toml.
Skrypt zachowuje wymagania zarzadzane przez `--include-managed-config`.
Nie uruchamia `codex exec`, nie loguje ponownie i nie kopiuje auth.json.

Powstaja wylacznie syntetyczne, tymczasowe pliki testowe:

- wspolne dowody i rubric: odczyt dozwolony, zapis zabroniony;
- zgoda operatora: zapis zabroniony;
- prywatny plik biezacej roli: odczyt dozwolony;
- wlasny katalog wyniku: utworzenie pliku dozwolone;
- prywatne pliki i wyniki innych rol: odpowiednio odczyt/zapis zabronione;
- plik poza lista dostepu: odczyt zabroniony.

Najpierw ten sam Python wykonuje kontrole pozytywna poza sandboxem: wszystkie
pliki musza istniec i byc dostepne. Potem wykonuje identyczne operacje w sandboxie.
Test zapisu istniejacego pliku tylko otwiera go do zapisu, bez modyfikacji tresci.
Nowy plik jest tworzony tylko w tymczasowym katalogu wyniku.
Brak pliku, blad uruchomienia albo brak odpowiedzi NIE sa uznawane za dowod odmowy.

## Raport

`runs/boundary-probe/<id>/summary.json` zawiera wynik i szczegoly testow.
Pelne stdout/stderr sa tylko w lokalnych plikach ignorowanego katalogu runs/.

- `filesystem_probe: PASS`: wszystkie operacje na probkach zachowaly sie zgodnie
  z oczekiwaniami w tym uruchomieniu.
- `filesystem_probe: FAIL`: proces dzialal, ale co najmniej jedna operacja dala
  inny wynik niz wymagany.
- `filesystem_probe: ERROR`: nie udalo sie miarodajnie wykonac testu.

`isolation_verified`, `instruction_isolation_verified` i `production_ready`
pozostaja false nawet przy PASS. Nie sa testowane MCP, wbudowana przegladarka,
automatyczne instrukcje, pamiec klienta, dziedziczenie kontekstu ani eskalacje.
`network_isolation_tested` pozostaje false: profil zada blokady sieci procesu,
ale skrypt nie wykonuje prob polaczen. Sam klient Codex moze ladowac swoja
konfiguracje i wymagania; nie jest to deklaracja calkowitego braku ruchu sieciowego.

Nie ma zmian w prywatnych materialach operatora ani recznej zmiany jego
konfiguracji. Codex korzysta z wlasnej istniejacej instalacji sandboxa i moze
zapisywac swoje standardowe dane techniczne. Nie nadajemy sobie dodatkowych
uprawnien i nie wylaczamy sandboxa, gdy test nie przechodzi.

## Istotne ograniczenie konfiguracji

Wedlug dokumentacji profile permissions i legacy sandbox_mode nie powinny byc
mieszane. Istniejacy legacy sandbox_mode moze spowodowac, ze oczekiwany profil
nie zostanie zastosowany. Skrypt niczego wtedy sam nie usuwa ani nie naprawia;
wynik operacji ma ujawnic problem. Niezgodnosc polityki z wariantem sandboxa
Windows rowniez oznacza ERROR/FAIL, nie zgode na slabsza izolacje.

## Wykonane testy

12 nowych testow unittest PASS w kontenerze Linux, w tym rzeczywiste wykonanie
lokalnego procesu Python na probkach i kontrola, ze brak pliku nie staje sie
pozorna odmowa dostepu. Kompilacja skladni PASS. Nie uruchamiano rzeczywistego
Codex ani sandboxa Windows w tym kontenerze. Ten ostatni wymaga uruchomienia
na komputerze operatora. Nie deklarujemy na tej podstawie produkcyjnej izolacji.

## Sprawdzone zrodla

- https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/cli/src/main.rs
- https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/cli/src/lib.rs
- https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/cli/src/debug_sandbox.rs
- https://developers.openai.com/codex/permissions/

Skrypt korzysta z argumentow opisanych w kodzie wersji operatora, a nie
ze zgadywanej skladni dla innych platform.
