# -*- coding: utf-8 -*-
"""
This module is responsible for storing configuration options
"""

"""
from __future__ import absolute_import
"""

class Config(object):
    """
    Class that holds all configuration options
    """

    # the log file path location
    LOG_FILE_PATH = "/var/log/cephfs-sync.log"

    # the log verbosity level
    LOG_LEVEL = "info"

    # default config file to read from
    CONFIG_FILE_PATH = ""


    # Summary at the end for dry-runs
    ERROR_COUNT = 0

    # Flags for checking the config file
    IS_DRY_RUN = False

    # Flags for exposing more info to the log files
    IS_VERBOSE = False

