
import h5py
import numpy as np
from tkinter import filedialog, messagebox
import tkinter as tk
import os
import uuid

def load_2dm(filepath):
    nodes = {}
    elements = []

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

    node_ids = sorted(nodes.keys())
    id_to_index = {nid: i for i, nid in enumerate(node_ids)}
    coords = np.array([nodes[nid] for nid in node_ids])
    triangles = np.array([[id_to_index[n] for n in tri] for tri in elements])
    return coords, triangles, node_ids, id_to_index

def build_neighbors(triangles, n_nodes):
    neighbors = [[] for _ in range(n_nodes)]
    for tri in triangles:
        for i in range(3):
            ni = tri[i]
            for j in range(3):
                nj = tri[j]
                if ni != nj and nj not in neighbors[ni]:
                    neighbors[ni].append(nj)
    return neighbors

def laplacian_smooth(data, neighbors, iterations):
    smoothed = data.copy()
    for _ in range(iterations):
        new_data = smoothed.copy()
        for i, nbrs in enumerate(neighbors):
            if nbrs:
                new_data[i] = np.mean([smoothed[j] for j in nbrs])
        smoothed = new_data
    return smoothed

def run_smoothing(mesh_file, h5_input_file, h5_output_file, iterations):
    coords, triangles, node_ids, id_to_index = load_2dm(mesh_file)
    n_nodes = coords.shape[0]

    with h5py.File(h5_input_file, "r") as f:
        dataset_path = "/Datasets/Steady State/Wave Height/Values"
        raw = f[dataset_path][:]
        if raw.shape[0] == 1:
            raw = raw[0]
        values = raw.astype("float32")

        try:
            obj_type = f["/Datasets/Steady State/Wave Height/PROPERTIES/Object Type"][()]
            if isinstance(obj_type, np.ndarray):
                obj_type = obj_type[0]
        except:
            obj_type = b"DataSet1D"

    neighbors = build_neighbors(triangles, n_nodes)
    smoothed = laplacian_smooth(values, neighbors, iterations)
    min_val, max_val = np.min(smoothed), np.max(smoothed)

    with h5py.File(h5_output_file, "w") as f_out:
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
        wavegrp.create_dataset("Values", data=smoothed.reshape(1, -1).astype("float32"))
        wavegrp.create_dataset("Mins", data=np.array([min_val], dtype="float32"))
        wavegrp.create_dataset("Maxs", data=np.array([max_val], dtype="float32"))

        prop = wavegrp.create_group("PROPERTIES")
        prop.attrs["Grouptype"] = np.array([b"PROPERTIES"], dtype="|S11")
        prop.create_dataset("Object Type", data=np.array([obj_type], dtype="|S14"))

    messagebox.showinfo("Success", f"Smoothed data saved to:\n{h5_output_file}")

# GUI code
def browse_file(entry, filetypes):
    file_path = filedialog.askopenfilename(filetypes=filetypes)
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)

def save_as(entry):
    file_path = filedialog.asksaveasfilename(defaultextension=".h5", filetypes=[("HDF5 files", "*.h5")])
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)

def start_gui():
    def run_gui_smooth():
        mesh_file = mesh_entry.get().strip()
        h5_input = h5_entry.get().strip()
        h5_output = out_entry.get().strip()
        try:
            iters = int(iter_entry.get())
            if iters < 1:
                raise ValueError
        except:
            messagebox.showerror("Error", "Smoothing iterations must be a positive integer.")
            return
        if not (mesh_file and h5_input and h5_output):
            messagebox.showerror("Error", "All file paths must be set.")
            return
        run_smoothing(mesh_file, h5_input, h5_output, iters)

    root = tk.Tk()
    root.title("Mesh-Aware Laplacian Smoother")
    root.geometry("600x320")

    tk.Label(root, text="Mesh File (.2dm):").pack()
    mesh_entry = tk.Entry(root, width=70)
    mesh_entry.pack()
    tk.Button(root, text="Browse", command=lambda: browse_file(mesh_entry, [("2DM files", "*.2dm")])).pack()

    tk.Label(root, text="Wave Height File (.h5):").pack()
    h5_entry = tk.Entry(root, width=70)
    h5_entry.pack()
    tk.Button(root, text="Browse", command=lambda: browse_file(h5_entry, [("HDF5 files", "*.h5")])).pack()

    tk.Label(root, text="Output File (.h5):").pack()
    out_entry = tk.Entry(root, width=70)
    out_entry.pack()
    tk.Button(root, text="Save As", command=lambda: save_as(out_entry)).pack()

    tk.Label(root, text="Smoothing Iterations (recommended: 5 to 20):").pack()
    iter_entry = tk.Entry(root)
    iter_entry.insert(0, "10")
    iter_entry.pack()

    tk.Button(root, text="Apply Smoothing", command=run_gui_smooth, height=2, width=30).pack(pady=10)

    root.mainloop()

if __name__ == "__main__":
    start_gui()
