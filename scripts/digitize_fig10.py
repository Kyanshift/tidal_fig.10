"""Read-only PDF rendering/digitization, using bundled document Python.

Scientific simulations use .venv. This auxiliary PDF-only script needs
pdfplumber/Pillow in a separate PDF-processing environment.
Calibration is for the published Figure 10, not the arXiv version.
"""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / "references/papers/brahm2018/published.pdf"
    output = ROOT / "data/processed/fig10"
    output.mkdir(parents=True, exist_ok=True)
    with pdfplumber.open(source) as pdf:
        im = pdf.pages[7].crop((54.198, 352.557, 278.632, 624.837)).to_image(resolution=300).original
    im.save(output / "published_crop.png")
    rgb = np.asarray(im.convert("RGB"), dtype=float)
    r, g, b = rgb.transpose(2, 0, 1)
    yellow = (r > 65) & (g > 65) & (abs(r-g) < 35) & (b < .55*np.minimum(r,g))
    green = (g > 60) & (g > 1.3*r) & (g > 1.3*b)
    red = (r > 150) & (g < 100) & (b < 100)
    # Pixel axis centres verified against rendered tick positions. Linear axes.
    x0, x1 = 87.5, 925.5
    e_top, e_bottom = 8., 510.
    a_top, a_bottom = 566., 1068.
    points = []
    def ys(mask, x, ylo, yhi, window=4):
        xx = int(round(x))
        sub = mask[int(ylo):int(yhi), max(0,xx-window):xx+window+1]
        return np.where(sub)[0] + int(ylo)
    for age in np.arange(.2, 9.601, .2):
        x = x0 + (age-.1)/9.9*(x1-x0)
        ey = ys(yellow, x, e_top+3, e_bottom-3)
        ay = ys(yellow, x, a_top+3, 960)
        qy = ys(yellow, x, 960, 1010, window=8)
        # At late times periapsis rises beyond y=960; partition by the
        # very clear empty band between a and q, independently of simulation.
        by = ys(yellow, x, a_top+3, a_bottom-3, window=8)
        if len(by):
            unique = np.unique(by)
            jumps = np.where(np.diff(unique) > 15)[0]
            if len(jumps):
                split = jumps[np.argmax(np.diff(unique)[jumps])]
                ay, qy = unique[:split+1], unique[split+1:]
        ry = ys(red, x, 1010, 1050)
        sy = ys(green, x, a_top+3, a_bottom-2)
        for field, values, bottom, scale in [
            ("e", ey, e_bottom, 1/(e_bottom-e_top)),
            ("a_au", ay, a_bottom, .25/(a_bottom-a_top)),
            ("pericentre_au", qy, a_bottom, .25/(a_bottom-a_top)),
            ("roche_limit_au", ry, a_bottom, .25/(a_bottom-a_top)),
            ("stellar_radius_au", sy, a_bottom, .25/(a_bottom-a_top))]:
            if len(values):
                points.append(dict(age_Gyr=round(float(age), 5), observable=field,
                                   value=(bottom-float(np.median(values)))*scale,
                                   pixel_y=float(np.median(values)),
                                   pixel_half_width=8 if field in {"a_au","pericentre_au"} else 4))
    with (output / "central_curves.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(points[0]))
        w.writeheader()
        w.writerows(points)
    metadata = dict(source=str(source.relative_to(ROOT)), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    page_one_based=8, dpi=300, crop_points=[54.198,352.557,278.632,624.837],
                    x_axis_pixels=[x0,x1], age_axis_Gyr=[.1,10.],
                    e_axis_pixels=[e_top,e_bottom], a_axis_pixels=[a_top,a_bottom],
                    method="colour_mask_median_published_raster_central_lines",
                    uncertainty="approximate_pixels_not_original_numerical_data; x-window broadens steep endpoint",
                    comparison_domain="0.2_to_9.6_Gyr; quantitative_acceptance_to_9.2_Gyr; endpoint_visual_only",
                    missing_points="colour_occlusion_or_dashed_gap_omitted_not_interpolated")
    (output / "digitization.json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(output=str(output), points=len(points))))


if __name__ == "__main__":
    main()
