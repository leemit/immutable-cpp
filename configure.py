#!/usr/bin/env python -B
"Script that generates the build.ninja file"
from __future__ import print_function

# source files
lib_src  = [
  'array',
]

from optparse import OptionParser
import os
import sys
from glob import glob
from distutils.spawn import find_executable
sys.path.insert(0, 'misc')
import platform_helper
import ninja_syntax

srcdir = os.path.dirname(os.path.abspath(__file__))

parser = OptionParser()
parser.add_option('--platform',
                  help='target platform (' +
                       '/'.join(platform_helper.platforms()) + ')',
                  choices=platform_helper.platforms())
parser.add_option('--host',
                  help='host platform (' +
                       '/'.join(platform_helper.platforms()) + ')',
                  choices=platform_helper.platforms())
parser.add_option('--debug', action='store_true',
                  help='enable debugging extras',)
(options, args) = parser.parse_args()
if args:
    print('ERROR: extra unparsed command-line arguments:', args)
    sys.exit(1)

platform = platform_helper.Platform(options.platform)
if options.host:
    host = platform_helper.Platform(options.host)
else:
    host = platform

# lib_src += ['os_' + platform.platform()]
# lib_h  = ['parse']

BUILD_FILENAME = 'build.ninja'
buildfile = open(BUILD_FILENAME, 'w')
n = ninja_syntax.Writer(buildfile)
n.comment('This file is generated by ' + os.path.basename(__file__) + '.')
n.newline()

n.variable('ninja_required_version', '1.3')
n.newline()

n.comment('The arguments passed to configure.py, for rerunning it.')
n.variable('configure_args', ' '.join(sys.argv[1:]))
env_keys = set(['CXX', 'AR', 'CFLAGS', 'LDFLAGS'])
configure_env = dict((k, os.environ[k]) for k in os.environ if k in env_keys)
if configure_env:
    config_str = ' '.join([k + '=' + configure_env[k] for k in configure_env])
    n.variable('configure_env', config_str + '$ ')
n.newline()

# prefer clang if its in PATH, otherwise default to g++
default_cxx = find_executable('clang')
if default_cxx is None:
  default_cxx = 'g++'

CXX = configure_env.get('CXX', default_cxx)
usingClang = 'clang' in os.path.basename(CXX)

objext = '.o'
if platform.is_msvc():
    CXX = 'cl'
    objext = '.obj'

def src(filename):
    return filename
    # return os.path.join('src', filename)
def built(filename):
    return os.path.join('$builddir', filename)
def doc(filename):
    return os.path.join('doc', filename)
def cc(name, **kwargs):
    return n.build(built(os.path.join('obj', name + objext)), 'cxx', src(name + '.c'), **kwargs)
def cxx(name, **kwargs):
    return n.build(built(os.path.join('obj', name + objext)), 'cxx', src(name + '.cc'), **kwargs)
def binary(name):
    if platform.is_windows():
        exe = name + '.exe'
        n.build(os.path.join('$builddir', 'bin', name), 'phony', exe)
        return exe
    return os.path.join('$builddir', 'bin', name)

if options.debug:
  n.variable('builddir', 'build/debug')
else:
  n.variable('builddir', 'build/release')

n.variable('cxx', CXX)
if platform.is_msvc():
    n.variable('ar', 'link')
else:
    n.variable('ar', configure_env.get('AR', 'ar'))

test_cflags = []

if platform.is_msvc():
    cflags = ['/nologo',  # Don't print startup banner.
              '/Zi',  # Create pdb with debug info.
              '/W4',  # Highest warning level.
              '/WX',  # Warnings as errors.
              '/wd4530', '/wd4100', '/wd4706',
              '/wd4512', '/wd4800', '/wd4702', '/wd4819',
              # Disable warnings about passing "this" during initialization.
              '/wd4355',
              '/GR-',  # Disable RTTI.
              # Disable size_t -> int truncation warning.
              # We never have strings or arrays larger than 2**31.
              '/wd4267',
              '/DNOMINMAX', '/D_CRT_SECURE_NO_WARNINGS',
              '/D_VARIADIC_MAX=10']
    if platform.msvc_needs_fs():
        cflags.append('/FS')
    # ldflags = ['/DEBUG', '/libpath:$builddir\lib']
    ldflags = ['/DEBUG']
    test_cflags = cflags[:]
    if not options.debug:
        cflags += ['/Ox', '/DNDEBUG', '/GL']
        ldflags += ['/LTCG', '/OPT:REF', '/OPT:ICF']
else:
    cflags = ['-g', '-Wall', '-Wextra',
              '-Wimplicit-fallthrough',
              # '-Wno-deprecated',
              # '-Wno-unused-parameter',
              '-std=c++1y',
              '-stdlib=libc++',
              '-fno-rtti',
              '-fvisibility=hidden', '-pipe',
              '-Wno-missing-field-initializers',
              '-Wno-unused-variable'
              # '-Ideps/dist/include'
              ]
              # '-DNINJA_PYTHON="%s"' % options.with_python
    if usingClang:
        cflags += ['-fcolor-diagnostics']
    if platform.is_mingw():
        cflags += ['-D_WIN32_WINNT=0x0501'] # wat?
    
    test_cflags = cflags + ['-DDEBUG=1', '-DUNIT_TEST=1']
    # ldflags = ['-lc++', '-L$builddir/lib']
    ldflags = ['-lc++']
    
    if options.debug:
        cflags += ['-D_GLIBCXX_DEBUG', '-D_GLIBCXX_DEBUG_PEDANTIC', '-DDEBUG=1']
        cflags.remove('-fno-rtti')  # Needed for above pedanticness.
        if usingClang:
            cflags_asan = [
                '-fsanitize=address',
                '-fno-omit-frame-pointer',
                '-fno-optimize-sibling-calls']
            cflags += cflags_asan
            test_cflags += cflags_asan
            ldflags += ['-fsanitize=address']
    else:
        cflags += ['-O3', '-DNDEBUG']
    

libs = []

if platform.is_mingw():
    cflags.remove('-fvisibility=hidden');
    test_cflags.remove('-fvisibility=hidden');
    ldflags.append('-static')
elif platform.is_sunos5():
    cflags.remove('-fvisibility=hidden')
    test_cflags.remove('-fvisibility=hidden')
elif platform.is_msvc():
    pass
# else:
#     if options.profile == 'gmon':
#         cflags.append('-pg')
#         ldflags.append('-pg')
#     elif options.profile == 'pprof':
#         cflags.append('-fno-omit-frame-pointer')
#         libs.extend(['-Wl,--no-as-needed', '-lprofiler'])

def shell_escape(str):
    """Escape str such that it's interpreted as a single argument by
    the shell."""

    # This isn't complete, but it's just enough to make NINJA_PYTHON work.
    if platform.is_windows():
      return str
    if '"' in str:
        return "'%s'" % str.replace("'", "\\'")
    return str

if 'CFLAGS' in configure_env:
    cflags.append(configure_env['CFLAGS'])
    test_cflags.append(configure_env['CFLAGS'])
n.variable('cflags', ' '.join(shell_escape(flag) for flag in cflags))
if 'LDFLAGS' in configure_env:
    ldflags.append(configure_env['LDFLAGS'])
n.variable('ldflags', ' '.join(shell_escape(flag) for flag in ldflags))
n.newline()

if platform.is_msvc():
    n.rule('cxx',
        command='$cxx /showIncludes $cflags -c $in /Fo$out',
        description='CXX $out',
        deps='msvc')
else:
    n.rule('cxx',
        command='$cxx -MMD -MT $out -MF $out.d $cflags -c $in -o $out',
        depfile='$out.d',
        deps='gcc',
        description='CXX $out')
n.newline()

if host.is_msvc():
    n.rule('ar',
           command='lib /nologo /ltcg /out:$out $in',
           description='LIB $out')
elif host.is_mingw():
    n.rule('ar',
           command='cmd /c $ar cqs $out.tmp $in && move /Y $out.tmp $out',
           description='AR $out')
else:
    n.rule('ar',
           command='rm -f $out && $ar crs $out $in',
           description='AR $out')
n.newline()

if platform.is_msvc():
    n.rule('link',
        command='$cxx $in $libs /nologo /link $ldflags /out:$out',
        description='LINK $out')
else:
    n.rule('link',
        command='$cxx $ldflags -o $out $in $libs',
        description='LINK $out')
n.newline()

objs = []

n.comment('Library source files')
for name in lib_src:
    objs += cxx(os.path.join('immutable', name))
# for name in lib_src_asm:
#     objs += asmxx(name)

if platform.is_msvc():
    immutable_lib = n.build(built('lib\immutable.lib'), 'ar', objs)
else:
    immutable_lib = n.build(built('lib/libimmutable.a'), 'ar', objs)
n.newline()

if platform.is_msvc():
    libs.append('immutable.lib')
else:
    libs.append('-limmutable')

all_targets = []


n.comment('Tests')

test_src = [os.path.splitext(path)[0] for path in glob('tests/*.cc')]

# variables = []
test_ldflags = ldflags[:]
test_libs = libs
objs = []

if platform.is_msvc():
  pass # TODO
else:
  test_cflags.append('-I.')
  test_ldflags.append('-L$builddir/lib')

n.variable('test_cflags', test_cflags)
for name in test_src:
    objs += cxx(name, variables=[('cflags', '$test_cflags')])
if platform.is_windows():
    for name in ['includes_normalize_test', 'msvc_helper_test']:
        objs += cxx(name, variables=[('cflags', test_cflags)])

if not platform.is_windows():
    test_libs.append('-lpthread')
test_exe = n.build(binary('test'), 'link', objs, implicit=immutable_lib,
                   variables=[('ldflags', test_ldflags),
                              ('libs', test_libs)])
n.newline()
all_targets += test_exe


if not host.is_mingw():
    n.comment('Regenerate build files if build script changes.')
    n.rule('configure',
           command='${configure_env}python configure.py $configure_args',
           generator=True)
    n.build('build.ninja', 'configure',
            implicit=['configure.py', os.path.normpath('misc/ninja_syntax.py')])
    n.newline()

n.default(test_exe)
n.newline()
n.build('all', 'phony', all_targets)

print('wrote %s.' % BUILD_FILENAME)
