# Mercurial extension to push to and pull from Perforce depots.
#
# Copyright 2009-13 Frank Kingswood <frank@kingswood-consulting.co.uk>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2, incorporated herein by reference.

'''Push to or pull from Perforce depots

This extension modifies the remote repository handling so that repository
paths that resemble
    p4://p4server[:port]/clientname[/path/to/directory]
cause operations on the named p4 client specification on the p4 server.
The client specification must already exist on the server before using
this extension. Making changes to the client specification Views causes
problems when synchronizing the repositories, and should be avoided.
If a /path/to/directory is given then only a subset of the p4 view
will be operated on. Multiple partial p4 views can use the same p4
client specification.

Five built-in commands are overridden:

 outgoing  If the destination repository name starts with p4:// then
           this reports files affected by the revision(s) that are
           in the local repository but not in the p4 depot.

 push      If the destination repository name starts with p4:// then
           this exports changes from the local repository to the p4
           depot. If no revision is specified then all changes since
           the last p4 changelist are pushed. In either case, all
           revisions to be pushed are folded into a single p4 changelist.
           Optionally the resulting changelist is submitted to the p4
           server, controlled by the --submit option to push, or by
           setting
              --config perfarce.submit=True
           If the option
              --config perfarce.keep=False
           is False then after a successful submit the files in the
           p4 workarea will be deleted.

 pull      If the source repository name starts with p4:// then this
           imports changes from the p4 depot, automatically creating
           merges of changelists submitted by hg push.
           If the option
              --config perfarce.keep=False
           is False then the import does not leave files in the p4
           workarea, otherwise the p4 workarea will be updated
           with the new files.
           The option
              --config perfarce.tags=False
           can be used to disable pulling p4 tags (a.k.a. labels).
           The option
              --config perfarce.pull_trim_log=False
           can be used to remove the {{mercurial}} node IDs from both
           p4 and the imported changes. Use with care as this is a
           non-reversible operation.
              --config perfarce.clientuser=script_or_regex
           can be used to enable quasi-multiuser operation, where
           several users submit changes to p4 with the same user name
           and have their real user name in the p4 client spec.
           If the value of this parameter contains at least one space
           then it is split into a search regular expression and
           replacement string.  The search and replace regular expressions
           describe the substitution to be made to turn a client spec name
           into a user name. If the search regex does not match then the
           username is left unchanged.
           If the value of this parameter has no spaces then it is
           taken as the name of a script to run. The script is run
           with the client and user names as arguments. If the script
           produces output then this is taken as the user name,
           otherwise the username is left unchanged.

 incoming  If the source repository name starts with p4:// then this
           reports changes in the p4 depot that are not yet in the
           local repository.

 clone     If the source repository name starts with p4:// then this
           creates the destination repository and pulls all changes
           from the p4 depot into it.
           If the option
              --config perfarce.lowercasepaths=False
           is True then the import forces all paths in lowercase,
           otherwise paths are recorded unchanged.  Filename case is
           preserved.
           If the option
              --config perfarce.ignorecase=False
           is True then the import ignores all case differences in
           the p4 depot. Directory and filename case is preserved.
           These two setting are workarounds to handle Perforce depots
           containing a path spelled differently from file to file
           (e.g. path/foo and PAth/bar are in the same directory),
           or where the same file may be spelled differently from time
           to time (e.g. path/foo and path/FOO are the same object).
'''

from mercurial import cmdutil, commands, context, copies, encoding, error, extensions, hg, node, phases, util, url
from mercurial.node import hex, short
from mercurial.i18n import _
from mercurial.error import ConfigError
import marshal, os, re, string, sys
propertycache=util.propertycache

try:
    # Mercurial 1.9
    from mercurial import scmutil
    util_opener = scmutil.opener
    util_setflags = util.setflags
    revpair = scmutil.revpair
except (ImportError,AttributeError):
    util_opener = util.opener
    util_setflags = util.set_flags
    revpair = cmdutil.revpair

try:
    # Mercurial 2.3
    from mercurial import peer
    repository = peer.peerrepository
except (ImportError,AttributeError):
    from mercurial import repo
    repository = repo.repository

def uisetup(ui):
    '''monkeypatch pull and push for p4:// support'''

    extensions.wrapcommand(commands.table, 'pull', pull)
    p = extensions.wrapcommand(commands.table, 'push', push)
    p[1].append(('', 'submit', None, 'for p4:// destination submit new changelist to server'))
    p[1].append(('', 'job', [], 'for p4:// destination set job id(s)'))
    extensions.wrapcommand(commands.table, 'incoming', incoming)
    extensions.wrapcommand(commands.table, 'outgoing', outgoing)
    p = extensions.wrapcommand(commands.table, 'clone', clone)
    p[1].append(('', 'startrev', '', 'for p4:// source set initial revisions for clone'))
    p[1].append(('', 'encoding', '', 'for p4:// source set encoding used by server'))
    hg.schemes['p4'] = p4repo

# --------------------------------------------------------------------------

class p4repo(repository):
    'Dummy repository class so we can use -R for p4submit and p4revert'
    def __init__(self, ui, path):
        self.path = path
        self.ui = ui
        self.root = None

    @staticmethod
    def instance(ui, path, create):
        return p4repo(ui, path)

    def local(self):
        return True

    def __getattr__(self, a):
        raise util.Abort(_('%s not supported for p4') % a)

def loaditer(f):
    "Yield the dictionary objects generated by p4"
    try:
        while True:
            d = marshal.load(f)
            if not d:
                break
            yield d
    except EOFError:
        pass

class p4notclient(util.Abort):
    "Exception raised when a path is not a p4 client or invalid"
    pass

class p4badclient(util.Abort):
    "Exception raised when a path is an invalid p4 client"
    pass

class TempFile:
    "Temporary file"
    def __init__(self, mode):
        import tempfile
        fd, self.Name = tempfile.mkstemp(prefix='hg-p4-')
        if mode:
            self.File = os.fdopen(fd, mode)
        else:
            os.close(fd)
            self.File = None

    def close(self):
        if self.File:
            self.File.close()
            self.File=None

    def __del__(self):
        self.close()
        try:
            os.unlink(self.Name)
        except Exception:
            pass


class p4client(object):

    def __init__(self, ui, repo, path):
        'initialize a p4client class from the remote path'

        if not path.startswith('p4:'):
            raise p4notclient(_('%s not a p4 repository') % path)
        if not path.startswith('p4://'):
            raise p4badclient(_('%s not a p4 repository') % path)

        self.ui = ui
        self.repo = repo
        self.server = None      # server name:port
        self.client = None      # client spec name
        self.root = None        # root directory of client workspace
        self.partial = None     # tail of path for partial checkouts (ending in /), or empty string
        self.rootpart = None    # root+partial directory in client workspace (ending in /)

        self.keep = ui.configbool('perfarce', 'keep', True)
        self.lowercasepaths = ui.configbool('perfarce', 'lowercasepaths', False)
        self.ignorecase = ui.configbool('perfarce', 'ignorecase', False)

        # caches
        self.clientspec = {}
        self.usercache = {}
        self.p4stat = None
        self.p4pending = None

        s, c = path[5:].split('/', 1)
        if ':' not in s:
            s = '%s:1666' % s
        self.server = s
        if c:
            if '/' in c:
                c, p = c.split('/', 1)
                p = '/'.join(q for q in p.split('/') if q)
                if p:
                    p += '/'
            else:
                p = ''

            d = self.runone('client -o %s' % util.shellquote(c), abort=False)
            if not isinstance(d, dict):
                raise p4badclient(_('%s is not a valid p4 client') % path)
            code = d.get('code')
            if code == 'error':
                data=d['data'].strip()
                ui.warn('%s\n' % data)
                raise p4badclient(_('%s is not a valid p4 client: %s') % (path, data))

            if sys.platform.startswith("cygwin"):
                re_dospath = re.compile('[a-z]:\\\\',re.I)
                def isdir(d):
                    return os.path.isdir(d) and not re_dospath.match(d)
            else:
                isdir=os.path.isdir

            for n in ['Root'] + ['AltRoots%d' % i for i in range(9)]:
                if n in d and isdir(d[n]):
                    self.root = util.pconvert(d[n])
                    break
            if not self.root:
                ui.note(_('the p4 client root must exist\n'))
                raise p4badclient(_('the p4 client root must exist\n'))

            self.clientspec = d
            self.client = c
            self.partial = p
            if p:
                if self.lowercasepaths:
                    p = self.normcase(p)
                p = os.path.join(self.root, p)
            else:
                p = self.root
            self.rootpart = util.pconvert(p)
            if not self.rootpart.endswith('/'):
                self.rootpart += '/'
            if self.root.endswith('/'):
                self.root = self.root[:-1]

    def find(self, rev=None, base=False, p4rev=None, abort=True):
        '''Find the most recent revision which has the p4 extra data which
        gives the p4 changelist it was converted from. If base is True then
        return the most recent child of that revision where the only changes
        between it and the p4 changelist are to .hg files.
        Returns the revision and p4 changelist number'''

        def dothgonly(ctx):
            'returns True if only .hg files in this context'

            if not ctx.files():
                # no files means this must have been a merge
                return False

            for f in ctx.files():
                if not f.startswith('.hg'):
                    return False
            return True

        try:
            mqnode = [self.repo['qbase'].node()]
        except Exception:
            mqnode = None

        if rev is None:
            current = self.repo['default']
        else:
            current = self.repo[rev]

        current = [(current,())]
        seen = set()
        while current:
            next = []
            self.ui.debug("find: %s\n" % (" ".join(hex(c[0].node()) for c in current)))
            for ctx,path in current:
                extra = ctx.extra()
                if 'p4' in extra:
                    if base:
                        while path:
                            if dothgonly(path[0]) and not (mqnode and
                                   self.repo.changelog.nodesbetween(mqnode, [ctx.node()])[0]):
                                ctx = path[0]
                                path = path[1:]
                            else:
                                path = []
                    p4 = int(extra['p4'])
                    if not p4rev or p4==p4rev:
                        return ctx.node(), p4

                for p in ctx.parents():
                    if p and p not in seen:
                        seen.add(p)
                        next.append((p, (ctx,) + path))

            current = next

        if abort:
            raise util.Abort(_('no p4 changelist revision found'))
        return node.nullid, 0

    @propertycache
    def re_type(self): return re.compile('([a-z]+)?(text|binary|symlink|apple|resource|unicode|utf\d+)(\+\w+)?$')
    @propertycache
    def re_keywords(self): return re.compile(r'\$(Id|Header|Date|DateTime|Change|File|Revision|Author):[^$\n]*\$')
    @propertycache
    def re_keywords_old(self): return re.compile('\$(Id|Header):[^$\n]*\$')

    def decodetype(self, p4type):
        'decode p4 type name into mercurial mode string and keyword substitution regex'

        base = mode = ''
        keywords = None
        utf16 = False
        p4type = self.re_type.match(p4type)
        if p4type:
            base = p4type.group(2)
            flags = (p4type.group(1) or '') + (p4type.group(3) or '')
            if 'x' in flags:
                mode = 'x'
            if base == 'symlink':
                mode = 'l'
            if base == 'utf16':
                utf16 = True
            if 'ko' in flags:
                keywords = self.re_keywords_old
            elif 'k' in flags:
                keywords = self.re_keywords
        return base, mode, keywords, utf16


    @propertycache
    def encoding(self):
        # work out character set for p4 text (but not filenames)
        emap = { 'none': 'ascii',
                 'utf8-bom': 'utf_8_sig',
                 'macosroman': 'mac-roman',
                 'winansi': 'cp1252' }
        e = os.environ.get("P4CHARSET")
        if e:
            return emap.get(e,e)
        return self.ui.config('perfarce', 'encoding', None)

    def decode(self, text):
        'decode text in p4 character set as utf-8'

        if self.encoding:
            try:
                return text.decode(self.encoding).encode(encoding.encoding)
            except LookupError, e:
                raise error.Abort("%s, please check your locale settings" % e)
        return text

    def encode(self, text):
        'encode utf-8 text to p4 character set'

        if self.encoding:
            try:
                return text.decode(encoding.encoding).encode(self.encoding)
            except LookupError, e:
                raise error.Abort("%s, please check your locale settings" % e)
        return text


    @staticmethod
    def encodename(name):
        'escape @ # % * characters in a p4 filename'
        return name.replace('%','%25').replace('@','%40').replace('#','%23').replace('*','%2A')


    @staticmethod
    def normcase(name):
        'convert path name to lower case'
        return os.path.normpath(name).lower()

    @propertycache
    def re_hgid(self): return re.compile('{{mercurial (([0-9a-f]{40})(:([0-9a-f]{40}))?)}}')

    def parsenodes(self, desc):
        'find revisions in p4 changelist description'
        m = self.re_hgid.search(desc)
        nodes = []
        if m:
            try:
                nodes = self.repo.changelog.nodesbetween(
                    [self.repo[m.group(2)].node()], [self.repo[m.group(4) or m.group(2)].node()])[0]
            except Exception:
                if self.ui.traceback:self.ui.traceback()
                self.ui.note(_('ignoring hg revision range %s from p4\n' % m.group(1)))
        return nodes, m

    def configint(self, section, name, default=None):
        'helper for configint which is missing before Mercurial 1.9'
        try:
            return self.ui.configint(section, name, default)
        except AttributeError:
            return int(self.ui.config(section, name, default))

    @propertycache
    def maxargs(self):
        try:
            r = self.configint('perfarce', 'maxargs', 0)
        except ConfigError:
            r = 0
        if r<1:
            if os.name == 'posix':
                r = 250
            else:
                r = 25
        return r


    def run(self, cmd, files=[], abort=True, client=None):
        'Run a P4 command and yield the objects returned'

        c = ['p4', '-G']
        if self.server:
            c.append('-p')
            c.append(self.server)
        if client or self.client:
            c.append('-c')
            c.append(client or self.client)
        if self.root:
            c.append('-d')
            c.append(util.shellquote(self.root))

        if files and len(files)>self.maxargs:
            tmp = TempFile('w')
            for f in files:
                if self.ui.debugflag: self.ui.debug('> -x %s\n' % f)
                print >>tmp.File,f
            tmp.close()
            c.append('-x')
            c.append(tmp.Name)
            files = []

        c.append(cmd)

        cs = ' '.join(c + [util.shellquote(f) for f in files])
        if self.ui.debugflag: self.ui.debug('> %s\n' % cs)

        for d in loaditer(util.popen(cs, mode='rb')):
            if self.ui.debugflag: self.ui.debug('< %r\n' % d)
            code = d.get('code')
            data = d.get('data')
            if code is not None and data is not None:
                data = data.strip()
                if abort and code == 'error':
                    raise util.Abort('p4: %s' % data)
                elif code == 'info':
                    self.ui.note('p4: %s\n' % data)
            yield d

    def runs(self, cmd, **args):
        '''Run a P4 command, discarding any output (except errors)'''
        for d in self.run(cmd, **args):
            pass

    def runone(self, cmd, **args):
        '''Run a P4 command and return the object returned'''

        value=None
        for d in self.run(cmd, **args):
            if value is None:
                value = d
            else:
                raise util.Abort(_('p4 %s returned more than one object') % cmd)
        if value is None:
           raise util.Abort(_('p4 %s returned no objects') % cmd)
        return value


    def getpending(self, node):
        '''returns True if node is pending in p4 or has been submitted to p4'''
        if self.p4stat is None:
            self._readp4stat()
        return node.node() in self.p4stat

    def getpendinglist(self):
        'return p4 submission state dictionary'
        if self.p4stat is None:
            self._readp4stat()
        return self.p4pending

    def _readp4stat(self):
        '''read pending and submitted changelists into pending cache'''
        self.p4stat = set()
        self.p4pending = []

        p4rev, p4id = self.find(abort=False)

        def helper(self,d,p4id):
            c = int(d['change'])
            if c == p4id:
                return

            desc = d['desc']
            nodes, match = self.parsenodes(desc)
            entry = (c, d['status'] == 'submitted', nodes, desc, d['client'])
            self.p4pending.append(entry)
            for n in nodes:
                self.p4stat.add(n)

        change = '%s...@%d,#head' % (self.partial, p4id)
        for d in self.run('changes -l -c %s %s' %
                           (util.shellquote(self.client), util.shellquote(change))):
            helper(self,d,p4id)
        for d in self.run('changes -l -c %s -s pending' %
                           (util.shellquote(self.client))):
            helper(self,d,p4id)
        self.p4pending.sort()


    def repopath(self, path):
        'Convert a p4 client path to a path relative to the hg root'
        if self.lowercasepaths:
            pathname, fname = os.path.split(path)
            path = os.path.join(self.normcase(pathname), fname)

        path = util.pconvert(path)
        if not path.startswith(self.rootpart):
            raise util.Abort(_('invalid p4 local path %s') % path)

        return path[len(self.rootpart):]

    def localpath(self, path):
        'Convert a path relative to the hg root to a path in the p4 workarea'
        return util.localpath(os.path.join(self.rootpart, path))


    def getuser(self, user, client=None):
        'get full name and email address of user (and optionally client spec name)'
        r = self.usercache.get((user,None)) or self.usercache.get((user,client))
        if r:
            return r

        # allow mapping the client name into a user name
        cu = self.ui.config("perfarce","clientuser")

        if cu and " " in cu:
            cus, cur = cu.split(" ", 1)
            u, f = re.subn(cus, cur, client)
            if f:
                r = string.capwords(u)
                self.usercache[(user, client)] = r
                return r

        elif cu:
            cmd = "%s %s %s" % (util.expandpath(cu), util.shellquote(client), util.shellquote(user))
            self.ui.debug('> %s\n' % cmd)

            old = os.getcwd()
            try:
                os.chdir(self.root)
                r = None
                for r in util.popen(cmd):
                    r = r.strip()
                    self.ui.debug('< %r\n' % r)
                if r:
                    self.usercache[(user, client)] = r
                    return r
            finally:
                os.chdir(old)

        else:
            d = self.runone('user -o %s' % util.shellquote(user), abort=False)
            if 'Update' in d:
                try:
                    r = '%s <%s>' % (d['FullName'], d['Email'])
                    self.usercache[(user, None)] = r
                    return r
                except Exception:
                    pass

        return user


    @propertycache
    def re_changeno(self): return re.compile('Change ([0-9]+) created.+')

    def change(self, change=None, description=None, update=False, jobs=None):
        '''Create a new p4 changelist or update an existing changelist with
        the given description. Returns the changelist number as a string.'''

        # get changelist data, and update it
        changelist = self.runone('change -o %s' % (change or ''))

        if jobs:
            for i,j in enumerate(jobs):
                changelist['Jobs%d'%i] = self.encode(j)

        if description is not None:
            changelist['Description'] = self.encode(description)

        # write changelist data to a temporary file
        tmp = TempFile('wb')
        marshal.dump(changelist, tmp.File, 0)
        tmp.close()

        # update p4 changelist
        d = self.runone('change -i%s <%s' % (update and " -u" or "", util.shellquote(tmp.Name)))
        data = d['data']
        if d['code'] == 'info':
            if not self.ui.verbose:
                self.ui.status('p4: %s\n' % data)
            if not change:
                m = self.re_changeno.match(data)
                if m:
                    change = m.group(1)
        else:
            raise util.Abort(_('error creating p4 change: %s') % data)

        if not change:
            raise util.Abort(_('did not get changelist number from p4'))

        # invalidate cache
        self.p4stat = None

        return change


    class description:
        'Changelist description'
        def __init__(self, **args):
            self.__dict__.update(args)
        def __repr__(self):
            return "%s(%s)"%(self.__class__.__name__,
                       ", ".join("%s=%r"%(k,getattr(self,k)) for k in sorted(self.__dict__.keys())))

    actions = { 'add':'A', 'branch':'A', 'move/add':'A',
                'edit':'M', 'integrate':'M', 'import':'A',
                'delete':'R', 'move/delete':'R', 'purge':'R',
              }

    def describe(self, change, local=None):
        '''Return p4 changelist description object with user name and date.
        If the local is true, then also collect a list of 5-tuples
            (depotname, revision, type, action, localname)
        If local is false then the files list returned holds 4-tuples
            (depotname, revision, type, action)
        Retrieving the local filenames is potentially very slow, even more
        so when this is used on pending changelists.
        '''

        d = self.runone('describe -s %s' % change)
        client = d['client']
        status = d['status']
        r = self.description(change=d['change'],
                             desc=self.decode(d['desc']),
                             user=self.getuser(self.decode(d['user']), client),
                             date=(int(d['time']), 0),     # p4 uses UNIX epoch
                             status=status,
                             client=client)

        files = {}
        if local and status=='submitted':
            r.files = self.fstat(change)
        else:
            r.files = []
            i = 0
            while True:
                df = 'depotFile%d' % i
                if df not in d:
                    break
                df = d[df]
                rv = d['rev%d' % i]
                tp = d['type%d' % i]
                ac = d['action%d' % i]
                files[df] = item = (df, int(rv), tp, self.actions[ac])
                r.files.append(item)
                i += 1

        r.jobs = []
        i = 0
        while True:
            jn = 'job%d' % i
            if jn not in d:
                break
            jn = d[jn]
            js = d['jobstat%d' % i]
            r.jobs.append((jn, js))
            i += 1

        if local and files:
            r.files = []
            for d in self.run('where', files=[f for f in files]):
                r.files.append(files[d['depotFile']] + (self.repopath(d['path']),))

        return r


    def fstat(self, change, all=False):
        '''Find local names for all the files belonging to a
        changelist.
        Returns a list of tuples
            (depotname, revision, type, action, localname)
        with only entries for files that appear in the workspace.
        If all is unset considers only files modified by the
        changelist, otherwise returns all files *at* that changelist.
        '''
        result = []

        if all:
            p4cmd = 'fstat %s' % util.shellquote('%s...@%d' % (self.partial, change))
        else:
            p4cmd = 'fstat -e %d %s' % (change, util.shellquote('%s...' % self.partial))

        for d in self.run(p4cmd):
            if len(result) % 250 == 0:
                if hasattr(self.ui, 'progress'):
                    self.ui.progress('p4 fstat', len(result), unit='entries')
                else:
                    self.ui.note('%d files\r' % len(result))
                    self.ui.flush()

            if 'desc' in d or d['clientFile'].startswith('.hg'):
                continue
            else:
                lf = self.repopath(d['clientFile'])
                df = d['depotFile']
                rv = d['headRev']
                tp = d['headType']
                ac = d['headAction']
                result.append((df, int(rv), tp, self.actions[ac], lf))

        if hasattr(self.ui, 'progress'):
            self.ui.progress('p4 fstat', None)
        self.ui.note(_('%d files \n') % len(result))

        return result


    def sync(self, change, fake=False, force=False, all=False, files=[]):
        '''Synchronize the client with the depot at the given change.
        Setting fake adds -k, force adds -f option. The all option is
        not used here, but indicates that the caller wants all the files
        at that revision, not just the files affected by the change.'''

        cmd = 'sync'
        if fake:
            cmd += ' -k'
        elif force:
            cmd += ' -f'
        if not files:
            cmd += ' ' + util.shellquote('%s...@%d' % (self.partial, change))

        n = 0
        for d in self.run(cmd, files=[("%s@%d" % (os.path.join(self.partial, f), change)) for f in files], abort=False):
            n += 1
            if n % 250 == 0:
                if hasattr(self.ui, 'progress'):
                    self.ui.progress('p4 sync', n, unit='files')
            code = d.get('code')
            if code == 'error':
                data = d['data'].strip()
                if d['generic'] == 17 or d['severity'] == 2:
                    self.ui.note('p4: %s\n' % data)
                else:
                    raise util.Abort('p4: %s' % data)

        if hasattr(self.ui, 'progress'):
            self.ui.progress('p4 sync', None)

        if files and n < len(files):
            raise util.Abort(_('incomplete reply from p4, reduce maxargs'))


    def getfile(self, entry):
        '''Return contents of a file in the p4 depot at the given revision number.
        Entry is a tuple
            (depotname, revision, type, action, localname)
        If self.keep is set, assumes that the client is in sync.
        Raises IOError if the file is deleted.
        '''

        if entry[3] == 'R':
            self.ui.debug('getfile ioerror on %r\n'%(entry,))
            raise IOError()

        try:
            basetype, mode, keywords, utf16 = self.decodetype(entry[2])

            if self.keep:
                fn = self.localpath(entry[4])
                if mode == 'l':
                    try:
                        contents = os.readlink(fn)
                    except AttributeError:
                        contents = file(fn, 'rb').read()
                        if contents.endswith('\n'):
                            contents = contents[:-1]
                else:
                    contents = file(fn, 'rb').read()
            else:
                cmd = 'print'
                if utf16:
                    tmp = TempFile(None)
                    tmp.close()
                    cmd += ' -o %s'%util.shellquote(tmp.Name)
                cmd += ' %s#%d' % (util.shellquote(entry[0]), entry[1])

                contents = []
                for d in self.run(cmd):
                    code = d['code']
                    if code == 'text' or code == 'binary':
                        contents.append(d['data'])

                if utf16:
                    contents = file(tmp.Name, 'rb').read()
                else:
                    contents = ''.join(contents)

                if mode == 'l' and contents.endswith('\n'):
                    contents = contents[:-1]

            if keywords:
                contents = keywords.sub('$\\1$', contents)

            return mode, contents
        except Exception, e:
            if self.ui.traceback:self.ui.traceback()
            raise util.Abort(_('file %s missing in p4 workspace') % entry[4])


    @propertycache
    def tags(self):
        try:
            t = self.configint('perfarce', 'tags', -1)
        except (ConfigError,ValueError),e:
            t = -1
        if t<0 or t>2:
            t = self.ui.configbool('perfarce', 'tags', True)
        return t

    def labels(self, change):
        'Return p4 labels a.k.a. tags at the given changelist'

        tags = []
        if self.tags:
            change = '%s...@%d,%d' % (self.partial, change, change)
            for d in self.run('labels %s' % util.shellquote(change)):
                l = d.get('label')
                if l:
                    tags.append(l)

        return tags


    def submit(self, change):
        '''submit one changelist to p4 and optionally delete the files added
        or modified in the p4 workarea'''

        cl = None
        for d in self.run('submit -c %s' % change):
            if d['code'] == 'error':
                raise util.Abort(_('error submitting p4 change %s: %s') % (change, d['data']))
            cl = d.get('submittedChange', cl)

        self.ui.note(_('submitted changelist %s\n') % cl)

        if not self.keep:
            # delete the files in the p4 client directory
            self.sync(0)

        # invalidate cache
        self.p4stat = None


    def hasmovecopy(self):
        '''detect whether p4 move and p4 copy are supported.
        these advanced features are available since about 2009.1 or so.'''

        mc = []
        for op in 'move','copy':
            v = self.ui.configbool('perfarce', op, None)
            if v is None:
                self.ui.note(_('checking if p4 %s is supported, set perfarce.%s to skip this test\n') % (op, op))
                d = self.runone('help %s' % op, abort=False)
                v = d['code']=='info'
                self.ui.debug(_('p4 %s is %ssupported\n') % (op, ["not ",""][v]))
            mc.append(v)

        return tuple(mc)


    @staticmethod
    def pullcommon(original, ui, repo, source, **opts):
        'Shared code for pull and incoming'

        if opts.get('mq',None):
            return True, original(ui, repo, *(source and [source] or []), **opts)

        source = ui.expandpath(source or 'default')
        try:
            client = p4client(ui, repo, source)
        except p4notclient:
            if ui.traceback:ui.traceback()
            return True, original(ui, repo, *(source and [source] or []), **opts)
        except p4badclient,e:
            if ui.traceback:ui.traceback()
            raise util.Abort(str(e))

        # if present, --rev will be the last Perforce changeset number to get
        stoprev = opts.get('rev')
        stoprev = stoprev and max(int(r) for r in stoprev) or 0

        # for clone we support a --startrev option to fold initial changelists
        startrev = opts.get('startrev')
        startrev = startrev and int(startrev) or 0

        # for clone we support an --encoding option to set server character set
        if opts.get('encoding'):
            client.encoding = opts.get('encoding')

        if len(repo):
            p4rev, p4id = client.find(base=True, abort=not opts['force'])
        else:
            p4rev, p4id = None, 0
        p4id = max(p4id, startrev)

        if stoprev:
           p4cset = '%s...@%d,@%d' % (client.partial, p4id, stoprev)
        else:
           p4cset = '%s...@%d,#head' % (client.partial, p4id)
        p4cset = util.shellquote(p4cset)

        if startrev < 0:
            # most recent changelists
            p4cmd = 'changes -s submitted -m %d -L %s' % (-startrev, p4cset)
        else:
            p4cmd = 'changes -s submitted -L %s' % p4cset

        changes = []
        for d in client.run(p4cmd):
            c = int(d['change'])
            if startrev or c != p4id:
                changes.append(c)
        changes.sort()

        return False, (client, p4rev, p4id, startrev, changes)


    @staticmethod
    def pushcommon(out, original, ui, repo, dest, **opts):
        'Shared code for push and outgoing'

        if opts.get('mq',None):
            return True, original(ui, repo, *(dest and [dest] or []), **opts)

        dest = ui.expandpath(dest or 'default-push', dest or 'default')
        try:
            client = p4client(ui, repo, dest)
        except p4notclient:
            if ui.traceback:ui.traceback()
            return True, original(ui, repo, *(dest and [dest] or []), **opts)
        except p4badclient,e:
            raise util.Abort(str(e))

        p4rev, p4id = client.find(base=True, abort=not opts['force'])
        ctx1 = repo[p4rev]
        rev = opts.get('rev')

        if rev:
            n1, n2 = revpair(repo, rev)
            if n2:
                ctx1 = repo[n1]
                ctx1 = ctx1.parents()[0]
                ctx2 = repo[n2]
            else:
                ctx2 = repo[n1]
                ctx1 = ctx2.parents()[0]
        else:
            ctx2 = repo['tip']

        nodes = repo.changelog.nodesbetween([ctx1.node()], [ctx2.node()])[0][bool(p4id):]

        if not opts['force']:
            # trim off nodes at either end that have already been pushed
            trim = False
            for end in [0, -1]:
                while nodes:
                    n = repo[nodes[end]]
                    if client.getpending(n):
                        del nodes[end]
                        trim = True
                    else:
                        break

            # recalculate the context
            if trim and nodes:
                ctx1 = repo[nodes[0]].parents()[0]
                ctx2 = repo[nodes[-1]]

            if ui.debugflag:
                for n in nodes:
                    ui.debug('outgoing %s\n' % hex(n))

            # check that remaining nodes have not already been pushed
            for n in nodes:
                n = repo[n]
                fail = False
                if client.getpending(n):
                    fail = True
                for ctx3 in n.children():
                    extra = ctx3.extra()
                    if 'p4' in extra:
                        fail = True
                        break
                if fail:
                    raise util.Abort(_('can not push, changeset %s is already in p4' % n))

        # find changed files
        if not nodes:
            mod = add = rem = []
            cpy = {}
        else:
            mod, add, rem = repo.status(node1=ctx1.node(), node2=ctx2.node())[:3]
            mod = [(f, ctx2.flags(f)) for f in mod]
            add = [(f, ctx2.flags(f)) for f in add]
            rem = [(f, "") for f in rem]

            try:
                # Mercurial 2.1
                cpy = copies.pathcopies(ctx1, ctx2)
            except AttributeError:
                cpy = copies.copies(repo, ctx1, ctx2, repo[node.nullid])[0]

            # remember which copies change the data
            for c in cpy:
                chg = ctx2.flags(c) != ctx1.flags(c) or ctx2[c].data() != ctx1[cpy[c]].data()
                cpy[c] = (cpy[c], chg)

            # remove .hg* files (mainly for .hgtags and .hgignore)
            for changes in [mod, add, rem]:
                i = 0
                while i < len(changes):
                    f = changes[i][0]
                    if f.startswith('.hg'):
                        del changes[i]
                    else:
                        i += 1

        if not (mod or add or rem):
            ui.status(_('no changes found\n'))
            return True, out and 1 or 0

        # detect MQ
        try:
            mq = repo.changelog.nodesbetween([repo['qbase'].node()], nodes)[0]
            if mq:
                if opts['force']:
                    ui.warn(_('source has mq patches applied\n'))
                else:
                    raise util.Abort(_('source has mq patches applied'))
        except error.RepoError:
            pass
        except error.RepoLookupError:
            pass

        # create description
        desc = []
        for n in nodes:
            desc.append(repo[n].description())

        if len(nodes) > 1:
            h = [repo[nodes[0]].hex()]
        else:
            h = []
        h.append(repo[nodes[-1]].hex())

        desc='\n* * *\n'.join(desc) + '\n\n{{mercurial %s}}\n' % (':'.join(h))

        if ui.debugflag:
            ui.debug('mod = %r\n' % (mod,))
            ui.debug('add = %r\n' % (add,))
            ui.debug('rem = %r\n' % (rem,))
            ui.debug('cpy = %r\n' % (cpy,))

        return False, (client, p4rev, p4id, nodes, ctx2, desc, mod, add, rem, cpy)


# --------------------------------------------------------------------------

def incoming(original, ui, repo, source=None, **opts):
    '''show changes that would be pulled from the p4 source repository
    Returns 0 if there are incoming changes, 1 otherwise.
    '''

    done, r = p4client.pullcommon(original, ui, repo, source, **opts)
    if done:
        return r

    limit = opts['limit']
    limit = limit and int(limit) or 0

    client, p4rev, p4id, startrev, changes = r
    for c in changes:
        cl = client.describe(c, local=ui.verbose)
        tags = client.labels(c)

        ui.write(_('changelist:  %d\n') % c)
        # ui.write(_('branch:      %s\n') % branch)
        for tag in tags:
            ui.write(_('tag:         %s\n') % tag)
        # ui.write(_('parent:      %d:%s\n') % parent)
        ui.write(_('user:        %s\n') % cl.user)
        ui.write(_('date:        %s\n') % util.datestr(cl.date))
        if ui.verbose:
            ui.write(_('files:       %s\n') % ' '.join(f[4] for f in cl.files))

        if cl.desc:
            if ui.verbose:
                ui.write(_('description:\n'))
                ui.write(cl.desc)
                ui.write('\n')
            else:
                ui.write(_('summary:     %s\n') % cl.desc.splitlines()[0])

        ui.write('\n')
        limit-=1
        if limit==0:
            break

    return not changes and 1 or 0


def pull(original, ui, repo, source=None, **opts):
    '''Wrap the pull command to look for p4 paths, import changelists'''

    done, r = p4client.pullcommon(original, ui, repo, source, **opts)
    if done:
        return r

    client, p4rev, p4id, startrev, changes = r
    entries = {}
    c = 0

    def memfilectx(context, repo, path, data, islink, isexec):
        'wrapper to handle 3.1 vs older differences'
        try:
            return context.memfilectx(repo=repo, path=path, data=data, islink=islink, isexec=isexec)
        except TypeError:
            return context.memfilectx(path=path, data=data, islink=islink, isexec=isexec, copied=None)

    def getfilectx(repo, memctx, fn):
        'callback to read file data'
        if fn.startswith('.hg'):
            return repo[parent].filectx(fn)

        mode, contents = client.getfile(entries[fn])
        return memfilectx(context, repo, fn, contents, 'l' in mode, 'x' in mode)

    # for clone we support a --startrev option to fold initial changelists
    if startrev:
        if len(changes) < 2:
            raise util.Abort(_('with --startrev there must be at least two revisions to clone'))
        if startrev < 0:
            startrev = changes[0]
        else:
            if changes[0] != startrev:
                raise util.Abort(_('changelist for --startrev not found, first changelist is %s' % changes[0]))

    if client.lowercasepaths:
        ui.note(_("converting pathnames to lowercase.\n"))
    if client.ignorecase:
        ui.note(_("ignoring case in file names.\n"))

    tags = {}
    trim = ui.configbool('perfarce', 'pull_trim_log', False)

    try:
        for c in changes:
            ui.note(_('change %s\n') % c)
            cl = client.describe(c)
            files = client.fstat(c, all=bool(startrev))

            if client.keep:
                if startrev:
                    client.sync(c, all=True, force=True)
                else:
                    client.runs('revert -k', files=[f[0] for f in files], abort=False)
                    client.sync(c, force=True, files=[f[0] for f in files if f[3]=="R"]+
                                                     [f[0] for f in files if f[3]!="R"])

            nodes, match = client.parsenodes(cl.desc)
            if nodes:
                parent = nodes[-1]
                hgfiles = [f for f in repo[parent].files() if f.startswith('.hg')]
                if trim:
                    # remove mercurial id from description in p4
                    cl.desc = cl.desc[:match.start(0)] + cl.desc[match.end(0):]
                    if cl.desc.endswith("\n\n\n"):
                        cl.desc = cl.desc[:-2]
                    client.change(c, cl.desc, update=True)
            else:
                parent = None
                hgfiles = []

            if startrev:
                # no 'p4' data on first revision as it does not correspond
                # to a p4 changelist but to all of history up to a point
                extra = {}
                startrev = None
            else:
                extra = {'p4':c}

            entries.clear()
            if client.ignorecase:
                manifiles = {}
                for n in (p4rev, parent):
                    if n:
                        for f in repo[n]:
                            manifiles[client.normcase(f)] = f
                seen = set()
                for f in files:
                    g = client.normcase(f[4])
                    if g not in seen:
                        entries[manifiles.get(g, f[4])] = f
                        seen.add(g)
            else:
                entries.update((f[4], f) for f in files)

            ctx = context.memctx(repo, (p4rev, parent), cl.desc,
                                 entries.keys() + hgfiles,
                                 getfilectx, cl.user, cl.date, extra)

            p4rev = repo.commitctx(ctx)
            ctx = repo[p4rev]

            for l in client.labels(c):
                tags[l] = (c, ctx.hex())

            repo.pushkey('phases', ctx.hex(), str(phases.draft), str(phases.public))

            ui.note(_('added changeset %d:%s\n') % (ctx.rev(), ctx))

    finally:
        if tags:
            p4rev, p4id = client.find()
            ctx = repo[p4rev]

            if '.hgtags' in ctx:
                tagdata = [ctx.filectx('.hgtags').data()]
            else:
                tagdata = []

            desc = ['p4 tags']
            for l in sorted(tags):
                t = tags[l]
                desc.append('   %s @ %d' % (l, t[0]))
                tagdata.append('%s %s\n' % (t[1], l))

            def getfilectx(repo, memctx, fn):
                'callback to read file data'
                assert fn=='.hgtags'
                return memfilectx(context, repo, fn, ''.join(tagdata), False, False)

            ctx = context.memctx(repo, (p4rev, None), '\n'.join(desc),
                                 ['.hgtags'], getfilectx)
            p4rev = repo.commitctx(ctx)
            ctx = repo[p4rev]
            ui.note(_('added changeset %d:%s\n') % (ctx.rev(), ctx))

    if opts['update']:
        return hg.update(repo, 'tip')


def clone(original, ui, source, dest=None, **opts):
    '''Wrap the clone command to look for p4 source paths, do pull'''

    try:
        client = p4client(ui, None, source)
    except p4notclient:
        if ui.traceback:ui.traceback()
        return original(ui, source, dest, **opts)
    except p4badclient,e:
        raise util.Abort(str(e))

    d = client.runone('info')
    if not isinstance(d,dict) or d['clientName']=='*unknown*' or "clientRoot" not in d:
        raise util.Abort(_('%s is not a valid p4 client') % source)

    if dest is None:
        dest = hg.defaultdest(source)
        ui.status(_("destination directory: %s\n") % dest)
    else:
        dest = ui.expandpath(dest)

    try:
        # Mercurial 1.9
        dest = util.urllocalpath(dest)
    except AttributeError:
        try:
            # Mercurial 1.8.2
            dest = url.localpath(dest)
        except AttributeError:
            dest = hg.localpath(dest)

    if not hg.islocal(dest):
        raise util.Abort(_("destination '%s' must be local") % dest)

    if os.path.exists(dest):
        if not os.path.isdir(dest):
            raise util.Abort(_("destination '%s' already exists") % dest)
        elif os.listdir(dest):
            raise util.Abort(_("destination '%s' is not empty") % dest)

    if client.root == util.pconvert(os.path.abspath(dest)):
        raise util.Abort(_("destination '%s' is same as p4 workspace") % dest)

    repo = hg.repository(ui, dest, create=True)

    opts['update'] = not opts['noupdate']
    opts['force'] = None

    try:
        r = pull(None, ui, repo, source=source, **opts)
    finally:
        fp = repo.opener("hgrc", "w", text=True)
        fp.write("[paths]\n")
        fp.write("default = %s\n" % source)
        fp.write("\n[perfarce]\n")
        fp.write("ignorecase = %s\n" % client.ignorecase)
        fp.write("keep = %s\n" % client.keep)
        fp.write("lowercasepaths = %s\n" % client.lowercasepaths)
        fp.write("tags = %s\n" % client.tags)

        if client.encoding:
            fp.write("encoding = %s\n" % client.encoding)
        cu = ui.config("perfarce", "clientuser")
        if cu:
            fp.write("clientuser = %s\n" % cu)

        move, copy = client.hasmovecopy()
        fp.write("move = %s\n" % move)
        fp.write("copy = %s\n" % copy)

        fp.close()

    return r


# --------------------------------------------------------------------------

def outgoing(original, ui, repo, dest=None, **opts):
    '''Wrap the outgoing command to look for p4 paths, report changes
    Returns 0 if there are outgoing changes, 1 otherwise.
    '''
    done, r = p4client.pushcommon(True, original, ui, repo, dest, **opts)
    if done:
        return r
    client, p4rev, p4id, nodes, ctx, desc, mod, add, rem, cpy = r

    if ui.quiet:
        # for thg integration until we support templates
        for n in nodes:
            ui.write('%s\n' % repo[n].hex())
    else:
        ui.write(desc)
        ui.write('\naffected files:\n')
        cwd = repo.getcwd()
        for char, files in zip('MAR', (mod, add, rem)):
            for f in files:
                ui.write('%s %s\n' % (char, repo.pathto(f[0], cwd)))
        ui.write('\n')


def push(original, ui, repo, dest=None, **opts):
    '''Wrap the push command to look for p4 paths, create p4 changelist'''

    done, r = p4client.pushcommon(False, original, ui, repo, dest, **opts)
    if done:
        return r
    client, p4rev, p4id, nodes, ctx, desc, mod, add, rem, cpy = r

    move, copy = client.hasmovecopy()

    # sync to the last revision pulled, converted or submitted
    for e in client.getpendinglist():
        if e[1]:
            p4id=e[0]

    if client.keep:
        client.sync(p4id)
    else:
        client.sync(p4id, fake=True)
        client.sync(p4id, force=True, files=[client.encodename(f[0]) for f in mod])

    # attempt to reuse an existing changelist
    def noid(d):
        return client.re_hgid.sub("{{}}", d)

    use = ''
    noiddesc = noid(desc)
    for d in client.run('changes -s pending -c %s -l' % client.client):
        if noid(d['desc']) == noiddesc:
            use = d['change']

    def rev(files, change="", abort=True):
        if files:
            ui.note(_('reverting: %s\n') % ' '.join(f[0] for f in files))
            if change:
                change = '-c %s' % change
            client.runs('revert %s' % change,
                        files=[os.path.join(client.partial, f[0]) for f in files],
                        abort=abort)

    # revert any other changes in existing changelist
    if use:
        cl = client.describe(use)
        rev(cl.files, use)

    # revert any other changes to the files
    rev(mod + add + rem, abort=False)

    # sort out the copies from the adds
    rems = {}
    for f in rem:
        rems[f[0]] = True

    moves = []      # src,dest,mode tuples for p4 move
    copies = []     # src,dest tuples for p4 copy
    ntg = []        # integrate
    add2 = []       # additions left after copies removed
    mod2 = []       # list of dest,mode for files modified as well as copied/moved
    for f,g in add:
        if f in cpy:
            r, chg = cpy[f]
            if move and r in rems and rems[r]:
                moves.append((r, f, g))
                rems[r] = False
            elif copy:
                copies.append((r, f))
            else:
                ntg.append((r, f))
            if chg:
                mod2.append((f,g))
        else:
            add2.append((f,g))
    add = add2

    rem = [r for r in rem if rems[r[0]]]

    if ui.debugflag:
        ui.debug('mod = %r+%r\n' % (mod,mod2))
        ui.debug('add = %r\n' % (add,))
        ui.debug('remove = %r\n' % (rem,))
        ui.debug('copies = %r\n' % (copies,))
        ui.debug('moves = %r\n' % (moves,))
        ui.debug('integrate = %r\n' % (ntg,))

    # create new changelist
    use = client.change(use, desc, jobs=opts['job'])

    def modal(note, cmd, files, encoder):
        'Run command grouped by file mode'
        ui.note(note % ' '.join(f[0] for f in files))
        retype = []
        modes = set(f[1] for f in files)
        for mode in modes:
            opt = ""
            if 'l' in mode:
                opt = "symlink"
            if 'x' in mode:
                opt += "+x"
            opt = opt and " -t " + opt
            bunch = [os.path.join(client.partial, encoder(f[0])) for f in files if f[1]==mode]
            if bunch:
                for d in client.run(cmd + opt, files=bunch):
                    if d['code'] == 'stat':
                        basetype, oldmode, keywords, utf16 = client.decodetype(d['type'])
                        if mode=='' and  oldmode=='x':
                            retype.append((d['depotFile'], basetype))

                    if d['code'] == 'info':
                        data = d['data']
                        if "- use 'reopen'" in data:
                            raise util.Abort('p4: %s' % data)
        modes = set(f[1] for f in retype)
        for mode in modes:
            bunch = [f[0] for f in retype if f[1]==mode]
            if bunch:
                client.runs("reopen -t %s"%mode, files=bunch)

    try:
        # now add/edit/delete the files

        if copies:
            ui.note(_('copying: %s\n') % ' '.join(f[1] for f in copies))
            for f in copies:
                client.runs('copy -c %s %s %s' % (use, client.rootpart + f[0], client.rootpart + f[1]))

        if moves:
            modal(_('opening for move: %s\n'), 'edit -c %s' % use,
                  [(f[0],f[2]) for f in moves], client.encodename)

            ui.note(_('moving: %s\n') % ' '.join(f[1] for f in moves))
            for f in moves:
                client.runs('move -c %s %s %s' % (
                    use, client.rootpart + client.encodename(f[0]),
                    client.rootpart + client.encodename(f[1])))

        if ntg:
            ui.note(_('opening for integrate: %s\n') % ' '.join(f[1] for f in ntg))
            for f in ntg:
                client.runs('integrate -c %s -t %s %s' % (use, client.rootpart + f[0], f[1]))

        if mod or mod2:
            modal(_('opening for edit: %s\n'), 'edit -c %s' % use, mod + mod2, client.encodename)

        if mod or add or mod2:
            ui.note(_('retrieving file contents...\n'))
            opener = util_opener(client.rootpart)

            for name, mode in mod + add + mod2:
                ui.debug(_('writing: %s\n') % name)
                if 'l' in mode:
                    opener.symlink(ctx[name].data(), name)
                else:
                    fp = opener(name, mode="w")
                    fp.write(ctx[name].data())
                    fp.close()
                util_setflags(client.localpath(name), 'l' in mode, 'x' in mode)

        if add:
            modal(_('opening for add: %s\n'), 'add -f -c %s' % use, add, lambda n:n)

        if rem:
            modal(_('opening for delete: %s\n'), 'delete -c %s' % use, rem, client.encodename)

        # submit the changelist to p4 if --submit was given
        if opts['submit'] or ui.configbool('perfarce', 'submit', default=False):
            client.submit(use)
        else:
            ui.note(_('pending changelist %s\n') % use)

    except Exception:
        revert(ui, repo, use, **opts)
        raise


# --------------------------------------------------------------------------

def subrevcommon(mode, ui, repo, *changes, **opts):
    'Collect list of changelist numbers from commandline'

    if repo.path.startswith('p4://'):
        dest = repo.path
    else:
        dest = ui.expandpath('default-push', 'default')
    client = p4client(ui, repo, dest)

    if changes:
        try:
            changes = [int(c) for c in changes]
        except ValueError:
            if ui.traceback:ui.traceback()
            raise util.Abort(_('changelist must be a number'))
    elif opts['all']:
        changes = [e[0] for e in client.getpendinglist() if not e[1]]
        if not changes:
            raise util.Abort(_('no pending changelists to %s') % mode)
    else:
        raise util.Abort(_('no changelists specified'))

    return client, changes


def submit(ui, repo, *changes, **opts):
    'submit one or more changelists to the p4 depot.'

    client, changes = subrevcommon('submit', ui, repo, *changes, **opts)

    for c in changes:
        ui.status(_('submitting: %d\n') % c)
        cl = client.describe(c)
        client.submit(c)


def revert(ui, repo, *changes, **opts):
    'revert one or more pending changelists and all opened files.'

    client, changes = subrevcommon('revert', ui, repo, *changes, **opts)

    for c in changes:
        ui.status(_('reverting: %d\n') % c)
        try:
            cl = client.describe(c)
        except Exception,e:
            if ui.traceback:ui.traceback()
            ui.warn('%s\n' % e)
            cl = None

        if cl is not None:
            files = [f[0] for f in cl.files]
            if files:
                ui.note(_('reverting: %s\n') % ' '.join(files))
                client.runs('revert', client=cl.client, files=files, abort=False)

            jobs = [j[0] for j in cl.jobs]
            if jobs:
                ui.note(_('unfixing: %s\n') % ' '.join(jobs))
                client.runs('fix -d -c %d' % c, client=cl.client, files=jobs, abort=False)

            ui.note(_('deleting: %d\n') % c)
            client.runs('change -d %d' %c , client=cl.client, abort=False)


def pending(ui, repo, dest=None, **opts):
    'report changelists already pushed and pending for submit in p4'

    dest = ui.expandpath(dest or 'default-push', dest or 'default')
    client = p4client(ui, repo, dest)

    dolong = opts.get('summary')
    hexfunc = ui.verbose and hex or short
    pl = client.getpendinglist()
    if pl:
        w = max(len(str(e[0])) for e in pl)
        for e in pl:
            if dolong:
                if ui.verbose:
                    cl = client.describe(e[0], local=True)
                ui.write(_('changelist:  %d\n') % e[0])
                if ui.verbose:
                    ui.write(_('client:      %s\n') % e[4])
                ui.write(_('status:      %s\n') % (['pending','submitted'][e[1]]))
                for n in e[2]:
                    ui.write(_('revision:    %s\n') % hexfunc(n))
                if ui.verbose:
                    ui.write(_('files:       %s\n') % ' '.join(f[4] for f in cl.files))
                    ui.write(_('description:\n'))
                    ui.write(e[3])
                    ui.write('\n')
                else:
                    ui.write(_('summary:     %s\n') % e[3].splitlines()[0])
                ui.write('\n')
            else:
                output = []
                output.append('%*d' % (-w, e[0]))
                output.append(['p','s'][e[1]])
                output+=[hexfunc(n) for n in e[2]]
                ui.write("%s\n" % ' '.join(output))


def identify(ui, repo, *args, **opts):
    '''show p4 and hg revisions for the most recent p4 changelist

    With no revision, show a summary of the most recent revision
    in the repository that was converted from p4.
    Otherwise, find the p4 changelist for the revision given.
    '''

    rev = opts.get('rev')
    if rev:
        ctx = repo[rev]
        extra = ctx.extra()
        if 'p4' not in extra:
            raise util.Abort(_('no p4 changelist revision found'))
        changelist = int(extra['p4'])
    else:
        client = p4client(ui, repo, 'p4:///')
        cl = opts.get('changelist')
        if cl:
            rev = None
        else:
            rev = '.'
        p4rev, changelist = client.find(rev=rev, base=opts.get('base'), p4rev=cl)
        ctx = repo[p4rev]

    num = opts.get('num')
    doid = opts.get('id')
    dop4 = opts.get('p4')
    default = not (num or doid or dop4)
    hexfunc = ui.verbose and hex or short
    output = []

    if default or dop4:
        output.append(str(changelist))
    if num:
        output.append(str(ctx.rev()))
    if default or doid:
        output.append(hexfunc(ctx.node()))

    ui.write("%s\n" % ' '.join(output))


cmdtable = {
    # 'command-name': (function-call, options-list, help-string)
    'p4pending':
        (   pending,
            [ ('s', 'summary', None, _('print p4 changelist summary')) ],
            'hg p4pending [-s] [p4://server/client]'),
    'p4revert':
        (   revert,
            [ ('a', 'all', None, _('revert all changelists listed by p4pending')) ],
            'hg p4revert [-a] changelist...'),
    'p4submit':
        (   submit,
            [ ('a', 'all', None, _('submit all changelists listed by p4pending')) ],
            'hg p4submit [-a] changelist...'),
    'p4identify':
        (   identify,
            [ ('b', 'base', None, _('show base revision for new incoming changes')),
              ('c', 'changelist', 0, _('identify the specified p4 changelist')),
              ('i', 'id',   None, _('show global revision id')),
              ('n', 'num',  None, _('show local revision number')),
              ('p', 'p4',   None, _('show p4 revision number')),
              ('r', 'rev',  '',   _('identify the specified revision')),
            ],
            'hg p4identify [-binp] [-r REV]'
        )
}
