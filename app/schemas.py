from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

class TokenData(BaseModel):
    username: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

    @field_validator('username')
    @classmethod
    def username_length(cls, v):
        if len(v) < 3:
            raise ValueError('Логин должен быть от 3 символов')
        return v

    @field_validator('password')
    @classmethod
    def password_length(cls, v):
        if len(v) <= 3:
            raise ValueError('Пароль должен быть больше 3 символов')
        return v

    @field_validator('email')
    @classmethod
    def email_valid(cls, v):
        if '@' not in v or '.' not in v:
            raise ValueError('Некорректный email')
        return v

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True

class UserUpdateRole(BaseModel):
    role: str

class BookCreate(BaseModel):
    isbn: str
    title: str
    author: str
    year: int
    total_copies: int = 1

    @field_validator('isbn')
    @classmethod
    def isbn_length(cls, v):
        if len(v) < 10 or len(v) > 13:
            raise ValueError('ISBN должен быть 10-13 символов')
        return v

    @field_validator('year')
    @classmethod
    def year_valid(cls, v):
        if v < 1000 or v > 2026:
            raise ValueError('Некорректный год')
        return v

    @field_validator('total_copies')
    @classmethod
    def copies_positive(cls, v):
        if v <= 0:
            raise ValueError('Количество должно быть > 0')
        return v

class BookResponse(BaseModel):
    id: int
    isbn: str
    title: str
    author: str
    year: int
    total_copies: int
    available_copies: int

    class Config:
        from_attributes = True

class LoanCreate(BaseModel):
    book_id: int

class LoanResponse(BaseModel):
    id: int
    user_id: int
    user_username: Optional[str] = None
    book_id: int
    book_title: Optional[str] = None
    book_author: Optional[str] = None
    loan_date: datetime
    due_date: datetime
    return_date: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True