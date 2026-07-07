# -*- coding: utf-8 -*-
# make_report.py — PDF izvjestaj iz izlaza bench_compare.py
# Rekonstruirano prema smoothing_suite_gui.py (smooth_wave_v3.exe): GUI poziva
#   python make_report.py --in DIR --title "Naslov"
# Cita metrics.csv i *.png iz DIR i sprema report.pdf u DIR.
import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

METRIC_LABELS = [
    ("runtime_s", "Vrijeme izvodenja [s]"),
    ("min", "Minimum"),
    ("max", "Maksimum"),
    ("mean", "Srednja vrijednost"),
    ("max_retention_pct", "Zadrzan maksimum [%]"),
    ("mean_abs_change", "Prosj. apsolutna promjena"),
    ("rmse_vs_original", "RMSE prema originalu"),
    ("max_drop_below_original", "Najveci pad ispod originala"),
    ("nodes_below_original_pct", "Cvorova ispod originala [%]"),
    ("roughness_after", "Hrapavost nakon"),
    ("roughness_reduction_pct", "Smanjenje hrapavosti [%]"),
]

PNG_TITLES = {
    "fields.png": "Polja valnih visina",
    "differences.png": "Razlike prema originalu",
    "histogram.png": "Histogram promjena",
}


def read_metrics(path):
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fmt(v):
    if v in ("", None):
        return "—"
    try:
        x = float(v)
    except ValueError:
        return str(v)
    if x == 0:
        return "0"
    if abs(x) >= 1000 or abs(x) < 0.001:
        return "%.3e" % x
    return "%.4g" % x


def title_page(pdf, title, indir, metrics):
    fig = plt.figure(figsize=(8.27, 11.69))  # A4
    fig.text(0.5, 0.86, title, ha="center", va="center", fontsize=20, weight="bold", wrap=True)
    fig.text(0.5, 0.80, "Usporedba metoda zagladivanja polja valnih visina",
             ha="center", fontsize=12)
    fig.text(0.5, 0.76, "Ulazni folder: %s" % os.path.abspath(indir),
             ha="center", fontsize=8, color="0.4")

    methods = [r for r in metrics if r.get("method") != "original"]
    col_labels = ["Metrika"] + [r["method"] for r in methods]
    cells = []
    for key, label in METRIC_LABELS:
        cells.append([label] + [fmt(r.get(key, "")) for r in methods])

    ax = fig.add_axes([0.08, 0.28, 0.84, 0.42])
    ax.axis("off")
    table = ax.table(cellText=cells, colLabels=col_labels, loc="center",
                     cellLoc="center", colLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.5)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#dbe5f1")

    fig.text(0.08, 0.20,
             "V1.0 — gaussian filter po nizu cvorova (scipy.ndimage.gaussian_filter).\n"
             "V2.0 — mesh-aware laplacian: iterativni prosjek susjeda po mrezi (.2dm)\n"
             "s ogranicenjem max(original, smoothed) — vrijednosti nikad ne padaju\n"
             "ispod originala (konzervativno za projektne valne visine).",
             fontsize=9, va="top", color="0.25")
    pdf.savefig(fig)
    plt.close(fig)


def image_page(pdf, png_path, title):
    img = plt.imread(png_path)
    fig = plt.figure(figsize=(11.69, 8.27))  # A4 lezece
    fig.suptitle(title, fontsize=14, weight="bold")
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.88])
    ax.imshow(img)
    ax.axis("off")
    pdf.savefig(fig)
    plt.close(fig)


def main(argv=None):
    # GUI cita stdout kroz pipe — bez ovoga bi se log pojavio tek na kraju
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    ap = argparse.ArgumentParser(description="PDF izvjestaj iz benchmark rezultata")
    ap.add_argument("--in", dest="indir", required=True, help="folder s rezultatima bench_compare.py")
    ap.add_argument("--title", default="Smoothing Benchmark — V1.0 vs V2.0", help="naslov izvjestaja")
    ap.add_argument("--out", help="putanja PDF-a (default: <in>/report.pdf)")
    args = ap.parse_args(argv)

    metrics_path = os.path.join(args.indir, "metrics.csv")
    metrics = []
    if os.path.isfile(metrics_path):
        print("[1/3] Citam metrics.csv")
        metrics = read_metrics(metrics_path)
    else:
        print("[1/3] Upozorenje: nema metrics.csv -- izvjestaj bez tablice metrika")

    pdf_path = args.out or os.path.join(args.indir, "report.pdf")
    pdf_tmp = pdf_path + ".tmp"
    print("[2/3] Generiram %s" % pdf_path)
    try:
        with PdfPages(pdf_tmp) as pdf:
            title_page(pdf, args.title, args.indir, metrics)
            for name in ("fields.png", "differences.png", "histogram.png"):
                p = os.path.join(args.indir, name)
                if os.path.isfile(p):
                    try:
                        image_page(pdf, p, PNG_TITLES.get(name, name))
                    except Exception as e:
                        print("[Upozorenje] Preskacem necitljiv PNG %s: %s" % (name, e))
            d = pdf.infodict()
            d["Title"] = args.title
            d["Subject"] = "Wave height smoothing benchmark"
        os.replace(pdf_tmp, pdf_path)
    except OSError as e:
        print("[Greska] Ne mogu pisati %s - zatvorite PDF preglednik ako je "
              "otvoren i pokusajte ponovno. (%s)" % (pdf_path, e))
        if os.path.isfile(pdf_tmp):
            try:
                os.remove(pdf_tmp)
            except OSError:
                pass
        return 1

    print("[3/3] Gotovo: %s" % os.path.abspath(pdf_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
