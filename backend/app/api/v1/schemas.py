from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ---------- Common ----------
class MessageResponse(BaseModel):
    detail: str


class PaginatedResponse(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class SelectCompanyRequest(BaseModel):
    company_id: int


class TokenBundle(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_superadmin: bool
    active: bool
    memberships: list["MembershipSummary"]
    permissions: list[str]


class MembershipSummary(BaseModel):
    company_id: int
    company_name: str
    company_slug: str | None
    company_active: bool
    is_admin: bool
    role: str
    active: bool


class CompanyOption(BaseModel):
    id: int
    name: str
    slug: str | None
    active: bool
    is_admin: bool


# ---------- Companies ----------
class CompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=30)
    slug: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=250)
    notes: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=16)


class CompanyCreate(CompanyBase):
    admin_email: EmailStr | None = None
    admin_full_name: str | None = None
    admin_password: str | None = Field(default=None, min_length=8, max_length=128)
    active: bool = True


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    legal_name: str | None = Field(default=None, max_length=200)
    tax_id: str | None = Field(default=None, max_length=30)
    slug: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=60)
    address: str | None = Field(default=None, max_length=250)
    notes: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=16)


class CompanyRead(CompanyBase):
    id: int
    active: bool
    timezone: str
    locale: str
    created_at: datetime
    updated_at: datetime
    user_count: int = 0


class CompanyDetail(CompanyRead):
    admin_count: int = 0
    member_count: int = 0
    is_active: bool


class CompanyListResponse(BaseModel):
    items: list[CompanyRead]
    total: int
    page: int
    page_size: int


# ---------- Users ----------
class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=150)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    is_superadmin: bool = False
    memberships: list["MembershipCreate"] = Field(default_factory=list)


class MembershipCreate(BaseModel):
    company_id: int
    role: Literal["ADMIN", "MEMBER"] = "MEMBER"
    is_admin: bool = False
    role_ids: list[int] = Field(default_factory=list)
    active: bool = True


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=150)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    active: bool | None = None


class UserRead(BaseModel):
    id: int
    # Lectura tolerante: la base puede contener usuarios legacy/seed creados
    # antes de validar EmailStr. Las altas y ediciones siguen validando EmailStr.
    email: str
    full_name: str
    active: bool
    is_superadmin: bool
    created_at: datetime


class UserDetail(UserRead):
    memberships: list[MembershipSummary]


class UserListResponse(BaseModel):
    items: list[UserDetail]
    total: int
    page: int
    page_size: int


class MembershipUpdate(BaseModel):
    role: Literal["ADMIN", "MEMBER"] | None = None
    is_admin: bool | None = None
    role_ids: list[int] | None = None
    active: bool | None = None


class MembershipRead(BaseModel):
    id: int
    user_id: int
    company_id: int
    role: str
    is_admin: bool
    active: bool
    role_ids: list[int] = Field(default_factory=list)


# ---------- Roles ----------
class PermissionRead(BaseModel):
    id: int
    code: str
    namespace: str
    description: str | None


class RoleBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    permission_ids: list[int] = Field(default_factory=list)
    active: bool = True


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    permission_ids: list[int] | None = None
    active: bool | None = None


class RoleRead(BaseModel):
    id: int
    company_id: int | None
    name: str
    description: str | None
    is_system: bool
    active: bool
    permission_codes: list[str] = Field(default_factory=list)


class RoleListResponse(BaseModel):
    items: list[RoleRead]


# Resolve forward refs
UserCreate.model_rebuild()
MeResponse.model_rebuild()