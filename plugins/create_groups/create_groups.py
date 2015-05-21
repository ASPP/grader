# This script must be run within grader using the command "loadpy"
import collections
import hashlib
import numpy as np

# Here we define how to weight different contributions to the total
# energy. For example, we could decide that matching the average
# python knowledge is more important than matching the average gender.
# As a default we opt for equal weight for all skills.
# Note that weights should be defined within the range [0,1].
SKILL_WEIGHTS = collections.OrderedDict([
                 ('gender',       1.),
                 ('python',       1.),
                 ('programming',  1.),
                 ('vcs',          1.),
                 ('open_source' , 1.),
                ])

# Probability of accepting one step in the wrong direction
# in the stochastic algorithm
REJECTION_PROBABILITY = 1.

# Print a lot of debugging output
DEBUG = True

### DO NOT NEED TO CHANGE BELOW THIS LINE ###

# Set parameters from config file
# Number of participants
NSTUDENTS = int(config['formula']['accept_count'])
# Labels (contains the CONFIRMED labels)
LABELS = config.sections['labels']
# How many students in a group
GSIZE = config['groups_parameters']['group_size']
# How many independent trials to run of the stochastic algorithm
TRIALS = config['groups_parameters']['number_trials']
# How long to run each independent trial
REPETITIONS = config['groups_parameters']['repetitions']
# Random seed (expected to be a UTF8 string, typically "City YEAR")
RANDOM_SEED = config['groups_random_seed']['seed']

# Derived constants
# Number of groups
NGROUPS = NSTUDENTS//GSIZE
# The ratings for each skill
RATINGS = { skill : config['_'.join(('groups', skill, 'rating'))]\
            for skill in SKILL_WEIGHTS }
# Weights for the skills
WEIGHTS = np.array(list(SKILL_WEIGHTS.values()))
WEIGHTS /= WEIGHTS.sum()

# interpret random seed as bytes
RANDOM_SEED = bytes(RANDOM_SEED, encoding='utf8')
# make nice cryptographic dance to get a proper random seed.
# idea: get a hash of the bytes and interpret the result as an array
# of unsigned 64bit integers. Then sum them up (normalizing by the number
# of trials to avoid an integer overflow down the road).
# The result is one nice random seed.
RANDOM_SEED = np.fromstring(hashlib.sha512(RANDOM_SEED).digest(),
                            dtype=np.uint64).sum()//np.uint64(TRIALS)

def debug(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


def participants():
    """Generator that returns persons labeled CONFIRMED"""
    for person in applications:
        try:
            labels = LABELS[person.fullname.lower()]
        except Exception:
            continue
        if 'CONFIRMED' in labels:
            yield person


def extract_data():
    """Rate all participants based on their skills.

    Returns a dictionary with mapping {idx : name} and a list
    of tuples: (skill1_rate, skill2_rate, ..., idx)
    """
    # transform confirmed list into useful format for generating groups
    # a single entry will contain
    # (idx, gender, python, programming, vcs, open source) ratings as a tuple
    # the idx is necessary to keep track of the people's names
    people = collections.OrderedDict()
    for idx, person in enumerate(participants()):
        rates = [idx]
        for field in SKILL_WEIGHTS:
            value = RATINGS[field]
            attr = getattr(person, field).lower()
            for splitchar in ' /,':
                attr = attr.split(splitchar)[0]
            rate = value[attr]
            rates.append(rate)
        people[person.fullname] = rates

    # security check
    assert(len(people) == NSTUDENTS)
    return people


def group(i):
    """Return a slice object that represents group i in the dataset"""
    return slice(i * GSIZE, (i + 1) * GSIZE)


def print_groups(data, energy, names):
    """prints dataset sorted into groups of size GSIZE, calculates energy of
    solution and average ratings for all groups"""

    debug('energy: %.4f' % (energy(data)))
    for i in range(NGROUPS):
        debug('#########################')
        debug('Group %d:' % (i))
        debug('Ratings:')
        debug(np.round(data[group(i), 1:], 2))
        debug('-------------------------')
        debug('Group average:')
        debug(np.round([x for x in np.mean(data[group(i), 1:],
                                        axis=0)], 2))
        print([names[int(k)] for k in data[group(i), 0]])
        debug('#########################')

    debug('Target averages:')
    debug(np.round(np.mean(data[:, 1:], axis=0), 2))
    debug('#########################')
    debug('Rel. deviation from target averages:')
    for i in range(NGROUPS):
        debug(np.round((np.array([round(x, 2) \
                    for x in np.mean(data[group(i), 1:], axis=0)]) -
                    np.mean(data[:, 1:], axis=0)) / np.mean(data[:, 1:],
                                                             axis=0), 2))
    debug('-------------------------')
    debug('Rel. deviation from target standard deviations:')
    for i in range(NGROUPS):
        debug(np.round((np.array([round(x, 2) \
                    for x in np.std(data[group(i), 1:], axis=0)]) -
                    np.std(data[:, 1:], axis=0)) / np.std(data[:, 1:],
                                                           axis=0), 2))


def optimize(data, energy, p=REJECTION_PROBABILITY):
    """Minimize energy of a dataset by randomly exchanging two items.

    Two items are randomly picked which don't belong to the same group,
    their position is swapped and the change in energy is calculated.
    If the energy is lower afterwards, keep the change, otherwise
    reject the change with a probability p.
    a function which calculates the energy must be provided."""

    for i in range(REPETITIONS):
        # pick two random students
        # make sure the two picked ones are not
        # in the same group
        while True:
            idx = np.random.randint(0, NSTUDENTS, 2)
            if idx[0] // GSIZE != idx[1] // GSIZE:
                break

        E_before = energy(data)
        data[idx] = data[idx[::-1]]
        E_after = energy(data)
        # write condition like this to avoid consuming
        # random numbers when p = 1.
        if E_before < E_after and (p==1 or p > np.random.rand()):
            # reject the change
            data[idx] = data[idx[::-1]]


def energy_mudeviation(skill):
    """Penalize deviation of a group from the mean over all groups for a certain
    skill."""
    return np.std([np.mean(skill[group(i)]) for i in range(NGROUPS)])


def energy_nonuniform(skill):
    """Penalize deviation of the group distribution for a certain skill from the
       uniform distribution.

    If a skill is not binary, mulitple solutions can lead to the same
    average. this term penalizes non-uniform distributions in single
    groups (i.e., (0,0,2,2) would be rated worse than (0,1,1,2)), by
    penalizing deviations of the standard deviation in a group from
    the standard deviation of all students."""
    # this is not used right now, as it doesn't seem to make a difference
    # most probably because it is too small of a term:
    # std(std) vs std(mean)
    return np.std([np.std(skill[group(i)]) for i in range(NGROUPS)])


def energy(data):
    """Calculate total energy of a certain configuration of students."""
    energy = 0
    for skill in range(len(WEIGHTS)):
        # skill+1 is needed to ignore the idx column in the data
        energy += WEIGHTS[skill] * energy_mudeviation(data[:, skill+1])
    return energy


def main():
    people = extract_data()
    in_data = np.array(list(people.values()))
    E0_trial = []
    E_trial = []
    data_trial = []

    # set the random seed
    np.random.seed(RANDOM_SEED)

    print('Running trials...')
    for seed in np.arange(1, TRIALS+1, dtype=np.uint64):
        # give a bit of a progress report
        print('Trial: %d/%d'%(seed,TRIALS)+20*'\b', end='', flush=True)
        # create different initial condition for every trial
        np.random.seed(seed * RANDOM_SEED)
        # IMPORTANT: data gets modified in place in the optimize
        # function! Do not generate copies here!
        data = np.random.permutation(in_data)
        # store the starting energy of the trial
        if DEBUG: E0_trial.append(energy(data))
        optimize(data, energy)
        # store the final energy of the trial
        E_trial.append(energy(data))
        # store the final configuration of the trial
        data_trial.append(data)

    print()
    debug('initial energy of all trials:')
    debug('mean: %.4f, std: %.4f' % (np.mean(E0_trial),
                                  np.std(E0_trial)))
    debug('final energy of all trials:')
    debug('mean: %.4f, std: %.4f' % (np.mean(E_trial), np.std(E_trial)))
    print('optimal group distribution:')
    pos = np.argsort(E_trial)
    names = {people[name][0]:name for name in people}

    print_groups(data_trial[pos[0]], energy, names)
    # TODO write data in csv file for later use

main()
