"""Render an invoice to a PDF byte string using reportlab.

reportlab over weasyprint: pure Python, no GTK/Cairo/Pango runtime deps,
identical output across Windows / macOS / Linux / slim Docker images.
Trade-off: programmatic layout (no HTML/CSS), which is fine for a
single-page tabular invoice. Swapping in weasyprint later is a one-file
change.

Visual style: bold violet brand band on top, generous whitespace,
right-aligned totals with a heavy grand-total line, small-caps section
labels. Tune `BRAND_*` constants below to match a different palette
without touching layout code.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.orders.models import Invoice, Order

# ---------------------------------------------------------------------------
# Brand tokens. One place to retheme.
# ---------------------------------------------------------------------------
BRAND_PRIMARY = HexColor("#5B2A86")  # deep violet
BRAND_PRIMARY_DARK = HexColor("#3F1C5F")  # band shadow / hover
BRAND_ACCENT = HexColor("#7C4DBA")  # secondary violet for badges
BRAND_INK = HexColor("#1A1530")  # near-black with violet tint
BRAND_MUTED = HexColor("#6B6680")  # secondary text
BRAND_RULE = HexColor("#E5E1F0")  # hairline dividers
BRAND_SURFACE = HexColor("#F7F4FC")  # alternating row / table header
BRAND_SUCCESS = HexColor("#0EA371")  # B2B badge etc.

PAGE_W, PAGE_H = A4
MARGIN_X = 16 * mm
BAND_HEIGHT = 28 * mm

# ---------------------------------------------------------------------------
# Paragraph styles.
# ---------------------------------------------------------------------------
_styles = getSampleStyleSheet()
_BASE = _styles["Normal"]

_BRAND_TITLE = ParagraphStyle(
    "BrandTitle",
    parent=_BASE,
    fontName="Helvetica-Bold",
    fontSize=22,
    leading=26,
    textColor=colors.white,
)
_BRAND_SUB = ParagraphStyle(
    "BrandSub",
    parent=_BASE,
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=HexColor("#E9DCFB"),
)
_META_LABEL = ParagraphStyle(
    "MetaLabel",
    parent=_BASE,
    fontName="Helvetica-Bold",
    fontSize=7,
    leading=10,
    spaceAfter=2,
    textColor=BRAND_MUTED,
    # ReportLab doesn't have letter-spacing — fake "small caps" with case.
)
_META_VALUE = ParagraphStyle(
    "MetaValue",
    parent=_BASE,
    fontName="Helvetica-Bold",
    fontSize=11,
    leading=14,
    textColor=BRAND_INK,
)
_SECTION_LABEL = ParagraphStyle(
    "SectionLabel",
    parent=_BASE,
    fontName="Helvetica-Bold",
    fontSize=8,
    leading=12,
    spaceAfter=4,
    textColor=BRAND_PRIMARY,
)
_BODY = ParagraphStyle(
    "Body",
    parent=_BASE,
    fontName="Helvetica",
    fontSize=10,
    leading=13,
    textColor=BRAND_INK,
)
_BODY_STRONG = ParagraphStyle(
    "BodyStrong",
    parent=_BODY,
    fontName="Helvetica-Bold",
)
_MUTED = ParagraphStyle(
    "Muted",
    parent=_BODY,
    fontSize=9,
    textColor=BRAND_MUTED,
)
_FOOTER = ParagraphStyle(
    "Footer",
    parent=_BASE,
    fontName="Helvetica",
    fontSize=8,
    leading=11,
    textColor=BRAND_MUTED,
    alignment=1,  # center
)


def render_invoice_pdf(*, invoice: Invoice, order: Order) -> bytes:
    """Produce a single-page invoice PDF for `order` + `invoice`.

    Reads only what's passed in -- no further DB queries, so the caller
    is responsible for prefetching items.product and customer.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=BAND_HEIGHT + 10 * mm,  # leave room under the brand band
        bottomMargin=20 * mm,
        title=f"Invoice #{invoice.invoice_number}",
        author="Acme Cart",
    )

    story: list = []
    story.append(_meta_strip(invoice, order))
    story.append(Spacer(1, 8 * mm))

    story.extend(_party_columns(order))
    if order.is_b2b:
        story.append(Spacer(1, 4 * mm))
        story.append(_b2b_badge(order))

    story.append(Spacer(1, 8 * mm))
    story.append(_line_items_table(order))
    story.append(Spacer(1, 4 * mm))
    story.append(_totals_table(order))
    story.append(Spacer(1, 10 * mm))
    if order.payment_terms and order.payment_due_date:
        terms_label = order.payment_terms.replace("_", "-").upper()
        due = order.payment_due_date.strftime("%d %b %Y")
        footer_text = (
            f"Payment terms: {terms_label}. Amount due on or before {due}. "
            "Remittance reference: order #"
            f"{order.order_number}."
        )
    else:
        footer_text = (
            "Thank you for your purchase. This invoice was generated automatically "
            "at the time of capture; the order record is the system of record."
        )
    story.append(Paragraph(footer_text, _FOOTER))

    doc.build(story, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Page chrome: top brand band + footer rule. Drawn on every page.
# ---------------------------------------------------------------------------
def _draw_chrome(canvas, doc):
    canvas.saveState()

    # Top band.
    canvas.setFillColor(BRAND_PRIMARY)
    canvas.rect(0, PAGE_H - BAND_HEIGHT, PAGE_W, BAND_HEIGHT, fill=1, stroke=0)

    # Thin darker shadow at the band's lower edge for depth.
    canvas.setFillColor(BRAND_PRIMARY_DARK)
    canvas.rect(0, PAGE_H - BAND_HEIGHT, PAGE_W, 1.2, fill=1, stroke=0)

    # Brand title left.
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(MARGIN_X, PAGE_H - BAND_HEIGHT + 12 * mm, "Acme Cart")

    canvas.setFillColor(HexColor("#E9DCFB"))
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(
        MARGIN_X,
        PAGE_H - BAND_HEIGHT + 7 * mm,
        "Multi-tenant commerce platform",
    )

    # "INVOICE" stamp on the right of the band.
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    label = "INVOICE"
    text_w = canvas.stringWidth(label, "Helvetica-Bold", 11)
    canvas.drawString(
        PAGE_W - MARGIN_X - text_w,
        PAGE_H - BAND_HEIGHT + 12 * mm,
        label,
    )

    # Footer rule + page #.
    canvas.setStrokeColor(BRAND_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN_X, 14 * mm, PAGE_W - MARGIN_X, 14 * mm)

    canvas.setFillColor(BRAND_MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawRightString(
        PAGE_W - MARGIN_X,
        9 * mm,
        f"Page {doc.page}",
    )

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Meta strip: invoice number, issued date, order number.
# Three label/value pairs in a single row, separated by hairlines.
# ---------------------------------------------------------------------------
def _meta_strip(invoice: Invoice, order: Order) -> Table:
    issued = invoice.issued_at.strftime("%d %b %Y") if invoice.issued_at else "—"
    cells = [
        [
            Paragraph("INVOICE NUMBER", _META_LABEL),
            Paragraph("ISSUED", _META_LABEL),
            Paragraph("ORDER", _META_LABEL),
            Paragraph("CURRENCY", _META_LABEL),
        ],
        [
            Paragraph(f"#{invoice.invoice_number}", _META_VALUE),
            Paragraph(issued, _META_VALUE),
            Paragraph(f"#{order.order_number}", _META_VALUE),
            Paragraph(order.currency, _META_VALUE),
        ],
    ]
    col_w = (PAGE_W - 2 * MARGIN_X) / 4
    t = Table(cells, colWidths=[col_w] * 4)
    t.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                # Vertical hairlines between columns
                ("LINEBEFORE", (1, 0), (-1, -1), 0.4, BRAND_RULE),
            ]
        )
    )
    return t


# ---------------------------------------------------------------------------
# Party blocks: Billed to / Ship to as two columns.
# ---------------------------------------------------------------------------
def _party_columns(order: Order) -> list:
    bill = _party_cell("Billed to", order.billing_address, customer=order.customer)

    has_ship = order.shipping_address and _addresses_differ(
        order.billing_address, order.shipping_address
    )
    ship = _party_cell("Ship to", order.shipping_address) if has_ship else [Spacer(1, 1)]

    col_w = (PAGE_W - 2 * MARGIN_X) / 2
    t = Table([[bill, ship]], colWidths=[col_w, col_w])
    t.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return [t]


def _party_cell(label: str, address: dict | None, *, customer=None) -> list:
    parts: list = [Paragraph(label.upper(), _SECTION_LABEL)]
    if customer is not None:
        name = (customer.name or customer.email or "").strip()
        if name:
            parts.append(Paragraph(name, _BODY_STRONG))
        if customer.company_name:
            parts.append(Paragraph(customer.company_name, _BODY))
        if customer.email:
            parts.append(Paragraph(customer.email, _MUTED))
    if address:
        street = address.get("street") or ""
        city = address.get("city") or ""
        country = address.get("country") or ""
        postal = address.get("postal_code") or address.get("postalCode") or ""
        if street:
            parts.append(Paragraph(street, _BODY))
        loc = ", ".join(p for p in (city, postal, country) if p)
        if loc:
            parts.append(Paragraph(loc, _BODY))
    return parts


def _addresses_differ(a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    keys = ("street", "city", "country", "postal_code", "postalCode")
    return any(a.get(k) != b.get(k) for k in keys)


# ---------------------------------------------------------------------------
# B2B badge: small rounded pill with the tax id.
# ---------------------------------------------------------------------------
def _b2b_badge(order: Order) -> Table:
    label = f"  B2B  •  Tax ID  {order.tax_id}  " if order.tax_id else "  B2B  "
    t = Table(
        [
            [
                Paragraph(
                    f'<font color="white"><b>{label}</b></font>',
                    _BODY,
                )
            ]
        ]
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_SUCCESS),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("ROUNDEDCORNERS", [4, 4, 4, 4]),
            ]
        )
    )
    t.hAlign = "LEFT"
    return t


# ---------------------------------------------------------------------------
# Line items table.
# ---------------------------------------------------------------------------
def _line_items_table(order: Order) -> Table:
    head = ["SKU", "Item", "Qty", "Unit price", "Line total"]
    rows = [head]
    for item in order.items.all():
        rows.append(
            [
                Paragraph(item.product_sku_snapshot, _MUTED),
                Paragraph(item.product_name_snapshot, _BODY_STRONG),
                str(item.quantity),
                _money(item.unit_price, order.currency),
                _money(item.line_total, order.currency),
            ]
        )

    avail = PAGE_W - 2 * MARGIN_X
    col_widths = [
        avail * 0.18,  # SKU
        avail * 0.42,  # Item
        avail * 0.08,  # Qty
        avail * 0.16,  # Unit
        avail * 0.16,  # Line total
    ]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (2, 0), (-1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, 0), 8),
                ("RIGHTPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                # Body rows
                ("FONTSIZE", (0, 1), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 1), (-1, -1), BRAND_INK),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 1), (-1, -1), 8),
                ("RIGHTPADDING", (0, 1), (-1, -1), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_SURFACE]),
                # Bottom rule beneath the last row.
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, BRAND_RULE),
            ]
        )
    )
    return t


# ---------------------------------------------------------------------------
# Totals table — right-aligned, with a heavy violet grand-total line.
# ---------------------------------------------------------------------------
def _totals_table(order: Order) -> Table:
    cur = order.currency
    rows = [
        ["Subtotal", _money(order.subtotal, cur)],
    ]
    if order.discount_total and Decimal(order.discount_total) != 0:
        rows.append(["Discount", "− " + _money(order.discount_total, cur)])
    rows.append(["Grand total", _money(order.grand_total, cur)])

    t = Table(rows, colWidths=[42 * mm, 42 * mm], hAlign="RIGHT")

    style = [
        ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -2), 10),
        ("TEXTCOLOR", (0, 0), (-1, -2), BRAND_MUTED),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        # Grand total: violet, bold, big, with a top rule.
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 13),
        ("TEXTCOLOR", (0, -1), (-1, -1), BRAND_PRIMARY),
        ("LINEABOVE", (0, -1), (-1, -1), 1.4, BRAND_PRIMARY),
        ("TOPPADDING", (0, -1), (-1, -1), 9),
    ]
    t.setStyle(TableStyle(style))
    return t


def _money(amount, currency: str) -> str:
    # Quantize for display only; the model already stores cents-accurate Decimals.
    q = Decimal(amount).quantize(Decimal("0.01"))
    return f"{q} {currency}"
