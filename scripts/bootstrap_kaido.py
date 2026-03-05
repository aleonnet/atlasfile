from __future__ import annotations

from pathlib import Path

from bootstrap_project import bootstrap_project, slugify

KAIDO_ROOT = Path("/Users/alessandro/Library/CloudStorage/OneDrive-Personal/Documentos/Projects/Kaidô")


def main() -> None:
    root = bootstrap_project(
        projects_root=KAIDO_ROOT.parent,
        project_dir_name=KAIDO_ROOT.name,
        project_id=slugify("kaido_upi_tahto"),
        project_label="Kaidô - Implantação UPI Tahto",
    )
    print(f"OK: projeto Kaidô inicializado em {root}")


if __name__ == "__main__":
    main()
