# -*- coding: utf-8 -*-
# bench_compare.py — usporedba V1.0 (gaussian) vs V2.0 (mesh-aware laplacian s max-floorom)
# Rekonstruirano prema smoothing_suite_gui.py (smooth_wave_v3.exe): GUI poziva
#   python bench_compare.py --mesh M.2dm --out DIR (--values V.csv | --xmdf F.h5 --dataset PATH)
# Izlazi u --out folder: metrics.csv, results.csv, *.png grafovi,
# a u XMDF modu i smoothed_v1.h5 / smoothed_v2.h5 (SMS-kompatibilni).
#
# Napomena o stdout-u: GUI cita stdout kroz pipe (cp1250) — svi printovi su
# namjerno bez dijakritika i linijski bufferirani.
import argparse
import os
import sys
import time
import uuid

import numpy as np
# import na razini modula da se vrijeme importa ne mjeri kao vrijeme algoritma
import scipy.sparse as sp
from scipy.ndimage import gaussian_filter

# ----------------------------------------------------------------------------
# Ucitavanje podataka
# ----------------------------------------------------------------------------

# ostale 2dm kartice elemenata (preskacu se, kao i u smooth_wave_v2.1_laplacian.py)
OTHER_ELEMENT_CARDS = ("E2L", "E3L", "E4Q", "E5Q", "E6T", "E8Q", "E9Q")


def load_2dm(filepath):
    """Kao u smooth_wave_v2.1_laplacian.py (samo E3T trokuti), uz brojanje
    preskocenih kartica elemenata drugih tipova."""
    nodes = {}
    elements = []
    skipped = 0
    with open(filepath, "r") as f:
        for line in f:
            if line.startswith("ND"):
                parts = line.split()
                node_id = int(parts[1])
                x, y = float(parts[2]), float(parts[3])
                nodes[node_id] = (x, y)
            elif line.startswith("E3T"):
                parts = line.split()
                n1, n2, n3 = int(parts[2]), int(parts[3]), int(parts[4])
                elements.append((n1, n2, n3))
            elif line.startswith(OTHER_ELEMENT_CARDS):
                skipped += 1
    node_ids = sorted(nodes.keys())
    id_to_index = {nid: i for i, nid in enumerate(node_ids)}
    coords = np.array([nodes[nid] for nid in node_ids])
    triangles = np.array([[id_to_index[n] for n in tri] for tri in elements])
    return coords, triangles, node_ids, id_to_index, skipped


def _is_num(s):
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False


def load_values_csv(filepath, n_nodes, node_ids=None, id_to_index=None):
    """CSV s vrijednostima po cvoru.

    Podrzani formati (uz opcionalni header):
      - jedan stupac vrijednosti, decimalna tocka ili zarez ("0.86" ili "0,86")
      - dva stupca (node_id, vrijednost) razdvojena s ';', tabom ili ','
    Napomena: dvoclani redovi poput "5,25" (zarez i kao delimiter i kao
    decimalni znak) tumace se kao JEDNA vrijednost s decimalnim zarezom;
    za parove (id, vrijednost) koristite ';' ili tab.
    """
    with open(filepath, "r", newline="") as f:
        raw_lines = [ln.strip() for ln in f if ln.strip()]
    if not raw_lines:
        raise ValueError("CSV je prazan.")

    # 1) jednostupcani slucaj — svaka linija je jedan broj
    #    (pokriva i decimalni zarez: "0,859606")
    data_lines = raw_lines[1:] if not _is_num(raw_lines[0]) else raw_lines
    if data_lines and all(_is_num(ln) for ln in data_lines):
        values = np.array([float(ln.replace(",", ".")) for ln in data_lines])
    else:
        # 2) vise stupaca — deterministicki delimiter (bez pogadanja Sniffera)
        sample = "\n".join(raw_lines[:50])
        if ";" in sample:
            delim = ";"
        elif "\t" in sample:
            delim = "\t"
        else:
            delim = ","
        rows = [[c.strip() for c in ln.split(delim) if c.strip() != ""] for ln in raw_lines]
        rows = [r for r in rows if r]
        if rows and not all(_is_num(c) for c in rows[0]):
            rows = rows[1:]  # header
        if not rows or not all(all(_is_num(c) for c in r) for r in rows):
            raise ValueError("CSV nije moguce protumaciti kao numericke podatke.")
        ncol = len(rows[0])
        if any(len(r) != ncol for r in rows):
            raise ValueError("CSV ima nejednak broj stupaca po recima.")
        if ncol != 2:
            raise ValueError(
                "CSV ima %d stupaca; podrzano: 1 (vrijednosti) ili 2 (node_id, vrijednost)." % ncol)

        data = np.array([[float(c.replace(",", ".")) for c in r] for r in rows])
        ids_f = data[:, 0]
        if not np.all(ids_f == np.round(ids_f)):
            # prvi stupac nije ID — uzmi zadnji stupac kao vrijednosti redom
            values = data[:, -1]
        else:
            ids = ids_f.astype(np.int64)
            if len(np.unique(ids)) != len(ids):
                raise ValueError("CSV sadrzi duplicirane node ID-eve.")
            if id_to_index is not None and node_ids is not None and set(ids.tolist()) == set(node_ids):
                # ID-evi odgovaraju mrezi -> eksplicitno mapiranje po ID-u
                out = np.empty(len(ids), dtype="float64")
                out[[id_to_index[i] for i in ids.tolist()]] = data[:, 1]
                values = out
            elif np.array_equal(np.sort(ids), np.arange(1, len(ids) + 1)):
                # ID-evi su 1..N ali mreza ima druge ID-eve -> po redoslijedu, uz upozorenje
                order = np.argsort(ids, kind="stable")
                values = data[order, 1]
                if node_ids is not None and set(ids.tolist()) != set(node_ids):
                    print("[Upozorenje] ID-evi u CSV-u (1..%d) ne odgovaraju ID-evima mreze "
                          "- vrijednosti su dodijeljene po redoslijedu cvorova." % len(ids))
            else:
                raise ValueError("ID-evi u CSV-u ne odgovaraju ID-evima cvorova mreze.")

    if len(values) != n_nodes:
        raise ValueError(
            "Broj vrijednosti u CSV-u (%d) ne odgovara broju cvorova mreze (%d)."
            % (len(values), n_nodes))
    return values.astype("float32")


def load_values_xmdf(filepath, dataset):
    """XMDF/HDF5: dataset je grupa (npr. /Datasets/Steady State/Wave Height)
    ili direktno .../Values."""
    import h5py
    with h5py.File(filepath, "r") as f:
        path = dataset.rstrip("/")
        if path not in f:
            raise KeyError("Dataset '%s' ne postoji u %s" % (path, filepath))
        if isinstance(f[path], h5py.Group):
            if (path + "/Values") not in f:
                raise KeyError("Grupa '%s' nema poddataset 'Values'" % path)
            path = path + "/Values"
        raw = f[path][:]
        if raw.ndim == 2 and 1 in raw.shape:
            raw = raw.ravel()
        elif raw.ndim != 1:
            raise ValueError("Nepodrzan oblik dataseta: %s" % (raw.shape,))
        obj_type = b"DataSet1D"
        prop = dataset.rstrip("/").rsplit("/Values", 1)[0] + "/PROPERTIES/Object Type"
        if prop in f:
            ot = f[prop][()]
            if isinstance(ot, np.ndarray):
                ot = ot[0]
            if isinstance(ot, bytes):
                obj_type = ot
    return raw.astype("float32"), obj_type


# ----------------------------------------------------------------------------
# Algoritmi
# ----------------------------------------------------------------------------

def smooth_v1_gaussian(values, sigma):
    """V1.0: scipy gaussian_filter po 1D nizu vrijednosti (redoslijed cvorova),
    identicno smooth_wave_v1_gausian.py."""
    return gaussian_filter(values, sigma=sigma)


def build_edges(triangles):
    """Jedinstveni bridovi mreze (par indeksa cvorova)."""
    e = np.vstack([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
    e = np.sort(e, axis=1)
    return np.unique(e, axis=0)


def smooth_v2_laplacian(values, edges, n_nodes, iterations):
    """V2.0/2.1: iterativni laplacian (prosjek susjeda, Jacobi) s podom
    max(original, smoothed) — vektorizirano. Matematicki identicno petlji iz
    smooth_wave_v2.1_laplacian.py za cvorove koji imaju susjede; cvorovi bez
    susjeda ovdje zadrzavaju svoju vrijednost (originalna v2.1 petlja na tom
    mjestu ima stale-variable bug i moze dici NameError)."""
    i, j = edges[:, 0], edges[:, 1]
    data = np.ones(2 * len(edges))
    adj = sp.coo_matrix((data, (np.r_[i, j], np.r_[j, i])),
                        shape=(n_nodes, n_nodes)).tocsr()
    deg = np.asarray(adj.sum(axis=1)).ravel()
    has_nbr = deg > 0

    original = values.astype("float64")
    smoothed = original.copy()
    for _ in range(iterations):
        mean_nbr = np.zeros_like(smoothed)
        mean_nbr[has_nbr] = (adj @ smoothed)[has_nbr] / deg[has_nbr]
        new = smoothed.copy()
        new[has_nbr] = np.maximum(original[has_nbr], mean_nbr[has_nbr])
        smoothed = new
    return smoothed


# ----------------------------------------------------------------------------
# Metrike
# ----------------------------------------------------------------------------

def roughness(values, edges):
    """Prosjecna kvadratna razlika po bridu — mjera 'nazubljenosti' polja."""
    d = values[edges[:, 0]] - values[edges[:, 1]]
    return float(np.mean(d * d))


def compute_metrics(name, orig, smoothed, edges, runtime_s):
    delta = smoothed - orig
    r0 = roughness(orig, edges)
    r1 = roughness(smoothed, edges)
    if r0 > 0 and np.isfinite(r0) and np.isfinite(r1):
        rough_red = float(100.0 * (1.0 - r1 / r0))
    else:
        rough_red = float("nan")
    return {
        "method": name,
        "runtime_s": round(runtime_s, 4),
        "min": float(np.min(smoothed)),
        "max": float(np.max(smoothed)),
        "mean": float(np.mean(smoothed)),
        "max_retention_pct": float(100.0 * np.max(smoothed) / np.max(orig)) if np.max(orig) != 0 else float("nan"),
        "mean_abs_change": float(np.mean(np.abs(delta))),
        "rmse_vs_original": float(np.sqrt(np.mean(delta * delta))),
        "max_drop_below_original": float(max(0.0, -np.min(delta))),
        "nodes_below_original_pct": float(100.0 * np.mean(delta < -1e-9)),
        "roughness_before": r0,
        "roughness_after": r1,
        "roughness_reduction_pct": rough_red,
    }


# ----------------------------------------------------------------------------
# Izlazi
# ----------------------------------------------------------------------------

# artefakti koje ova skripta proizvodi (report.pdf ostavljamo — njega
# make_report.py svakako prepisuje)
ARTIFACTS = ("metrics.csv", "metrics.csv.tmp", "results.csv", "fields.png",
             "differences.png", "histogram.png", "smoothed_v1.h5", "smoothed_v2.h5")


def clean_outdir(outdir):
    for name in ARTIFACTS:
        p = os.path.join(outdir, name)
        if os.path.isfile(p):
            os.remove(p)


def write_metrics_csv(path, orig, edges, rows):
    import csv
    fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        base = {k: "" for k in fields}
        base.update(method="original", runtime_s="",
                    min=float(np.min(orig)), max=float(np.max(orig)),
                    mean=float(np.mean(orig)),
                    roughness_before=roughness(orig, edges),
                    roughness_after=roughness(orig, edges))
        w.writerow(base)
        for r in rows:
            w.writerow(r)


def write_results_csv(path, node_ids, orig, v1, v2):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["node_id", "original", "v1_gaussian", "v2_laplacian"])
        for nid, o, a, b in zip(node_ids, orig, v1, v2):
            w.writerow([nid, "%.6g" % o, "%.6g" % a, "%.6g" % b])


def write_xmdf(path, values, obj_type):
    """SMS-kompatibilan XMDF izlaz, identicna struktura kao u v1/v2.1."""
    import h5py
    values = np.asarray(values, dtype="float32")
    with h5py.File(path, "w") as f_out:
        f_out.create_dataset("File Type", data=np.array([b"Xmdf"], dtype="|S5"))
        f_out.create_dataset("File Version", data=np.array([99.99], dtype="float32"))
        datasets = f_out.create_group("Datasets")
        datasets.attrs["Grouptype"] = np.array([b"MULTI DATASETS"], dtype="|S15")
        datasets.create_dataset("Guid", data=np.array([str(uuid.uuid4()).encode()], dtype="|S37"))
        grp = datasets.create_group("Steady State")
        wavegrp = grp.create_group("Wave Height Smoothed")
        wavegrp.attrs["Grouptype"] = np.array([b"DATASET SCALAR"], dtype="|S15")
        wavegrp.attrs["Data Type"] = np.array([0], dtype="int32")
        wavegrp.attrs["DatasetCompression"] = np.array([-1], dtype="int32")
        wavegrp.attrs["DatasetUnits"] = np.array([b"None"], dtype="|S5")
        wavegrp.attrs["TimeUnits"] = np.array([b"Seconds"], dtype="|S8")
        wavegrp.create_dataset("Times", data=np.array([0.0]))
        wavegrp.create_dataset("Values", data=values.reshape(1, -1))
        wavegrp.create_dataset("Mins", data=np.array([np.min(values)], dtype="float32"))
        wavegrp.create_dataset("Maxs", data=np.array([np.max(values)], dtype="float32"))
        prop = wavegrp.create_group("PROPERTIES")
        prop.attrs["Grouptype"] = np.array([b"PROPERTIES"], dtype="|S11")
        prop.create_dataset("Object Type", data=np.array([obj_type], dtype="|S14"))


def make_plots(outdir, coords, triangles, orig, v1, v2):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    tri = mtri.Triangulation(coords[:, 0], coords[:, 1], triangles)
    vmin = float(min(orig.min(), v1.min(), v2.min()))
    vmax = float(max(orig.max(), v1.max(), v2.max()))

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharex=True, sharey=True)
    for ax, (title, vals) in zip(axes, [("Original", orig),
                                        ("V1.0 gaussian", v1),
                                        ("V2.0 laplacian", v2)]):
        tc = ax.tricontourf(tri, vals, levels=24, cmap="viridis", vmin=vmin, vmax=vmax)
        ax.triplot(tri, color="k", lw=0.1, alpha=0.3)
        ax.set_title(title)
        ax.set_aspect("equal")
    fig.colorbar(tc, ax=axes, shrink=0.85, label="Wave height")
    fig.suptitle("Polje valnih visina — usporedba metoda")
    fig.savefig(os.path.join(outdir, "fields.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharex=True, sharey=True)
    dmax = float(max(np.abs(v1 - orig).max(), np.abs(v2 - orig).max())) or 1.0
    for ax, (title, vals) in zip(axes, [("V1.0 − original", v1 - orig),
                                        ("V2.0 − original", v2 - orig)]):
        tc = ax.tricontourf(tri, vals, levels=24, cmap="RdBu_r", vmin=-dmax, vmax=dmax)
        ax.set_title(title)
        ax.set_aspect("equal")
    fig.colorbar(tc, ax=axes, shrink=0.85, label="Razlika")
    fig.suptitle("Promjena u odnosu na original")
    fig.savefig(os.path.join(outdir, "differences.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    # zajednicki rubovi binova da histogrami budu izravno usporedivi
    deltas = np.concatenate([v1 - orig, v2 - orig])
    bins = np.histogram_bin_edges(deltas, bins=40)
    ax.hist(v1 - orig, bins=bins, alpha=0.6, label="V1.0 gaussian")
    ax.hist(v2 - orig, bins=bins, alpha=0.6, label="V2.0 laplacian")
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlabel("Promjena vrijednosti po cvoru")
    ax.set_ylabel("Broj cvorova")
    ax.set_title("Histogram promjena")
    ax.legend()
    fig.savefig(os.path.join(outdir, "histogram.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------

def main(argv=None):
    # GUI cita stdout kroz pipe — bez ovoga bi se log pojavio tek na kraju
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    ap = argparse.ArgumentParser(description="Benchmark: V1.0 gaussian vs V2.0 mesh-aware laplacian")
    ap.add_argument("--mesh", required=True, help=".2dm mreza")
    ap.add_argument("--out", required=True, help="izlazni folder")
    ap.add_argument("--values", help="CSV s vrijednostima po cvoru")
    ap.add_argument("--xmdf", help="XMDF/HDF5 datoteka")
    ap.add_argument("--dataset", help="putanja dataseta u XMDF-u")
    ap.add_argument("--sigma", type=float, default=2.0, help="sigma za V1.0 (default 2.0)")
    ap.add_argument("--iters", type=int, default=10, help="iteracije za V2.0 (default 10)")
    args = ap.parse_args(argv)

    if not args.values and not (args.xmdf and args.dataset):
        ap.error("potreban je --values CSV ili --xmdf + --dataset")

    os.makedirs(args.out, exist_ok=True)
    # ukloni artefakte proslih pokretanja da neuspjeh ne ostavi stare rezultate
    # koje bi GUI/make_report protumacio kao svjeze
    clean_outdir(args.out)

    try:
        print("[1/6] Ucitavam mrezu: %s" % args.mesh)
        coords, triangles, node_ids, id_to_index, skipped = load_2dm(args.mesh)
        n = coords.shape[0]
        print("      %d cvorova, %d E3T elemenata" % (n, len(triangles)))
        if skipped:
            print("[Upozorenje] %d elemenata preskoceno (nisu E3T trokuti) - ti elementi "
                  "ne ulaze u V2.0 izgladivanje, metrike hrapavosti ni grafove." % skipped)
        if n == 0:
            print("[Greska] Mreza nema cvorova.")
            return 1
        if len(triangles) == 0:
            print("[Greska] Mreza nema E3T trokutastih elemenata.")
            return 1

        print("[2/6] Ucitavam vrijednosti...")
        obj_type = b"DataSet1D"
        if args.values:
            orig = load_values_csv(args.values, n, node_ids, id_to_index)
        else:
            orig, obj_type = load_values_xmdf(args.xmdf, args.dataset)
            if len(orig) != n:
                print("[Greska] Broj vrijednosti (%d) != broj cvorova (%d)." % (len(orig), n))
                return 1
    except (ValueError, KeyError, IndexError, OSError) as e:
        print("[Greska] %s" % (e.args[0] if e.args else e))
        return 1

    orig = orig.astype("float64")
    bad = np.flatnonzero(~np.isfinite(orig))
    if bad.size:
        print("[Greska] Ulazni podaci sadrze %d NaN/inf vrijednosti (indeksi cvorova: %s%s). "
              "Ocistite podatke pa pokusajte ponovno."
              % (bad.size, ", ".join(map(str, bad[:10].tolist())),
                 "..." if bad.size > 10 else ""))
        return 1

    edges = build_edges(triangles)
    n_iso = n - len(np.unique(edges))
    if n_iso:
        print("[Upozorenje] %d cvorova bez susjeda u E3T elementima - V2.0 ih "
              "ostavlja na originalnoj vrijednosti." % n_iso)

    print("[3/6] V1.0 gaussian (sigma=%.2f)..." % args.sigma)
    t0 = time.perf_counter()
    v1 = np.asarray(smooth_v1_gaussian(orig, args.sigma), dtype="float64")
    t1 = time.perf_counter() - t0
    print("      gotovo u %.3f s" % t1)

    print("[4/6] V2.0 laplacian (iteracije=%d)..." % args.iters)
    t0 = time.perf_counter()
    v2 = smooth_v2_laplacian(orig, edges, n, args.iters)
    t2 = time.perf_counter() - t0
    print("      gotovo u %.3f s" % t2)

    print("[5/6] Metrike i izlazne datoteke...")
    rows = [compute_metrics("v1_gaussian", orig, v1, edges, t1),
            compute_metrics("v2_laplacian", orig, v2, edges, t2)]
    # metrics.csv je GUI-jev dokaz uspjeha — pisi u .tmp, preimenuj tek na kraju
    metrics_tmp = os.path.join(args.out, "metrics.csv.tmp")
    write_metrics_csv(metrics_tmp, orig, edges, rows)
    write_results_csv(os.path.join(args.out, "results.csv"), node_ids, orig, v1, v2)
    if args.xmdf:
        write_xmdf(os.path.join(args.out, "smoothed_v1.h5"), v1, obj_type)
        write_xmdf(os.path.join(args.out, "smoothed_v2.h5"), v2, obj_type)

    print("[6/6] Grafovi...")
    make_plots(args.out, coords, triangles, orig, v1, v2)
    os.replace(metrics_tmp, os.path.join(args.out, "metrics.csv"))

    for r in rows:
        print("  %-13s max=%.4f (%.1f%% originala)  hrapavost -%.1f%%  ispod originala: %.1f%% cvorova"
              % (r["method"], r["max"], r["max_retention_pct"],
                 r["roughness_reduction_pct"], r["nodes_below_original_pct"]))
    print("Rezultati u: %s" % os.path.abspath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
