from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
from typing import List
from pathlib import Path
from app.database.models.stock_item import StockItem

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class ReportService:
    @staticmethod
    def _register_fonts():
        try:
            # Common locations for DejaVuSans on Linux/Debian
            pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
            return True
        except Exception:
            # Fallback if fonts not found (local dev), but warn
            return False

    @staticmethod
    def generate_expiry_pdf(items: List[StockItem], filepath: Path) -> str:
        """
        Generates a PDF report for expired/expiring items using ReportLab.
        Returns the filename.
        """
        ReportService._register_fonts()
        font_regular = 'DejaVuSans'
        font_bold = 'DejaVuSans-Bold'
        
        doc = SimpleDocTemplate(str(filepath), pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Update styles to use Unicode font
        styles['Heading1'].fontName = font_bold
        styles['BodyText'].fontName = font_regular
        styles['Normal'].fontName = font_regular

        # Title
        title_style = styles['Heading1']
        title_style.alignment = 1 # Center
        elements.append(Paragraph(f"Raport Terminu Ważności - {datetime.now().strftime('%Y-%m-%d %H:%M')}", title_style))
        elements.append(Spacer(1, 20))

        # Legend
        legend_data = [
            ["Kolor", "Opis"],
            ["", "Przeterminowane (Po terminie)"],
            ["", "Kończy się ważność (Wymagane działanie w ciągu 24h)"]
        ]
        legend_table = Table(legend_data, colWidths=[50, 300])
        legend_style = TableStyle([
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), font_regular),
            # Red box for Expired
            ('BACKGROUND', (0, 1), (0, 1), colors.lightcoral),
            # Orange box for Expiring Soon
            ('BACKGROUND', (0, 2), (0, 2), colors.orange),
        ])
        legend_table.setStyle(legend_style)
        elements.append(legend_table)
        elements.append(Spacer(1, 20))
        
        # Table Data
        data = [["Asortyment", "Kod", "Data Ważności", "Dni", "Regał", "Poz"]]
        
        # Style logic
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTNAME', (0, 1), (-1, -1), font_regular),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ])

        now_date = datetime.now().date()
        
        for i, item in enumerate(items):
            # Ensure proper type for subtraction
            expiry = item.expiry_date
            if isinstance(expiry, datetime):
                expiry = expiry.date()
                
            days_left = (expiry - now_date).days
            row = [
                item.product.name[:30], # Truncate long names
                item.product.barcode,
                item.expiry_date.strftime('%Y-%m-%d'),
                str(days_left),
                item.rack.designation if item.rack else "Brak",
                f"{item.position_row}x{item.position_col}"
            ]
            data.append(row)
            
            # Conditional Formatting
            row_idx = i + 1
            if days_left < 0:
                # Red for expired
                table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.lightcoral)
            elif days_left <= 1: # 30 days specific warning
                # Orange for warning
                table_style.add('BACKGROUND', (0, row_idx), (-1, row_idx), colors.orange)

        if not items:
            elements.append(Paragraph("Brak asortymentu spełniającego kryteria raportu.", styles['BodyText']))
        else:
            t = Table(data)
            t.setStyle(table_style)
            elements.append(t)

        doc.build(elements)
        return filepath.name
