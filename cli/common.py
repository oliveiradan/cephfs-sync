# -*- coding: utf-8 -*-
"""
This module is responsible for storing common code
"""

import contextlib
import datetime
import errno
import ipaddress
import logging
import os
import pprint
import re
import signal
import string
import sys
import textwrap
import tempfile
import time

from gevent import joinall
from itertools import groupby
from pssh.clients.native import ParallelSSHClient
from pssh.clients.native.single import SSHClient as SingleSSHClient
from pssh.utils import enable_host_logger
from subprocess import Popen, PIPE



def is_not_empty(data_str):
    return bool(data_str != None and (data_str and 
                                      data_str.strip()))


def is_empty(data_str):
    return bool(data_str == None or (not data_str and 
                                     not data_str.strip()))


def log_timefy():
    current_date_time = datetime.datetime.now()
    return current_date_time.strftime("%Y%m%d_%H%M%S_%f")


def cmd_launcher(**kwargs):
    cmd_string = kwargs.get('cmd', None)
    env_string = kwargs.get('env', None)
    timeout_string = kwargs.get('timeout', None)
    workdir_string = kwargs.get('cwd', None)
    workdir_original = None

    if is_empty(env_string):
        env_string = os.environ

    if is_empty(timeout_string):
        timeout_string = 30

    if is_empty(cmd_string):
        return 256, '', ''

    # Handling directory changes
    if is_not_empty(workdir_string):
        workdir_original = os.getcwd()
        os.chdir(workdir_string)

    """
    If we need to log what's being executed:
    logger.info('Executing: ' + cmd_string)
    """
    process = Popen([cmd_string],
                    shell=True,
                    stdout=PIPE,
                    stderr=PIPE,
                    env=env_string,
                    bufsize=0)

    if is_not_empty(workdir_original):
        os.chdir(workdir_original)

    process_counter = 0
    process_retcode = None
    handle_process = True
    stdout = ''
    stderr = ''
    while handle_process:
        process_counter += 1
        cout, cerr = process.communicate()
        stdout += str(cout)
        stderr += str(cerr)

        process.poll()
        process_retcode = process.returncode
        if process_retcode != None:
            break
        if process_counter == timeout_string:
            os.kill(process.pid, signal.SIGQUIT)
        if process_counter > timeout_string:
            os.kill(process.pid, signal.SIGKILL)
            process_retcode = -9
            break

        time.sleep(1)

    return (process_retcode, stdout, stderr)


def eval_launcher_returns(cmd,
                          check_cmd_success=False,
                          handout_err_msg=False):
    rc, stdout, stderr = cmd_launcher(cmd=cmd)
    # Only checks if the cmd is/was successful
    if check_cmd_success and not handout_err_msg:
        return bool(rc)

    """
    If not checking out success only, we still have the option to
    pass along the error msgs, or assert in case we are not handing
    out the errors to the caller.
    """
    if not handout_err_msg and not check_cmd_success:
        assert (rc == 0), 'Error while executing the command {}. \
                           Error message: {}'.format(cmd, stderr)
    return rc, stdout, stderr


def proc_open(cmd):
    """
    Runs cmd and returns stdout and stderr
    """
    stdout=[]
    stderr=[]
    proc_result = Popen(cmd, stdout=PIPE, stderr=PIPE)
    for line in proc_result.stdout:
        line = line.decode('ascii')
        stdout.append(line.rstrip('\n'))
    for line in proc_result.stderr:
        line = line.decode('ascii')
        stderr.append(line.rstrip('\n'))
    proc_result.wait()
    return(stdout, stderr)


def does_file_exist(file_path):
    return (os.path.exists(file_path) and
            os.path.isfile(file_path))


def does_dir_exist(dir_path):
    return (os.path.exists(dir_path) and
            os.path.isdir(dir_path))


def does_tool_exist(tool_name):
    return does_file_exist(tool_name)


def is_it_cephfs(src_path='', host=None):
    """
    Instead of matching a $src_path from a list of mounting points, then
    check if that is a 'cephfs' file system, we just test it straight with:

    $ stat -f /mnt/cephfs/data/isos/openSUSE-Tumbleweed-DVD-x86_64-Snapshot20190202-Media.iso

    Part of the output we expect *if we are running it on a 'cephfs'*, is:
        ...
        ID: 9892f072c60473e3 Namelen: 255     Type: ceph
        ...

        OR, *if we are not running it on a 'cephfs'*:

        ...
        ID: b333aa8538b776cf Namelen: 255     Type: btrfs
        ...
    """

    """cmd = "stat -f {} | egrep -i 'type: ceph' | wc -l".format(src_path)"""
    cephfs_check = 'Type: ceph'
    cmd = 'stat -f {}'.format(src_path)

    if host != None:
        ssh_client = ParallelSSHClient([host], 'root')
        #enable_host_logger()
        ssh_client_output = ssh_client.run_command(cmd)
        for host_name, host_output in ssh_client_output.items():
            for output_line in host_output.stdout:
                if cephfs_check in output_line:
                    return True

    else:
        rc, stdout, stderr = cmd_launcher(cmd=cmd)
        if rc != 0:
            raise Exception('Error while executing the command {}. \
                            Error message: {}'.format(cmd, stderr))

        return (cephfs_check in stdout)
    return False


def is_snapshot_enabled(src_path='', host=None):
    if src_path and host == None:
        snap_dir = src_path + '/.snap'
        if does_dir_exist(snap_dir):
            return True

    if host != None and src_path:
        read_file_check = 'cannot read file system information'
        snap_dir = src_path + '/.snap'
        cmd = 'stat -f {}'.format(snap_dir)
        ssh_client = ParallelSSHClient([host], 'root',)
        #enable_host_logger()
        ssh_client_output = ssh_client.run_command(cmd)
        for host_name, host_output in ssh_client_output.items():
            for output_line in host_output.stdout:
                if read_file_check in output_line:
                    return False
        return True
    return False

def is_it_cephfs_snapshot_enabled(src_path='', host=None):
    return is_it_cephfs(src_path, host) and is_snapshot_enabled(src_path, host)


def snapshot_dir(src_path='', suffix=''):
    if src_path:
        snap_dir = src_path + '/.snap/' + suffix
        rc, stdout, stderr = eval_launcher_returns(cmd=('mkdir ' + snap_dir), 
                                                    check_cmd_success=True, 
                                                    handout_err_msg=True)
        return rc, stdout, stderr
    return -1, '', ''


def rsync_dir(src_path='', target_dir='', log_file=''):
    if src_path and target_dir and log_file:
        """
            If we are using '-e ssh', we can also do:
                $ rsync -aHAXxv --numeric-ids --delete --progress -e \ 
                    "ssh -T -c arcfour -o Compression=no -x" user@<source>:<source_dir> <dest_dir>

            Tested with Gbit Network and got 40MB/s -> up to 64MB/s.
            Also, on SSD to SSD transfer, up to 110MB/s.

            PS: We are keeping 'X' out of the options, due to: 
                'Operation not supported (95)\nrsync: rsync_xal_set: lsetxattr' errors.
        """
        rsync_cmd = 'rsync -aHAxv --numeric-ids --delete --progress --log-file={} {} root@{}'.format(log_file, src_path, target_dir)
        rc, stdout, stderr = eval_launcher_returns(cmd=rsync_cmd, 
                                                    check_cmd_success=True, 
                                                    handout_err_msg=True)
        return rc, stdout, stderr
    return -1, '', ''


def check_host_address(host):
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def ssh_host(host='', directory=''):
    if host and directory:
        with tempfile.NamedTemporaryFile() as local_test_file:
            local_test_file.write (b'Testing CephFS_Sync')
            ssh_client = ParallelSSHClient([host], 'root',)
            target_file = (directory + '/cephfs_sync_' + log_timefy())
            ssh_copy = ssh_client.scp_send(local_test_file.name, target_file)
            #enable_host_logger()
            try:
                joinall(ssh_copy, raise_error=True)
            except Exception:
                return False
    return True


def ping_host(host):
    if host:
        ping_result = proc_open(['/usr/bin/ping', '-c', '2', host])
        for line in ping_result[0]:
            if re.match(r'\d+ bytes from', line):
                return True
    return False


def has_root_privileges():
    if os.getuid !=0:
        return False
    return True


def check_root_privileges():
    """
    This function checks if the current user is root.
    If the user is not root it exits immediately.
    """
    if os.getuid() != 0:
        # check if root user
        PrettyPrinter.println(PrettyPrinter.red("Root privileges are required to run this tool"))
        sys.exit(1)


def requires_root_privileges(func):
    """
    Function decorator to ensure function is executed by a user with root privileges.
    """
    # pylint: disable=C0111
    def func_wraper(*args, **kwargs):
        check_root_privileges()
        return func(*args, **kwargs)
    return func_wraper


def check_terminal_utf8_support():
    """
    Checks whether the terminal supports UTF-8 glyphs.
    """
    symbol = u"\u23F3"
    if sys.stdout.encoding is None:
        return False
    try:
        symbol.encode(sys.stdout.encoding)
        return True
    except UnicodeEncodeError:
        return False


def get_terminal_size():
    """
    Returns the number of rows and columns of the current terminal
    """
    with os.popen('stty size', 'r') as f:
        rows, columns = f.read().split()
    try:
        return int(rows), int(columns)
    except ValueError:
        return 80, 80


max_text_width=60
default_text_prefix=' '
default_indent_size=2
default_text_placeholder='...'
def get_txt_indented(text='', text_prefix=default_text_prefix,
                     indent_size=default_indent_size,
                     max_width=max_text_width,
                     txt_placeholder=default_text_placeholder):
    new_text=textwrap.indent(text, (text_prefix * indent_size))
    return new_text


def get_txt_dedented(text='', text_prefix=default_text_prefix,
                     dedent_size=default_indent_size):
    if dedent_size == 0:
        return textwrap.dedent(text)

    consecutive_list = get_consecutive_chars(text)
    for description, count in consecutive_list:
        if description == text_prefix:
            break

    new_text=textwrap.dedent(text)
    new_size=0 if (count - dedent_size) < 0 else (count - dedent_size)
    new_text=textwrap.indent(text, (text_prefix * new_size))
    return new_text


def get_consecutive_chars(text):
    groups = groupby(text)
    consecutive_list = [(description, sum(1 for _ in group))
                        for description, group in groups]
    return consecutive_list


class PrettyPrinter(object):
    """
    Helper class to pretty print
    """

    _PP = pprint.PrettyPrinter(indent=1)

    class Colors(object):
        """
        Color enum
        """
        HEADER = '\x1B[95m'
        BOLD = '\x1B[1m'
        UNDERLINE = '\x1B[4m'
        RED = '\x1B[38;5;196m'
        GREEN = '\x1B[38;5;83m'
        DARK_GREEN = '\x1B[38;5;34m'
        YELLOW = '\x1B[38;5;226m'
        DARK_YELLOW = '\x1B[38;5;178m'
        BLUE = '\x1B[38;5;33m'
        MAGENTA = '\x1B[38;5;198m'
        CYAN = '\x1B[38;5;43m'
        ORANGE = '\x1B[38;5;214m'
        PURPLE = '\x1B[38;5;134m'
        GREY = '\x1B[38;5;245m'
        LIGHT_YELLOW = '\x1B[38;5;228m'
        LIGTH_PURPLE = '\x1B[38;5;225m'
        ENDC = '\x1B[0m'

    @classmethod
    def _format(cls, color, text):
        """
        Generic pretty print string formatter
        """
        return u"{}{}{}".format(color, text, cls.Colors.ENDC)

    @classmethod
    def header(cls, text):
        """
        Formats text as header
        """
        return cls._format(cls.Colors.HEADER, text)

    @classmethod
    def bold(cls, text):
        """
        Formats text as bold
        """
        return cls._format(PrettyPrinter.Colors.BOLD, text)

    @classmethod
    def blue(cls, text):
        """
        Formats text as blue
        """
        return cls._format(cls.Colors.BLUE, text)

    @classmethod
    def grey(cls, text):
        """
        Formats text as grey
        """
        return cls._format(PrettyPrinter.Colors.GREY, text)

    @staticmethod
    def light_purple(text):
        """
        Formats text as light_purple
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.LIGTH_PURPLE, text)

    @staticmethod
    def green(text):
        """
        Formats text as green
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.GREEN, text)

    @staticmethod
    def dark_green(text):
        """
        Formats text as dark_green
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.DARK_GREEN, text)

    @staticmethod
    def yellow(text):
        """
        Formats text as yellow
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.YELLOW, text)

    @staticmethod
    def dark_yellow(text):
        """
        Formats text as dark_yellow
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.DARK_YELLOW, text)

    @staticmethod
    def red(text):
        """
        Formats text as red
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.RED, text)

    @staticmethod
    def orange(text):
        """
        Formats text as orange
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.ORANGE, text)

    @staticmethod
    def cyan(text):
        """
        Formats text as cyan
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.CYAN, text)

    @staticmethod
    def magenta(text):
        """
        Formats text as magenta
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.MAGENTA, text)

    @staticmethod
    def purple(text):
        """
        Formats text as purple
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.PURPLE, text)

    @staticmethod
    def info(text):
        """
        Formats text as info
        """
        return PrettyPrinter._format(PrettyPrinter.Colors.LIGHT_YELLOW, text)

    @staticmethod
    def p_header(text):
        """
        Prints text formatted as header
        """
        print(PrettyPrinter.header(text))

    @staticmethod
    def p_bold(text):
        """
        Prints text formatted as bold
        """
        sys.stdout.write(PrettyPrinter.bold(text))
        sys.stdout.flush()

    @staticmethod
    def pl_bold(text):
        """
        Prints text formatted as bold with newline in the end
        """
        sys.stdout.write(u"{}\n".format(PrettyPrinter.bold(text)))
        sys.stdout.flush()

    @classmethod
    def print(cls, text):
        """
        Prints text as is
        """
        sys.stdout.write(text)
        sys.stdout.flush()

    @classmethod
    def println(cls, text=None):
        """
        Prints text as is with newline in the end
        """
        if text:
            sys.stdout.write(u"{}\n".format(text))
            sys.stdout.flush()
        else:
            sys.stdout.write(u"\n")
            sys.stdout.flush()

    @classmethod
    def p_blue(cls, text):
        """
        Prints text formatted as blue
        """
        cls.print(cls.blue(text))

    @classmethod
    def pl_blue(cls, text):
        """
        Prints text formatted as blue
        """
        cls.println(cls.blue(text))

    @classmethod
    def p_green(cls, text):
        """
        Prints text formatted as green
        """
        cls.print(cls.green(text))

    @classmethod
    def pl_green(cls, text):
        """
        Prints text formatted as green
        """
        cls.println(cls.green(text))

    @staticmethod
    def p_red(text):
        """
        Prints text formatted as red
        """
        print(PrettyPrinter.red(text))

    @staticmethod
    def flush():
        """
        Flush stdout
        """
        sys.stderr.flush()
        sys.stdout.flush()

    @staticmethod
    def format_dict(dict_obj):
        """
        Formats a dict structure using pprint formatter
        """
        return PrettyPrinter._PP.pformat(dict_obj)


class PrettyFormat(object):
    OK = PrettyPrinter.green(PrettyPrinter.bold(u"\u2713")) \
        if check_terminal_utf8_support() else PrettyPrinter.green("OK")

    FAIL = PrettyPrinter.red(u"\u274C") \
        if check_terminal_utf8_support() else PrettyPrinter.red("Fail")

    WAITING = PrettyPrinter.orange(u"\u23F3") \
        if check_terminal_utf8_support() else PrettyPrinter.orange("Running")


def print_progress_bar(progress_array, iteration, prefix='', suffix='', bar_length=100):
    """
    Prints a progress bar
    """
    import json
    str_format = "{0:.1f}"
    total = len(progress_array)
    percents = str_format.format(100 * (iteration / float(total)))
    fill_length = int(round(bar_length / float(total)))
    bar_symbol = ''
    for idx, pos in enumerate(progress_array):

        if idx == iteration:
            bar_symbol += (PrettyPrinter.yellow(u'█') * fill_length)
        elif pos is None:
            bar_symbol += ('-' * fill_length)
        elif pos:
            bar_symbol += (PrettyPrinter.green(u'█') * fill_length)
        else:
            bar_symbol += (PrettyPrinter.red(u'█') * fill_length)

    # pylint: disable=W0106
    sys.stdout.write(u'\x1b[2K\r{} |{}| {}{} {}\n'
                     .format(prefix, bar_symbol, percents, '%', suffix)),
    sys.stdout.flush()

