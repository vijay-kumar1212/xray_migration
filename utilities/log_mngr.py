import logging

_global_logger = None

def setup_custom_logger():
    return  logging.getLogger()

#  Here we have centralized logging behavior, due to this no need to call logging.getLogger() everywhere
#  Just return the root logger