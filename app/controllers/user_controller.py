# Exemplo de Controller — substitua pelo seu domínio
#
# from fastapi import HTTPException, status
# from sqlalchemy.orm import Session
# from app.models.user import User
# from app.repositories.user_repository import UserRepository
# from app.schemas.user_schema import UserCreate, UserUpdate
#
#
# class UserController:
#     def __init__(self, db: Session):
#         self.repository = UserRepository(db)
#
#     def get_all(self) -> list[User]:
#         return self.repository.get_all()
#
#     def get_by_id(self, user_id: int) -> User:
#         user = self.repository.get_by_id(user_id)
#         if not user:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="Usuário não encontrado",
#             )
#         return user
#
#     def create(self, data: UserCreate) -> User:
#         user = User(
#             name=data.name,
#             email=data.email,
#             password_hash="hash_aqui",
#         )
#         return self.repository.create(user)
