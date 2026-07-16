"""Tests for distutils.command.check."""

import distutils.command.check as _check
import importlib
import os
import sys
import textwrap
from distutils.errors import DistutilsSetupError
from distutils.tests import support

import pytest

HERE = os.path.dirname(__file__)


@pytest.fixture
def hide_pygments(monkeypatch, request):
    """
    Clear docutils and hide the presence of pygments.
    """
    clear_docutils(monkeypatch)
    monkeypatch.setitem(sys.modules, 'pygments', None)
    reload_check()
    # restore 'check' to its normal state after monkeypatch is undone
    request.addfinalizer(reload_check)


def clear_docutils(monkeypatch):
    docutils_names = [
        name for name in sys.modules if name.partition('.')[0] == 'docutils'
    ]
    for name in docutils_names:
        monkeypatch.delitem(sys.modules, name)


def reload_check():
    """
    Reload the 'check' command module to reflect the import state.
    """
    importlib.reload(_check)


@support.combine_markers
class TestCheck(support.TempdirManager):
    def _run(self, metadata=None, cwd=None, **options):
        if metadata is None:
            metadata = {}
        if cwd is not None:
            old_dir = os.getcwd()
            os.chdir(cwd)
        pkg_info, dist = self.create_dist(**metadata)
        cmd = _check.check(dist)
        cmd.initialize_options()
        for name, value in options.items():
            setattr(cmd, name, value)
        cmd.ensure_finalized()
        cmd.run()
        if cwd is not None:
            os.chdir(old_dir)
        return cmd

    def test_check_metadata(self):
        # let's run the command with no metadata at all
        # by default, check is checking the metadata
        # should have some warnings
        cmd = self._run()
        assert cmd._warnings == 1

        # now let's add the required fields
        # and run it again, to make sure we don't get
        # any warning anymore
        metadata = {
            'url': 'xxx',
            'author': 'xxx',
            'author_email': 'xxx',
            'name': 'xxx',
            'version': 'xxx',
        }
        cmd = self._run(metadata)
        assert cmd._warnings == 0

        # now with the strict mode, we should
        # get an error if there are missing metadata
        with pytest.raises(DistutilsSetupError):
            self._run({}, **{'strict': 1})

        # and of course, no error when all metadata are present
        cmd = self._run(metadata, strict=True)
        assert cmd._warnings == 0

        # now a test with non-ASCII characters
        metadata = {
            'url': 'xxx',
            'author': '\u00c9ric',
            'author_email': 'xxx',
            'name': 'xxx',
            'version': 'xxx',
            'description': 'Something about esszet \u00df',
            'long_description': 'More things about esszet \u00df',
        }
        cmd = self._run(metadata)
        assert cmd._warnings == 0

    def test_check_author_maintainer(self):
        for kind in ("author", "maintainer"):
            # ensure no warning when author_email or maintainer_email is given
            # (the spec allows these fields to take the form "Name <email>")
            metadata = {
                'url': 'xxx',
                kind + '_email': 'Name <name@email.com>',
                'name': 'xxx',
                'version': 'xxx',
            }
            cmd = self._run(metadata)
            assert cmd._warnings == 0

            # the check should not warn if only email is given
            metadata[kind + '_email'] = 'name@email.com'
            cmd = self._run(metadata)
            assert cmd._warnings == 0

            # the check should not warn if only the name is given
            metadata[kind] = "Name"
            del metadata[kind + '_email']
            cmd = self._run(metadata)
            assert cmd._warnings == 0

    def test_check_document(self):
        pkg_info, dist = self.create_dist()
        cmd = _check.check(dist)

        # let's see if it detects broken rest
        broken_rest = 'title\n===\n\ntest'
        msgs = cmd._check_rst_data(broken_rest)
        assert len(msgs) == 1

        # and non-broken rest
        rest = 'title\n=====\n\ntest'
        msgs = cmd._check_rst_data(rest)
        assert len(msgs) == 0

    def test_check_restructuredtext(self):
        # let's see if it detects broken rest in long_description
        broken_rest = 'title\n===\n\ntest'
        pkg_info, dist = self.create_dist(long_description=broken_rest)
        cmd = _check.check(dist)
        cmd.check_restructuredtext()
        assert cmd._warnings == 1

        # let's see if we have an error with strict=True
        metadata = {
            'url': 'xxx',
            'author': 'xxx',
            'author_email': 'xxx',
            'name': 'xxx',
            'version': 'xxx',
            'long_description': broken_rest,
        }
        with pytest.raises(DistutilsSetupError):
            self._run(metadata, **{'strict': 1, 'restructuredtext': 1})

        # and non-broken rest, including a non-ASCII character to test #12114
        metadata['long_description'] = 'title\n=====\n\ntest \u00df'
        cmd = self._run(metadata, strict=True, restructuredtext=True)
        assert cmd._warnings == 0

        # check that includes work to test #31292
        metadata['long_description'] = 'title\n=====\n\n.. include:: includetest.rst'
        cmd = self._run(metadata, cwd=HERE, strict=True, restructuredtext=True)
        assert cmd._warnings == 0

    code_examples = [
        textwrap.dedent(
            f"""
            Here's some code:

            .. {directive}:: python

                def foo():
                    pass
            """
        ).lstrip()
        for directive in ['code', 'code-block']
    ]

    def check_rst_data(self, descr):
        pkg_info, dist = self.create_dist(long_description=descr)
        cmd = _check.check(dist)
        cmd.check_restructuredtext()
        return cmd._check_rst_data(descr)

    @pytest.mark.parametrize('descr', code_examples)
    def test_check_rst_with_syntax_highlight_pygments(self, descr):
        assert self.check_rst_data(descr) == []

    @pytest.mark.parametrize('descr', code_examples)
    def test_check_rst_with_syntax_highlight_no_pygments(self, descr, hide_pygments):
        (msg,) = self.check_rst_data(descr)
        _, exc, _, _ = msg
        assert str(exc) == 'Cannot analyze code. Pygments package not found.'

    def test_check_all(self):
        with pytest.raises(DistutilsSetupError):
            self._run({}, **{'strict': 1, 'restructuredtext': 1})
