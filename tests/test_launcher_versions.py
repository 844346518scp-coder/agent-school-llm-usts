"""Readiness must not reuse the pre-classroom backend after a source upgrade."""
import pytest

from backend.app.platform.portable import compatible_health


def test_current_service_is_reusable():
    assert compatible_health({
        'instance_id': 'same-checkout', 'status': 'ok',
        'agent_version': '0.2.0', 'teaching_version': '0.3.0', 'schema_version': 3,
    }, 'same-checkout')


def test_other_directory_is_not_reused_or_stopped():
    assert not compatible_health({'instance_id': 'other-checkout', 'status': 'ok'}, 'same-checkout')


@pytest.mark.parametrize('fields', [
    {}, {'agent_version': '0.2.0'},
    {'agent_version': '0.2.0', 'teaching_version': '0.3.0', 'schema_version': 2},
])
def test_old_same_directory_service_blocks_migration(fields):
    with pytest.raises(RuntimeError, match='Stop that backend before upgrading'):
        compatible_health({'instance_id': 'same-checkout', 'status': 'ok', **fields}, 'same-checkout')
