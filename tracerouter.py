#!/usr/bin/python
#
# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Simple traceroute to the Gcloud VM's using gcloud SDK python library.

This script will lookup VMs within a gcloud project that matches a regexp
and run traceroute to each of them. This simplifies obtaining this kind
of debug information.

Typical Usage:
  python traceroute.py "[regexp]"

  Run "python traceroute.py -h" for more options

Requirements:
- Python 2.7
- Requires gcloud tool installed with a default project set up.
  This will be the project that the script will use to look for VMs.
- Requires the Google API Client for Python
  (https://cloud.google.com/compute/docs/tutorials/python-guide)
- Requires traceroute and dig (optional) to be installed and in PATH

"""

from __future__ import absolute_import
from __future__ import print_function

import argparse
import re
import subprocess

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials

###############################################
# Argument parsing
###############################################


def parse_args():
  """Parse the command line arguments.

  Returns:
    The parsed argparse instance
  """
  parser = argparse.ArgumentParser(description="Utility for easily debug VMs")
  parser.add_argument(
      "-p",
      "--print",
      action="store_true",
      help="List all the instances, instead of traceroute.")
  parser.add_argument(
      "--project",
      help="""Project in which to run the tracerouter.
      If none is specified, the default project will be used.""")
  parser.add_argument(
      "-d",
      "--dig",
      action="store_true",
      help="Include dig (DNS lookup) information.")
  parser.add_argument(
      "-r",
      "--reverse_traceroute",
      action="store_true",
      help="Include reverse traceroute (from VM to host).")
  parser.add_argument(
      "match_pattern",
      help="""Pattern to match against VM names within the project.
                      Can use regexp expressions to match.""")

  return parser.parse_args()


##############################################
# gcloud account / helpers
##############################################


def get_gcloud_api():
  """Obtains the google SDK api instance.

  Returns:
    The authenticated gcloud api instance
  """
  credentials = GoogleCredentials.get_application_default()
  compute_api = discovery.build("compute", "v1", credentials=credentials)
  return compute_api


def obtain_self_ip():
  """Query open DNS to obtain the public IP of the current host.

  Returns:
    The public ip string
  """
  ip = subprocess.check_output(
      ["dig", "myip.opendns.com", "@resolver1.opendns.com", "+short"])
  return ip.strip()


def obtain_default_project():
  """Obtains the default project from the gcloud configuration.

  Returns:
    The name of the default project currently defined in gcloud's config
  """
  default_project = subprocess.check_output(
      ["gcloud", "config", "get-value", "project"], stderr=subprocess.PIPE)
  default_project = default_project.strip()
  return default_project


def list_instances(compute_api, project, zone):
  """List the instances for a project/zone.

  Args:
    compute_api: The gcloud api instance.
    project: The project name.
    zone: The zone name

  Returns:
    A list of instance objects.
  """
  result = compute_api.instances().list(project=project, zone=zone).execute()
  if "items" in result:
    return result["items"]
  else:
    return []


def get_zone_names(compute_api, project):
  """Obtains a list of zone names for a given project.

  Args:
    compute_api: The gcloud api instance.
    project: The project name.

  Returns:
    A list of zone names that are running
  """
  result = compute_api.zones().list(project=project).execute()
  filtered_list = [
      i for i in result["items"]
      if (i["status"] == "UP") and (i["kind"] == "compute#zone")
  ]
  return [i["name"] for i in filtered_list]


##############################################
# DNS Lookup
##############################################


def print_dig():
  """Performs a dig call and prints the result."""
  print("Running \"dig -t txt o-o.myaddr.l.google.com @ns1.google.com\"")
  dig = subprocess.Popen(
      ["dig", "-t", "txt", "o-o.myaddr.l.google.com", "@ns1.google.com"],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT)
  for line in iter(dig.stdout.readline, ""):
    print(line, end="")
  print("")


##############################################
# Obtaining instances
##############################################


def obtain_instances(compute_api, project, match_pattern):
  """Obtains all the VM instances that match a certain pattern.

  Args:
    compute_api: The gcloud api instance.
    project: The project name.
    match_pattern: The regex pattern to match.

  Returns:
    A dictionary of instances with the zone names as keys
    i.e.
    {
      "us-central-1": [... list of instances ...],
      "us-east-1: [... list of instances ...],
      ...
    }
  """
  zone_names = get_zone_names(compute_api, project)
  regex = re.compile(match_pattern)

  zone_instances = {}
  for zone_name in zone_names:
    zone_instances[zone_name] = []
    instances = list_instances(compute_api, project, zone_name)
    f = [
        x for x in instances
        if (x["status"] == "RUNNING") and (x["kind"] == "compute#instance") and
        regex.match(x["name"])
    ]
    zone_instances[zone_name] = f
  return zone_instances


##############################################
# Action to be taken
##############################################


def print_subprocess(proc_name, proc_args):
  """Runs a subprocess and prints out the output.

  Has special management of exception when running a remote command
  (i.e. running a ssh command through gcloud).

  Args:
    proc_name: The name of the subprocess to call.
      Mainly used for error printing.
    proc_args: A list with all the arguments for a subprocess call.
      Must be able to be passed to a subprocess.Popen call.
  """

  error_str = ""
  proc_args_str = " ".join(proc_args)
  try:
    proc = subprocess.Popen(
        proc_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for l in iter(proc.stdout.readline, ""):
      print(l, end="")
    proc.wait()
    if proc.returncode != 0:
      e_str = "[FROM VM]: {0}".format(proc.stderr.read().strip())
      # Recycling exception type
      raise OSError(e_str)
    print("")
  except OSError as e:
    error_str = str(e)
    print("Error running {0}: {1}\nCALL: {2}\n".format(proc_name, error_str,
                                                       proc_args_str))


def traceroute_instance(instance,
                        tr_project_name,
                        tr_zone_name,
                        reverse_traceroute=False):
  """Runs a traceroute to a certain instance in a project/zone.

  Args:
    instance: Instance name.
    tr_project_name: The project to which the instance belongs.
    tr_zone_name: The zone to which the instance belongs.
    reverse_traceroute: By default, there will only be a traceroute from
      the host to the VM. Enabling this flag will output a traceroute from
      the VM to the host also. This will require to obtain the public IP
      of the host using an external DNS server (probably openDNS).
  """

  name = instance["name"]
  external_ip = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
  self_ip = obtain_self_ip()
  print("Traceroute TO {0}: {1} -> {2}".format(name, self_ip, external_ip))
  print_subprocess("Traceroute", ["traceroute", external_ip])

  if reverse_traceroute:
    print("Traceroute FROM {0}: {1} -> {2}".format(name, external_ip, self_ip))
    print_subprocess("Reverse Traceroute", [
        "gcloud", "compute", "ssh", name, "--project", tr_project_name,
        "--zone", tr_zone_name, "--command", "traceroute {0}".format(self_ip)
    ])


def print_instance(instance):
  """Prints the instance name/external ip."""

  name = instance["name"]
  external_ip = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
  print("{0}: {1}".format(name, external_ip))


def main():
  args = parse_args()

  if args.dig:
    print_dig()

  if args.project is None:
    current_project = obtain_default_project()
  else:
    current_project = args.project
  print("Project is: {0}".format(current_project))
  print("#################################")

  print("Obtaining instances...")
  compute_api = get_gcloud_api()
  zone_instances = obtain_instances(compute_api, current_project,
                                    args.match_pattern)

  for zone_name in zone_instances:
    instances = zone_instances[zone_name]
    if not len(instances):
      continue

    print("")
    print("Instances in {0}".format(zone_name))
    print("----------------------------------------")

    for inst in zone_instances[zone_name]:
      if args.print:
        print_instance(inst)
      else:
        traceroute_instance(inst, current_project, zone_name,
                            args.reverse_traceroute)


if __name__ == "__main__":
  main()
