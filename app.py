import io
import streamlit as st
import barcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# --- 1. GS1 / SSCC-18 校验码计算算法 ---
def calculate_sscc_check_digit(number_17_digits: str) -> int:
    """根据前17位数字计算 GS1 模数10校验位"""
    if len(number_17_digits) != 17 or not number_17_digits.isdigit():
        raise ValueError("SSCC-18 前体必须是17位纯数字")
    
    total = 0
    for i, char in enumerate(number_17_digits):
        digit = int(char)
        if i % 2 == 0:
            total += digit * 3
        else:
            total += digit * 1

    check_digit = (10 - (total % 10)) % 10
    return check_digit

def generate_sscc_18(ext_digit: str, gs1_prefix: str, serial_num: int) -> str:
    """组装并生成完整的18位SSCC编码"""
    serial_str = f"{serial_num:09d}"
    base_17 = f"{ext_digit}{gs1_prefix}{serial_str}"
    
    if len(base_17) != 17:
        raise ValueError(f"生成的 base 长度错误 ({len(base_17)}位)，请检查 GS1 Prefix 是否为 7 位数字。")
        
    check_digit = calculate_sscc_check_digit(base_17)
    return f"{base_17}{check_digit}"

# --- 2. 条形码图像生成 ---
def generate_barcode_image(sscc_18: str):
    """生成带有 Application Identifier (00) 的 GS1-128 / UCC-128 条形码图像"""
    barcode_data = f"00{sscc_18}"
    
    Code128 = barcode.get_barcode_class('code128')
    rv = io.BytesIO()
    
    writer = ImageWriter()
    options = {
        'module_width': 0.35,
        'module_height': 12.0,
        'quiet_zone': 2.0,
        'write_text': False,
    }
    
    bc = Code128(barcode_data, writer=writer)
    bc.write(rv, options=options)
    rv.seek(0)
    return rv

# --- 3. 生成符合 THD 格式的 PDF 标签 (4x6 英寸) ---
def create_thd_pdf(data: dict) -> bytes:
    buffer = io.BytesIO()
    
    page_width = 4 * inch
    page_height = 6 * inch
    
    margin = 0.15 * inch
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(page_width, page_height),
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )
    
    usable_width = page_width - 2 * margin
    styles = getSampleStyleSheet()
    
    style_label = ParagraphStyle('Label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8)
    style_val_sm = ParagraphStyle('ValSm', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10)
    style_val_lg = ParagraphStyle('ValLg', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=20, alignment=TA_CENTER)
    style_val_po = ParagraphStyle('ValPo', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=22, leading=24, alignment=TA_CENTER)
    style_sscc_text = ParagraphStyle('SSCCText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=13, alignment=TA_CENTER)

    sscc_18 = data['sscc_18']
    barcode_img_stream = generate_barcode_image(sscc_18)
    barcode_img = Image(barcode_img_stream, width=usable_width * 0.95, height=1.1 * inch)

    # 格式化显示: (00) 0 0872560 000000001 7
    sscc_formatted = f"(00) {sscc_18[0]} {sscc_18[1:8]} {sscc_18[8:17]} {sscc_18[17]}"

    # 第 1 行：FROM 和 TO (安全格式化字符串，避免 f-string 语法错误)
    from_lines = [data['from_name']] + [addr for addr in [data['from_addr1'], data['from_addr2'], data['from_addr3'], data['from_addr4']] if addr]
    from_text = "<b>FROM:</b><br/>" + "<br/>".join(from_lines)
    
    to_lines = ["<b>" + data['to_name'] + "</b>"] + [addr for addr in [data['to_addr1'], data['to_addr2'], data['to_addr3'], data['to_addr4']] if addr]
    to_text = "<b>TO:</b> " + "<br/>".join(to_lines)
    
    cell_from = [Paragraph(from_text, style_val_sm)]
    cell_to = [Paragraph(to_text, style_val_sm)]

    # 第 2 行：CARRIER 和 STORE #
    carrier_text = "<b>CARRIER:</b><br/><b>" + data['carrier'] + "</b><br/><b>TMS ID#: " + data['tms_id'] + "</b><br/><b>BOL #: " + data['bol_num'] + "</b>"
    store_text = "<b>STORE #:</b>"
    
    cell_carrier = [Paragraph(carrier_text, style_val_sm)]
    cell_store = [
        Paragraph(store_text, style_label),
        Spacer(1, 4),
        Paragraph(data['store_num'], style_val_lg)
    ]

    # 第 3 行：PO #
    cell_po = [Paragraph("PO: " + data['po_num'], style_val_po)]

    # 第 4 行：PALLET NO. 和 NO. OF CARTONS
    cell_pallet = [
        Paragraph("<b>PALLET NO.:</b>", style_label),
        Spacer(1, 4),
        Paragraph(str(data['pallet_curr']) + " of " + str(data['pallet_total']), style_val_lg)
    ]
    cell_cartons = [
        Paragraph("<b>NO. OF CARTONS:</b>", style_label),
        Spacer(1, 4),
        Paragraph(str(data['cartons']), style_val_lg)
    ]

    # 第 5 行：条码区
    cell_barcode = [
        Paragraph("<b>SSCC-18 &nbsp;&nbsp;&nbsp;&nbsp; " + sscc_formatted + "</b>", style_sscc_text),
        Spacer(1, 2),
        barcode_img
    ]

    col_w = usable_width / 2.0
    table_data = [
        [cell_from, cell_to],
        [cell_carrier, cell_store],
        [cell_po, ''],
        [cell_pallet, cell_cartons],
        [cell_barcode, '']
    ]

    t = Table(table_data, colWidths=[col_w, col_w])
    t.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1.5, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 1, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('SPAN', (0, 2), (1, 2)),
        ('ALIGN', (0, 2), (1, 2), 'CENTER'),
        ('VALIGN', (0, 2), (1, 2), 'MIDDLE'),
        ('SPAN', (0, 4), (1, 4)),
        ('ALIGN', (0, 4), (1, 4), 'CENTER'),
        ('VALIGN', (0, 4), (1, 4), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 4),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))

    story = [t]
    doc.build(story)
    
    pdf_val = buffer.getvalue()
    buffer.close()
    return pdf_val

# --- 4. Streamlit UI 界面 ---
st.set_page_config(page_title="THD UCC-128 Label Generator", layout="wide")

st.title("📦 The Home Depot UCC-128 Pallet Label Generator")
st.markdown("用于生成 THD 标准 4x6 英寸 UCC-128 / SSCC-18 托盘标签 PDF。")

with st.form("label_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. 发货与收货信息 (Addresses)")
        from_name = st.text_input("Supplier Name", "Supplier Name")
        from_addr1 = st.text_input("From Address 1", "From Address 1")
        from_addr2 = st.text_input("From Address 2", "From Address 2")
        from_addr3 = st.text_input("From Address 3", "From Address 3")
        from_addr4 = st.text_input("From Address 4", "From Address 4")
        
        to_name = st.text_input("TO Name", "The Home Depot - RDC XXXX")
        to_addr1 = st.text_input("TO Address 1", "TO ADDRESS 1")
        to_addr2 = st.text_input("TO Address 2", "TO ADDRESS 2")
        to_addr3 = st.text_input("TO Address 3", "TO ADDRESS 3")
        to_addr4 = st.text_input("TO Address 4", "TO ADDRESS 4")

    with col2:
        st.subheader("2. 运输与订单信息 (Order & Shipment)")
        carrier = st.text_input("Carrier", "On-Time Freight")
        tms_id = st.text_input("TMS ID#", "14823774")
        bol_num = st.text_input("BOL #", "12897593513267812")
        store_num = st.text_input("STORE #", "1987")
        po_num = st.text_input("PO #", "01945678")
        
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            pallet_curr = st.number_input("Pallet Current", min_value=1, value=3)
        with col_p2:
            pallet_total = st.number_input("Pallet Total", min_value=1, value=12)
        with col_p3:
            cartons = st.number_input("No. of Cartons", min_value=1, value=14)

        st.subheader("3. SSCC-18 编号参数")
        ext_digit = st.selectbox("Extension Digit (1位)", ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], index=0)
        gs1_prefix = st.text_input("GS1 Company Prefix (7位数字)", "0872560", max_chars=7)
        serial_num = st.number_input("Serial Reference (流水号，自动补足9位)", min_value=0, max_value=999999999, value=1)

    submitted = st.form_submit_button("🔨 生成标签 PDF")

if submitted:
    try:
        sscc_18 = generate_sscc_18(ext_digit, gs1_prefix, serial_num)
        
        label_data = {
            "from_name": from_name, "from_addr1": from_addr1, "from_addr2": from_addr2,
            "from_addr3": from_addr3, "from_addr4": from_addr4,
            "to_name": to_name, "to_addr1": to_addr1, "to_addr2": to_addr2,
            "to_addr3": to_addr3, "to_addr4": to_addr4,
            "carrier": carrier, "tms_id": tms_id, "bol_num": bol_num,
            "store_num": store_num, "po_num": po_num,
            "pallet_curr": pallet_curr, "pallet_total": pallet_total, "cartons": cartons,
            "sscc_18": sscc_18
        }

        pdf_bytes = create_thd_pdf(label_data)

        st.success(f"✅ 生成成功！生成的 SSCC-18 编码为: **{sscc_18}**")
        st.info(f"对应 ASN 中 MAN*GM 段的值应为: `00{sscc_18}`")

        st.download_button(
            label="📥 下载 UCC-128 Label (PDF)",
            data=pdf_bytes,
            file_name=f"THD_UCC128_{po_num}_pallet_{pallet_curr}.pdf",
            mime="application/pdf"
        )
    except Exception as e:
        st.error(f"生成失败，错误信息: {str(e)}")
