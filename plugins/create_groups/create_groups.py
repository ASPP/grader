# This script must be run within grader using the command "loadpy"
import collections
import hashlib
import os
import csv
import unicodedata
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
REJECTION_PROBABILITY = 0.01
# Minimum number of independent trials to run
MIN_TRIALS = 5
# Maximum number of rejected step in the optimization routine before
# declaring convergence
MAX_REJECTIONS = 200
# Relative and absolute tolerance to consider two values of energy equal
RTOL, ATOL = 0.001, 1e-10
# Output file
CSV = 'list_groups.csv'

### DO NOT NEED TO CHANGE BELOW THIS LINE ###

# Set parameters from config file
# Number of participants
NSTUDENTS = int(config['formula']['accept_count'])
# How many students in a group
GSIZE = config['groups_parameters']['group_size']
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
# of unsigned 32bit integers. Then sum them up (normalizing by the number
# of trials to avoid an integer overflow down the road).
# The result is one nice random seed.
RANDOM_SEED = np.fromstring(hashlib.sha512(RANDOM_SEED).digest(),
                            dtype=np.uint32).sum(dtype=np.uint32)

def participants():
    """Generator that returns persons labeled CONFIRMED"""
    for person in applications.applicants:
        try:
            labels = person.labels
        except Exception:
            continue
        if 'CONFIRMED' in labels:
            # get a proposed login name for forgejo
            # try to get a ascii-only form of the firstname
            login = unicodedata.normalize('NFKD', person.name).encode('ascii', 'ignore').decode('ascii').lower()
            person.login = login.split()[0].split('-')[0]
            # we set a fake password here, the real one will be generated later by a secret script
            person.password = str(person.born)
            yield person


def extract_data():
    """Rate all participants based on their skills.

    Returns a dictionary with mapping {idx : name} and a list
    of tuples: (skill1_rate, skill2_rate, ..., idx)
    """
    # transform confirmed list into useful format for generating groups
    # a single entry will contain
    # the idx and the ordered dict are necessary to keep track of names
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
        people[(person.fullname, person.email, person.login, person.password)] = rates

    # security check
    assert(len(people) == NSTUDENTS)
    return people


def name(idx, people):
    """Return a name given an index in the people database"""
    for (fullname, email, login, password), skill in people.items():
        if skill[0] == idx:
            return (fullname, email, login, password)

def group(i):
    """Return a slice object that represents group i in the dataset"""
    return slice(i * GSIZE, (i + 1) * GSIZE)


def optimize(data, energy, p=REJECTION_PROBABILITY):
    """Minimize energy of a dataset by randomly exchanging two items.

    Two items are randomly picked which don't belong to the same group,
    their position is swapped and the change in energy is calculated.
    If the energy is lower afterwards, keep the change, otherwise
    reject the change with a probability p.
    A function which calculates the energy must be provided."""

    rejected = 0
    count = 0
    p = 1-p
    #for i in range(REPETITIONS):
    while True:
        count += 1
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
            rejected += 1
        elif np.isclose(E_before, E_after, rtol=RTOL, atol=ATOL):
            # there was a minimal improvement but let's count it as a rejection
            rejected += 1
        else:
            # this was a good step, let's reset the rejection counter
            rejected = 0
        if rejected > MAX_REJECTIONS:
            # we had enough rejections, no point in optimizing further
            return count


def energy_mudeviation(skill):
    """Penalize deviation of a group from the mean over all groups for a certain
    skill."""
    return np.std([skill[group(i)].mean() for i in range(NGROUPS)])


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
    return np.std([skill[group(i)].std() for i in range(NGROUPS)])


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
    E_trial = []
    data_trial = []

    # set the random seed
    np.random.seed(RANDOM_SEED)

    # Run several independent trials until we converge to a good solution
    print('Running trials...')
    trial = 0
    while True:
        trial += 1
        # create different initial condition for every trial
        #np.random.seed(np.uint32(trial) * RANDOM_SEED)
        # IMPORTANT: data gets modified in place in the optimize
        # function! Do not generate copies here!
        data = np.random.permutation(in_data)
        count = optimize(data, energy)
        # final energy
        E = energy(data)
        # store the final energy of the trial
        E_trial.append(E)
        # store the final configuration of the trial
        data_trial.append(data)
        # give a bit of a progress report
        print('Trial #%d(%d):'%(trial, count), E)
        # collect a minimum of trials
        if trial < MIN_TRIALS: continue

        # if we did not improve much in this last step, we converged
        E_min = min(E_trial[:-1])
        if E <= E_min and np.isclose(E, E_min, rtol=RTOL, atol=ATOL):
            best_trial = np.argmin(E_trial)
            best = data_trial[best_trial]
            print('Converged! Best trial #%d,'%(best_trial+1),
                  'Energy:', E_trial[best_trial])
            break

    # calculate optimal skill distribution: that is the average over all students
    opt_skills = in_data.mean(axis=0)[1:]
    opt_skills_dev = in_data.std(axis=0)[1:]
    print('Optimal:', opt_skills.round(7))
    # open CSV output
    with open(CSV, 'wt') as csv:
        # write header
        csv.write('$FULLNAME$;$EMAIL$;$LOGIN$;$PASSWORD$;$TEAMS$\n')
        for i in range(NGROUPS):
            print('Group %d:'%i, best[group(i), 1:].mean(axis=0).round(7))
            for member in best[group(i),0]:
                # write member line
                csv.write(';'.join(name(member, people))+';students,group'+str(i)+'\n')

    # print relative deviation from optimal skills
    print('Deviation from optimal skills (percent):')
    dev = [(best[group(i), 1:].mean(axis=0)-opt_skills)/opt_skills\
            for i in range(NGROUPS)]
    print((100*np.abs(dev)).round(1))
    print('Deviation from optimal skills standard deviations (percent):')
    dev = [(best[group(i), 1:].std(axis=0)-opt_skills_dev)/opt_skills\
           for i in range(NGROUPS)]
    print((100*np.abs(dev)).round(1))
    print('Wrote group list to "'+CSV+'"')

main()
