from pathlib import Path

import yaml
import pytest


def test_release_requires_successful_main_push_tests_at_exact_commit():
    path = Path(__file__).resolve().parents[1] / '.github/workflows/release.yml'
    config = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    trigger = config['on']
    assert 'push' not in trigger
    assert trigger['workflow_run'] == {'workflows': ['tests'], 'types': ['completed'], 'branches': ['main']}
    job = config['jobs']['publish']
    assert "github.event.workflow_run.conclusion == 'success'" in job['if']
    assert "github.event.workflow_run.event == 'push'" in job['if']
    assert 'github.event.workflow_run.head_repository.full_name == github.repository' in job['if']
    checkout = next(step for step in job['steps'] if step.get('uses', '').startswith('actions/checkout@'))
    assert checkout['with']['ref'] == '${{ github.event.workflow_run.head_sha }}'
    publish = next(step for step in job['steps'] if 'gh release create' in step.get('run', ''))
    assert publish['env']['RELEASE_SHA'] == '${{ github.event.workflow_run.head_sha }}'
    assert '--target "$RELEASE_SHA"' in publish['run']
    assert 'python -m scripts.check_release_tag "$RELEASE_SHA" "$tag"' in publish['run']


@pytest.mark.parametrize('output,allowed', [
    ('', True),
    ('a' * 40 + '\trefs/tags/v2.2.1\n', True),
    ('b' * 40 + '\trefs/tags/v2.2.1\n', False),
    ('b' * 40 + '\trefs/tags/v2.2.1\n' + 'a' * 40 + '\trefs/tags/v2.2.1^{}\n', True),
    ('a' * 40 + '\trefs/tags/v2.2.1\n' + 'b' * 40 + '\trefs/tags/v2.2.1^{}\n', False),
])
def test_existing_release_tag_must_resolve_to_tested_commit(output, allowed):
    from scripts.check_release_tag import verify_target
    if allowed:
        verify_target(output, 'v2.2.1', 'a' * 40)
    else:
        with pytest.raises(ValueError, match='different commit'):
            verify_target(output, 'v2.2.1', 'a' * 40)
