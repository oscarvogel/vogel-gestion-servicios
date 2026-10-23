import os, sys
sys.path.insert(0, r"C:\Programacion\vogel-gestion\backend")
# La base de staging (IP privada de la LAN: el firewall publico no deja el 33061).
# La URL con la password llega por variable de entorno: al repo no llega ninguna.
os.environ["DATABASE_URL"] = os.environ.get(
    "STAGING_DATABASE_URL",
    "mysql+pymysql://vogelapp:<password>@192.168.0.189:33061/vogel_gestion_servicios",
)
if "<password>" in os.environ["DATABASE_URL"]:
    raise SystemExit("Falta STAGING_DATABASE_URL (mysql+pymysql://usuario:password@host:puerto/base)")

from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.work_order import WorkOrder
from app.models.customer import Customer, Equipment
from app.api.v1.work_orders import _read, _tecnicos_de_varias

db = SessionLocal()
company_id = 3

print("-- conteos --")
for tabla in ("work_orders", "customers", "equipment", "technicians"):
    print("   ", tabla, db.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar())

print("-- work_orders por company_id --")
for f in db.execute(text("SELECT company_id, COUNT(*) FROM work_orders GROUP BY company_id")):
    print("   ", tuple(f))

print("-- equipment por company_id --")
for f in db.execute(text("SELECT company_id, COUNT(*) FROM equipment GROUP BY company_id")):
    print("   ", tuple(f))

q = (db.query(WorkOrder)
     .join(Customer, Customer.id == WorkOrder.customer_id)
     .join(Equipment, Equipment.id == WorkOrder.equipment_id)
     .filter(WorkOrder.company_id == company_id))
print("total con los joins:", q.count())
rows = q.order_by(WorkOrder.received_at.desc(), WorkOrder.id.desc()).offset(0).limit(25).all()
print("filas:", len(rows))

mapa = _tecnicos_de_varias(db, [r.id for r in rows])
fallos = 0
for r in rows:
    try:
        _read(db, r, mapa.get(r.id, []))
    except Exception as exc:
        fallos += 1
        if fallos <= 3:
            print("FALLA OT", r.id, type(exc).__name__, exc)
            for etiqueta, sql in (
                ("cliente", f"SELECT COUNT(*) FROM customers WHERE id={r.customer_id} AND company_id={r.company_id}"),
                ("equipo", f"SELECT COUNT(*) FROM equipment WHERE id={r.equipment_id} AND company_id={r.company_id}"),
                ("categoria", "SELECT COUNT(*) FROM equipment_categories WHERE id=(SELECT category_id FROM equipment WHERE id=" + str(r.equipment_id) + f") AND company_id={r.company_id}"),
            ):
                print("    ", etiqueta, db.execute(text(sql)).scalar())
print("fallos:", fallos, "de", len(rows))
