from fastapi import Depends,Header,HTTPException
from jose import JWTError,jwt
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import ALGORITHM
from app.db.session import SessionLocal
from app.models.user import User,CompanyUser
def get_db():
    db=SessionLocal()
    try:yield db
    finally:db.close()
def get_current_user(authorization:str=Header(default=""),db:Session=Depends(get_db))->User:
    if not authorization.startswith("Bearer "):raise HTTPException(401,"Missing bearer token")
    try:
        p=jwt.decode(authorization[7:],settings.jwt_secret,algorithms=[ALGORITHM]); uid=int(p["sub"])
        if p.get("type")!="access":raise ValueError()
    except (JWTError,ValueError,KeyError):raise HTTPException(401,"Invalid token")
    u=db.get(User,uid)
    if not u or not u.active:raise HTTPException(401,"Inactive user")
    return u
def get_current_company_id(authorization:str=Header(default=""),user:User=Depends(get_current_user),db:Session=Depends(get_db))->int:
    try:p=jwt.decode(authorization[7:],settings.jwt_secret,algorithms=[ALGORITHM]); cid=int(p["company_id"])
    except (JWTError,ValueError,KeyError):raise HTTPException(409,"Active company required")
    if user.is_superadmin:return cid
    if not db.query(CompanyUser).filter_by(user_id=user.id,company_id=cid,active=True).first():raise HTTPException(403,"Company access denied")
    return cid
