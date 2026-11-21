"""Generate small, synthetic PDFs for testing the bidder document workflow."""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


OUTPUT_DIR = Path(__file__).resolve().parent
WATERMARK = "SYNTHETIC TEST SAMPLE - NOT A GOVERNMENT CERTIFICATE"

SAMPLES = {
    "valid_gst_certificate.pdf": [
        ("Document", "GST Registration Certificate"),
        ("Legal name", "TechCorp India Pvt Ltd"),
        ("GSTIN", "27ABCDE1234F1Z5"),
        ("PAN", "ABCDE1234F"),
        ("Registration status", "ACTIVE"),
        ("Effective from", "2025-04-01"),
        ("Valid through", "2027-03-31"),
        ("Registered address", "14 Sample Industrial Estate, Mumbai, Maharashtra"),
    ],
    "valid_pan_certificate.pdf": [
        ("Document", "Permanent Account Number Record"),
        ("Entity name", "TechCorp India Pvt Ltd"),
        ("PAN", "ABCDE1234F"),
        ("Issue date", "2020-06-15"),
    ],
    "valid_udyam_certificate.pdf": [
        ("Document", "Udyam Registration Certificate"),
        ("Enterprise name", "TechCorp India Pvt Ltd"),
        ("Udyam number", "UDYAM-MH-00-1234567"),
        ("Registration status", "ACTIVE"),
        ("Registration date", "2021-02-10"),
    ],
    "mismatched_gst_certificate.pdf": [
        ("Document", "GST Registration Certificate"),
        ("Legal name", "TechCorp India Pvt Ltd"),
        ("GSTIN", "29PQRSX5678K1Z3"),
        ("PAN", "PQRSX5678K"),
        ("Registration status", "ACTIVE"),
        ("Valid through", "2027-03-31"),
        ("Registered address", "22 Fictional Test Park, Bengaluru, Karnataka"),
    ],
}


def write_sample(filename: str, rows: list[tuple[str, str]]) -> None:
    path = OUTPUT_DIR / filename
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    page_width, page_height = A4
    pdf.setTitle(filename.replace("_", " ").removesuffix(".pdf"))
    pdf.setAuthor("BharatSetu Test Data Generator")

    pdf.setFillColorRGB(0.08, 0.18, 0.35)
    pdf.rect(0, page_height - 34 * mm, page_width, 34 * mm, fill=1, stroke=0)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(20 * mm, page_height - 17 * mm, "BharatSetu Synthetic Test Document")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(20 * mm, page_height - 25 * mm, WATERMARK)

    y = page_height - 51 * mm
    for label, value in rows:
        pdf.setFillColorRGB(0.35, 0.40, 0.48)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(22 * mm, y, label.upper())
        pdf.setFillColorRGB(0.10, 0.14, 0.20)
        pdf.setFont("Helvetica", 12)
        pdf.drawString(22 * mm, y - 7 * mm, value)
        y -= 20 * mm

    pdf.setStrokeColorRGB(0.82, 0.85, 0.89)
    pdf.line(20 * mm, 24 * mm, page_width - 20 * mm, 24 * mm)
    pdf.setFillColorRGB(0.40, 0.43, 0.49)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(20 * mm, 18 * mm, "Fictional values for software testing only. Not valid for procurement or tax use.")
    pdf.save()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, rows in SAMPLES.items():
        write_sample(filename, rows)
        print(f"Generated {OUTPUT_DIR / filename}")


if __name__ == "__main__":
    main()
