import functools
import numpy as np


# In all places when you have code like this:
#
#     def do_something():
#        l = []
#        for i in range(10):
#            l.append(i)
#        return l
#
# you can instead do this
#
#    @vectorize
#    def do_something():
#        for i in range(10)
#        yield i
#
# this way the code only contains the iteration logic, and you have
# delegated the book-keeping to the decorator
#
# This class is also used whenever you want an easy way to extract
# attributes from all the elements of a sequence. So for example if you have
#
#    l = [person1, person2, person3]
#    names = (person.name for person in l)
#
# you can instead do
#
#    v = vector(l)
#    names = l.name
class vector(list):
    """A vector of objects with easy extraction:
           v.E == vector(elem.E for elem in v)

    >>> V = vector((1, 2, 3, 4))
    >>> V.numerator
    array([1, 2, 3, 4])
    >>> list(V.denominator)
    [1, 1, 1, 1]

    Slice access returns a vector:
    >>> V[::-1]                           # doctest: +NORMALIZE_WHITESPACE
    vector[ 4, 3, 2, 1]
    >>> V[:3]                             # doctest: +NORMALIZE_WHITESPACE
    vector[ 1, 2, 3]

    >>> @vectorize
    ... def gen():
    ...     yield 1; yield 2; yield 3
    >>> f = gen()
    >>> f[0], f[1], f[2]
    (1, 2, 3)
    """

    def __getattr__(self, name):
        # array of tuples is not very usefull
        return vector(getattr(elem, name) for elem in self)

    def __repr__(self):
        return 'vector[\t'+',\n\t'.join([str(elem) for elem in self])+']'

    def __getitem__(self, i):
        if isinstance(i, slice):
            return vector(super(vector,self).__getitem__(i))
        else:
            return super(vector,self).__getitem__(i)

    def __getslice__(self, i, j):
        return vector(super(vector,self).__getslice__(i, j))

    def __add__(self, other):
        return vector(super(vector,self).__add__(other))

    def mean(self):
        valid = [arg for arg in self if arg is not None]
        if not valid:
            return float('nan')
        return np.nanmean(valid)

# wraps generators into a vector object
def vectorize(generator_func):
    def wrapper(*args, **kwargs):
        return vector(generator_func(*args, **kwargs))
    return functools.update_wrapper(wrapper, generator_func)

# wraps a generator into a dictionary
def dictify(generator_func):
    def wrapper(*args, **kwargs):
        return dict(generator_func(*args, **kwargs))
    return functools.update_wrapper(wrapper, generator_func)
