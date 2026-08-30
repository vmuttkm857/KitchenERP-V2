from io import BytesIO
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import event
from app.db.session import engine as process_engine
from tests.api.kitchen_operations.test_kitchen_operations_api import kitchen_fixture
from tests.api.requirements.test_requirements_api import auth

def test_exports_require_auth(client):
    response=client.post("/api/v1/exports/kitchen-operations/xlsx",json={"menu_id":"00000000-0000-0000-0000-000000000001"})
    assert response.status_code==401

def test_kitchen_excel_and_pdf_are_binary_authenticated_downloads(client,db_session):
    headers=auth(client,db_session);menu,*_=kitchen_fixture(client,headers,db_session);body={"menu_id":menu["id"],"selected_dates":["2026-10-01"]}
    xlsx=client.post("/api/v1/exports/kitchen-operations/xlsx",headers=headers,json=body)
    assert xlsx.status_code==200,xlsx.text;assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in xlsx.headers["content-disposition"];assert xlsx.content[:2]==b"PK"
    wb=load_workbook(BytesIO(xlsx.content));assert "備料明細" in wb.sheetnames and wb["備料明細"].max_row>1
    pdf=client.post("/api/v1/exports/kitchen-operations/pdf",headers=headers,json=body)
    assert pdf.status_code==200,pdf.text;assert pdf.headers["content-type"].startswith("application/pdf");assert pdf.content.startswith(b"%PDF")
    assert len(PdfReader(BytesIO(pdf.content)).pages)>=1

def test_kitchen_a4_excel_is_an_independent_print_download(client,db_session):
    headers=auth(client,db_session);menu,*_=kitchen_fixture(client,headers,db_session);body={"menu_id":menu["id"],"selected_dates":["2026-10-01"]}
    response=client.post("/api/v1/exports/kitchen-operations/a4-xlsx",headers=headers,json=body)
    assert response.status_code==200,response.text
    assert "A4" in response.headers["content-disposition"]
    wb=load_workbook(BytesIO(response.content))
    assert wb.sheetnames
    assert all(ws.page_setup.paperSize==9 and ws.page_setup.fitToWidth==1 for ws in wb.worksheets)

def test_kitchen_a4_export_query_count_does_not_grow_per_row(client,db_session):
    headers=auth(client,db_session);menu,*_=kitchen_fixture(client,headers,db_session);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.post("/api/v1/exports/kitchen-operations/a4-xlsx",headers=headers,json={"menu_id":menu["id"]})
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=4

def test_kitchen_export_query_count_does_not_grow_per_row(client,db_session):
    headers=auth(client,db_session);menu,*_=kitchen_fixture(client,headers,db_session);statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
    event.listen(process_engine,"before_cursor_execute",record)
    try:response=client.post("/api/v1/exports/kitchen-operations/xlsx",headers=headers,json={"menu_id":menu["id"]})
    finally:event.remove(process_engine,"before_cursor_execute",record)
    assert response.status_code==200
    assert len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])<=4
