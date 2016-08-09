#!/usr/bin/env python
"""
This is the main python script for our Ontap Select Deployment.
This script will read the ontap_select.cfg and perform create cluster and destroy cluster
operations.
Create clsuter workflow:
1) Add hosts
2) Configure Hosts
3) Add Cluster
Destroy cluster workflow:
1) Stop all nodes
2) offline Cluster
3) Delete cluster
4) Delete Hosts

Author: Kapil Arora
Github: @kapilarora
"""
import ConfigParser
from ontap_select import OntapSelect
import io
import time
import sys
import logging
from time import strftime


def main():
    config = ConfigParser.ConfigParser()
    # reading config file ontap_select.cfg
    config.read(io.BytesIO('ontap_select.cfg'))

    default_config = dict(config.items('default'))
    cluster_config = dict(config.items('cluster'))
    host_ids_str = default_config['hosts']
    host_ids = host_ids_str.split(',')
    host_configs = {}
    for host_id in host_ids:
        host_configs[host_id] = dict(config.items(host_id))
    node_name_str = cluster_config['nodes']
    node_names = node_name_str.split(',')
    node_configs = {}
    for node_name in node_names:
        node_configs[node_name] = dict(config.items(node_name))
    # getting log level from the config file
    log_level = default_config['log_level']
    level = _get_Log_level(log_level)

    # initializing logger
    logging.basicConfig(filename=strftime("ontap_select_%Y%m%d%H%M%S.log"),
                        level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    # @TODO change no-execute to env variable
    # no-execute? checking if no_execute is set. We won't execute any apis..just list the operations
    no_execute_str = default_config['no_execute']

    sleep_time = int(default_config['sleep_time_in_seconds_for_status_checks'])
    logging.debug('Configured sleep time for status checks is %s', sleep_time)

    logging.info('no_execute is set to %s', no_execute_str)
    if no_execute_str.lower() == 'true':
        logging.info('This is a dry run, No APIs will be executed.')

    logging.info('ONTAP Management VM IP:user/pass %s:%s/**** and with API version %s will be used',
                 default_config['ontap_select_mgmt_vm_ip_host'], default_config['ontap_select_mgmt_user'],
                 default_config['ontap_select_mgmt_api_version'])
    logging.debug('Initializing ONTAP select class')
    # Instantiating OntapSelect class
    ontap_select = OntapSelect(default_config)

    operation = default_config['operation']
    logging.info('Requested operation is : %s', operation)
    cluster_name = cluster_config['name']
    logging.info('Cluster name is %s', cluster_name)

    if operation == 'create':
        create_cluster(cluster_config, host_configs, node_configs, ontap_select, sleep_time)
    elif operation == 'destroy:create':
        destroy_cluster(ontap_select, cluster_name, host_ids, sleep_time)
        create_cluster(cluster_config, host_configs, node_configs, ontap_select, sleep_time)
    elif operation == 'destroy':
        destroy_cluster(ontap_select, cluster_name, host_ids, sleep_time)
    else:
        logging.error('Unknown Operation %s , valid values : create, destroy and destroy:create', operation)


def create_cluster(cluster_config, host_configs, node_configs, ontap_select, sleep_time):
    '''

    :param cluster_config: dict of cluster config params
    :param host_configs: dict of host config params
    :param node_configs: dict of node config params
    :param ontap_select: OntapSelect class object
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Starting ONTAP Select Cluster Deployment')
    add_hosts(host_configs, ontap_select, sleep_time)
    configure_hosts(host_configs, ontap_select, sleep_time)
    add_cluster(cluster_config, node_configs, ontap_select, sleep_time)


def destroy_cluster(ontap_select, cluster_name, host_ids, sleep_time):
    '''

    :param ontap_select: OntapSelect class obj
    :param cluster_name: name of the cluster
    :param host_ids: list of host ids
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Checking if cluster  %s exists', cluster_name)
    if cluster_exists(ontap_select, cluster_name):
        stop_all_nodes(ontap_select, cluster_name, sleep_time)  # @TODO..check if node is powered on
        cluster_offline(ontap_select, cluster_name, sleep_time)  # @TODO..add check if cluster offline
        cluster_delete(ontap_select, cluster_name, sleep_time)
    for host_id in host_ids:
        if host_exists(ontap_select, host_id):
            delete_host(ontap_select, host_id, sleep_time)


def add_hosts(host_configs, ontap_select, sleep_time):
    '''
    :param host_configs: dict of host config params
    :param ontap_select: OntapSelect class object
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Reading hosts config')

    for host_id, host_config in host_configs.iteritems():
        logging.info('Adding host %s with username/password: %s/***** and vcenter: %s',
                     host_id, host_config['username'], host_config['vcenter'])
        # Seding host add request
        ontap_select.add_host(host_id, host_config)
    # Wait for hosts to be added
    logging.info('Waiting for Hosts to be added and authenticated.')
    all_hosts_authenticated = False
    while not all_hosts_authenticated:
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)
        all_hosts_authenticated = True
        logging.info('Getting Status for all hosts.')
        hosts = ontap_select.get_hosts()
        logging.debug('Get hosts result %s', hosts)
        for host in hosts:
            status = host['status']
            logging.info('Status of Host %s is %s', host['host'], status)
            if status == 'authentication_in_progress':
                all_hosts_authenticated = False
            elif status == 'authentication_failed':
                logging.error('Authentication failed for Host %s', host['host'])
                logging.error('Stopping Execution, check host credentials')
                sys.exit('Authentication failed for  host ' + host['host'])
    logging.info('All Hosts have been added and authenticated')


def configure_hosts(host_configs, ontap_select, sleep_time):
    '''
    :param host_configs: dict of host config params
    :param ontap_select: OntapSelect class object
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    for host_id, host_config in host_configs.iteritems():
        # Read host config
        logging.info('Reading configuration params for host %s', host_id)
        # Send configure Host request
        logging.debug('Host Configuration: %s', host_config)
        logging.info('Sending add configuration request for host %s', host_id)
        ontap_select.add_host_config(host_id, host_config)

    # wait for hosts to be configured
    logging.info('Wait for host configurations to complete')
    all_hosts_configured = False
    # @TODO wait for only newly configured hosts
    while not all_hosts_configured:
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)
        all_hosts_configured = True
        logging.info('Sending request to get status of all hosts')
        hosts = ontap_select.get_hosts()
        logging.debug('Status result for all hosts: %s', hosts)
        for host in hosts:
            status = host['status']
            logging.info('Status of Host %s is %s', host['host'], status)
            if status == 'configuration_in_progress':
                all_hosts_configured = False
            elif status == 'configuration_failed':
                logging.error('Configuration failed for Host %s', host['host'])
                logging.error('Stopping Execution, check host configuration options.')
                sys.exit('Configuration failed for  host ' + host['host'])


def add_cluster(cluster_config, node_configs, ontap_select, sleep_time):
    '''
    :param cluster_config: dict of cluster config params
    :param node_configs: dict of node config params
    :param ontap_select: OntapSelect class object
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Reading Cluster config parameters')
    logging.debug('Cluster config : %s', cluster_config)
    logging.debug('Nodes configs : %s', node_configs)
    logging.info('Sending add cluster request for cluster name: %s', cluster_config['name'])
    ontap_select.add_cluster(cluster_config, node_configs)

    # wait for cluster to be online
    logging.info('Waiting for Cluster creation and setup to complete')
    cluster_online = False
    while not cluster_online:
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)
        cluster_online = True
        logging.info('Requesting status of all clusters')
        clusters = ontap_select.get_clusters()
        # if cluster create fails, the cluster disappears. Hence we need to check if clusters list is empty
        if len(clusters) < 1:
            logging.error('Cluster creation failed, cluster %s does not exist.', cluster_name)
        for cluster in clusters:
            cluster_name = cluster['name']
            logging.debug('Cluster name: %s', cluster_name)
            if cluster_name == cluster_config['name']:
                state = cluster['state']
                logging.info('State of cluster %s is %s', cluster_name, state)
                if state == 'creating':
                    cluster_online = False
                elif state == 'deploying_nodes':
                    cluster_online = False
                elif state == 'post_deploy_setup':
                    cluster_online = False
                elif state == 'online_setup_failed':
                    logging.error('Online setup failed for Cluster %s', cluster_name)
                    logging.error('Stopping Execution, check cluster configuration options.')
                    sys.exit('Online setup failed for cluster  ' + cluster_name)
                elif state == 'online_failed':
                    logging.error('Online operation failed for Cluster %s', cluster_name)
                    logging.error('Stopping Execution, check cluster configuration options.')
                    sys.exit('Online  failed for cluster  ' + cluster_name)
                elif state == 'create_failed':
                    logging.error('Creation failed for Cluster %s', cluster_name)
                    logging.error('Stopping Execution, check cluster configuration options.')
                    sys.exit('Creation failed for  cluster ' + cluster_name)
    # logging.info('Cluster %s successfully created and is online', name)
    print "Cluster creation workflow completed.!"


def cluster_exists(ontap_select, cluster_name):
    '''
    :param ontap_select: OntapSelect class object
    :param cluster_name: str
    :return: None
    '''
    logging.info('Getting List of Clusters.')
    clusters = ontap_select.get_clusters()
    logging.debug('Cluster get result %s', clusters)
    for cluster in clusters:

        if cluster['name'] == cluster_name:
            logging.info('Cluster %s exists', cluster_name)
            return True
    logging.info('Cluster %s does not exist.', cluster_name)
    return False


def host_exists(ontap_select, host_id):
    '''

    :param ontap_select: OntapSelect class object
    :param host_id: str
    :return:
    '''
    logging.info('Getting List of Hosts.')
    hosts = ontap_select.get_hosts()
    logging.debug('Hosts get result %s', hosts)
    for host in hosts:

        if host['host'] == host_id:
            logging.info('Host %s exists', host_id)
            return True
    logging.info('Host %s does not exist.', host_id)
    return False


def delete_host(ontap_select, host_id, sleep_time):
    '''

    :param ontap_select: OntapSelect class object
    :param host_id: str
    :param sleep_time: int time in seconds for recursive wait functions
    :return:
    '''
    logging.info('Deleting Hosts %s', host_id)
    hosts = ontap_select.delete_host(host_id)
    while host_exists(ontap_select, host_id):
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)


def stop_all_nodes(ontap_select, cluster_name, sleep_time):
    '''

    :param ontap_select: OntapSelect class object
    :param cluster_name: str
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Stopping all cluster nodes for Cluster name: %s', cluster_name)
    nodes = ontap_select.get_cluster_nodes(cluster_name)
    for node in nodes:
        node_name = node['name']
        node_state = node['state']
        logging.info('State of node %s is %s', node_name, node_state)
        if (node_state == 'powered_on' or node_state == 'powering_off_failed' or
                    node_state == 'powering_on' or node_state == 'suspended'):
            logging.info('Sending request to stop node %s', node_name)
            ontap_select.stop_node(cluster_name, node_name)

    logging.info('Wait for all nodes to stop')
    all_nodes_stopped = False
    while not all_nodes_stopped:
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)
        all_nodes_stopped = True
        logging.info('Sending request to get status of all nodes')
        nodes = ontap_select.get_cluster_nodes(cluster_name)
        logging.debug('Status result for all nodes: %s', nodes)
        for node in nodes:
            node_name = node['name']
            node_state = node['state']
            logging.info('State of Node %s is %s', node_name, node_state)
            if node_state == 'powering_off':
                all_nodes_stopped = False
            elif node_state == 'powering_off_failed':
                logging.error('Powering failed for Node %s', node_name)
                logging.error('Stopping Execution, check vmware env')
                sys.exit('Powering off failed for  node ' + node_name)


def cluster_offline(ontap_select, cluster_name, sleep_time):
    '''

    :param ontap_select: OntapSelect class object
    :param cluster_name: str
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Making cluster %s offline', cluster_name)
    ontap_select.offline_cluster(cluster_name, True)
    # wait for cluster to be offline
    logging.info('Waiting for Cluster offline to finish')
    is_cluster_offline = False
    while is_cluster_offline == False:
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)
        is_cluster_offline = True
        logging.info('Requesting status of all clusters')
        clusters = ontap_select.get_clusters()
        for cluster in clusters:
            name = cluster['name']
            logging.debug('Cluster name: %s', cluster_name)
            if cluster_name == name:
                state = cluster['state']
                logging.info('State of cluster %s is %s', cluster_name, state)
                if state == 'online':
                    is_cluster_offline = False
                elif state == 'offline_failed':
                    logging.error('Offline  failed for Cluster %s', cluster_name)
                    logging.error('Stopping Execution, retry!')
                    sys.exit('Offline  failed for cluster  ' + name)
    logging.info('Cluster %s successfully offlined ', name)


def cluster_delete(ontap_select, cluster_name, sleep_time):
    '''

    :param ontap_select: OntapSelect class object
    :param cluster_name: str
    :param sleep_time: int time in seconds for recursive wait functions
    :return: None
    '''
    logging.info('Deleting cluster %s ', cluster_name)
    ontap_select.delete_cluster(cluster_name)
    logging.info('Waiting for Cluster deletion to finish')
    while cluster_exists(ontap_select, cluster_name):
        logging.info('Sleeping for %s seconds before next status check.', sleep_time)
        time.sleep(sleep_time)


def _get_Log_level(log_level):
    '''

    :param log_level: str info/error/warn/debug
    :return: logging.level
    '''
    if log_level == 'info':
        level = logging.INFO
    elif log_level == 'error':
        level = logging.ERROR
    elif log_level == 'warn':
        level = logging.WARN
    else:
        level = logging.DEBUG
    return level


if __name__ == '__main__':
    main()