[![Build Status](https://travis-ci.org/SUSE/CephFS_Sync.svg?branch=master)](https://travis-ci.org/SUSE/CephFS_Sync)
# CephFS_Sync
A tool for synchronizing CephFS Snapshots [Ceph](https://github.com/ceph/ceph) to a remote server/cluster.

The main goal is to copy, and synchronize Snapshots remotely. The tool allows the use of a configuration file (yaml format) so multiple sources and targets (1 to 1 relationship) can be set. 

With that, having multiple config files and using `cron jobs`, would allow us to have more flexibility with sources, and time we want to have Snapshots synced. 

## Status
CephFS_Sync currently supports the following functionality:

- Different configuration files
- Local/Source copy *must be* CephFS and have *Snapshot feature* enabled
- Target file system can be of any format. In case it is `CephFS`, a snapshot will also be taken to guarantee two-way sync. 

## Get Involved
To learn more about CephFS_Sync and some other tools, take a look at the [Wiki](https://github.com/SUSE/Extra_Tools/wiki).

If you think you've found a bug or would like to suggest an enhancement, please submit it via the [bug tracker](https://github.com/oliveiradan/cephfs-sync/issues/new) on GitHub.

If you would like to contribute to CephFS_Sync, refer to the [contribution guidelines](https://github.com/oliveiradan/cephfs-sync/blob/master/contributing.md).

## Usage
Quick things to know: 
    - One must have *Root privileges* to run this tool.
    - There must be a *Passwordless login* in between the *sources* and *targets*. Same requirement as `[Rsync]`(), otherwise user interaction is required.


When we type `$ cephfs_sync --help`, the following options are shown: 
```
Usage: cephfs_sync.py [OPTIONS]

  CephFS_Sync CLI.

Options:
  -c, --conf-file FILE            .yml config file to be used for directory
                                  structure synchronization. (default: '' ).
                                  [required]
  -l, --log-level [info|error|debug|silent]
                                  sets log level (default: info)
  --log-file FILE                 the file path for the log to be stored
                                  (default: /var/log/cephfs-sync.log).
  --dry-run                       Checks for the config file and results.
  --verbose                       prints verbose messages.
  --help                          Show this message and exit.
```

The format of the configuration file, is as follows: 
```
$ cat syncparams.yml 
cephfs_synchronization:
  - {sync_description: Synchronizing Point A, source_location: /src_cephfs_dir1, target_location: "server2:/dst_backups/src_cephfs_dir1/"}
  - {sync_description: Synchronizing Point B, source_location: /src_cephfs_dir2, target_location: "server3:/dst_backups/src_cephfs_dir2/"}
  - {sync_description: Synchronizing Point C, source_location: /src_cephfs_dir5, target_location: "server1:/dst_backups/src_cephfs_dir5/"}
  - {sync_description: Synchronizing Point D, source_location: /src_cephfs_dir10, target_location: "192.168.20.10:/dst_backups/src_cephfs_dir10/"}
```

Where: 
    - `sync_description` is purely informational, and used as a note for the administrator.
    - `source_location` is the source directory tree structure we want to synchronize to a remote location. 
    - `target_location` is either the *hostname* or *ip address* of the target host and directory where a copy of the `source_location` structure will be copied `(rsynced)` to.

After we have the config file the way we want, we can run `cephfs_sync -c syncparams2.yml --dry-run` and check on errors (ie.): 
```
CephFS_Sync Remote Sync Tool CLI.
Checking for root privileges ...
  ✓ root privileges ...

Checking for needed tools ...
  ✓ /usr/bin/rsync is available ...
  ✓ /usr/bin/ping is available ...

Parsing Config file: syncparams.yml ...

Checking source directory: /storage/work/SUSE/suse-dev/cephfs_sync/tests/src ...
  ✓  Source directory: /storage/work/SUSE/suse-dev/cephfs_sync/tests/src does exist!
  ❌  Source point: /storage/work/SUSE/suse-dev/cephfs_sync/tests/src is not a *CephFS*!
Checking target host/directory: testserver:/storage/work/SUSE/suse-dev/cephfs_sync/tests/tgt ...
  ⏳ Trying to ping target host: testserver ...
    ❌ Host testserver has not replied to ping! 
  ❌ Could not get proper target host 'testserver' and directory '/storage/work/SUSE/suse-dev/cephfs_sync/tests/tgt' !

Checking source directory: /home/doliveira/test2 ...
  ❌  Source directory: /home/doliveira/test2 does not exist!
Checking target host/directory: testserver:/home/doliveira/test2B ...
  ⏳ Trying to ping target host: testserver ...
    ❌ Host testserver has not replied to ping! 
  ❌ Could not get proper target host 'testserver' and directory '/home/doliveira/test2B' !

Checking source directory: /home/doliveira/test10A ...
  ❌  Source directory: /home/doliveira/test10A does not exist!
Checking target host/directory: testserver2:/home/doliveira/test10B ...
  ⏳ Trying to ping target host: testserver2 ...
    ❌ Host testserver2 has not replied to ping! 
  ❌ Could not get proper target host 'testserver2' and directory '/home/doliveira/test10B' !

Checking source directory: /storage/work/SUSE/suse-dev/cephfs_sync/tests/tgt ...
  ✓  Source directory: /storage/work/SUSE/suse-dev/cephfs_sync/tests/tgt does exist!
  ❌  Source point: /storage/work/SUSE/suse-dev/cephfs_sync/tests/tgt is not a *CephFS*!
Checking target host/directory: 127.0.0.1:/storage/work/SUSE/suse-dev/cephfs_sync/tests/src ...
  ⏳ Trying to ping target host: 127.0.0.1 ...
    ✓ Host 127.0.0.1 has replied to ping! 
  ⏳ Trying to access target host/directory [root@127.0.0.1:/storage/work/SUSE/suse-dev/cephfs_sync/tests/src] ...
    ❌ Could not SSH access to host [127.0.0.1] !


Summary: 
  ❌  There were 11+ errors found! Please, solve the issues pointed out before running CephFS_Sync!
```

Finally, if passing the config file `-c myconfig.yml` is too much work, we can also set the `CEPHFS_SYNC_CONF_FILE=myconfig.yml` and run the command line without the `-c` option. 

We can also use `cron` and schedule jobs, for example: 
```
0 * * * *       root    cephfs_sync -c syncparams1.yml --verbose --log-file hourlyback.log
0 0 * * *       root    cephfs_sync -c syncparams2.yml --verbose --log-file dailyback.log
0 0 * * 1       root    cephfs_sync -c syncparams3.yml --verbose --log-file weeklyback.log
0 0 * 1 *       root    cephfs_sync -c syncparams4.yml --verbose --log-file monthlyback.log
```
