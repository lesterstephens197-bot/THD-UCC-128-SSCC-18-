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
        # 奇数索引(从1开始，即0,2,4...)乘以3，偶数索引乘以1
        if i % 2 == 0:
            total += digit * 3
        else:
            total += digit * 1

    check_digit = (10 - (total % 10)) % 10
    return check_digit

def generate_sscc_18(ext_digit: str, gs1_prefix: str, serial_num: int) -> str:
    """组装并生成完整的18位SSCC编码"""
    # 保证 Serial Reference 为 9 位纯数字（不足补前导0）
    serial_str = f"{serial_num:09d}"
    base_17 = f"{ext_digit}{gs1_prefix}{serial_str}"
    
    if len(base_17) != 17:
        raise ValueError(f"生成的 base 长度错误 ({len(base_17)}位)，请检查 GS1 Prefix 是否为 7 位数字。")
        
    check_digit = calculate_sscc_check_digit(base_17)
    return f"{base_17}{check_digit}"

# --- 2. 条形码图像生成 ---
def generate_barcode_image(sscc_18: str):
    """生成带有 AI (00) 的 GS1-128 / UCC-128 条形码图像"""
    # UCC-128 数据内容格式为 (00) + SSCC-18
    barcode_data = f"00{sscc_18}"
    
    # 使用 Code128 写入器生成条码
    Code128 = barcode.get_barcode_class('code128')
    rv = io.BytesIO()
    
    # 配置条码样式
    writer = ImageWriter()
    options = {
        'module_width': 0.35,  # 条码线宽
        'module_height': 12.0, # 条码高度
        'quiet_zone': 2.0,    # 左右留白
        'write_text': False,  # 不在图片内部自动打印文本，我们手动绘制标准格式文本
    }
    
    bc = Code128(barcode_data, writer=writer)
    bc.write(rv, options=options)
    rv.seek(0)
    return rv

# --- 3. 生成符合THD格式的 PDF 标签 (4x6 英寸) ---
def create_thd_pdf(data: dict) -> bytes:
    buffer = io.BytesIO()
    
    # 4x6 英寸标准热敏纸标签尺寸
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
    
    # 自定义样式
    style_label = ParagraphStyle('Label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=6.5, leading=8)
    style_val_sm = ParagraphStyle('ValSm', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10)
    style_val_lg = ParagraphStyle('ValLg', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=18, leading=20, alignment=TA_CENTER)
    style_val_po = ParagraphStyle('ValPo', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=22, leading=24, alignment=TA_CENTER)
    style_sscc_text = ParagraphStyle('SSCCText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=13, alignment=TA_CENTER)

    # 生成条形码
    sscc_18 = data['sscc_18']
    barcode_img_stream = generate_barcode_image(sscc_18)
    barcode_img = Image(barcode_img_stream, width=usable_width * 0.95, height=1.1 * inch)

    # 格式化 SSCC 显示文本: (00) X XXXXXXX XXXXXXXXX X
    sscc_formatted = f"(00) {sscc_18[0]} {sscc_18[1:8]} {sscc_18[8:17]} {sscc_18[17]}"

    # 第 1 行：FROM 和 TO
    from_text = f"**FROM:**
