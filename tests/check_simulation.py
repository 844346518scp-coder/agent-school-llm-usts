"""HTTP simulation against an explicitly marked, disposable local QA server.

Start the server with an isolated DATABASE_URL, AGENT_MODE=demo,
SHUBAN_SEED_DEMO=true and SHUBAN_INSTANCE_ID=simulation-<unique-id>.
This script refuses unmarked/remote servers. It never imports the application
or reads model secrets. It creates synthetic data and keeps it for browser QA.
"""
import argparse
from contextlib import ExitStack
from datetime import date, timedelta
import json
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx


HEADERS = {'X-Requested-With': 'shuban-web'}
TEMP_PASSWORD = 'SimulationTemp123!'
CHANGED_PASSWORD = 'SimulationChanged456!'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expect-instance', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    url = urlparse(args.base_url)
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost') or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        parser.error('Only a local HTTP origin is allowed.')
    if not args.expect_instance.startswith('simulation-'):
        parser.error('A simulation-* instance marker is required.')
    root = Path(__file__).resolve().parents[1]
    report_path = args.report.resolve()
    if report_path.parent != (root / '.tmp').resolve() or report_path.exists():
        parser.error('Report must be a new file directly inside the ignored .tmp directory.')
    checks = []
    marker = uuid4().hex[:8]

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
        print('PASS ' + name, flush=True)

    def request(client, method, path, body=None, expected=200):
        result = client.request(method, '/api' + path, json=body)
        # Do not dump response bodies: this runner also checks privacy boundaries.
        if result.status_code != expected:
            raise AssertionError(f'{method} {path}: expected {expected}, got {result.status_code}')
        return result.json()

    def login(client, username, password, role):
        return request(client, 'POST', '/auth/login', dict(username=username, password=password, role=role))

    with ExitStack() as stack:
        def client():
            return stack.enter_context(httpx.Client(base_url=args.base_url, headers=HEADERS, timeout=30, trust_env=False))

        teacher, student, second, newcomer = client(), client(), client(), client()
        health = request(teacher, 'GET', '/health')
        check('isolated_instance_and_demo_mode', health.get('instance_id') == args.expect_instance and health['agent_mode'] == 'demo')
        login(teacher, 'teacher', 'Teacher123!', 'teacher')
        login(student, 'student', 'Student123!', 'student')
        other = request(teacher, 'POST', '/auth/teachers', dict(username='sim.teacher.' + marker, name='隔离验收教师乙', password=TEMP_PASSWORD), 201)
        login(second, other['username'], TEMP_PASSWORD, 'teacher')
        request(second, 'GET', '/classes', expected=403)
        request(second, 'POST', '/auth/password', dict(current_password=TEMP_PASSWORD, new_password=CHANGED_PASSWORD))
        check('temporary_teacher_password_gate', True)
        classroom = request(teacher, 'POST', '/classes', dict(name='模拟联动班-' + marker, course='高等数学', term='合成测试'), 201)
        cpath = '/classes/' + classroom['id']
        request(teacher, 'POST', cpath + '/members', {'username': 'student'}, 201)
        private_class = request(second, 'POST', '/classes', dict(name='教师乙隔离班-' + marker, course='高等数学', term='合成测试'), 201)
        request(second, 'GET', cpath + '/students', expected=404)
        request(teacher, 'GET', '/classes/' + private_class['id'] + '/students', expected=404)
        check('two_teacher_class_isolation', True)
        question = request(teacher, 'POST', '/questions', dict(title='模拟测试·导数定义', topic='导数与微分', content='用定义求 $f(x)=x^2$ 在 $x=2$ 处的导数，并说明切线斜率。', reference_answer='PRIVATE_SIMULATION_REFERENCE: 导数与切线斜率均为4。'), 201)
        check('question_bank_private', question['id'] not in [q['id'] for q in request(second, 'GET', '/questions')])
        assignment = request(teacher, 'POST', '/assignments/drafts', dict(title='师生联动验收-' + marker, topic='导数与微分', content='请写出差商和极限过程。', question_ids=[question['id']], due_date=(date.today() + timedelta(days=7)).isoformat(), class_id=classroom['id']), 201)
        apath = '/assignments/' + assignment['id']
        check('student_cannot_read_drafts', assignment['id'] not in [a['id'] for a in request(student, 'GET', '/assignments')])
        request(teacher, 'POST', apath + '/publish')
        shown = next(a for a in request(student, 'GET', '/assignments') if a['id'] == assignment['id'])
        check('published_assignment_visible_without_private_answer', shown['recipient_count'] == 1 and shown['can_submit'] and 'PRIVATE_SIMULATION_REFERENCE' not in json.dumps(shown))
        request(second, 'PATCH', apath, {'due_date': shown['due_date']}, expected=404)
        request(second, 'GET', '/teaching/stats?class_id=' + classroom['id'], expected=404)
        check('assignment_and_stats_owner_isolation', True)
        saved = request(student, 'PUT', apath + '/submission', {'answer': '第一次：把函数值4当作导数，尚未写差商。'})
        check('submission_version_one', saved['submission']['version'] == 1)
        request(teacher, 'PUT', apath + '/submissions/student/review', dict(version=1, comment='结果虽为4，但请补充差商 ((2+h)^2-4)/h=4+h，再令h趋于0。', status='needs_improvement'))
        feedback = next(a for a in request(student, 'GET', '/assignments') if a['id'] == assignment['id'])
        check('student_receives_teacher_feedback', feedback['submission']['review']['status'] == 'needs_improvement')
        saved = request(student, 'PUT', apath + '/submission', {'answer': '差商为 ((2+h)^2-4)/h=4+h，令h趋于0得4，因此切线斜率为4。'})
        check('revision_preserves_old_feedback_and_requires_review', saved['submission']['version'] == 2 and saved['submission']['review'] is None and len(saved['submission']['review_history']) == 1)
        request(teacher, 'PUT', apath + '/submissions/student/review', dict(version=1, comment='过期反馈', status='completed'), expected=409)
        request(teacher, 'PUT', apath + '/submissions/student/review', dict(version=2, comment='差商、极限和切线解释完整，教师确认完成。', status='completed'))
        stats = request(teacher, 'GET', '/teaching/stats?class_id=' + classroom['id'])
        check('teacher_stats_match_reviewed_submission', stats['expected'] == 1 and stats['submitted'] == 1 and stats['completed'] == 1 and stats['pending'] == 0)
        added = request(teacher, 'POST', cpath + '/students', dict(username='sim.student.' + marker, name='隔离验收后加学生', password=TEMP_PASSWORD), 201)
        login(newcomer, added['username'], TEMP_PASSWORD, 'student')
        request(newcomer, 'GET', '/assignments', expected=403)
        request(newcomer, 'POST', '/auth/password', dict(current_password=TEMP_PASSWORD, new_password=CHANGED_PASSWORD))
        check('late_join_does_not_gain_old_assignment', assignment['id'] not in [a['id'] for a in request(newcomer, 'GET', '/assignments')])
        request(newcomer, 'PUT', apath + '/submission', {'answer': '越权验收'}, expected=404)
        request(teacher, 'PATCH', cpath + '/members/student', {'active': False})
        removed = next(a for a in request(student, 'GET', '/assignments') if a['id'] == assignment['id'])
        check('removed_member_keeps_readonly_history', not removed['can_submit'] and removed['submission']['version'] == 2)
        request(student, 'PUT', apath + '/submission', {'answer': '退班后不能改'}, expected=409)
        request(teacher, 'PATCH', cpath + '/members/student', {'active': True})
        stats = request(teacher, 'GET', '/teaching/stats?class_id=' + classroom['id'])
        check('membership_changes_preserve_recipient_snapshot', stats['expected'] == 1 and stats['completed'] == 1)
        conversation = request(student, 'POST', '/conversations', dict(question='用定义解释 x^2 在 x=2 处的导数，为何不能只代入函数值？', topic='导数与微分'), 201)
        # Explicit demo mode uses a body disclaimer; notice is for call failures.
        check('demo_response_honest_and_referenced', conversation['mode'] == 'demo' and '固定例题演示' in conversation['answer'] and bool(conversation.get('references')))
        check('teacher_cannot_read_student_private_conversation', conversation['id'] not in [c['id'] for c in request(teacher, 'GET', '/conversations')])
        request(teacher, 'PATCH', '/conversations/' + conversation['id'], {'favorite': True}, expected=404)
        request(student, 'PATCH', '/conversations/' + conversation['id'], {'favorite': True})
        request(student, 'POST', '/auth/logout')
        login(student, 'student', 'Student123!', 'student')
        saved_chat = next(c for c in request(student, 'GET', '/conversations') if c['id'] == conversation['id'])
        check('conversation_and_favorite_survive_relogin', saved_chat['favorite'] and saved_chat['mode'] == 'demo')
        # Valid synthetic PNG, no personal photo and no claim of real OCR quality.
        png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII='
        unavailable = request(student, 'POST', '/agent/recognize', dict(image_base64=png, media_type='image/png'), expected=503)
        check('unconfigured_ocr_refuses_instead_of_fabricating', '演示模式' in unavailable['detail'])
        record = dict(instance=args.expect_instance, checks=checks, class_id=classroom['id'], class_name=classroom['name'], assignment_id=assignment['id'], assignment_title=assignment['title'], conversation_id=conversation['id'], ai_mode='demo', real_model_tested=False, photo_ui_tested=False)
        report_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'passed': len(checks), 'report': str(report_path), 'class_name': classroom['name'], 'assignment_title': assignment['title']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
