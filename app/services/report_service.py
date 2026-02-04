from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
from typing import List
from pathlib import Path
import os
from app.database.models.stock_item import StockItem
from app.database.models.rack import Rack
from app.database.models.alert import Alert

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

class ReportService:
    @staticmethod
    def _register_fonts():
        # Common locations for DejaVuSans on Linux/Debian/Alpine
        possible_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/ttf/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/local/share/fonts/DejaVuSans.ttf"
            # Add more if needed
        ]
        
        font_path = None
        for p in possible_paths:
            if os.path.exists(p):
                font_path = p
                break
        
        if not font_path:
             print("Warning: DejaVuSans font not found. Using default default Helvetica which lacks utf-8.")
             return False

        try:
             # Register Regular
             pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
             
             # Try Bold (heuristics: same dir, -Bold suffix)
             base_dir = os.path.dirname(font_path)
             bold_path = os.path.join(base_dir, "DejaVuSans-Bold.ttf")
             
             if os.path.exists(bold_path):
                 pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_path))
             else:
                 # Fallback bold to regular to avoid crash/missing font error
                 pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_path))
                 
             return True
        except Exception as e:
            print(f"Error registering fonts: {e}")
            return False

    @staticmethod
    def generate_expiry_pdf(items: List[StockItem], filepath: Path) -> str:
        """
        Generates a PDF report for expired/expiring items using ReportLab.
        Returns the filename.
        """
        # Register fonts or fallback
        if ReportService._register_fonts():
            font_regular = 'DejaVuSans'
            font_bold = 'DejaVuSans-Bold'
        else:
            font_regular = 'Helvetica'
            font_bold = 'Helvetica-Bold'
        
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

    @staticmethod
    def generate_audit_pdf(racks: List[Rack], items: List[StockItem], alerts: List[Alert], filepath: Path) -> str:
        """
        Generates a comprehensive audit PDF report.
        Includes:
        1. Rack Analysis (Fill percentage)
        2. Product Audit (Inventory with receiver info)
        3. Alerts & Expiry (Unresolved alerts)
        """
        # Register fonts or fallback
        if ReportService._register_fonts():
            font_regular = 'DejaVuSans'
            font_bold = 'DejaVuSans-Bold'
        else:
            font_regular = 'Helvetica'
            font_bold = 'Helvetica-Bold'
        
        doc = SimpleDocTemplate(str(filepath), pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Update styles
        styles['Heading1'].fontName = font_bold
        styles['Heading2'].fontName = font_bold
        styles['BodyText'].fontName = font_regular
        styles['Normal'].fontName = font_regular

        # Title
        title_style = styles['Heading1']
        title_style.alignment = 1 # Center
        elements.append(Paragraph(f"Raport Audytowy - {datetime.now().strftime('%Y-%m-%d %H:%M')}", title_style))
        elements.append(Spacer(1, 20))

        # --- SECTION 1: RACK ANALYSIS ---
        elements.append(Paragraph("1. Analiza Regałów (Zapełnienie)", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        rack_data = [["Regał", "Pojemność", "Zajęte", "Zapełnienie %", "Status"]]
        
        rack_table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTNAME', (0, 1), (-1, -1), font_regular),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ])

        for rack in racks:
            capacity = rack.rows_m * rack.cols_n
            used = len(rack.items) if rack.items else 0
            fill_img = used / capacity * 100 if capacity > 0 else 0
            
            status = "Wolny"
            if fill_img > 90:
                status = "Krytyczny"
            elif fill_img > 75:
                status = "Wysoki"
            
            row = [
                rack.designation,
                str(capacity),
                str(used),
                f"{fill_img:.1f}%",
                status
            ]
            rack_data.append(row)
            
            # Simple color coding for high usage
            idx = len(rack_data) - 1
            if fill_img > 90:
                rack_table_style.add('BACKGROUND', (0, idx), (-1, idx), colors.lightcoral)
            elif fill_img > 75:
                rack_table_style.add('BACKGROUND', (0, idx), (-1, idx), colors.lightyellow)

        t_racks = Table(rack_data, colWidths=[100, 80, 80, 100, 100])
        t_racks.setStyle(rack_table_style)
        elements.append(t_racks)
        elements.append(Spacer(1, 20))

        # --- SECTION 2: PRODUCT AUDIT ---
        elements.append(Paragraph("2. Inwentaryzacja Produktów", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        # Columns: Product, Rack/Pos, Entry Date, Received By
        item_data = [["Produkt", "Poz", "Data Przyjęcia", "Przyjął"]]
        
        item_table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.navy),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTNAME', (0, 1), (-1, -1), font_regular),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 8), # Smaller font for list
        ])

        for item in items:
            received_by = "System"
            if item.receiver:
                received_by = f"{item.receiver.email}"
            
            pos = f"{item.rack.designation if item.rack else '-'} [{item.position_row},{item.position_col}]"
            
            row = [
                item.product.name[:25],
                pos,
                item.entry_date.strftime('%Y-%m-%d %H:%M'),
                received_by
            ]
            item_data.append(row)

        if len(items) > 0:
            t_items = Table(item_data, colWidths=[150, 120, 120, 150])
            t_items.setStyle(item_table_style)
            elements.append(t_items)
        else:
            elements.append(Paragraph("Brak produktów w magazynie.", styles['BodyText']))
            
        elements.append(Spacer(1, 20))

        # --- SECTION 3: ALERTS & EXPIRY ---
        elements.append(Paragraph("3. Aktywne Alerty i Problemy", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        alert_data = [["Data", "Typ", "Wiadomość", "Dotyczy"]]
        
        alert_table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkred),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTNAME', (0, 1), (-1, -1), font_regular),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
             ('FONTSIZE', (0, 0), (-1, -1), 9),
        ])

        if alerts:
            for alert in alerts:
                target = "-"
                if alert.rack:
                    target = f"Regał {alert.rack.designation}"
                elif alert.product:
                    target = f"Prod {alert.product.name[:15]}"
                
                row = [
                    alert.created_at.strftime('%Y-%m-%d'),
                    alert.alert_type.value,
                    alert.message[:40],
                    target
                ]
                alert_data.append(row)
            
            t_alerts = Table(alert_data, colWidths=[80, 80, 250, 130])
            t_alerts.setStyle(alert_table_style)
            elements.append(t_alerts)
        else:
             elements.append(Paragraph("Brak aktywnych alertów.", styles['BodyText']))

        doc.build(elements)
        return filepath.name
    @staticmethod
    def generate_temp_pdf(alerts: List[Alert], filepath: Path) -> str:
        """
        Generates a temperature report showing exceeded ranges.
        """
        # Register fonts or fallback
        if ReportService._register_fonts():
            font_regular = 'DejaVuSans'
            font_bold = 'DejaVuSans-Bold'
        else:
            font_regular = 'Helvetica'
            font_bold = 'Helvetica-Bold'
        
        doc = SimpleDocTemplate(str(filepath), pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Update styles
        styles['Heading1'].fontName = font_bold
        styles['BodyText'].fontName = font_regular
        styles['Normal'].fontName = font_regular

        # Title
        title_style = styles['Heading1']
        title_style.alignment = 1 # Center
        elements.append(Paragraph(f"Raport Temperatury - {datetime.now().strftime('%Y-%m-%d %H:%M')}", title_style))
        elements.append(Spacer(1, 20))
        
        elements.append(Paragraph("Wykaz przekroczonych temperatur:", styles['Heading2']))
        elements.append(Spacer(1, 10))
        
        # Table Header
        data = [["Data", "Godzina", "Regał / Asortyment", "Komunikat"]]
        
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), font_bold),
            ('FONTNAME', (0, 1), (-1, -1), font_regular),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ])

        if not alerts:
             elements.append(Paragraph("Brak zarejestrowanych przekroczeń temperatur.", styles['BodyText']))
        else:
            for alert in alerts:
                target = "Nieznany"
                if alert.rack:
                    target = f"Regał {alert.rack.designation}"
                elif alert.product:
                    target = f"Produkt {alert.product.name} ({alert.product.barcode})"
                
                row = [
                    alert.created_at.strftime('%Y-%m-%d'),
                    alert.created_at.strftime('%H:%M:%S'),
                    target,
                    alert.message
                ]
                data.append(row)
            
            t = Table(data, colWidths=[80, 80, 200, 200])
            t.setStyle(table_style)
            elements.append(t)

        doc.build(elements)
        return filepath.name
