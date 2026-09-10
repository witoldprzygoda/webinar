# M2c: niezalezny sedzia jezykowy i Gate A

M2c nie regeneruje autora i nie zmienia artefaktu. Przyjmuje tylko ukonczony M2b,
w ktorym ten sam hash artefaktu ma PASS sedziego merytorycznego oraz prawidlowy
dowod wykonania.

Nowa sesja `judge_language` otrzymuje tylko brief, rubric, hash oraz kanoniczna
narracje. Nie otrzymuje source-pack, execution evidence, raportu sedziego
tresciowego, jego werdyktu, sesji autora ani historii rozmowy. Ocena obejmuje
L1, L2, L3 i P1. PASS jest dopuszczalny tylko wtedy, gdy wszystkie cztery
kryteria maja PASS.

Prefect zna wynik M2b jedynie jako warunek przejscia. Po zakonczeniu niezaleznej
oceny laczy oba wyniki w `gate-a-package.json`. Nie jest to automatyczna zgoda:
`gate_a_status=PENDING_HUMAN_APPROVAL`, a `gate_a_approved=false`.

## Uruchomienie z wyniku M2b

```bash
./.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_m2c_language.py' -v

./.venv/Scripts/python.exe flows/m2c_language.py \
  runs/m2b-execution/<RUN_ID>
```

Po PASS sedziego jezykowego oczekiwane sa m.in.:

```json
{
  "status": "COMPLETED",
  "content_judge_pass": true,
  "language_judge_pass": true,
  "gate_a_reached": true,
  "gate_a_approved": false,
  "gate_a_status": "PENDING_HUMAN_APPROVAL"
}
```

Nastepnym krokiem jest rzeczywisty human Gate A: czlowiek czyta kanoniczna
narracje i oba raporty, a dopiero jawna akceptacja pozwala wejsc w projektowanie
scen. Audio i Remotion nadal nie sa uruchamiane.
