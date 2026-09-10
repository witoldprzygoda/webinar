# M1b: diagnostyka granicy dostepu do plikow

To ograniczony test Windows na plikach syntetycznych. Nie uruchamia LLM,
lekcji, audio ani Prefect. Nie zmienia produkcyjnego adaptera Codex.

## Wynik poprzedniej wersji

Raport operatora z 10.09.2026, codex-cli 0.153.4: author PASS, judge FAIL,
arbiter FAIL. Sedzia mogl odczytac private.txt autora, a arbiter private.txt
autora i sedziego. Zapis rubric i cudzych wynikow pozostawal zablokowany.
Wniosek: profil natywny NIE zapewnil wymaganej separacji miedzy rolami.
Poprawnych testow jednostkowych nie wolno utozsamiac z poprawna izolacja OS.

Kod Codex potwierdza, ze ACL sa stanowe i pozostaja po zakonczeniu polecen.
Windows przyznaje pierwszenstwo wpisom bezposrednim przed dziedziczonymi.
To wiarygodna hipoteza mechanizmu obserwowanego problemu, ale nie mamy zrzutu
DACL z maszyny operatora i nie oglaszamy pelnej diagnozy przyczyny.

## Poprawka: dodatkowa warstwa, nie zmiana oczekiwan testu

Natywny profil uprawnien pozostaje bez zmian: cudze katalogi sa deny,
wspolne dowody sa read, tylko wlasny katalog wyniku jest write, siec wylaczona.

Domyslnie test dodaje teraz fixture ACL guard:

1. Poza sandboxem weryfikuje istnienie i dostepnosc wszystkich probek.
2. Enumeruje cudze drzewa testowe, odrzucajac symlinki i reparse points.
3. Na KAZDYM istniejacym pliku i katalogu tych drzew dodaje bezposredni
   wpis deny FullControl dla istniejacej lokalnej grupy CodexSandboxUsers.
   Nie polega wylacznie na dziedziczeniu zakazu z katalogu nadrzednego.
4. Uruchamia niezmieniony profil `codex sandbox` i proby dostepu.
5. Po poleceniu odtwarza zapisane DACL chronionych obiektow, takze po bledzie.
   Wczesniejsze uprawnienia pozostaja w tescie, nie tworzymy czystych probek
   dla kazdej roli tylko po to, by otrzymac PASS.

Dodatkowe ACL dotycza WYLACZNIE swiezo utworzonych plikow syntetycznych.
Skrypt nie ma opcji przekazania prawdziwego katalogu kursu do ochrony.
Identyfikator tymczasowego katalogu jest sprawdzany przed zmiana/odtworzeniem ACL.
Nie zmieniamy config.toml, auth.json, kont, czlonkostwa grup ani uprawnien repo.
Nie prosimy o administratora. Gdy operator nalezy do grupy objetej zakazem,
brakuje grupy albo nie mozna ustawic/odtworzyc ACL, wynik to ERROR.

Helper `scripts/fixture_acl.ps1` jest wywolywany przez Windows PowerShell
z Pythona. Uzywamy stalego kodu polecen (EncodedCommand) i danych JSON na stdin;
nie zmieniamy ExecutionPolicy i nie uzywamy Bypass, profilu powloki ani UAC.
Komendy operatora nadal sa dla Git Bash. Niczego nie trzeba doinstalowywac.

## Silniejszy test

Ten sam zestaw probek jest uzywany kolejno przez:

    author -> judge -> arbiter -> author -> arbiter -> judge -> author

Kazda rola wraca po wczesniejszych uruchomieniach; wszystkie szesc kierunkow
przejscia miedzy roznymi rolami jest sprawdzonych. Wynik wczesniejszego kroku
nie jest nadpisywany pozniejszym PASS. Test zawiera rowniez listing katalogow,
czytanie zagniezdzonych plikow, czytanie cudzych raportow i wczesniej
utworzonego wyjscia oraz niezalezna kontrole hashy tresci probek.
Nie poluzowano zadnej z 12 pierwotnych prob.
Brak pliku, blad launchera, brak JSON lub awaria helpera NIE oznaczaja DENIED.

## Uruchomienie w Git Bash

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_codex_boundary.py' -v &&
./.venv/Scripts/python.exe scripts/check_codex_boundary.py
```

Serwer Prefect moze pozostac uruchomiony, ale nie uczestniczy w tej probie.
Zamknij inne aktywnie wykonujace polecenia sesje Codex na czas testu: profil
natywny korzysta ze wspolnego stanu systemowego. Test jest celowo sekwencyjny.

Opcjonalne odtworzenie profilu bez dodatkowego guardu:

```bash
./.venv/Scripts/python.exe scripts/check_codex_boundary.py --native-only
```

Nie nalezy go wykonywac jako warunku startu. Poprzedni negatywny wynik jest znany.

## Raport i uczciwy zakres PASS

Konsola pokazuje krotki raport; wszystkie proby pozostaja w
`runs/boundary-probe/<id>/summary.json` i lokalnych logach ignorowanych przez Git.

- `filesystem_probe: PASS`: wszystkie kroki/proby dostepu w tym przebiegu przeszly.
- `FAIL`: co najmniej jedna proba wykazala dostep sprzeczny z oczekiwaniami.
- `ERROR`: nie udalo sie miarodajnie przeprowadzic calej proby.
- `guard_mode: native_plus_fixture_acl`: wynik dotyczy OBU warstw, nie samego Codex.

`isolation_verified`, `instruction_isolation_verified`, `production_ready`
i `network_isolation_tested` nadal false. Nie testujemy MCP, dostepu modelu
do plikow, automatycznych instrukcji, pamieci ani sieci. Nie poprawiamy
samego Codex ani nie twierdzimy, ze jego natywny profil zostal naprawiony.

Ten guard NIE jest jeszcze ogolnym mechanizmem produkcyjnym. W szczegolnosci:
nie testuje wspolbieznosci, asynchronicznych zmian ACL przez inne sesje,
hardlinkow, innych drog dostepu, niezmiennosci przyszlych plikow ani awarii
komputera w trakcie operacji. Nie stosowac do danych operatora. Przed M2
pozostaja testy izolacji instrukcji i integracja przyjetego mechanizmu
w rzeczywistym wykonawcy, a nie tylko w programie diagnostycznym.

## Wykonane testy

28 testow jednostkowych PASS w kontenerze Linux. Zawieraja realne uruchomienie
Pythona dla kontroli probek, kontrole wszystkich kierunkow zmian rol,
niezmiennosci oczekiwan, obslugi bledow i przywracania ACL w mockach.
Kompilacja skladni modulow Python PASS.

Windows PowerShell, rzeczywiste DACL i natywny sandbox NIE zostaly wykonane
w kontenerze Linux. Tylko lokalny przebieg operatora zweryfikuje ich integracje.
Testy nie wywolywaly modelu i nie pobieraly kredytow.

## Zrodla techniczne

- openai/codex, rust-v0.153.4, `codex-rs/windows-sandbox-rs/src/deny_read_state.rs`:
  https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/windows-sandbox-rs/src/deny_read_state.rs
- Ta sama wersja, `src/acl.rs` i `src/bin/setup_main/win.rs`:
  https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/windows-sandbox-rs/src/acl.rs
  https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/windows-sandbox-rs/src/bin/setup_main/win.rs
- Microsoft, Order of ACEs in a DACL:
  https://learn.microsoft.com/en-us/windows/win32/secauthz/order-of-aces-in-a-dacl
- Codex Permissions: https://developers.openai.com/codex/permissions/

PRODUCTION_WORKFLOW.md, QUALITY_RUBRIC.md oraz kryteria odbioru M1 pozostaja bez zmian.
