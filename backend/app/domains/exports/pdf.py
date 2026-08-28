from io import BytesIO
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle

FONT_PATH=Path(__file__).parent/"assets"/"NotoSansTC-Subset.ttf";FONT_NAME="KitchenERP-NotoSansTC"

def paginate_blocks(rows:list,capacity:int)->list[list]:
    if capacity<1:raise ValueError("capacity must be positive")
    return [rows[i:i+capacity] for i in range(0,len(rows),capacity)] or [[]]

def _text(value):return ("-" if value is None else str(value)).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def _styles():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(FONT_NAME,str(FONT_PATH)))
    body=ParagraphStyle("zh-body",fontName=FONT_NAME,fontSize=8.5,leading=12)
    return body,ParagraphStyle("zh-title",parent=body,fontSize=16,leading=22,alignment=TA_CENTER,spaceAfter=8*mm),ParagraphStyle("zh-heading",parent=body,fontSize=11,leading=16,spaceBefore=4*mm,spaceAfter=2*mm)
def _page(canvas,doc):
    canvas.saveState();canvas.setFont(FONT_NAME,8);canvas.drawString(15*mm,10*mm,"KitchenERP V2");canvas.drawRightString(195*mm,10*mm,f"第 {doc.page} 頁");canvas.restoreState()
def _table(headers,rows,body,widths):
    data=[[Paragraph(_text(x),body) for x in headers]]+[[Paragraph(_text(x),body) for x in row] for row in rows]
    table=Table(data,colWidths=widths,repeatRows=1,hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,-1),FONT_NAME),("VALIGN",(0,0),(-1,-1),"TOP"),("GRID",(0,0),(-1,-1),0.25,colors.HexColor("#CBD5E1")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F8FAFC")]),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3)]));return table
def _document(title,sections):
    stream=BytesIO();body,title_style,heading=_styles();doc=SimpleDocTemplate(stream,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=14*mm,bottomMargin=16*mm,title=title,author="KitchenERP V2")
    story=[Paragraph(_text(title),title_style)]
    for index,(name,headers,rows,widths) in enumerate(sections):
        if index:story.append(Spacer(1,4*mm))
        story.extend([Paragraph(_text(name),heading),_table(headers,rows,body,widths)])
    doc.build(story,onFirstPage=_page,onLaterPages=_page);return stream.getvalue()
def kitchen_pdf(result):
    rows=[]
    for day in result["days"]:
        for meal in day["meals"]:
            for dish in meal["dishes"]:
                for line in dish["ingredients"]:rows.append([day["menu_date"],meal["meal_type_name"],dish["dish_name"],dish["diner_count"],line["ingredient_name"],line["display_quantity"],line["display_unit"],"、".join(a["code"] for a in line["anomalies"]) or "正常"])
    anomalies=[[x["severity"],x["code"],x["message"]] for x in result["anomalies"]]
    return _document(f'{result["menu"]["menu_name"]} 廚房備料表',[("備料明細",["日期","餐別","菜色","人數","食材","備料量","單位","狀態"],rows,[22*mm,18*mm,29*mm,12*mm,34*mm,20*mm,15*mm,30*mm]),("異常與提醒",["等級","代碼","訊息"],anomalies,[18*mm,42*mm,120*mm])])
def purchase_pdf(result):
    summary=[["採購編號",result["purchase_number"]],["狀態",result["status"]],["建立時間",result["created_at"]],["建立者",result["created_by_name"]],["來源 Snapshot Revision",result["source_snapshot_revision"]],["備註",result["notes"]],["總成本",result["total_cost"] or f'已知 {result["known_total_cost"]}']]
    sections=[("採購摘要",["欄位","固定值"],summary,[48*mm,132*mm])]
    for order in result["orders"]:
        rows=[[x.ingredient_code_snapshot,x.ingredient_name_snapshot,x.final_purchase_quantity,x.purchase_unit_snapshot,x.package_size_snapshot,x.minimum_order_quantity_snapshot,x.purchase_cost_snapshot or "無法估算"] for x in order["items"]]
        sections.append((f'{order["supplier_name_snapshot"]} - {order["total_cost"] or "成本未完整"}',["代碼","食材","採購量","單位","包裝","最低量","成本"],rows,[22*mm,43*mm,24*mm,18*mm,22*mm,22*mm,29*mm]))
    return _document(f'{result["purchase_number"]} 採購單',sections)
