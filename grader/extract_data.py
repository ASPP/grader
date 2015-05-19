import json

# retrieved confirmed applicants
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
# (gender, python, git, programming, open source, id) ratings as a tuple
# the id is necessary to generate the list of names in the end
rated = []
names = {}
i = 0
for person in confirmed:
    gender = int(person.female)
    # print(person.vcs.split(',')[0])  # add git rating
    print(list(config['groups_open_source_rating'].values()))
    python = config['groups_python_rating'][person.python.split('/')[0].lower()]
    programming = config['groups_programming_rating'][person.programming.split('/')[0].lower()]
    open_source = config['groups_open_source_rating'][person.open_source.split(' ')[0].lower()]
    rated.append((gender, python, programming, open_source, i))
    names[i] = person.fullname.lower()
    i += 1
                  
data = {
    'rated': rated,
    'names': names,
}
f = open('data.json', 'w')
json.dump(data, f)
f.close()
