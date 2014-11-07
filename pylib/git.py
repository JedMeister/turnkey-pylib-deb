# Copyright (c) 2007 Liraz Siri <liraz@turnkeylinux.org>
#
# This file is part of turnkey-pylib.
#
# turnkey-pylib is open source software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.

import sys
import os
from os.path import *
import subprocess
from subprocess import PIPE

import commands

from executil import *

def is_git_repository(path):
    """Return True if path is a git repository"""
    
    try:
        git = Git(path)
        return True
    except:
        return False

def setup(method):
    """Decorator that:
    1) chdirs into git.path
    2) processes arguments (only non-keywords arguments):
       stringifies them (except None, True or False)
       translates all absolute paths inside git.path to be relative to git.path
    
    """

    def wrapper(self, *args, **kws):
        orig_cwd = os.getcwd()
        os.chdir(self.path)
        os.environ['GIT_DIR'] = self.gitdir

        def make_relative(arg):
            for constant in (None, True, False):
                if arg is constant:
                    return arg

            if isinstance(arg, (list, tuple)):
                return map(make_relative, arg)

            try:
                return self.make_relative(arg)
            except self.Error:
                return arg

        args = map(make_relative, args)

        try:
            ret = method(self, *args, **kws)
        finally:
            os.chdir(orig_cwd)

        return ret
        
    return wrapper

class Error(Exception):
    def __str__(self):
        return str(self.args[0])

class Git(object):
    """Class for interfacing with a git repository.

    Most methods that are documented to return values raise an exception on error,
    except if the method is documented to return None on error.
    """
    Error = Error

    class MergeMsg(object):
        """Magical attribute.

        Set writes to .git/MERGE_MSG
        Get reads value from .git/MERGE_MSG
        """

        def get_path(self, obj):
            return join(obj.path, ".git", "MERGE_MSG")
        
        def __get__(self, obj, type):
            path = self.get_path(obj)
            if exists(path):
                return file(path, "r").read()

            return None
        
        def __set__(self, obj, val):
            path = self.get_path(obj)
            file(path, "w").write(val)

    MERGE_MSG = MergeMsg()

    class IndexLock(object):
        def get_path(self, obj):
            return join(obj.gitdir, "index.lock")

        def __get__(self, obj, type):
            path = self.get_path(obj)
            return exists(path)
        
        def __set__(self, obj, val):
            path = self.get_path(obj)
            if val:
                file(path, "w").close()
            else:
                if exists(path):
                    os.remove(path)

    index_lock = IndexLock()

    @classmethod
    def init_create(cls, path, bare=False, verbose=False):
        if not lexists(path):
            os.mkdir(path)

        init_path = path
        if not bare:
            init_path = join(init_path, ".git")

        command = "git --git-dir %s init" % commands.mkarg(init_path)
        if not verbose:
            command += " > /dev/null"
            
        os.system(command)

        return cls(path)

    def __init__(self, path):
        # heuristic: if the path has a .git directory in it, then its not bare
        # otherwise we assume its a bare repo if
        # 1) it ends with .git
        # 2) seems to be initialized (objects and refs directories exist)
        self.path = realpath(path)
        path_git = join(self.path, ".git")
        if isdir(path_git):
            self.bare = False
            self.gitdir = path_git
        elif self.path.endswith(".git") and \
                 isdir(join(self.path, "refs")) and isdir(join(self.path, "objects")):
            self.bare = True
            self.gitdir = self.path
        else:
            raise self.Error("Not a git repository `%s'" % self.path)

    def make_relative(self, path):
        path = str(path)
        path = join(realpath(dirname(path)), basename(path))

        if not (path == self.path or path.startswith(self.path + "/")):
            raise self.Error("path not in the git repository (%s)" % path)

        return path[len(self.path):].lstrip("/")

    @setup
    def _system(self, command, *args):
        try:
            system("git " + command, *args)
        except ExecError, e:
            raise self.Error(e)

    def read_tree(self, *opts):
        """git read-tree *opts"""
        self._system("read-tree", *opts)

    def update_index(self, *paths):
        """git update-index --remove <paths>"""
        self._system("update-index --remove", *paths)
        
    def update_index_refresh(self):
        """git update-index --refresh"""
        self._system("update-index -q --unmerged --refresh")

    @setup
    def update_index_all(self):
        """update all files that need update according to git update-index --refresh"""
        err, output = commands.getstatusoutput("git update-index --refresh")
        if not err:
            return
        output.split('\n')

        files = [ line.rsplit(':', 1)[0] for line in output.split('\n')
                  if line.endswith("needs update") ]
        self.update_index(*files)

    def add(self, *paths):
        """git add <path>"""
        # git add chokes on empty directories
        self._system("add", *paths)

    def checkout(self, *args):
        """git checkout *args"""
        self._system("checkout", *args)
        
    def checkout_index(self):
        """git checkout-index -a -f"""
        self._system("checkout-index -a -f")

    def update_ref(self, *args):
        """git update-ref [ -d ] <ref> <rev> [ <oldvalue > ]"""
        self._system("update-ref", *args)

    def rm_cached(self, path):
        """git rm <path>"""
        self._system("rm --ignore-unmatch --cached --quiet -f -r", path)

    def commit(self, paths=(), msg=None, update_all=False, verbose=False):
        """git commit"""
        command = "commit"
        if update_all:
            command += " -a"
        if verbose:
            command += " -v"

        if msg:
            self._system(command, "-m", msg, *paths)
        else:
            self._system(command, *paths)

    def merge(self, remote):
        """git merge <remote>"""
        self._system("merge", remote)

    def reset(self, *args):
        """git reset"""
        self._system("reset", *args)

    def branch_delete(self, branch):
        """git branch -D <branch>"""
        self._system("branch -D", branch)

    def branch(self, *args):
        """git branch *args"""
        self._system("branch", *args)

    def prune(self):
        """git prune"""
        self._system("prune")

    def repack(self, *args):
        """git repack *args"""
        self._system("repack", *args)
        
    def fetch(self, repository, refspec):
        self._system("fetch", repository, refspec)

    def raw(self, command, *args):
        """execute a raw git command.
        Returns:
            exit status code if command failed
            None if it was successfuly"""
        
        try:
            self._system(command, *args)
        except self.Error, e:
            return e[0].exitcode

    @setup
    def _getoutput(self, command, *args):
        try:
            output = getoutput("git " + command, *args)
        except ExecError, e:
            raise self.Error(e)
        return output

    def cat_file(self, *args):
        return self._getoutput("cat-file", *args)

    def write_tree(self):
        """git write-tree
        Returns id of written tree"""
        return self._getoutput("write-tree")

    def rev_parse(self, *args):
        """git rev-parse <rev>.
        Returns object-id of parsed rev.
        Returns None on failure.
        """
        try:
            return self._getoutput("rev-parse", *args)
        except self.Error:
            return None

    def merge_base(self, a, b):
        """git merge-base <a> <b>.
        Returns common ancestor"""
        try:
            return self._getoutput("merge-base", a, b)
        except self.Error:
            return None

    def symbolic_ref(self, name, ref=None):
        """git symbolic-ref <name> [ <ref> ]
        Returns the value of the symbolic ref.
        """
        args = ["symbolic-ref", name]
        if ref:
            args.append(ref)
        return self._getoutput(*args)

    def rev_list(self, *args):
        """git rev-list <commit>.
        Returns list of commits.
        """
        output = self._getoutput("rev-list", *args)
        if not output:
            return []
        
        return output.split('\n')
    
    def name_rev(self, rev):
        """git name-rev <rev>
        Returns name of rev"""
        return self._getoutput("name-rev", rev).split(" ")[1]

    def show_ref(self, ref):
        """git show-ref <rev>.
        Returns ref name if succesful
        Returns None on failure"""
        try:
            return self._getoutput("show-ref", ref).split(" ")[1]
        except self.Error:
            return None

    def show(self, *args):
        """git show *args -> output"""
        return self._getoutput("show", *args)

    @setup
    def describe(self, *args):
        """git describe *args -> list of described tags.

        Note: git describe terminates on the first argument it can't
        describe and we ignore that error.
        """
        command = ["git", "describe"] + list(args)
        p = subprocess.Popen(command, stdout=PIPE, stderr=PIPE)

        stdout, stderr = p.communicate()
        return stdout.splitlines()
        
    @setup
    def commit_tree(self, id, log, parents=None):
        """git commit-tree <id> [ -p <parents> ] < <log>
        Return id of object committed"""
        args = ["git", "commit-tree", id]
        if parents:
            if not isinstance(parents, (list, tuple)):
                parents = [ parents ]

            for parent in parents:
                args += ["-p", parent]

        p = subprocess.Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        try:
            p.stdin.write(log)
            p.stdin.close()
        except IOError:
            pass
        
        err = p.wait()
        if err:
            raise self.Error("git commit-tree failed: " + p.stderr.read())

        return p.stdout.read().strip()

    def mktree_empty(self):
        """return an empty tree id which is needed for some comparisons"""

        args = ["git", "mktree"]
        p = subprocess.Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        try:
            p.stdin.close()
        except IOError:
            pass
        
        err = p.wait()
        if err:
            raise self.Error("git mktree failed: " + p.stderr.read())

        return p.stdout.read().strip()

    @setup
    def log(self, *args):
        """git log *args
        Return stdout pipe"""


        command = ["git", "log"]
        command.extend(args)

        p = subprocess.Popen(command, stdout=PIPE, bufsize=1)

        return p.stdout
    
    def status(self, *paths):
        """git diff-index --name-status HEAD
        Returns array of (status, path) changes """

        self.update_index_refresh()
        output = self._getoutput("diff-index --ignore-submodules --name-status HEAD", *paths)
        if output:
            return [ line.split('\t', 1) for line in output.split('\n')]
        return []
    
    def list_unmerged(self):
        output = self._getoutput("diff --name-only --diff-filter=U")
        if output:
            return output.split('\n')
        return []

    def get_commit_log(self, committish):
        """Returns commit log text for <committish>"""

        str = self._getoutput("cat-file commit", committish)
        return str[str.index('\n\n') + 2:]

    def ls_files(self, *args):
        return self._getoutput("ls-files", *args).splitlines()
            
    def list_changed_files(self, compared, *paths):
        """Return a list of files that changed between compared.

        If compared is tuple/list with 2 elements, we compare the
        compared[0] and compared[1] with git diff-tree.
        
        If compared is not a tuple/list, or a tuple/list with 1 element,
        we compare compared with git diff-index which compares a commit/treeish to
        the index."""

        self.update_index_refresh()
        if not isinstance(compared, (list, tuple)):
            compared = [ compared ]

        if len(compared) == 2:
            str = self._getoutput("diff-tree -r --name-only",
                                  compared[0], compared[1], *paths)
        elif len(compared) == 1:
            str = self._getoutput("diff-index --ignore-submodules -r --name-only",
                                  compared[0], *paths)
        else:
            raise self.Error("compared does not contain 1 or 2 elements")
            
        if str:
            return str.split('\n')
        return []

    def list_refs(self, refpath):
        """list refs in <refpath> (e.g., "heads")"""
        path = join(self.gitdir, "refs", refpath)
        if not isdir(path):
            return []
        return os.listdir(path)

    def list_heads(self):
        return self.list_refs("heads")

    def list_tags(self):
        return self.list_refs("tags")

    def remove_ref(self, ref):
        """deletes refs/<ref> from the git repository"""
        path = join(self.gitdir, "refs", ref)
        if lexists(path):
            os.remove(path)

    def remove_tag(self, name):
        self.remove_ref("tags/" + name)

    def set_alternates(self, git):
        """set alternates path to point to the objects path of the specified git object"""

        fh = file(join(self.gitdir, "objects/info/alternates"), "w")
        print >> fh, join(git.gitdir, "objects")
        fh.close()

    @staticmethod
    def set_gitignore(path, lines):
        fh = file(join(path, ".gitignore"), "w")
        for line in lines:
            print >> fh, line

    @staticmethod
    def anchor(path):
        fh = file(join(path, ".anchor"), "w")
        fh.close()

