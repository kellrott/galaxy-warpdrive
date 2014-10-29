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
import tempfile
import string
import json

from glob import glob

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
    mounts={},
    privledged=False,
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
    for k, v in mounts.items():
        cmd.extend( ["-v", "%s:%s" % (k, v)])
    if privledged:
        cmd.append("--privileged")
        cmd.extend( ['-v', '/var/run/docker.sock:/var/run/docker.sock'] )
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
    subprocess.check_call(cmd, close_fds=True, env=sys_env, stdout=subprocess.PIPE)
    
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


def run_up(name="galaxy", docker_tag="bgruening/galaxy-stable", port=8080, host=None,
    lib_data=None, tool_data=None, tool_dir=None,
    work_dir="/tmp", tool_docker=False,
    key="HSNiugRFvgT574F43jZ7N9F3"):


    env = {
        "GALAXY_CONFIG_CHECK_MIGRATE_TOOLS" : "False",
        "GALAXY_CONFIG_MASTER_API_KEY" : key
    }

    mounts = {}
    privledged = False

    if tool_data is not None:
        mounts[os.path.abspath(tool_data)] = "/tool_data"
        env['GALAXY_CONFIG_TOOL_DATA_PATH'] = "/tool_data"

    config_dir = os.path.abspath(os.path.join(work_dir, "warpdrive_%s" % (name)))
    if not os.path.exists(config_dir):
        os.mkdir(config_dir)

    if tool_dir is not None:
        mounts[os.path.abspath(tool_dir)] = "/tools_import"
        mounts[config_dir] = "/config"
        with open( os.path.join(config_dir, "import_tool_conf.xml"), "w" ) as handle:
            handle.write(TOOL_IMPORT_CONF)
        env['GALAXY_CONFIG_TOOL_CONFIG_FILE'] = "/config/import_tool_conf.xml,config/tool_conf.xml.main"
    
    data_load = []
    if lib_data is not None:
        env['GALAXY_CONFIG_ALLOW_LIBRARY_PATH_PASTE'] = "True"
        lpath = os.path.abspath(lib_data)
        mounts[lpath] = "/export/lib_data"
        for a in glob(os.path.join(lpath, "*")):
            if os.path.isfile(a):
                data_load.append( os.path.join("/export/lib_data", os.path.relpath(a, lpath) ) )

    if tool_docker:
        mounts[config_dir] = "/config"
        with open( os.path.join(config_dir, "job_conf.xml"), "w" ) as handle:
            handle.write(string.Template(JOB_CHILD_CONF).substitute(TAG=docker_tag, NAME=name))
        env["GALAXY_CONFIG_JOB_CONFIG_FILE"] = "/config/job_conf.xml"
        env['GALAXY_CONFIG_OUTPUTS_TO_WORKING_DIRECTORY'] = "True"
        privledged=True

    call_docker_run(
        docker_tag,
        ports={str(port) : "80"},
        host=host,
        name=name,
        mounts=mounts,
        privledged=privledged,
        env=env
    )

    host="localhost"
    if 'DOCKER_HOST' in os.environ:
        u = urlparse.urlparse(os.environ['DOCKER_HOST'])
        host = u.netloc.split(":")[0]

    while True:
        time.sleep(3)
        try:
            url = "http://%s:%s/api/tools?key=%s" % (host, port, key)
            logging.debug("Pinging: %s" % (url))
            res = requests.get(url, timeout=3)
            if res.status_code / 100 == 5:
                continue
            break
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.Timeout:
            pass
    
    rg = RemoteGalaxy("http://%s:%s"  % (host, port), 'admin')
    library_id = rg.create_library("Imported")
    folder_id = rg.library_find(library_id, "/")['id']
    for data in data_load:
        logging.info("Loading: %s" % (data))
        print rg.library_paste_file(library_id, folder_id, os.path.basename(data), data)

class RemoteGalaxy(object):
    
    def __init__(self, url, api_key):
        self.url = url
        self.api_key = api_key

    def get(self, path):
        c_url = self.url + path
        params = {}
        params['key'] = self.api_key
        req = requests.get(c_url, params=params)
        return req.json()

    def post(self, path, payload):
        c_url = self.url + path
        params = {}
        params['key'] = self.api_key
        logging.debug("POSTING: %s %s" % (c_url, json.dumps(payload)))
        req = requests.post(c_url, data=json.dumps(payload), params=params, headers = {'Content-Type': 'application/json'} )
        return req.json()

    def post_text(self, path, payload, params=None):
        c_url = self.url + path
        if params is None:
            params = {}
        params['key'] = self.api_key
        logging.debug("POSTING: %s %s" % (c_url, json.dumps(payload)))
        req = requests.post(c_url, data=json.dumps(payload), params=params, headers = {'Content-Type': 'application/json'} )
        return req.text

    def create_library(self, name):
        lib_create_data = {'name' : name}
        library = self.post('/api/libraries', lib_create_data)
        library_id = library['id']
        return library_id
    
    def library_list(self, library_id):
        return self.get("/api/libraries/%s/contents" % library_id)
    
    def library_find(self, library_id, name):
        for a in self.library_list(library_id):
            if a['name'] == name:
                return a
        return None

    def library_paste_file(self, library_id, library_folder_id, name, datapath, metadata=None):
        data = {}
        data['folder_id'] = library_folder_id
        data['file_type'] = 'auto'
        data['name'] = name
        data['dbkey'] = ''
        data['upload_option'] = 'upload_paths'
        data['create_type'] = 'file'
        data['link_data_only'] = 'link_to_files'
        if metadata is not None:
            data['extended_metadata'] = metadata
        data['filesystem_paths'] = datapath
        libset = self.post("/api/libraries/%s/contents" % library_id, data)
        return libset



def run_down(name, host=None, rm=False, work_dir="/tmp"):
    try:
        call_docker_kill(
            name, host=host
            )
    except subprocess.CalledProcessError:
        return
    if rm:
        call_docker_rm(
            name, host=host
        )
        config_dir = os.path.join(work_dir, "warpdrive_%s" % (name))
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)


def run_status(name="galaxy", host=None):
    txt = call_docker_ps(
        host=host
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
            cur_name = line[namesIndex:sizeIndex].split()[0]
            tmp = line[statusIndex:portsIndex].split()
            status = "NotFound"
            if len(tmp):
                status = tmp[0]
            if cur_name == name:
                print status
                found = True
    if not found:
        print "NotFound"


TOOL_IMPORT_CONF = """<?xml version='1.0' encoding='utf-8'?>
<toolbox>
  <section id="imported" name="Imported Tools">
    <tool_dir dir="/tools_import"/>
  </section>
</toolbox>
"""

JOB_CHILD_CONF = """<?xml version="1.0"?>
<job_conf>
    <plugins workers="2">
        <plugin id="slurm" type="runner" load="galaxy.jobs.runners.slurm:SlurmJobRunner">
            <param id="drmaa_library_path">/usr/lib/slurm-drmaa/lib/libdrmaa.so</param>
        </plugin>
    </plugins>
    <handlers default="handlers">
        <handler id="handler0" tags="handlers"/>
        <handler id="handler1" tags="handlers"/>
    </handlers>
    <destinations default="cluster">
        <destination id="cluster" runner="slurm">
            <param id="docker_enabled">true</param>
            <param id="docker_sudo">false</param>
            <param id="docker_net">bridge</param>
            <param id="docker_default_container_id">${TAG}</param>
            <param id="docker_volumes"></param>
            <param id="docker_volumes_from">${NAME}</param>
        </destination>
    </destinations>
</job_conf>
"""



if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", action="store_true", default=False)
    parser.add_argument("-vv", action="store_true", default=False)

    subparsers = parser.add_subparsers(title="subcommand")

    parser_up = subparsers.add_parser('up')
    parser_up.add_argument("-t", "--tag", dest="docker_tag", default="bgruening/galaxy-stable")
    parser_up.add_argument("-x", "--tool-dir", default=None)
    parser_up.add_argument("-d", "--tool-data", default=None)
    parser_up.add_argument("-w", "--work-dir", default="/tmp")
    parser_up.add_argument("-p", "--port", default="8080")
    parser_up.add_argument("-n", "--name", default="galaxy")
    parser_up.add_argument("-l", "--lib-data", default=None)
    parser_up.add_argument("-c", "--child", dest="tool_docker", action="store_true", help="Launch jobs in child containers", default=False)
    parser_up.add_argument("--key", default="HSNiugRFvgT574F43jZ7N9F3")
    parser_up.add_argument("--host", default=None)
    parser_up.set_defaults(func=run_up)

    parser_down = subparsers.add_parser('down')
    parser_down.add_argument("-n", "--name", default="galaxy")
    parser_down.add_argument("--rm", action="store_true", default=False)
    parser_down.add_argument("--host", default=None)
    parser_down.add_argument("-w", "--work-dir", default="/tmp")
    parser_down.set_defaults(func=run_down)

    parser_status = subparsers.add_parser('status')
    parser_status.add_argument("-n", "--name", default="galaxy")
    parser_status.add_argument("--host", default=None)
    parser_status.set_defaults(func=run_status)

    args = parser.parse_args()

    if args.v:
        logging.basicConfig(level=logging.INFO)
    if args.vv:
        logging.basicConfig(level=logging.DEBUG)
    
    func = args.func
    kwds=vars(args)
    del kwds['v'] 
    del kwds['vv']
    del kwds['func']
    
    sys.exit(func(**kwds))
