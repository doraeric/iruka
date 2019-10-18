#!/usr/bin/env python3
import errno
import logging
import os
import subprocess
import sys
from os import path
from contextlib import contextmanager

from ..protos import (common_pb2, checker_io_pb2)
from ..exceptions import IrukaInternalError


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('checkers.hoj_special_judge')

rtncode_map = {
    1: common_pb2.AC,
    6: common_pb2.WA,
    7: common_pb2.PE
}


@contextmanager
def symlink_force(*args):
    src, dest, *_ = args
    try:
        yield os.symlink(*args)
    except OSError as err:
        if err.errno == errno.EEXIST:
            os.remove(dest)
            os.symlink(*args)
        else:
            raise err
    finally:
        # should succeed?
        os.remove(dest)


def main(cxt, checker_exec='./checker'):
    logger.debug('Checker path={}'.format(checker_exec))

    pathIn = cxt.path_infile
    pathOut = cxt.path_outfile
    pathOut_user = cxt.path_out_user

    pShmIn = '/run/shm/in.txt'
    pShmAns = '/run/shm/ans.txt'
    pShmOut = '/run/shm/out.txt'

    for p, pShm in [(pathIn, pShmIn),
                    (pathOut, pShmAns),
                    (pathOut_user, pShmOut)]:
        if not p:
            raise IrukaInternalError('Missing path to be named with "{}"'.format(pShm))

    # link to "in.txt", "out.txt", "ans.txt"
    # because some dumb checkers hardcode these filenames :(
    with symlink_force(path.realpath(pathIn), pShmIn), \
         symlink_force(path.realpath(pathOut), pShmAns), \
         symlink_force(path.realpath(pathOut_user), pShmOut):

        subp = None
        try:
            subp = subprocess.run([
                checker_exec,
                pShmIn,
                pShmOut,
                pShmAns,
                # 'special-report'
            ],
            cwd='/run/shm',
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            )
        except Exception as err:
            logger.error(err)

    output = checker_io_pb2.CheckerOutput()

    if subp is not None:
        rtncode = subp.returncode
        logger.info('Result: {}'.format(rtncode))

        output.user_message = subp.stdout
        output.log = subp.stderr
        # I would like to set score_tmp, but HOJ does not
        # implement partial grading :(
    else:
        rtncode = -1
        logger.error('Cannot determine return code of checker')


    verdict = rtncode_map.get(rtncode, None)

    if verdict is not None:
        output.verdict = verdict
    else:
        logger.error('Unknown return code from testlib checker: {}'.format(rtncode))
        output.verdict = common_pb2.SERR

    return output


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Usage: python -m {} <in> <out> <out_user> [checker-path]'.format(__spec__.name))
        sys.exit(1)

    kwargs = {}
    try:
        kwargs['checker_exec'] = sys.argv[4]
    except KeyError:
        pass

    inp = checker_io_pb2.CheckerInput(
        path_infile=sys.argv[1],
        path_outfile=sys.argv[2],
        path_out_user=sys.argv[3]
    )

    cxtOut = main(inp, **kwargs)

    from google.protobuf import text_format

    print('---  # checker output')
    print(text_format.MessageToString(cxtOut)[:-1])
    print('---')
