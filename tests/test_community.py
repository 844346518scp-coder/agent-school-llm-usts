from tests.test_teacher_workspace import workspace, PASSWORD
from sqlalchemy import select, inspect, text
from backend.app.platform.database import User, Classroom, ClassMember
from backend.app.teaching.community import CommunityBase, ClassCode
from migrations.community import upgrade_community


def setup_teacher(c, username='teacherone'):
    r=c.post('/api/auth/setup',json={'username':username,'name':'测试老师','password':PASSWORD})
    assert r.status_code==201
    return r.json()

def classroom(c):
    r=c.post('/api/classes',json={'name':'测试班','course':'高数','term':'2026'})
    assert r.status_code==201
    assert len(r.json()['join_code'])==6 and r.json()['join_code'].isdigit()
    return r.json()

def register(c, name='learner', code=''):
    return c.post('/api/auth/register/student',json={'username':name,'name':'测试同学','password':PASSWORD,'class_code':code})

def test_register_join_code_and_assignment_snapshot(workspace):
    t,s=workspace.client(),workspace.client()
    setup_teacher(t); cl=classroom(t)
    assert register(s,code='bad').status_code==404
    with workspace.sessions() as db:
        assert db.scalar(select(User).where(User.username=='learner')) is None
    student=register(s,code=cl['join_code'].lower()).json()
    assert student['role']=='student' and not student['must_change_password']
    assert register(s).status_code==409
    assert len(s.get('/api/student/classes').json())==1
    assert s.post('/api/student/classes/join',json={'code':cl['join_code']}).status_code==200
    assert t.get('/api/classes/'+cl['id']+'/students').json()[0]['manageable'] is False
    assert t.post('/api/students/'+student['id']+'/password',json={'password':'ResetPassword123!'}).status_code==404
    a=t.post('/api/assignments/drafts',json={'title':'新作业','content':'求导','topic':'导数','due_date':'2099-01-01','class_id':cl['id']}).json()
    assert t.post('/api/assignments/'+a['id']+'/publish').status_code==200
    assert s.put('/api/assignments/'+a['id']+'/submission',json={'answer':'2x'}).status_code==200
    late=workspace.client(); assert register(late,name='latelearner',code=cl['join_code']).status_code==201
    assert late.get('/api/assignments').json()==[]
    new=t.post('/api/classes/'+cl['id']+'/join-code').json()['code'];assert new!=cl['join_code']
    assert late.post('/api/student/classes/join',json={'code':cl['join_code']}).status_code==404
    t.patch('/api/classes/'+cl['id']+'/members/'+student['id'],json={'active':False})
    assert s.post('/api/student/classes/join',json={'code':new}).status_code==403
    t.patch('/api/classes/'+cl['id'],json={'archived':True})
    assert late.post('/api/student/classes/join',json={'code':new}).status_code==404
    s.post('/api/auth/logout')
    assert s.post('/api/auth/login',json={'username':'learner','password':PASSWORD,'role':'student','remember':True}).status_code==200

def test_mail_permissions_unread_idempotency_and_history(workspace):
    t,s,other=workspace.client(),workspace.client(),workspace.client()
    teacher=setup_teacher(t);cl=classroom(t)
    student=register(s,code=cl['join_code']).json();register(other,name='outsider')
    msg={'recipient_id':teacher['id'],'content':'老师好，想请教一道题。','client_id':'request-one'}
    first=s.post('/api/mail/messages',json=msg);assert first.status_code==201
    assert s.post('/api/mail/messages',json=msg).json()['id']==first.json()['id']
    assert other.post('/api/mail/messages',json=msg).status_code==403
    assert other.get('/api/mail/messages/'+student['id']).json()==[]
    assert t.get('/api/mail/contacts').json()[0]['unread']==1
    mail=t.get('/api/mail/messages/'+student['id']).json();assert mail[0]['content']==msg['content']
    assert t.post('/api/mail/messages/'+student['id']+'/read',json={'through_id':mail[-1]['id']}).status_code==200
    assert t.get('/api/mail/contacts').json()[0]['unread']==0
    assert t.post('/api/mail/messages',json={'recipient_id':student['id'],'content':'可以，请描述思路。','client_id':'reply-one'}).status_code==201
    workspace.restart();assert len(s.get('/api/mail/messages/'+teacher['id']).json())==2
    t.patch('/api/classes/'+cl['id']+'/members/'+student['id'],json={'active':False})
    assert s.post('/api/mail/messages',json={**msg,'client_id':'request-two'}).status_code==403
    assert len(s.get('/api/mail/messages/'+teacher['id']).json())==2
    assert s.get('/api/mail/contacts').json()[0]['can_send'] is False

def test_community_migration_idempotent_and_preserves_platform(workspace):
    t=workspace.client();setup_teacher(t);cl=classroom(t)
    with workspace.engine.connect() as conn:
        before=conn.execute(text('SELECT * FROM classrooms')).fetchall()
    assert upgrade_community(workspace.engine,CommunityBase.metadata) is None
    workspace.restart()
    with workspace.engine.connect() as conn:
        assert before==conn.execute(text('SELECT * FROM classrooms')).fetchall()
        assert conn.scalar(text('SELECT MAX(version) FROM schema_migrations'))==3
    assert t.get('/api/classes').json()[0]['join_code']==cl['join_code']
