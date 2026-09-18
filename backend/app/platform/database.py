"""Local MVP persistence; DATABASE_URL may also point to PostgreSQL."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, String, Text, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / '.env')
DATABASE_URL = os.getenv('DATABASE_URL') or f'sqlite:///{ROOT / "backend" / "demo.db"}'
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(80))


class Session(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[int] = mapped_column(Integer)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(40))
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))


class Assignment(Base):
    __tablename__ = 'assignments'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(40))
    due_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default='published', server_default='published')


class Submission(Base):
    __tablename__ = 'submissions'
    id: Mapped[str] = mapped_column(String(90), primary_key=True)
    assignment_id: Mapped[str] = mapped_column(ForeignKey('assignments.id'))
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    answer: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')


class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str] = mapped_column(String(100))
    topic: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str] = mapped_column(Text, default='')
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class Review(Base):
    __tablename__ = 'reviews'
    __table_args__ = (UniqueConstraint('submission_id', 'version'),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    submission_id: Mapped[str] = mapped_column(ForeignKey('submissions.id'), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    version: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    answer_snapshot: Mapped[str] = mapped_column(Text)
    reviewed_at: Mapped[str] = mapped_column(String(40))


class SchemaMigration(Base):
    __tablename__ = 'schema_migrations'
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[str] = mapped_column(String(40))


def get_db():
    with SessionLocal() as db:
        yield db
