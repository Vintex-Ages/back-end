# Exemplo de Schema (DTO) — substitua pelo seu domínio
#
# from datetime import datetime
# from pydantic import BaseModel, EmailStr
#
#
# class UserCreate(BaseModel):
#     name: str
#     email: EmailStr
#     password: str
#
#
# class UserResponse(BaseModel):
#     id: int
#     name: str
#     email: str
#     created_at: datetime
#     updated_at: datetime
#
#     model_config = {"from_attributes": True}
#
#
# class UserUpdate(BaseModel):
#     name: str | None = None
#     email: EmailStr | None = None
