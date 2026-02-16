import requests
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

def download_and_save_image(url, folder, filename):
    os.makedirs(folder, exist_ok=True)

    response = requests.get(url)
    path = os.path.join(folder, filename)

    with open(path, "wb") as f:
        f.write(response.content)

    return path

def generate_pdf_report(folder, result, metadata):

    pdf_path = os.path.join(folder, "report.pdf")

    doc = SimpleDocTemplate(pdf_path)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("UrbanEye Encroachment Analysis Report", styles['Heading1']))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph(f"Encroachment Detected: {result['encroachment_percent']}%", styles['Normal']))
    elements.append(Paragraph(f"Risk Level: {result['risk_level']}", styles['Normal']))
    elements.append(Spacer(1, 0.5 * inch))

    elements.append(Paragraph("Before Image (t0)", styles['Heading2']))
    elements.append(Image(os.path.join(folder, "t0.png"), width=5*inch, height=3*inch))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("After Image (t1)", styles['Heading2']))
    elements.append(Image(os.path.join(folder, "t1.png"), width=5*inch, height=3*inch))
    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph("Detected Encroachment", styles['Heading2']))
    elements.append(Image(os.path.join(folder, "encroachment.png"), width=5*inch, height=3*inch))

    elements.append(Paragraph("Analysis Metadata", styles['Heading2']))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph(f"Before Period: {metadata['date1_start']} to {metadata['date1_end']}", styles['Normal']))
    elements.append(Paragraph(f"After Period: {metadata['date2_start']} to {metadata['date2_end']}", styles['Normal']))
    elements.append(Paragraph(f"Generated On: {metadata['generated_on']}", styles['Normal']))
    elements.append(Spacer(1, 0.5 * inch))

    elements.append(Paragraph("Methodology", styles['Heading2']))
    elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph(
        "Vegetation Loss Detection:",
        styles['Heading3']
    ))
    elements.append(Paragraph(
        "NDVI Change = NDVI(t1) - NDVI(t0)",
        styles['Normal']
    ))
    elements.append(Paragraph(
        "Vegetation Loss if NDVI Change < -0.2",
        styles['Normal']
    ))

    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph(
        "Built-up Detection:",
        styles['Heading3']
    ))
    elements.append(Paragraph(
        "NDBI Change = NDBI(t1) - NDBI(t0)",
        styles['Normal']
    ))
    elements.append(Paragraph(
        "Built-up Increase if NDBI Change > 0.2",
        styles['Normal']
    ))

    elements.append(Spacer(1, 0.3 * inch))

    elements.append(Paragraph(
        "Encroachment = Vegetation Loss AND Built-up Increase",
        styles['Normal']
    ))

    elements.append(Spacer(1, 0.4 * inch))
    elements.append(Paragraph("Encroachment Percentage Calculation", styles['Heading2']))
    elements.append(Paragraph(
        "Encroachment % = (Encroached Area / Total AOI Area) × 100",
        styles['Normal']
    ))

    doc.build(elements)

    return pdf_path
