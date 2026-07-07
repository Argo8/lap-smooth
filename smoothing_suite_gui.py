# Rekonstruirano iz smooth_wave_v3.exe (PyInstaller, Python 3.8) — 7.7.2026.
# Izvorni naziv datoteke: smoothing_suite_gui.py (buildano 11.8.2025.)
# Napomena: GUI poziva bench_compare.py i make_report.py koje ocekuje pokraj
# ove skripte — te dvije skripte nisu bile ugradene u exe i nisu pronadene.
import os, sys, subprocess, threading, queue, tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Smoothing Suite — V1.0 vs V2.0"
DEFAULT_TITLE = "Smoothing Benchmark — V1.0 vs V2.0"


def which_python():
    return sys.executable


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("820x520")
        self.minsize(820, 520)
        self.var_mesh = tk.StringVar()
        self.var_values = tk.StringVar()
        self.var_xmdf = tk.StringVar()
        self.var_dataset = tk.StringVar()
        self.var_outdir = tk.StringVar()
        self.var_report_title = tk.StringVar(value=DEFAULT_TITLE)
        self.var_mode = tk.StringVar(value="csv")
        self.log_q = queue.Queue()
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        pad = {'padx': 8, 'pady': 6}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)

        r0 = ttk.Frame(frm)
        r0.pack(fill="x", **pad)
        ttk.Label(r0, text="Mesh (.2dm):").pack(side="left")
        ttk.Entry(r0, textvariable=self.var_mesh).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r0, text="Odaberi…", command=self.pick_mesh).pack(side="left")

        rmode = ttk.Frame(frm)
        rmode.pack(fill="x", **pad)
        ttk.Label(rmode, text="Ulazni podaci:").pack(side="left")
        ttk.Radiobutton(rmode, text="CSV vrijednosti", value="csv", variable=self.var_mode, command=self._toggle_mode).pack(side="left", padx=6)
        ttk.Radiobutton(rmode, text="XMDF dataset", value="xmdf", variable=self.var_mode, command=self._toggle_mode).pack(side="left")

        r1 = ttk.Frame(frm)
        r1.pack(fill="x", **pad)
        self.row_csv = r1
        ttk.Label(r1, text="Values (.csv):").pack(side="left")
        ttk.Entry(r1, textvariable=self.var_values).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r1, text="Odaberi…", command=self.pick_values).pack(side="left")

        r2 = ttk.Frame(frm)
        r2.pack(fill="x", **pad)
        self.row_xmdf = r2
        ttk.Label(r2, text="XMDF (.xmdf):").pack(side="left")
        ttk.Entry(r2, textvariable=self.var_xmdf).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r2, text="Odaberi…", command=self.pick_xmdf).pack(side="left")

        r2b = ttk.Frame(frm)
        r2b.pack(fill="x", **pad)
        self.row_dataset = r2b
        ttk.Label(r2b, text="XMDF dataset path:").pack(side="left")
        ttk.Entry(r2b, textvariable=self.var_dataset).pack(side="left", fill="x", expand=True, padx=6)

        r3 = ttk.Frame(frm)
        r3.pack(fill="x", **pad)
        ttk.Label(r3, text="Output folder:").pack(side="left")
        ttk.Entry(r3, textvariable=self.var_outdir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(r3, text="Odaberi…", command=self.pick_outdir).pack(side="left")

        r4 = ttk.Frame(frm)
        r4.pack(fill="x", **pad)
        ttk.Label(r4, text="Naslov izvještaja:").pack(side="left")
        ttk.Entry(r4, textvariable=self.var_report_title).pack(side="left", fill="x", expand=True, padx=6)

        rb = ttk.Frame(frm)
        rb.pack(fill="x", **pad)
        ttk.Button(rb, text="1) Pokreni benchmark", command=self.run_benchmark).pack(side="left")
        ttk.Button(rb, text="2) Generiraj PDF", command=self.run_report).pack(side="left", padx=6)
        ttk.Button(rb, text="Sve — Benchmark + PDF", command=self.run_all).pack(side="left", padx=6)
        ttk.Button(rb, text="Otvori output", command=self.open_outdir).pack(side="right")

        rprog = ttk.Frame(frm)
        rprog.pack(fill="x", **pad)
        ttk.Label(rprog, text="Status:").pack(side="left")
        self.pb = ttk.Progressbar(rprog, mode="indeterminate")
        self.pb.pack(side="left", fill="x", expand=True, padx=6)

        rlog = ttk.Frame(frm)
        rlog.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(rlog, height=14)
        self.txt.pack(fill="both", expand=True)

        self._toggle_mode()
        self.after(100, self._drain_log)

    def pick_mesh(self):
        f = filedialog.askopenfilename(title="Odaberi .2dm", filetypes=[('2DM mesh', '*.2dm'), ('Svi', '*.*')])
        if f:
            self.var_mesh.set(f)

    def pick_values(self):
        f = filedialog.askopenfilename(title="Odaberi .csv", filetypes=[('CSV', '*.csv'), ('Svi', '*.*')])
        if f:
            self.var_values.set(f)

    def pick_xmdf(self):
        f = filedialog.askopenfilename(title="Odaberi .xmdf", filetypes=[('XMDF', '*.xmdf'), ('Svi', '*.*')])
        if f:
            self.var_xmdf.set(f)

    def pick_outdir(self):
        d = filedialog.askdirectory(title="Odaberi izlazni folder")
        if d:
            self.var_outdir.set(d)

    def _toggle_mode(self):
        m = self.var_mode.get()
        if m == "csv":
            self.row_csv.pack_configure(fill="x")
            self.row_xmdf.pack_forget()
            self.row_dataset.pack_forget()
        else:
            self.row_csv.pack_forget()
            self.row_xmdf.pack_configure(fill="x")
            self.row_dataset.pack_configure(fill="x")

    def log(self, s):
        self.log_q.put(s)

    def _drain_log(self):
        try:
            while True:
                s = self.log_q.get_nowait()
                self.txt.insert("end", s + "\n")
                self.txt.see("end")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _validate_common(self):
        if not os.path.isfile(self.var_mesh.get()):
            messagebox.showerror("Greška", "Nedostaje .2dm mesh.")
            return False
        if not os.path.isdir(self.var_outdir.get()):
            messagebox.showerror("Greška", "Nedostaje output folder.")
            return False
        return True

    def _build_bench_cmd(self):
        py = which_python()
        bench = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_compare.py")
        if not os.path.isfile(bench):
            messagebox.showerror("Greška", "bench_compare.py nije pronađen pokraj GUI skripte.")
            return
        cmd = [py, bench, "--mesh", self.var_mesh.get(), "--out", self.var_outdir.get()]
        if self.var_mode.get() == "csv":
            if not os.path.isfile(self.var_values.get()):
                messagebox.showerror("Greška", "Odaberi CSV s vrijednostima.")
                return
            cmd += ["--values", self.var_values.get()]
        else:
            if not os.path.isfile(self.var_xmdf.get()):
                messagebox.showerror("Greška", "Odaberi XMDF datoteku.")
                return
            if not self.var_dataset.get().strip():
                messagebox.showerror("Greška", "Upiši XMDF dataset path.")
                return
            cmd += ["--xmdf", self.var_xmdf.get(), "--dataset", self.var_dataset.get()]
        return cmd

    def _build_report_cmd(self):
        py = which_python()
        rep = os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_report.py")
        if not os.path.isfile(rep):
            messagebox.showerror("Greška", "make_report.py nije pronađen pokraj GUI skripte.")
            return
        cmd = [py, rep, "--in", self.var_outdir.get(), "--title", self.var_report_title.get()]
        return cmd

    def _run_cmd_async(self, cmd, done_cb=None):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("U tijeku", "Druga radnja još traje.")
            return
        self.pb.start(12)
        self.log("> " + " ".join(cmd))

        def _work():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:
                    self.log(line.rstrip("\n"))
                ret = proc.wait()
                if ret != 0:
                    self.log(f"[Greška] Proces završio s kodom {ret}")
                    messagebox.showerror("Greška", f"Proces završio s kodom {ret}.\nProvjeri log.")
                else:
                    self.log("[OK] Gotovo.")
                    if done_cb:
                        self.after(0, done_cb)
            except Exception as e:
                self.log(f"[Izuzetak] {e}")
                messagebox.showerror("Greška", str(e))
            finally:
                self.after(0, self.pb.stop)

        self.worker = threading.Thread(target=_work, daemon=True)
        self.worker.start()

    def run_benchmark(self):
        if not self._validate_common():
            return
        cmd = self._build_bench_cmd()
        if cmd:
            self._run_cmd_async(cmd)

    def run_report(self):
        if not self._validate_common():
            return
        metrics = os.path.join(self.var_outdir.get(), "metrics.csv")
        if not os.path.isfile(metrics):
            if not messagebox.askyesno("Upozorenje", "Nema metrics.csv u outputu. Svejedno generirati PDF?"):
                return
        cmd = self._build_report_cmd()
        if cmd:
            self._run_cmd_async(cmd, done_cb=lambda: messagebox.showinfo("PDF", "PDF je generiran."))

    def run_all(self):
        if not self._validate_common():
            return
        bench_cmd = self._build_bench_cmd()
        if not bench_cmd:
            return

        def after_bench():
            rep_cmd = self._build_report_cmd()
            if rep_cmd:
                self._run_cmd_async(rep_cmd, done_cb=lambda: messagebox.showinfo("Gotovo", "Benchmark + PDF završeni."))

        self._run_cmd_async(bench_cmd, done_cb=after_bench)

    def open_outdir(self):
        d = self.var_outdir.get().strip()
        if not (d and os.path.isdir(d)):
            messagebox.showerror("Greška", "Output folder ne postoji.")
            return
        if sys.platform.startswith("win"):
            os.startfile(d)
        elif sys.platform == "darwin":
            subprocess.call(["open", d])
        else:
            subprocess.call(["xdg-open", d])


if __name__ == "__main__":
    App().mainloop()
