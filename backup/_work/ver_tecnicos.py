import os, sys
sys.path.insert(0, r"C:\Programacion\vogel-gestion\backend")
os.environ["DATABASE_URL"] = "mysql+pymysql://vogel:change_me@localhost:3307/vogel_gestion_servicios"
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as c:
    print("-- técnicos por empresa y estado --")
    for fila in c.execute(text("SELECT company_id, active, COUNT(*) FROM technicians GROUP BY company_id, active ORDER BY company_id")):
        print("   ", fila)
    print("-- muestra de nombres (company 3) --")
    for fila in c.execute(text("SELECT id, name, active, legacy_code FROM technicians WHERE company_id=3 ORDER BY id LIMIT 8")):
        print("   ", fila)
    print("-- total por empresa --")
    for fila in c.execute(text("SELECT company_id, COUNT(*) FROM technicians GROUP BY company_id")):
        print("   ", fila)
