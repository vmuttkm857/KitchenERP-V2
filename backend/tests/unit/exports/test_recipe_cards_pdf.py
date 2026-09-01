from copy import deepcopy
from io import BytesIO

from PIL import Image as PILImage
from pypdf import PdfReader

from app.domains.exports.recipe_cards import format_decimal,format_duration,recipe_cards_pdf


def batch(number,servings,official=True,with_steps=True):
    return {
        "batch_number":number,"serving_count":servings,"official":official,"version_id":f"v-{servings}" if official else None,"version_name":f"{servings} 人版" if official else None,"version_notes":"分盤後立即出餐" if official else None,
        "ingredients":[
            {"ingredient_id":"chicken","ingredient_name":"去骨雞腿","quantity":"50.0000000000","unit":"隻","usage_category":"main_ingredient","sort_order":1,"quantity_note":None,"notes":None},
            {"ingredient_id":"soy","ingredient_name":"醬油","quantity":"1.5000000000","unit":"L","usage_category":"marinade","sort_order":2,"quantity_note":"分兩盆","notes":None},
            {"ingredient_id":"onion","ingredient_name":"蔥花","quantity":"200.0000000000","unit":"g","usage_category":"final_addition","sort_order":3,"quantity_note":None,"notes":None},
        ],
        "steps":[
            {"step_order":1,"step_type":"marinate","title":"醃製","instruction":"雞腿加入醬油抓拌均勻","equipment":None,"duration_seconds":1800,"temperature_celsius":None,"batch_size":None,"servings_per_tray":None,"trays_per_batch":None,"quantity_note":None,"notes":None},
            {"step_order":2,"step_type":"bake","title":"烘烤","instruction":"放入蒸烤箱烘烤","equipment":"蒸烤箱","duration_seconds":90,"temperature_celsius":"180.0000000000","batch_size":None,"servings_per_tray":20,"trays_per_batch":5,"quantity_note":None,"notes":"確認中心熟度"},
        ] if with_steps else [],
    }


def sample_plan(batches=None,with_missing=True):
    dishes=[{"dish_id":"dish-1","dish_code":"D1","dish_name":"烤去骨雞腿","diner_count":250,"sort_order":1,"notes":"起鍋後再撒蔥花","profile_notes":"出餐前確認中心熟度","profile_missing":False,"max_batch_size":100,"has_image":False,"batch_count":len(batches or [batch(1,50)]),"batches":batches or [batch(1,50)]}]
    if with_missing:dishes.append({"dish_id":"dish-2","dish_code":"D2","dish_name":"烤肉雞腿","diner_count":50,"sort_order":2,"notes":None,"profile_notes":None,"profile_missing":True,"max_batch_size":None,"has_image":False,"batch_count":0,"batches":[]})
    return {"menu_id":"menu-1","menu_name":"測試菜單01","days":[{"menu_date":"2026-08-31","meals":[{"meal_type_id":"breakfast","meal_type_name":"早餐","meal_order":1,"dishes":dishes}]}]}


def pdf_text(payload):
    reader=PdfReader(BytesIO(payload))
    return reader,"\n".join(page.extract_text() or "" for page in reader.pages)


def test_work_pdf_single_dish_single_batch_and_grouped_ingredients():
    reader,text=pdf_text(recipe_cards_pdf(sample_plan(with_missing=False),lambda _:None,"work"))
    assert len(reader.pages)==1
    assert "烤去骨雞腿" in text and "2026-08-31｜早餐｜50 人" not in text
    assert "【今日製作】" in text
    assert "50 人份 × 1 批" in text
    assert "共 50 人｜1 批" in text
    assert all(label in text for label in ("【先準備】","主食材","醃料","最後加入","去骨雞腿","醬油","蔥花"))
    assert "用途" not in text and "50.0000000000" not in text


def test_work_pdf_multi_batch_checklist_estimate_steps_and_empty_fields():
    batches=[batch(1,100),batch(2,100),batch(3,50,official=False,with_steps=False)]
    reader,text=pdf_text(recipe_cards_pdf(sample_plan(batches,with_missing=False),lambda _:None,"work"))
    assert len(reader.pages)>=1
    assert "100 人份 × 2 批" in text and "50 人份 × 1 批" in text and "共 250 人｜3 批" in text
    assert "批次勾選" not in text
    assert all(f"第 {number} 批" not in text for number in (1,2,3))
    assert "系統估算" in text and "沒有已確認製作步驟" in text
    assert "1. 醃製" in text and "2. 烘烤" in text
    assert "30 分鐘" in text and "1 分鐘 30 秒" in text and "180°C" in text
    assert "—" not in text and "設備：" not in text


def test_work_pdf_photo_optional_and_missing_profile(tmp_path):
    image_path=tmp_path/"dish.png";PILImage.new("RGB",(320,180),(220,220,220)).save(image_path)
    plan=sample_plan();plan["days"][0]["meals"][0]["dishes"][0]["has_image"]=True
    reader,text=pdf_text(recipe_cards_pdf(plan,lambda dish_id:image_path if dish_id=="dish-1" else None,"work"))
    assert len(reader.pages)==2
    assert "烤去骨雞腿" in reader.pages[0].extract_text()
    assert "烤肉雞腿" in reader.pages[1].extract_text() and "尚未建立標準食譜卡" in reader.pages[1].extract_text()
    assert "/XObject" in reader.pages[0]["/Resources"]


def test_detailed_pdf_complete_estimate_missing_and_human_formatting():
    batches=[batch(1,50),batch(2,21,official=False,with_steps=False)]
    reader,text=pdf_text(recipe_cards_pdf(sample_plan(batches),lambda _:None,"detailed"))
    assert len(reader.pages)>=2
    assert "標準食譜卡｜詳細版" in text and "菜單：測試菜單01" in text
    assert "一次最多：100 人" in text and "本次共：2 批" in text
    assert "50 人份 × 1 批｜已確認" in text and "21 人份 × 1 批｜系統估算" in text
    assert all(label in text for label in ("用途","食材／調味","用量","說明","步驟 1｜醃製","操作","時間"))
    assert "尚未建立標準食譜資料" in text
    assert "1.5000000000" not in text and "180.0000000000" not in text


def test_both_modes_consume_the_same_plan_without_mutation_and_keep_dish_order():
    plan=sample_plan();before=deepcopy(plan)
    work_reader,work_text=pdf_text(recipe_cards_pdf(plan,lambda _:None,"work"))
    detail_reader,detail_text=pdf_text(recipe_cards_pdf(plan,lambda _:None,"detailed"))
    assert plan==before
    assert len(work_reader.pages)==len(detail_reader.pages)==2
    assert work_text.index("烤去骨雞腿")<work_text.index("烤肉雞腿")
    assert detail_text.index("烤去骨雞腿")<detail_text.index("烤肉雞腿")


def test_decimal_and_duration_formatters_cover_large_and_fractional_values():
    assert format_decimal("50.0000000000")=="50"
    assert format_decimal("1.5000000000")=="1.5"
    assert format_decimal("2.2500000000")=="2.25"
    assert format_duration(1800)=="30 分鐘"
    assert format_duration(7200)=="2 小時"
    assert format_duration(90)=="1 分鐘 30 秒"
    assert format_duration(469200)=="130 小時 20 分鐘"
