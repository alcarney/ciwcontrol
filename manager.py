import json
import networkx as nx
from pprint import PrettyPrinter
from yaml import load, dump

distributions = {'Exponential': 1,
                 'Uniform': 2,
                 'Deterministic': 1,
                 'Triangular': 3,
                 'Gamma': 2,
                 'Lognormal': 2,
                 'Weibull': 1,
                 'NoArrivals': 0}

def parse_distribution(s):
    """
    Parses the distribution from the given string
    """
    segments = s.split(' ')
    dist = segments[0]
    args = segments[1:]

    # Check to see if the given distribution is supported
    if dist not in distributions.keys():
        raise ValueError('Unsupported distribution %s' % dist)

    # Does it have the correct number of arguments?
    if len(args) != distributions[dist]:
        raise ValueError('%s distribution supports %i argument(s) (%i given)'
                          % (dist, distributions[dist], len(args)))

    args = [float(a) for a in args]

    if dist == 'NoArrivals':
        return 'NoArrivals'
    else:
        return [dist, *args]

def parse_connections(connections, current_name):
    """
    Parses the connections into tuples ready for us to contruct
    the transition matrices
    """
    total_prob = 0
    connect = []

    for c in connections:
        total_prob += c['prob']
        connect.append((current_name, c['target'], c['prob']))

    if total_prob > 1.0:
        raise ValueError('Total probabilty cannot exceed 1 for any customer class (Issue in node: %s)' % current_name)

    return connect

def parse_customers(customers, current_name):
    """
    Parses the customer definitions for a station
    """
    keys = []
    dists = []
    serv_dists = []
    connections = []

    for customer in customers:
        keys.append('Class %i' % customer['class'])

        try:
            dists.append(parse_distribution(customer['dist']))
        except:
            dists.append('NoArrivals')

        serv_dists.append(parse_distribution(customer['service']))

        conns = []

        if 'connections' in customer.keys():
            conns += parse_connections(customer['connections'], current_name)

        connections.append(conns)

    arrival_dists = dict(zip(keys, dists))
    service_dists = dict(zip(keys, serv_dists))
    connections = dict(zip(keys, connections))

    return {'arrival' : arrival_dists, 'service': service_dists, 'connections': connections}

def parse_station(station):
    """
    Parses a single station
    """

    dists = parse_customers(station['customers'], station['name'])

    params = {'name': station['name'],
              'capacity': station['capacity'],
              'arrivals': dists['arrival'],
              'service': dists['service'],
              'servers': station['servers'],
              'connections': dists['connections']}

    return params

def update_distributions(existing, new, current_node):
    """
    Given the existing distributions dictionary and another
    containing new entries to add this function will handle merging them
    """

    # Loop through the keys in the new dictionary
    for new_key in new.keys():

        # Check to see if the key exists in the existing dictionary
        if new_key not in existing.keys():

            # This means this customer class hasn't been defined for
            # other nodes in the network so far. So to keep things
            # consistent we need to initialise the existing dictionary
            # with (current_node - 1) NoArrivals
            existing[new_key] = ['NoArrivals' for n in range(current_node - 1)]

        # Add the distribution to the existing dictionary
        existing[new_key].append(new[new_key])

    # We also need to handle the cases where we have a node which doesn't recieve
    # customers which have been defined elsewhere in the network. So we now need
    # to go through each key in the exisiting dictionary to ensure that each list
    # is the required length and append 'NoArrivals' to any that don't match
    for existing_key in existing.keys():

        # Check the length - it should match the current node
        if len(existing[existing_key]) != current_node:

            # We need to add a 'NoArrivals'
            existing[existing_key].append('NoArrivals')

    # Finally return the existing dictionary
    return existing

def update_connections(existing, new):
    """
    This will update the connections dictonary
    """
    for new_key in new.keys():

        if new_key not in existing.keys():
            existing[new_key] = new[new_key]
        else:
            existing[new_key] += new[new_key]

    return existing


def build_params(stations):
    """
    Given each of the parsed stations construct the full blown parameter
    dictionary for Ciw
    """

    pp = PrettyPrinter(indent=2)
    # Count the number of nodes in the network
    num_nodes = len(stations)

    # Build the basic structure of the parameters dictionary
    params = {'Arrival_distributions' : {},
              'Number_of_nodes': len(stations),
              'Number_of_servers': [],
              'Queue_capacities': [],
              'Service_distributions': {}}

    # We will need to keep track of the node we are
    # currently processing
    current_node = 0

    # We will build a lookup of node names as we go
    names_to_nodes = {}
    connections = {}

    # For each node in the network
    for station in stations:

        # Parse the next node and keep count
        current_node += 1
        node = parse_station(station)

        # Update the mapping of node names
        if node['name'] in names_to_nodes.keys():
            raise ValueError('A node with the name %s has already been defined! Please use unique node names' % node['name'])
        names_to_nodes[node['name']] = current_node

        # It's a simple case to incorporate the number of severs and queue
        # capacities
        params['Number_of_servers'].append(node['servers'])
        params['Queue_capacities'].append(node['capacity'])

        # But we have to take more care when it comes to the distributions
        params['Arrival_distributions'] = update_distributions(params['Arrival_distributions'],
                                                               node['arrivals'], current_node)

        params['Service_distributions'] = update_distributions(params['Service_distributions'],
                                                                node['service'], current_node)

        connections = update_connections(connections, node['connections'])


    matrices = {}
    # Now that we have the bulk of the parameters sorted it's time to construct the transition
    # matrix for each class of customer.
    for key in connections.keys():


        c = connections[key]

        if len(c) > 0:

            # Convert all the node names to their equivalent node number
            # and converting the probability into a weight for the edge
            c = list(map(lambda t: (names_to_nodes[t[0]], names_to_nodes[t[1]], {'weight': t[2]}), c))

            DG = nx.DiGraph()
            DG.add_edges_from(c)

            matrices[key] = nx.to_numpy_matrix(DG).tolist()
        else:
            # None of the nodes are connected and everyone just leaves when they have been
            # served
            matrices[key] = [[0.0 for i in range(num_nodes)] for j in range(num_nodes)]

    # Add the transition matrices
    params['Transition_matrices'] = matrices

    return params


with open('test.yml') as f:
    network = load(f.read())

    with open('params.json', 'w') as g:
       json.dump(build_params(network), g)
