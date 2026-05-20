import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, DataError

from app.database import engine, get_db, Base
from app.models import User, Book, Loan
from app.schemas import UserCreate, UserLogin, UserResponse, BookCreate, BookResponse, LoanCreate, LoanResponse, UserUpdateRole
from app.auth import get_password_hash, verify_password, create_access_token, get_current_active_user, require_role, get_current_user

# Создание таблиц
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Library Management System")

# Шаблоны и статика
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Создание админа при старте
def create_default_admin():
    db = next(get_db())
    if not db.query(User).filter(User.username == "admin").first():
        admin = User(
            username="admin",
            email="admin@library.com",
            hashed_password=get_password_hash("admin123"),
            role="admin",
            is_active=True
        )
        db.add(admin)
        db.commit()

@app.on_event("startup")
def startup_event():
    create_default_admin()

# ==================== API ROUTES ====================

# Auth
@app.post("/api/v1/auth/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    # Проверка на существующего пользователя (дубликат)
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Логин уже занят")
    
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        role="reader"
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError:
        db.rollback()
        # Если база данных отклонила запись (дубликат, нарушение уникальности)
        raise HTTPException(status_code=400, detail="Невалидные данные пользователя")
    except DataError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Данные слишком длинные")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ошибка сервера базы данных")

@app.post("/api/v1/auth/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")
    if not db_user.is_active:
        raise HTTPException(status_code=400, detail="Пользователь неактивен")
    
    access_token = create_access_token(data={"sub": db_user.username})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": db_user.id,
            "username": db_user.username,
            "role": db_user.role
        }
    }

@app.get("/api/v1/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user

# Books
@app.get("/api/v1/books", response_model=list[BookResponse])
def get_books(q: str = None, db: Session = Depends(get_db)):
    query = db.query(Book)
    if q:
        query = query.filter(
            or_(
                Book.title.ilike(f"%{q}%"),
                Book.author.ilike(f"%{q}%")
            )
        )
    return query.all()

@app.get("/api/v1/books/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")
    return book

@app.post("/api/v1/books", response_model=BookResponse)
def create_book(book: BookCreate, current_user: User = Depends(require_role("librarian", "admin")), db: Session = Depends(get_db)):
    if db.query(Book).filter(Book.isbn == book.isbn).first():
        raise HTTPException(status_code=400, detail="ISBN уже существует")
    
    db_book = Book(
        isbn=book.isbn,
        title=book.title,
        author=book.author,
        year=book.year,
        total_copies=book.total_copies,
        available_copies=book.total_copies
    )
    db.add(db_book)
    db.commit()
    db.refresh(db_book)
    return db_book

@app.delete("/api/v1/books/{book_id}")
def delete_book(book_id: int, current_user: User = Depends(require_role("librarian", "admin")), db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")
    
    active_loans = db.query(Loan).filter(Loan.book_id == book_id, Loan.status == "active").first()
    if active_loans:
        raise HTTPException(status_code=400, detail="Невозможно удалить книгу с активными выдачами")
    
    db.delete(book)
    db.commit()
    return {"message": "Книга удалена"}

# Loans
@app.get("/api/v1/loans/my", response_model=list[LoanResponse])
def get_my_loans(current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    loans = db.query(Loan).filter(Loan.user_id == current_user.id).all()
    result = []
    for loan in loans:
        book = db.query(Book).filter(Book.id == loan.book_id).first()
        result.append(LoanResponse(
            id=loan.id,
            user_id=loan.user_id,
            user_username=current_user.username,
            book_id=loan.book_id,
            book_title=book.title if book else "Unknown",
            book_author=book.author if book else "Unknown",
            loan_date=loan.loan_date,
            due_date=loan.due_date,
            return_date=loan.return_date,
            status=loan.status
        ))
    return result

@app.get("/api/v1/loans/all", response_model=list[LoanResponse])
def get_all_loans(current_user: User = Depends(require_role("librarian", "admin")), db: Session = Depends(get_db)):
    loans = db.query(Loan).all()
    result = []
    for loan in loans:
        book = db.query(Book).filter(Book.id == loan.book_id).first()
        user_obj = db.query(User).filter(User.id == loan.user_id).first()
        result.append(LoanResponse(
            id=loan.id,
            user_id=loan.user_id,
            user_username=user_obj.username if user_obj else "Unknown",
            book_id=loan.book_id,
            book_title=book.title if book else "Unknown",
            book_author=book.author if book else "Unknown",
            loan_date=loan.loan_date,
            due_date=loan.due_date,
            return_date=loan.return_date,
            status=loan.status
        ))
    return result

@app.post("/api/v1/loans", response_model=LoanResponse)
def create_loan(loan: LoanCreate, current_user: User = Depends(require_role("reader", "librarian", "admin")), db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == loan.book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Книга не найдена")
    if book.available_copies <= 0:
        raise HTTPException(status_code=400, detail="Нет доступных копий")
    
    existing_loan = db.query(Loan).filter(
        Loan.user_id == current_user.id,
        Loan.book_id == loan.book_id,
        Loan.status == "active"
    ).first()
    if existing_loan:
        raise HTTPException(status_code=400, detail="Вы уже взяли эту книгу")
    
    db_loan = Loan(
        user_id=current_user.id,
        book_id=loan.book_id,
        due_date=datetime.utcnow() + timedelta(days=14)
    )
    book.available_copies -= 1
    
    db.add(db_loan)
    db.commit()
    db.refresh(db_loan)
    
    book_db = db.query(Book).filter(Book.id == loan.book_id).first()
    return LoanResponse(
        id=db_loan.id,
        user_id=current_user.id,
        user_username=current_user.username,
        book_id=db_loan.book_id,
        book_title=book_db.title,
        book_author=book_db.author,
        loan_date=db_loan.loan_date,
        due_date=db_loan.due_date,
        return_date=db_loan.return_date,
        status=db_loan.status
    )

@app.post("/api/v1/loans/{loan_id}/return", response_model=LoanResponse)
def return_loan(loan_id: int, current_user: User = Depends(require_role("librarian", "admin")), db: Session = Depends(get_db)):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Выдача не найдена")
    if loan.status == "returned":
        raise HTTPException(status_code=400, detail="Книга уже возвращена")
    
    loan.status = "returned"
    loan.return_date = datetime.utcnow()
    
    book = db.query(Book).filter(Book.id == loan.book_id).first()
    if book:
        book.available_copies += 1
    
    db.commit()
    db.refresh(loan)
    
    book_db = db.query(Book).filter(Book.id == loan.book_id).first()
    user_obj = db.query(User).filter(User.id == loan.user_id).first()
    
    return LoanResponse(
        id=loan.id,
        user_id=loan.user_id,
        user_username=user_obj.username if user_obj else "Unknown",
        book_id=loan.book_id,
        book_title=book_db.title if book_db else "Unknown",
        book_author=book_db.author if book_db else "Unknown",
        loan_date=loan.loan_date,
        due_date=loan.due_date,
        return_date=loan.return_date,
        status=loan.status
    )

# Admin
@app.get("/api/v1/admin/users", response_model=list[UserResponse])
def get_users(current_user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    return db.query(User).all()

@app.put("/api/v1/admin/users/{user_id}/role")
def update_user_role(user_id: int, role_data: UserUpdateRole, current_user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if role_data.role not in ["reader", "librarian", "admin"]:
        raise HTTPException(status_code=400, detail="Некорректная роль")
    
    user.role = role_data.role
    db.commit()
    return {"message": f"Роль пользователя {user.username} изменена на {role_data.role}"}

@app.delete("/api/v1/admin/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(require_role("admin")), db: Session = Depends(get_db)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Невозможно удалить себя")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    active_loans = db.query(Loan).filter(Loan.user_id == user_id, Loan.status == "active").first()
    if active_loans:
        raise HTTPException(status_code=400, detail="Невозможно удалить пользователя с активными выдачами")
    
    db.delete(user)
    db.commit()
    return {"message": "Пользователь удален"}

# ==================== FRONTEND ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get("/my-loans", response_class=HTMLResponse)
async def my_loans_page(request: Request):
    return templates.TemplateResponse("my_loans.html", {"request": request})

@app.get("/books/manage", response_class=HTMLResponse)
async def manage_books_page(request: Request):
    return templates.TemplateResponse("manage_books.html", {"request": request})

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    return templates.TemplateResponse("admin_users.html", {"request": request})