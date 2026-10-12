"""Fail closed if an existing remote tag points away from the tested commit."""
import subprocess
import sys


def verify_target(output, tag, expected_sha):
    refs = {}
    for line in output.splitlines():
        if line.strip():
            sha, ref = line.split()
            refs[ref] = sha
    name = 'refs/tags/' + tag
    target = refs.get(name + '^{}', refs.get(name))
    if target is not None and target != expected_sha:
        raise ValueError(f'Tag {tag} resolves to a different commit. Refusing to replace it.')


def main():
    expected_sha, tag = sys.argv[1:]
    result = subprocess.run(['git', 'ls-remote', '--tags', 'origin',
                             'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'],
                            check=True, capture_output=True, text=True, timeout=30)
    verify_target(result.stdout, tag, expected_sha)


if __name__ == '__main__':
    main()
