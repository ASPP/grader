# global imports
import numpy as np
import json
np.random.seed(12345)


def print_groups(data, K, energy, targets, weights, names):
    '''prints dataset sorted into groups of size K, calculates energy of
    solution and average ratings for all groups

    '''
    print 'energy: %.2f' % (energy(data, K, targets, weights))
    for i in xrange(len(data) / K):
        print '#########################'
        print 'Group %d:' % (i)
        print [names['%d' % k] for k in data[i * K:(i + 1) * K, -1]]
        print 'Ratings:'
        print data[i * K:(i + 1) * K, :-1]
        print '-------------------------'
        print 'Group average:'
        print [round(x, 2) for x in np.mean(data[i * K:(i + 1) * K, :-1],
                                            axis=0)]
    print '#########################'
    print 'Target averages:'
    print np.mean(data[:, :-1], axis=0)


def optimize(data, K, rep, energy, targets, weights, p=0.):
    '''optimize dataset by randomly exchanging two items

    a pair is randomly picked and the change in energy is calculated.
    if the energy is lower afterwards, keep the change. with a
    probability of p, a change that leads to increase in energy is
    accepted.

    a function which calculates the energy must be provided.

    '''
    for _ in xrange(rep):
        idx = np.random.randint(0, len(data), 2)
        E1 = energy(data, K, targets, weights)
        data[idx] = data[idx[::-1]]
        E2 = energy(data, K, targets, weights)
        if E1 < E2:
            if p < np.random.rand():
                data[idx] = data[idx[::-1]]


def energy_mudeviation(data, K, mu):
    '''penalize deviation from target group mean mu

    '''
    return np.sum([(np.mean(data[i * K:(i + 1) * K]) - mu) ** 2 for i in xrange(len(data) / K)])


def energy_nonuniform(data, K):
    '''penalize deviation from uniform distribution

    '''
    return np.sum([np.var(data[i * K:(i + 1) * K]) for i in xrange(len(data) / K)])


def energy(data, K, targets, weights):
    '''calculate total energy of array of tuples with the form (gender,
    python, programming, open_source) rating prefactors are (more or
    less) arbitrary choices (see below)

    '''

    assert(len(np.shape(data)) == 2)
    assert(np.shape(data)[1] == len(targets))
    E = weights[0] * energy_mudeviation(data[:, 0], K, targets[0])
    E += weights[1] * energy_mudeviation(data[:, 1], K, targets[1])
    E += weights[2] * energy_mudeviation(data[:, 2], K, targets[2])
    E += weights[3] * energy_mudeviation(data[:, 3], K, targets[3])
    # we only need this term for open source, as all others ratings
    # are "binary"
    E += weights[4] * energy_nonuniform(data[:, 3], K)
    return E

######################################################################

# parameters
N = 30  # total number of persons
K = 6  # number of persons per group
Nseeds = 30  # number of different initial conditions (trials) for optimization
rep = 300  # number of optimizations steps in each trial

# here we define how to weight different contributions to the total
# energy, for example can we decide that matching the average python
# knowledge is more important than avoiding very strong and very weak
# people in the same group
weights = np.array([2., 2., 2., 2., 1.5])
weights *= 1. / np.sum(weights)

######################################################################

# loads the data extracted from grader with 'loadpy extract_data.py'
f = open('data.json', 'r')
data = json.load(f)
f.close()

rated = np.array(data['rated'])
names = data['names']

# use average of all students as target values (->optimal solution
# would be if all groups had this strength)
targets = np.mean(rated, axis=0)

data = np.random.permutation(rated)
print 'initial energy', energy(data, K, targets, weights)

E_seeds = []
data_seeds = []

for seed in np.arange(0, Nseeds):
    # create different initial condition for every trial
    np.random.seed(seed * 12345)
    data = np.random.permutation(rated)
    optimize(data, K, rep, energy, targets, weights)
    E_seeds.append(energy(data, K, targets, weights))
    data_seeds.append(data)

print 'final energy of all trials:'
print [round(E, 4) for E in E_seeds]
print 'optimal group distribution:'
pos = np.argsort(E_seeds)
print_groups(data_seeds[pos[0]], K, energy, targets, weights, names)
