from contextlib import asynccontextmanager
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .platform.database import Base, engine, SessionLocal, User, Assignment
from .platform.auth import router as auth_router, hash_password
from .ai.service import router as agent_router
from .teaching.routes import router as teaching_router
from migrations.upgrade import upgrade


def initialize_database():
    upgrade(engine, Base.metadata)
    with SessionLocal() as db:
        for role, name, password in [('student', '林同学', 'Student123!'), ('teacher', '陈老师', 'Teacher123!')]:
            if not db.get(User, role):
                db.add(User(id=role, username=role, role=role, name=name, password_hash=hash_password(password)))
        db.commit()
        if not db.get(Assignment, 'demo-limit'):
            db.add(Assignment(id='demo-limit', teacher_id='teacher', title='第一章 · 极限概念小练习',
                content='1. 用自己的话解释函数极限。\n2. 求 lim(x→0) sin(x)/x，并说明理由。\n3. 思考：函数在一点有极限，是否一定在该点有定义？',
                topic='函数与极限', due_date=(date.today() + timedelta(days=7)).isoformat(), created_at=datetime.now(timezone.utc).isoformat()))
            db.commit()


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield


app = FastAPI(title='数伴 · 教育智能体 MVP', version='0.2.0', lifespan=lifespan)


@app.middleware('http')
async def request_guard(request: Request, call_next):
    # A non-simple header plus no cross-origin CORS prevents browser cross-site mutations.
    if request.url.path.startswith('/api/') and request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if request.headers.get('X-Requested-With') != 'shuban-web':
            return JSONResponse({'detail': '请求来源校验失败，请从应用页面操作。'}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(teaching_router)


@app.get('/api/health')
def health():
    return {'status': 'ok', 'agent_mode': 'demo', 'version': '0.2.0'}


DIST = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
if DIST.is_dir():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
