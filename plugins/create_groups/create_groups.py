# global imports
import numpy as np

# fix random seed
np.random.seed(12345)


def extract_data():
    '''retrieved confirmed students and rate them

    retrieve all confirmed students from applications by checking the
    labels and rate them using the ratings defined in
    grader.conf. returns a dictionary with mapping id->name and a list
    of tuples.

    '''
    confirmed = []
    for person in applications:
        try:
            labels = config.sections['labels'][person.fullname.lower()]
        except Exception:
            labels = []
        if 'CONFIRMED' in labels:
            confirmed.append(person)
    assert(len(confirmed) == 30)

    # transform confirmed list into useful format for generating groups
    # a single entry will contain
    # (gender, python, programming, vcs, open source, id) ratings as a tuple
    # the id is necessary to generate the list of names in the end
    rated = []
    names = {}
    for i, person in enumerate(confirmed):
        gender = int(person.female)
        python = config['groups_python_rating'][person.python.split('/')[0].lower()]
        programming = config['groups_programming_rating'][person.programming.split('/')[0].lower()]
        vcs = config['groups_vcs_rating'][person.vcs.split(',')[0].lower()]
        open_source = config['groups_open_source_rating'][person.open_source.split(' ')[0].lower()]
        rated.append((gender, python, programming, vcs, open_source, i))
        names[i] = person.fullname.lower()

    return names, rated


def print_groups(data, K, energy, weights, names):
    '''prints dataset sorted into groups of size K, calculates energy of
    solution and average ratings for all groups

    '''
    print('energy: %.4f' % (energy(data, K, weights)))
    for i in range(int(len(data) / K)):
        print('#########################')
        print('Group %d:' % (i))
        print([names[int(k)] for k in data[i * K:(i + 1) * K, -1]])
        print('Ratings:')
        print(np.round(data[i * K:(i + 1) * K, :-1], 2))
        print('-------------------------')
        print('Group average:')
        print(np.round([x for x in np.mean(data[i * K:(i + 1) * K, :-1],
                                           axis=0)], 2))
    print('#########################')
    print('Target averages:')
    print(np.round(np.mean(data[:, :-1], axis=0), 2))
    print('#########################')
    print('Rel. deviation from target averages:')
    for i in range(int(len(data) / K)):
        print(np.round((np.array([round(x, 2) for x in np.mean(data[i * K:(i + 1) * K, :-1], axis=0)]) -
                        np.mean(data[:, :-1], axis=0)) / np.mean(data[:, :-1], axis=0), 2))
    print('-------------------------')
    print('Rel. deviation from target standard deviations:')
    for i in range(int((len(data) / K))):
        print(np.round((np.array([round(x, 2) for x in np.std(data[i * K:(i + 1) * K, :-1], axis=0)]) -
                        np.std(data[:, :-1], axis=0)) / np.std(data[:, :-1], axis=0), 2))


def optimize(data, K, rep, energy, weights, p=0.):
    '''optimize dataset by randomly exchanging two items

    a pair is randomly picked and the change in energy is calculated.
    if the energy is lower afterwards, keep the change. with a
    probability of p, a change that leads to increase in energy is
    accepted.

    a function which calculates the energy must be provided.

    '''
    for i in range(rep):
        idx = np.random.randint(0, len(data), 2)
        while idx[0] // K == idx[1] // K:
            idx = np.random.randint(0, len(data), 2)
        E1 = energy(data, K, weights)
        data[idx] = data[idx[::-1]]
        E2 = energy(data, K, weights)
        if E1 < E2 or (p > 0. and p > np.random.rand()):
            data[idx] = data[idx[::-1]]


def energy_mudeviation(data, K, mu):
    '''penalize deviation from target group mean mu

    the collection of students defines an average level for all
    criteria (i.e., gender, python skill, etc.). this term penalizes
    large deviations of the average of a single group from the average
    of all students.

    '''
    return np.std([np.mean(data[i * K:(i + 1) * K]) for i in range(int(len(data) / K))])


def energy_nonuniform(data, K):
    '''penalize deviation from uniform distribution

    if a rating is not binary, mulitple solutions can lead to the same
    average. this term penalizes non-uniform distributions in single
    groups (i.e., (0,0,2,2) would be rated worse than (0,1,1,2)), by
    penalizing deviations of the standard deviation in a group from
    the standard deviation of all students.

    '''
    return np.std([np.std(data[i * K:(i + 1) * K]) for i in range(int(len(data) / K))])


def energy(data, K, weights):
    '''calculate total energy of a certain configuration of students

    data is an array of tuples with the form (gender, python,
    programming, open_source). weights can be used if certain terms
    are more important than others.

    '''
    # normalize the weights
    weights *= 1. / np.sum(weights)

    # use average of all students as target values (->optimal solution
    # would be if all groups had this strength)
    targets = np.mean(rated, axis=0)

    assert(len(np.shape(data)) == 2)
    assert(np.shape(data)[1] == len(targets))
    E = weights[0] * energy_mudeviation(data[:, 0], K, targets[0])
    E += weights[1] * energy_mudeviation(data[:, 1], K, targets[1])
    E += weights[2] * energy_mudeviation(data[:, 2], K, targets[2])
    E += weights[3] * energy_mudeviation(data[:, 3], K, targets[3])
    E += weights[4] * energy_mudeviation(data[:, 4], K, targets[4])
    return E

######################################################################
# here we define how to weight different contributions to the total
# energy. for example, we could decide that matching the average
# python knowledge is more important than matching the average gender.
# as a default we opt for equal weight in all criteria
weights = np.array([1., 1., 1., 1., 1.])
######################################################################

names, rated = extract_data()

initial_E_seeds = []
E_seeds = []
data_seeds = []

for seed in np.arange(0, config['groups_parameters']['number_trials']):
    # create different initial condition for every trial
    np.random.seed(seed * 12345)
    data = np.random.permutation(rated)
    initial_E_seeds.append(energy(data, config['groups_parameters']['group_size'], weights))
    optimize(data, config['groups_parameters']['group_size'], config['groups_parameters']['repetitions'], energy, weights)
    E_seeds.append(energy(data, config['groups_parameters']['group_size'], weights))
    data_seeds.append(data)

print('initial energy of all trials:')
print('mean: %.4f, std: %.4f' % (np.mean(initial_E_seeds), np.std(initial_E_seeds)))
print('final energy of all trials:')
print('mean: %.4f, std: %.4f' % (np.mean(E_seeds), np.std(E_seeds)))
print('optimal group distribution:')
pos = np.argsort(E_seeds)
print_groups(data_seeds[pos[0]], config['groups_parameters']['group_size'], energy, weights, names)
# TODO write data in csv file for later use
