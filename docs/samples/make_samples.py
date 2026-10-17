"""Generate synthetic Soil Health Card PDFs for testing the report reader (no real farmer data)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
CARDS = {
    "sample_soil_health_card_bathinda.pdf": ("Bathinda", "SHC/PB/BTI/2026/000123", [
        ("pH (1:2)", "8.9", "", "Alkaline"), ("EC (1:2)", "1.12", "dS/m", "Saline"), ("Organic Carbon (OC)", "0.31", "%", "Low"),
        ("Available Nitrogen (N)", "188", "kg/ha", "Low"), ("Available Phosphorus (P)", "14.2", "kg/ha", "Medium"),
        ("Available Potassium (K)", "310", "kg/ha", "High"), ("Available Sulphur (S)", "9.5", "ppm", "Low"),
        ("Zinc (Zn)", "0.48", "ppm", "Deficient"), ("Boron (B)", "0.52", "ppm", "Sufficient"),
        ("Iron (Fe)", "4.1", "ppm", "Sufficient"), ("Manganese (Mn)", "3.6", "ppm", "Sufficient"),
        ("Copper (Cu)", "0.36", "ppm", "Sufficient")]),
    "sample_soil_health_card_ludhiana.pdf": ("Ludhiana", "SHC/PB/LDH/2026/004567", [
        ("pH (1:2)", "7.8", "", "Normal"), ("EC (1:2)", "0.32", "dS/m", "Normal"), ("Organic Carbon (OC)", "0.52", "%", "Medium"),
        ("Available Nitrogen (N)", "290", "kg/ha", "Medium"), ("Available Phosphorus (P)", "24.0", "kg/ha", "High"),
        ("Available Potassium (K)", "180", "kg/ha", "Medium"), ("Available Sulphur (S)", "14", "ppm", "Medium"),
        ("Zinc (Zn)", "0.9", "ppm", "Sufficient"), ("Boron (B)", "0.7", "ppm", "Sufficient"),
        ("Iron (Fe)", "6.3", "ppm", "Sufficient"), ("Manganese (Mn)", "5.1", "ppm", "Sufficient"),
        ("Copper (Cu)", "0.6", "ppm", "Sufficient")]),
}


def make(name, district, number, rows):
    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(HERE / name), pagesize=A4, title="Soil Health Card (sample)")
    story = [Paragraph("Soil Health Card", ss["Title"]),
             Paragraph("SAMPLE — synthetic data for testing Apni Kheti. Not a real report.", ss["Italic"]),
             Spacer(1, 10),
             Paragraph(f"Card No: {number} &nbsp; | &nbsp; State: Punjab &nbsp; | &nbsp; District: {district}", ss["Normal"]),
             Paragraph("Sample collected: 12/09/2026 &nbsp; | &nbsp; Lab: District Soil Testing Laboratory", ss["Normal"]),
             Spacer(1, 12), Paragraph("Soil Test Results", ss["Heading2"])]
    data = [["Sr.", "Parameter", "Test Value", "Unit", "Rating"]] + [[str(i + 1), *r] for i, r in enumerate(rows)]
    tbl = Table(data, colWidths=[30, 190, 80, 60, 90])
    tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1EC")),
                             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    story += [tbl, Spacer(1, 12), Paragraph("Fertilizer recommendations: as per PAU Package of Practices.", ss["Normal"])]
    doc.build(story)


if __name__ == "__main__":
    for n, (d, num, rows) in CARDS.items():
        make(n, d, num, rows)
        print("wrote", n)
