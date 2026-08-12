# Exemplo de Repository — substitua pelo seu domínio
#
# from sqlalchemy.orm import Session
# from app.models.user import User
#
#
# class UserRepository:
#     def __init__(self, db: Session):
#         self.db = db
#
#     def get_all(self) -> list[User]:
#         return self.db.query(User).all()
#
#     def get_by_id(self, user_id: int) -> User | None:
#         return self.db.query(User).filter(User.id == user_id).first()
#
#     def create(self, user: User) -> User:
#         self.db.add(user)
#         self.db.commit()
#         self.db.refresh(user)
#         return user
#
#     def update(self, user: User, data: dict) -> User:
#         for key, value in data.items():
#             if value is not None:
#                 setattr(user, key, value)
#         self.db.commit()
#         self.db.refresh(user)
#         return user
#
#     def delete(self, user: User) -> None:
#         self.db.delete(user)
#         self.db.commit()
