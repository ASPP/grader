import functools

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

    def argsort(self):
        return vector(key for key,val in sorted(zip(self, xrange(len(self)))))

def vectorize(generator_func):
    def wrapper(*args, **kwargs):
        return vector(generator_func(*args, **kwargs))
    return functools.update_wrapper(wrapper, generator_func)
