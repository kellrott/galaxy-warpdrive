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

def which(file):
    for path in os.environ["PATH"].split(":"):
        p = os.path.join(path, file)
        if os.path.exists(p):
            return p

def get_docker_path():
    docker_path = which('docker')
    if docker_path is None:
        raise Exception("Cannot find docker")
    return docker_path

def call_docker_run(
    docker_tag, ports={},
    args=[], host=None,
    env={},
    set_user=False,
    name=None):

    docker_path = get_docker_path()

    cmd = [
        docker_path, "run"
    ]

    if set_user:
        cmd.extend( ["-u", str(os.geteuid())] )
    for k, v in ports.items():
        cmd.extend( ["-p", "%s:%s" % (k,v) ] )
    for k, v in env.items():
        cmd.extend( ["-e", "%s=%s" % (k,v)] )
    if name is not None:
        cmd.extend( ["--name", name])
    cmd.append("-d")
    cmd.extend( [docker_tag] )
    cmd.extend(args)

    sys_env = dict(os.environ)
    if host is not None:
        sys_env['DOCKER_HOST'] = host

    logging.info("executing: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, close_fds=True, env=sys_env, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise Exception("Call Failed: %s" % (cmd))


def call_docker_kill(
    name,
    host=None,
    ):

    docker_path = get_docker_path()

    cmd = [
        docker_path, "kill", name
    ]

    sys_env = dict(os.environ)
    if host is not None:
        sys_env['DOCKER_HOST'] = host

    logging.info("executing: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, close_fds=True, env=sys_env, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise Exception("Call Failed: %s" % (cmd))

def call_docker_rm(
    name=None,
    host=None
    ):

    docker_path = get_docker_path()

    cmd = [
        docker_path, "rm", name
    ]

    sys_env = dict(os.environ)
    if host is not None:
        sys_env['DOCKER_HOST'] = host

    logging.info("executing: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, close_fds=True, env=sys_env, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise Exception("Call Failed: %s" % (cmd))



def call_docker_ps(
    host=None
    ):

    docker_path = get_docker_path()

    cmd = [
        docker_path, "ps", "-a", "--no-trunc", "-s"
    ]

    sys_env = dict(os.environ)
    if host is not None:
        sys_env['DOCKER_HOST'] = host

    logging.info("executing: " + " ".join(cmd))
    proc = subprocess.Popen(cmd, close_fds=True, env=sys_env, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise Exception("Call Failed: %s" % (cmd))
    return stdout


def run_up(args):
    env = {
        "GALAXY_CONFIG_CHECK_MIGRATE_TOOLS" : "False",
        "GALAXY_CONFIG_MASTER_API_KEY" : args.key
    }

    if args.tool_data is not None:
        env['GALAXY_CONFIG_TOOL_DATA_PATH'] = args.tool_data

    call_docker_run(
        args.tag,
        ports={args.port : "80"},
        host=args.host,
        name=args.name,
        env=env
    )

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


def run_down(args):
    call_docker_kill(
        args.name, host=args.host
    )

    if args.rm:
        call_docker_rm(
            args.name, host=args.host
        )


def run_status(args):
    txt = call_docker_ps(
        host=args.host
    )

    lines = txt.split("\n")

    containerIndex = lines[0].index("CONTAINER ID")
    imageIndex = lines[0].index("IMAGE")
    commandIndex = lines[0].index("COMMAND")
    portsIndex = lines[0].index("PORTS")
    statusIndex = lines[0].index("STATUS")
    namesIndex = lines[0].index("NAMES")
    sizeIndex = lines[0].index("SIZE")

    found = False
    for line in lines[1:]:
        if len(line):
            name = line[namesIndex:sizeIndex].split()[0]
            status = line[statusIndex:portsIndex].split()[0]
            if name == args.name:
                print status
                found = True
    if not found:
        print "NotFound"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", action="store_true", default=False)

    subparsers = parser.add_subparsers(title="subcommand")

    parser_up = subparsers.add_parser('up')
    parser_up.add_argument("-t", "--tag", default="bgruening/galaxy-stable")
    parser_up.add_argument("-x", "--tool-dir", default=None)
    parser_up.add_argument("-d", "--tool-data", default=None)
    parser_up.add_argument("-w", "--work-dir", default="/tmp")
    parser_up.add_argument("-p", "--port", default="8080")
    parser_up.add_argument("-n", "--name", default="galaxy")
    parser_up.add_argument("-c", "--child", action="store_true", help="Launch jobs in child containers", default=False)
    parser_up.add_argument("--key", default="HSNiugRFvgT574F43jZ7N9F3")
    parser_up.add_argument("--host", default=None)
    parser_up.set_defaults(func=run_up)

    parser_down = subparsers.add_parser('down')
    parser_down.add_argument("-n", "--name", default="galaxy")
    parser_down.add_argument("--rm", action="store_true", default=False)
    parser_down.add_argument("--host", default=None)
    parser_down.set_defaults(func=run_down)

    parser_status = subparsers.add_parser('status')
    parser_status.add_argument("-n", "--name", default="galaxy")
    parser_status.add_argument("--host", default=None)
    parser_status.set_defaults(func=run_status)

    args = parser.parse_args()

    if args.v:
        logging.basicConfig(level=logging.INFO)
    sys.exit(args.func(args))
