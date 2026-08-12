# Exemplo de Model — substitua pelo seu domínio
#
# from sqlalchemy import String
# from sqlalchemy.orm import Mapped, mapped_column
# from app.models.base_model import BaseModel
#
#
# class User(BaseModel):
#     __tablename__ = "users"
#
#     name: Mapped[str] = mapped_column(String(255), nullable=False)
#     email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
#     password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
