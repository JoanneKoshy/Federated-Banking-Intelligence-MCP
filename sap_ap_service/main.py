"""
SAP AP/Procurement Service -- meant to be deployed onto SAP BTP Cloud
Foundry (see manifest.yml), same pattern as core-banking-service.

Unlike core-banking-service (which uses hardcoded Python dicts for 4
customers), this service has real volume (5,000+ line items across 8
SAP-standard tables), so on startup it loads the bundled CSVs into a
real in-memory SQLite database and serves it via SQL queries.

Tables loaded (standard SAP table names, kept as-is for authenticity):
    LFA1  -- Vendor master
    EKKO  -- Purchase order header
    EKPO  -- Purchase order line items
    MKPF  -- Goods movement (material document) header
    MSEG  -- Goods movement line items
    BKPF  -- Accounting document header
    BSEG  -- Accounting document line items (the actual invoice postings)
    SKAT  -- G/L account master

Endpoints:
    GET /health
    GET /vendors/search?name=xxx
    GET /vendors/{lifnr}
    GET /vendors/{lifnr}/purchase-orders
    GET /vendors/{lifnr}/invoices
    GET /vendors/{lifnr}/summary
    GET /purchase-orders/{ebeln}
    GET /purchase-orders/{ebeln}/goods-receipts
"""
from __future__ import annotations

import csv
import os
import sqlite3

from fastapi import FastAPI, HTTPException

app = FastAPI(title="SAP AP/Procurement Service")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

SCHEMAS = {
    "LFA1": "LIFNR TEXT PRIMARY KEY, NAME1 TEXT, LAND1 TEXT, ORT01 TEXT, STRAS TEXT, KTOKK TEXT, ERDAT TEXT",
    "EKKO": "EBELN TEXT, BUKRS TEXT, BSART TEXT, LIFNR TEXT, EKORG TEXT, EKGRP TEXT, BEDAT TEXT, WAERS TEXT, ZTERM TEXT",
    "EKPO": "EBELN TEXT, EBELP TEXT, MATNR TEXT, TXZ01 TEXT, WERKS TEXT, MATKL TEXT, MENGE REAL, MEINS TEXT, NETPR REAL, PEINH REAL, NETWR REAL",
    "MKPF": "MBLNR TEXT, MJAHR TEXT, BLDAT TEXT, BUDAT TEXT",
    "MSEG": "MBLNR TEXT, MJAHR TEXT, ZEILE TEXT, BWART TEXT, MATNR TEXT, MENGE REAL, MEINS TEXT, WERKS TEXT, LIFNR TEXT, EBELN TEXT, EBELP TEXT",
    "BKPF": "BUKRS TEXT, BELNR TEXT, GJAHR TEXT, BLART TEXT, BLDAT TEXT, BUDAT TEXT, WAERS TEXT, XBLNR TEXT",
    "BSEG": "BUKRS TEXT, BELNR TEXT, GJAHR TEXT, BUZEI TEXT, BSCHL TEXT, HKONT TEXT, LIFNR TEXT, DMBTR REAL, WRBTR REAL, SHKZG TEXT, ZFBDT TEXT, AUGDT TEXT",
    "SKAT": "SAKNR TEXT PRIMARY KEY, KTOPL TEXT, SPRAS TEXT, TXT50 TEXT",
}

_db = None


def get_db():
    """In-memory SQLite, loaded once per app process (fast: <6000 rows total)."""
    global _db
    if _db is not None:
        return _db

    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    for table, schema in SCHEMAS.items():
        cur.execute(f"CREATE TABLE {table} ({schema})")
        csv_path = os.path.join(DATA_DIR, f"{table}.csv")
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            placeholders = ",".join("?" for _ in cols)
            rows = [tuple(row[c] for c in cols) for row in reader]
            cur.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})", rows)

    con.commit()
    _db = con
    return _db


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


@app.get("/health")
def health():
    db = get_db()
    counts = {}
    for table in SCHEMAS:
        counts[table] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return {"status": "ok", "source": "SAP_BTP_AP", "row_counts": counts}


@app.get("/vendors/search")
def search_vendors(name: str):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM LFA1 WHERE NAME1 LIKE ? LIMIT 20", (f"%{name}%",)
    ).fetchall()
    return {"vendors": rows_to_dicts(rows)}


@app.get("/vendors/{lifnr}")
def get_vendor(lifnr: str):
    db = get_db()
    row = db.execute("SELECT * FROM LFA1 WHERE LIFNR = ?", (lifnr,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="VENDOR_NOT_FOUND")
    return dict(row)


@app.get("/vendors/{lifnr}/purchase-orders")
def vendor_purchase_orders(lifnr: str):
    db = get_db()
    pos = db.execute("SELECT * FROM EKKO WHERE LIFNR = ?", (lifnr,)).fetchall()
    result = []
    for po in pos:
        items = db.execute("SELECT * FROM EKPO WHERE EBELN = ?", (po["EBELN"],)).fetchall()
        result.append({**dict(po), "items": rows_to_dicts(items)})
    return {"purchase_orders": result, "count": len(result)}


@app.get("/purchase-orders/{ebeln}")
def get_purchase_order(ebeln: str):
    db = get_db()
    po = db.execute("SELECT * FROM EKKO WHERE EBELN = ?", (ebeln,)).fetchone()
    if not po:
        raise HTTPException(status_code=404, detail="PO_NOT_FOUND")
    items = db.execute("SELECT * FROM EKPO WHERE EBELN = ?", (ebeln,)).fetchall()
    return {**dict(po), "items": rows_to_dicts(items)}


@app.get("/purchase-orders/{ebeln}/goods-receipts")
def po_goods_receipts(ebeln: str):
    db = get_db()
    rows = db.execute(
        "SELECT m.*, h.BLDAT as doc_date FROM MSEG m JOIN MKPF h ON m.MBLNR = h.MBLNR AND m.MJAHR = h.MJAHR "
        "WHERE m.EBELN = ?", (ebeln,)
    ).fetchall()
    return {"goods_receipts": rows_to_dicts(rows), "count": len(rows)}


@app.get("/vendors/{lifnr}/invoices")
def vendor_invoices(lifnr: str):
    db = get_db()
    rows = db.execute(
        "SELECT b.*, h.BLDAT, h.BUDAT, h.WAERS, h.XBLNR FROM BSEG b "
        "JOIN BKPF h ON b.BUKRS=h.BUKRS AND b.BELNR=h.BELNR AND b.GJAHR=h.GJAHR "
        "WHERE b.LIFNR = ?", (lifnr,)
    ).fetchall()
    return {"invoices": rows_to_dicts(rows), "count": len(rows)}


@app.get("/vendors/{lifnr}/summary")
def vendor_summary(lifnr: str):
    db = get_db()
    vendor = db.execute("SELECT * FROM LFA1 WHERE LIFNR = ?", (lifnr,)).fetchone()
    if not vendor:
        raise HTTPException(status_code=404, detail="VENDOR_NOT_FOUND")

    po_count = db.execute("SELECT COUNT(*) FROM EKKO WHERE LIFNR = ?", (lifnr,)).fetchone()[0]
    po_value = db.execute(
        "SELECT COALESCE(SUM(p.NETWR),0) FROM EKPO p JOIN EKKO k ON p.EBELN=k.EBELN WHERE k.LIFNR = ?", (lifnr,)
    ).fetchone()[0]
    invoice_total = db.execute(
        "SELECT COALESCE(SUM(DMBTR),0) FROM BSEG WHERE LIFNR = ? AND SHKZG='H'", (lifnr,)
    ).fetchone()[0]
    total_items = db.execute("SELECT COUNT(*) FROM BSEG WHERE LIFNR = ?", (lifnr,)).fetchone()[0]
    open_items = db.execute(
        "SELECT COUNT(*) FROM BSEG WHERE LIFNR = ? AND (AUGDT IS NULL OR AUGDT = '')", (lifnr,)
    ).fetchone()[0]

    return {
        "vendor": dict(vendor),
        "purchase_order_count": po_count,
        "total_po_value": round(po_value, 2),
        "total_invoiced": round(invoice_total, 2),
        "total_invoice_items": total_items,
        "open_items": open_items,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
