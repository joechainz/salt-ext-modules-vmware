import logging
import ssl
import socket
import hashlib

import salt.exceptions
import saltext.vmware.utils.common as utils_common
import saltext.vmware.utils.datacenter as utils_datacenter
import saltext.vmware.utils.cluster as utils_cluster

# pylint: disable=no-name-in-module
try:
    from pyVmomi import vim, vmodl

    HAS_PYVMOMI = True
except ImportError:
    HAS_PYVMOMI = False

log = logging.getLogger(__name__)


def get_hosts(
    service_instance,
    datacenter_name=None,
    host_names=None,
    cluster_name=None,
    get_all_hosts=False,
):
    """
    Returns a list of vim.HostSystem objects representing ESXi hosts
    in a vcenter filtered by their names and/or datacenter, cluster membership.

    service_instance
        The Service Instance Object from which to obtain the hosts.

    datacenter_name
        The datacenter name. Default is None.

    host_names
        The host_names to be retrieved. Default is None.

    cluster_name
        The cluster name - used to restrict the hosts retrieved. Only used if
        the datacenter is set.  This argument is optional.

    get_all_hosts
        Specifies whether to retrieve all hosts in the container.
        Default value is False.
    """
    properties = ["name"]
    if cluster_name and not datacenter_name:
        raise salt.exceptions.ArgumentValueError(
            "Must specify the datacenter when specifying the cluster"
        )
    if not host_names:
        host_names = []
    if not datacenter_name:
        # Assume the root folder is the starting point
        start_point = utils_common.get_root_folder(service_instance)
    else:
        start_point = utils_datacenter.get_datacenter(service_instance, datacenter_name)
        if cluster_name:
            # Retrieval to test if cluster exists. Cluster existence only makes
            # sense if the datacenter has been specified
            properties.append("parent")

    # Search for the objects
    hosts = utils_common.get_mors_with_properties(
        service_instance,
        vim.HostSystem,
        container_ref=start_point,
        property_list=properties,
    )
    log.trace("Retrieved hosts: %s", [h["name"] for h in hosts])
    filtered_hosts = []
    for h in hosts:
        # Complex conditions checking if a host should be added to the
        # filtered list (either due to its name and/or cluster membership)

        if cluster_name:
            if not isinstance(h["parent"], vim.ClusterComputeResource):
                continue
            parent_name = utils_common.get_managed_object_name(h["parent"])
            if parent_name != cluster_name:
                continue

        if get_all_hosts:
            filtered_hosts.append(h["object"])
            continue

        if h["name"] in host_names:
            filtered_hosts.append(h["object"])
    return filtered_hosts


# TODO Support host caches on multiple datastores
def configure_host_cache(host_ref, datastore_ref, swap_size_MiB, host_cache_manager=None):
    """
    Configures the host cahe of the specified host

    host_ref
        The vim.HostSystem object representing the host that contains the
        requested disks.

    datastore_ref
        The vim.Datastore opject representing the datastore the host cache will
        be configured on.

    swap_size_MiB
        The size in Mibibytes of the swap.

    host_cache_manager
        The vim.HostCacheConfigurationManager object representing the cache
        configuration manager on the specified host. Default is None. If None,
        it will be retrieved in the method
    """
    hostname = utils_common.get_managed_object_name(host_ref)
    if not host_cache_manager:
        props = utils_common.get_properties_of_managed_object(
            host_ref, ["configManager.cacheConfigurationManager"]
        )
        if not props.get("configManager.cacheConfigurationManager"):
            raise salt.exceptions.VMwareObjectRetrievalError(
                "Host '{}' has no host cache".format(hostname)
            )
        host_cache_manager = props["configManager.cacheConfigurationManager"]
    log.trace(
        "Configuring the host cache on host '%s', datastore '%s', " "swap size=%s MiB",
        hostname,
        datastore_ref.name,
        swap_size_MiB,
    )

    spec = vim.HostCacheConfigurationSpec(datastore=datastore_ref, swapSize=swap_size_MiB)
    log.trace("host_cache_spec=%s", spec)
    try:
        task = host_cache_manager.ConfigureHostCache_Task(spec)
    except vim.fault.NoPermission as exc:
        log.exception(exc)
        raise salt.exceptions.VMwareApiError(
            "Not enough permissions. Required privilege: " "{}".format(exc.privilegeId)
        )
    except vim.fault.VimFault as exc:
        log.exception(exc)
        raise salt.exceptions.VMwareApiError(exc.msg)
    except vmodl.RuntimeFault as exc:
        log.exception(exc)
        raise salt.exceptions.VMwareRuntimeError(exc.msg)
    utils_common.wait_for_task(task, hostname, "HostCacheConfigurationTask")
    log.trace("Configured host cache on host '%s'", hostname)
    return True


def list_hosts(service_instance):
    """
    Returns a list of hosts associated with a given service instance.

    service_instance
        The Service Instance Object from which to obtain hosts.
    """
    return utils_common.list_objects(service_instance, vim.HostSystem)


def disconnect_host(name, service_instance):
    """
    Disconnects host from vCenter instance

    Returns connection state of host

    name
        Name of host.
    
    service_instance
        The Service Instance Object from which to obtain host.
    """
    host = utils_common.get_mor_by_property(service_instance, vim.HostSystem, name)
    if host.summary.runtime.connectionState == "disconnected":
        return host.summary.runtime.connectionState
    task = host.DisconnectHost_Task()
    host = utils_common.wait_for_task(task, name, "disconnect host task")
    return host.summary.runtime.connectionState


def reconnect_host(name, service_instance):
    """
    Reconnects host from vCenter instance

    Returns connection state of host

    name
        Name of host.
    
    service_instance
        The Service Instance Object from which to obtain host.
    """
    host = utils_common.get_mor_by_property(service_instance, vim.HostSystem, name)
    if host.summary.runtime.connectionState == "connected":
        return host.summary.runtime.connectionState
    task = host.ReconnectHost_Task()
    ret_host = utils_common.wait_for_task(task, name, "reconnect host task")
    return ret_host.summary.runtime.connectionState


def move_host(name, cluster_name, service_instance):
    """
    Move host to a different cluster.

    Returns connection state of host

    name
        Name of host.
    
    service_instance
        The Service Instance Object from which to obtain host.
    """
    host_ref = utils_common.get_mor_by_property(service_instance, vim.HostSystem, name)
    cluster_ref = utils_common.get_mor_by_property(service_instance, vim.ClusterComputeResource, cluster_name)
    task = cluster_ref.MoveInto_Task([host_ref])
    utils_common.wait_for_task(task, cluster_name, "move host task")
    return 'moved'


def remove_host(name, service_instance):
    """
    Removes host from vCenter instance.

    Returns connection state of host

    name
        Name of host.
    
    service_instance
        The Service Instance Object from which to obtain host.
    """
    host = utils_common.get_mor_by_property(service_instance, vim.HostSystem, name)
    task = host.Destroy_Task()
    utils_common.wait_for_task(task, name, "destroy host task")
    return 'removed'


def _format_ssl_thumbprint(number):
    """
    Formats ssl cert number

    number
        Number to be formatted into ssl thumbprint
    """
    string = str(number)
    return ':'.join(a + b for a, b in zip(string[::2], string[1::2]))


def add_host(name, user, password, cluster_name, datacenter_name, connect, service_instance):
    """
    Adds host from vCenter instance

    Returns connection state of host

    name
        Name of host
    
    user
        User name used to log into esxi instance.

    password
        Password to log into esxi instance.

    cluster_name
        

    service_instance
        The Service Instance Object to place host on.
    """
    dc_ref = utils_common.get_datacenter(service_instance, datacenter_name)
    cluster_ref = utils_cluster.get_cluster(dc_ref, cluster_name)
    connect_spec = vim.host.ConnectSpec()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    wrapped_socket = ssl.wrap_socket(sock)
    try:
        wrapped_socket.connect((name, 443))
    except socket.error as error:
        log.error(error)
    else:
        der_cert_bin = wrapped_socket.getpeercert(True)
        wrapped_socket.close()

    sslThumbprint = _format_ssl_thumbprint(hashlib.sha1(der_cert_bin).hexdigest())
    connect_spec.sslThumbprint = sslThumbprint
    connect_spec.hostName = name
    connect_spec.userName = user
    connect_spec.password = password
    task = cluster_ref.AddHost_Task(connect_spec, connect)
    host = utils_common.wait_for_task(task, name, "add host task")
    return host.summary.runtime.connectionState