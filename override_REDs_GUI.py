#!/usr/bin/env python3

from __future__ import annotations

import csv
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:
    tk = None
    filedialog = None
    messagebox = None
    ttk = None
    TK_IMPORT_ERROR = exc
else:
    TK_IMPORT_ERROR = None

from override_REDs import StructureEntry, extract_structures, load_red_overrides


DEFAULT_OVERRIDES = Path(__file__).with_name("RED_overrides.csv")


class StructureRow:
    def __init__(
        self,
        parent: tk.Widget,
        entry: StructureEntry,
        csv_override: str | None,
        save_override_callback,
    ) -> None:
        self.entry = entry
        self.csv_override = csv_override
        self.save_override_callback = save_override_callback

        self.force_var = tk.BooleanVar(value=entry.is_forced_override)
        self.red_var = tk.StringVar(value=entry.values[2])
        self.csv_var = tk.StringVar(value=csv_override or "")

        self.name_label = ttk.Label(parent, text=entry.name, anchor="w")
        self.force_check = ttk.Checkbutton(parent, variable=self.force_var)
        self.red_entry = ttk.Entry(parent, textvariable=self.red_var, width=12)
        self.csv_label = ttk.Label(parent, textvariable=self.csv_var, width=12, anchor="center")
        self.force_button = ttk.Button(parent, text="Force", command=self.apply_csv_override)
        self.save_button = ttk.Button(parent, text="Add to overrides", command=self.save_override)

    def grid(self, row_index: int) -> None:
        self.name_label.grid(row=row_index, column=0, sticky="ew", padx=(0, 8), pady=2)
        self.force_check.grid(row=row_index, column=1, padx=4, pady=2)
        self.red_entry.grid(row=row_index, column=2, sticky="ew", padx=4, pady=2)
        self.csv_label.grid(row=row_index, column=3, sticky="ew", padx=4, pady=2)
        self.force_button.grid(row=row_index, column=4, padx=4, pady=2)
        self.save_button.grid(row=row_index, column=5, padx=(4, 0), pady=2)
        self.refresh_buttons()

    def refresh_buttons(self) -> None:
        if self.csv_override is None:
            self.force_button.state(["disabled"])
        else:
            self.force_button.state(["!disabled"])

    def apply_csv_override(self) -> None:
        if self.csv_override is None:
            return
        self.red_var.set(self.csv_override)
        self.force_var.set(True)

    def save_override(self) -> None:
        try:
            value = self.red_var.get().strip()
            self.validate_red(value)
            self.save_override_callback(self.entry.name, value)
            self.csv_override = value
            self.csv_var.set(value)
            self.save_button.configure(text="Update override")
            self.refresh_buttons()
        except Exception as exc:
            messagebox.showerror("Invalid RED value", str(exc))

    def validate_red(self, value: str) -> None:
        if not value:
            raise ValueError(f"RED value is required for {self.entry.name}")
        float(value)

    def apply_to_plan(self, lines: list[str]) -> None:
        value = self.red_var.get().strip()
        self.validate_red(value)
        self.entry.values[0] = "2" if self.force_var.get() else "1"
        self.entry.values[2] = value
        lines[self.entry.value_line] = ",".join(self.entry.values)


class OverrideRedsGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Override REDs")
        self.root.geometry("1050x700")

        self.plan_path: Path | None = None
        self.plan_lines: list[str] = []
        self.overrides_path = DEFAULT_OVERRIDES
        self.overrides: dict[str, str] = {}
        self.rows: list[StructureRow] = []

        self.plan_var = tk.StringVar()
        self.overrides_var = tk.StringVar(value=str(self.overrides_path))
        self.status_var = tk.StringVar(value="Select a plan file to begin.")

        self.build_ui()
        self.load_overrides_if_available()

    def build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        controls = ttk.Frame(self.root, padding=12)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Plan file").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.plan_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(controls, text="Browse...", command=self.pick_plan).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(controls, text="Load plan", command=self.load_plan).grid(row=0, column=3)

        ttk.Label(controls, text="Overrides CSV").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.overrides_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(controls, text="Browse...", command=self.pick_overrides).grid(row=1, column=2, padx=(0, 8), pady=(8, 0))
        ttk.Button(controls, text="Reload overrides", command=self.reload_overrides).grid(row=1, column=3, pady=(8, 0))

        actions = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        actions.grid(row=1, column=0, sticky="ew")
        ttk.Button(actions, text="Save modified plan...", command=self.save_plan).pack(side="left")
        ttk.Button(actions, text="Save overrides CSV", command=self.save_overrides_file).pack(side="left", padx=8)
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=12)

        table_host = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        table_host.grid(row=2, column=0, sticky="nsew")
        table_host.columnconfigure(0, weight=1)
        table_host.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(table_host, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(table_host, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = ttk.Frame(self.canvas)
        self.scroll_frame.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        self.scroll_frame.columnconfigure(0, weight=1)
        self.scroll_frame.columnconfigure(2, weight=1)

        headers = ["Structure", "Forced", "RED value", "CSV override", "", ""]
        for column, header in enumerate(headers):
            ttk.Label(self.scroll_frame, text=header).grid(row=0, column=column, sticky="w", padx=4, pady=(0, 6))

    def pick_plan(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select Monaco plan file",
            initialdir=str(Path.cwd()),
        )
        if selected:
            self.plan_var.set(selected)

    def pick_overrides(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select RED overrides CSV",
            initialdir=str(self.overrides_path.parent if self.overrides_path.parent.exists() else Path.cwd()),
            filetypes=[("Spreadsheet files", "*.csv *.tsv *.txt *.xlsx"), ("All files", "*.*")],
        )
        if selected:
            self.overrides_var.set(selected)

    def load_overrides_if_available(self) -> None:
        if self.overrides_path.exists():
            self.reload_overrides()
        else:
            self.status_var.set(f"Overrides file not found yet: {self.overrides_path}")

    def reload_overrides(self) -> None:
        try:
            self.overrides_path = Path(self.overrides_var.get()).expanduser()
            if self.overrides_path.exists():
                self.overrides = load_red_overrides(self.overrides_path, None)
                self.status_var.set(f"Loaded {len(self.overrides)} override entries.")
            else:
                self.overrides = {}
                self.status_var.set(f"Overrides file will be created at {self.overrides_path}")
            self.refresh_rows()
        except Exception as exc:
            messagebox.showerror("Failed to load overrides", str(exc))

    def load_plan(self) -> None:
        try:
            self.plan_path = Path(self.plan_var.get()).expanduser()
            self.plan_lines = self.plan_path.read_text(encoding="utf-8").splitlines()
            structures = extract_structures(self.plan_lines)
            if not structures:
                raise ValueError(f"No structure records found in plan file: {self.plan_path}")
            self.rebuild_rows(structures)
            self.status_var.set(f"Loaded {len(structures)} structures from {self.plan_path.name}")
        except Exception as exc:
            messagebox.showerror("Failed to load plan", str(exc))

    def rebuild_rows(self, structures: list[StructureEntry]) -> None:
        for widget in self.scroll_frame.grid_slaves():
            if int(widget.grid_info()["row"]) > 0:
                widget.destroy()

        self.rows = []
        for index, entry in enumerate(structures, start=1):
            row = StructureRow(
                self.scroll_frame,
                entry,
                self.overrides.get(entry.name),
                self.save_override_from_row,
            )
            row.grid(index)
            if row.csv_override is not None:
                row.save_button.configure(text="Update override")
            self.rows.append(row)

    def refresh_rows(self) -> None:
        for row in self.rows:
            new_override = self.overrides.get(row.entry.name)
            row.csv_override = new_override
            row.csv_var.set(new_override or "")
            row.refresh_buttons()
            if new_override is not None:
                row.save_button.configure(text="Update override")
            else:
                row.save_button.configure(text="Add to overrides")

    def save_override_from_row(self, structure_name: str, value: str) -> None:
        try:
            self.overrides[str(structure_name)] = value
            self.persist_overrides_file()
            self.status_var.set(f"Saved override for {structure_name}")
        except Exception as exc:
            messagebox.showerror("Failed to save override", str(exc))

    def save_overrides_file(self) -> None:
        try:
            self.persist_overrides_file()
            self.status_var.set(f"Wrote overrides to {self.overrides_path}")
        except Exception as exc:
            messagebox.showerror("Failed to save overrides", str(exc))

    def persist_overrides_file(self) -> None:
        self.overrides_path = Path(self.overrides_var.get()).expanduser()
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        with self.overrides_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["structure", "red"])
            for name in sorted(self.overrides, key=str.casefold):
                writer.writerow([name, self.overrides[name]])

    def save_plan(self) -> None:
        if self.plan_path is None or not self.plan_lines:
            messagebox.showerror("No plan loaded", "Load a plan file before saving.")
            return

        try:
            new_lines = list(self.plan_lines)
            for row in self.rows:
                row.apply_to_plan(new_lines)

            suggested_name = f"{self.plan_path.name} modified"
            destination = filedialog.asksaveasfilename(
                title="Save modified plan",
                initialdir=str(self.plan_path.parent),
                initialfile=suggested_name,
            )
            if not destination:
                return

            output_path = Path(destination)
            output_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            self.status_var.set(f"Saved modified plan to {output_path}")
        except Exception as exc:
            messagebox.showerror("Failed to save plan", str(exc))


def main() -> int:
    if TK_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Tk is not available in this Python environment. Install Python with Tk support "
            "and run this script again."
        ) from TK_IMPORT_ERROR
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    app = OverrideRedsGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
