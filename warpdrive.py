#!/usr/bin/env python

import re
import sys
import os
import time
import urlparse
import argparse
import subprocess
import logging
import requests

logging.basicConfig(level=logging.INFO)

def which(file):
    for path in os.environ["PATH"].split(":"):
        p = os.path.join(path, file)
        if os.path.exists(p):
            return p

def call_docker(command,
    docker_tag, ports={},
    args=[], host=None,
    env={},
    auto_rm=False, set_user=False):

    docker_path = which('docker')
    if docker_path is None:
        raise Exception("Cannot find docker")

    cmd = [
        docker_path, command
    ]

    if command == "run":
        if auto_rm:
            cmd.extend( ["--rm"] )
        if set_user:
            cmd.extend( ["-u", str(os.geteuid())] )
        for k, v in ports.items():
            cmd.extend( ["-p", "%s:%s" % (k,v) ] )
        for k, v in env.items():
            cmd.extend( ["-e" "%s=%s" % (k,v)] )
        cmd.append("-d")
        cmd.extend( [docker_tag] )
        cmd.extend(args)
    else:
        raise Exception("Unknown command: %s" % (command))

    sys_env = dict(os.environ)
    if host is not None:
        sys_env['DOCKER_HOST'] = host

    logging.info("executing: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, close_fds=True, env=sys_env)
    proc.communicate()
    if proc.returncode != 0:
        raise Exception("Call Failed: %s" % (cmd))

def run_up(args):
    env = {
        "GALAXY_CONFIG_CHECK_MIGRATE_TOOLS" : "False",
        "GALAXY_CONFIG_MASTER_API_KEY" : args.key
    }

    if args.tool_data is not None:
        env['GALAXY_CONFIG_TOOL_DATA_PATH'] = args.tool_data

    call_docker("run", args.tag, ports={args.port : "80"}, host=args.host, auto_rm=args.rm)

    host="localhost"
    if 'DOCKER_HOST' in os.environ:
        u = urlparse.urlparse(os.environ['DOCKER_HOST'])
        host = u.netloc.split(":")[0]

    while True:
        time.sleep(3)
        try:
            requests.get("http://%s:%s/api/tools?key=%s" % (host, args.port, args.key), timeout=3)
            return 0
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.Timeout:
            pass



if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(title="subcommand")

    parser_up = subparsers.add_parser('up')
    parser_up.add_argument("-t", "--tag", default="bgruening/galaxy-stable")
    parser_up.add_argument("-x", "--tool-dir", default=None)
    parser_up.add_argument("-d", "--tool-data", default=None)
    parser_up.add_argument("-w", "--work-dir", default="/tmp")
    parser_up.add_argument("-p", "--port", default="8080")
    parser_up.add_argument("--key", default="HSNiugRFvgT574F43jZ7N9F3")
    parser_up.add_argument("--rm", action="store_true", default=False)
    parser_up.add_argument("--host", default=None)
    parser_up.set_defaults(func=run_up)


    args = parser.parse_args()
    sys.exit(args.func(args))
