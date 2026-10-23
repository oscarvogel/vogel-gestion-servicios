import os, sys, traceback
sys.path.insert(0, r"C:\Programacion\vogel-gestion\backend")
os.environ["DATABASE_URL"] = "mysql+pymysql://vogel:change_me@localhost:3307/vogel_gestion_servicios"

from app.db.session import SessionLocal
from app.models.work_order import WorkOrder
from app.models.customer import Customer, Equipment

from app.api.v1.work_orders import _read, _tecnicos_de_varias

db = SessionLocal()
company_id = 3
q = (db.query(WorkOrder)
     .join(Customer, Customer.id == WorkOrder.customer_id)
     .join(Equipment, Equipment.id == WorkOrder.equipment_id)
     .filter(WorkOrder.company_id == company_id))
total = q.count()
print("total con los joins:", total)
rows = q.order_by(WorkOrder.received_at.desc(), WorkOrder.id.desc()).offset(0).limit(25).all()
print("filas de la pagina:", len(rows))

mapa = _tecnicos_de_varias(db, [r.id for r in rows])
print("tecnicos por ot:", {k: len(v) for k, v in mapa.items()})

fallos = 0
for r in rows:
    try:
        _read(db, r, mapa.get(r.id, []))
    except Exception as exc:
        fallos += 1
        if fallos <= 3:
            print("FALLA en la OT", r.id, "->", type(exc).__name__, exc)
            print("   customer_id:", r.customer_id, "equipment_id:", r.equipment_id)
print("fallos:", fallos, "de", len(rows))

# Las tres consultas que hace _read, sin el wrap:
for r in rows[:3]:
    try:
        customer = db.query(Customer).filter_by(id=r.customer_id, company_id=r.company_id).one()
    except Exception as exc:
        print("cliente falla para la OT", r.id, "customer_id", r.customer_id, type(exc).__name__)
    try:
        equipment = db.query(Equipment).filter_by(id=r.equipment_id, company_id=r.company_id).one()
    except Exception as exc:
        print("equipo falla para la OT", r.id, "equipment_id", r.equipment_id, type(exc).__name__)
