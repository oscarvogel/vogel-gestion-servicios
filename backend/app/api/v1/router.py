from fastapi import APIRouter

from app.api.v1 import auth, companies, company_parameters, customers, dashboard, roles, users, work_orders, work_order_quotes

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(companies.router, prefix="/companies", tags=["companies"])
router.include_router(company_parameters.router, prefix="/company-parameters", tags=["company-parameters"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(roles.router, prefix="/roles", tags=["roles"])
router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
router.include_router(customers.router, prefix="/customers", tags=["customers"])
router.include_router(work_orders.router, prefix="/work-orders", tags=["work-orders"])
router.include_router(work_order_quotes.router, prefix="/work-orders", tags=["work-order-quotes"])
