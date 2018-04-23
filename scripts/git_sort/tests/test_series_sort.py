#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import os.path
import pygit2
import shutil
import subprocess
import sys
import tempfile
import unittest

import git_sort
import lib
import tests.support


class TestSeriesSort(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        tree = self.repo.TreeBuilder().write()

        m0 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 0\n\nlog",
            tree,
            []
        )

        n0 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 0\n\nlog",
            tree,
            [m0]
        )

        self.repo.checkout("refs/heads/mainline")
        m1 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 1, merge net\n\nlog",
            tree,
            [m0, n0]
        )

        m2 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 2\n\nlog",
            tree,
            [m1]
        )

        n1 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 1\n\nlog",
            tree,
            [n0]
        )

        n2 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 2\n\nlog",
            tree,
            [n1]
        )

        oot0 = self.repo.create_commit(
            "refs/heads/oot",
            author,
            committer,
            "oot 0\n\nlog",
            tree,
            [m0]
        )

        oot1 = self.repo.create_commit(
            "refs/heads/oot",
            author,
            committer,
            "oot 1\n\nlog",
            tree,
            [oot0]
        )

        k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
        origin_repo = k_org_canon_prefix + "torvalds/linux.git"
        self.repo.remotes.create("origin", origin_repo)
        self.repo.references.create("refs/remotes/origin/master", m2)

        net_repo = k_org_canon_prefix + "davem/net.git"
        self.repo.remotes.create("net", net_repo)
        self.repo.references.create("refs/remotes/net/master", n2)

        self.index = git_sort.SortIndex(self.repo)

        # setup stub kernel-source content
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        patch_dir = os.path.join(self.ks_dir, "patches.suse")
        os.mkdir(patch_dir)
        os.chdir(patch_dir)
        tests.support.format_patch(self.repo.get(m0), mainline="v3.45-rc6")
        tests.support.format_patch(self.repo.get(n0), mainline="v3.45-rc6")
        tests.support.format_patch(self.repo.get(n1), repo=net_repo)
        tests.support.format_patch(self.repo.get(n2), repo=net_repo)
        tests.support.format_patch(self.repo.get(oot0))
        tests.support.format_patch(self.repo.get(oot1))

    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_nofile(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        try:
            subprocess.check_output([ss_path, "aaa"], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(
                err.output.decode(),
                "Error: [Errno 2] No such file or directory: 'aaa'\n")
        else:
            self.assertTrue(False)


    def test_absent(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(
"""
	patches.suse/unsorted-before.patch
""")

        try:
            subprocess.check_output([ss_path, series], stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.output.decode(), "Error: Sorted subseries not found.\n")
        else:
            self.assertTrue(False)

        os.unlink(series)


    def test_sort_small(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(
"""########################################################
	# sorted patches
	########################################################
	patches.suse/mainline-0.patch
	patches.suse/net-0.patch
	########################################################
	# end of sorted patches
	########################################################
""")

        subprocess.check_call([ss_path, "-c", series])
        with open(series) as f:
            content1 = f.read()
        subprocess.check_call([ss_path, series])
        with open(series) as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        os.unlink(series)


    def test_sort(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(
"""
	patches.suse/unsorted-before.patch

	########################################################
	# sorted patches
	########################################################
	patches.suse/mainline-0.patch
	patches.suse/net-0.patch

	# davem/net
	patches.suse/net-1.patch
	patches.suse/net-2.patch

	# out-of-tree patches
	patches.suse/oot-0.patch
	patches.suse/oot-1.patch

	########################################################
	# end of sorted patches
	########################################################

	patches.suse/unsorted-after.patch
""")

        subprocess.check_call([ss_path, "-c", series])
        with open(series) as f:
            content1 = f.read()
        subprocess.check_call([ss_path, series])
        with open(series) as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        os.unlink(series)


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSeriesSort)
    unittest.TextTestRunner(verbosity=2).run(suite)
