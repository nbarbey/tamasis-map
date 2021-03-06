import numpy as np
from tamasis import *
from tamasis.utils import _distance_slow, diff as udiff, diffT, diffTdiff, shift

class TestFailure(Exception):
    pass

origin = (1.,)
d0 = np.arange(5.)*0.5
d1 = distance(5, origin=origin, resolution=0.5)
d2 = _distance_slow((5,), origin, [0.5], None)
if any_neq(d0, d1): raise TestFailure()
if any_neq(d0, d2): raise TestFailure()

origin = (1.,2.)
d0 = np.array([[2., np.sqrt(5), np.sqrt(8)], [0,1,2]])
d1 = distance((2,3), origin=origin, resolution=(1.,2.))
d2 = _distance_slow((2,3), origin, [1.,2.], None)
if any_neq(d0, d1): raise TestFailure()
if any_neq(d0, d2): raise TestFailure()

m = gaussian((1000,1000),fwhm=10, resolution=0.1)
if np.sum(m[500,:] > np.max(m)/2) != 100: raise TestFailure()
m = gaussian((1000,1000),fwhm=10, resolution=1)
if np.sum(m[500,:] > np.max(m)/2) != 10: raise TestFailure()
m = gaussian((1000,1000),fwhm=100, resolution=10)
if np.sum(m[500,:] > np.max(m)/2) != 10: raise TestFailure()

m = airy_disk((1000,1000),fwhm=10, resolution=0.1)
if np.sum(m[500,:] > np.max(m)/2) != 100: raise TestFailure()
m = airy_disk((1000,1000),fwhm=10, resolution=1)
if np.sum(m[500,:] > np.max(m)/2) != 10: raise TestFailure()
m = airy_disk((1000,1000),fwhm=100, resolution=10)
if np.sum(m[500,:] > np.max(m)/2) != 10: raise TestFailure()

# diff
for axis in range(2):
    a=np.random.random_integers(1, 10, size=(8,9)).astype(float)
    ref = -np.diff(a, axis=axis)
    s = ref.shape
    udiff(a, axis=axis)
    a[:s[0],:s[1]] -= ref
    if any_neq(a, 0): raise TestFailure()

for axis in range(3):
    a=np.random.random_integers(1, 10, size=(8,9,10)).astype(float)
    ref = -np.diff(a, axis=axis)
    s = ref.shape
    udiff(a, axis=axis)
    a[:s[0],:s[1],:s[2]] -= ref
    if any_neq(a, 0): raise TestFailure()

for axis in range(4):
    a=np.random.random_integers(1, 10, size=(8,9,10,11)).astype(float)
    ref = -np.diff(a, axis=axis)
    s = ref.shape
    udiff(a, axis=axis)
    a[:s[0],:s[1],:s[2],:s[3]] -= ref
    if any_neq(a, 0): raise TestFailure()

# shift

for a in (np.ones(10),np.ones((12,10))):
    for s in (10,11,100,-10,-11,-100):
        b = a.copy()
        shift(b,s,axis=-1)
        if any_neq(b, 0): raise TestFailure()

a = np.array([[1.,1.,1.,1.],[2.,2.,2.,2.]])
shift(a, [1,-1], axis=1)
if any_neq(a, [[0,1,1,1],[2,2,2,0]]): raise TestFailure()

a = np.array([[0.,0,0],[0,1,0],[0,0,0]])
b = a.copy()
shift(b, 1, axis=0)
if any_neq(b, np.roll(a,1,axis=0)): raise TestFailure()
shift(b, -2, axis=0)
if any_neq(b, np.roll(a,-1,axis=0)): raise TestFailure()
b = a.copy()
shift(b, 1, axis=1)
if any_neq(b, np.roll(a,1,axis=1)): raise TestFailure()
shift(b, -2, axis=1)
if any_neq(b, np.roll(a,-1,axis=1)): raise TestFailure()

# profile

def profile_slow(input, origin=None, bin=1.):
    d = distance(input.shape, origin=origin)
    d /= bin
    d = d.astype(int)
    m = np.max(d)
    p = np.ndarray(int(m+1))
    n = np.zeros(m+1, int)
    for i in range(m+1):
        p[i] = np.mean(input[d == i])
        n[i] = np.sum(d==i)
    return p, n

d = distance((10,20))
x, y, n = profile(d, origin=(4,5), bin=2., histogram=True)
y2, n2 = profile_slow(d, origin=(4,5), bin=2.)
if any_neq(y, y2[0:y.size]): raise TestFailure()
if any_neq(n, n2[0:n.size]): raise TestFailure()
