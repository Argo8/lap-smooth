# lap-smooth — zaglađivanje polja visina valova

Alati za prostorno zaglađivanje rezultata numeričkih modela valova (SWAN, STWAVE,
CGWAVE…) na nepravilnim trokutastim mrežama, uz **očuvanje maksimuma** (max-preserving).
Izlazi su kompatibilni sa SMS softverom (Aquaveo) — XMDF/HDF5 format.

> Teoretska pozadina: [Teoretska osnova zaglađivanja polja visina valova.docx](Teoretska%20osnova%20zagla%C4%91ivanja%20polja%20visina%20valova.docx)

---

## Problem

Rezultati valnih modela interpretiraju se kao polje maksimalnih visina valova
(*Hmax*) na čvorovima proračunske mreže. Zbog ograničenog broja vremenskih koraka
i numeričkog šuma, polje sadrži lokalne oscilacije, skokove i nerealne točke koje
narušavaju čitljivost i tehničku primjenjivost rezultata.

Klasično zaglađivanje (npr. Gaussov filtar) rješava šum, ali **snižava vrhove** —
što je neprihvatljivo za projektiranje valobrana, lukobrana i obalnih građevina,
gdje su vršne vrijednosti sigurnosno relevantne.

## Metoda (V2.0 / v2.1)

Laplacovo prostorno filtriranje preko nepravilne (unstructured) trokutaste mreže,
s **asimetričnim (jednosmjernim) zaglađivanjem**:

```
H_i^(k+1) = max( H_i^(0) ,  mean( H_j^(k) : j ∈ susjedi(i) ) )
```

- Mreža se učitava iz `.2dm` datoteke (`ND` linije → koordinate čvorova,
  `E3T` linije → trokuti); susjedi čvora su svi čvorovi koji s njim dijele trokut.
- U svakoj iteraciji (tipično 10–30) čvor poprima prosjek susjeda, **ali nikad
  ispod svoje početne vrijednosti**.

Time se postiže:

- lokalni maksimumi ostaju očuvani (konzervativno za *Hmax*),
- nerealne "rupe" i točke se podižu,
- radi na proizvoljnoj nepravilnoj mreži, bez pretpostavki o rasporedu čvorova.

## Povijest verzija

| Verzija | Datoteka | Opis |
|---|---|---|
| **v1** (7/2025) | [smooth_wave_v1_gausian.py](smooth_wave_v1_gausian.py) | Gaussov filtar (`scipy.ndimage.gaussian_filter`) po 1D nizu čvorova. Jednostavno, ali ignorira topologiju mreže i **snižava maksimume**. |
| **v2** (7/2025) | [smooth_wave_v2_laplacian.py](smooth_wave_v2_laplacian.py) | Mesh-aware Laplacian: prosjek susjeda po `.2dm` mreži. Poštuje topologiju, ali još uvijek može sniziti vrhove. |
| **v2.1** (7/2025) | [smooth_wave_v2.1_laplacian.py](smooth_wave_v2.1_laplacian.py) | v2 + `max(original, smoothed)` pod — **konačna verzija algoritma**. Vrijednosti nikad ne padaju ispod originala. |
| **v3** (8/2025) | [smoothing_suite_gui.py](smoothing_suite_gui.py) + [bench_compare.py](bench_compare.py) + [make_report.py](make_report.py) | **Smoothing Suite** — ne mijenja algoritam, nego uspoređuje V1 vs V2 na istim podacima: benchmark s metrikama, grafovi i PDF izvještaj. |

### Napomena o obnovi v3 (7/2026)

Izvorni kod v3 bio je izgubljen — postojao je samo `smooth_wave_v3.exe`.
`smoothing_suite_gui.py` je **rekonstruiran dekompajliranjem exe-a** (PyInstaller,
Python 3.8 bytecode) i verificiran prema disassembly-ju. Radne skripte
`bench_compare.py` i `make_report.py` nisu bile ugrađene u exe pa su **napisane
ispočetka** prema ugovoru koji GUI očekuje; V2.0 implementacija u njima
verificirana je kao numerički identična v2.1 petlji (razlika ≤ 10⁻¹⁵), a kod je
prošao adversarial review (27 agenata, 15 popravaka) i regresijski paket od 16
testova.

> ⚠️ Zamrznuti `smooth_wave_v3.exe` ima ugrađeni bug: poziva `sys.executable`
> (tj. samog sebe) umjesto Pythona, pa benchmark iz exe-a nikad nije radio.
> Suite pokrećite iz izvornog koda.

---

## Instalacija

Python 3.8+ i paketi:

```
pip install numpy scipy h5py matplotlib
```

## Korištenje

### Smoothing Suite (v3) — preporučeno

```
python smoothing_suite_gui.py
```

1. odaberi `.2dm` mrežu,
2. odaberi ulaz: **CSV vrijednosti** ili **XMDF dataset** (datoteka + putanja
   dataseta, npr. `/Datasets/Steady State/Wave Height`),
3. odaberi izlazni folder i naslov izvještaja,
4. **1) Pokreni benchmark** → **2) Generiraj PDF**, ili sve odjednom.

Ili iz komandne linije:

```
python bench_compare.py --mesh mreza.2dm --values visine.csv --out rezultati
python bench_compare.py --mesh mreza.2dm --xmdf model.h5 --dataset "/Datasets/Steady State/Wave Height" --out rezultati
python make_report.py --in rezultati --title "Smoothing Benchmark — Luka X"
```

Opcije: `--sigma` (V1.0, default 2.0), `--iters` (V2.0, default 10).

**Izlazi u `--out` folderu:**

| Datoteka | Sadržaj |
|---|---|
| `metrics.csv` | metrike usporedbe (vidi dolje) |
| `results.csv` | po čvoru: original, V1.0, V2.0 |
| `fields.png`, `differences.png`, `histogram.png` | grafovi polja, razlika i histogram promjena |
| `smoothed_v1.h5`, `smoothed_v2.h5` | SMS-kompatibilni XMDF izlazi (samo u XMDF modu) |
| `report.pdf` | A4 izvještaj s tablicom metrika i grafovima (nakon make_report) |

**Metrike u `metrics.csv`:**

- `max_retention_pct` — koliko je % originalnog maksimuma zadržano (V2.0 uvijek 100 %)
- `nodes_below_original_pct` — % čvorova spuštenih ispod originala (V2.0 uvijek 0 %)
- `roughness_before/after/reduction_pct` — hrapavost = prosječna kvadratna razlika
  po bridu mreže; mjera uklonjenih oscilacija
- `mean_abs_change`, `rmse_vs_original`, `max_drop_below_original`, `runtime_s`

**CSV formati ulaza** (s headerom ili bez):

- jedan stupac vrijednosti — decimalna točka **ili zarez** (`0.86` / `0,86`),
- dva stupca `node_id` + vrijednost, razdvojena s `;`, tabom ili zarezom
  (ID-evi se mapiraju na ID-eve čvorova mreže i validiraju).

### Samostalni alat (v2.1)

```
python smooth_wave_v2.1_laplacian.py
```

GUI: `.2dm` mreža + ulazni `.h5` (dataset `/Datasets/Steady State/Wave Height`)
+ izlazni `.h5` + broj iteracija (preporuka 5–20). Izlaz je SMS-kompatibilan
XMDF s datasetom `Wave Height Smoothed`.

---

## Ograničenja i napomene

- Mreža: koriste se samo `E3T` trokuti (kao i u v2.1). Ostale kartice elemenata
  (`E4Q`, `E6T`…) se preskaču uz upozorenje — ti čvorovi se ne zaglađuju.
- Čvorovi bez susjeda zadržavaju originalnu vrijednost (uz upozorenje).
- Ulazi s `NaN/inf` vrijednostima se odbijaju s jasnom porukom.
- V1.0 (Gaussov filtar po nizu čvorova) namjerno je zadržan identičan originalnoj
  v1 skripti — on je *referenca za usporedbu*, ne preporučena metoda.

## Rezultat usporedbe (sintetički test, 500 čvorova)

| | V1.0 gaussian | V2.0 laplacian |
|---|---|---|
| Zadržan maksimum | 93 % | **100 %** |
| Čvorova ispod originala | 48 % | **0 %** |
| Smanjenje hrapavosti | −56 % | **−70 %** |

V2.0 uklanja više šuma, a pritom ne dira niti jedan sigurnosno relevantan vrh.
