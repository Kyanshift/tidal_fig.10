"""Validate packaged scientific inputs and YAML references."""
import hashlib
import json
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
def check():
    documents = list((ROOT / "configs").rglob("*.yaml"))
    for path in documents:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError(f"Invalid YAML: {path}")
        for item in doc.get("inputs", []):
            if not (ROOT / item).is_file():
                raise ValueError(f"Missing input: {item}")
    truth = yaml.safe_load((ROOT / "configs/parameters/paper_truth.yaml").read_text(encoding="utf-8"))
    for source in truth["sources"].values():
        if not (ROOT / source["path"]).is_file():
            raise ValueError(f"Missing source: {source['path']}")
    catalog = yaml.safe_load((ROOT / "data/raw/stellar_tracks/catalog.yaml").read_text(encoding="utf-8"))
    for key in ["source_path", "path"]:
        if hashlib.sha256((ROOT / catalog[key]).read_bytes()).hexdigest() != catalog["sha256"]:
            raise ValueError("Stellar track hash mismatch")
    return {"config_yaml_documents": len(documents), "paper_source_paths_verified": len(truth["sources"]), "stellar_track_copy_verified": True}
if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
