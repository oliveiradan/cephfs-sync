# -*- coding: utf-8 -*-
# pylint: disable=too-many-branches,too-many-statements
"""
CephFS-Sync CLI
"""

"""
from __future__ import absolute_import
from __future__ import print_function
"""

import logging.config
import logging
import os
import re
import signal
import sys
import time

import click
import yaml

from config import Config
from common import has_root_privileges
from common import PrettyPrinter as PP, PrettyFormat as PF
from common import log_timefy
from common import does_file_exist
from common import does_dir_exist
from common import does_tool_exist
from common import is_it_cephfs
from common import is_snapshot_enabled
from common import is_it_cephfs_snapshot_enabled
from common import snapshot_dir
from common import rsync_dir
from common import check_host_address
from common import ping_host
from common import get_txt_indented
from common import get_txt_dedented
from common import ssh_host


logger = logging.getLogger(__name__)

def _setup_logging():
    """
    Logging configuration
    """
    if Config.LOG_LEVEL == "silent":
        return

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'standard': {
                'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            },
        },
        'handlers': {
            'file': {
                'level': Config.LOG_LEVEL.upper(),
                'filename': Config.LOG_FILE_PATH,
                'class': 'logging.FileHandler',
                'formatter': 'standard'
            },
        },
        'loggers': {
            '': {
                'handlers': ['file'],
                'level': Config.LOG_LEVEL.upper(),
                'propagate': True,
            },
        },
        'config': {
            'file': {
                'filename': Config.CONFIG_FILE_PATH,
                'formatter': 'standard'
            }
        }
    })


def _dispatch_msg(message='', color='', flag='', font='', indent=0, err_raise=False):

    if message:
        new_message = message

        if Config.IS_DRY_RUN or Config.IS_VERBOSE:
            new_message = message
            if (flag == PF.OK) or (flag == PF.FAIL) or (flag == PF.WAITING):
                new_message = (flag + ' ' + new_message)

            if color == PP.Colors.DARK_YELLOW:
                new_message = (PP.dark_yellow(new_message))

            if color == PP.Colors.GREY:
                new_message = (PP.grey(new_message))

            if color == PP.Colors.RED:
                new_message = (PP.red(new_message))

            if font == PP.Colors.BOLD:
                new_message = (PP.bold(new_message))

            if indent > 0:
                new_message = get_txt_indented(text=new_message, indent_size=indent)

            PP.println("{}".format(new_message))
            return

        if not Config.IS_DRY_RUN:
            if indent > 0:
                new_message = get_txt_indented(text=new_message, indent_size=indent)
            logger.info(new_message)

            if err_raise:
                raise SystemExit('\n' + message)
            return


def _check_root_access():
    _dispatch_msg(message="CephFS_Sync Remote Sync Tool CLI.", color=PP.Colors.GREY)

    status_message=('Checking for root privileges ...')
    _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)

    indent=2
    if has_root_privileges:
        status_message=('root privileges ...')
        _dispatch_msg(message=status_message, flag=PF.OK, font=PP.bold, indent=indent)
    else:
        Config.ERROR_COUNT += 1
        status_message=("Root privileges are required to run this tool!")
        _dispatch_msg(message=status_message, color=PP.Colors.RED)
        sys.exit(1)


def _check_needed_tools():
    needed_tools = ['/usr/bin/rsync', '/usr/bin/ping']
    status_message=('\nChecking for needed tools ...')
    _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)

    indent=2
    for tool in needed_tools:
        status_message=('{} is available ...'.format(tool))
        if does_tool_exist(tool):
            _dispatch_msg(message=status_message, flag=PF.OK, font=PP.bold, indent=indent)
        else:
            Config.ERROR_COUNT += 1
            _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.bold, indent=indent)
            exit(1)


def _load_conf_file(conf_file):
    status_message=("\nParsing Config file: {} ...".format(conf_file))
    _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)

    with open(conf_file, 'r') as yml_document:
        sync_points = yaml.safe_load(yml_document)

        sync_point_info = {}
        for cephfs_sync in sync_points['cephfs_synchronization']:
            for sync_point in cephfs_sync:
                sync_description = cephfs_sync['sync_description']
                source_location  = cephfs_sync['source_location']
                target_location  = cephfs_sync['target_location']

                """ Filter Possible Errors/Duplicates by 'source' """
                sync_point_info[source_location] = target_location
        _work_sync_point(sync_point_info)


def _work_sync_point(sync_points):
    """ We validate each source before spending time trying to sync it """
    for srcdir, tgtdir in sync_points.items():
        status_message=('\nChecking source directory: {} ...'.format(srcdir))
        _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)

        indent=2
        if srcdir.find(':') != -1:
            status_message=(' Source directory: {} *must be local* !'.format(srcdir))
            _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=indent, err_raise=True)
            if not Config.IS_DRY_RUN:
                exit(1)

        if not does_dir_exist(srcdir):
            Config.ERROR_COUNT += 1
            status_message=(' Source directory: {} does not exist!'.format(srcdir))
            _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=indent, err_raise=True)

        else:
            status_message=(' Source directory: {} does exist!'.format(srcdir))
            _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=indent)

            """ If source does exist, validate it is 'CephFS' """
            if not is_it_cephfs(srcdir):
                Config.ERROR_COUNT += 1
                status_message=(" Source point: {} is not a *CephFS*!".format(srcdir))
                _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=indent, err_raise=True)

            else:
                status_message=(" Source point: {} is *CephFS*!".format(srcdir))
                _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=indent)

                if is_snapshot_enabled(srcdir):
                    status_message=(" Source point: {} has *Snapshot* feature enabled!".format(srcdir))
                    _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=indent)

                else:
                    Config.ERROR_COUNT += 1
                    status_message=(" Source point: {} does not have *Snapshot* feature enabled!".format(srcdir))
                    _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=indent, err_raise=True)


        """ We validate each target before spending time trying to sync it """
        status_message=('Checking target host/directory: {} ...'.format(tgtdir))
        _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)

        target_host=str(tgtdir)
        target_directory=str(tgtdir)
        target_host=re.match("(.*?):/",target_host).group()[:-2]
        target_directory=target_directory[(re.match("(.*?):/",target_directory).end() - 1):]
        target_host.strip()
        indent=2
        is_target_host_ready=False
        if target_host:
            status_message=('Trying to ping target host: {} ...'.format(target_host))
            _dispatch_msg(message=status_message, flag=PF.WAITING, font=PP.Colors.BOLD, indent=indent)

            if ping_host(target_host):
                is_target_host_ready = True
                status_message=('Host {} has replied to ping! '.format(target_host))
                _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=(indent * 2))

            else:
                Config.ERROR_COUNT += 1
                status_message=('Host {} has not replied to ping! '.format(target_host))
                _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=(indent * 2))

        else:
            Config.ERROR_COUNT += 1
            status_message=('Could not get the target host: {} ...'.format(target_host))
            _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=indent)
            exit(1)


        """
        Can we ssh in without any problems?
        We need to be able to SSH in without passwords or any user interaction.
        That's the same requirement as DeepSea or even Rsync.
        """
        if is_target_host_ready and target_directory:
            _work_remote_sync_point(target_host, target_directory)
            if not Config.IS_DRY_RUN:
                _run_remote_sync(srcdir, target_host, target_directory)
        else:
            Config.ERROR_COUNT += 1
            status_message=("Could not get proper target host '{}' and directory '{}' !".format(target_host, target_directory))
            _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.RED, indent=indent, err_raise=True)


def _work_remote_sync_point(target_host, target_directory):
    indent=2
    if target_host and target_directory:
        status_message=('Trying to access target host/directory [root@{}] ...'.format(target_host + ':' + target_directory))
        _dispatch_msg(message=status_message, flag=PF.WAITING, font=PP.Colors.BOLD, indent=indent)

        """ Try to establish SSH session """
        if ssh_host(target_host, target_directory):
            status_message=('SSH access to host [{}] worked! '.format(target_host))
            _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=(indent * 2))

        else:
            Config.ERROR_COUNT += 1
            status_message=('Could not SSH access to host [{}] !'.format(target_host))
            _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=(indent * 2))


def _check_errors():
    status_message=('\n\nSummary: ')
    _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)

    indent=2
    if Config.ERROR_COUNT > 0:
        status_message=(' There were {}+ errors found! Please, solve the issues pointed out before running CephFS_Sync! \n'.format(Config.ERROR_COUNT))
        _dispatch_msg(message=status_message, flag=PF.FAIL, font=PP.Colors.BOLD, indent=indent, err_raise=True)

    else:
        status_message=(' No errors found! CephFS_Sync seems to be able to work.')
        _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=indent)


def _run_remote_sync(srcdir, target_host, target_directory):
    """
    I suspect the sync logic will look something like this:

    1. On $source, snapshot the tree.
    2. Sync $source/snap to $target, restarting as required
        a.  This would benefit from rsync or similar patched with knowledge about CephFS's 
            recursive mtime for efficiency, but that is optional
    3. Once $target has been synced, snapshot $target
    4. Now $source/snap and $target/snap are in sync

    The target snapshot in the final step is also necessary since during the sync, $target is inconsistent.
    This needs to be run periodically, which should be configurable.
    And also in some intervals, old snaps need to be removed. That also should be configurable.
    """
    if Config.IS_DRY_RUN:
        pass
    else:
        status_message=('\nTrying to sync: ')
        _dispatch_msg(message=status_message, color=PP.Colors.DARK_YELLOW)
        indent=2
        status_message=('{} -> {}:{} ...'.format(srcdir, target_host, target_directory))
        _dispatch_msg(message=status_message, flag=PF.WAITING, font=PP.Colors.BOLD, indent=indent)

        timestamp = log_timefy()
        snap_dir = '/.snap/' + timestamp
        local_src_snap_dir = srcdir + snap_dir
        remote_target_dir = target_host + ':' + target_directory +  '/' + timestamp
        remote_target_snap_dir = remote_target_dir + snap_dir
        """ Step #1: On $source, snapshot the tree. """
        rc, stdout, stderr = snapshot_dir(srcdir, timestamp)
        if rc != 0:
            raise Exception('Error while creating the snapshot directory. \
                            Error message: {}'.format(stderr))
        status_message=('Snapshotting source directory: {} to: {} ...'.format(srcdir, local_src_snap_dir))
        _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=(indent * 2))

        """ Step #2. Sync $source/snap to $target, restarting as required 
            We are using rsync here, but this could be any other mechanism.
        """
        rc, stdout, stderr = rsync_dir(local_src_snap_dir, remote_target_dir)
        if rc != 0:
            raise Exception('Error while running rsync. \
                            Error message: {}'.format(stderr))
        status_message=('RSyncing source directory: {} to: {} ...'.format((srcdir + snap_dir), 
                                                                          (target_directory +  '/' + timestamp)))
        _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=(indent * 2))

        """ Step #3. Once $target has been synced, snapshot $target 
            Only if the target directory is a CephFS, and supports snapshots
        """
        if is_it_cephfs_snapshot_enabled(target_directory, target_host):
            status_message=('Snapshotting target directory: {} to: {} ...'.format(remote_target_dir, remote_target_snap_dir))
            _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=(indent * 2))
        else:
            status_message=('Target directory [{}] does not support *Snapshotting* ... '.format(target_directory))
            _dispatch_msg(message=status_message, flag=PF.OK, font=PP.Colors.BOLD, indent=(indent * 2))



@click.command()
@click.option('-c', '--conf-file', required=True,
              envvar='CEPHFS_SYNC_CONF_FILE', type=click.Path(dir_okay=False),
              help=".yml config file to be used for directory structure synchronization. (default: '' ).")
@click.option('-l', '--log-level', default='info',
              type=click.Choice(["info", "error", "debug", "silent"]),
              help="sets log level (default: info)")
@click.option('--log-file', default='/var/log/cephfs-sync.log',
              type=click.Path(dir_okay=False),
              help="the file path for the log to be stored (default: /var/log/cephfs-sync.log).")
@click.option('--dry-run', is_flag=True,
              help="Checks for the config file and results.")
@click.option('--verbose', is_flag=True,
              help="prints verbose messages.")
def cli(conf_file, log_level, log_file, dry_run, verbose):
    """
    CephFS_Sync CLI.
    """
    Config.CONFIG_FILE_PATH = conf_file
    Config.LOG_LEVEL = log_level
    Config.LOG_FILE_PATH = log_file
    Config.IS_DRY_RUN = dry_run
    Config.IS_VERBOSE = verbose

    _setup_logging()
    _check_root_access()
    _check_needed_tools()
    _load_conf_file(conf_file)
    _check_errors()


if __name__ == "__main__":
    os.system('clear')
    cli()

