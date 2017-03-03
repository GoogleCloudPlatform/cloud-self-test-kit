# Cloud Self Test Kit

A set of utilities designed to make the process of getting useful debug
information out of a gcloud project easier.

## Tracerouter

A simple python script designed to traceroute to (and also back) to a set of VMs
within the project. The script makes it very simple by allowing to select the
VMs in question by specifying a regular expression.

Example of usage:
```
python tracerouter.py REGEX
```
Run ```python tracerouter.py -h``` or refer to tracerouter.py for more
documentation.

### Dependencies

Tracerouter requires at least the gcloud SDK installed and traceroute to be installed and in the PATH. See tracerouter.py for more information.
