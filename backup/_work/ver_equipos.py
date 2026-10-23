import os, sys
sys.path.insert(0, r"C:\Programacion\vogel-gestion\backend")
os.environ["DATABASE_URL"] = "mysql+pymysql://vogel:change_me@localhost:3307/vogel_gestion_servicios"
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as c:
    print("-- work_orders por company_id --")
    for f in c.execute(text("SELECT company_id, COUNT(*) FROM work_orders GROUP BY company_id")):
        print("   ", f)
    print("-- equipment por company_id --")
    for f in c.execute(text("SELECT company_id, COUNT(*) FROM equipment GROUP BY company_id")):
        print("   ", f)
    print("-- customers por company_id --")
    for f in c.execute(text("SELECT company_id, COUNT(*) FROM customers GROUP BY company_id")):
        print("   ", f)
    print("-- OTs cuyo equipo NO existe --")
    q = """
    SELECT COUNT(*) FROM work_orders o
    LEFT JOIN equipment e ON e.id = o.equipment_id
    WHERE e.id IS NULL
    """
    print("   equipo inexistente:", c.execute(text(q)).scalar())
    print("-- OTs cuyo equipo existe pero de otra empresa --")
    q2 = """
    SELECT COUNT(*) FROM work_orders o
    JOIN equipment e ON e.id = o.equipment_id
    WHERE e.company_id <> o.company_id
    """
    print("   equipo de otra empresa:", c.execute(text(q2)).scalar())
    print("-- sample de OTs --")
    for f in c.execute(text("SELECT o.id, o.company_id, o.customer_id, o.equipment_id, e.company_id FROM work_orders o LEFT JOIN equipment e ON e.id=o.equipment_id LIMIT 5")):
        print("   ", f)
