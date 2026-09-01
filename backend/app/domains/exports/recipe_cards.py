from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal,InvalidOperation
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER,TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image,KeepTogether,PageBreak,Paragraph,SimpleDocTemplate,Spacer,Table,TableStyle

FONT_PATH=Path(__file__).parent/"assets"/"NotoSansTC-Subset.ttf"
FONT="KitchenERP-NotoSansTC"
STEP_LABELS={"wash":"清洗","cut":"切","chop":"剁","marinate":"醃製","blanch":"汆燙","thaw":"退冰","stir_fry":"拌炒","boil":"水煮","braise":"燉煮／滷","steam":"蒸","bake":"烘烤","fry":"油炸","pan_fry":"煎","add_ingredient":"加入食材","add_water":"加水","stir":"攪拌","flip":"翻面","thicken":"勾芡","sauce":"淋醬／拌料","garnish":"撒料／裝飾","final_addition":"最後加入","portion":"分裝","plating":"擺盤","quality_check":"成品確認","other":"其他"}
USE_LABELS={"main_ingredient":"主食材","preprocessing":"前處理","marinade":"醃料","seasoning":"烹調調味","sauce":"醬汁","final_addition":"最後加入","garnish":"裝飾"}
USE_ORDER=tuple(USE_LABELS)
INK=colors.HexColor("#171B18")
MID=colors.HexColor("#5D655F")
LINE=colors.HexColor("#AEB5B0")
PALE=colors.HexColor("#F1F3F1")


def esc(value)->str:
    return str(value or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>")


def format_decimal(value)->str:
    if value is None or value=="":return ""
    try:
        number=Decimal(str(value))
    except (InvalidOperation,ValueError):
        return str(value)
    if not number.is_finite():return str(value)
    rendered=format(number,"f")
    if "." in rendered:rendered=rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"","-0"} else rendered


def format_duration(seconds)->str:
    if seconds is None:return ""
    total=int(seconds)
    hours,remainder=divmod(total,3600);minutes,secs=divmod(remainder,60);parts=[]
    if hours:parts.append(f"{hours} 小時")
    if minutes:parts.append(f"{minutes} 分鐘")
    if secs or not parts:parts.append(f"{secs} 秒")
    return " ".join(parts)


def aggregate_batches(batches:list[dict])->list[dict]:
    groups:OrderedDict[tuple,dict]=OrderedDict()
    for batch in batches:
        key=(batch["serving_count"],batch["official"],str(batch.get("version_id") or ""))
        if key not in groups:groups[key]={"serving_count":batch["serving_count"],"official":batch["official"],"count":0,"batch_numbers":[],"batch":batch}
        groups[key]["count"]+=1;groups[key]["batch_numbers"].append(batch["batch_number"])
    return list(groups.values())


def aggregate_ingredients(batches:list[dict])->list[dict]:
    values:OrderedDict[tuple,dict]=OrderedDict()
    for batch in batches:
        for item in batch.get("ingredients",[]):
            key=(item.get("usage_category"),str(item.get("ingredient_id") or item.get("ingredient_name")),item.get("unit"),item.get("quantity_note") or item.get("notes") or "")
            if key not in values:values[key]={**item,"quantity":Decimal(0)}
            values[key]["quantity"]+=Decimal(str(item["quantity"]))
    order={value:index for index,value in enumerate(USE_ORDER)}
    return sorted(values.values(),key=lambda item:(order.get(item.get("usage_category"),99),item.get("sort_order",999),item.get("ingredient_name","") ))


class RecipeCardStyles:
    def __init__(self):
        self.body=ParagraphStyle("rc-body",fontName=FONT,fontSize=10,leading=15,textColor=INK)
        self.small=ParagraphStyle("rc-small",parent=self.body,fontSize=8.5,leading=12,textColor=MID)
        self.title=ParagraphStyle("rc-title",parent=self.body,fontSize=25,leading=30,spaceAfter=2*mm)
        self.detail_title=ParagraphStyle("rc-detail-title",parent=self.body,fontSize=21,leading=26,spaceAfter=1*mm)
        self.meta=ParagraphStyle("rc-meta",parent=self.body,fontSize=11.5,leading=16)
        self.section=ParagraphStyle("rc-section",parent=self.body,fontSize=13,leading=18,spaceBefore=4*mm,spaceAfter=2*mm)
        self.group=ParagraphStyle("rc-group",parent=self.body,fontSize=11,leading=15,spaceBefore=2*mm,spaceAfter=1*mm)
        self.step_title=ParagraphStyle("rc-step-title",parent=self.body,fontSize=13,leading=18)
        self.step_body=ParagraphStyle("rc-step-body",parent=self.body,leftIndent=7*mm,spaceAfter=1*mm)
        self.warning=ParagraphStyle("rc-warning",parent=self.body,fontSize=11,leading=16)
        self.center=ParagraphStyle("rc-center",parent=self.body,alignment=TA_CENTER)
        self.right=ParagraphStyle("rc-right",parent=self.body,alignment=TA_RIGHT)


def _image(path,max_width,max_height):
    if not path:return None
    try:
        value=Image(str(path));value._restrictSize(max_width,max_height);return value
    except Exception:return None


def _boxed(content,widths=None,padding=3*mm,background=colors.white):
    table=Table([content],colWidths=widths,hAlign="LEFT")
    table.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.8,INK),("BACKGROUND",(0,0),(-1,-1),background),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),padding),("RIGHTPADDING",(0,0),(-1,-1),padding),("TOPPADDING",(0,0),(-1,-1),padding),("BOTTOMPADDING",(0,0),(-1,-1),padding)]))
    return table


def _header(story,plan,day,meal,dish,styles,image_loader,detail=False):
    title_style=styles.detail_title if detail else styles.title
    text=[Paragraph(esc(dish["dish_name"]),title_style)]
    if detail:text.append(Paragraph("標準食譜卡｜詳細版",styles.meta))
    text.append(Paragraph(f'{esc(day["menu_date"])}｜{esc(meal["meal_type_name"])}｜<b>{dish["diner_count"]} 人</b>',styles.meta))
    photo=None
    if dish.get("has_image"):
        try:photo=_image(image_loader(dish["dish_id"]),48*mm,34*mm)
        except Exception:photo=None
    if photo:
        photo_cell=[Paragraph("成品參考",styles.small),photo]
        header=Table([[text,photo_cell]],colWidths=[128*mm,48*mm],hAlign="LEFT")
        header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]));story.append(header)
    else:story.extend(text)
    if detail:story.append(Paragraph(f'菜單：{esc(plan["menu_name"])}',styles.small))


def _batch_summary(dish,styles,work=True):
    groups=aggregate_batches(dish["batches"]);rows=[]
    for group in groups:
        status="" if group["official"] else "　[注意：系統估算]"
        rows.append([Paragraph(f'<b>{group["serving_count"]} 人份 × {group["count"]} 批</b>{status}',styles.meta)])
    total_servings=sum(batch["serving_count"] for batch in dish["batches"])
    rows.append([Paragraph(f'共 <b>{total_servings} 人</b>｜<b>{dish["batch_count"]} 批</b>',styles.meta)])
    return _boxed([[row[0] for row in rows]],widths=[176*mm],padding=3*mm,background=PALE) if rows else Spacer(1,0)


def _work_ingredients(dish,styles):
    ingredients=aggregate_ingredients(dish["batches"])
    if not ingredients:return []
    result=[Paragraph("【先準備】",styles.section)]
    for usage in USE_ORDER:
        items=[item for item in ingredients if item.get("usage_category")==usage]
        if not items:continue
        result.append(Paragraph(esc(USE_LABELS[usage]),styles.group));rows=[]
        for item in items:
            note=item.get("quantity_note") or item.get("notes") or ""
            rows.append([Paragraph(esc(item["ingredient_name"]),styles.body),Paragraph(f'<b>{format_decimal(item["quantity"])} {esc(item["unit"])}</b>',styles.right),Paragraph(esc(note),styles.small)])
        table=Table(rows,colWidths=[77*mm,42*mm,57*mm],hAlign="LEFT")
        table.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,-1),.25,LINE),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),1.5*mm),("RIGHTPADDING",(0,0),(-1,-1),1.5*mm),("TOPPADDING",(0,0),(-1,-1),1.7*mm),("BOTTOMPADDING",(0,0),(-1,-1),1.7*mm)]));result.append(table)
    return result


def _step_details(step,styles,compact=True):
    lines=[]
    if step.get("instruction"):lines.append(Paragraph(esc(step["instruction"]),styles.body))
    controls=[]
    if step.get("equipment"):controls.append(esc(step["equipment"]))
    if step.get("temperature_celsius") is not None:controls.append(f'{format_decimal(step["temperature_celsius"])}°C')
    if step.get("duration_seconds") is not None:controls.append(format_duration(step["duration_seconds"]))
    if controls:lines.append(Paragraph("｜".join(controls),styles.body))
    capacity=[]
    if step.get("batch_size"):capacity.append(f'一次 {step["batch_size"]} 人')
    if step.get("servings_per_tray"):capacity.append(f'每盤 {step["servings_per_tray"]} 人')
    if step.get("trays_per_batch"):capacity.append(f'一次 {step["trays_per_batch"]} 盤')
    if capacity:lines.append(Paragraph("｜".join(capacity),styles.body))
    note=step.get("notes") or step.get("quantity_note")
    if note:lines.append(Paragraph(f'[注意] {esc(note)}',styles.warning))
    return lines


def _work_steps(dish,styles):
    result=[Paragraph("【製作步驟】",styles.section)];groups=aggregate_batches(dish["batches"]);has_steps=False
    for group in groups:
        steps=group["batch"].get("steps") or []
        if not steps:
            if not group["official"]:result.append(_boxed([Paragraph(f'{group["serving_count"]} 人估算批次沒有已確認製作步驟，請現場確認。',styles.warning)],widths=[176*mm],background=PALE))
            continue
        has_steps=True
        if len(groups)>1:result.append(Paragraph(f'{group["serving_count"]} 人份 × {group["count"]} 批',styles.group))
        for step in steps:
            title=step.get("title") or STEP_LABELS.get(step.get("step_type"),step.get("step_type") or "製作")
            details=_step_details(step,styles)
            for detail in details:detail.style=styles.step_body if detail.style is styles.body else detail.style
            result.append(KeepTogether([Paragraph(f'<b>{step["step_order"]}. {esc(title)}</b>',styles.step_title),*details,Spacer(1,4*mm)]))
    if not has_steps:result.append(Paragraph("尚未建立製作步驟。",styles.body))
    return result


def _notes(dish,styles,work=True):
    values=[value for value in (dish.get("profile_notes"),dish.get("notes")) if value]
    if not values:return []
    title="【注意事項】" if work else "【注意事項與備註】"
    rows=[[Paragraph(f'[注意] {esc(value)}',styles.warning)] for value in values]
    return [Paragraph(title,styles.section),_boxed([[row[0] for row in rows]],widths=[176*mm],background=PALE)]


def _work_page(plan,day,meal,dish,styles,image_loader):
    story=[];_header(story,plan,day,meal,dish,styles,image_loader)
    if dish["profile_missing"]:
        story.extend([Spacer(1,12*mm),_boxed([Paragraph("[注意] 尚未建立標準食譜卡",styles.warning)],widths=[176*mm],padding=6*mm,background=PALE)]);return story
    story.extend([Paragraph("【今日製作】",styles.section),_batch_summary(dish,styles),*_work_ingredients(dish,styles),*_work_steps(dish,styles),*_notes(dish,styles)])
    return story


def _detail_ingredients(batch,styles):
    if not batch.get("ingredients"):return []
    rows=[[Paragraph("用途",styles.small),Paragraph("食材／調味",styles.small),Paragraph("用量",styles.small),Paragraph("說明",styles.small)]]
    for item in batch["ingredients"]:
        rows.append([Paragraph(esc(USE_LABELS.get(item.get("usage_category"),item.get("usage_category"))),styles.body),Paragraph(esc(item["ingredient_name"]),styles.body),Paragraph(f'{format_decimal(item["quantity"])} {esc(item["unit"])}',styles.body),Paragraph(esc(item.get("quantity_note") or item.get("notes")),styles.small)])
    table=Table(rows,colWidths=[30*mm,58*mm,36*mm,52*mm],repeatRows=1,hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),PALE),("BOX",(0,0),(-1,-1),.5,LINE),("INNERGRID",(0,0),(-1,-1),.25,LINE),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),2*mm),("RIGHTPADDING",(0,0),(-1,-1),2*mm),("TOPPADDING",(0,0),(-1,-1),2*mm),("BOTTOMPADDING",(0,0),(-1,-1),2*mm)]));return [table]


def _detail_steps(batch,styles):
    result=[]
    for step in batch.get("steps") or []:
        type_label=STEP_LABELS.get(step.get("step_type"),step.get("step_type") or "製作")
        explicit_title=step.get("title")
        title=explicit_title or type_label
        type_suffix=f"（{type_label}）" if explicit_title and explicit_title != type_label else ""
        fields=[]
        if step.get("instruction"):fields.append(("操作",step["instruction"]))
        if step.get("equipment"):fields.append(("設備",step["equipment"]))
        if step.get("temperature_celsius") is not None:fields.append(("溫度",f'{format_decimal(step["temperature_celsius"])}°C'))
        if step.get("duration_seconds") is not None:fields.append(("時間",format_duration(step["duration_seconds"])))
        if step.get("batch_size"):fields.append(("一次製作",f'{step["batch_size"]} 人'))
        if step.get("servings_per_tray"):fields.append(("每盤",f'{step["servings_per_tray"]} 人'))
        if step.get("trays_per_batch"):fields.append(("一次放入",f'{step["trays_per_batch"]} 盤'))
        if step.get("quantity_note"):fields.append(("用量提醒",step["quantity_note"]))
        if step.get("notes"):fields.append(("注意",step["notes"]))
        rows=[[Paragraph(f'<b>{esc(label)}</b>',styles.small),Paragraph(esc(value),styles.body)] for label,value in fields]
        content=[Paragraph(f'步驟 {step["step_order"]}｜{esc(title)}{esc(type_suffix)}',styles.step_title)]
        if rows:
            table=Table(rows,colWidths=[28*mm,142*mm],hAlign="LEFT");table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,-1),.2,LINE),("LEFTPADDING",(0,0),(-1,-1),1.5*mm),("RIGHTPADDING",(0,0),(-1,-1),1.5*mm),("TOPPADDING",(0,0),(-1,-1),1.5*mm),("BOTTOMPADDING",(0,0),(-1,-1),1.5*mm)]));content.append(table)
        result.append(KeepTogether([_boxed([content],widths=[176*mm],padding=2.5*mm),Spacer(1,2*mm)]))
    if not result:result.append(Paragraph("尚未建立製作步驟。",styles.body))
    return result


def _detail_page(plan,day,meal,dish,styles,image_loader):
    story=[];_header(story,plan,day,meal,dish,styles,image_loader,detail=True)
    if dish["profile_missing"]:
        story.extend([Spacer(1,10*mm),_boxed([Paragraph("尚未建立標準食譜資料。",styles.warning)],widths=[176*mm],padding=6*mm,background=PALE)]);return story
    summary=[Paragraph(f'一次最多：<b>{dish["max_batch_size"]} 人</b>　｜　本次共：<b>{dish["batch_count"]} 批</b>',styles.meta)]
    story.extend([Spacer(1,3*mm),_boxed(summary,widths=[176*mm],background=PALE),Paragraph("【製作版本】",styles.section)])
    groups=aggregate_batches(dish["batches"])
    for group in groups:
        status="已確認" if group["official"] else "系統估算"
        story.append(Paragraph(f'{group["serving_count"]} 人份 × {group["count"]} 批｜{status}',styles.meta))
    for group in groups:
        batch=group["batch"];status="已確認" if group["official"] else "系統估算"
        story.append(Paragraph(f'【食材與調味｜{group["serving_count"]} 人份｜{status}】',styles.section))
        if batch.get("version_notes"):story.append(Paragraph(f'份數備註：{esc(batch["version_notes"])}',styles.body))
        story.extend(_detail_ingredients(batch,styles) or [Paragraph("沒有食材資料。",styles.body)])
        story.append(Paragraph(f'【完整製作流程｜{group["serving_count"]} 人份】',styles.section));story.extend(_detail_steps(batch,styles))
    story.extend(_notes(dish,styles,work=False));return story


def recipe_cards_pdf(plan:dict,image_loader,mode:str="work")->bytes:
    if mode not in {"work","detailed"}:raise ValueError("Unknown recipe card mode")
    if FONT not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(FONT,str(FONT_PATH)))
    styles=RecipeCardStyles();stream=BytesIO();label="廚房工作單" if mode=="work" else "標準食譜詳細版"
    doc=SimpleDocTemplate(stream,pagesize=A4,leftMargin=17*mm,rightMargin=17*mm,topMargin=14*mm,bottomMargin=14*mm,title=f'{plan["menu_name"]} {label}',author="KitchenERP V2",allowSplitting=True)
    story=[];first=True
    for day in plan["days"]:
        for meal in day["meals"]:
            for dish in meal["dishes"]:
                if not first:story.append(PageBreak())
                first=False;story.extend((_work_page if mode=="work" else _detail_page)(plan,day,meal,dish,styles,image_loader))
    if first:story.append(Paragraph("指定範圍沒有菜色",styles.title))
    def footer(canvas,document):
        canvas.saveState();canvas.setStrokeColor(LINE);canvas.line(17*mm,10*mm,193*mm,10*mm);canvas.setFillColor(MID);canvas.setFont(FONT,7.5);canvas.drawString(17*mm,6.5*mm,f"KitchenERP V2｜{label}");canvas.drawRightString(193*mm,6.5*mm,f"第 {document.page} 頁");canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer);return stream.getvalue()
