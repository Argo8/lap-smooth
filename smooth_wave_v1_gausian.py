
import h5py
import numpy as np
from scipy.ndimage import gaussian_filter
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import uuid

def process_file(input_file_path, output_file_path, sigma_value=2):
    in_group = "/Datasets/Steady State/Wave Height"
    out_group = "/Datasets/Steady State/Wave Height Smoothed"

    try:
        with h5py.File(input_file_path, "r") as f:
            raw = f[in_group + "/Values"][:]
            if raw.ndim == 2 and raw.shape[0] == 1:
                H = raw[0]
            elif raw.ndim == 1:
                H = raw
            else:
                messagebox.showerror("Error", "Unsupported dataset shape")
                return

            try:
                obj_type = f[in_group + "/PROPERTIES/Object Type"][()]
                if isinstance(obj_type, bytes):
                    obj_type = obj_type
                elif isinstance(obj_type, np.ndarray):
                    obj_type = obj_type[0]
            except:
                obj_type = b"DataSet1D"

        # Apply smoothing
        H_smooth = gaussian_filter(H, sigma=sigma_value)

        # Compute min/max
        min_val = np.min(H_smooth).astype("float32")
        max_val = np.max(H_smooth).astype("float32")

        with h5py.File(output_file_path, "w") as f_out:
            # File-level metadata (as in original)
            f_out.create_dataset("File Type", data=np.array([b"Xmdf"], dtype="|S5"))  # lowercase
            f_out.create_dataset("File Version", data=np.array([99.99], dtype="float32"))  # match original

            # /Datasets group
            datasets = f_out.create_group("Datasets")
            datasets.attrs["Grouptype"] = np.array([b"MULTI DATASETS"], dtype="|S15")
            datasets.create_dataset("Guid", data=np.array([str(uuid.uuid4()).encode()], dtype="|S37"))

            # Create target group
            steady = datasets.create_group("Steady State")
            target = steady.create_group("Wave Height Smoothed")
            target.attrs["Grouptype"] = np.array([b"DATASET SCALAR"], dtype="|S15")
            target.attrs["Data Type"] = np.array([0], dtype="int32")
            target.attrs["DatasetCompression"] = np.array([-1], dtype="int32")
            target.attrs["DatasetUnits"] = np.array([b"None"], dtype="|S5")
            target.attrs["TimeUnits"] = np.array([b"Seconds"], dtype="|S8")

            target.create_dataset("Times", data=np.array([0.0], dtype="float64"))
            target.create_dataset("Values", data=H_smooth.reshape(1, -1).astype("float32"))
            target.create_dataset("Mins", data=np.array([min_val], dtype="float32"))
            target.create_dataset("Maxs", data=np.array([max_val], dtype="float32"))

            prop = target.create_group("PROPERTIES")
            prop.attrs["Grouptype"] = np.array([b"PROPERTIES"], dtype="|S11")
            prop.create_dataset("Object Type", data=np.array([obj_type], dtype="|S14"))

        messagebox.showinfo("Success", f"Fixed-format SMS-compatible file saved as:\n{output_file_path}")

    except Exception as e:
        messagebox.showerror("Error", f"An error occurred:\n{str(e)}")

def choose_input_file():
    file_path = filedialog.askopenfilename(filetypes=[("HDF5 files", "*.h5")])
    if file_path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, file_path)

def choose_output_file():
    file_path = filedialog.asksaveasfilename(defaultextension=".h5",
                                              filetypes=[("HDF5 files", "*.h5")])
    if file_path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, file_path)

def run_smoothing():
    input_path = input_entry.get().strip()
    output_path = output_entry.get().strip()
    sigma_text = sigma_entry.get().strip()

    if not input_path or not output_path:
        messagebox.showerror("Error", "Please select both input and output file paths.")
        return

    try:
        sigma = float(sigma_text)
        if not (0.1 <= sigma <= 10):
            raise ValueError
    except ValueError:
        messagebox.showerror("Error", "Smoothing strength (sigma) must be a number between 0.1 and 10.")
        return

    process_file(input_path, output_path, sigma)

# GUI
root = tk.Tk()
root.title("Wave Height Smoother (SMS Final Fix)")
root.geometry("550x300")

tk.Label(root, text="Input HDF5 File:").pack(pady=(10, 0))
input_entry = tk.Entry(root, width=60)
input_entry.pack()
tk.Button(root, text="Browse", command=choose_input_file).pack(pady=(0, 10))

tk.Label(root, text="Output HDF5 File:").pack()
output_entry = tk.Entry(root, width=60)
output_entry.pack()
tk.Button(root, text="Save As", command=choose_output_file).pack(pady=(0, 10))

tk.Label(root, text="Smoothing Strength (σ):  (recommended: 1.0 to 3.0)").pack()
sigma_entry = tk.Entry(root, width=10)
sigma_entry.insert(0, "2.0")
sigma_entry.pack(pady=(0, 10))

tk.Button(root, text="Apply Smoothing", command=run_smoothing, height=2, width=25).pack(pady=10)

root.mainloop()
