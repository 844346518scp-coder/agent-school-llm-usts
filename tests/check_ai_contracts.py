"""Reproduce known AI contract gaps with synthetic data only.

Run from the repository root: python -B tests/check_ai_contracts.py
Writes a new JSON report under ignored .tmp/. Exit 0 means the observations were
recorded, NOT that the product passed. Known issues remain issue_reproduced.
There are no HTTP requests, real model calls, application startup or DB writes.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

# Set these before any application import. Do not discover or read local secrets.
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['AGENT_MODE'] = 'demo'
os.environ['SHUBAN_SEED_DEMO'] = 'false'

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Synthetic one-pixel PNG. It is passed only to a mocked model function.
PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='


class IsolationViolation(RuntimeError):
    pass


def run_checks():
    forbidden_attempts = []

    def forbidden(kind):
        def reject(*args, **kwargs):
            forbidden_attempts.append(kind)
            raise IsolationViolation(kind)
        return reject

    cases = []

    def record(case_id, expected, observed, issue):
        cases.append({'id': case_id, 'expected': expected, 'observed': observed,
                      'status': 'issue_reproduced' if issue else 'behavior_as_expected'})

    # The patches also protect installations whose python-dotenv version predates
    # PYTHON_DOTENV_DISABLED. Credentials/URLs are never read or reported.
    with ExitStack() as guards:
        guards.enter_context(patch('dotenv.load_dotenv', return_value=False))
        guards.enter_context(patch('dotenv.dotenv_values', return_value={}))
        guards.enter_context(patch('dotenv.main.DotEnv.dict', side_effect=forbidden('dotenv_read')))
        guards.enter_context(patch('socket.create_connection', side_effect=forbidden('network')))
        guards.enter_context(patch('socket.socket.connect', side_effect=forbidden('network')))
        guards.enter_context(patch('socket.socket.connect_ex', side_effect=forbidden('network')))
        guards.enter_context(patch('sqlite3.connect', side_effect=forbidden('database_connect')))
        guards.enter_context(patch('sqlalchemy.engine.Engine.connect', side_effect=forbidden('database_connect')))
        guards.enter_context(patch('sqlalchemy.schema.MetaData.create_all', side_effect=forbidden('database_initialize')))

        from fastapi import HTTPException
        from pydantic import ValidationError
        from backend.app.ai import knowledge, service
        from backend.app.ai.llm import ModelCallFailed

        guards.enter_context(patch.object(service, 'chat', side_effect=forbidden('real_model_call')))
        assert 'backend.app.main' not in sys.modules, 'Application startup module must not be imported.'

        coverage = knowledge.stats()
        for case_id, question, allowed_topics in (
            ('integral_topic', '求定积分 integral_0^1 x^2 dx', (None, '定积分', '积分', '一元函数积分学')),
            ('series_topic', '判断级数 sum(1/n^2) 的敛散性', (None, '无穷级数', '级数')),
        ):
            topic = knowledge.suggest_topic(question)
            hits = knowledge.retrieve(question, top_k=3)
            record(case_id,
                   'Return a relevant topic, or no suggestion when the knowledge base does not cover it.',
                   {'question': question, 'suggested_topic': topic,
                    'top_point_ids': [hit.point.id for hit in hits]},
                   topic not in allowed_topics)

        # Input validation is tested separately from model execution.
        for case_id, fields, expectation in (
            ('invalid_base64', {'image_base64': '@' * 16, 'media_type': 'image/png'},
             'Reject malformed base64 before contacting a model.'),
            ('unsupported_mime', {'image_base64': PNG, 'media_type': 'text/plain'},
             'Reject a non-image MIME type before contacting a model.'),
        ):
            try:
                service.RecognizeInput(**fields)
                accepted = True
            except ValidationError:
                accepted = False
            record(case_id, expectation, {'accepted_by_input_model': accepted}, accepted)

        valid_input = service.RecognizeInput(image_base64=PNG, media_type='image/png')
        assert base64.b64decode(PNG, validate=True).startswith(b'\x89PNG')
        live = SimpleNamespace(resolved_mode='live', vision_model='synthetic-only')

        with patch.object(service, 'load_settings', return_value=live):
            with patch.object(service, 'chat', return_value='{}'):
                try:
                    result = service.recognize_question(valid_input, None)
                    observed = {'returned_result': True, 'mode': result.get('mode'),
                                'text_empty': not bool(result.get('text', '').strip()),
                                'requires_confirmation': result.get('requires_confirmation')}
                    issue = observed['text_empty']
                except HTTPException as error:
                    observed, issue = {'raised_http_status': error.status_code}, False
                record('empty_model_json', 'Reject an empty transcription with a controlled error.', observed, issue)

            with patch.object(service, 'chat', return_value='{"text":"synthetic question","warnings":123}'):
                try:
                    result = service.recognize_question(valid_input, None)
                    observed = {'returned_result': True, 'warnings_is_list': isinstance(result.get('warnings'), list)}
                    issue = not observed['warnings_is_list']
                except HTTPException as error:
                    observed, issue = {'raised_http_status': error.status_code}, False
                except IsolationViolation:
                    raise
                except Exception as error:
                    observed = {'uncaught_exception_type': type(error).__name__,
                                'http_500_is_inferred_not_requested': True}
                    issue = True
                record('numeric_model_warnings', 'Handle malformed model warnings without an uncaught exception.', observed, issue)

            with patch.object(service, 'chat', side_effect=ModelCallFailed('Synthetic model failure.')):
                try:
                    service.recognize_question(valid_input, None)
                    observed = {'raised_http_status': None}
                except HTTPException as error:
                    observed = {'raised_http_status': error.status_code}
                record('simulated_model_502', 'Translate a synthetic ModelCallFailed to HTTPException 502.',
                       observed, observed['raised_http_status'] != 502)

        with patch.object(service, 'load_settings', return_value=SimpleNamespace(resolved_mode='demo')):
            try:
                service.recognize_question(valid_input, None)
                observed = {'raised_http_status': None}
            except HTTPException as error:
                observed = {'raised_http_status': error.status_code}
            record('demo_503', 'Reject demo recognition with HTTPException 503 and no model call.',
                   observed, observed['raised_http_status'] != 503)

        assert not forbidden_attempts, 'An isolation guard was triggered.'

    issue_count = sum(case['status'] == 'issue_reproduced' for case in cases)
    return {'generated_at': datetime.now(timezone.utc).isoformat(),
            'report_type': 'synthetic_function_contract_observations',
            'product_acceptance': 'NOT_PASSED_KNOWN_ISSUES' if issue_count else 'NOT_ASSESSED',
            'limits': ['No HTTP/auth/browser validation.', 'No real model or vision quality validation.',
                       'No knowledge-point popup exists or is validated by this script.',
                       'Function-raised HTTPException statuses are not observed HTTP responses.'],
            'isolation': {'dotenv_disabled': True, 'dotenv_functions_stubbed': True,
                          'application_startup_imported': False, 'database_initialized': False,
                          'real_model_called': False, 'forbidden_attempts': forbidden_attempts},
            'knowledge_coverage': coverage,
            'summary': {'cases': len(cases), 'issues_reproduced': issue_count,
                        'behaviors_as_expected': len(cases) - issue_count},
            'cases': cases}


def main():
    report = run_checks()
    output_dir = ROOT / '.tmp'
    output_dir.mkdir(exist_ok=True)
    output = output_dir / f'ai-contract-observations-{uuid4().hex}.json'
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    # ASCII JSON avoids console encoding loss on Windows; the report itself is UTF-8.
    print(json.dumps({'report': str(output), 'product_acceptance': report['product_acceptance'],
                      **report['summary']}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
